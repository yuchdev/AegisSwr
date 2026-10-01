"""Rich terminal view adapters.

Two views subscribe to the core :class:`~aegis_swr.core.events.EventBus` and
render an investigation live:

* :class:`WarRoomView` - a full-screen, three-pane "Synthetic War Room"
  (Evidence Stream | Forensic Agents / Investigation Process) built on
  :class:`rich.layout.Layout` inside a :class:`rich.live.Live`. See
  ``docs/adr/new-ui_sketches-rich-based-design.md``.
* :class:`RichView` - a simpler single-column trail, kept as a fallback for
  narrow terminals.

:func:`make_view` selects between them by terminal width.
:func:`render_verdict` prints the final report once the live block freezes.
"""

from __future__ import annotations

import codecs
import io
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Optional, TextIO, Union, cast

from loguru import logger
from rich.console import Console, Group, RenderableType
from rich.json import JSON
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.text import Text
from rich.theme import Theme

from aegis_swr.core.events import (
    AgentSpoke,
    ConsensusEvaluated,
    DomainEvent,
    EventBus,
    EvidenceExtracted,
    HumanInputRequired,
    InvestigationCompleted,
    InvestigationStarted,
    PanelAgentDescriptor,
    PanelResolved,
)
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    ConfidenceLevel,
    IncidentSource,
    RCAReport,
)
from aegis_swr.views.evidence_detail import (
    describe_log_window,
    file_properties,
    pcap_metadata,
)

#: Encode error handlers that cannot raise on the glyphs the view emits, so a
#: stream already using one (paired with UTF-8) is left untouched.
_SAFE_STREAM_ERRORS: Final[frozenset[str]] = frozenset({"replace", "backslashreplace", "xmlcharrefreplace"})


def _ensure_unicode_safe_stream(stream: Optional[TextIO]):
    """Make *stream* able to carry the view's Unicode glyphs without ever raising.

    Every war-room frame contains non-ASCII glyphs (``✔``, the Braille spinner,
    box-drawing rules). When stdout is **redirected** on Windows, Python opens it
    with the locale encoding (``cp1252``) rather than UTF-8, and Rich's write
    raises :class:`UnicodeEncodeError`. That happens in ``Live.stop()``, i.e.
    *after* a full investigation has succeeded, so an encoding detail destroys a
    completed multi-minute analysis. Requiring ``PYTHONIOENCODING=utf-8`` from
    the caller is not a fix - it makes correct behaviour opt-in.

    Two independent guarantees are established, because each covers a failure the
    other does not:

    * **UTF-8 encoding** so the glyphs survive intact for a consumer that reads
      UTF-8 (a redirect into a file, a CI log).
    * **A non-strict error handler**, because UTF-8 alone is *not* sufficient
      here: incident text is decoded with ``errors="replace"``/``surrogateescape``
      upstream, so a dump or log can carry lone surrogates, which no UTF-8
      encoder will accept. ``replace`` degrades those to a placeholder instead of
      aborting the render.

    Note that ``surrogateescape`` is deliberately *not* treated as safe: on
    encode it only round-trips the ``U+DC80..U+DCFF`` range it produces itself,
    so a surrogate outside that range still raises.

    **This changes the bytes on the wire**: a redirected stream that previously
    got locale-encoded (or ASCII-substituted) output now receives UTF-8, so a
    consumer decoding with the system locale must be told to read UTF-8. That is
    the intended trade - ``cp1252`` cannot represent box-drawing at all, so
    preserving the locale encoding would reduce the whole war-room layout to
    ``?``. An operator who needs a specific codec can set ``PYTHONIOENCODING``,
    which is honoured verbatim; only the non-strict error handler is still forced
    on, since that alone is what prevents the crash.

    The stream is reconfigured in place (rather than wrapped) so ordering with
    plain ``print`` is preserved, and the call is idempotent - an already-safe
    stream is left untouched. Anything that cannot be reconfigured (a pytest
    capture buffer, :class:`io.StringIO`, a closed stream) is skipped with a DEBUG
    note: this is a best-effort hardening of the output path and must never
    itself break rendering.

    :param stream: The text stream the console will write to, or ``None``.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if stream is None or reconfigure is None:
        return

    try:
        current = codecs.lookup(stream.encoding).name if stream.encoding else ""
    except (LookupError, TypeError):
        current = ""

    errors_safe = getattr(stream, "errors", None) in _SAFE_STREAM_ERRORS

    if os.environ.get("PYTHONIOENCODING"):
        # An explicit PYTHONIOENCODING is a deliberate choice by the operator (a
        # consumer that must read a specific codec, say), so the encoding is left
        # exactly as they set it and only the crash-safety half is enforced.
        if errors_safe:
            return
        changes = {"errors": "replace"}
    elif current == "utf-8" and errors_safe:
        return  # already safe; nothing to do
    else:
        # Both arguments are always passed together: ``reconfigure(encoding=...)``
        # silently resets ``errors`` back to ``"strict"``, so setting the encoding
        # alone would *downgrade* a stream that already had a tolerant handler.
        changes = {"encoding": "utf-8", "errors": "replace"}

    try:
        reconfigure(**changes)
    except (OSError, ValueError, AttributeError) as exc:
        # An unreconfigurable stream keeps its original settings; rendering
        # proceeds and any loss is the caller's pre-existing behaviour. Only the
        # exception type is recorded - never the stream contents.
        logger.debug("console stream hardening skipped ({})", type(exc).__name__)


def make_console(*, stderr: bool = False) -> Console:
    """Console factory used by all Rich rendering.

    PyCharm's run window understands ANSI escape codes but is not a tty, so
    rich would otherwise disable the live display and all animation.  Force
    terminal mode there; everywhere else keep rich's auto-detection so piped
    output stays clean.

    The target stream is hardened by :func:`_ensure_unicode_safe_stream` first,
    so a redirected (non-UTF-8) stdout degrades a glyph instead of aborting the
    run. Routing every console through this factory is what keeps that guarantee
    global.
    """
    _ensure_unicode_safe_stream(sys.stderr if stderr else sys.stdout)
    force = True if os.environ.get("PYCHARM_HOSTED") else None
    return Console(stderr=stderr, force_terminal=force)


# ---------------------------------------------------------------------------
# Visual helpers
# ---------------------------------------------------------------------------

#: Spinner frames cycled for the active forensic agent (Braille dots).
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _activity_label(descriptor: PanelAgentDescriptor) -> str:
    """What the Investigation Process status line says while an agent works.

    Derived from the agent's behavioural :class:`~aegis_swr.core.schemas.AgentRole`
    (from the :class:`~aegis_swr.core.events.PanelResolved` event) so it works for
    any dynamically resolved panel rather than a fixed set of named agents. The
    adversarial arbiter gets a distinct "stress-testing" phrasing; every
    investigator gets a generic "analyzing" phrasing.

    :param descriptor: The resolved panel agent to describe.
    :type descriptor: PanelAgentDescriptor
    :return: A human-readable status line for the agent's active phase.
    :rtype: str
    """
    if descriptor.role is AgentRole.ARBITER:
        return f"{descriptor.display_name} is stress-testing the hypothesis…"
    return f"{descriptor.display_name} is analyzing the evidence…"


def _spinner_char(elapsed: float) -> str:
    """Return the spinner frame for *elapsed* seconds (advances at ~10 Hz)"""
    return SPINNER_FRAMES[round(elapsed * 10) % len(SPINNER_FRAMES)]


def _fmt_elapsed(seconds: float) -> str:
    """Format *seconds* as ``H:MM:SS`` (e.g. ``0:01:42``)"""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _fmt_stamp(seconds: float) -> str:
    """Format *seconds* as ``MM:SS`` for evidence line timestamps"""
    total = int(seconds)
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"


def _truncate(text: str, width: int) -> str:
    """Clip *text* to *width* columns, appending ``…`` when shortened"""
    if len(text) < width:
        return text
    if width <= 1:
        return ""
    return text[: width - 1] + "…"


def _conf_color(score: float) -> str:
    """Map a confidence *score* to a traffic-light Rich colour name.

    :param score: confidence in the range ``[0, 1]``.
    :return: ``green`` at >=0.80, ``yellow`` at >=0.50, otherwise ``red``.
    """
    return "green" if score >= 0.80 else "yellow" if score >= 0.50 else "red"


def _confidence_bar(score: float, width: int = 24) -> Text:
    """Render a unicode confidence bar: ``████████░░░░ 67%``"""
    filled = max(0, min(width, round(score * width)))
    color = _conf_color(score)
    bar = Text()
    bar.append("█" * filled, style=color)
    bar.append("░" * (width - filled), style="grey35")
    bar.append(f" {score:.0%}", style=f"bold {color}")
    return bar


def _bar(ratio: float, width: int, color: str) -> Text:
    """A plain filled/empty bar (no percent suffix)"""
    filled = max(0, min(width, round(ratio * width)))
    bar = Text()
    bar.append("█" * filled, style=color)
    bar.append("░" * (width - filled), style="grey35")
    return bar


# ---------------------------------------------------------------------------
# War-room view (full-screen, three panes)
# ---------------------------------------------------------------------------


#: War-room stream verbosity levels, least → most verbose. ``INFO`` is the curated
#: summary shown by default; ``TRACE`` surfaces every detail - the full per-artifact
#: evidence metadata in the Evidence Stream, and each agent's full reasoning in the
#: Investigation Process pane. The former ``DEBUG`` level is collapsed into ``TRACE``
#: (the log-subsystem split, plan Part III - Phase D).
EvidenceLevel = Literal["INFO", "TRACE"]

#: Rank of each level (higher == more verbose).  A buffered line tagged at level
#: *L* is shown when the active display level's rank is ``>=`` rank(*L*).
_LEVEL_RANK: dict[str, int] = {"INFO": 0, "TRACE": 1}


def _normalize_evidence_level(level: object) -> EvidenceLevel:
    """Coerce an arbitrary severity string to a known ``EvidenceLevel``.

    ``DEBUG`` collapses into ``TRACE``; logging-only levels (``WARNING`` /
    ``ERROR``) and anything unrecognised fall back to the ``INFO`` summary stream.
    """
    candidate = str(level).upper()
    if candidate in ("DEBUG", "TRACE"):
        return "TRACE"
    return "INFO"


#: Left indent (columns) for sub-detail evidence/process lines.
_SUBDETAIL_INDENT = 2


def _subdetail(body: Text, *, left: int = _SUBDETAIL_INDENT) -> Padding:
    """Wrap a sub-detail line in a plain left indent (no vertical gutter).

    The gutter character used to be baked into the line text (``"    │ …"``),
    so when a long line wrapped, the continuation row had no gutter and crossed
    it. ``Padding`` indents *every* wrapped row uniformly and draws no bar, so
    long lines wrap cleanly inside the panel border.
    """
    return Padding(body, (0, 0, 0, left))


def _plain_text(renderable: RenderableType) -> str:
    """Render *renderable* to a plain (uncoloured, unwrapped) text string.

    Used to serialise the Evidence Stream to a persisted transcript: a wide,
    no-colour capture console avoids ANSI escapes and line wrapping.
    """
    buffer = io.StringIO()
    capture = Console(file=buffer, width=10_000, no_color=True, force_terminal=False)
    capture.print(renderable)
    return buffer.getvalue().rstrip("\n")


@dataclass
class AgentState:
    """Live state for one forensic agent sub-panel"""

    status: Literal["STANDBY", "ANALYZING", "REVIEWING", "DONE"] = "STANDBY"
    confidence: float = 0.0
    finding: str = ""  # latest finding, truncated to panel width at render time


@dataclass
class _EvidenceLine:
    """One stream entry tagged with the verbosity it belongs to"""

    level: EvidenceLevel
    text: RenderableType


class _StreamLog:
    """A capped, time-revealed line buffer rendered as a scrolling tail.

    Backs both the Evidence Stream and the Investigation Process conversation.
    A line is appended the instant its event fires, so the buffer is the full
    record (the same data persisted to the report files).  The display reveals
    those lines at a fixed cadence (:attr:`reveal_interval`) and shows only the
    trailing window, so new lines stream in at the bottom and old ones scroll
    off the top once they exceed the visible height.  The user never scrolls
    back in the UI - the complete trail lives in the report.
    """

    def __init__(self, *, max_lines: int, reveal_interval: float):
        """Initialise an empty capped buffer with a reveal cadence.

        :param max_lines: maximum retained lines before the oldest are dropped.
        :param reveal_interval: seconds between surfacing one buffered line.
        """
        self._lines: list[_EvidenceLine] = []
        self._max_lines = max_lines
        self._reveal_interval = reveal_interval
        self._revealed = 0
        self._last_reveal = 0.0

    @property
    def lines(self) -> list[_EvidenceLine]:
        """The full (capped) record - every line ever appended, in order"""
        return self._lines

    def reset(self, now: float):
        """Clear the buffer for a fresh run, anchoring the reveal clock"""
        self._lines = []
        self._revealed = 0
        self._last_reveal = now

    def append(self, text: RenderableType, *, level: EvidenceLevel = "INFO"):
        """Append *text* tagged at *level*, trimming the oldest on overflow.

        :param text: the renderable line to record.
        :param level: verbosity tag controlling when the line is shown.
        """
        self._lines.append(_EvidenceLine(level=level, text=text))
        overflow = len(self._lines) - self._max_lines
        if overflow > 0:
            del self._lines[:overflow]
            # The reveal pointer indexes into the buffer; drop it by the same
            # amount so trimmed-off lines do not shift what is shown.
            self._revealed = max(0, self._revealed - overflow)

    def reveal_all(self):
        """Surface every buffered line at once (used when the run freezes)"""
        self._revealed = len(self._lines)

    def _advance(self, now: float, *, finished: bool):
        """Advance the reveal pointer by the lines due since the last tick.

        :param now: current monotonic timestamp.
        :param finished: when True, reveal every buffered line at once.
        """
        total = len(self._lines)
        if finished:
            self._revealed = total
            return
        if self._revealed >= total:
            # Caught up - keep the clock current so the next burst of lines
            # streams in fresh rather than appearing instantly.
            self._last_reveal = now
            return
        due = int((now - self._last_reveal) / self._reveal_interval)
        if due > 0:
            self._revealed = min(total, self._revealed + due)
            self._last_reveal += due * self._reveal_interval

    def visible(
        self,
        *,
        now: float,
        finished: bool,
        level: EvidenceLevel,
        max_lines: int,
    ) -> list[RenderableType]:
        """Advance the reveal clock and return the trailing visible lines"""
        self._advance(now, finished=finished)
        revealed = self._lines[: self._revealed]
        threshold = _LEVEL_RANK.get(level, 0)
        shown = [entry.text for entry in revealed if _LEVEL_RANK.get(entry.level, 0) <= threshold]
        return shown[-max_lines:]


class WarRoomView:
    """Full-screen three-pane war room driven by the :class:`EventBus`.

    The view is itself a Rich renderable (``__rich__``); a 12 fps ``Live``
    re-renders it each tick so spinners and clocks animate without any timer
    threads of our own.  Internal state is mutated by the event handlers and
    read by the ``_render_*`` methods.
    """

    _MAX_EVIDENCE = 500

    #: Seconds between revealing one buffered line to the display.  Lines are
    #: appended to the backing :class:`_StreamLog` the instant their event
    #: fires, but surfaced at this cadence so they appear to stream in and
    #: scroll past in real time rather than dumping at once.  At the 12 fps
    #: ``Live`` refresh this works out to ~14 lines/second.
    _REVEAL_INTERVAL = 0.07

    def __init__(
        self,
        console: Optional[Console] = None,
        *,
        auto_refresh: bool = True,
        level: str = "INFO",
        process_level: Optional[str] = None,
    ):
        """Initialise the war-room view state and verbosity channels.

        :param console: Rich console to render into; a default is built when omitted.
        :param auto_refresh: whether the backing ``Live`` refreshes on its own timer.
        :param level: Evidence Stream (left pane) verbosity level.
        :param process_level: Investigation Process (right pane) verbosity; defaults
            to *level* when not supplied.
        """
        self._console = console or make_console()
        self._auto_refresh = auto_refresh
        # Evidence Stream (left pane) verbosity.
        self._evidence_level: EvidenceLevel = _normalize_evidence_level(level)
        # Investigation Process (right pane) verbosity - an independent channel
        # (log-subsystem split, plan Part III); defaults to the evidence level when
        # not supplied. Consulted by the process-pane handlers/renderers below.
        self._process_level: EvidenceLevel = _normalize_evidence_level(
            process_level if process_level is not None else level
        )
        self._live: Optional[Live] = None

        # ── investigation state ──
        self._start = 0.0
        self._incident_label = "incident"
        self._mode = ""
        self._round = 0
        self._finished = False
        self._source: Optional[IncidentSource] = None

        # Two scrolling logs: extracted artifacts (Evidence Stream) and the
        # agent deliberation (Investigation Process).  Each keeps the full
        # record and reveals it gradually as a scrolling tail.
        self._evidence_log = _StreamLog(max_lines=self._MAX_EVIDENCE, reveal_interval=self._REVEAL_INTERVAL)
        self._process_log = _StreamLog(max_lines=self._MAX_EVIDENCE, reveal_interval=self._REVEAL_INTERVAL)
        # Per-run agent tracking, rebuilt from the PanelResolved event so the
        # view adapts to any resolved roster rather than a fixed panel. Empty
        # until the panel is announced.
        self._agents: dict[str, AgentState] = {}
        self._node_to_agent: dict[str, str] = {}
        self._next_agent: dict[str, Optional[str]] = {}
        self._agent_activity: dict[str, str] = {}
        self._panel_size = 0
        self._consensus_history: list[dict[str, object]] = []

        # Investigation-process bookkeeping.
        self._status = ""
        self._stage = 0
        self._stage_total = 7

    # -- attachment ---------------------------------------------------------

    def attach(self, bus: EventBus) -> Callable[[], None]:
        """Subscribe to *bus*; returns a detach function"""
        unsubscribers = [
            bus.subscribe(InvestigationStarted, self._on_started),
            bus.subscribe(EvidenceExtracted, self._on_evidence),
            bus.subscribe(PanelResolved, self._on_panel),
            bus.subscribe(AgentSpoke, self._on_agent),
            bus.subscribe(ConsensusEvaluated, self._on_consensus),
            bus.subscribe(InvestigationCompleted, self._on_completed),
            bus.subscribe(HumanInputRequired, self._on_hitl),
        ]

        def _detach():
            """Unsubscribe every handler and stop the Live war-room block."""
            for unsubscribe in unsubscribers:
                unsubscribe()
            self._stop_live()

        return _detach

    # -- event handlers -----------------------------------------------------

    def _on_started(self, event: DomainEvent):
        """Reset per-run state, label the incident, and start the Live war-room block."""
        assert isinstance(event, InvestigationStarted)
        source = event.source
        self._source = source
        if source.dump_path:
            self._incident_label = Path(source.dump_path).name
        elif source.log_paths:
            self._incident_label = ", ".join(Path(p).name for p in source.log_paths)
        else:
            self._incident_label = "incident"
        self._mode = source.mode.value

        # Reset so one view instance can render successive runs.
        self._start = time.monotonic()
        self._round = 1
        self._finished = False
        self._evidence_log.reset(self._start)
        self._process_log.reset(self._start)
        # Agent tracking is (re)built when the panel is resolved (see _on_panel),
        # which happens after evidence extraction, so start from an empty roster.
        self._agents = {}
        self._node_to_agent = {}
        self._next_agent = {}
        self._agent_activity = {}
        self._panel_size = 0
        self._consensus_history = []
        self._stage = 0
        self._stage_total = 7
        self._status = "Extracting evidence from crash artifacts…"

        self._stamp("CDB extraction started…", style="dim")

        self._live = Live(
            self,
            console=self._console,
            refresh_per_second=12,
            auto_refresh=self._auto_refresh,
            screen=False,
        )
        self._live.start()

    def _on_evidence(self, event: DomainEvent):
        """Stamp the extracted fault fields (and TRACE detail) into the Evidence Stream."""
        assert isinstance(event, EvidenceExtracted)
        brief = event.brief

        fault = str(brief.get("fault_class") or "unknown").upper()
        self._stamp_field("fault_class", fault, "bold magenta")
        if brief.get("faulting_module"):
            self._stamp_field("module", str(brief["faulting_module"]), "bold magenta")
        if brief.get("faulting_function"):
            self._stamp_field("function", str(brief["faulting_function"]), "bold magenta")
        score = brief.get("symbol_resolution_score")
        if score is not None:
            self._stamp_field("sym_coverage", f"{float(score):.0%}", "bold magenta")
        if brief.get("low_symbol_coverage_warning"):
            self._stamp("⚠ low symbol coverage", style="bold yellow")

        for i, frame in enumerate(brief.get("stack_frames", [])[:3]):
            func = frame.get("function") or frame.get("instruction_address") or "?"
            self._stamp_field(f"stack[{i}]", str(func), "blue")

        if self._evidence_level == "TRACE":
            self._emit_trace_evidence(brief)

        # The panel is not resolved yet (PanelResolved fires next); the first
        # agent is woken there once the roster is known.
        self._status = "Assembling the forensic panel…"
        self._refresh()

    def _on_panel(self, event: DomainEvent):
        """Build per-run agent tracking from the resolved panel.

        Replaces the former static ``AGENT_SEQUENCE``-derived constants: the
        node→name, name→next-name, and activity-label maps and the per-agent
        :class:`AgentState` roster are all rebuilt from :attr:`PanelResolved.panel`,
        so the view scales to any resolved panel. The stage budget is resized to
        the panel size, and the first agent is woken.
        """
        assert isinstance(event, PanelResolved)
        panel = event.panel
        self._panel_size = len(panel)
        self._agents = {descriptor.display_name: AgentState() for descriptor in panel}
        self._node_to_agent = {descriptor.node_name: descriptor.display_name for descriptor in panel}
        names = [descriptor.display_name for descriptor in panel]
        # Each agent's "next to wake" is the following one in speaking order; the
        # last (the arbiter) has no successor - the round then moves to consensus.
        self._next_agent = {name: (names[i + 1] if i + 1 < len(names) else None) for i, name in enumerate(names)}
        self._agent_activity = {descriptor.display_name: _activity_label(descriptor) for descriptor in panel}
        # Stage budget for round 1: evidence + one turn per agent + consensus +
        # verdict == len(panel) + 3 (matching the historical 7 for a 4-agent panel).
        self._stage_total = self._panel_size + 3
        if names:
            self._wake(names[0])
        self._refresh()

    def _emit_trace_evidence(self, brief: dict[str, object]):
        """Append the verbose TRACE evidence metadata for one incident.

        Surfaces the four detailed evidence categories on top of the curated INFO
        stream: the textual core-dump analysis (the *full* ``!analyze -v`` output),
        the temporal window of every analyzed log file, screenshot file properties,
        and network traffic capture metadata - plus the low-level fault fields.
        Every line is tagged ``TRACE`` so it shows only at the TRACE level.
        """
        # ── very detailed fault metadata ──
        for label, key in (
            ("dump_hash", "dump_hash"),
            ("exc_code", "exception_code_raw"),
            ("exc_addr", "exception_address"),
        ):
            value = brief.get(key)
            if value:
                self._stamp_field(label, str(value), "grey70", level="TRACE")

        # Full stack beyond the INFO top-three, with module/source detail.
        frames = cast("list[dict[str, object]]", brief.get("stack_frames", []))
        for i, frame in enumerate(frames):
            if i < 3:
                continue
            self._stamp_field(f"stack[{i}]", _format_frame(frame), "blue", level="TRACE")

        # ── 1. textual result of the core-dump analysis (full !analyze -v) ──
        excerpt = str(brief.get("raw_text_excerpt") or "").strip()
        if excerpt:
            self._stamp("core dump analysis (cdb !analyze -v):", style="dim", level="TRACE")
            for raw in excerpt.splitlines():
                self._add_evidence(_subdetail(Text(raw, style="grey62")), level="TRACE")

        src = self._source
        incident_ts = src.incident_timestamp if src else None

        # ── 2. ±2 minute window for every analyzed log file ──
        for raw_path in src.log_paths if src else []:
            props = file_properties(raw_path)
            self._stamp_field("log", props.describe(), "cyan", level="TRACE")
            self._add_evidence(
                _subdetail(Text(f"window {describe_log_window(incident_ts)}", style="grey62")),
                level="TRACE",
            )
        summary = str(brief.get("log_summary") or "").strip()
        if summary:
            self._stamp_field(
                "log_summary",
                f"{len(summary.splitlines())} clustered lines",
                "cyan",
                level="TRACE",
            )

        # ── 3. name and properties of every screenshot file ──
        for raw_path in src.screenshot_paths if src else []:
            props = file_properties(raw_path)
            self._stamp_field("screenshot", props.describe(), "magenta", level="TRACE")
        ui = brief.get("ui_context")
        if isinstance(ui, dict):
            elements = ui.get("ui_elements") or []
            ocr = str(ui.get("error_message") or "")
            self._add_evidence(
                _subdetail(
                    Text(
                        f"OCR: {len(elements)} elements, {len(ocr)} chars",
                        style="grey62",
                    )
                ),
                level="TRACE",
            )

        # ── 4. metadata of every network traffic capture ──
        for raw_path in src.network_capture_paths if src else []:
            props = file_properties(raw_path)
            self._stamp_field("netcap", props.describe(), "yellow", level="TRACE")
            for detail in _format_pcap(raw_path):
                self._add_evidence(_subdetail(Text(detail, style="grey62")), level="TRACE")

    def _on_agent(self, event: DomainEvent):
        """Record an agent's turn, log its finding, and wake the next agent."""
        assert isinstance(event, AgentSpoke)
        turn = event.turn

        # A higher turn number means a fresh debate round began: the previous
        # consensus check did not converge.
        if turn.turn_number > self._round:
            if self._consensus_history:
                self._consensus_history[-1]["converged"] = False
            self._round = turn.turn_number
            # One turn per panel agent + one consensus check for the extra round.
            self._stage_total += self._panel_size + 1
            note = f"threshold not reached - re-deliberating round {self._round}"
            self._stamp_process(note, style="dim italic")

        name = self._node_to_agent.get(event.node)
        message = turn.message.strip()
        finding = message.splitlines()[0] if message else ""
        if name and name in self._agents:
            state = self._agents[name]
            state.status = "DONE"
            state.confidence = turn.confidence_score
            state.finding = finding

        # Agent communication is process, not evidence: it goes to the
        # Investigation Process conversation log.
        short = (name or turn.agent).removesuffix(" Agent")
        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(f"{short} » ", style="bold")
        line.append(finding, style="italic")
        self._add_process(line)
        # At TRACE the Investigation Process pane surfaces the agent's full
        # reasoning, not just the headline - gated by its own process channel.
        if self._process_level == "TRACE":
            for extra in message.splitlines()[1:]:
                self._add_process(_subdetail(Text(extra, style="grey62")), level="TRACE")
        self._advance()

        nxt = self._next_agent.get(name) if name else None
        if nxt:
            self._wake(nxt)
        else:
            self._status = "Weighing panel consensus…"
        self._refresh()

    def _on_consensus(self, event: DomainEvent):
        """Log the weighted consensus for the round and reset agents to standby."""
        assert isinstance(event, ConsensusEvaluated)
        score = event.score
        level = ConfidenceLevel.from_score(score)
        self._consensus_history.append({"round": self._round, "score": score, "converged": None})

        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(f"consensus R{self._round}  ", style="bold")
        line.append(f"{score:.0%}  ", style=f"bold {_conf_color(score)}")
        line.append(level.value.upper(), style=_conf_color(score))
        self._add_process(line)

        # Next round (if any) reassigns agents; reset them to standby.
        for state in self._agents.values():
            state.status = "STANDBY"
        self._status = "Reviewing consensus - deciding next step…"
        self._advance()
        self._refresh()

    def _on_completed(self, event: DomainEvent):
        """Mark the final round converged, finish all agents, and freeze the view."""
        if self._consensus_history:
            self._consensus_history[-1]["converged"] = True
        for state in self._agents.values():
            state.status = "DONE"
        self._stamp_process("✔  investigation complete", style="bold green")
        self._finalize()

    def _on_hitl(self, event: DomainEvent):
        """Record non-convergence, note the escalation, and freeze the view."""
        if self._consensus_history:
            self._consensus_history[-1]["converged"] = False
        self._stamp_process("⚠  human input required", style="bold red")
        self._finalize()

    # -- state helpers ------------------------------------------------------

    @property
    def _elapsed(self) -> float:
        """Seconds since the run started, or ``0.0`` before it begins."""
        return time.monotonic() - self._start if self._start else 0.0

    def _plain(self, text: str) -> Text:
        """Wrap *text* in an unstyled Rich :class:`Text`."""
        return Text(text)

    def _add_evidence(self, line: RenderableType, *, level: EvidenceLevel = "INFO"):
        """Append *line* to the Evidence Stream buffer at *level*."""
        self._evidence_log.append(line, level=level)

    def _add_process(self, line: RenderableType, *, level: EvidenceLevel = "INFO"):
        """Append *line* to the Investigation Process buffer at *level*."""
        self._process_log.append(line, level=level)

    def _stamp(self, message: str, *, style: str = "", level: EvidenceLevel = "INFO"):
        """Append a timestamped, styled *message* to the Evidence Stream."""
        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(message, style=style)
        self._add_evidence(line, level=level)

    def _stamp_process(self, message: str, *, style: str = "", level: EvidenceLevel = "INFO"):
        """Append a timestamped, styled *message* to the Investigation Process log."""
        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(message, style=style)
        self._add_process(line, level=level)

    def _stamp_field(
        self,
        label: str,
        value: str,
        value_style: str,
        *,
        level: EvidenceLevel = "INFO",
    ):
        """Append a timestamped ``label  value`` evidence line at *level*."""
        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(f"{label:<13}", style="dim")
        line.append(value, style=value_style)
        self._add_evidence(line, level=level)

    def _wake(self, name: str):
        """Set agent *name* to analyzing, update the status line, and advance a stage."""
        state = self._agents.get(name)
        if state is not None and state.status != "DONE":
            state.status = "ANALYZING"
        self._status = self._agent_activity.get(name, "Deliberating…")
        self._advance()

    def _advance(self):
        """Advance the investigation-process stage counter by one, capped at the total."""
        self._stage = min(self._stage + 1, self._stage_total)

    def _finalize(self):
        """Freeze the run: fill the stage bar, reveal all buffers, and stop the Live."""
        self._finished = True
        self._stage = self._stage_total
        # The Live block is about to freeze: surface any still-buffered lines
        # at once so both final tails (including the completion marker in the
        # conversation log) are shown.
        self._evidence_log.reveal_all()
        self._process_log.reveal_all()
        self._refresh()
        self._stop_live()

    def evidence_transcript(self) -> str:
        """Plain-text record of the full Evidence Stream, for opt-in persistence.

        Joins every buffered evidence line - the complete record at the active
        verbosity (INFO summary lines, plus the TRACE detail when the evidence
        channel is TRACE). Returns ``""`` when no evidence was captured.
        """
        return "\n".join(_plain_text(line.text) for line in self._evidence_log.lines)

    # -- rendering ----------------------------------------------------------

    def __rich__(self) -> Layout:
        """Render the current view state as a Rich :class:`Layout` (Live protocol)."""
        return self._build_layout()

    def _build_layout(self) -> Layout:
        """Assemble the header plus the three body panes into a root layout."""
        root = Layout()
        root.split_column(
            Layout(self._render_header(), name="header", size=1),
            Layout(name="body"),
        )
        root["body"].split_row(
            Layout(self._render_evidence(), name="evidence", ratio=1),
            Layout(name="right", ratio=1),
        )
        root["body"]["right"].split_column(
            Layout(self._render_agents(), name="agents", ratio=1),
            Layout(self._render_process(), name="process", ratio=1),
        )
        return root

    def _render_header(self) -> Text:
        """Render the single-row header (title, incident, mode, clock, round)."""
        header = Text(no_wrap=True, overflow="ellipsis")
        header.append("  AEGIS SWR ", style="bold cyan")
        header.append(" Synthetic War Room   ", style="cyan")
        header.append(f"{self._incident_label}  ", style="bold white")
        header.append(f"{self._mode}", style="dim")
        header.append(f"   {_fmt_elapsed(self._elapsed)}  ", style="dim")
        round_style = "bold yellow" if self._round > 1 else "dim"
        header.append(f"R{self._round}", style=round_style)
        return header

    def _rendered_rows(self, renderable: RenderableType, width: int) -> int:
        """Number of visual rows *renderable* occupies when wrapped to *width*."""
        options = self._console.options.update(width=max(1, width))
        return max(1, len(self._console.render_lines(renderable, options, pad=False)))

    def _fit_tail(self, lines: list[RenderableType], *, width: int, height: int) -> list[RenderableType]:
        """Return the trailing *lines* whose wrapped heights fit within *height*.

        Bottom-anchored: accumulates from the newest line backwards until the
        next line would overflow. Selecting by *rendered* height (not logical
        line count) means wrapped lines no longer push the panel past its region
        and get cropped off the bottom - so the end of the stream is always the
        last thing shown.
        """
        selected: list[RenderableType] = []
        used = 0
        for renderable in reversed(lines):
            rows = self._rendered_rows(renderable, width)
            if selected and used + rows > height:
                break
            selected.append(renderable)
            used += rows
            if used >= height:
                break
        selected.reverse()
        return selected

    def _evidence_inner(self) -> tuple[int, int]:
        """Inner (content) width and height of the Evidence Stream panel.

        Evidence is the left half of the body (below the 1-row header), inside a
        bordered Panel with the default ``(0, 1)`` padding.
        """
        inner_h = max(1, self._console.height - 1 - 2)  # header row, panel borders
        inner_w = max(10, self._console.width // 2 - 4)  # 2 border + 2 padding cols
        return inner_w, inner_h

    def _render_evidence(self) -> Panel:
        """Render the Evidence Stream panel as a bottom-anchored scrolling tail."""
        inner_w, inner_h = self._evidence_inner()
        revealed = self._evidence_log.visible(
            now=time.monotonic(),
            finished=self._finished,
            level=self._evidence_level,
            max_lines=self._MAX_EVIDENCE,
        )
        # While running, reserve the bottom row for the streaming cursor.
        budget = max(1, inner_h - (0 if self._finished else 1))
        lines = self._fit_tail(revealed, width=inner_w, height=budget)
        if not self._finished:
            cursor = "▌" if int(self._elapsed) % 2 == 0 else " "
            lines = [*lines, Text(cursor, style="cyan")]
        body = Group(*lines) if lines else Text("")
        title = "[bold]EVIDENCE STREAM[/bold]"
        if self._evidence_level != "INFO":
            title += f" [dim]({self._evidence_level.lower()})[/dim]"
        return Panel(body, title=title, border_style="grey37")

    def _render_agents(self) -> Panel:
        """Render the Forensic Agents panel: one status block per resolved agent."""
        compact = self._console.height < 36
        finding_width = max(10, self._console.width // 2 - 6)
        elapsed = self._elapsed

        blocks: list[RenderableType] = []
        for index, (name, state) in enumerate(self._agents.items()):
            if index:
                blocks.append(Rule(style="grey30"))

            badge, badge_style, marker = _agent_badge(state.status, elapsed)
            head = Text()
            head.append(f"{marker} ", style=badge_style)
            head.append(f"{name:<20}", style="bold")
            head.append(badge, style=badge_style)
            blocks.append(head)

            blocks.append(Text("  ").append_text(_confidence_bar(state.confidence, 20)))

            if not compact:
                finding = _truncate(state.finding, finding_width) if state.finding else "-"
                blocks.append(Text(f"  {finding}", style="italic grey70"))

        return Panel(
            Group(*blocks),
            title="[bold]FORENSIC AGENTS[/bold]",
            subtitle=f"Round {self._round}",
            border_style="grey37",
        )

    def _process_inner(self) -> tuple[int, int]:
        """Inner (content) width and height of the Investigation Process panel.

        The pane is the lower half of the right column (below the 1-row
        header), inside a bordered ``Panel`` with the default ``(0, 1)``
        padding.  Used to tail the conversation log so the newest deliberation
        lines are never clipped off the bottom.
        """
        body = max(1, self._console.height - 1)  # below the header row
        pane = max(1, body // 2)  # right column splits agents / process evenly
        inner_h = max(1, pane - 2)  # minus the panel's top and bottom borders
        inner_w = max(10, self._console.width // 2 - 4)  # 2 border + 2 padding cols
        return inner_w, inner_h

    def _render_process(self) -> Panel:
        """Render the Investigation Process panel: activity, stage bar, and conversation."""
        elapsed = self._elapsed
        sections: list[RenderableType] = []

        # Section 1 - live activity (spinner + stage bar).
        spin = "✔" if self._finished else _spinner_char(elapsed)
        status = "Investigation complete" if self._finished else self._status
        head = Text()
        head.append(f"{spin} ", style="cyan")
        head.append(status, style="cyan")
        sections.append(head)

        ratio = self._stage / self._stage_total if self._stage_total else 0.0
        bar = Text("")
        bar.append_text(_bar(ratio, 22, "cyan"))
        bar.append(f"  {self._stage}/{self._stage_total}  ", style="dim")
        bar.append(_fmt_elapsed(elapsed), style="dim")
        sections.append(bar)
        sections.append(Text())

        # Section 2 - agent deliberation (scrolling conversation log).  Agent
        # findings and consensus checks are the *process* of investigation, not
        # evidence; newest lines sit at the bottom and older ones scroll off the
        # top once they exceed the pane.  The full transcript lives in the
        # report files.  One row is held back as a clipping safety margin.
        inner_w, inner_h = self._process_inner()
        used = sum(self._rendered_rows(section, inner_w) for section in sections)
        convo = self._process_log.visible(
            now=time.monotonic(),
            finished=self._finished,
            level=self._process_level,
            max_lines=self._MAX_EVIDENCE,
        )
        # One row held back as a clipping safety margin; fit by rendered height
        # so wrapped deliberation lines are not cropped off the bottom.
        fitted = self._fit_tail(convo, width=inner_w, height=max(1, inner_h - used - 1))
        if fitted:
            sections.extend(fitted)
        else:
            sections.append(Text("Awaiting panel deliberation…", style="dim italic"))

        return Panel(
            Group(*sections),
            title="[bold]INVESTIGATION PROCESS[/bold]",
            subtitle=f"Round {self._round}",
            border_style="grey37",
        )

    def _refresh(self):
        """Trigger a Live re-render if the war-room block is active."""
        if self._live is not None:
            self._live.refresh()

    def _stop_live(self):
        """Stop and clear the Live war-room block if it is running."""
        if self._live is not None:
            self._live.stop()
            self._live = None


def _agent_badge(status: str, elapsed: float) -> tuple[str, str, str]:
    """Return (badge_text, style, line-marker) for an agent status"""
    if status == "ANALYZING":
        return "ANALYZING", "bold cyan", _spinner_char(elapsed)
    if status == "REVIEWING":
        return "REVIEWING", "bold yellow", _spinner_char(elapsed)
    if status == "DONE":
        return "DONE", "bold green", "✔"
    return "STANDBY", "dim", " "


def _format_frame(frame: dict[str, object]) -> str:
    """Render a stack frame with module/source detail for the DEBUG stream"""
    module = frame.get("module")
    function = frame.get("function")
    if module and function:
        name = f"{module}!{function}"
    else:
        name = str(function or module or frame.get("instruction_address") or "?")
    src = frame.get("source_file")
    if src:
        line = frame.get("source_line")
        name += f"  ({src}:{line})" if line else f"  ({src})"
    addr = frame.get("instruction_address")
    if addr and (module or function or src):
        name += f"  @ {addr}"
    return name


def _format_pcap(raw_path: str) -> list[str]:
    """Render network-capture metadata lines for the DEBUG stream"""
    info = pcap_metadata(raw_path)
    if info.container != "pcap":
        return [f"{info.container}: {info.note}" if info.note else info.container]
    lines = [
        f"pcap v{info.version}  {info.byte_order}-endian  {info.timestamp_resolution} ts",
        f"link-layer {info.link_type}  snaplen {info.snaplen}",
        f"packets {info.packet_count}",
    ]
    if info.first_timestamp and info.last_timestamp:
        duration = (info.last_timestamp - info.first_timestamp).total_seconds()
        lines.append(
            f"span {info.first_timestamp:%Y-%m-%d %H:%M:%S} → {info.last_timestamp:%H:%M:%S}  ({duration:.3f}s)"
        )
    return lines


# ---------------------------------------------------------------------------
# Simple fallback view (narrow terminals)
# ---------------------------------------------------------------------------


def _agent_trail_line(turn: AgentTurn, elapsed: float) -> Text:
    """One compact line for a completed agent turn in the live trail"""
    color = _conf_color(turn.confidence_score)
    line = Text("  ")
    line.append("✔ ", style="bold green")
    line.append(f"{turn.agent:<22}", style="bold")
    line.append(f"{turn.confidence_score:>4.0%}", style=f"bold {color}")
    line.append(" confident", style="dim")
    line.append(f"  ·  {elapsed:.1f}s", style="dim")
    return line


def _turn_summary(turn: AgentTurn, limit: int = 96) -> Text:
    """A single dim line previewing what the agent concluded"""
    first_line = turn.message.strip().splitlines()[0] if turn.message.strip() else ""
    if len(first_line) > limit:
        first_line = first_line[: limit - 1] + "…"
    return Text(f"      {first_line}", style="dim italic")


class RichView:
    """Live terminal adapter: renders domain events as a single-column trail.

    Used as a fallback for narrow terminals where the three-pane
    :class:`WarRoomView` would not fit.
    """

    def __init__(self, console: Optional[Console] = None):
        """Initialise the fallback trail view state.

        :param console: Rich console to render into; a default is built when omitted.
        """
        self._console = console or make_console()
        self._trail: list[RenderableType] = []
        self._live: Optional[Live] = None
        self._progress: Optional[Progress] = None
        self._task_id: Optional[TaskID] = None
        # Stages in round 1: evidence, one turn per agent, consensus check,
        # verdict == len(panel) + 3. Each extra debate round adds len(panel) + 1
        # (one turn per agent + one consensus check). Both are resized from the
        # PanelResolved event; 7 is a provisional default until then.
        self._stages_total = 7
        self._panel_size = 0
        # node-that-just-completed → status describing who speaks next, and the
        # first agent's activity, both rebuilt from the resolved panel.
        self._next_status: dict[str, str] = {}
        self._first_activity = "Deliberating…"
        self._last_round = 0
        self._stage_started = 0.0

    def attach(self, bus: EventBus) -> Callable[[], None]:
        """Subscribe to *bus*; returns a detach function"""
        unsubscribers = [
            bus.subscribe(InvestigationStarted, self._on_started),
            bus.subscribe(EvidenceExtracted, self._on_evidence),
            bus.subscribe(PanelResolved, self._on_panel),
            bus.subscribe(AgentSpoke, self._on_agent),
            bus.subscribe(ConsensusEvaluated, self._on_consensus),
            bus.subscribe(InvestigationCompleted, self._on_finished),
            bus.subscribe(HumanInputRequired, self._on_finished),
        ]

        def _detach():
            """Unsubscribe every handler and stop the Live trail block."""
            for unsubscribe in unsubscribers:
                unsubscribe()
            self._stop_live()

        return _detach

    # -- event handlers -----------------------------------------------------

    def _on_started(self, event: DomainEvent):
        """Print the incident header, reset state, and start the Live trail block."""
        assert isinstance(event, InvestigationStarted)
        source = event.source
        target = (
            Path(source.dump_path).name
            if source.dump_path
            else ", ".join(Path(p).name for p in source.log_paths) or "incident"
        )
        header = Text()
        header.append("Incident  ", style="dim")
        header.append(target, style="bold")
        header.append(f"   mode: {source.mode.value}", style="dim")
        if source.user_assumption:
            header.append(f"\nContext   {source.user_assumption}", style="dim italic")
        self._console.print(
            Panel(
                header,
                title="[bold cyan]AEGIS SWR - Synthetic War Room[/bold cyan]",
                border_style="cyan",
            )
        )

        # Reset state so one view instance can render successive runs.
        self._trail = []
        self._stages_total = 7
        self._panel_size = 0
        self._next_status = {}
        self._first_activity = "Deliberating…"
        self._last_round = 0
        self._stage_started = time.monotonic()
        self._progress = Progress(
            SpinnerColumn("dots", style="cyan"),
            TextColumn("[cyan]{task.description}"),
            BarColumn(bar_width=24, style="grey35", complete_style="cyan", pulse_style="cyan"),
            TextColumn("[dim]{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self._console,
        )
        self._task_id = self._progress.add_task("Extracting evidence from crash artifacts…", total=self._stages_total)
        self._live = Live(self._render(), console=self._console, refresh_per_second=12)
        self._live.start()

    def _on_evidence(self, event: DomainEvent):
        """Append a one-line evidence-extracted summary to the trail."""
        assert isinstance(event, EvidenceExtracted)
        brief = event.brief
        elapsed = time.monotonic() - self._stage_started
        fault = brief.get("fault_class") or "unknown"
        module = brief.get("faulting_module")
        fn = brief.get("faulting_function")
        where = " in ".join(x for x in (fn, module) if x)
        line = Text("  ")
        line.append("✔ ", style="bold green")
        line.append(f"{'Evidence extracted':<22}", style="bold")
        line.append(str(fault).upper(), style="magenta")
        if where:
            line.append(f"  →  {where}")
        line.append(f"  ·  {elapsed:.1f}s", style="dim")
        self._trail.append(line)
        # The panel resolves next (PanelResolved); the first agent's activity is
        # set there once the roster is known.
        self._set_status("Assembling the forensic panel…")
        self._refresh()

    def _on_panel(self, event: DomainEvent):
        """Resize the stage budget and build the next-status map from the panel.

        Replaces the former static ``_NEXT_STATUS`` constant: the map keyed by
        the node that just completed (whose value describes who speaks next) is
        rebuilt from :attr:`PanelResolved.panel`, and the progress-bar total is
        resized to the panel size, so the trail view scales to any roster.
        """
        assert isinstance(event, PanelResolved)
        panel = event.panel
        self._panel_size = len(panel)
        activities = [_activity_label(descriptor) for descriptor in panel]
        node_names = [descriptor.node_name for descriptor in panel]
        # Each completed node advances to the next agent's activity; the last
        # (the arbiter) hands off to the consensus check.
        self._next_status = {
            node: (activities[i + 1] if i + 1 < len(node_names) else "Weighing panel consensus…")
            for i, node in enumerate(node_names)
        }
        self._first_activity = activities[0] if activities else "Deliberating…"
        self._stages_total = self._panel_size + 3
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, total=self._stages_total, description=self._first_activity)
        self._stage_started = time.monotonic()
        self._refresh()

    def _on_agent(self, event: DomainEvent):
        """Append the agent's trail line and summary, adding a round rule as needed."""
        assert isinstance(event, AgentSpoke)
        turn = event.turn
        elapsed = time.monotonic() - self._stage_started

        if turn.turn_number != self._last_round:
            if self._last_round and self._progress is not None and self._task_id is not None:
                # Another debate round: one turn per agent + one consensus check.
                self._stages_total += self._panel_size + 1
                self._progress.update(self._task_id, total=self._stages_total)
            self._last_round = turn.turn_number
            self._trail.append(Rule(f"Round {turn.turn_number} - panel deliberation", style="dim"))

        self._trail.append(_agent_trail_line(turn, elapsed))
        self._trail.append(_turn_summary(turn))
        self._set_status(self._next_status.get(event.node, "Deliberating…"))
        self._refresh()

    def _on_consensus(self, event: DomainEvent):
        """Append a weighted-consensus line with its confidence bar to the trail."""
        assert isinstance(event, ConsensusEvaluated)
        score = event.score
        level = ConfidenceLevel.from_score(score).value.upper()
        color = _conf_color(score)
        line = Text("  ")
        line.append("⚖ ", style=color)
        line.append(f"{'Weighted consensus':<22}", style="bold")
        line.append_text(_confidence_bar(score))
        line.append(f"  {level}", style=f"bold {color}")
        self._trail.append(line)
        self._set_status("Reviewing consensus - deciding next step…")
        self._refresh()

    def _on_finished(self, event: DomainEvent):
        """Complete the progress bar and stop the Live trail block on run end."""
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, completed=self._stages_total)
        self._progress = None
        self._refresh()
        self._stop_live()

    # -- rendering ------------------------------------------------------------

    def _set_status(self, message: str):
        """Update the progress description, advance one stage, and reset the stage clock."""
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, description=message, advance=1)
        self._stage_started = time.monotonic()

    def _render(self) -> Group:
        """Render the trail plus the active progress bar as a Rich :class:`Group`."""
        items: list[RenderableType] = list(self._trail)
        if self._progress is not None:
            items.append(Text())
            items.append(self._progress)
        return Group(*items)

    def _refresh(self):
        """Push a freshly rendered trail into the Live block if it is active."""
        if self._live is not None:
            self._live.update(self._render())

    def _stop_live(self):
        """Stop and clear the Live trail block if it is running."""
        if self._live is not None:
            self._live.stop()
            self._live = None


def make_view(
    console: Console, *, level: str = "INFO", process_level: Optional[str] = None
) -> Union[RichView, WarRoomView]:
    """Pick the war-room view on wide terminals, the trail view otherwise.

    *level* selects the Evidence Stream (left pane) verbosity: ``INFO`` shows the
    curated summary; ``TRACE`` surfaces the full per-artifact evidence metadata and
    the full debugger ``!analyze`` output. *process_level* selects the Investigation
    Process (right pane) verbosity independently - at ``TRACE`` the agents' full
    reasoning is shown. ``DEBUG`` collapses into ``TRACE``; unrecognised values fall
    back to ``INFO``.
    """
    return WarRoomView(console, level=level, process_level=process_level) if console.width >= 80 else RichView(console)


# ---------------------------------------------------------------------------
# Final verdict
# ---------------------------------------------------------------------------


#: Theme pushed onto the console while the verdict frame renders, so the
#: Markdown headings, lists, and inline code pick up the green house palette
#: instead of rich's default magenta/blue. Restored immediately afterwards so
#: the live war-room styling is untouched.
_REPORT_THEME = Theme(
    {
        "markdown.h1": "bold green",
        "markdown.h2": "bold green",
        "markdown.h3": "bold bright_cyan",
        "markdown.h4": "bold bright_cyan",
        "markdown.item.bullet": "bold green",
        "markdown.item.number": "bold green",
        "markdown.code": "bold yellow",
    }
)


def _final_findings(report: RCAReport) -> list[AgentTurn]:
    """The last turn each forensic agent took, in panel-speaking order.

    The panel's detailed reasoning is the substance of the report, but it only
    streams transiently through the Investigation Process pane during the live
    run.  The full prose survives in :attr:`RCAReport.agent_dialogue`; here we
    keep the *final* turn per agent (its most refined position after any
    re-deliberation) so the verdict frame can reproduce that reasoning instead
    of discarding it.

    Ordering follows each agent's *first appearance* in
    :attr:`RCAReport.agent_dialogue`, which is already recorded in panel-speaking
    order. This replaces the former dependency on a static agent sequence, so the
    findings reflect whatever dynamic panel actually ran.
    """
    latest: dict[str, AgentTurn] = {}
    first_seen: dict[str, int] = {}
    for index, turn in enumerate(report.agent_dialogue):
        first_seen.setdefault(turn.agent, index)
        prior = latest.get(turn.agent)
        if prior is None or turn.turn_number >= prior.turn_number:
            latest[turn.agent] = turn

    return sorted(latest.values(), key=lambda t: first_seen.get(t.agent, len(first_seen)))


def _build_diagnosis(report: RCAReport) -> str:
    """Compose the Markdown RCA body rendered inside the verdict frame.

    Aegis SWR has no single "report" field, so the human-readable report is
    organised here from the whole analysis result - the converged conclusion,
    the supporting evidence, each agent's detailed reasoning, the dissenting
    alternatives and skeptic challenges, the implicated module, and the
    recommended actions - laid out in the same Markdown sections as the
    prototype's ``root-cause-analysis.txt`` so the verdict frame can colour
    headings, lists, and inline code.
    """
    level = report.confidence_level.value.upper()
    rounds = report.consensus_rounds
    md: list[str] = []

    md.append("## Root Cause Analysis (RCA)")
    md.append("")
    md.append(f"**Conclusion:** {report.root_cause.strip()}")
    md.append("")
    md.append(
        f"**Confidence:** {level} ({report.confidence_score:.0%}) - resolved after "
        f"{rounds} debate round{'s' if rounds != 1 else ''}."
    )

    evidence = [e for e in report.primary_hypothesis.evidence if not e.startswith("__fix__:")]
    if evidence:
        md.append("")
        md.append("### Evidence")
        md.extend(f"- {item}" for item in evidence)

    findings = _final_findings(report)
    if findings:
        md.append("")
        md.append("### Panel Findings")
        for turn in findings:
            md.append("")
            md.append(f"**{turn.agent}** - {turn.confidence_score:.0%} confident")
            md.append("")
            md.append(turn.message.strip())

    if report.alternative_hypotheses:
        md.append("")
        md.append("### Alternative Hypotheses")
        md.extend(f"- {alt.root_cause.strip()} ({alt.confidence:.0%})" for alt in report.alternative_hypotheses)

    if report.skeptic_challenges:
        md.append("")
        md.append("### Skeptic Challenges")
        md.extend(f"- {item}" for item in report.skeptic_challenges)

    if report.faulting_module or report.faulting_function or report.dump_hash:
        md.append("")
        md.append("---")
        md.append("")
        md.append("## Faulting Module")
        if report.faulting_module:
            md.append(f"- **Module:** `{report.faulting_module}`")
        if report.faulting_function:
            md.append(f"- **Function:** `{report.faulting_function}`")
        if report.dump_hash:
            md.append(f"- **Dump hash:** `{report.dump_hash}`")
        if report.symbol_resolution_score is not None:
            md.append(f"- **Symbol coverage:** {report.symbol_resolution_score:.0%}")

    md.append("")
    md.append("---")
    md.append("")
    md.append("## Recommendation")
    if report.mitigation_instructions:
        md.extend(f"{i}. {step}" for i, step in enumerate(report.mitigation_instructions, start=1))
    else:
        target = report.faulting_module or "the implicated component"
        md.append(f"1. Review the faulting module `{target}` and add defensive checks around the faulting code path.")

    if report.probabilistic_fix:
        conf = report.fix_confidence or 0.0
        md.append("")
        md.append(f"### Probabilistic Fix - confidence {conf:.0%}")
        md.append("```diff")
        md.append(report.probabilistic_fix.strip())
        md.append("```")

    return "\n".join(md)


def _incident_record(report: RCAReport) -> dict[str, object]:
    """The short machine-readable record stamped at the foot of the frame.

    Keyed by incident id so the printed frame carries the same handle used to
    look the report up in storage; the few extra fields make the JSON a usable
    at-a-glance summary without duplicating the prose above.
    """
    record: dict[str, object] = {
        "incident_id": str(report.incident_id),
        "confidence": round(report.confidence_score, 2),
    }
    if report.faulting_module:
        record["faulting_module"] = report.faulting_module
    if report.dump_hash:
        record["dump_hash"] = report.dump_hash
    return record


def render_verdict(
    report: RCAReport,
    *,
    console: Optional[Console] = None,
    model: str = "",
    show_dialogue: bool = False,  # noqa: ARG001 - kept for CLI signature compatibility
):
    """Print the final report as a single prototype-style verdict frame.

    A converged investigation renders a green ``Root Cause Analysis Report``
    panel: the Markdown diagnosis with coloured headings, then a short JSON
    incident record stamped at the foot of the same frame.  A deadlock (HITL)
    renders a red ``Human Input Required`` panel instead and omits the
    diagnosis.
    """
    console = console or make_console()
    console.print()

    if report.hitl_request:
        req = report.hitl_request
        body = Text()
        body.append(req.question.strip(), style="bold yellow")
        if req.context_summary:
            body.append(f"\n\n{req.context_summary.strip()}", style="white")
        if req.requested_data:
            body.append("\n")
            for item in req.requested_data:
                body.append(f"\n  • {item}", style="white")
        console.print(
            Panel(
                body,
                title="[bold red]Human Input Required[/bold red]",
                subtitle=f"Model: {model}" if model else None,
                border_style="red",
                padding=(1, 2),
            )
        )
        return

    frame = Group(
        Markdown(_build_diagnosis(report)),
        Text(),
        Rule("Incident Record", style="green"),
        JSON.from_data(_incident_record(report)),
    )
    panel = Panel(
        frame,
        title="[bold green]Root Cause Analysis Report[/bold green]",
        subtitle=f"Model: {model}" if model else None,
        border_style="green",
        padding=(1, 2),
    )
    console.push_theme(_REPORT_THEME)
    try:
        console.print(panel)
    finally:
        console.pop_theme()
