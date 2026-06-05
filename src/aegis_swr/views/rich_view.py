"""Rich terminal view adapters.

Two views subscribe to the core :class:`~aegis_swr.core.events.EventBus` and
render an investigation live:

* :class:`WarRoomView` — a full-screen, three-pane "Synthetic War Room"
  (Evidence Stream | Forensic Agents / Investigation Process) built on
  :class:`rich.layout.Layout` inside a :class:`rich.live.Live`. See
  ``docs/adr/new-ui-rich-based-design.md``.
* :class:`RichView` — a simpler single-column trail, kept as a fallback for
  narrow terminals.

:func:`make_view` selects between them by terminal width.
:func:`render_verdict` prints the final report once the live block freezes.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
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

from aegis_swr.core.events import (
    AgentSpoke,
    ConsensusEvaluated,
    EvidenceExtracted,
    HumanInputRequired,
    InvestigationCompleted,
    InvestigationStarted,
)
from aegis_swr.core.schemas import ConfidenceLevel
from aegis_swr.views.evidence_detail import (
    describe_log_window,
    file_properties,
    pcap_metadata,
)
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.core.schemas import AgentTurn, IncidentSource, RCAReport


def make_console(*, stderr: bool = False) -> Console:
    """Console factory used by all Rich rendering.

    PyCharm's run window understands ANSI escape codes but is not a tty, so
    rich would otherwise disable the live display and all animation.  Force
    terminal mode there; everywhere else keep rich's auto-detection so piped
    output stays clean.
    """
    force = True if os.environ.get("PYCHARM_HOSTED") else None
    return Console(stderr=stderr, force_terminal=force)


# ---------------------------------------------------------------------------
# Visual helpers
# ---------------------------------------------------------------------------

#: Spinner frames cycled for the active forensic agent (Braille dots).
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

#: Panel speaking order: (LangGraph node name, human-readable agent name).
AGENT_SEQUENCE: list[tuple[str, str]] = [
    ("os_kernel_node", "OS Kernel Agent"),
    ("code_analyst_node", "Code Analyst Agent"),
    ("log_historian_node", "Log Historian Agent"),
    ("skeptic_node", "Skeptic Agent"),
]

# node → name and name → "the next agent to wake" derived from the sequence.
_NODE_TO_AGENT: dict[str, str] = {node: name for node, name in AGENT_SEQUENCE}
_NEXT_AGENT: dict[str, str | None] = {
    name: (AGENT_SEQUENCE[i + 1][1] if i + 1 < len(AGENT_SEQUENCE) else None)
    for i, (_, name) in enumerate(AGENT_SEQUENCE)
}

# What the Investigation Process line says while each agent is working.
_AGENT_ACTIVITY: dict[str, str] = {
    "OS Kernel Agent": "OS Kernel Agent is analyzing the exception…",
    "Code Analyst Agent": "Code Analyst Agent is tracing the faulting code…",
    "Log Historian Agent": "Log Historian Agent is mining incident history…",
    "Skeptic Agent": "Skeptic Agent is stress-testing the hypothesis…",
}


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


#: Evidence-stream verbosity levels.  ``INFO`` is the curated summary shown by
#: default; ``DEBUG`` adds every detailed evidence line on top of it.
EvidenceLevel = Literal["INFO", "DEBUG"]

# How many lines of the raw core-dump analysis text to surface at DEBUG.
_DEBUG_EXCERPT_LINES = 40


@dataclass
class AgentState:
    """Live state for one forensic agent sub-panel"""

    status: Literal["STANDBY", "ANALYZING", "REVIEWING", "DONE"] = "STANDBY"
    confidence: float = 0.0
    finding: str = ""  # latest finding, truncated to panel width at render time


@dataclass
class _EvidenceLine:
    """One Evidence Stream entry tagged with the verbosity it belongs to"""

    level: EvidenceLevel
    text: Text


class WarRoomView:
    """Full-screen three-pane war room driven by the :class:`EventBus`.

    The view is itself a Rich renderable (``__rich__``); a 12 fps ``Live``
    re-renders it each tick so spinners and clocks animate without any timer
    threads of our own.  Internal state is mutated by the event handlers and
    read by the ``_render_*`` methods.
    """

    _MAX_EVIDENCE = 500

    def __init__(
        self,
        console: Console | None = None,
        *,
        auto_refresh: bool = True,
        level: EvidenceLevel = "INFO",
    ):
        self._console = console or make_console()
        self._auto_refresh = auto_refresh
        self._level: EvidenceLevel = "DEBUG" if str(level).upper() == "DEBUG" else "INFO"
        self._live: Live | None = None

        # ── investigation state ──
        self._start = 0.0
        self._incident_label = "incident"
        self._mode = ""
        self._round = 0
        self._finished = False
        self._source: IncidentSource | None = None

        self._evidence_lines: list[_EvidenceLine] = []
        self._agents: dict[str, AgentState] = {}
        self._consensus_history: list[dict[str, object]] = []

        # Investigation-process bookkeeping.
        self._status = ""
        self._stage = 0
        self._stage_total = 7
        self._stage_notes: list[str] = []

    # -- attachment ---------------------------------------------------------

    def attach(self, bus: EventBus) -> Callable[[], None]:
        """Subscribe to *bus*; returns a detach function"""
        unsubscribers = [
            bus.subscribe(InvestigationStarted, self._on_started),
            bus.subscribe(EvidenceExtracted, self._on_evidence),
            bus.subscribe(AgentSpoke, self._on_agent),
            bus.subscribe(ConsensusEvaluated, self._on_consensus),
            bus.subscribe(InvestigationCompleted, self._on_completed),
            bus.subscribe(HumanInputRequired, self._on_hitl),
        ]

        def _detach():
            for unsubscribe in unsubscribers:
                unsubscribe()
            self._stop_live()

        return _detach

    # -- event handlers -----------------------------------------------------

    def _on_started(self, event: DomainEvent):
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
        self._evidence_lines = []
        self._agents = {name: AgentState() for _, name in AGENT_SEQUENCE}
        self._consensus_history = []
        self._stage = 0
        self._stage_total = 7
        self._stage_notes = []
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

        if self._level == "DEBUG":
            self._emit_debug_evidence(brief)

        self._wake("OS Kernel Agent")
        self._refresh()

    def _emit_debug_evidence(self, brief: dict[str, object]):
        """Append the verbose, DEBUG-only evidence metadata for one incident.

        Surfaces the four detailed evidence categories on top of the curated
        INFO stream: the textual core-dump analysis, the temporal window of
        every analyzed log file, screenshot file properties, and network
        traffic capture metadata — plus the low-level fault fields.
        """
        # ── very detailed fault metadata ──
        for label, key in (
            ("dump_hash", "dump_hash"),
            ("exc_code", "exception_code_raw"),
            ("exc_addr", "exception_address"),
        ):
            value = brief.get(key)
            if value:
                self._stamp_field(label, str(value), "grey70", level="DEBUG")

        # Full stack beyond the INFO top-three, with module/source detail.
        frames = brief.get("stack_frames") or []
        for i, frame in enumerate(frames):
            if i < 3:
                continue
            self._stamp_field(f"stack[{i}]", _format_frame(frame), "blue", level="DEBUG")

        # ── 1. textual result of the core-dump analysis ──
        excerpt = str(brief.get("raw_text_excerpt") or "").strip()
        if excerpt:
            self._stamp("core dump analysis (cdb !analyze -v):", style="dim", level="DEBUG")
            for raw in excerpt.splitlines()[:_DEBUG_EXCERPT_LINES]:
                self._add_evidence(Text(f"    │ {raw}", style="grey62"), level="DEBUG")

        src = self._source
        incident_ts = src.incident_timestamp if src else None

        # ── 2. ±2 minute window for every analyzed log file ──
        for raw_path in (src.log_paths if src else []):
            props = file_properties(raw_path)
            self._stamp_field("log", props.describe(), "cyan", level="DEBUG")
            self._add_evidence(
                Text(f"    │ window {describe_log_window(incident_ts)}", style="grey62"),
                level="DEBUG",
            )
        summary = str(brief.get("log_summary") or "").strip()
        if summary:
            self._stamp_field(
                "log_summary", f"{len(summary.splitlines())} clustered lines", "cyan",
                level="DEBUG",
            )

        # ── 3. name and properties of every screenshot file ──
        for raw_path in (src.screenshot_paths if src else []):
            props = file_properties(raw_path)
            self._stamp_field("screenshot", props.describe(), "magenta", level="DEBUG")
        ui = brief.get("ui_context")
        if isinstance(ui, dict):
            elements = ui.get("ui_elements") or []
            ocr = str(ui.get("error_message") or "")
            self._add_evidence(
                Text(
                    f"    │ OCR: {len(elements)} elements, {len(ocr)} chars",
                    style="grey62",
                ),
                level="DEBUG",
            )

        # ── 4. metadata of every network traffic capture ──
        for raw_path in (src.network_capture_paths if src else []):
            props = file_properties(raw_path)
            self._stamp_field("netcap", props.describe(), "yellow", level="DEBUG")
            for detail in _format_pcap(raw_path):
                self._add_evidence(Text(f"    │ {detail}", style="grey62"), level="DEBUG")

    def _on_agent(self, event: DomainEvent):
        assert isinstance(event, AgentSpoke)
        turn = event.turn

        # A higher turn number means a fresh debate round began: the previous
        # consensus check did not converge.
        if turn.turn_number > self._round:
            if self._consensus_history:
                self._consensus_history[-1]["converged"] = False
            self._round = turn.turn_number
            self._stage_total += 5  # 4 agent turns + 1 consensus check
            note = f"threshold not reached — re-deliberating round {self._round}"
            self._stamp(note, style="dim italic")
            self._stage_notes.append(f"{_fmt_stamp(self._elapsed)}  {note}")

        name = _NODE_TO_AGENT.get(event.node)
        finding = turn.message.strip().splitlines()[0] if turn.message.strip() else ""
        if name and name in self._agents:
            state = self._agents[name]
            state.status = "DONE"
            state.confidence = turn.confidence_score
            state.finding = finding

        short = (name or turn.agent).removesuffix(" Agent")
        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(f"{short} » ", style="bold")
        line.append(finding, style="italic")
        self._add_evidence(line)
        self._advance()

        nxt = _NEXT_AGENT.get(name) if name else None
        if nxt:
            self._wake(nxt)
        else:
            self._status = "Weighing panel consensus…"
        self._refresh()

    def _on_consensus(self, event: DomainEvent):
        assert isinstance(event, ConsensusEvaluated)
        score = event.score
        level = ConfidenceLevel.from_score(score)
        self._consensus_history.append(
            {"round": self._round, "score": score, "converged": None}
        )

        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(f"consensus R{self._round}  ", style="bold")
        line.append(f"{score:.0%}  ", style=f"bold {_conf_color(score)}")
        line.append(level.value.upper(), style=_conf_color(score))
        self._add_evidence(line)

        # Next round (if any) reassigns agents; reset them to standby.
        for state in self._agents.values():
            state.status = "STANDBY"
        self._status = "Reviewing consensus — deciding next step…"
        self._advance()
        self._refresh()

    def _on_completed(self, event: DomainEvent):
        if self._consensus_history:
            self._consensus_history[-1]["converged"] = True
        for state in self._agents.values():
            state.status = "DONE"
        self._stamp("✔  investigation complete", style="bold green")
        self._finalize()

    def _on_hitl(self, event: DomainEvent):
        if self._consensus_history:
            self._consensus_history[-1]["converged"] = False
        self._stamp("⚠  human input required", style="bold red")
        self._finalize()

    # -- state helpers ------------------------------------------------------

    @property
    def _elapsed(self) -> float:
        return time.monotonic() - self._start if self._start else 0.0

    def _plain(self, text: str) -> Text:
        return Text(text)

    def _add_evidence(self, line: Text, *, level: EvidenceLevel = "INFO"):
        self._evidence_lines.append(_EvidenceLine(level=level, text=line))
        if len(self._evidence_lines) > self._MAX_EVIDENCE:
            del self._evidence_lines[: -self._MAX_EVIDENCE]

    def _stamp(self, message: str, *, style: str = "", level: EvidenceLevel = "INFO"):
        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(message, style=style)
        self._add_evidence(line, level=level)

    def _stamp_field(
        self,
        label: str,
        value: str,
        value_style: str,
        *,
        level: EvidenceLevel = "INFO",
    ):
        line = Text(f"{_fmt_stamp(self._elapsed)}  ")
        line.append(f"{label:<13}", style="dim")
        line.append(value, style=value_style)
        self._add_evidence(line, level=level)

    def _wake(self, name: str):
        state = self._agents.get(name)
        if state is not None and state.status != "DONE":
            state.status = "ANALYZING"
        self._status = _AGENT_ACTIVITY.get(name, "Deliberating…")
        self._advance()

    def _advance(self):
        self._stage = min(self._stage + 1, self._stage_total)

    def _finalize(self):
        self._finished = True
        self._stage = self._stage_total
        self._refresh()
        self._stop_live()

    # -- rendering ----------------------------------------------------------

    def __rich__(self) -> Layout:
        return self._build_layout()

    def _build_layout(self) -> Layout:
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
        header = Text(no_wrap=True, overflow="ellipsis")
        header.append("  AEGIS SWR ", style="bold cyan")
        header.append(" Synthetic War Room   ", style="cyan")
        header.append(f"{self._incident_label}  ", style="bold white")
        header.append(f"{self._mode}", style="dim")
        header.append(f"   {_fmt_elapsed(self._elapsed)}  ", style="dim")
        round_style = "bold yellow" if self._round > 1 else "dim"
        header.append(f"R{self._round}", style=round_style)
        return header

    def _render_evidence(self) -> Panel:
        visible = [
            entry.text
            for entry in self._evidence_lines
            if entry.level == "INFO" or self._level == "DEBUG"
        ]
        max_lines = max(1, self._console.height - 5)
        lines = visible[-max_lines:]
        if not self._finished:
            cursor = "▌" if int(self._elapsed) % 2 == 0 else " "
            lines = [*lines, Text(cursor, style="cyan")]
        body = Group(*lines) if lines else Text("")
        title = "[bold]EVIDENCE STREAM[/bold]"
        if self._level == "DEBUG":
            title += " [dim](debug)[/dim]"
        return Panel(body, title=title, border_style="grey37")

    def _render_agents(self) -> Panel:
        compact = self._console.height < 36
        finding_width = max(10, self._console.width // 2 - 6)
        elapsed = self._elapsed

        blocks: list[RenderableType] = []
        for index, (_, name) in enumerate(AGENT_SEQUENCE):
            state = self._agents.get(name, AgentState())
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
                finding = _truncate(state.finding, finding_width) if state.finding else "—"
                blocks.append(Text(f"  {finding}", style="italic grey70"))

        return Panel(
            Group(*blocks),
            title="[bold]FORENSIC AGENTS[/bold]",
            subtitle=f"Round {self._round}",
            border_style="grey37",
        )

    def _render_process(self) -> Panel:
        elapsed = self._elapsed
        sections: list[RenderableType] = []

        # Section 1 — waiting animation (spinner + stage bar).
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

        # Section 2 — consensus history.
        if self._consensus_history:
            sections.append(Text())
            sections.append(Text("Consensus history", style="bold"))
            for row in self._consensus_history:
                sections.append(_consensus_row(row))

        # Section 3 — recent stage notes (overflow).
        if self._stage_notes:
            sections.append(Text())
            for note in self._stage_notes[-3:]:
                sections.append(Text(note, style="dim"))

        return Panel(
            Group(*sections),
            title="[bold]INVESTIGATION PROCESS[/bold]",
            border_style="grey37",
        )

    def _refresh(self):
        if self._live is not None:
            self._live.refresh()

    def _stop_live(self):
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
            f"span {info.first_timestamp:%Y-%m-%d %H:%M:%S} → "
            f"{info.last_timestamp:%H:%M:%S}  ({duration:.3f}s)"
        )
    return lines


def _consensus_row(row: dict[str, object]) -> Text:
    score = float(row["score"])  # type: ignore[arg-type]
    converged = row["converged"]
    level = ConfidenceLevel.from_score(score).value.upper()
    line = Text(f"R{row['round']}  ")
    line.append_text(_bar(score, 14, _conf_color(score)))
    line.append(f"  {score:.0%}  ", style=f"bold {_conf_color(score)}")
    line.append(f"{level:<6}", style=_conf_color(score))
    if converged is True:
        line.append(" ✔", style="green")
    elif converged is False:
        line.append(" ✗", style="red")
    else:
        line.append(" …", style="dim")
    return line


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


# What the waiting line says while each upcoming stage runs.  Keyed by the
# node that just COMPLETED — the value describes who speaks next.
_NEXT_STATUS: dict[str, str] = {
    "data_adapter_node": "OS Kernel Agent is analyzing the exception…",
    "os_kernel_node": "Code Analyst Agent is tracing the faulting code…",
    "code_analyst_node": "Log Historian Agent is mining incident history…",
    "log_historian_node": "Skeptic Agent is stress-testing the hypothesis…",
    "skeptic_node": "Weighing panel consensus…",
}


class RichView:
    """Live terminal adapter: renders domain events as a single-column trail.

    Used as a fallback for narrow terminals where the three-pane
    :class:`WarRoomView` would not fit.
    """

    def __init__(self, console: Console | None = None):
        self._console = console or make_console()
        self._trail: list[RenderableType] = []
        self._live: Live | None = None
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None
        # Stages in round 1: evidence, 4 agent turns, consensus check, verdict.
        # Each extra debate round adds 4 agent turns + 1 consensus check.
        self._stages_total = 7
        self._last_round = 0
        self._stage_started = 0.0

    def attach(self, bus: EventBus) -> Callable[[], None]:
        """Subscribe to *bus*; returns a detach function"""
        unsubscribers = [
            bus.subscribe(InvestigationStarted, self._on_started),
            bus.subscribe(EvidenceExtracted, self._on_evidence),
            bus.subscribe(AgentSpoke, self._on_agent),
            bus.subscribe(ConsensusEvaluated, self._on_consensus),
            bus.subscribe(InvestigationCompleted, self._on_finished),
            bus.subscribe(HumanInputRequired, self._on_finished),
        ]

        def _detach():
            for unsubscribe in unsubscribers:
                unsubscribe()
            self._stop_live()

        return _detach

    # -- event handlers -----------------------------------------------------

    def _on_started(self, event: DomainEvent):
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
                title="[bold cyan]AEGIS SWR — Synthetic War Room[/bold cyan]",
                border_style="cyan",
            )
        )

        # Reset state so one view instance can render successive runs.
        self._trail = []
        self._stages_total = 7
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
        self._task_id = self._progress.add_task(
            "Extracting evidence from crash artifacts…", total=self._stages_total
        )
        self._live = Live(self._render(), console=self._console, refresh_per_second=12)
        self._live.start()

    def _on_evidence(self, event: DomainEvent):
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
        self._set_status(_NEXT_STATUS["data_adapter_node"])
        self._refresh()

    def _on_agent(self, event: DomainEvent):
        assert isinstance(event, AgentSpoke)
        turn = event.turn
        elapsed = time.monotonic() - self._stage_started

        if turn.turn_number != self._last_round:
            if self._last_round and self._progress is not None and self._task_id is not None:
                # Another debate round: 4 agent turns + consensus check.
                self._stages_total += 5
                self._progress.update(self._task_id, total=self._stages_total)
            self._last_round = turn.turn_number
            self._trail.append(
                Rule(f"Round {turn.turn_number} — panel deliberation", style="dim")
            )

        self._trail.append(_agent_trail_line(turn, elapsed))
        self._trail.append(_turn_summary(turn))
        self._set_status(_NEXT_STATUS.get(event.node, "Deliberating…"))
        self._refresh()

    def _on_consensus(self, event: DomainEvent):
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
        self._set_status("Reviewing consensus — deciding next step…")
        self._refresh()

    def _on_finished(self, event: DomainEvent):
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, completed=self._stages_total)
        self._progress = None
        self._refresh()
        self._stop_live()

    # -- rendering ------------------------------------------------------------

    def _set_status(self, message: str):
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, description=message, advance=1)
        self._stage_started = time.monotonic()

    def _render(self) -> Group:
        items: list[RenderableType] = list(self._trail)
        if self._progress is not None:
            items.append(Text())
            items.append(self._progress)
        return Group(*items)

    def _refresh(self):
        if self._live is not None:
            self._live.update(self._render())

    def _stop_live(self):
        if self._live is not None:
            self._live.stop()
            self._live = None


def make_view(console: Console, *, level: EvidenceLevel = "INFO") -> RichView | WarRoomView:
    """Pick the war-room view on wide terminals, the trail view otherwise.

    *level* selects the Evidence Stream verbosity for the war-room view
    (``DEBUG`` surfaces the detailed per-artifact evidence metadata).
    """
    return WarRoomView(console, level=level) if console.width >= 80 else RichView(console)


# ---------------------------------------------------------------------------
# Final verdict
# ---------------------------------------------------------------------------


def _build_diagnosis(report: RCAReport) -> str:
    """Compose the plain-text RCA shown inside the verdict panel.

    Mirrors the prototype's single-block diagnosis: human-readable prose with
    labelled sections and no Markdown markup (the panel supplies the styling).
    """
    level = report.confidence_level.value.upper()
    lines: list[str] = []

    lines.append("Root Cause Analysis")
    lines.append("")
    lines.append(report.root_cause.strip())
    lines.append("")
    lines.append(f"Confidence: {level} ({report.confidence_score:.0%})")

    if report.faulting_module:
        lines.append(f"Faulting Module:   {report.faulting_module}")
    if report.faulting_function:
        lines.append(f"Faulting Function: {report.faulting_function}")

    evidence = [
        e for e in report.primary_hypothesis.evidence if not e.startswith("__fix__:")
    ]
    if evidence:
        lines.append("")
        lines.append("Key Evidence:")
        lines.extend(f"  • {item}" for item in evidence)

    lines.append("")
    lines.append("Recommended Actions:")
    if report.mitigation_instructions:
        lines.extend(
            f"  {i}. {step}"
            for i, step in enumerate(report.mitigation_instructions, start=1)
        )
    else:
        target = report.faulting_module or "the implicated component"
        lines.append(
            f"  • Review the faulting module {target} and add defensive checks "
            "around the faulting code path."
        )

    if report.probabilistic_fix:
        conf = report.fix_confidence or 0.0
        lines.append("")
        lines.append(f"Probabilistic Fix (confidence {conf:.0%}):")
        lines.append(report.probabilistic_fix.strip())

    rounds = report.consensus_rounds
    lines.append("")
    lines.append(f"Resolved after {rounds} debate round{'s' if rounds != 1 else ''}.")

    return "\n".join(lines)


def render_verdict(
    report: RCAReport,
    *,
    console: Console | None = None,
    model: str = "",
    show_dialogue: bool = False,  # noqa: ARG001 — kept for CLI signature compatibility
):
    """Print the final report as a single prototype-style verdict frame.

    A converged investigation renders a green ``AI Root Cause Analysis`` panel
    subtitled with the model name.  A deadlock (HITL) renders a red
    ``Human Input Required`` panel instead and omits the diagnosis.
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

    console.print(
        Panel(
            Text(_build_diagnosis(report)),
            title="[bold green]AI Root Cause Analysis[/bold green]",
            subtitle=f"Model: {model}" if model else None,
            border_style="green",
            padding=(1, 2),
        )
    )
