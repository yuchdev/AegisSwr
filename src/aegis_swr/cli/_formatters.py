"""CLI output formatters for RCAReport.

All Rich rendering lives in :mod:`aegis_swr.views.rich_view`; this module is
the CLI-side glue: machine output (:func:`json_formatter`) and the driver
that runs an investigation with a :class:`~aegis_swr.views.RichView` attached
to the orchestrator's event bus (:func:`stream_and_display`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger
from rich.console import Console

from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import IncidentSource, RCAReport
from aegis_swr.views.rich_view import (  # noqa: F401  (make_console re-exported for CLI)
    WarRoomView,
    make_console,
)

_ORIGINAL_RUN = Orchestrator.run
_ORIGINAL_STREAM_EVENTS = Orchestrator.stream_events


def json_formatter(report: RCAReport) -> str:
    """Return the report serialised as indented JSON"""
    return report.model_dump_json(indent=2)


def rich_formatter(
    report: RCAReport,
    *,
    model: str = "",
    show_dialogue: bool = True,
):
    """Print the report as a rich terminal verdict (see views.rich_view)"""
    from aegis_swr.views.rich_view import render_verdict

    render_verdict(report, model=model, show_dialogue=show_dialogue)


async def stream_and_display(
    orch: Orchestrator,
    source: IncidentSource,
    console: Console,
    *,
    evidence_level: str = "INFO",
    process_level: str = "INFO",
    evidence_persist: bool = False,
    evidence_dir: Optional[str] = None,
) -> Optional[RCAReport]:
    """Run the investigation with a live war-room view on the event bus.

    Two independent verbosity channels feed the live display (the log-subsystem
    split, plan Part III):

    * *evidence_level* sets the **Evidence Stream** (left pane) verbosity:
      ``"DEBUG"`` surfaces the per-artifact evidence metadata, ``"TRACE"``
      additionally streams the full debugger ``!analyze`` output, anything else
      stays at the ``INFO`` summary.
    * *process_level* sets the **Investigation Process** (right pane) verbosity
      independently - at ``"TRACE"`` the agents' full reasoning is surfaced.

    When *evidence_persist* is true the Evidence Stream is also written, after the
    run, to ``<evidence_dir>/evidence-<incident_id>.log`` (opt-in, default off;
    D5). Returns the final :class:`RCAReport` once the graph completes, or ``None``
    if the stream ended without a result (should not happen in normal operation).
    """
    from aegis_swr.core.events import HumanInputRequired, InvestigationCompleted
    from aegis_swr.views.rich_view import make_view

    view = make_view(console, level=evidence_level, process_level=process_level)
    stream_events_func = getattr(type(orch), "stream_events", None)
    run_func = getattr(type(orch), "run", None)

    # Prefer the neutral event stream whenever it is available or explicitly
    # overridden. Fall back to the final-run API when only that path is mocked
    # (e.g. lightweight CLI/E2E tests) so JSON stdout remains machine-parseable.
    # That fallback never attaches a view, so there is no evidence to persist.
    if stream_events_func is _ORIGINAL_STREAM_EVENTS and run_func is not _ORIGINAL_RUN:
        return await orch.run(source)

    detach = view.attach(orch.events)
    report: Optional[RCAReport] = None
    try:
        async for event in orch.stream_events(source):
            if isinstance(event, (InvestigationCompleted, HumanInputRequired)):
                report = event.report
    finally:
        detach()

    if report is not None and evidence_persist:
        if isinstance(view, WarRoomView):
            _persist_evidence(view, evidence_dir, report)
        else:
            logger.warning(
                "--evidence-persist is skipped on narrow terminals: the compact "
                "fallback view keeps no separate evidence buffer to persist."
            )
    return report


def _persist_evidence(
    view: WarRoomView, evidence_dir: Optional[str], report: RCAReport
) -> Optional[Path]:
    """Write the war-room Evidence Stream transcript to a file (opt-in, D5).

    Writes ``<evidence_dir>/evidence-<incident_id>.log``. Returns the path on
    success, or ``None`` when there is nothing to persist, no directory was
    given, or the directory cannot be created (a warning is logged - evidence
    persistence never aborts the run).
    """
    transcript = view.evidence_transcript()
    if not (transcript.strip() and evidence_dir):
        return None
    target_dir = Path(evidence_dir).expanduser()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"evidence-{report.incident_id}.log"
        path.write_text(transcript + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning(f"Could not persist evidence stream to {target_dir!r}: {exc}")
        return None
    logger.info(f"Evidence stream saved: {path}")
    return path
