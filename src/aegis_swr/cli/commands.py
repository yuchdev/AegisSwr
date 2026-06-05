"""Aegis SWR command-line interface.

Options can be given as explicit CLI flags or read from a JSON config file
(default path: ``~/.aegis-swr/analyze.json``).  An explicit flag always wins
over a JSON value, which wins over the hardcoded default — the same precedence
chain as the prototype's ``--config-file`` / ``--save-config`` pattern.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from aegis_swr.cli._config import (
    DEFAULT_CONFIG_PATH,
    load_analyze_config,
    merge_options,
    save_analyze_config,
)
from aegis_swr.cli._formatters import json_formatter, rich_formatter, stream_and_display
from aegis_swr.cli.aegis_logging import configure_logging

console = Console()

app = typer.Typer(
    name="aegis",
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
        typer.Option("--config", help="JSON config file (default: ~/.aegis-swr/analyze.json)."),
    ] = None,
    save_config: Annotated[
        bool,
        typer.Option("--save-config/--no-save-config", help="Save options to JSON file and exit."),
    ] = False,
):
    """Run analysis in-process — no API server required"""
    configure_logging(severity)

    file_config = load_analyze_config(config_path)

    # If --save-config: write current CLI values (no merge needed) and exit.
    if save_config:
        opts_to_save = {
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
        target = config_path or DEFAULT_CONFIG_PATH
        save_analyze_config(opts_to_save, target)
        console.print(f"[green]Config saved to:[/green] {target}")
        raise typer.Exit()

    opts = merge_options(
        file_config,
        ctx,
        dump=dump,
        logs=logs or [],
        shots=shots or [],
        pcaps=pcaps or [],
        sym=sym,
        assume=assume,
        engine=engine,
        ai=ai,
        store=store,
        store_config=store_config,
        code_provider=code_provider,
        repo=repo,
        log_provider=log_provider,
        log_service=log_service,
        output=output,
        severity=severity,
    )

    # Build IncidentSource. The code backend reads metadata["repo_path"]; the log
    # backend reads metadata["service"] (Data Adapter stages 8 and 4).
    from aegis_swr.core.schemas import IncidentMode, IncidentSource

    metadata: dict[str, str] = {}
    if opts.get("repo"):
        metadata["repo_path"] = str(opts["repo"])
    if opts.get("log_service"):
        metadata["service"] = str(opts["log_service"])

    mode = IncidentMode.CRASH_DUMP if opts.get("dump") else IncidentMode.LOG_FORENSICS
    source = IncidentSource(
        mode=mode,
        dump_path=str(opts["dump"]) if opts.get("dump") else None,
        log_paths=[str(p) for p in (opts.get("logs") or [])],
        screenshot_paths=[str(p) for p in (opts.get("shots") or [])],
        network_capture_paths=[str(p) for p in (opts.get("pcaps") or [])],
        symbol_path=str(opts["sym"]) if opts.get("sym") else None,
        user_assumption=opts.get("assume"),
        metadata=metadata,
    )

    # Build settings overrides for engine and AI provider.
    from aegis_swr.config.settings import Settings

    settings = Settings()
    settings.backends.ai.provider = opts["ai"]
    settings.backends.debug.engine = opts["engine"]
    settings.backends.storage.provider = opts["store"]
    if opts.get("store_config"):
        _apply_store_config(settings, opts["store"], opts["store_config"])

    # Code backend: --repo implies enabled; default provider to git unless one
    # was explicitly requested via --code-provider.
    code_provider_opt = opts.get("code_provider") or "none"
    if opts.get("repo"):
        settings.backends.code.enabled = True
        settings.backends.code.repo_path = str(opts["repo"])
        settings.backends.code.provider = (
            "git" if code_provider_opt == "none" else code_provider_opt
        )
    else:
        settings.backends.code.enabled = code_provider_opt != "none"
        if code_provider_opt != "none":
            settings.backends.code.provider = code_provider_opt

    # Log backend provider.
    settings.backends.log.provider = opts.get("log_provider") or "file"

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

    fmt = opts.get("output", "rich")

    if fmt == "quiet":
        # No display — just run and store.
        report = asyncio.run(orch.run(source))
    else:
        # For json output, stream the live display to stderr so stdout stays
        # clean for machine parsing.
        from aegis_swr.cli._formatters import make_console
        stream_con = make_console(stderr=(fmt == "json"))
        report = asyncio.run(
            stream_and_display(orch, source, stream_con, level=opts.get("severity", "INFO"))
        )
        if report is None:
            typer.echo("Error: investigation ended without producing a report.", err=True)
            raise typer.Exit(code=1)

    if fmt == "json":
        typer.echo(json_formatter(report))
    elif fmt == "rich":
        # Agent dialogue was already printed live; show the final conclusion +
        # fix panels only.
        rich_formatter(report, model=settings.backends.ai.resolved_model, show_dialogue=False)

    if report.hitl_request:
        typer.echo(
            f"\nHuman input required: {report.hitl_request.question}",
            err=True,
        )
        raise typer.Exit(code=1)


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
