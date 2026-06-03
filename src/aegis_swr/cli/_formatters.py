"""CLI output formatters for RCAReport.

All Rich rendering lives in :mod:`aegis_swr.views.rich_view`; this module is
the CLI-side glue: machine output (:func:`json_formatter`) and the driver
that runs an investigation with a :class:`~aegis_swr.views.RichView` attached
to the orchestrator's event bus (:func:`stream_and_display`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aegis_swr.views.rich_view import make_console  # noqa: F401  (re-export for CLI)

if TYPE_CHECKING:
    from rich.console import Console

    from aegis_swr.core.orchestrator import Orchestrator
    from aegis_swr.core.schemas import IncidentSource, RCAReport


def json_formatter(report: RCAReport) -> str:
    """Return the report serialised as indented JSON."""
    return report.model_dump_json(indent=2)


def rich_formatter(report: RCAReport, *, show_dialogue: bool = True) -> None:
    """Print the report as a rich terminal verdict (see views.rich_view)."""
    from aegis_swr.views.rich_view import render_verdict

    render_verdict(report, show_dialogue=show_dialogue)


async def stream_and_display(
    orch: Orchestrator,
    source: IncidentSource,
    console: Console,
) -> RCAReport | None:
    """Run the investigation with a live RichView attached to the event bus.

    Returns the final :class:`RCAReport` once the graph completes, or ``None``
    if the stream ended without a result (should not happen in normal operation).
    """
    from aegis_swr.core.events import HumanInputRequired, InvestigationCompleted
    from aegis_swr.views.rich_view import RichView

    view = RichView(console)
    detach = view.attach(orch.events)
    report: RCAReport | None = None
    try:
        async for event in orch.stream_events(source):
            if isinstance(event, (InvestigationCompleted, HumanInputRequired)):
                report = event.report
    finally:
        detach()
    return report
