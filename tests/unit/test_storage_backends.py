"""Unit tests for all four storage backends - no external services required"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from unittest import mock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from aegis_swr.backends.storage import (
    FilesystemStore,
    PostgresStore,
    S3Store,
    SQLiteStore,
    create_storage_backends,
)
from aegis_swr.config.settings import StorageSettings
from aegis_swr.core.exceptions import IncidentNotFoundError
from aegis_swr.core.schemas import (
    ConfidenceLevel,
    HITLRequest,
    Hypothesis,
    IncidentMode,
    RCAReport,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report(dump_hash: Optional[str] = None) -> RCAReport:
    return RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        dump_hash=dump_hash or f"sha256:{uuid4().hex}",
        root_cause="Use-after-free in serialize()",
        faulting_module="db_writer",
        confidence_score=0.88,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(root_cause="UAF", confidence=0.88),
        consensus_rounds=1,
    )


def _hitl_payload() -> dict[str, object]:
    return HITLRequest(
        question="What is the DB pool size?",
        context_summary="Split decision at 0.4 cs.",
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# FilesystemStore
# ---------------------------------------------------------------------------


@pytest.fixture
def fs_settings(tmp_path: Path) -> StorageSettings:
    return StorageSettings(
        provider="filesystem",
        reports_dir=str(tmp_path / "reports"),
        objects_dir=str(tmp_path / "objects"),
    )


@pytest.fixture
def fs_store(fs_settings: StorageSettings) -> FilesystemStore:
    return FilesystemStore(fs_settings)


async def test_filesystem_save_get_roundtrip(fs_store: FilesystemStore):
    """
    [Unit] storage backends: verifies filesystem save get roundtrip.

    Scenario:
        Given test inputs and fixtures for filesystem save get roundtrip
        When test_filesystem_save_get_roundtrip executes the target flow
        Then the expected outcome for filesystem save get roundtrip is confirmed.

    Boundaries:
        - Focus: filesystem save get roundtrip
        - Fixtures/params: fs_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to filesystem save get roundtrip
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report()
    await fs_store.save_report(report)
    loaded = await fs_store.get_report(report.incident_id)
    assert loaded is not None
    assert loaded.incident_id == report.incident_id
    assert loaded.root_cause == report.root_cause


async def test_filesystem_get_unknown_returns_none(fs_store: FilesystemStore):
    """
    [Unit] storage backends: verifies filesystem get unknown returns none.

    Scenario:
        Given test inputs and fixtures for filesystem get unknown returns none
        When test_filesystem_get_unknown_returns_none executes the target flow
        Then the expected outcome for filesystem get unknown returns none is confirmed.

    Boundaries:
        - Focus: filesystem get unknown returns none
        - Fixtures/params: fs_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to filesystem get unknown returns none
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    assert await fs_store.get_report(uuid4()) is None


async def test_filesystem_find_by_hash(fs_store: FilesystemStore):
    """
    [Unit] storage backends: verifies filesystem find by hash.

    Scenario:
        Given test inputs and fixtures for filesystem find by hash
        When test_filesystem_find_by_hash executes the target flow
        Then the expected outcome for filesystem find by hash is confirmed.

    Boundaries:
        - Focus: filesystem find by hash
        - Fixtures/params: fs_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to filesystem find by hash
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report(dump_hash="sha256:abc123")
    await fs_store.save_report(report)
    found = await fs_store.find_by_hash("sha256:abc123")
    assert found is not None
    assert found.incident_id == report.incident_id


async def test_filesystem_find_by_hash_unknown(fs_store: FilesystemStore):
    """
    [Unit] storage backends: verifies filesystem find by hash unknown.

    Scenario:
        Given test inputs and fixtures for filesystem find by hash unknown
        When test_filesystem_find_by_hash_unknown executes the target flow
        Then the expected outcome for filesystem find by hash unknown is confirmed.

    Boundaries:
        - Focus: filesystem find by hash unknown
        - Fixtures/params: fs_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to filesystem find by hash unknown
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    assert await fs_store.find_by_hash("sha256:no_such") is None


async def test_filesystem_update_hitl_response(fs_store: FilesystemStore):
    """
    [Unit] storage backends: verifies filesystem update hitl response.

    Scenario:
        Given test inputs and fixtures for filesystem update hitl response
        When test_filesystem_update_hitl_response executes the target flow
        Then the expected outcome for filesystem update hitl response is confirmed.

    Boundaries:
        - Focus: filesystem update hitl response
        - Fixtures/params: fs_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to filesystem update hitl response
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report()
    await fs_store.save_report(report)
    await fs_store.update_hitl_response(report.incident_id, _hitl_payload())
    loaded = await fs_store.get_report(report.incident_id)
    assert loaded is not None
    assert loaded.hitl_request is not None
    assert "DB pool size" in loaded.hitl_request.question


async def test_filesystem_upload_raw_get_raw(fs_store: FilesystemStore):
    """
    [Unit] storage backends: verifies filesystem upload raw get raw.

    Scenario:
        Given test inputs and fixtures for filesystem upload raw get raw
        When test_filesystem_upload_raw_get_raw executes the target flow
        Then the expected outcome for filesystem upload raw get raw is confirmed.

    Boundaries:
        - Focus: filesystem upload raw get raw
        - Fixtures/params: fs_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to filesystem upload raw get raw
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    incident_id = uuid4()
    data = b"MDMP\x00\x00\x00\x00" + b"\xab" * 64
    key = await fs_store.upload_raw(incident_id, "dump.dmp", data)
    assert key == f"{incident_id}/dump.dmp"
    recovered = await fs_store.get_raw(key)
    assert recovered == data


async def test_filesystem_get_raw_unknown_raises(fs_store: FilesystemStore):
    """
    [Unit] storage backends: verifies filesystem get raw unknown raises.

    Scenario:
        Given test inputs and fixtures for filesystem get raw unknown raises
        When test_filesystem_get_raw_unknown_raises executes the target flow
        Then the expected outcome for filesystem get raw unknown raises is confirmed.

    Boundaries:
        - Focus: filesystem get raw unknown raises
        - Fixtures/params: fs_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to filesystem get raw unknown raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    with pytest.raises(IncidentNotFoundError):
        await fs_store.get_raw(f"{uuid4()}/missing.dmp")


async def test_filesystem_path_traversal_blocked(fs_store: FilesystemStore):
    """
    [Unit] storage backends: verifies filesystem path traversal blocked.

    Scenario:
        Given test inputs and fixtures for filesystem path traversal blocked
        When test_filesystem_path_traversal_blocked executes the target flow
        Then the expected outcome for filesystem path traversal blocked is confirmed.

    Boundaries:
        - Focus: filesystem path traversal blocked
        - Fixtures/params: fs_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to filesystem path traversal blocked
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    with pytest.raises((ValueError, IncidentNotFoundError)):
        await fs_store.get_raw("../../etc/passwd")


# ---------------------------------------------------------------------------
# SQLiteStore
# ---------------------------------------------------------------------------


@pytest.fixture
def sq_store(tmp_path: Path) -> SQLiteStore:
    return SQLiteStore(
        StorageSettings(
            provider="sqlite",
            db_path=str(tmp_path / "test.db"),
        )
    )


async def test_sqlite_save_get_roundtrip(sq_store: SQLiteStore):
    """
    [Unit] storage backends: verifies sqlite save get roundtrip.

    Scenario:
        Given test inputs and fixtures for sqlite save get roundtrip
        When test_sqlite_save_get_roundtrip executes the target flow
        Then the expected outcome for sqlite save get roundtrip is confirmed.

    Boundaries:
        - Focus: sqlite save get roundtrip
        - Fixtures/params: sq_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to sqlite save get roundtrip
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report()
    await sq_store.save_report(report)
    loaded = await sq_store.get_report(report.incident_id)
    assert loaded is not None
    assert loaded.incident_id == report.incident_id


async def test_sqlite_get_unknown_returns_none(sq_store: SQLiteStore):
    """
    [Unit] storage backends: verifies sqlite get unknown returns none.

    Scenario:
        Given test inputs and fixtures for sqlite get unknown returns none
        When test_sqlite_get_unknown_returns_none executes the target flow
        Then the expected outcome for sqlite get unknown returns none is confirmed.

    Boundaries:
        - Focus: sqlite get unknown returns none
        - Fixtures/params: sq_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to sqlite get unknown returns none
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    assert await sq_store.get_report(uuid4()) is None


async def test_sqlite_find_by_hash(sq_store: SQLiteStore):
    """
    [Unit] storage backends: verifies sqlite find by hash.

    Scenario:
        Given test inputs and fixtures for sqlite find by hash
        When test_sqlite_find_by_hash executes the target flow
        Then the expected outcome for sqlite find by hash is confirmed.

    Boundaries:
        - Focus: sqlite find by hash
        - Fixtures/params: sq_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to sqlite find by hash
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report(dump_hash="sha256:deadbeef")
    await sq_store.save_report(report)
    found = await sq_store.find_by_hash("sha256:deadbeef")
    assert found is not None
    assert found.incident_id == report.incident_id


async def test_sqlite_find_by_hash_unknown(sq_store: SQLiteStore):
    """
    [Unit] storage backends: verifies sqlite find by hash unknown.

    Scenario:
        Given test inputs and fixtures for sqlite find by hash unknown
        When test_sqlite_find_by_hash_unknown executes the target flow
        Then the expected outcome for sqlite find by hash unknown is confirmed.

    Boundaries:
        - Focus: sqlite find by hash unknown
        - Fixtures/params: sq_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to sqlite find by hash unknown
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    assert await sq_store.find_by_hash("sha256:no_such") is None


async def test_sqlite_upsert_replaces_existing(sq_store: SQLiteStore):
    """
    [Unit] storage backends: verifies sqlite upsert replaces existing.

    Scenario:
        Given test inputs and fixtures for sqlite upsert replaces existing
        When test_sqlite_upsert_replaces_existing executes the target flow
        Then the expected outcome for sqlite upsert replaces existing is confirmed.

    Boundaries:
        - Focus: sqlite upsert replaces existing
        - Fixtures/params: sq_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to sqlite upsert replaces existing
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report(dump_hash="sha256:dup")
    await sq_store.save_report(report)
    report2 = report.model_copy(update={"root_cause": "Updated cause"})
    await sq_store.save_report(report2)
    loaded = await sq_store.get_report(report.incident_id)
    assert loaded is not None
    assert loaded.root_cause == "Updated cause"


async def test_sqlite_update_hitl_response(sq_store: SQLiteStore):
    """
    [Unit] storage backends: verifies sqlite update hitl response.

    Scenario:
        Given test inputs and fixtures for sqlite update hitl response
        When test_sqlite_update_hitl_response executes the target flow
        Then the expected outcome for sqlite update hitl response is confirmed.

    Boundaries:
        - Focus: sqlite update hitl response
        - Fixtures/params: sq_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to sqlite update hitl response
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report()
    await sq_store.save_report(report)
    await sq_store.update_hitl_response(report.incident_id, _hitl_payload())
    loaded = await sq_store.get_report(report.incident_id)
    assert loaded is not None and loaded.hitl_request is not None
    assert "DB pool size" in loaded.hitl_request.question


# ---------------------------------------------------------------------------
# S3Store - mocked boto3
# ---------------------------------------------------------------------------


@pytest.fixture
def s3_store() -> S3Store:
    with mock.patch("boto3.client") as mock_client_cls:
        mock_client_cls.return_value = mock.MagicMock()
        store = S3Store(
            StorageSettings(
                provider="s3",
                object_store_url="s3://test-bucket",
                object_store_region="us-east-1",
            )
        )
    return store


def _s3_get_object_response(body: bytes) -> dict[str, Any]:
    return {"Body": mock.Mock(read=mock.Mock(return_value=body))}


def _s3_no_such_key() -> ClientError:
    return ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject",
    )


async def test_s3_save_get_roundtrip(s3_store: S3Store):
    """
    [Mock] storage backends: verifies s3 save get roundtrip.

    Scenario:
        Given test inputs and fixtures for s3 save get roundtrip
        When test_s3_save_get_roundtrip executes the target flow
        Then the expected outcome for s3 save get roundtrip is confirmed.

    Boundaries:
        - Focus: s3 save get roundtrip
        - Fixtures/params: s3_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to s3 save get roundtrip
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report(dump_hash="sha256:s3hash")
    client = s3_store._client
    # After save, simulate the report existing.
    client.put_object = mock.MagicMock()
    stored_json: dict[str, bytes] = {}

    def _put(Bucket: str, Key: str, Body: bytes, **_: Any):  # noqa: N803
        stored_json[Key] = Body

    def _get(Bucket: str, Key: str, **_: Any) -> dict[str, Any]:  # noqa: N803
        if Key not in stored_json:
            raise _s3_no_such_key()
        return {"Body": mock.Mock(read=mock.Mock(return_value=stored_json[Key]))}

    client.put_object.side_effect = _put
    client.get_object.side_effect = _get

    await s3_store.save_report(report)
    loaded = await s3_store.get_report(report.incident_id)
    assert loaded is not None
    assert loaded.incident_id == report.incident_id


async def test_s3_find_by_hash(s3_store: S3Store):
    """
    [Mock] storage backends: verifies s3 find by hash.

    Scenario:
        Given test inputs and fixtures for s3 find by hash
        When test_s3_find_by_hash executes the target flow
        Then the expected outcome for s3 find by hash is confirmed.

    Boundaries:
        - Focus: s3 find by hash
        - Fixtures/params: s3_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to s3 find by hash
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    report = _report(dump_hash="sha256:findme")
    client = s3_store._client
    stored: dict[str, bytes] = {}

    def _put(Bucket: str, Key: str, Body: bytes, **_: Any):  # noqa: N803
        stored[Key] = Body

    def _get(Bucket: str, Key: str, **_: Any) -> dict[str, Any]:  # noqa: N803
        if Key not in stored:
            raise _s3_no_such_key()
        return {"Body": mock.Mock(read=mock.Mock(return_value=stored[Key]))}

    client.put_object.side_effect = _put
    client.get_object.side_effect = _get

    await s3_store.save_report(report)
    found = await s3_store.find_by_hash("sha256:findme")
    assert found is not None
    assert found.incident_id == report.incident_id


async def test_s3_find_by_hash_unknown(s3_store: S3Store):
    """
    [Unit] storage backends: verifies s3 find by hash unknown.

    Scenario:
        Given test inputs and fixtures for s3 find by hash unknown
        When test_s3_find_by_hash_unknown executes the target flow
        Then the expected outcome for s3 find by hash unknown is confirmed.

    Boundaries:
        - Focus: s3 find by hash unknown
        - Fixtures/params: s3_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to s3 find by hash unknown
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    s3_store._client.get_object.side_effect = _s3_no_such_key()
    result = await s3_store.find_by_hash("sha256:unknown")
    assert result is None


async def test_s3_upload_raw_get_raw(s3_store: S3Store):
    """
    [Mock] storage backends: verifies s3 upload raw get raw.

    Scenario:
        Given test inputs and fixtures for s3 upload raw get raw
        When test_s3_upload_raw_get_raw executes the target flow
        Then the expected outcome for s3 upload raw get raw is confirmed.

    Boundaries:
        - Focus: s3 upload raw get raw
        - Fixtures/params: s3_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to s3 upload raw get raw
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    incident_id = uuid4()
    data = b"\xde\xad\xbe\xef"
    stored: dict[str, bytes] = {}

    def _put(Bucket: str, Key: str, Body: bytes, **_: Any):  # noqa: N803
        stored[Key] = Body

    def _get(Bucket: str, Key: str, **_: Any) -> dict[str, Any]:  # noqa: N803
        return {"Body": mock.Mock(read=mock.Mock(return_value=stored[Key]))}

    s3_store._client.put_object.side_effect = _put
    s3_store._client.get_object.side_effect = _get

    key = await s3_store.upload_raw(incident_id, "core.dmp", data)
    assert key == f"{incident_id}/core.dmp"
    recovered = await s3_store.get_raw(key)
    assert recovered == data


# ---------------------------------------------------------------------------
# PostgresStore - stub
# ---------------------------------------------------------------------------


@pytest.fixture
def pg_store() -> PostgresStore:
    return PostgresStore(StorageSettings(provider="postgres"))


async def test_postgres_save_raises(pg_store: PostgresStore):
    """
    [Unit] storage backends: verifies postgres save raises.

    Scenario:
        Given test inputs and fixtures for postgres save raises
        When test_postgres_save_raises executes the target flow
        Then the expected outcome for postgres save raises is confirmed.

    Boundaries:
        - Focus: postgres save raises
        - Fixtures/params: pg_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to postgres save raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    with pytest.raises(NotImplementedError):
        await pg_store.save_report(_report())


async def test_postgres_get_raises(pg_store: PostgresStore):
    """
    [Unit] storage backends: verifies postgres get raises.

    Scenario:
        Given test inputs and fixtures for postgres get raises
        When test_postgres_get_raises executes the target flow
        Then the expected outcome for postgres get raises is confirmed.

    Boundaries:
        - Focus: postgres get raises
        - Fixtures/params: pg_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to postgres get raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    with pytest.raises(NotImplementedError):
        await pg_store.get_report(uuid4())


async def test_postgres_find_by_hash_raises(pg_store: PostgresStore):
    """
    [Unit] storage backends: verifies postgres find by hash raises.

    Scenario:
        Given test inputs and fixtures for postgres find by hash raises
        When test_postgres_find_by_hash_raises executes the target flow
        Then the expected outcome for postgres find by hash raises is confirmed.

    Boundaries:
        - Focus: postgres find by hash raises
        - Fixtures/params: pg_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to postgres find by hash raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    with pytest.raises(NotImplementedError):
        await pg_store.find_by_hash("sha256:x")


async def test_postgres_update_hitl_raises(pg_store: PostgresStore):
    """
    [Unit] storage backends: verifies postgres update hitl raises.

    Scenario:
        Given test inputs and fixtures for postgres update hitl raises
        When test_postgres_update_hitl_raises executes the target flow
        Then the expected outcome for postgres update hitl raises is confirmed.

    Boundaries:
        - Focus: postgres update hitl raises
        - Fixtures/params: pg_store
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to postgres update hitl raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    with pytest.raises(NotImplementedError):
        await pg_store.update_hitl_response(uuid4(), {})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_filesystem(tmp_path: Path):
    """
    [Unit] storage backends: verifies factory filesystem.

    Scenario:
        Given test inputs and fixtures for factory filesystem
        When test_factory_filesystem executes the target flow
        Then the expected outcome for factory filesystem is confirmed.

    Boundaries:
        - Focus: factory filesystem
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory filesystem
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    settings = StorageSettings(
        provider="filesystem",
        reports_dir=str(tmp_path / "r"),
        objects_dir=str(tmp_path / "o"),
    )
    relational, object_store = create_storage_backends(settings)
    assert isinstance(relational, FilesystemStore)
    assert isinstance(object_store, FilesystemStore)
    assert relational is object_store


def test_factory_sqlite(tmp_path: Path):
    """
    [Unit] storage backends: verifies factory sqlite.

    Scenario:
        Given test inputs and fixtures for factory sqlite
        When test_factory_sqlite executes the target flow
        Then the expected outcome for factory sqlite is confirmed.

    Boundaries:
        - Focus: factory sqlite
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory sqlite
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    relational, object_store = create_storage_backends(
        StorageSettings(provider="sqlite", db_path=str(tmp_path / "t.db"))
    )
    assert isinstance(relational, SQLiteStore)
    assert object_store is None


def test_factory_s3():
    """
    [Mock] storage backends: verifies factory s3.

    Scenario:
        Given test inputs and fixtures for factory s3
        When test_factory_s3 executes the target flow
        Then the expected outcome for factory s3 is confirmed.

    Boundaries:
        - Focus: factory s3
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory s3
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    with mock.patch("boto3.client"):
        relational, object_store = create_storage_backends(StorageSettings(provider="s3"))
    assert isinstance(relational, S3Store)
    assert isinstance(object_store, S3Store)
    assert relational is object_store


def test_factory_postgres():
    """
    [Unit] storage backends: verifies factory postgres.

    Scenario:
        Given test inputs and fixtures for factory postgres
        When test_factory_postgres executes the target flow
        Then the expected outcome for factory postgres is confirmed.

    Boundaries:
        - Focus: factory postgres
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory postgres
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by storage backends
    """
    relational, object_store = create_storage_backends(StorageSettings(provider="postgres"))
    assert isinstance(relational, PostgresStore)
    assert object_store is None


def test_factory_unknown_provider_raises():
    """
    [Unit] storage backends: verifies factory unknown provider raises.

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
        - Recent changes in code paths exercised by storage backends
    """
    settings = StorageSettings.__new__(StorageSettings)
    object.__setattr__(settings, "provider", "unknown_db")
    with pytest.raises(ValueError, match="Unknown storage provider"):
        create_storage_backends(settings)
