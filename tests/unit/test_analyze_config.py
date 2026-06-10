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
    assert ANALYZE_CONFIG_KEYS == keys


def test_cli_options_match_schema_keys_exactly():
    """CLI and config.json must not maintain separate key lists.

    Every ``aegis analyze`` option (besides the CLI-only ``--config`` and
    ``--save-config`` meta flags) must correspond to an ``AnalyzeConfig`` field,
    and vice versa - guarding against duplicated / drifting setting names.
    """
    from aegis_swr.cli.commands import analyze

    cli_params = set(inspect.signature(analyze).parameters)
    cli_params -= {"ctx", "config_path", "save_config"}
    assert cli_params == set(AnalyzeConfig.keys())


# ---------------------------------------------------------------------------
# Deserialization from the JSON fixtures
# ---------------------------------------------------------------------------


def test_from_dict_reads_full_config_01():
    cfg = AnalyzeConfig.from_dict(_asset("test_config-01.json"))
    assert cfg.dump == "C:/dumps/CrashUi.dmp"
    assert cfg.sym == "C:/symbols"
    assert cfg.engine == "cdb"
    assert cfg.ai == "openai"
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
    assert cfg.ai == "anthropic"
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
    assert cfg.ai == "openai"
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
    assert data["ai"] == "openai"
    assert data["engine"] == "cdb"


def test_load_analyze_config_rejects_non_object_json(tmp_path: Path):
    bad = tmp_path / "list.json"
    bad.write_text("[1, 2, 3]")
    assert load_analyze_config(bad) == {}


# ---------------------------------------------------------------------------
# Merge precedence: defaults < config.json < CLI
# ---------------------------------------------------------------------------


def test_merge_empty_sources_yields_defaults():
    cfg = AnalyzeConfig.merge({}, {})
    assert cfg == AnalyzeConfig()


def test_merge_file_overrides_defaults():
    cfg = AnalyzeConfig.merge({"engine": "cdb", "ai": "openai"}, {})
    assert cfg.engine == "cdb"
    assert cfg.ai == "openai"
    assert cfg.store == "filesystem"  # untouched default


def test_merge_cli_overrides_file():
    file_config = _asset("test_config-01.json")  # ai=openai, engine=cdb
    cfg = AnalyzeConfig.merge(file_config, {"ai": "anthropic"})
    # CLI wins for ai …
    assert cfg.ai == "anthropic"
    # … but the rest of config.json is preserved.
    assert cfg.engine == "cdb"
    assert cfg.store == "sqlite"
    assert cfg.log_severity == "DEBUG"


def test_merge_ignores_none_cli_values():
    # Values that were not explicitly set on the CLI (None) must not clobber
    # config.json - only real overrides count.
    cfg = AnalyzeConfig.merge({"ai": "openai"}, {"ai": None, "engine": "windbg_js"})
    assert cfg.ai == "openai"
    assert cfg.engine == "windbg_js"
