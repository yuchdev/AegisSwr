# 02 — Define the SQLAlchemy `reports` model (Postgres path)

**Parent task:** [03.0 Storage Layer Durability & Concurrency](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** [03 — Alembic migration harness](03-alembic-migration-harness.md)

## Objective

The Postgres path has no SQLAlchemy schema. `postgres_store.py` is a stub whose
docstring defers the real implementation and whose methods all raise
`NotImplementedError` (postgres_store.py:31-53); SQLAlchemy is not imported in
`src/` at all. Alembic (subtask 03) autogenerates migrations by diffing a
`MetaData` against the live DB — with no models, there is nothing to diff.
This subtask creates the missing declarative model for the `reports` table so
subtask 03 has a target, **without** implementing `PostgresStore`'s persistence
(that stays out of scope).

The schema to reproduce is the one the SQLite backend already defines as DDL —
`sqlite_store.py:34-48`:

```python
_CREATE = """
CREATE TABLE IF NOT EXISTS reports (
    incident_id TEXT PRIMARY KEY,
    dump_hash   TEXT,
    created_at  TEXT NOT NULL,
    mode        TEXT NOT NULL,
    report_json TEXT NOT NULL
)
"""
_CREATE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_dump_hash
    ON reports(dump_hash)
    WHERE dump_hash IS NOT NULL
"""
```

## Implementation approach

Add `src/aegis_swr/backends/storage/models.py` with a SQLAlchemy 2.x typed
declarative base and one mapped class mirroring that table exactly:

```python
from __future__ import annotations

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for Aegis SWR relational storage models."""


class ReportRow(Base):
    """ORM mapping of the `reports` table (schema parity with SQLiteStore)."""

    __tablename__ = "reports"

    incident_id: Mapped[str] = mapped_column(String, primary_key=True)
    dump_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index(
            "idx_reports_dump_hash",
            "dump_hash",
            unique=True,
            postgresql_where=dump_hash.isnot(None),   # partial index (parity)
        ),
    )
```

Design notes:

- **Column types mirror SQLite's affinity, not an idealised schema.**
  `created_at` is stored as an ISO-8601 *string* in the SQLite backend
  (`sqlite_store.py:90` writes `report.created_at.isoformat()`), and
  `report_json` is the Pydantic `model_dump_json()` blob (`sqlite_store.py:91`).
  Keep them `String`/`Text` for cross-backend row compatibility; do **not**
  "improve" them to `DateTime`/`JSONB` here — that would be a schema change, not
  the no-op-in-effect foundation this task scopes.
- **The partial unique index is load-bearing** — it is what lets the dump-hash
  cache lookup (`find_by_hash`) stay unique while allowing many `NULL`
  dump-hash rows. Postgres supports `postgresql_where`, so it is expressible
  natively and must be reproduced, not dropped.
- This module imports only SQLAlchemy + stdlib. It does **not** import a backend
  family and does not touch `postgres_store.py`'s stub methods.

## Exclusions

- No change to `PostgresStore` method bodies — they keep raising
  `NotImplementedError`. This subtask delivers the schema definition only.
- No change to `sqlite_store.py` — the SQLite backend keeps its raw-DDL path;
  the ORM model is for the Postgres/Alembic path and schema-parity assertions.
- `pyproject.toml` already declares SQLAlchemy/asyncpg (per `../../CLAUDE.md`
  §2); if the dev extra is missing the import, add it — coordinate the
  resulting `uv.lock` change with Task 04.0's `--locked` check.

## Test plan

- `tests/unit/backends/storage/test_reports_model.py` (new): compile the model's
  DDL for the SQLite dialect and assert column names, nullability, the primary
  key on `incident_id`, and the **partial** unique index on `dump_hash` match
  the constants in `sqlite_store.py` (`_CREATE`, `_CREATE_INDEX`). This pins
  cross-backend schema parity so a future divergence fails a test.
- No integration test (no live Postgres is touched; `PostgresStore` stays a
  stub). The Alembic subtask (03) adds the migration-level check.
</content>
