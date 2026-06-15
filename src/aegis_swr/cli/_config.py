"""Unified ``aegis analyze`` configuration: one schema, two sources.

Startup options can be supplied two ways, and both deserialize into the *same*
dict shape and the *same* class:

1. **JSON config file** - by default ``~/.local/state/.aegis-swr/config.json``
   (override with ``--config PATH``). Keys mirror the CLI option names exactly.
2. **CLI flags** - ``aegis analyze --ai openai …``.

When both are present the file is applied first and explicit CLI flags are
layered on top, so the precedence (low → high) is::

    dataclass defaults  <  config.json  <  CLI flags

:class:`AnalyzeConfig` is the **single source of truth** for the option keys,
their types, and their defaults. Neither the JSON loader, the CLI, nor the merge
keeps its own separate list of key names - they all derive from this one class.

The logging-related options are grouped, on disk, into four nested sections that
separate concerns a single ``log_*`` group used to conflate (plan Part III):

* ``ingest.log_source`` - reading the *investigated system's* logs (overrides
  ``backends.log``), distinct from Aegis's own logging;
* ``logging``  - Aegis's own application diagnostics (sink + severity + dir);
* ``evidence`` - the war-room Evidence Stream (left pane);
* ``process``  - the war-room Investigation Process pane (agent reasoning).

This is purely a config.json *layout* choice: the dataclass and the CLI still use
flat field names (``log_provider``, ``evidence_severity``, …), each 1:1 with a CLI
option, and the translation happens at the JSON boundary via dotted-path mapping
(:func:`AnalyzeConfig.from_dict` / :func:`load_analyze_config` flatten the sections
to flat keys; :func:`save_analyze_config` re-nests them).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

import typer
from loguru import logger

#: Default config-file location (``--config`` overrides it).  Imported from the
#: settings module so the CLI and the runtime :class:`Settings` always resolve
#: the *same* ``config.json`` - a past divergence here (``share/aegis`` vs
#: ``share/aegis-swr``) is what stopped the file from overriding the storage
#: defaults.  Re-exported so existing ``from _config import DEFAULT_CONFIG_PATH``
#: callers keep working.
from aegis_swr.config.settings import DEFAULT_CONFIG_PATH as DEFAULT_CONFIG_PATH

#: Top-level keys owned by the runtime :class:`~aegis_swr.config.settings.Settings`
#: schema. ``config.json`` is unified - it carries both the flat analyze options
#: *and* these nested sections - so they are expected here and ignored without a
#: warning (unlike genuine typos in analyze keys).
_RUNTIME_SECTION_KEYS: frozenset[str] = frozenset(
    {"core", "backends", "sandbox", "api", "agent_weights"}
)

#: Flat ``AnalyzeConfig`` field → dotted JSON path inside config.json. The
#: dataclass keeps the flat field names (each 1:1 with a CLI option); config.json
#: groups them into four nested sections separating concerns a single ``log_*``
#: group used to conflate (plan Part III). The names are deliberately *not* peers
#: of the runtime ``backends.log`` block (the log-ingestion backend).
#: :func:`_flatten_sections` / :func:`_nest_sections` translate at the JSON boundary.
_FIELD_TO_PATH: dict[str, str] = {
    # Log ingestion - reading the investigated system's logs (overrides backends.log).
    "log_provider": "ingest.log_source.provider",
    "log_service": "ingest.log_source.service",
    # Application logging - Aegis's own diagnostics.
    "log_severity": "logging.severity",
    "log_sink": "logging.sink",
    "log_dir": "logging.dir",
    "log_elk_url": "logging.elk_url",
    "log_fluent_host": "logging.fluent_host",
    "log_fluent_port": "logging.fluent_port",
    # Evidence stream - war-room left pane.
    "evidence_severity": "evidence.severity",
    "evidence_persist": "evidence.persist",
    "evidence_dir": "evidence.dir",
    # Investigation process - war-room right pane (agent reasoning).
    "process_severity": "process.severity",
}

#: Top-level section names consumed by :func:`_flatten_sections`, derived from the
#: path map (never hand-maintained). Popped during flattening so they are never
#: mistaken for unknown (typo) analyze keys.
_ANALYZE_SECTION_KEYS: frozenset[str] = frozenset(
    path.split(".", 1)[0] for path in _FIELD_TO_PATH.values()
)

#: Sentinel for "no value at this path" - distinct from a legitimate ``None``.
_MISSING = object()


def _dig(data: Mapping[str, Any], path: str) -> Any:
    """Return the value at a dotted *path* in *data*, or ``_MISSING`` if absent."""
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _bury(root: dict[str, Any], path: str, value: Any) -> None:
    """Set *value* at a dotted *path* in *root*, creating intermediate dicts."""
    parts = path.split(".")
    node = root
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _clamp_stream_level(value: object) -> str:
    """Coerce a severity to the war-room channels' ``INFO``/``TRACE`` vocabulary.

    Mirrors the old single-knob evidence behavior: ``DEBUG``/``TRACE`` surfaced
    detail (→ ``TRACE``); anything else stayed at the ``INFO`` summary.
    """
    return "TRACE" if str(value).upper() in {"DEBUG", "TRACE"} else "INFO"


def _migrate_legacy(data: Mapping[str, Any]) -> dict[str, Any]:
    """Upgrade a pre-split ``logging`` section to the new four-section layout.

    The earlier layout grouped *everything* under ``logging`` (``provider`` /
    ``service`` / ``severity`` / ``dir``), where the single ``severity`` drove the
    application log **and** both war-room panes. Migration (only when the matching
    new keys are absent, so new files are untouched):

    * ``logging.provider`` / ``logging.service`` → ``ingest.log_source.*``;
    * ``logging.severity`` additionally seeds ``evidence.severity`` /
      ``process.severity`` (clamped to ``INFO``/``TRACE``).

    Emits a single deprecation warning listing what was migrated. ``logging.dir``
    and ``logging.severity`` themselves still map to the (unchanged) ``logging``
    section, so they need no migration.
    """
    section = data.get("logging")
    if not isinstance(section, Mapping):
        return dict(data)

    migrated = dict(data)
    notes: list[str] = []
    has_ingest = "ingest" in migrated
    for short, field_name in (("provider", "log_provider"), ("service", "log_service")):
        if short in section and field_name not in migrated and not has_ingest:
            migrated[field_name] = section[short]
            notes.append(f"logging.{short} -> ingest.log_source.{short}")

    legacy_severity = section.get("severity")
    if legacy_severity is not None:
        for pane, field_name in (
            ("evidence", "evidence_severity"),
            ("process", "process_severity"),
        ):
            if pane not in migrated and field_name not in migrated:
                migrated[field_name] = _clamp_stream_level(legacy_severity)
                notes.append(f"{pane}.severity seeded from logging.severity")

    if notes:
        logger.warning(
            "Deprecated config layout migrated (" + "; ".join(notes) + "). Update "
            "config.json to the ingest/logging/evidence/process sections - see "
            "docs/configuration/config.md."
        )
    return migrated


def _flatten_sections(data: Mapping[str, Any]) -> dict[str, Any]:
    """Lift the nested analyze sections up to the flat ``AnalyzeConfig`` fields.

    config.json groups the logging-related options into nested sections
    (``ingest.log_source`` / ``logging`` / ``evidence`` / ``process``); the schema
    works in flat fields. A flat field already present at the top level wins over
    its nested counterpart, so a hand-edited or legacy file still loads. The
    consumed top-level sections are dropped from the result, so they are neither
    re-flattened nor flagged as unknown keys. A pre-split ``logging`` section is
    upgraded first (see :func:`_migrate_legacy`). Idempotent: a dict with no
    recognised section is returned unchanged.
    """
    flat = _migrate_legacy(data)
    for field_name, path in _FIELD_TO_PATH.items():
        if field_name in flat:
            continue  # an explicit flat key wins over the nested section
        value = _dig(flat, path)
        if value is not _MISSING:
            flat[field_name] = value
    for section in _ANALYZE_SECTION_KEYS:
        flat.pop(section, None)
    return flat


def _nest_sections(opts: Mapping[str, Any]) -> dict[str, Any]:
    """Group the flat analyze fields into their nested config.json sections.

    Inverse of :func:`_flatten_sections`, used when writing config.json. Fields
    that are not section-mapped pass through unchanged; a section (and any
    intermediate object) is created only when at least one of its fields is present.
    """
    nested: dict[str, Any] = {}
    for key, value in opts.items():
        path = _FIELD_TO_PATH.get(key)
        if path is None:
            nested[key] = value
        else:
            _bury(nested, path, value)
    return nested


@dataclass
class AnalyzeConfig:
    """Deserialized ``aegis analyze`` settings - shared by both config sources.

    Field names match the ``aegis analyze`` CLI option destinations one-to-one,
    so a config.json round-trips through the CLI without any second mapping table.
    The field names are flat; on disk the logging-related fields are grouped into
    the ``ingest``/``logging``/``evidence``/``process`` sections (see the module
    docstring), translated transparently by the (de)serialisers. Defaults here are
    the canonical defaults for the whole application.
    """

    dump: Optional[str] = None
    logs: list[str] = field(default_factory=list)
    shots: list[str] = field(default_factory=list)
    pcaps: list[str] = field(default_factory=list)
    sym: list[str] = field(default_factory=list)
    assume: Optional[str] = None
    engine: str = "auto"
    ai: str = "anthropic"
    store: str = "filesystem"
    store_config: Optional[str] = None
    code_provider: str = "none"
    repo: Optional[str] = None
    output: str = "rich"
    # Log ingestion (investigated system's logs) → ingest.log_source.*
    log_provider: str = "file"
    log_service: Optional[str] = None
    # Application logging (Aegis's own diagnostics) → logging.*
    log_severity: str = "INFO"
    log_dir: str = "~/.local/state/aegis-swr/logs"
    log_sink: str = "file"
    log_elk_url: Optional[str] = None
    log_fluent_host: Optional[str] = None
    log_fluent_port: Optional[int] = None
    # Evidence stream (war-room left pane) → evidence.*
    evidence_severity: str = "INFO"
    evidence_persist: bool = False
    evidence_dir: Optional[str] = None
    # Investigation process (war-room right pane) → process.*
    process_severity: str = "INFO"

    @classmethod
    def keys(cls) -> tuple[str, ...]:
        """Every setting key - the one authoritative list of names."""
        return tuple(f.name for f in fields(cls))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AnalyzeConfig:
        """Build from a raw mapping, ignoring unknown keys and ``None`` values.

        Nested analyze sections (``ingest``/``logging``/``evidence``/``process``)
        are flattened to their flat fields first. Unknown keys are warned about
        (typo protection) rather than raising, so a slightly stale config loads.
        """
        data = _flatten_sections(data)
        known = set(cls.keys())
        unknown = [key for key in data if key not in known and key not in _RUNTIME_SECTION_KEYS]
        if unknown:
            logger.warning(f"Ignoring unknown config keys: {sorted(unknown)}")
        return cls(**{k: v for k, v in data.items() if k in known and v is not None})

    @classmethod
    def merge(
        cls,
        file_config: Mapping[str, Any],
        cli_overrides: Mapping[str, Any],
    ) -> AnalyzeConfig:
        """Apply config.json first, then CLI overrides atop it.

        Only keys present (and non-``None``) in each source contribute, so a
        partial config.json and a single ``--flag`` compose cleanly over the
        dataclass defaults.
        """
        merged: dict[str, Any] = {}
        for source in (file_config, cli_overrides):
            flat = _flatten_sections(source)
            for key in cls.keys():
                value = flat.get(key)
                if value is not None:
                    merged[key] = value
        return cls.from_dict(merged)

    def as_dict(self) -> dict[str, Any]:
        """Serialise back to the shared dict shape (e.g. to save a config)."""
        return asdict(self)


#: Backwards-compatible alias - derived from the schema, never hand-maintained.
ANALYZE_CONFIG_KEYS: tuple[str, ...] = AnalyzeConfig.keys()


def load_analyze_config(path: Optional[Path] = None) -> dict[str, Any]:
    """Load raw option values from a JSON file.

    Returns an empty dict if the file is missing, unreadable, malformed, or not
    a JSON object - a bad config never aborts the run.
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
    # Flatten the nested analyze sections to flat fields so callers (and the
    # merge) see one uniform, flat dict shape.
    return _flatten_sections(data)


def save_analyze_config(opts: Mapping[str, Any], path: Optional[Path] = None):
    """Write *opts* (filtered to known keys) to the JSON config file."""
    target = path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    filtered = {key: opts[key] for key in AnalyzeConfig.keys() if key in opts}
    # Group the flat fields into their nested sections for the on-disk layout.
    nested = _nest_sections(filtered)
    target.write_text(json.dumps(nested, indent=2, default=str), encoding="utf-8")
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
