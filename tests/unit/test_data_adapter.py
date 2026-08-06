from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

from aegis_swr.backends.base import DebugBackend
from aegis_swr.config.settings import Settings
from aegis_swr.core.data_adapter import DataAdapter, _ScrubState, apply_noise_filter
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    DebugExtractionResult,
    DumpFormat,
    IncidentBrief,
    IncidentMode,
    IncidentSource,
    StackFrame,
)
from aegis_swr.core.tokens import count_tokens

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Mock debug backend
# ---------------------------------------------------------------------------


class MockDebugBackend(DebugBackend):
    """Support type for the data adapter tests (MockDebugBackend)."""

    SUPPORTED_FORMATS = [DumpFormat.WINDOWS_MINIDUMP]
    SUPPORTED_PLATFORMS = ["Windows"]

    def __init__(self, result: DebugExtractionResult):
        """Helper that provides init for the data adapter tests."""
        self._result = result
        self.extract_called = False

    def extract(self, source: IncidentSource, symbol_path: Optional[str]) -> DebugExtractionResult:
        """Helper that provides extract for the data adapter tests."""
        self.extract_called = True
        return self._result

    def _build_command_sequence(self, source: IncidentSource, symbol_path: Optional[str]) -> list[str]:
        """Helper that provides build command sequence for the data adapter tests."""
        return ["mock"]


def _mock_extraction() -> DebugExtractionResult:
    """Helper that provides mock extraction for the data adapter tests."""
    return DebugExtractionResult(
        fault_class=FaultClass.MEMORY_ACCESS_VIOLATION,
        exception_code_raw="0xc0000005",
        exception_address="0x00007ff8016a1c3f",
        faulting_module="db_writer",
        faulting_function="db_writer::serialize",
        stack_frames=[
            StackFrame(
                frame_number=0,
                module="db_writer",
                function="db_writer::serialize",
                instruction_address="0x00007ff8016a1c3f",
            ),
            StackFrame(frame_number=1, instruction_address="0x00007ff8016a2210"),
        ],
        symbol_resolution_score=0.5,
        raw_text_excerpt="DBGHELP: ntdll.pdb - file not found\nEXCEPTION_CODE: 0xc0000005\n",
    )


@pytest.fixture
def adapter(settings: Settings) -> DataAdapter:
    """Helper that provides adapter for the data adapter tests."""
    return DataAdapter(settings)


# ---------------------------------------------------------------------------
# Stage 1: hash + format detection
# ---------------------------------------------------------------------------


def test_hash_consistency(tmp_path: Path):
    """
    [Unit] data adapter: verifies hash consistency.

    Scenario:
        Given test inputs and fixtures for hash consistency
        When test_hash_consistency executes the target flow
        Then the expected outcome for hash consistency is confirmed.

    Boundaries:
        - Focus: hash consistency
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to hash consistency
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    a = tmp_path / "a.dmp"
    b = tmp_path / "b.dmp"
    a.write_bytes(b"MDMP" + b"\x00" * 100)
    b.write_bytes(b"MDMP" + b"\x00" * 100)
    assert DataAdapter._compute_hash(a) == DataAdapter._compute_hash(b)


def test_hash_differs_on_different_content(tmp_path: Path):
    """
    [Unit] data adapter: verifies hash differs on different content.

    Scenario:
        Given test inputs and fixtures for hash differs on different content
        When test_hash_differs_on_different_content executes the target flow
        Then the expected outcome for hash differs on different content is confirmed.

    Boundaries:
        - Focus: hash differs on different content
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to hash differs on different content
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    a = tmp_path / "a.dmp"
    b = tmp_path / "b.dmp"
    a.write_bytes(b"MDMP" + b"\x00" * 100)
    b.write_bytes(b"MDMP" + b"\x01" * 100)
    assert DataAdapter._compute_hash(a) != DataAdapter._compute_hash(b)


def test_hash_has_prefix(tmp_path: Path):
    """
    [Unit] data adapter: verifies hash has prefix.

    Scenario:
        Given test inputs and fixtures for hash has prefix
        When test_hash_has_prefix executes the target flow
        Then the expected outcome for hash has prefix is confirmed.

    Boundaries:
        - Focus: hash has prefix
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to hash has prefix
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    f = tmp_path / "a.dmp"
    f.write_bytes(b"MDMP")
    assert DataAdapter._compute_hash(f).startswith("sha256:")


def test_format_detection_minidump(tmp_path: Path):
    """
    [Unit] data adapter: verifies format detection minidump.

    Scenario:
        Given test inputs and fixtures for format detection minidump
        When test_format_detection_minidump executes the target flow
        Then the expected outcome for format detection minidump is confirmed.

    Boundaries:
        - Focus: format detection minidump
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to format detection minidump
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    f = tmp_path / "crash.dmp"
    f.write_bytes(b"MDMP\x93\xa7" + b"\x00" * 50)
    assert DataAdapter._detect_format(f) == DumpFormat.WINDOWS_MINIDUMP


def test_format_detection_elf_core(tmp_path: Path):
    """
    [Unit] data adapter: verifies format detection elf core.

    Scenario:
        Given test inputs and fixtures for format detection elf core
        When test_format_detection_elf_core executes the target flow
        Then the expected outcome for format detection elf core is confirmed.

    Boundaries:
        - Focus: format detection elf core
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to format detection elf core
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    f = tmp_path / "core.1234"
    f.write_bytes(b"\x7fELF" + b"\x00" * 50)
    assert DataAdapter._detect_format(f) == DumpFormat.LINUX_CORE


def test_format_detection_apple_crashreport(tmp_path: Path):
    """
    [Unit] data adapter: verifies format detection apple crashreport.

    Scenario:
        Given test inputs and fixtures for format detection apple crashreport
        When test_format_detection_apple_crashreport executes the target flow
        Then the expected outcome for format detection apple crashreport is confirmed.

    Boundaries:
        - Focus: format detection apple crashreport
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to format detection apple crashreport
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    f = tmp_path / "crash.ips"
    f.write_bytes(b'{"app_name":"x"}')
    assert DataAdapter._detect_format(f) == DumpFormat.APPLE_CRASHREPORT


# ---------------------------------------------------------------------------
# Stage 3: noise filter
# ---------------------------------------------------------------------------


def test_noise_filter_removes_dbghelp():
    """
    [Unit] data adapter: verifies noise filter removes dbghelp.

    Scenario:
        Given test inputs and fixtures for noise filter removes dbghelp
        When test_noise_filter_removes_dbghelp executes the target flow
        Then the expected outcome for noise filter removes dbghelp is confirmed.

    Boundaries:
        - Focus: noise filter removes dbghelp
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to noise filter removes dbghelp
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    filtered = apply_noise_filter(raw)
    assert "DBGHELP" not in filtered


def test_noise_filter_drops_dll_load_list():
    """
    [Unit] data adapter: verifies noise filter drops dll load list.

    Scenario:
        Given test inputs and fixtures for noise filter drops dll load list
        When test_noise_filter_drops_dll_load_list executes the target flow
        Then the expected outcome for noise filter drops dll load list is confirmed.

    Boundaries:
        - Focus: noise filter drops dll load list
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to noise filter drops dll load list
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    filtered = apply_noise_filter(raw)
    assert "ModuleLoad" not in filtered
    # The exception analysis block must survive.
    assert "EXCEPTION_ANALYSIS:" in filtered
    assert "db_writer::serialize" in filtered


def test_noise_filter_replaces_fill_patterns():
    """
    [Unit] data adapter: verifies noise filter replaces fill patterns.

    Scenario:
        Given test inputs and fixtures for noise filter replaces fill patterns
        When test_noise_filter_replaces_fill_patterns executes the target flow
        Then the expected outcome for noise filter replaces fill patterns is confirmed.

    Boundaries:
        - Focus: noise filter replaces fill patterns
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to noise filter replaces fill patterns
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    filtered = apply_noise_filter(raw)
    assert "0xCCCCCCCC" not in filtered
    assert "<fill>" in filtered


def test_noise_filter_reduces_tokens_by_60_percent():
    """
    [Unit] data adapter: verifies noise filter reduces tokens by 60 percent.

    Scenario:
        Given test inputs and fixtures for noise filter reduces tokens by 60 percent
        When test_noise_filter_reduces_tokens_by_60_percent executes the target flow
        Then the expected outcome for noise filter reduces tokens by 60 percent is confirmed.

    Boundaries:
        - Focus: noise filter reduces tokens by 60 percent
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to noise filter reduces tokens by 60 percent
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    filtered = apply_noise_filter(raw)
    reduction = 1 - (count_tokens(filtered) / count_tokens(raw))
    assert reduction >= 0.60, f"only reduced {reduction:.0%}"


def test_noise_filter_truncates_to_8k():
    """
    [Unit] data adapter: verifies noise filter truncates to 8k.

    Scenario:
        Given test inputs and fixtures for noise filter truncates to 8k
        When test_noise_filter_truncates_to_8k executes the target flow
        Then the expected outcome for noise filter truncates to 8k is confirmed.

    Boundaries:
        - Focus: noise filter truncates to 8k
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to noise filter truncates to 8k
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    raw = "HEAD_MARKER\n" + ("x" * 12000) + "\nTAIL_MARKER"
    filtered = apply_noise_filter(raw)
    assert "[... middle section truncated ...]" in filtered
    assert filtered.startswith("HEAD_MARKER")
    assert filtered.endswith("TAIL_MARKER")
    # head 4000 + tail 4000 + marker
    assert len(filtered) < 8100


def test_noise_filter_no_truncation_when_small():
    """
    [Unit] data adapter: verifies noise filter no truncation when small.

    Scenario:
        Given test inputs and fixtures for noise filter no truncation when small
        When test_noise_filter_no_truncation_when_small executes the target flow
        Then the expected outcome for noise filter no truncation when small is confirmed.

    Boundaries:
        - Focus: noise filter no truncation when small
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to noise filter no truncation when small
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    raw = "short text"
    assert apply_noise_filter(raw) == raw


# ---------------------------------------------------------------------------
# Stage 4: temporal windowing + clustering
# ---------------------------------------------------------------------------


def test_temporal_window_slices_correctly(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies temporal window slices correctly.

    Scenario:
        Given test inputs and fixtures for temporal window slices correctly
        When test_temporal_window_slices_correctly executes the target flow
        Then the expected outcome for temporal window slices correctly is confirmed.

    Boundaries:
        - Focus: temporal window slices correctly
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to temporal window slices correctly
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    incident = datetime(2026, 5, 30, 14, 2, 11)
    summary = adapter._process_logs([str(FIXTURES / "sample_logs_timestamped.txt")], incident)
    assert summary is not None
    # In window, WARN+ kept
    assert "FATAL_MARKER" in summary
    assert "ERROR_IN_WINDOW_MARKER" in summary
    assert "WARN_IN_WINDOW_MARKER" in summary
    # In inner ±5s window, even INFO kept
    assert "INNER_INFO_MARKER" in summary
    # In broad window but outside inner: INFO dropped
    assert "OUTER_INFO_MARKER" not in summary
    # Outside the ±30s window entirely: dropped
    assert "BEFORE_WINDOW_MARKER" not in summary
    assert "AFTER_WINDOW_MARKER" not in summary


def test_no_timestamp_keeps_tail(adapter: DataAdapter):
    # No incident timestamp → fall back to last N lines (all kept here).
    """
    [Unit] data adapter: verifies no timestamp keeps tail.

    Scenario:
        Given test inputs and fixtures for no timestamp keeps tail
        When test_no_timestamp_keeps_tail executes the target flow
        Then the expected outcome for no timestamp keeps tail is confirmed.

    Boundaries:
        - Focus: no timestamp keeps tail
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to no timestamp keeps tail
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    summary = adapter._process_logs([str(FIXTURES / "sample_logs_timestamped.txt")], None)
    assert summary is not None
    assert "AFTER_WINDOW_MARKER_2" in summary


def test_process_logs_returns_none_for_missing_path(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies process logs returns none for missing path.

    Scenario:
        Given test inputs and fixtures for process logs returns none for missing path
        When test_process_logs_returns_none_for_missing_path executes the target flow
        Then the expected outcome for process logs returns none for missing path is confirmed.

    Boundaries:
        - Focus: process logs returns none for missing path
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to process logs returns none for missing path
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    assert adapter._process_logs(["/nonexistent/file.log"], None) is None


def test_process_logs_merges_extra_lines(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies process logs merges extra lines.

    Scenario:
        Given test inputs and fixtures for process logs merges extra lines
        When test_process_logs_merges_extra_lines executes the target flow
        Then the expected outcome for process logs merges extra lines is confirmed.

    Boundaries:
        - Focus: process logs merges extra lines
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to process logs merges extra lines
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    incident = datetime(2026, 5, 30, 14, 2, 11)
    extra = ["2026-05-30T14:02:13 ERROR EXTRA_MARKER from backend"]
    summary = adapter._process_logs([], incident, extra_lines=extra)
    assert summary is not None
    assert "EXTRA_MARKER" in summary


# ---------------------------------------------------------------------------
# Stage 4: LogBackend integration
# ---------------------------------------------------------------------------


class _FakeLogBackend:
    """Minimal LogBackend returning canned windowed lines"""

    def __init__(self, lines: list[str]):
        """Helper that provides init for the data adapter tests."""
        self._lines = lines
        self.called_with: tuple = ()

    async def query_window(self, service, start_time, end_time, severity_levels=None) -> list[str]:
        """Helper that provides query window for the data adapter tests."""
        self.called_with = (service, start_time, end_time)
        return self._lines


class _StubLogBackend:
    """LogBackend stub that always raises (like FluentAdapter)"""

    async def query_window(self, *args, **kwargs):
        """Helper that provides query window for the data adapter tests."""
        raise NotImplementedError("stub")


async def test_log_backend_lines_merged_into_brief(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies log backend lines merged into brief.

    Scenario:
        Given test inputs and fixtures for log backend lines merged into brief
        When test_log_backend_lines_merged_into_brief executes the target flow
        Then the expected outcome for log backend lines merged into brief is confirmed.

    Boundaries:
        - Focus: log backend lines merged into brief
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log backend lines merged into brief
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    backend = _FakeLogBackend(["2026-05-30T14:02:13 ERROR LOGBACKEND_MARKER from fluent"])
    source = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
        metadata={"service": "auth-api"},
    )
    brief = await adapter.process(source, log_backend=backend)
    assert brief.log_summary is not None
    assert "LOGBACKEND_MARKER" in brief.log_summary
    assert backend.called_with[0] == "auth-api"


async def test_log_backend_not_queried_without_service(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies log backend not queried without service.

    Scenario:
        Given test inputs and fixtures for log backend not queried without service
        When test_log_backend_not_queried_without_service executes the target flow
        Then the expected outcome for log backend not queried without service is confirmed.

    Boundaries:
        - Focus: log backend not queried without service
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log backend not queried without service
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    backend = _FakeLogBackend(["2026-05-30T14:02:13 ERROR SHOULD_NOT_APPEAR"])
    source = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
    )  # no metadata["service"]
    brief = await adapter.process(source, log_backend=backend)
    assert backend.called_with == ()
    assert brief.log_summary is None


async def test_log_backend_stub_degrades_gracefully(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies log backend stub degrades gracefully.

    Scenario:
        Given test inputs and fixtures for log backend stub degrades gracefully
        When test_log_backend_stub_degrades_gracefully executes the target flow
        Then the expected outcome for log backend stub degrades gracefully is confirmed.

    Boundaries:
        - Focus: log backend stub degrades gracefully
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log backend stub degrades gracefully
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    source = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
        metadata={"service": "auth-api"},
    )
    # NotImplementedError from the backend must not fail the pipeline.
    brief = await adapter.process(source, log_backend=_StubLogBackend())
    assert brief.log_summary is None


def test_drain3_deduplicates_heartbeats():
    """
    [Unit] data adapter: verifies drain3 deduplicates heartbeats.

    Scenario:
        Given test inputs and fixtures for drain3 deduplicates heartbeats
        When test_drain3_deduplicates_heartbeats executes the target flow
        Then the expected outcome for drain3 deduplicates heartbeats is confirmed.

    Boundaries:
        - Focus: drain3 deduplicates heartbeats
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to drain3 deduplicates heartbeats
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    lines = ["Connection pool status OK"] * 100
    lines += [
        "ERROR database write failed on shard 7",
        "FATAL irrecoverable corruption detected",
    ]
    output = DataAdapter._cluster_and_dedup(lines)
    # 100 identical heartbeats collapse to a single annotated line.
    assert len(output) <= 5
    assert any("×" in line for line in output)
    assert any("shard 7" in line for line in output)


# ---------------------------------------------------------------------------
# Stage 6: PII scrubbing
# ---------------------------------------------------------------------------


def test_pii_scrubbing_emails(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies pii scrubbing emails.

    Scenario:
        Given test inputs and fixtures for pii scrubbing emails
        When test_pii_scrubbing_emails executes the target flow
        Then the expected outcome for pii scrubbing emails is confirmed.

    Boundaries:
        - Focus: pii scrubbing emails
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pii scrubbing emails
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    text = (FIXTURES / "sample_logs_with_pii.txt").read_text()
    state = _ScrubState()
    scrubbed = adapter._scrub_text(text, state)
    assert "alice@example.com" not in scrubbed
    assert "bob.smith@corp.internal" not in scrubbed
    assert "[REDACTED_EMAIL_1]" in scrubbed


def test_pii_scrubbing_aws_keys(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies pii scrubbing aws keys.

    Scenario:
        Given test inputs and fixtures for pii scrubbing aws keys
        When test_pii_scrubbing_aws_keys executes the target flow
        Then the expected outcome for pii scrubbing aws keys is confirmed.

    Boundaries:
        - Focus: pii scrubbing aws keys
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pii scrubbing aws keys
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    text = (FIXTURES / "sample_logs_with_pii.txt").read_text()
    state = _ScrubState()
    scrubbed = adapter._scrub_text(text, state)
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert any("AWS_KEY" in token for token in state.mapping)


def test_pii_scrubbing_ip_and_db_conn(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies pii scrubbing ip and db conn.

    Scenario:
        Given test inputs and fixtures for pii scrubbing ip and db conn
        When test_pii_scrubbing_ip_and_db_conn executes the target flow
        Then the expected outcome for pii scrubbing ip and db conn is confirmed.

    Boundaries:
        - Focus: pii scrubbing ip and db conn
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pii scrubbing ip and db conn
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    text = (FIXTURES / "sample_logs_with_pii.txt").read_text()
    state = _ScrubState()
    scrubbed = adapter._scrub_text(text, state)
    assert "192.168.10.45" not in scrubbed
    assert "s3cr3tpw" not in scrubbed


def test_pii_scrubbing_stable_tokens(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies pii scrubbing stable tokens.

    Scenario:
        Given test inputs and fixtures for pii scrubbing stable tokens
        When test_pii_scrubbing_stable_tokens executes the target flow
        Then the expected outcome for pii scrubbing stable tokens is confirmed.

    Boundaries:
        - Focus: pii scrubbing stable tokens
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pii scrubbing stable tokens
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    state = _ScrubState()
    scrubbed = adapter._scrub_text("ping x@y.com then x@y.com again", state)
    # Same value reuses the same token.
    assert scrubbed.count("[REDACTED_EMAIL_1]") == 2
    assert len([t for t in state.mapping if t.startswith("[REDACTED_EMAIL")]) == 1


def test_pii_map_recovers_original(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies pii map recovers original.

    Scenario:
        Given test inputs and fixtures for pii map recovers original
        When test_pii_map_recovers_original executes the target flow
        Then the expected outcome for pii map recovers original is confirmed.

    Boundaries:
        - Focus: pii map recovers original
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pii map recovers original
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    state = _ScrubState()
    adapter._scrub_text("contact alice@example.com", state)
    assert "[REDACTED_EMAIL_1]" in state.mapping
    assert state.mapping["[REDACTED_EMAIL_1]"] == "alice@example.com"


# ---------------------------------------------------------------------------
# Stage 7: assumption token cap
# ---------------------------------------------------------------------------


def test_assumption_token_cap(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies assumption token cap.

    Scenario:
        Given test inputs and fixtures for assumption token cap
        When test_assumption_token_cap executes the target flow
        Then the expected outcome for assumption token cap is confirmed.

    Boundaries:
        - Focus: assumption token cap
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to assumption token cap
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    long_assumption = "the database connection pool was reduced yesterday " * 200
    capped = adapter._enforce_assumption_limit(long_assumption)
    limit = adapter._settings.core.user_assumption_token_limit
    assert count_tokens(capped) <= limit
    assert len(capped) < len(long_assumption)


def test_assumption_under_cap_unchanged(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies assumption under cap unchanged.

    Scenario:
        Given test inputs and fixtures for assumption under cap unchanged
        When test_assumption_under_cap_unchanged executes the target flow
        Then the expected outcome for assumption under cap unchanged is confirmed.

    Boundaries:
        - Focus: assumption under cap unchanged
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to assumption under cap unchanged
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    short = "pool reduced from 10 to 5 connections"
    assert adapter._enforce_assumption_limit(short) == short


# ---------------------------------------------------------------------------
# Stage 5.3: conditional history injection
# ---------------------------------------------------------------------------


def test_should_inject_history_module_recurrence():
    """
    [Unit] data adapter: verifies should inject history module recurrence.

    Scenario:
        Given test inputs and fixtures for should inject history module recurrence
        When test_should_inject_history_module_recurrence executes the target flow
        Then the expected outcome for should inject history module recurrence is confirmed.

    Boundaries:
        - Focus: should inject history module recurrence
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to should inject history module recurrence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    brief = IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="db_writer")
    recent = [
        IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="db_writer"),
        IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="db_writer"),
        IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="other"),
    ]
    assert DataAdapter.should_inject_history(brief, recent) is True


def test_should_not_inject_history_when_no_recurrence():
    """
    [Unit] data adapter: verifies should not inject history when no recurrence.

    Scenario:
        Given test inputs and fixtures for should not inject history when no recurrence
        When test_should_not_inject_history_when_no_recurrence executes the target flow
        Then the expected outcome for should not inject history when no recurrence is confirmed.

    Boundaries:
        - Focus: should not inject history when no recurrence
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to should not inject history when no recurrence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    brief = IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="db_writer")
    recent = [IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="other")]
    assert DataAdapter.should_inject_history(brief, recent) is False


def test_should_not_inject_history_empty():
    """
    [Unit] data adapter: verifies should not inject history empty.

    Scenario:
        Given test inputs and fixtures for should not inject history empty
        When test_should_not_inject_history_empty executes the target flow
        Then the expected outcome for should not inject history empty is confirmed.

    Boundaries:
        - Focus: should not inject history empty
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to should not inject history empty
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    brief = IncidentBrief(mode=IncidentMode.CRASH_DUMP)
    assert DataAdapter.should_inject_history(brief, []) is False


# ---------------------------------------------------------------------------
# Stage 9: full pipeline
# ---------------------------------------------------------------------------


async def test_full_pipeline_produces_brief(adapter: DataAdapter, tmp_path: Path):
    """
    [Unit] data adapter: verifies full pipeline produces brief.

    Scenario:
        Given test inputs and fixtures for full pipeline produces brief
        When test_full_pipeline_produces_brief executes the target flow
        Then the expected outcome for full pipeline produces brief is confirmed.

    Boundaries:
        - Focus: full pipeline produces brief
        - Fixtures/params: adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to full pipeline produces brief
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 200)
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
        dump_path=str(dump),
        log_paths=[str(FIXTURES / "sample_logs_with_pii.txt")],
        user_assumption="pool reduced yesterday",
    )
    backend = MockDebugBackend(_mock_extraction())

    brief = await adapter.process(source, debug_backend=backend)

    assert isinstance(brief, IncidentBrief)
    assert backend.extract_called is True
    assert brief.dump_hash is not None and brief.dump_hash.startswith("sha256:")
    assert brief.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert brief.faulting_module == "db_writer"
    assert len(brief.stack_frames) == 2
    # Symbol score 0.5 is NOT < 0.50, so no low-coverage warning.
    assert brief.low_symbol_coverage_warning is None
    # Noise filter applied to the raw excerpt.
    assert brief.raw_text_excerpt is not None
    assert "DBGHELP" not in brief.raw_text_excerpt
    # Log summary present and PII-scrubbed.
    assert brief.log_summary is not None
    assert "alice@example.com" not in brief.log_summary
    # PII map captured out-of-band, never in the brief.
    assert adapter.last_pii_substitution_map
    assert "pii" not in brief.model_dump()


async def test_full_pipeline_low_symbol_warning(adapter: DataAdapter, tmp_path: Path):
    """
    [Unit] data adapter: verifies full pipeline low symbol warning.

    Scenario:
        Given test inputs and fixtures for full pipeline low symbol warning
        When test_full_pipeline_low_symbol_warning executes the target flow
        Then the expected outcome for full pipeline low symbol warning is confirmed.

    Boundaries:
        - Focus: full pipeline low symbol warning
        - Fixtures/params: adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to full pipeline low symbol warning
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 10)
    extraction = _mock_extraction()
    extraction.symbol_resolution_score = 0.30
    source = IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path=str(dump))
    brief = await adapter.process(source, debug_backend=MockDebugBackend(extraction))
    assert brief.low_symbol_coverage_warning == "[LOW SYMBOL COVERAGE: 30%]"


async def test_full_pipeline_log_only_mode(adapter: DataAdapter):
    """
    [Unit] data adapter: verifies full pipeline log only mode.

    Scenario:
        Given test inputs and fixtures for full pipeline log only mode
        When test_full_pipeline_log_only_mode executes the target flow
        Then the expected outcome for full pipeline log only mode is confirmed.

    Boundaries:
        - Focus: full pipeline log only mode
        - Fixtures/params: adapter
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to full pipeline log only mode
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by data adapter
    """
    source = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
        log_paths=[str(FIXTURES / "sample_logs_with_pii.txt")],
    )
    brief = await adapter.process(source)
    assert brief.fault_class is None
    assert brief.dump_hash is None
    assert brief.log_summary is not None
