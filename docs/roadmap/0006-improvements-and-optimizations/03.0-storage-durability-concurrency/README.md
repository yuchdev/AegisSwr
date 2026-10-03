# Task 03.0 — Storage Layer Durability & Concurrency

**Parent milestone:** [Milestone 0006 — Improvements & Optimizations](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
**Status:** ⬜ Not started

## Scope

Two storage gaps, both read directly out of the repository:

1. **SQLite runs on default rollback-journal locking with no tuning.**
   `src/aegis_swr/backends/storage/sqlite_store.py` opens every connection with
   `sqlite3.connect(str(self._db_path), timeout=30)` and **zero `PRAGMA`
   statements** — see `_init_db` (sqlite_store.py:67) and `_connect`
   (sqlite_store.py:74). No `journal_mode=WAL`, no `synchronous=NORMAL`, no
   `busy_timeout`. Every read and write goes through `asyncio.to_thread`
   (`save_report`:80-82, `find_by_hash`:115-117, etc.), so concurrent report
   saves and the cache-lookup `find_by_hash` — called on *every* orchestrator
   run before the cache-hit short-circuit — contend on the connection under
   SQLite's default journal, which serialises a writer against all readers more
   aggressively than WAL would.
2. **The Postgres path has no migration framework — and no schema at all.**
   `../../CLAUDE.md` §2 and `pyproject.toml` both name SQLAlchemy/asyncpg as the
   Postgres storage path, but no `alembic/` directory exists anywhere
   (confirmed: a repo-wide search for `alembic/` returns nothing).

### Re-verification note — the plan assumed models that do not exist

`plan.md`'s Task 03.0 proposed shape (b) says to "stand up an Alembic
environment against the **existing SQLAlchemy models** for the Postgres path."
At decomposition time those models **do not exist**.
`src/aegis_swr/backends/storage/postgres_store.py` is a **stub**: its module
docstring says *"Full implementation (SQLAlchemy async + alembic migration) is
deferred to a dedicated future phase"* and every method raises
`NotImplementedError` (postgres_store.py:31-53). There is no declarative base,
no `reports` table model, no `MetaData` — SQLAlchemy is not imported anywhere in
`src/` except a passing mention in `cli/commands.py`.

Alembic cannot autogenerate "against existing models" that are not there. This
task therefore **splits the Postgres work into two subtasks**: first *define*
the SQLAlchemy model for the `reports` table (the schema the stub lacks),
matching the concrete SQLite DDL already in `sqlite_store.py:34-48`, then stand
up Alembic with an initial migration against that model. Fully implementing
`PostgresStore`'s methods (making it actually persist) stays out of scope —
this task delivers the *schema definition and migration foundation* only, which
is the honest reading of "a no-op in effect, a foundation in practice."

| Decision point | Plan assumed | Reality | This task's call |
|----------------|--------------|---------|------------------|
| SQLAlchemy models for Postgres | already exist | none exist; `PostgresStore` is a stub | add a dedicated subtask (02) to define the `reports` model first |
| Alembic autogenerate target | the existing models | nothing to target | subtask 03 targets the model subtask 02 creates |
| `PostgresStore` method bodies | out of scope (unchanged) | still a stub | remains out of scope — foundation only |

The authoritative current schema is the SQLite DDL (`sqlite_store.py:34-48`):
a `reports` table (`incident_id` PK, `dump_hash`, `created_at`, `mode`,
`report_json`) plus a partial unique index `idx_reports_dump_hash` on
`dump_hash WHERE dump_hash IS NOT NULL`. The SQLAlchemy model and initial
Alembic migration must reproduce exactly this shape so the two backends stay
schema-compatible.

## Subtasks

| #  | Name                                                     | Document                                                       | Status         |
|----|----------------------------------------------------------|----------------------------------------------------------------|----------------|
| 01 | SQLite WAL + `synchronous=NORMAL` + `busy_timeout` pragmas | [SQLite durability pragmas](01-sqlite-wal-pragmas.md)         | ⬜ Not started |
| 02 | Define the SQLAlchemy `reports` model (Postgres path)    | [SQLAlchemy reports model](02-sqlalchemy-reports-model.md)      | ⬜ Not started |
| 03 | Alembic environment + initial migration                  | [Alembic migration harness](03-alembic-migration-harness.md)   | ⬜ Not started |

**Sequencing.** Subtask 01 (SQLite) is fully independent of 02/03 and can
proceed in parallel. Subtask 03 (Alembic) **depends on** subtask 02 (the model
it autogenerates from must exist first) — this ordering is the direct
consequence of the stale-evidence finding above. 01 is the highest-value quick
win; 02→03 is the foundation for a Postgres path that currently cannot evolve.

## Key constraints

- The SQLite pragma change must not alter the `RelationalStore` contract or any
  method signature in `sqlite_store.py` — it changes connection *setup* only.
- WAL creates `-wal` and `-shm` sidecar files next to the DB; any code or docs
  that enumerates/cleans the DB file (and `.gitignore`, which already ignores
  `prototype/*.db` per `.claude/settings.json`) must account for them.
- The SQLAlchemy model and Alembic migration must reproduce the current SQLite
  schema exactly (`sqlite_store.py:34-48`), including the **partial** unique
  index — Postgres supports partial indexes, so this is expressible natively.
- No incident payload may reach a log or an Alembic revision message: a
  migration's `down_revision`/message strings carry schema identifiers only,
  never `report_json` contents (`.claude/CLAUDE.md` §3).
- Implementing `PostgresStore`'s method bodies is **out of scope** — this task
  stops at schema + migration foundation; the stub keeps raising
  `NotImplementedError` until a future phase.

## Files created or modified by this task

```
src/aegis_swr/backends/storage/
├── sqlite_store.py            ← _init_db / _connect gain PRAGMA journal_mode=WAL,
│                                 synchronous=NORMAL, busy_timeout (subtask 01)
└── models.py                  ← NEW: SQLAlchemy declarative Base + ReportRow
                                 mapping the `reports` table (subtask 02)

alembic/                       ← NEW (subtask 03)
├── env.py                     ← wires target_metadata to models.Base.metadata
├── script.py.mako
└── versions/
    └── <rev>_initial_reports_schema.py   ← initial migration == current schema

alembic.ini                    ← NEW: Alembic config (DB URL from StorageSettings)

tests/unit/backends/storage/
├── test_sqlite_pragmas.py     ← NEW: asserts WAL/synchronous/busy_timeout applied
└── test_reports_model.py      ← NEW: asserts model DDL matches the SQLite schema
```
</content>
