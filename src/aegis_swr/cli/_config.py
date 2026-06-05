"""CLI JSON config file: load, save, and merge with explicit CLI flags.

The JSON config file mirrors the ``aegis analyze`` option names so users can
persist their preferred settings without repeating flags on every invocation.
The merge rule is simple: an explicit CLI flag always wins over the file value.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from loguru import logger
import typer

DEFAULT_CONFIG_PATH: Path = Path("~/.aegis-swr/analyze.json").expanduser()

ANALYZE_CONFIG_KEYS: tuple[str, ...] = (
    "dump",
    "logs",
    "shots",
    "pcaps",
    "sym",
    "assume",
    "engine",
    "ai",
    "store",
    "store_config",
    "code_provider",
    "repo",
    "log_provider",
    "log_service",
    "output",
    "severity",
)


def load_analyze_config(path: Optional[Path] = None) -> dict[str, Any]:
    """Load analyze options from a JSON file.

    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    target = path or DEFAULT_CONFIG_PATH
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not read config file {target}: {exc}")
        return {}


def save_analyze_config(
    opts: dict[str, Any],
    path: Optional[Path] = None,
):
    """Write *opts* (filtered to known keys) to the JSON config file"""
    target = path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    filtered = {k: opts[k] for k in ANALYZE_CONFIG_KEYS if k in opts}
    target.write_text(json.dumps(filtered, indent=2, default=str), encoding="utf-8")
    logger.info(f"Saved analyze config to {target}")


def merge_options(
    config: dict[str, Any],
    ctx: typer.Context,
    **cli_values: Any,
) -> dict[str, Any]:
    """Return effective option values: CLI flag > JSON config > hardcoded default.

    ``ctx.get_parameter_source(name)`` is ``ParameterSource.COMMAND_LINE`` when
    the user explicitly passed a flag; any other source means the value came from
    the Typer default.
    """
    # Typer 0.26 bundles its own ParameterSource in typer._click.core with
    # different enum values from click.core.ParameterSource. Compare by .name
    # (a string) rather than by identity so the check is version-agnostic.
    merged: dict[str, Any] = {}
    for key, cli_val in cli_values.items():
        source = ctx.get_parameter_source(key)
        if source is not None and source.name == "COMMANDLINE":
            merged[key] = cli_val
        elif key in config and config[key] is not None:
            merged[key] = config[key]
        else:
            merged[key] = cli_val
    return merged
