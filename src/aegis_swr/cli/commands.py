"""Aegis SWR command-line interface.

Options can be given as explicit CLI flags or read from a JSON config file
(default path: ``~/.aegis-swr/config.json``).  Both sources share one
schema (:class:`~aegis_swr.cli._config.AnalyzeConfig`): the file is applied
first and explicit CLI flags are layered on top - defaults < config.json < CLI.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Optional

import click
import typer
from loguru import logger
from rich.console import Console
from typer.core import TyperGroup

from aegis_swr.cli._config import (
    DEFAULT_CONFIG_PATH,
    AnalyzeConfig,
    collect_cli_overrides,
    load_analyze_config,
    save_analyze_config,
)
from aegis_swr.cli._formatters import json_formatter, rich_formatter, stream_and_display
from aegis_swr.cli.aegis_logging import configure_logging
from aegis_swr.config.settings import CONFIG_DIR

console = Console()

#: Allowed values for the war-room verbosity channels (evidence / process). The
#: application log channel accepts the full loguru range, so it is left to loguru.
_STREAM_LEVELS = frozenset({"INFO", "TRACE"})
#: Allowed application log sinks (elk/fluent are stubs until a later phase).
_LOG_SINKS = frozenset({"file", "elk", "fluent"})
#: Default directory for the opt-in Evidence Stream transcript (--evidence-persist).
_DEFAULT_EVIDENCE_DIR = str(CONFIG_DIR / "evidence")


def _validate_log_options(config: AnalyzeConfig) -> None:
    """Reject out-of-range logging-channel values (from CLI flags or config.json).

    Evidence and Investigation-Process accept only ``INFO``/``TRACE``; the
    application log sink must be ``file``/``elk``/``fluent``. The application
    severity accepts the full loguru range, so it is left to loguru to validate.
    """
    errors: list[str] = []
    if config.evidence_severity.upper() not in _STREAM_LEVELS:
        errors.append(
            f"--evidence-severity must be INFO or TRACE (got {config.evidence_severity!r})"
        )
    if config.process_severity.upper() not in _STREAM_LEVELS:
        errors.append(f"--process-severity must be INFO or TRACE (got {config.process_severity!r})")
    if config.log_sink.lower() not in _LOG_SINKS:
        errors.append(f"--log-sink must be one of file, elk, fluent (got {config.log_sink!r})")
    if errors:
        for message in errors:
            typer.echo(f"Error: {message}", err=True)
        raise typer.Exit(code=2)


class FullHelpGroup(TyperGroup):
    """Root command group whose ``--help`` documents the *entire* app.

    Click/Typer only list the top-level commands and global options at the root.
    After that summary this group walks the command tree depth-first and prints
    the full help - usage, description, and every CLI option - for each
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
    help="Aegis SWR - production forensics platform.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Manage runtime settings in ~/.aegis-swr/config.json.")
app.add_typer(config_app, name="config")


# ---------------------------------------------------------------------------
# aegis analyze
# ---------------------------------------------------------------------------


@app.command("analyze")
def analyze(  # noqa: PLR0913
    ctx: typer.Context,
    dump: Annotated[
        Optional[Path], typer.Option("--dump", help="Crash dump file (.dmp / .core / .ips).")
    ] = None,
    logs: Annotated[
        Optional[list[Path]], typer.Option("--log", help="Log file (repeatable).")
    ] = None,
    shots: Annotated[
        Optional[list[Path]], typer.Option("--shot", help="Screenshot file (repeatable).")
    ] = None,
    pcaps: Annotated[
        Optional[list[Path]],
        typer.Option("--pcap", help="Network traffic capture file, e.g. .pcap (repeatable)."),
    ] = None,
    sym: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--sym",
            help="Symbol search path (repeatable). Each value is appended to the debugger symbol chain.",
        ),
    ] = None,
    assume: Annotated[
        Optional[str], typer.Option("--assume", help="User context / assumption text.")
    ] = None,
    engine: Annotated[
        str, typer.Option("--engine", help="Debug engine: auto | cdb | windbg_js.")
    ] = "auto",
    ai: Annotated[
        Optional[str], typer.Option("--ai", help="AI provider: anthropic | openai | bedrock.")
    ] = None,
    store: Annotated[
        str,
        typer.Option("--store", help="Storage backend: filesystem | sqlite | s3 | postgres."),
    ] = "filesystem",
    store_config: Annotated[
        Optional[str],
        typer.Option("--store-config", help="Storage config value (path / bucket URL)."),
    ] = None,
    code_provider: Annotated[
        str, typer.Option("--code-provider", help="Code backend: none | git | filesystem.")
    ] = "none",
    repo: Annotated[
        Optional[Path],
        typer.Option("--repo", help="Repo / source root (enables the code backend)."),
    ] = None,
    log_provider: Annotated[
        str,
        typer.Option(
            "--log-provider",
            help="Log-ingestion backend (reads the investigated system's logs): "
            "file | fluent. Sets ingest.log_source.provider -> backends.log.provider.",
        ),
    ] = "file",
    log_service: Annotated[
        Optional[str],
        typer.Option(
            "--log-service",
            help="Service name for LogBackend.query_window "
            "(sets ingest.log_source.service -> metadata['service']).",
        ),
    ] = None,
    output: Annotated[
        str,
        typer.Option(
            "--output",
            help="Output format: rich | json | json-full | quiet. "
            "'json' prints a locator pointing at the saved report; "
            "'json-full' prints the full report JSON to stdout instead.",
        ),
    ] = "rich",
    log_severity: Annotated[
        str,
        typer.Option(
            "--log-severity",
            help="Application log verbosity (Aegis's own diagnostics): "
            "TRACE | DEBUG | INFO | WARNING | ERROR. The Evidence Stream and "
            "Investigation Process panes have their own --evidence-severity / "
            "--process-severity controls.",
        ),
    ] = "WARNING",
    log_dir: Annotated[
        Optional[str],
        typer.Option(
            "--log-dir",
            help="Directory for the classic application log file "
            "(default: ~/.aegis-swr/logs). The rotating "
            "aegis-swr.log is written here at the chosen --log-severity.",
        ),
    ] = None,
    log_sink: Annotated[
        str,
        typer.Option(
            "--log-sink",
            help="Application log sink: file | elk | fluent. elk/fluent are not yet "
            "implemented and fall back to the file sink (planned: later phase).",
        ),
    ] = "file",
    evidence_severity: Annotated[
        str,
        typer.Option(
            "--evidence-severity",
            help="Evidence Stream (war-room left pane) verbosity: INFO | TRACE. "
            "INFO shows the curated summary; TRACE surfaces every evidence detail.",
        ),
    ] = "INFO",
    process_severity: Annotated[
        str,
        typer.Option(
            "--process-severity",
            help="Investigation Process (war-room right pane) verbosity: INFO | TRACE. "
            "TRACE prints each agent's full reasoning, not just the headline.",
        ),
    ] = "INFO",
    evidence_persist: Annotated[
        bool,
        typer.Option(
            "--evidence-persist/--no-evidence-persist",
            help="Persist the Evidence Stream to a file (off by default). Not yet "
            "implemented; reserved for a later phase.",
        ),
    ] = False,
    config_path: Annotated[
        Optional[Path],
        typer.Option(
            "--config",
            help="JSON config file (default: ~/.aegis-swr/config.json).",
        ),
    ] = None,
    save_config: Annotated[
        bool,
        typer.Option("--save-config/--no-save-config", help="Save options to JSON file and exit."),
    ] = False,
):
    """Run analysis in-process - no API server required"""
    # Bootstrap logging at the CLI severity with a (delayed) file sink at the
    # resolved log dir, so warnings raised while loading config.json - e.g. an
    # unreadable or malformed file - are captured in the log file, not just on
    # stderr. The dir resolves to --log-dir (if given) else the schema default,
    # which is exactly the effective dir when config.json fails to load (defaults
    # take over). The effective level/sink/dir are re-applied from the merged
    # config below; delay=True means a clean run leaves no empty bootstrap file.
    configure_logging(log_severity, log_dir=(log_dir or AnalyzeConfig().log_dir))

    # Normalise every CLI value into the shared config dict shape (Paths → str)
    # so both sources - config.json and the CLI - speak the same JSON dialect.
    cli_values: dict[str, object] = {
        "dump": str(dump) if dump else None,
        "logs": [str(p) for p in (logs or [])],
        "shots": [str(p) for p in (shots or [])],
        "pcaps": [str(p) for p in (pcaps or [])],
        "sym": [str(p) for p in (sym or [])],
        "assume": assume,
        "engine": engine,
        "store": store,
        "store_config": store_config,
        "code_provider": code_provider,
        "repo": str(repo) if repo else None,
        "log_provider": log_provider,
        "log_service": log_service,
        "output": output,
        "log_severity": log_severity,
        "log_dir": log_dir,
        "log_sink": log_sink,
        "evidence_severity": evidence_severity,
        "process_severity": process_severity,
        "evidence_persist": evidence_persist,
    }

    # If --save-config: persist the current CLI values and exit.
    if save_config:
        target = config_path or DEFAULT_CONFIG_PATH
        # AI provider lives in backends.ai, not the flat analyze keys.
        ai_extra: dict[str, object] = (
            {"backends": {"ai": {"provider": ai}}} if ai is not None else {}
        )
        save_analyze_config(cli_values, target, extra=ai_extra)
        console.print(f"[green]Config saved to:[/green] {target}")
        raise typer.Exit()

    # config.json first, explicit CLI flags atop. AnalyzeConfig is the single
    # source of truth for the keys; both sources feed it the same dict shape.
    file_config = load_analyze_config(config_path)
    overrides = collect_cli_overrides(ctx, cli_values)
    config = AnalyzeConfig.merge(file_config, overrides)

    # Validate the logging channels (covers both CLI flags and config.json values).
    _validate_log_options(config)

    # Three independent logging channels (the log-subsystem split, plan Part III),
    # each now sourced from its own config field:
    #   - application logging   -> configure_logging (diagnostics: stderr + file)
    #   - evidence stream       -> war-room left pane
    #   - investigation process -> war-room right pane (agent reasoning)
    app_severity = config.log_severity
    evidence_severity = config.evidence_severity
    process_severity = config.process_severity

    # Evidence persistence (opt-in, D5) writes the Evidence Stream after the run.
    # It needs a rendered stream, so it has no effect in --output quiet mode.
    # (--log-sink is handled by configure_logging, which warns + falls back for
    # the not-yet-implemented elk/fluent sinks.)
    evidence_dir = config.evidence_dir or _DEFAULT_EVIDENCE_DIR
    if config.evidence_persist and config.output == "quiet":
        logger.warning(
            "--evidence-persist has no effect with --output quiet (no Evidence "
            "Stream is rendered to persist)."
        )

    # Re-apply logging at the effective severity, sink, and log directory
    # (config.json may set any of them). This is where the diagnostic log starts
    # being written; elk/fluent sinks warn and fall back to file/stderr for now.
    configure_logging(
        app_severity,
        log_dir=config.log_dir,
        sink=config.log_sink,
        elk_url=config.log_elk_url,
        fluent_host=config.log_fluent_host,
        fluent_port=config.log_fluent_port,
    )

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
    # Settings() always reads from the default config path. When --config points
    # to a custom file, apply its backends.ai.provider so it takes effect.
    if config_path is not None:
        custom_ai_provider = file_config.get("backends", {}).get("ai", {}).get("provider")
        if custom_ai_provider:
            settings.backends.ai.provider = custom_ai_provider
    # --ai flag takes highest priority.
    if ai is not None:
        settings.backends.ai.provider = ai
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
        # No display - just run and store.
        report = asyncio.run(orch.run(source))
    else:
        # For json / json-full output, stream the live display to stderr so
        # stdout carries only the machine-readable payload.
        from aegis_swr.cli._formatters import make_console

        stream_con = make_console(stderr=(fmt in ("json", "json-full")))
        report = asyncio.run(
            stream_and_display(
                orch,
                source,
                stream_con,
                evidence_level=evidence_severity,
                process_level=process_severity,
                evidence_persist=config.evidence_persist,
                evidence_dir=evidence_dir,
            )
        )
        if report is None:
            typer.echo("Error: investigation ended without producing a report.", err=True)
            raise typer.Exit(code=1)

    # The full report is persisted as a result file by the storage backend. The
    # 'rich' and 'json' formats only surface where to find it; 'json-full' is
    # the one mode that also dumps the complete report body to stdout.
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
        # Machine-readable *locator* only - not the report body, which lives in
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
    elif fmt == "json-full":
        # The complete report body on stdout, in place of the locator.
        typer.echo(json_formatter(report))

    if report.hitl_request:
        typer.echo(
            f"\nHuman input required: {report.hitl_request.question}",
            err=True,
        )
        raise typer.Exit(code=1)


def _report_file_path(settings: object, incident_id: str) -> Optional[Path]:
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
    store: Annotated[str, typer.Option("--store", help="Source storage backend.")] = "filesystem",
    store_config: Annotated[
        Optional[str], typer.Option("--store-config", help="Source config value.")
    ] = None,
    to_store: Annotated[
        str, typer.Option("--to-store", help="Destination storage backend.")
    ] = "filesystem",
    to_config: Annotated[
        Optional[str], typer.Option("--to-config", help="Destination config value.")
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
    """Start the FastAPI API server. (Phase 8 - not yet implemented.)"""
    typer.echo(
        "API server not yet implemented - available in Phase 8.\n"
        f"Configured for {host}:{port} (reload={reload})."
    )


# ---------------------------------------------------------------------------
# aegis config show / set
# ---------------------------------------------------------------------------


@config_app.command("show")
def config_show():
    """Print resolved config.json + env overrides (secrets redacted)"""
    from aegis_swr.config.settings import Settings

    settings = Settings()
    typer.echo(json.dumps(settings.redacted_dump(), indent=2))


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Dotted key path, e.g. backends.ai.anthropic.model")],
    value: Annotated[str, typer.Argument(help="New value.")],
):
    """Set a single value in ~/.aegis-swr/config.json"""
    config_path = DEFAULT_CONFIG_PATH
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            loaded = {}
        data: dict[str, object] = loaded if isinstance(loaded, dict) else {}
    else:
        data = {}

    parts = key.split(".")
    node: dict[str, object] = data
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Set {key} = {value!r} in {config_path}")
