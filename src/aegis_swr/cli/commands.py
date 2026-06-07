"""Aegis SWR command-line interface.

Options can be given as explicit CLI flags or read from a JSON config file
(default path: ``~/.local/share/aegis/config.json``).  Both sources share one
schema (:class:`~aegis_swr.cli._config.AnalyzeConfig`): the file is applied
first and explicit CLI flags are layered on top — defaults < config.json < CLI.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import click
import typer
from rich.console import Console
from typer.core import TyperGroup

from aegis_swr.cli._config import (
    DEFAULT_CONFIG_PATH,
    AnalyzeConfig,
    collect_cli_overrides,
    load_analyze_config,
    save_analyze_config,
)
from aegis_swr.cli._formatters import rich_formatter, stream_and_display
from aegis_swr.cli.aegis_logging import configure_logging

console = Console()


class FullHelpGroup(TyperGroup):
    """Root command group whose ``--help`` documents the *entire* app.

    Click/Typer only list the top-level commands and global options at the root.
    After that summary this group walks the command tree depth-first and prints
    the full help — usage, description, and every CLI option — for each
    subcommand and nested subcommand, so a single ``aegis --help`` (or
    ``python -m aegis_swr.cli --help``) shows all subparsers, subcommands, and
    options at once.
    """

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        super().format_help(ctx, formatter)  # the usual top-level summary
        _echo_subcommands_help(self, ctx)


def _echo_subcommands_help(group: TyperGroup, parent_ctx: click.Context) -> None:
    """Depth-first print the full help of every subcommand under *group*."""
    for name in group.list_commands(parent_ctx):
        cmd = group.get_command(parent_ctx, name)
        if cmd is None or getattr(cmd, "hidden", False):
            continue
        sub_ctx = click.Context(cmd, info_name=name, parent=parent_ctx)
        typer.echo()
        typer.echo("=" * 78)
        typer.echo(f"  {sub_ctx.command_path}")
        typer.echo("=" * 78)
        # get_help() renders the command's own help; for rich Typer commands it
        # prints as a side effect and returns "" (echoing it adds a blank line).
        typer.echo(cmd.get_help(sub_ctx))
        # Recurse into nested groups (e.g. ``config``), detected by duck typing
        # since Typer groups subclass Command, not click.Group.
        if hasattr(cmd, "list_commands"):
            _echo_subcommands_help(cmd, sub_ctx)


app = typer.Typer(
    name="aegis",
    cls=FullHelpGroup,
    help="Aegis SWR — production forensics platform.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Manage config.yaml settings.")
app.add_typer(config_app, name="config")


# ---------------------------------------------------------------------------
# aegis analyze
# ---------------------------------------------------------------------------

@app.command("analyze")
def analyze(  # noqa: PLR0913
    ctx: typer.Context,
    dump: Annotated[
        Path | None, typer.Option("--dump", help="Crash dump file (.dmp / .core / .ips).")
    ] = None,
    logs: Annotated[
        list[Path] | None, typer.Option("--log", help="Log file (repeatable).")
    ] = None,
    shots: Annotated[
        list[Path] | None, typer.Option("--shot", help="Screenshot file (repeatable).")
    ] = None,
    pcaps: Annotated[
        list[Path] | None,
        typer.Option("--pcap", help="Network traffic capture file, e.g. .pcap (repeatable)."),
    ] = None,
    sym: Annotated[Path | None, typer.Option("--sym", help="Symbol path.")] = None,
    assume: Annotated[
        str | None, typer.Option("--assume", help="User context / assumption text.")
    ] = None,
    engine: Annotated[
        str, typer.Option("--engine", help="Debug engine: auto | cdb | windbg_js.")
    ] = "auto",
    ai: Annotated[
        str, typer.Option("--ai", help="AI provider: anthropic | openai.")
    ] = "anthropic",
    store: Annotated[
        str,
        typer.Option("--store", help="Storage backend: filesystem | sqlite | s3 | postgres."),
    ] = "filesystem",
    store_config: Annotated[
        str | None, typer.Option("--store-config", help="Storage config value (path / bucket URL).")
    ] = None,
    code_provider: Annotated[
        str, typer.Option("--code-provider", help="Code backend: none | git | filesystem.")
    ] = "none",
    repo: Annotated[
        Path | None,
        typer.Option("--repo", help="Repo / source root (enables the code backend)."),
    ] = None,
    log_provider: Annotated[
        str, typer.Option("--log-provider", help="Log backend: file | fluent.")
    ] = "file",
    log_service: Annotated[
        str | None,
        typer.Option("--log-service", help="Service name for LogBackend.query_window."),
    ] = None,
    output: Annotated[
        str, typer.Option("--output", help="Output format: rich | json | quiet.")
    ] = "rich",
    severity: Annotated[
        str,
        typer.Option(
            "--severity",
            help="Log verbosity: DEBUG | INFO | WARNING | ERROR. "
            "Defaults to WARNING so logs do not interleave with the live display.",
        ),
    ] = "WARNING",
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="JSON config file (default: ~/.local/share/aegis/config.json).",
        ),
    ] = None,
    save_config: Annotated[
        bool,
        typer.Option("--save-config/--no-save-config", help="Save options to JSON file and exit."),
    ] = False,
):
    """Run analysis in-process — no API server required"""
    # Bootstrap logging at the CLI severity so config-loading warnings surface;
    # the effective level is re-applied from the merged config below.
    configure_logging(severity)

    # Normalise every CLI value into the shared config dict shape (Paths → str)
    # so both sources — config.json and the CLI — speak the same JSON dialect.
    cli_values: dict[str, object] = {
        "dump": str(dump) if dump else None,
        "logs": [str(p) for p in (logs or [])],
        "shots": [str(p) for p in (shots or [])],
        "pcaps": [str(p) for p in (pcaps or [])],
        "sym": str(sym) if sym else None,
        "assume": assume,
        "engine": engine,
        "ai": ai,
        "store": store,
        "store_config": store_config,
        "code_provider": code_provider,
        "repo": str(repo) if repo else None,
        "log_provider": log_provider,
        "log_service": log_service,
        "output": output,
        "severity": severity,
    }

    # If --save-config: persist the current CLI values and exit.
    if save_config:
        target = config_path or DEFAULT_CONFIG_PATH
        save_analyze_config(cli_values, target)
        console.print(f"[green]Config saved to:[/green] {target}")
        raise typer.Exit()

    # config.json first, explicit CLI flags atop. AnalyzeConfig is the single
    # source of truth for the keys; both sources feed it the same dict shape.
    file_config = load_analyze_config(config_path)
    overrides = collect_cli_overrides(ctx, cli_values)
    config = AnalyzeConfig.merge(file_config, overrides)

    # Re-apply logging at the effective severity (config.json may set it).
    configure_logging(config.severity)

    # Build IncidentSource. The code backend reads metadata["repo_path"]; the log
    # backend reads metadata["service"] (Data Adapter stages 8 and 4).
    from aegis_swr.core.schemas import IncidentMode, IncidentSource

    metadata: dict[str, str] = {}
    if config.repo:
        metadata["repo_path"] = config.repo
    if config.log_service:
        metadata["service"] = config.log_service

    mode = IncidentMode.CRASH_DUMP if config.dump else IncidentMode.LOG_FORENSICS
    source = IncidentSource(
        mode=mode,
        dump_path=config.dump,
        log_paths=list(config.logs),
        screenshot_paths=list(config.shots),
        network_capture_paths=list(config.pcaps),
        symbol_path=config.sym,
        user_assumption=config.assume,
        metadata=metadata,
    )

    # Build settings overrides for engine and AI provider.
    from aegis_swr.config.settings import Settings

    settings = Settings()
    settings.backends.ai.provider = config.ai
    settings.backends.debug.engine = config.engine
    settings.backends.storage.provider = config.store
    if config.store_config:
        _apply_store_config(settings, config.store, config.store_config)

    # Code backend: --repo implies enabled; default provider to git unless one
    # was explicitly requested via --code-provider.
    code_provider_opt = config.code_provider or "none"
    if config.repo:
        settings.backends.code.enabled = True
        settings.backends.code.repo_path = config.repo
        settings.backends.code.provider = (
            "git" if code_provider_opt == "none" else code_provider_opt
        )
    else:
        settings.backends.code.enabled = code_provider_opt != "none"
        if code_provider_opt != "none":
            settings.backends.code.provider = code_provider_opt

    # Log backend provider.
    settings.backends.log.provider = config.log_provider or "file"

    # Create backends.
    from aegis_swr.backends.ai import create_ai_backend
    from aegis_swr.backends.code import create_code_backend
    from aegis_swr.backends.debug import create_debug_backend
    from aegis_swr.backends.log import create_log_backend
    from aegis_swr.backends.storage import create_storage_backends

    ai_backend = create_ai_backend(settings.backends.ai)
    relational, object_store = create_storage_backends(settings.backends.storage)

    debug_backend = None
    if source.dump_path:
        try:
            debug_backend = create_debug_backend(settings.backends.debug)
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"Warning: debug backend unavailable ({exc})", err=True)

    code_backend = create_code_backend(settings.backends.code)

    log_backend = None
    try:
        log_backend = create_log_backend(settings.backends.log)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Warning: log backend unavailable ({exc})", err=True)

    from aegis_swr.core.orchestrator import Orchestrator

    orch = Orchestrator(
        settings=settings,
        ai_backend=ai_backend,
        debug_backend=debug_backend,
        relational_store=relational,
        object_store=object_store,
        log_backend=log_backend,
        code_backend=code_backend,
    )

    fmt = config.output

    if fmt == "quiet":
        # No display — just run and store.
        report = asyncio.run(orch.run(source))
    else:
        # For json output, stream the live display to stderr so stdout carries
        # only the machine-readable locator.
        from aegis_swr.cli._formatters import make_console
        stream_con = make_console(stderr=(fmt == "json"))
        report = asyncio.run(
            stream_and_display(orch, source, stream_con, level=config.severity)
        )
        if report is None:
            typer.echo("Error: investigation ended without producing a report.", err=True)
            raise typer.Exit(code=1)

    # The full report is persisted *exclusively* as a result file by the storage
    # backend — it is never dumped to stdout, regardless of --output or
    # --severity. We only surface where to find it.
    saved_path = _report_file_path(settings, str(report.incident_id))

    if fmt == "rich":
        # Agent dialogue was already printed live; show the final conclusion +
        # fix panels, then point to the saved result file.
        rich_formatter(report, model=settings.backends.ai.resolved_model, show_dialogue=False)
        if saved_path is not None:
            console.print(f"[green]Report saved:[/green] {saved_path}")
        else:
            console.print(
                f"[green]Report stored in the {settings.backends.storage.provider} "
                f"store[/green] (incident {report.incident_id})"
            )
    elif fmt == "json":
        # Machine-readable *locator* only — not the report body, which lives in
        # the result file. Lets scripts find the saved report on stdout.
        typer.echo(
            json.dumps(
                {
                    "incident_id": str(report.incident_id),
                    "mode": report.mode.value,
                    "status": "hitl_required" if report.hitl_request else "complete",
                    "storage": settings.backends.storage.provider,
                    "report_path": str(saved_path) if saved_path else None,
                },
                indent=2,
            )
        )

    if report.hitl_request:
        typer.echo(
            f"\nHuman input required: {report.hitl_request.question}",
            err=True,
        )
        raise typer.Exit(code=1)


def _report_file_path(settings: object, incident_id: str) -> Path | None:
    """Path of the saved report file for filesystem storage, else ``None``.

    Other backends (sqlite / s3 / postgres) have no single result file, so the
    caller falls back to naming the store instead.
    """
    from aegis_swr.config.settings import Settings

    assert isinstance(settings, Settings)
    storage = settings.backends.storage
    if storage.provider == "filesystem":
        return Path(storage.reports_dir).expanduser() / f"{incident_id}.json"
    return None


def _apply_store_config(settings: object, store: str, value: str):
    """Map --store-config value to the correct StorageSettings field"""
    from aegis_swr.config.settings import Settings

    assert isinstance(settings, Settings)
    if store == "filesystem":
        settings.backends.storage.reports_dir = value
    elif store == "sqlite":
        settings.backends.storage.db_path = value
    elif store == "s3":
        settings.backends.storage.object_store_url = value


# ---------------------------------------------------------------------------
# aegis export
# ---------------------------------------------------------------------------

@app.command("export")
def export(
    store: Annotated[
        str, typer.Option("--store", help="Source storage backend.")
    ] = "filesystem",
    store_config: Annotated[
        str | None, typer.Option("--store-config", help="Source config value.")
    ] = None,
    to_store: Annotated[
        str, typer.Option("--to-store", help="Destination storage backend.")
    ] = "filesystem",
    to_config: Annotated[
        str | None, typer.Option("--to-config", help="Destination config value.")
    ] = None,
):
    """Migrate reports between storage backends"""
    from aegis_swr.backends.storage import create_storage_backends
    from aegis_swr.config.settings import Settings

    async def _run() -> int:
        src_settings = Settings()
        src_settings.backends.storage.provider = store
        if store_config:
            _apply_store_config(src_settings, store, store_config)
        src_rel, _ = create_storage_backends(src_settings.backends.storage)
        if src_rel is None:
            typer.echo("Source storage has no relational store.", err=True)
            return 1

        dst_settings = Settings()
        dst_settings.backends.storage.provider = to_store
        if to_config:
            _apply_store_config(dst_settings, to_store, to_config)
        dst_rel, _ = create_storage_backends(dst_settings.backends.storage)
        if dst_rel is None:
            typer.echo("Destination storage has no relational store.", err=True)
            return 1

        reports = await src_rel.load_recent(limit=0)
        count = 0
        for report in reports:
            await dst_rel.save_report(report)
            count += 1
        typer.echo(f"Exported {count} reports from {store} to {to_store}.")
        return 0

    exit_code = asyncio.run(_run())
    if exit_code:
        raise typer.Exit(code=exit_code)


# ---------------------------------------------------------------------------
# aegis server
# ---------------------------------------------------------------------------

@app.command("server")
def server(
    host: Annotated[str, typer.Option("--host", help="Bind host.")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", help="Bind port.")] = 8000,
    reload: Annotated[
        bool, typer.Option("--reload/--no-reload", help="Enable hot-reload.")
    ] = False,
):
    """Start the FastAPI API server. (Phase 8 — not yet implemented.)"""
    typer.echo(
        "API server not yet implemented — available in Phase 8.\n"
        f"Configured for {host}:{port} (reload={reload})."
    )


# ---------------------------------------------------------------------------
# aegis config show / set
# ---------------------------------------------------------------------------

@config_app.command("show")
def config_show():
    """Print resolved config.yaml + env overrides (secrets redacted)"""
    from aegis_swr.config.settings import Settings

    settings = Settings()
    typer.echo(json.dumps(settings.redacted_dump(), indent=2))


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Dotted key path, e.g. backends.ai.model")],
    value: Annotated[str, typer.Argument(help="New value.")],
):
    """Set a single value in config.yaml"""
    import yaml

    config_path = Path("config.yaml")
    if config_path.exists():
        with config_path.open(encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
            data: dict[str, object] = loaded if isinstance(loaded, dict) else {}
    else:
        data = {}

    parts = key.split(".")
    node: dict[str, object] = data
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        node = child if isinstance(child, dict) else {}
    node[parts[-1]] = value

    with config_path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)
    typer.echo(f"Set {key} = {value!r} in {config_path}")
