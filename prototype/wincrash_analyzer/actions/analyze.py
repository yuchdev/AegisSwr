"""Analyze action: perform crash dump analysis"""
import logging
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from wincrash_analyzer.backends.debug.factory import create_debug_backend
from wincrash_analyzer.backends.ai.factory import create_ai_backend
from wincrash_analyzer.backends.store.factory import create_storage_backend
from wincrash_analyzer.core.orchestrator import Orchestrator
from wincrash_analyzer.core.data_sources import DumpSource, SymbolSource, LogSource, SourceCollection

logger = logging.getLogger(__name__)
console = Console()

def run_analyze(args, resolved_cdb):
    """
    Execute the analysis pipeline.

    @param args: Parsed CLI arguments.
    @param resolved_cdb: The resolved absolute path to cdb.exe.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task(description="Invoking debug engine...", total=None)
        
        debug_backend = create_debug_backend(args.engine, cdb_path=resolved_cdb)
        ai_backend = create_ai_backend(args.ai)
        storage_backend = create_storage_backend(args.store, args.store_config)

        orchestrator = Orchestrator(
            debug_backend=debug_backend,
            ai_backend=ai_backend,
            storage_backend=storage_backend,
        )

        sources = SourceCollection(
            dump=DumpSource(args.dump) if args.dump else None,
            symbols=SymbolSource(args.sym) if args.sym else None,
            logs=LogSource(args.log_source) if args.log_source else None,
        )

        diagnosis = orchestrator.run(
            sources, 
            analyze_history=args.analyze_history,
            assumption=args.assumption if hasattr(args, 'assumption') else None
        )

    console.print(
        Panel(
            diagnosis,
            title="[bold green]AI Root Cause Analysis[/bold green]",
            subtitle=f"Model: {args.ai}",
            border_style="green",
        )
    )
