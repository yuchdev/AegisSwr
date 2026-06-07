"""Unified ``aegis analyze`` configuration: one schema, two sources.

Startup options can be supplied two ways, and both deserialize into the *same*
dict shape and the *same* class:

1. **JSON config file** — by default ``~/.local/share/aegis/config.json``
   (override with ``--config PATH``). Keys mirror the CLI option names exactly.
2. **CLI flags** — ``aegis analyze --ai openai …``.

When both are present the file is applied first and explicit CLI flags are
layered on top, so the precedence (low → high) is::

    dataclass defaults  <  config.json  <  CLI flags

:class:`AnalyzeConfig` is the **single source of truth** for the option keys,
their types, and their defaults. Neither the JSON loader, the CLI, nor the merge
keeps its own separate list of key names — they all derive from this one class.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping, Optional

import typer
from loguru import logger

#: Default config-file location (``--config`` overrides it).
DEFAULT_CONFIG_PATH: Path = Path("~/.local/share/aegis/config.json").expanduser()


@dataclass
class AnalyzeConfig:
    """Deserialized ``aegis analyze`` settings — shared by both config sources.

    Field names match the ``aegis analyze`` CLI option destinations one-to-one,
    so a config.json written with those keys round-trips through the CLI without
    any second mapping table. Defaults here are the canonical defaults for the
    whole application.
    """

    dump: Optional[str] = None
    logs: list[str] = field(default_factory=list)
    shots: list[str] = field(default_factory=list)
    pcaps: list[str] = field(default_factory=list)
    sym: Optional[str] = None
    assume: Optional[str] = None
    engine: str = "auto"
    ai: str = "anthropic"
    store: str = "filesystem"
    store_config: Optional[str] = None
    code_provider: str = "none"
    repo: Optional[str] = None
    log_provider: str = "file"
    log_service: Optional[str] = None
    output: str = "rich"
    severity: str = "WARNING"

    @classmethod
    def keys(cls) -> tuple[str, ...]:
        """Every setting key — the one authoritative list of names."""
        return tuple(f.name for f in fields(cls))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AnalyzeConfig":
        """Build from a raw mapping, ignoring unknown keys and ``None`` values.

        Unknown keys are warned about (typo protection) rather than raising, so a
        slightly stale config file still loads.
        """
        known = set(cls.keys())
        unknown = [key for key in data if key not in known]
        if unknown:
            logger.warning(f"Ignoring unknown config keys: {sorted(unknown)}")
        return cls(**{k: v for k, v in data.items() if k in known and v is not None})

    @classmethod
    def merge(
        cls,
        file_config: Mapping[str, Any],
        cli_overrides: Mapping[str, Any],
    ) -> "AnalyzeConfig":
        """Apply config.json first, then CLI overrides atop it.

        Only keys present (and non-``None``) in each source contribute, so a
        partial config.json and a single ``--flag`` compose cleanly over the
        dataclass defaults.
        """
        merged: dict[str, Any] = {}
        for source in (file_config, cli_overrides):
            for key in cls.keys():
                value = source.get(key)
                if value is not None:
                    merged[key] = value
        return cls.from_dict(merged)

    def as_dict(self) -> dict[str, Any]:
        """Serialise back to the shared dict shape (e.g. to save a config)."""
        return asdict(self)


#: Backwards-compatible alias — derived from the schema, never hand-maintained.
ANALYZE_CONFIG_KEYS: tuple[str, ...] = AnalyzeConfig.keys()


def load_analyze_config(path: Optional[Path] = None) -> dict[str, Any]:
    """Load raw option values from a JSON file.

    Returns an empty dict if the file is missing, unreadable, malformed, or not
    a JSON object — a bad config never aborts the run.
    """
    target = path or DEFAULT_CONFIG_PATH
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not read config file {target}: {exc}")
        return {}
    if not isinstance(data, dict):
        logger.warning(f"Config file {target} is not a JSON object; ignoring.")
        return {}
    return data


def save_analyze_config(opts: Mapping[str, Any], path: Optional[Path] = None):
    """Write *opts* (filtered to known keys) to the JSON config file."""
    target = path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    filtered = {key: opts[key] for key in AnalyzeConfig.keys() if key in opts}
    target.write_text(json.dumps(filtered, indent=2, default=str), encoding="utf-8")
    logger.info(f"Saved analyze config to {target}")


def collect_cli_overrides(
    ctx: typer.Context,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep only the option values the user passed *explicitly* on the CLI.

    Typer always supplies a value for every option (its default), so we consult
    the Click parameter source and keep only flags whose source is the command
    line. Without this, Typer's defaults would clobber the config.json values.

    Compared by ``source.name == "COMMANDLINE"`` (a string) rather than by
    identity, since Typer bundles its own ``ParameterSource`` enum with values
    distinct from ``click.core``.
    """
    overrides: dict[str, Any] = {}
    for key, value in values.items():
        source = ctx.get_parameter_source(key)
        if source is not None and source.name == "COMMANDLINE":
            overrides[key] = value
    return overrides
