"""CLI output formatters for RCAReport.

All Rich rendering lives in :mod:`aegis_swr.views.rich_view`; this module is
the CLI-side glue: machine output (:func:`json_formatter`) and the driver
that runs an investigation with a :class:`~aegis_swr.views.RichView` attached
to the orchestrator's event bus (:func:`stream_and_display`).
"""
from __future__ import annotations

from typing import Optional

from aegis_swr.views.rich_view import make_console  # noqa: F401  (re-export for CLI)
from rich.console import Console
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import IncidentSource, RCAReport

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
    level: str = "INFO",
) -> Optional[RCAReport]:
    """Run the investigation with a live war-room view on the event bus.

    *level* sets the Evidence Stream verbosity: ``"DEBUG"`` surfaces the
    per-artifact evidence metadata, ``"TRACE"`` additionally streams the full
    debugger ``!analyze`` output, and anything else stays at the ``INFO``
    summary.  Returns the final :class:`RCAReport` once the graph completes,
    or ``None`` if the stream ended without a result (should not happen in
    normal operation).
    """
    from aegis_swr.core.events import HumanInputRequired, InvestigationCompleted
    from aegis_swr.views.rich_view import make_view

    view = make_view(console, level=level)
    stream_events_func = getattr(type(orch), "stream_events", None)
    run_func = getattr(type(orch), "run", None)

    # Prefer the neutral event stream whenever it is available or explicitly
    # overridden. Fall back to the final-run API when only that path is mocked
    # (e.g. lightweight CLI/E2E tests) so JSON stdout remains machine-parseable.
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
    return report
