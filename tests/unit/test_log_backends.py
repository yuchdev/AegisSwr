"""Unit tests for the log backends — no network, no Fluent service required."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aegis_swr.backends.log import FileLogAdapter, FluentAdapter, create_log_backend
from aegis_swr.config.settings import LogBackendSettings

_START = datetime(2026, 5, 30, 13, 59, 30, tzinfo=timezone.utc)
_END = datetime(2026, 5, 30, 14, 0, 30, tzinfo=timezone.utc)


def _write_log(root: Path, name: str, *lines: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def file_adapter(tmp_path: Path) -> FileLogAdapter:
    return FileLogAdapter(LogBackendSettings(provider="file", file_root=str(tmp_path)))


# ---------------------------------------------------------------------------
# FileLogAdapter
# ---------------------------------------------------------------------------


async def test_file_window_filters_by_time(
    file_adapter: FileLogAdapter, tmp_path: Path
) -> None:
    _write_log(
        tmp_path,
        "auth-api.log",
        "2026-05-30T14:00:01 ERROR db write failed",   # inside window
        "2026-05-30T14:05:00 ERROR much later",        # outside window
    )
    lines = await file_adapter.query_window("auth-api", _START, _END)
    assert any("db write failed" in ln for ln in lines)
    assert all("much later" not in ln for ln in lines)


async def test_file_severity_filter(file_adapter: FileLogAdapter, tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        "auth-api.log",
        "2026-05-30T14:00:01 ERROR boom",
        "2026-05-30T14:00:02 INFO routine heartbeat",
    )
    lines = await file_adapter.query_window(
        "auth-api", _START, _END, severity_levels=["ERROR"]
    )
    assert any("boom" in ln for ln in lines)
    assert all("heartbeat" not in ln for ln in lines)


async def test_file_no_severity_returns_all_windowed(
    file_adapter: FileLogAdapter, tmp_path: Path
) -> None:
    _write_log(
        tmp_path,
        "auth-api.log",
        "2026-05-30T14:00:01 ERROR boom",
        "2026-05-30T14:00:02 INFO heartbeat",
    )
    lines = await file_adapter.query_window("auth-api", _START, _END)
    assert len(lines) == 2


async def test_file_glob_matches_txt_and_suffix(
    file_adapter: FileLogAdapter, tmp_path: Path
) -> None:
    _write_log(tmp_path, "auth-api-2026.txt", "2026-05-30T14:00:05 WARNING latency high")
    lines = await file_adapter.query_window("auth-api", _START, _END)
    assert any("latency high" in ln for ln in lines)


async def test_file_no_file_root_returns_empty() -> None:
    adapter = FileLogAdapter(LogBackendSettings(provider="file", file_root=None))
    assert await adapter.query_window("svc", _START, _END) == []


async def test_file_unknown_service_returns_empty(
    file_adapter: FileLogAdapter, tmp_path: Path
) -> None:
    _write_log(tmp_path, "other.log", "2026-05-30T14:00:01 ERROR x")
    assert await file_adapter.query_window("auth-api", _START, _END) == []


async def test_file_service_traversal_blocked(
    file_adapter: FileLogAdapter, tmp_path: Path
) -> None:
    assert await file_adapter.query_window("../../etc/passwd", _START, _END) == []


# ---------------------------------------------------------------------------
# FluentAdapter — stub
# ---------------------------------------------------------------------------


async def test_fluent_query_window_raises_notimplemented() -> None:
    adapter = FluentAdapter(LogBackendSettings(provider="fluent", fluent_host="localhost"))
    with pytest.raises(NotImplementedError, match="stub"):
        await adapter.query_window("svc", _START, _END)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_file() -> None:
    assert isinstance(create_log_backend(LogBackendSettings(provider="file")), FileLogAdapter)


def test_factory_fluent() -> None:
    assert isinstance(create_log_backend(LogBackendSettings(provider="fluent")), FluentAdapter)


def test_factory_elk_deferred() -> None:
    settings = LogBackendSettings()
    object.__setattr__(settings, "provider", "elk")
    with pytest.raises(NotImplementedError, match="deferred"):
        create_log_backend(settings)


def test_factory_unknown_provider_raises() -> None:
    settings = LogBackendSettings()
    object.__setattr__(settings, "provider", "splunk")
    with pytest.raises(ValueError, match="Unknown log provider"):
        create_log_backend(settings)
