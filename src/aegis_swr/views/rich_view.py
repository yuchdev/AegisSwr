"""Rich terminal view adapter.

Subscribes to the core :class:`~aegis_swr.core.events.EventBus` and renders
the investigation as a live "war room" display: an animated waiting line
(spinner + current activity + stage bar + elapsed clock) above a compact
trail of completed agent turns and consensus meters.

:func:`render_verdict` renders the final report after the panel concludes.
"""
from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Callable

from rich.console import Console, Group, RenderableType
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
from rich.syntax import Syntax
from rich.table import Table
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

if TYPE_CHECKING:
    from aegis_swr.core.events import DomainEvent, EventBus
    from aegis_swr.core.schemas import AgentTurn, RCAReport


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

def _conf_color(score: float) -> str:
    return "green" if score >= 0.80 else "yellow" if score >= 0.50 else "red"


def _confidence_bar(score: float, width: int = 24) -> Text:
    """Render a unicode confidence bar: ``████████░░░░ 67%``."""
    filled = max(0, min(width, round(score * width)))
    color = _conf_color(score)
    bar = Text()
    bar.append("█" * filled, style=color)
    bar.append("░" * (width - filled), style="grey35")
    bar.append(f" {score:.0%}", style=f"bold {color}")
    return bar


def _agent_trail_line(turn: AgentTurn, elapsed: float) -> Text:
    """One compact line for a completed agent turn in the live trail."""
    color = _conf_color(turn.confidence_score)
    line = Text("  ")
    line.append("✔ ", style="bold green")
    line.append(f"{turn.agent:<22}", style="bold")
    line.append(f"{turn.confidence_score:>4.0%}", style=f"bold {color}")
    line.append(" confident", style="dim")
    line.append(f"  ·  {elapsed:.1f}s", style="dim")
    return line


def _turn_summary(turn: AgentTurn, limit: int = 96) -> Text:
    """A single dim line previewing what the agent concluded."""
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


# ---------------------------------------------------------------------------
# Live war-room view
# ---------------------------------------------------------------------------

class RichView:
    """Live terminal adapter: renders domain events as they are published."""

    def __init__(self, console: Console | None = None) -> None:
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
        """Subscribe to *bus*; returns a detach function."""
        unsubscribers = [
            bus.subscribe(InvestigationStarted, self._on_started),
            bus.subscribe(EvidenceExtracted, self._on_evidence),
            bus.subscribe(AgentSpoke, self._on_agent),
            bus.subscribe(ConsensusEvaluated, self._on_consensus),
            bus.subscribe(InvestigationCompleted, self._on_finished),
            bus.subscribe(HumanInputRequired, self._on_finished),
        ]

        def _detach() -> None:
            for unsubscribe in unsubscribers:
                unsubscribe()
            self._stop_live()

        return _detach

    # -- event handlers -----------------------------------------------------

    def _on_started(self, event: DomainEvent) -> None:
        assert isinstance(event, InvestigationStarted)
        from pathlib import Path

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

    def _on_evidence(self, event: DomainEvent) -> None:
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

    def _on_agent(self, event: DomainEvent) -> None:
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

    def _on_consensus(self, event: DomainEvent) -> None:
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

    def _on_finished(self, event: DomainEvent) -> None:
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, completed=self._stages_total)
        self._progress = None
        self._refresh()
        self._stop_live()

    # -- rendering ------------------------------------------------------------

    def _set_status(self, message: str) -> None:
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, description=message, advance=1)
        self._stage_started = time.monotonic()

    def _render(self) -> Group:
        items: list[RenderableType] = list(self._trail)
        if self._progress is not None:
            items.append(Text())
            items.append(self._progress)
        return Group(*items)

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def _stop_live(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None


# ---------------------------------------------------------------------------
# Final verdict
# ---------------------------------------------------------------------------

def render_verdict(
    report: RCAReport,
    *,
    console: Console | None = None,
    show_dialogue: bool = False,
) -> None:
    """Print the final report as a polished terminal verdict."""
    console = console or make_console()
    console.print()

    # --- Banner --------------------------------------------------------------
    if report.hitl_request:
        console.rule("[bold red]⚠  PANEL DEADLOCKED — HUMAN INPUT REQUIRED[/bold red]", style="red")
    else:
        console.rule(
            "[bold green]✔  CONSENSUS REACHED — VERDICT APPROVED BY THE PANEL[/bold green]",
            style="green",
        )
    console.print()

    # --- Root cause panel -----------------------------------------------------
    body = Text()
    body.append(report.root_cause.strip(), style="bold white")
    body.append("\n\n")
    body.append("Confidence  ", style="dim")
    body.append_text(_confidence_bar(report.confidence_score))
    body.append(f"  {report.confidence_level.value.upper()}",
                style=f"bold {_conf_color(report.confidence_score)}")
    if report.faulting_module:
        body.append("\nModule      ", style="dim")
        body.append(report.faulting_module)
    if report.faulting_function:
        body.append("\nFunction    ", style="dim")
        body.append(report.faulting_function)
    console.print(
        Panel(
            body,
            title="[bold green]Root Cause Analysis[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    # --- Panel approval table --------------------------------------------------
    final_turns = _final_turn_per_agent(report.agent_dialogue)
    if final_turns:
        table = Table(
            title="Panel Verdict",
            expand=False,
            border_style="dim",
            title_style="bold",
            pad_edge=True,
        )
        table.add_column("Agent", style="bold", min_width=22)
        table.add_column("Confidence", min_width=30)
        table.add_column("Verdict", min_width=12)
        for turn in final_turns:
            approved = turn.confidence_score >= 0.65
            verdict = (
                Text("✔ Approved", style="bold green")
                if approved
                else Text("⚠ Reserved", style="bold yellow")
            )
            table.add_row(turn.agent, _confidence_bar(turn.confidence_score), verdict)
        console.print(table)

    # --- Key evidence -----------------------------------------------------------
    evidence = [
        e for e in report.primary_hypothesis.evidence if not e.startswith("__fix__:")
    ]
    if evidence:
        bullets = "\n".join(f"  • {e}" for e in evidence[:8])
        console.print(Panel(bullets, title="[bold]Key Evidence[/bold]", border_style="cyan"))

    # --- Full agent dialogue (opt-in) --------------------------------------------
    if show_dialogue and report.agent_dialogue:
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

    # --- Mitigation ---------------------------------------------------------------
    if report.mitigation_instructions:
        steps = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(report.mitigation_instructions))
        console.print(Panel(steps, title="[bold]Mitigation Instructions[/bold]", border_style="yellow"))

    # --- Probabilistic fix ----------------------------------------------------------
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

    # --- HITL request -----------------------------------------------------------------
    if report.hitl_request:
        req = report.hitl_request
        items = "\n".join(f"  • {d}" for d in req.requested_data)
        hitl_body = f"[bold yellow]{req.question}[/bold yellow]\n\n{req.context_summary}\n\n{items}"
        console.print(
            Panel(
                hitl_body,
                title="[bold red]Human Input Required[/bold red]",
                border_style="red",
            )
        )

    # --- Footer --------------------------------------------------------------------------
    tokens = report.total_input_tokens + report.total_output_tokens
    footer = (
        f"incident {str(report.incident_id)[:8]}"
        f"  ·  {report.consensus_rounds} debate round{'s' if report.consensus_rounds != 1 else ''}"
        f"  ·  {tokens:,} tokens"
    )
    if report.symbol_resolution_score is not None:
        footer += f"  ·  symbol coverage {report.symbol_resolution_score:.0%}"
    console.print(Text(footer, style="dim"), justify="center")
    console.print()


def _final_turn_per_agent(dialogue: list[AgentTurn]) -> list[AgentTurn]:
    """Return each agent's last turn, preserving panel speaking order."""
    last: dict[str, AgentTurn] = {}
    for turn in dialogue:
        last[turn.agent] = turn
    return list(last.values())
