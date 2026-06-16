"""Unit tests for the unified analyze configuration (config.json + CLI).

Covers the single-source-of-truth schema (:class:`AnalyzeConfig`), JSON
deserialization from the ``test_config-NN.json`` fixtures, and the
``config.json`` < CLI merge precedence.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from loguru import logger

from aegis_swr.cli._config import (
    ANALYZE_CONFIG_KEYS,
    DEFAULT_CONFIG_PATH,
    AnalyzeConfig,
    load_analyze_config,
    save_analyze_config,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _asset(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Single source of truth
# ---------------------------------------------------------------------------


def test_default_path_is_canonical_config_location():
    # The config file lives under ~/.local/state/.aegis-swr/config.json, and the
    # CLI and runtime Settings must resolve the *same* file.
    from aegis_swr.config.settings import CONFIG_JSON

    normalized = str(DEFAULT_CONFIG_PATH).replace("\\", "/")
    assert normalized.endswith(".local/state/.aegis-swr/config.json")
    assert DEFAULT_CONFIG_PATH == CONFIG_JSON


def test_keys_have_no_duplicates():
    keys = AnalyzeConfig.keys()
    assert len(keys) == len(set(keys))
    # The public alias is derived from the schema, not hand-maintained.
    assert keys == ANALYZE_CONFIG_KEYS


#: Schema fields that are intentionally **config-file-only** - no CLI flag. These
#: are connection details and the evidence-persistence directory (mirroring
#: ``backends.storage.database_url``, which is also config-only). Every *other*
#: field maps 1:1 to a CLI option.
_CONFIG_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "log_elk_url",
        "log_fluent_host",
        "log_fluent_port",
        "evidence_dir",
    }
)


def test_cli_options_have_backing_schema_keys():
    """CLI and config.json must not maintain separate key lists.

    Every ``aegis analyze`` option (besides meta flags and Settings-level
    overrides) must correspond to an ``AnalyzeConfig`` field - no orphan flags.
    Conversely every field has a CLI flag *except* the explicit config-file-only
    set (connection details / evidence-persistence dir).

    ``ai`` is intentionally excluded: it is a CLI-only override for
    ``settings.backends.ai.provider`` and is not persisted as a flat analyze key.
    """
    from aegis_swr.cli.commands import analyze

    cli_params = set(inspect.signature(analyze).parameters)
    # Exclude meta flags and Settings-level overrides that bypass AnalyzeConfig.
    cli_params -= {"ctx", "config_path", "save_config", "ai"}
    schema_keys = set(AnalyzeConfig.keys())

    # No CLI option may exist without a backing schema field.
    assert cli_params <= schema_keys
    # The only fields without a flag are the intentional config-file-only ones.
    assert schema_keys - cli_params == _CONFIG_ONLY_FIELDS


# ---------------------------------------------------------------------------
# Deserialization from the JSON fixtures
# ---------------------------------------------------------------------------


def test_from_dict_reads_full_config_01():
    cfg = AnalyzeConfig.from_dict(_asset("test_config-01.json"))
    assert cfg.dump == "C:/dumps/CrashUi.dmp"
    assert cfg.sym == "C:/symbols"
    assert cfg.engine == "cdb"
    assert cfg.store == "sqlite"
    assert cfg.store_config == "C:/data/reports.db"
    assert cfg.code_provider == "git"
    assert cfg.repo == "C:/src/imagescope"
    assert cfg.log_service == "render-svc"
    assert cfg.output == "json"
    assert cfg.log_severity == "DEBUG"
    # Unspecified list fields fall back to their (empty) defaults.
    assert cfg.logs == []
    assert cfg.shots == []


def test_from_dict_partial_config_02_uses_defaults():
    cfg = AnalyzeConfig.from_dict(_asset("test_config-02.json"))
    # Provided values.
    assert cfg.logs == ["C:/logs/app.log", "C:/logs/render.log"]
    assert cfg.log_severity == "INFO"
    # Everything else stays at the schema defaults.
    assert cfg.dump is None
    assert cfg.engine == "auto"
    assert cfg.store == "filesystem"
    assert cfg.output == "rich"


def test_from_dict_config_03_ignores_unknown_keys_with_warning():
    data = _asset("test_config-03.json")  # contains "verbosity" and "engien" typos
    captured: list[str] = []
    sink_id = logger.add(lambda m: captured.append(str(m)), level="WARNING")
    try:
        cfg = AnalyzeConfig.from_dict(data)
    finally:
        logger.remove(sink_id)

    # Known keys are applied …
    assert cfg.store == "filesystem"
    assert cfg.store_config == "C:/data/reports"
    # … the typo'd field did not silently become a real setting.
    assert cfg.engine == "auto"
    # … and the user is warned about the unknown keys.
    warning = " ".join(captured)
    assert "verbosity" in warning
    assert "engien" in warning


def test_load_analyze_config_reads_fixture_as_dict():
    data = load_analyze_config(FIXTURES / "test_config-01.json")
    assert data["engine"] == "cdb"


def test_load_analyze_config_rejects_non_object_json(tmp_path: Path):
    bad = tmp_path / "list.json"
    bad.write_text("[1, 2, 3]")
    assert load_analyze_config(bad) == {}


# ---------------------------------------------------------------------------
# Nested sections (ingest.log_source / logging / evidence / process) <-> flat fields
# ---------------------------------------------------------------------------


def _full_sections() -> dict:
    """A config carrying every section the log-subsystem split owns."""
    return {
        "ingest": {"log_source": {"provider": "fluent", "service": "auth-api"}},
        "logging": {
            "severity": "DEBUG",
            "sink": "elk",
            "dir": "/var/log/aegis",
            "elk_url": "http://elk:9200",
            "fluent_host": "fluentd",
            "fluent_port": 24224,
        },
        "evidence": {"severity": "TRACE", "persist": True, "dir": "/var/log/evidence"},
        "process": {"severity": "TRACE"},
    }


def test_from_dict_flattens_all_nested_sections():
    """Every nested section maps onto its flat ``AnalyzeConfig`` field."""
    cfg = AnalyzeConfig.from_dict(_full_sections())
    # ingest.log_source.*
    assert cfg.log_provider == "fluent"
    assert cfg.log_service == "auth-api"
    # logging.*
    assert cfg.log_severity == "DEBUG"
    assert cfg.log_sink == "elk"
    assert cfg.log_dir == "/var/log/aegis"
    assert cfg.log_elk_url == "http://elk:9200"
    assert cfg.log_fluent_host == "fluentd"
    assert cfg.log_fluent_port == 24224
    # evidence.*
    assert cfg.evidence_severity == "TRACE"
    assert cfg.evidence_persist is True
    assert cfg.evidence_dir == "/var/log/evidence"
    # process.*
    assert cfg.process_severity == "TRACE"


def test_from_dict_partial_sections_keep_defaults():
    cfg = AnalyzeConfig.from_dict({"evidence": {"severity": "TRACE"}})
    assert cfg.evidence_severity == "TRACE"
    # Unspecified fields fall back to their schema defaults.
    assert cfg.evidence_persist is False
    assert cfg.process_severity == "INFO"
    assert cfg.log_sink == "file"
    assert cfg.log_provider == "file"


def test_load_analyze_config_flattens_sections(tmp_path: Path):
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "ingest": {"log_source": {"provider": "fluent"}},
                "process": {"severity": "TRACE"},
            }
        )
    )
    data = load_analyze_config(path)
    # Nested sections are lifted to flat keys; the section names are consumed.
    assert data["log_provider"] == "fluent"
    assert data["process_severity"] == "TRACE"
    for section in ("ingest", "logging", "evidence", "process"):
        assert section not in data


def test_save_analyze_config_nests_all_sections(tmp_path: Path):
    path = tmp_path / "cfg.json"
    save_analyze_config(
        {
            "log_provider": "fluent",
            "log_service": "auth-api",
            "log_severity": "DEBUG",
            "log_dir": "/var/log/aegis",
            "log_sink": "fluent",
            "evidence_severity": "TRACE",
            "evidence_persist": True,
            "process_severity": "TRACE",
        },
        path,
    )
    raw = json.loads(path.read_text())
    # Each flat field is grouped under its dotted section path …
    assert raw["ingest"]["log_source"] == {"provider": "fluent", "service": "auth-api"}
    assert raw["logging"] == {"severity": "DEBUG", "dir": "/var/log/aegis", "sink": "fluent"}
    assert raw["evidence"] == {"severity": "TRACE", "persist": True}
    assert raw["process"] == {"severity": "TRACE"}
    # … no flat key leaks to the top level …
    assert "log_provider" not in raw
    assert "evidence_severity" not in raw
    # … and ai provider is not part of the analyze config.
    assert "ai" not in raw


def test_sections_round_trip_through_save_and_load(tmp_path: Path):
    path = tmp_path / "cfg.json"
    opts = {
        "log_provider": "fluent",
        "log_service": "auth-api",
        "log_severity": "TRACE",
        "log_dir": "/logs",
        "log_sink": "elk",
        "log_elk_url": "http://elk:9200",
        "evidence_severity": "TRACE",
        "evidence_persist": True,
        "evidence_dir": "/ev",
        "process_severity": "TRACE",
    }
    save_analyze_config(opts, path)
    cfg = AnalyzeConfig.from_dict(load_analyze_config(path))
    for key, value in opts.items():
        assert getattr(cfg, key) == value


def test_flat_key_overrides_nested_section():
    """A legacy top-level flat key wins over the nested section."""
    cfg = AnalyzeConfig.from_dict(
        {
            "log_severity": "ERROR",
            "logging": {"severity": "INFO"},
            "log_provider": "fluent",
            "ingest": {"log_source": {"provider": "file"}},
        }
    )
    assert cfg.log_severity == "ERROR"
    assert cfg.log_provider == "fluent"


# ---------------------------------------------------------------------------
# Legacy (pre-split) config migration (Phase J)
# ---------------------------------------------------------------------------


def _capture_warnings():
    captured: list[str] = []
    sink_id = logger.add(lambda m: captured.append(str(m)), level="WARNING")
    return captured, sink_id


def test_legacy_conflated_logging_section_is_migrated():
    """The pre-split ``logging`` section upgrades to the four-section layout.

    ``logging.provider``/``service`` move to ``ingest.log_source``; the conflated
    ``logging.severity`` seeds the war-room panes (clamped to INFO/TRACE) while
    still driving the application log. A deprecation warning is emitted.
    """
    captured, sink_id = _capture_warnings()
    try:
        cfg = AnalyzeConfig.from_dict(
            {"logging": {"provider": "fluent", "service": "svc", "severity": "DEBUG"}}
        )
    finally:
        logger.remove(sink_id)

    # provider/service migrated out of logging.* …
    assert cfg.log_provider == "fluent"
    assert cfg.log_service == "svc"
    # … logging.severity still drives the application log …
    assert cfg.log_severity == "DEBUG"
    # … and seeds the war-room panes, clamped to the INFO/TRACE vocabulary.
    assert cfg.evidence_severity == "TRACE"
    assert cfg.process_severity == "TRACE"
    assert any("Deprecated config layout migrated" in m for m in captured)


def test_legacy_severity_clamps_non_stream_levels_to_info():
    cfg = AnalyzeConfig.from_dict({"logging": {"severity": "WARNING"}})
    assert cfg.log_severity == "WARNING"  # application channel keeps it verbatim
    assert cfg.evidence_severity == "INFO"  # WARNING is not a stream level → INFO
    assert cfg.process_severity == "INFO"


def test_new_sections_suppress_legacy_migration():
    """When the new sections are present, the legacy `logging` keys do not override."""
    captured, sink_id = _capture_warnings()
    try:
        cfg = AnalyzeConfig.from_dict(
            {
                "logging": {"provider": "fluent", "severity": "DEBUG"},
                "ingest": {"log_source": {"provider": "file"}},
                "evidence": {"severity": "INFO"},
                "process": {"severity": "INFO"},
            }
        )
    finally:
        logger.remove(sink_id)

    assert cfg.log_provider == "file"  # ingest.log_source wins, no migration
    assert cfg.evidence_severity == "INFO"
    assert cfg.process_severity == "INFO"
    assert not any("Deprecated config layout migrated" in m for m in captured)


# ---------------------------------------------------------------------------
# Merge precedence: defaults < config.json < CLI
# ---------------------------------------------------------------------------


def test_merge_empty_sources_yields_defaults():
    cfg = AnalyzeConfig.merge({}, {})
    assert cfg == AnalyzeConfig()


def test_merge_file_overrides_defaults():
    cfg = AnalyzeConfig.merge({"engine": "cdb"}, {})
    assert cfg.engine == "cdb"
    assert cfg.store == "filesystem"  # untouched default


def test_merge_cli_overrides_file():
    file_config = _asset("test_config-01.json")  # engine=cdb, store=sqlite
    cfg = AnalyzeConfig.merge(file_config, {"engine": "windbg_js"})
    # CLI wins for engine …
    assert cfg.engine == "windbg_js"
    # … but the rest of config.json is preserved.
    assert cfg.store == "sqlite"
    assert cfg.log_severity == "DEBUG"


def test_merge_ignores_none_cli_values():
    # Values that were not explicitly set on the CLI (None) must not clobber
    # config.json - only real overrides count.
    cfg = AnalyzeConfig.merge({"engine": "cdb"}, {"engine": None, "store": "sqlite"})
    assert cfg.engine == "cdb"
    assert cfg.store == "sqlite"
