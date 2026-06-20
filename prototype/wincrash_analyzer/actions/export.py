"""Export action: migrate analysis records between store backends"""
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from wincrash_analyzer.backends.store.factory import create_storage_backend

logger = logging.getLogger(__name__)
console = Console()

def run_export(args):
    """
    Export records from source store to destination store.

    Uses existing storage interface.
    --store and --store-config define the source.
    --to-store and --to-store-config define the destination.

    @param args: Parsed CLI arguments.
    """
    if not args.to_store:
        console.print("[bold red]Error:[/bold red] --to-store is required for export action.")
        return

    source_backend = create_storage_backend(args.store, args.store_config)
    dest_backend = create_storage_backend(args.to_store, args.to_store_config)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task(description=f"Exporting from {args.store} to {args.to_store}...", total=None)
        
        records = source_backend.load_all()
        logger.info("Loaded %d records from source store.", len(records))
        
        success_count = 0
        for record in records:
            if dest_backend.save(record):
                success_count += 1
            else:
                logger.error("Failed to export record: %s", record.get("report_id", "unknown"))

    console.print(f"[bold green]Export complete.[/bold green] Processed {len(records)} records, {success_count} successful.")
