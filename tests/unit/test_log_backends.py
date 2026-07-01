"""Unit tests for the log backends - no network, no Fluent service required"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aegis_swr.backends.log import FileLogAdapter, FluentAdapter, create_log_backend
from aegis_swr.config.settings import LogBackendSettings

_START = datetime(2026, 5, 30, 13, 59, 30, tzinfo=timezone.utc)
_END = datetime(2026, 5, 30, 14, 0, 30, tzinfo=timezone.utc)


def _write_log(root: Path, name: str, *lines: str):
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
):
    """
    [Unit] log backends: verifies file window filters by time.

    Scenario:
        Given test inputs and fixtures for file window filters by time
        When test_file_window_filters_by_time executes the target flow
        Then the expected outcome for file window filters by time is confirmed.

    Boundaries:
        - Focus: file window filters by time
        - Fixtures/params: file_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file window filters by time
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    _write_log(
        tmp_path,
        "auth-api.log",
        "2026-05-30T14:00:01 ERROR db write failed",   # inside window
        "2026-05-30T14:05:00 ERROR much later",        # outside window
    )
    lines = await file_adapter.query_window("auth-api", _START, _END)
    assert any("db write failed" in ln for ln in lines)
    assert all("much later" not in ln for ln in lines)


async def test_file_severity_filter(file_adapter: FileLogAdapter, tmp_path: Path):
    """
    [Unit] log backends: verifies file severity filter.

    Scenario:
        Given test inputs and fixtures for file severity filter
        When test_file_severity_filter executes the target flow
        Then the expected outcome for file severity filter is confirmed.

    Boundaries:
        - Focus: file severity filter
        - Fixtures/params: file_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file severity filter
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
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
):
    """
    [Unit] log backends: verifies file no severity returns all windowed.

    Scenario:
        Given test inputs and fixtures for file no severity returns all windowed
        When test_file_no_severity_returns_all_windowed executes the target flow
        Then the expected outcome for file no severity returns all windowed is confirmed.

    Boundaries:
        - Focus: file no severity returns all windowed
        - Fixtures/params: file_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file no severity returns all windowed
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
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
):
    """
    [Unit] log backends: verifies file glob matches txt and suffix.

    Scenario:
        Given test inputs and fixtures for file glob matches txt and suffix
        When test_file_glob_matches_txt_and_suffix executes the target flow
        Then the expected outcome for file glob matches txt and suffix is confirmed.

    Boundaries:
        - Focus: file glob matches txt and suffix
        - Fixtures/params: file_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file glob matches txt and suffix
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    _write_log(tmp_path, "auth-api-2026.txt", "2026-05-30T14:00:05 WARNING latency high")
    lines = await file_adapter.query_window("auth-api", _START, _END)
    assert any("latency high" in ln for ln in lines)


async def test_file_no_file_root_returns_empty():
    """
    [Unit] log backends: verifies file no file root returns empty.

    Scenario:
        Given test inputs and fixtures for file no file root returns empty
        When test_file_no_file_root_returns_empty executes the target flow
        Then the expected outcome for file no file root returns empty is confirmed.

    Boundaries:
        - Focus: file no file root returns empty
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file no file root returns empty
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    adapter = FileLogAdapter(LogBackendSettings(provider="file", file_root=None))
    assert await adapter.query_window("svc", _START, _END) == []


async def test_file_unknown_service_returns_empty(
    file_adapter: FileLogAdapter, tmp_path: Path
):
    """
    [Unit] log backends: verifies file unknown service returns empty.

    Scenario:
        Given test inputs and fixtures for file unknown service returns empty
        When test_file_unknown_service_returns_empty executes the target flow
        Then the expected outcome for file unknown service returns empty is confirmed.

    Boundaries:
        - Focus: file unknown service returns empty
        - Fixtures/params: file_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file unknown service returns empty
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    _write_log(tmp_path, "other.log", "2026-05-30T14:00:01 ERROR x")
    assert await file_adapter.query_window("auth-api", _START, _END) == []


async def test_file_service_traversal_blocked(
    file_adapter: FileLogAdapter, tmp_path: Path
):
    """
    [Unit] log backends: verifies file service traversal blocked.

    Scenario:
        Given test inputs and fixtures for file service traversal blocked
        When test_file_service_traversal_blocked executes the target flow
        Then the expected outcome for file service traversal blocked is confirmed.

    Boundaries:
        - Focus: file service traversal blocked
        - Fixtures/params: file_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file service traversal blocked
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    assert await file_adapter.query_window("../../etc/passwd", _START, _END) == []


# ---------------------------------------------------------------------------
# FluentAdapter - stub
# ---------------------------------------------------------------------------


async def test_fluent_query_window_raises_notimplemented():
    """
    [Unit] log backends: verifies fluent query window raises notimplemented.

    Scenario:
        Given test inputs and fixtures for fluent query window raises notimplemented
        When test_fluent_query_window_raises_notimplemented executes the target flow
        Then the expected outcome for fluent query window raises notimplemented is confirmed.

    Boundaries:
        - Focus: fluent query window raises notimplemented
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fluent query window raises notimplemented
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    adapter = FluentAdapter(LogBackendSettings(provider="fluent", fluent_host="localhost"))
    with pytest.raises(NotImplementedError, match="stub"):
        await adapter.query_window("svc", _START, _END)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_file():
    """
    [Unit] log backends: verifies factory file.

    Scenario:
        Given test inputs and fixtures for factory file
        When test_factory_file executes the target flow
        Then the expected outcome for factory file is confirmed.

    Boundaries:
        - Focus: factory file
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory file
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    assert isinstance(create_log_backend(LogBackendSettings(provider="file")), FileLogAdapter)


def test_factory_fluent():
    """
    [Unit] log backends: verifies factory fluent.

    Scenario:
        Given test inputs and fixtures for factory fluent
        When test_factory_fluent executes the target flow
        Then the expected outcome for factory fluent is confirmed.

    Boundaries:
        - Focus: factory fluent
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory fluent
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    assert isinstance(create_log_backend(LogBackendSettings(provider="fluent")), FluentAdapter)


def test_factory_elk_deferred():
    """
    [Unit] log backends: verifies factory elk deferred.

    Scenario:
        Given test inputs and fixtures for factory elk deferred
        When test_factory_elk_deferred executes the target flow
        Then the expected outcome for factory elk deferred is confirmed.

    Boundaries:
        - Focus: factory elk deferred
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory elk deferred
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    settings = LogBackendSettings()
    object.__setattr__(settings, "provider", "elk")
    with pytest.raises(NotImplementedError, match="deferred"):
        create_log_backend(settings)


def test_factory_unknown_provider_raises():
    """
    [Unit] log backends: verifies factory unknown provider raises.

    Scenario:
        Given test inputs and fixtures for factory unknown provider raises
        When test_factory_unknown_provider_raises executes the target flow
        Then the expected outcome for factory unknown provider raises is confirmed.

    Boundaries:
        - Focus: factory unknown provider raises
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory unknown provider raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by log backends
    """
    settings = LogBackendSettings()
    object.__setattr__(settings, "provider", "splunk")
    with pytest.raises(ValueError, match="Unknown log provider"):
        create_log_backend(settings)
