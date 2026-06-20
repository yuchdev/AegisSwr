"""Unit tests for CLI logging configuration.

Focus: the incident/resolution JSON that the AI SDKs and httpx log as HTTP
request/response bodies must never reach the console at Aegis's INFO level.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from loguru import logger

from aegis_swr.cli.aegis_logging import (
    LOG_FILENAME,
    NOISY_LIBRARY_LOGGERS,
    configure_logging,
)


@pytest.fixture(autouse=True)
def _restore_logger_levels():
    """Snapshot and restore the third-party logger levels around each test"""
    saved = {name: logging.getLogger(name).level for name in NOISY_LIBRARY_LOGGERS}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


@pytest.mark.parametrize("severity", ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"])
def test_noisy_loggers_clamped_to_warning(severity: str):
    configure_logging(severity)
    for name in NOISY_LIBRARY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING, name


def test_http_body_record_suppressed_at_info():
    # The exact shape of what leaked before: an httpx/SDK INFO record carrying
    # the request body JSON (incident brief + agent resolution).
    configure_logging("INFO")
    httpx_logger = logging.getLogger("httpx")
    body = '{"incident_brief": {"root_cause": "UAF"}, "resolution": "patch"}'
    # A WARNING-clamped logger does not emit INFO records.
    assert not httpx_logger.isEnabledFor(logging.INFO)
    record = httpx_logger.makeRecord("httpx", logging.INFO, __file__, 0, body, None, None)
    assert not httpx_logger.isEnabledFor(record.levelno)


def test_anthropic_child_logger_inherits_clamp():
    configure_logging("INFO")
    # SDK internals log under child loggers (e.g. anthropic._base_client);
    # they inherit the WARNING clamp from the parent.
    child = logging.getLogger("anthropic._base_client")
    assert not child.isEnabledFor(logging.DEBUG)
    assert not child.isEnabledFor(logging.INFO)


def test_log_dir_writes_classic_log_file(tmp_path: Path):
    log_dir = tmp_path / "logs"
    try:
        configure_logging("INFO", log_dir=str(log_dir))
        logger.info("investigation started")
    finally:
        # Detach the file sink so the file handle is released before assertions.
        configure_logging("INFO")

    log_file = log_dir / LOG_FILENAME
    assert log_file.exists()
    assert "investigation started" in log_file.read_text(encoding="utf-8")


def test_log_dir_redacts_secrets_in_file(tmp_path: Path):
    log_dir = tmp_path / "logs"
    try:
        configure_logging("INFO", log_dir=str(log_dir))
        logger.info("using OPENAI_API_KEY=sk-secret-value-1234567890")
    finally:
        configure_logging("INFO")

    contents = (log_dir / LOG_FILENAME).read_text(encoding="utf-8")
    assert "sk-secret-value-1234567890" not in contents
    assert "[REDACTED]" in contents


def test_missing_log_dir_does_not_break_stderr_logging(tmp_path: Path, monkeypatch):
    # If the log directory can't be created, stderr logging must still work.
    import aegis_swr.cli.aegis_logging as mod

    def _boom(*_a, **_k):
        raise OSError("no permission")

    monkeypatch.setattr(mod.Path, "mkdir", _boom)
    # Should not raise.
    configure_logging("INFO", log_dir=str(tmp_path / "nope"))
    configure_logging("INFO")  # reset


# ---------------------------------------------------------------------------
# Application log sinks (the log-subsystem split, plan Part III - Phase E)
# ---------------------------------------------------------------------------


def test_file_sink_emits_no_warning(tmp_path: Path):
    log_dir = tmp_path / "logs"
    try:
        configure_logging("INFO", log_dir=str(log_dir), sink="file")
        logger.info("file sink line")
    finally:
        configure_logging("INFO")
    contents = (log_dir / LOG_FILENAME).read_text(encoding="utf-8")
    assert "file sink line" in contents
    assert "not yet implemented" not in contents
    assert "Unknown application log sink" not in contents


@pytest.mark.parametrize("sink", ["elk", "fluent"])
def test_unimplemented_sink_warns_and_falls_back_to_file(tmp_path: Path, sink: str):
    log_dir = tmp_path / "logs"
    try:
        configure_logging("INFO", log_dir=str(log_dir), sink=sink)
        logger.info("after fallback")
    finally:
        configure_logging("INFO")
    contents = (log_dir / LOG_FILENAME).read_text(encoding="utf-8")
    # The stub sink warned …
    assert f"'{sink}' is not yet implemented" in contents
    # … and the file sink is active as the fallback (logging is never lost).
    assert "after fallback" in contents


def test_unknown_sink_warns_and_falls_back_to_file(tmp_path: Path):
    log_dir = tmp_path / "logs"
    try:
        configure_logging("INFO", log_dir=str(log_dir), sink="kafka")
        logger.info("after fallback")
    finally:
        configure_logging("INFO")
    contents = (log_dir / LOG_FILENAME).read_text(encoding="utf-8")
    assert "Unknown application log sink 'kafka'" in contents
    assert "after fallback" in contents


def test_sink_registration_seams_return_false():
    # Until the real emitters land, the seams report "not handled" so the caller
    # falls back to the file/stderr sinks.
    from aegis_swr.cli.aegis_logging import _register_elk_sink, _register_fluent_sink

    assert _register_elk_sink("INFO", elk_url="http://elk:9200") is False
    assert _register_fluent_sink("INFO", fluent_host="fluentd", fluent_port=24224) is False


def test_file_sink_is_delayed_until_first_record(tmp_path: Path):
    # delay=True: the directory is created, but the log file itself is not written
    # until something is actually logged - so a quiet bootstrap leaves no empty file.
    log_dir = tmp_path / "logs"
    try:
        configure_logging("INFO", log_dir=str(log_dir))
        assert not (log_dir / LOG_FILENAME).exists()  # nothing logged yet
        logger.warning("now it exists")
    finally:
        configure_logging("INFO")
    assert (log_dir / LOG_FILENAME).exists()
    assert "now it exists" in (log_dir / LOG_FILENAME).read_text(encoding="utf-8")
