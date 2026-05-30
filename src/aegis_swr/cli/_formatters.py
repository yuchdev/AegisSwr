"""CLI output formatters for RCAReport."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aegis_swr.core.schemas import RCAReport


def json_formatter(report: RCAReport) -> str:
    """Return the report serialised as indented JSON."""
    return report.model_dump_json(indent=2)


def rich_formatter(report: RCAReport) -> None:
    """Print the report as a rich terminal display."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table

    console = Console()

    # --- Conclusion panel ---------------------------------------------------
    conf_str = f"{report.confidence_score:.0%} ({report.confidence_level.value.upper()})"
    module_line = f"\n[dim]Module:[/dim] {report.faulting_module}" if report.faulting_module else ""
    function_line = (
        f"\n[dim]Function:[/dim] {report.faulting_function}" if report.faulting_function else ""
    )
    conclusion_body = (
        f"[bold]{report.root_cause}[/bold]"
        f"\n[dim]Confidence:[/dim] {conf_str}"
        f"{module_line}{function_line}"
    )
    console.print(
        Panel(
            conclusion_body,
            title="[bold green]Root Cause Analysis[/bold green]",
            border_style="green",
        )
    )

    # --- Agent dialogue table -----------------------------------------------
    if report.agent_dialogue:
        table = Table(title="Agent Dialogue", expand=False)
        table.add_column("Round", style="dim", width=6)
        table.add_column("Agent", style="bold", width=22)
        table.add_column("Message")
        table.add_column("Conf", style="cyan", width=6)
        for turn in report.agent_dialogue:
            table.add_row(
                str(turn.turn_number),
                turn.agent,
                turn.message[:120] + ("…" if len(turn.message) > 120 else ""),
                f"{turn.confidence_score:.0%}",
            )
        console.print(table)

    # --- Mitigation --------------------------------------------------------
    if report.mitigation_instructions:
        steps = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(report.mitigation_instructions))
        console.print(Panel(steps, title="Mitigation Instructions", border_style="yellow"))

    # --- Probabilistic fix -------------------------------------------------
    if report.probabilistic_fix:
        console.print(
            Panel(
                Syntax(report.probabilistic_fix, "diff", theme="monokai"),
                title=(
                    f"[bold]Probabilistic Fix[/bold]"
                    f" (confidence {report.fix_confidence or 0:.0%})"
                ),
                border_style="blue",
            )
        )

    # --- HITL request ------------------------------------------------------
    if report.hitl_request:
        req = report.hitl_request
        items = "\n".join(f"  • {d}" for d in req.requested_data)
        body = f"[bold yellow]{req.question}[/bold yellow]\n\n{req.context_summary}\n\n{items}"
        console.print(
            Panel(
                body,
                title="[bold red]Human Input Required[/bold red]",
                border_style="red",
            )
        )
