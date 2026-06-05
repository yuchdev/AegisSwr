"""Data-integrity tests for the storage backends (filesystem & SQLite)"""
from __future__ import annotations

import os

import pytest

from wincrash_analyzer.backends.store.filesystem import FilesystemBackend
from wincrash_analyzer.backends.store.sqlite import SQLiteBackend
from wincrash_analyzer.core.data_schema import make_report_id, make_timestamp
from wincrash_analyzer.core.exceptions import StorageBackendError


# ---------------------------------------------------------------------------
# Shared fixture: a canonical CrashReportEntity
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_record():
    """Return a minimal but valid CrashReportEntity dictionary"""
    return {
        "report_id": make_report_id(),
        "timestamp": make_timestamp(),
        "dump_path": "/crashes/example.dmp",
        "exception_code": "0xc0000005",
        "faulting_module": "ntdll.dll",
        "raw_stack": ["ntdll!RtlAllocateHeap+0x1234", "kernel32!BaseThreadInitThunk+0x14"],
        "ai_analysis": "## Root Cause\n\nAccess violation in heap allocator.",
        "engine_type": "cdb",
        "ai_model": "gemini-1.5-pro",
    }


# ---------------------------------------------------------------------------
# FilesystemBackend tests
# ---------------------------------------------------------------------------

class TestFilesystemBackend:
    def test_save_creates_json_file(self, sample_record, tmp_path):
        backend = FilesystemBackend(output_dir=str(tmp_path))
        result = backend.save(sample_record)
        assert result is True
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_round_trip(self, sample_record, tmp_path):
        """Saved data must be retrievable and identical to the original"""
        backend = FilesystemBackend(output_dir=str(tmp_path))
        backend.save(sample_record)
        loaded = backend.load_all()
        assert len(loaded) == 1
        assert loaded[0]["ai_analysis"] == sample_record["ai_analysis"]
        assert loaded[0]["report_id"] == sample_record["report_id"]

    def test_load_all_empty_dir(self, tmp_path):
        backend = FilesystemBackend(output_dir=str(tmp_path))
        assert backend.load_all() == []

    def test_load_all_nonexistent_dir(self, tmp_path):
        backend = FilesystemBackend(output_dir=str(tmp_path / "missing"))
        assert backend.load_all() == []

    def test_save_sanitizes_dump_path(self, tmp_path):
        """Records without report_id use sanitized dump_path as file stem"""
        record = {
            "dump_path": 'C:\\crashes\\my<bad>file.dmp',
            "ai_analysis": "ok",
        }
        backend = FilesystemBackend(output_dir=str(tmp_path))
        backend.save(record)
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "<" not in files[0].name
        assert ">" not in files[0].name

    @pytest.mark.skipif(os.name == "nt", reason="chmod(0o444) on a directory does not prevent file creation on Windows.")
    def test_save_readonly_dir_raises(self, sample_record, tmp_path):
        """Writing to a read-only directory raises StorageBackendError"""
        readonly = tmp_path / "ro"
        readonly.mkdir()
        readonly.chmod(0o444)
        try:
            backend = FilesystemBackend(output_dir=str(readonly))
            with pytest.raises(StorageBackendError):
                backend.save(sample_record)
        finally:
            readonly.chmod(0o755)


# ---------------------------------------------------------------------------
# SQLiteBackend tests
# ---------------------------------------------------------------------------

class TestSQLiteBackend:
    def test_save_returns_true(self, sample_record, tmp_path):
        db = str(tmp_path / "test.db")
        backend = SQLiteBackend(db_path=db)
        assert backend.save(sample_record) is True

    def test_round_trip(self, sample_record, tmp_path):
        """Saved data must be retrievable and ai_analysis must match exactly"""
        db = str(tmp_path / "test.db")
        backend = SQLiteBackend(db_path=db)
        backend.save(sample_record)
        rows = backend.load_all()
        assert len(rows) == 1
        assert rows[0]["ai_analysis"] == sample_record["ai_analysis"]

    def test_multiple_records(self, sample_record, tmp_path):
        db = str(tmp_path / "test.db")
        backend = SQLiteBackend(db_path=db)
        record2 = dict(sample_record, report_id=make_report_id(), exception_code="0x80000003")
        backend.save(sample_record)
        backend.save(record2)
        assert len(backend.load_all()) == 2

    def test_dump_name_stored(self, sample_record, tmp_path):
        """The dump_path should be stored in the record"""
        db = str(tmp_path / "test.db")
        backend = SQLiteBackend(db_path=db)
        backend.save(sample_record)
        rows = backend.load_all()
        assert rows[0]["dump_path"] == sample_record["dump_path"]

    def test_record_integrity(self, sample_record, tmp_path):
        """The stored JSON must contain all fields of the original record"""
        db = str(tmp_path / "test.db")
        backend = SQLiteBackend(db_path=db)
        backend.save(sample_record)
        rows = backend.load_all()
        assert rows[0] == sample_record
