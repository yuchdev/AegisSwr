from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
    SUPPORTED_FORMATS = [DumpFormat.WINDOWS_MINIDUMP]
    SUPPORTED_PLATFORMS = ["Windows"]

    def __init__(self, result: DebugExtractionResult) -> None:
        self._result = result
        self.extract_called = False

    def extract(self, source: IncidentSource, symbol_path: str | None) -> DebugExtractionResult:
        self.extract_called = True
        return self._result

    def _build_command_sequence(
        self, source: IncidentSource, symbol_path: str | None
    ) -> list[str]:
        return ["mock"]


def _mock_extraction() -> DebugExtractionResult:
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
    return DataAdapter(settings)


# ---------------------------------------------------------------------------
# Stage 1: hash + format detection
# ---------------------------------------------------------------------------


def test_hash_consistency(tmp_path: Path) -> None:
    a = tmp_path / "a.dmp"
    b = tmp_path / "b.dmp"
    a.write_bytes(b"MDMP" + b"\x00" * 100)
    b.write_bytes(b"MDMP" + b"\x00" * 100)
    assert DataAdapter._compute_hash(a) == DataAdapter._compute_hash(b)


def test_hash_differs_on_different_content(tmp_path: Path) -> None:
    a = tmp_path / "a.dmp"
    b = tmp_path / "b.dmp"
    a.write_bytes(b"MDMP" + b"\x00" * 100)
    b.write_bytes(b"MDMP" + b"\x01" * 100)
    assert DataAdapter._compute_hash(a) != DataAdapter._compute_hash(b)


def test_hash_has_prefix(tmp_path: Path) -> None:
    f = tmp_path / "a.dmp"
    f.write_bytes(b"MDMP")
    assert DataAdapter._compute_hash(f).startswith("sha256:")


def test_format_detection_minidump(tmp_path: Path) -> None:
    f = tmp_path / "crash.dmp"
    f.write_bytes(b"MDMP\x93\xa7" + b"\x00" * 50)
    assert DataAdapter._detect_format(f) == DumpFormat.WINDOWS_MINIDUMP


def test_format_detection_elf_core(tmp_path: Path) -> None:
    f = tmp_path / "core.1234"
    f.write_bytes(b"\x7fELF" + b"\x00" * 50)
    assert DataAdapter._detect_format(f) == DumpFormat.LINUX_CORE


def test_format_detection_apple_crashreport(tmp_path: Path) -> None:
    f = tmp_path / "crash.ips"
    f.write_bytes(b'{"app_name":"x"}')
    assert DataAdapter._detect_format(f) == DumpFormat.APPLE_CRASHREPORT


# ---------------------------------------------------------------------------
# Stage 3: noise filter
# ---------------------------------------------------------------------------


def test_noise_filter_removes_dbghelp() -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    filtered = apply_noise_filter(raw)
    assert "DBGHELP" not in filtered


def test_noise_filter_drops_dll_load_list() -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    filtered = apply_noise_filter(raw)
    assert "ModuleLoad" not in filtered
    # The exception analysis block must survive.
    assert "EXCEPTION_ANALYSIS:" in filtered
    assert "db_writer::serialize" in filtered


def test_noise_filter_replaces_fill_patterns() -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    filtered = apply_noise_filter(raw)
    assert "0xCCCCCCCC" not in filtered
    assert "<fill>" in filtered


def test_noise_filter_reduces_tokens_by_60_percent() -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    filtered = apply_noise_filter(raw)
    reduction = 1 - (count_tokens(filtered) / count_tokens(raw))
    assert reduction >= 0.60, f"only reduced {reduction:.0%}"


def test_noise_filter_truncates_to_8k() -> None:
    raw = "HEAD_MARKER\n" + ("x" * 12000) + "\nTAIL_MARKER"
    filtered = apply_noise_filter(raw)
    assert "[... middle section truncated ...]" in filtered
    assert filtered.startswith("HEAD_MARKER")
    assert filtered.endswith("TAIL_MARKER")
    # head 4000 + tail 4000 + marker
    assert len(filtered) < 8100


def test_noise_filter_no_truncation_when_small() -> None:
    raw = "short text"
    assert apply_noise_filter(raw) == raw


# ---------------------------------------------------------------------------
# Stage 4: temporal windowing + clustering
# ---------------------------------------------------------------------------


def test_temporal_window_slices_correctly(adapter: DataAdapter) -> None:
    incident = datetime(2026, 5, 30, 14, 2, 11)
    summary = adapter._process_logs(
        [str(FIXTURES / "sample_logs_timestamped.txt")], incident
    )
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


def test_no_timestamp_keeps_tail(adapter: DataAdapter) -> None:
    # No incident timestamp → fall back to last N lines (all kept here).
    summary = adapter._process_logs(
        [str(FIXTURES / "sample_logs_timestamped.txt")], None
    )
    assert summary is not None
    assert "AFTER_WINDOW_MARKER_2" in summary


def test_process_logs_returns_none_for_missing_path(adapter: DataAdapter) -> None:
    assert adapter._process_logs(["/nonexistent/file.log"], None) is None


def test_drain3_deduplicates_heartbeats() -> None:
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


def test_pii_scrubbing_emails(adapter: DataAdapter) -> None:
    text = (FIXTURES / "sample_logs_with_pii.txt").read_text()
    state = _ScrubState()
    scrubbed = adapter._scrub_text(text, state)
    assert "alice@example.com" not in scrubbed
    assert "bob.smith@corp.internal" not in scrubbed
    assert "[REDACTED_EMAIL_1]" in scrubbed


def test_pii_scrubbing_aws_keys(adapter: DataAdapter) -> None:
    text = (FIXTURES / "sample_logs_with_pii.txt").read_text()
    state = _ScrubState()
    scrubbed = adapter._scrub_text(text, state)
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert any("AWS_KEY" in token for token in state.mapping)


def test_pii_scrubbing_ip_and_db_conn(adapter: DataAdapter) -> None:
    text = (FIXTURES / "sample_logs_with_pii.txt").read_text()
    state = _ScrubState()
    scrubbed = adapter._scrub_text(text, state)
    assert "192.168.10.45" not in scrubbed
    assert "s3cr3tpw" not in scrubbed


def test_pii_scrubbing_stable_tokens(adapter: DataAdapter) -> None:
    state = _ScrubState()
    scrubbed = adapter._scrub_text("ping x@y.com then x@y.com again", state)
    # Same value reuses the same token.
    assert scrubbed.count("[REDACTED_EMAIL_1]") == 2
    assert len([t for t in state.mapping if t.startswith("[REDACTED_EMAIL")]) == 1


def test_pii_map_recovers_original(adapter: DataAdapter) -> None:
    state = _ScrubState()
    adapter._scrub_text("contact alice@example.com", state)
    assert "[REDACTED_EMAIL_1]" in state.mapping
    assert state.mapping["[REDACTED_EMAIL_1]"] == "alice@example.com"


# ---------------------------------------------------------------------------
# Stage 7: assumption token cap
# ---------------------------------------------------------------------------


def test_assumption_token_cap(adapter: DataAdapter) -> None:
    long_assumption = "the database connection pool was reduced yesterday " * 200
    capped = adapter._enforce_assumption_limit(long_assumption)
    limit = adapter._settings.core.user_assumption_token_limit
    assert count_tokens(capped) <= limit
    assert len(capped) < len(long_assumption)


def test_assumption_under_cap_unchanged(adapter: DataAdapter) -> None:
    short = "pool reduced from 10 to 5 connections"
    assert adapter._enforce_assumption_limit(short) == short


# ---------------------------------------------------------------------------
# Stage 5.3: conditional history injection
# ---------------------------------------------------------------------------


def test_should_inject_history_module_recurrence() -> None:
    brief = IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="db_writer")
    recent = [
        IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="db_writer"),
        IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="db_writer"),
        IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="other"),
    ]
    assert DataAdapter.should_inject_history(brief, recent) is True


def test_should_not_inject_history_when_no_recurrence() -> None:
    brief = IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="db_writer")
    recent = [IncidentBrief(mode=IncidentMode.CRASH_DUMP, faulting_module="other")]
    assert DataAdapter.should_inject_history(brief, recent) is False


def test_should_not_inject_history_empty() -> None:
    brief = IncidentBrief(mode=IncidentMode.CRASH_DUMP)
    assert DataAdapter.should_inject_history(brief, []) is False


# ---------------------------------------------------------------------------
# Stage 9: full pipeline
# ---------------------------------------------------------------------------


async def test_full_pipeline_produces_brief(adapter: DataAdapter, tmp_path: Path) -> None:
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


async def test_full_pipeline_low_symbol_warning(adapter: DataAdapter, tmp_path: Path) -> None:
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 10)
    extraction = _mock_extraction()
    extraction.symbol_resolution_score = 0.30
    source = IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path=str(dump))
    brief = await adapter.process(source, debug_backend=MockDebugBackend(extraction))
    assert brief.low_symbol_coverage_warning == "[LOW SYMBOL COVERAGE: 30%]"


async def test_full_pipeline_log_only_mode(adapter: DataAdapter) -> None:
    source = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
        log_paths=[str(FIXTURES / "sample_logs_with_pii.txt")],
    )
    brief = await adapter.process(source)
    assert brief.fault_class is None
    assert brief.dump_hash is None
    assert brief.log_summary is not None
