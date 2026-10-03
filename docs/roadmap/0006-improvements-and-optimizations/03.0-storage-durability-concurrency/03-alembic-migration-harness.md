# 03 — Alembic environment + initial migration

**Parent task:** [03.0 Storage Layer Durability & Concurrency](README.md)
**State:** ⬜ Not started
**Depends on:** [02 — SQLAlchemy reports model](02-sqlalchemy-reports-model.md)
(Alembic autogenerates from `models.Base.metadata`, which subtask 02 creates)
**Blocks:** none

## Objective

No `alembic/` directory exists anywhere in the repository, so the Postgres path
named in `../../CLAUDE.md` §2 and `pyproject.toml` has no schema-evolution
framework — any future column/index change would be ad-hoc manual SQL. Stand up a
standard Alembic environment wired to the model from subtask 02, and generate an
**initial migration that reproduces the current schema exactly** (a no-op in
effect against an already-correct DB, a foundation for every future change).

## Implementation approach

1. `uv run alembic init alembic` to scaffold `alembic/` and `alembic.ini`, then
   trim the generated boilerplate to the project's conventions.
2. In `alembic/env.py`, point `target_metadata` at the subtask-02 base:
   ```python
   from aegis_swr.backends.storage.models import Base
   target_metadata = Base.metadata
   ```
3. **Source the DB URL from settings, never hard-code it.** Read the Postgres
   URL from `StorageSettings` (the same settings object `postgres_store.py:26`
   receives) / the environment, following the project's "read from settings/env,
   never hard-code credentials" rule (`.claude/CLAUDE.md` §3). Do not write a
   literal connection string with an embedded password into `alembic.ini`;
   resolve it in `env.py` from settings so `SensitiveFilter` and the secret-scan
   hook are never bypassed.
4. `uv run alembic revision --autogenerate -m "initial reports schema"` and
   verify the generated `versions/<rev>_initial_reports_schema.py`:
   - creates the `reports` table with the five columns from
     `sqlite_store.py:34-48`;
   - creates the **partial** unique index `idx_reports_dump_hash` with the
     `postgresql_where=dump_hash IS NOT NULL` clause (autogenerate may not emit
     the partial clause — hand-correct the `op.create_index(...)` call to include
     `postgresql_where=sa.text("dump_hash IS NOT NULL")` if it does not);
   - has a correct `downgrade()` that drops the index then the table.
5. Document the two commands an operator runs (`alembic upgrade head`,
   `alembic revision --autogenerate -m "..."`) in the migration module docstring
   or a short `alembic/README.md`.

## Edge cases / exclusions

- **Autogenerate and partial indexes**: Alembic's autogenerate historically does
  not round-trip partial-index predicates reliably. Treat the generated file as a
  draft and hand-verify the `postgresql_where` clause against subtask 02's model
  — this is called out explicitly so the implementer does not ship a migration
  that silently drops the partial predicate (which would break the dump-hash
  cache uniqueness semantics).
- This migration targets the **Postgres** path. The SQLite backend keeps its own
  `CREATE TABLE IF NOT EXISTS` bootstrap (`sqlite_store.py:_init_db`) and is not
  migrated by Alembic — the two paths share a schema shape, not a migration
  runner. Note this so no one wires SQLite into `alembic upgrade`.
- `PostgresStore` stays a stub (out of scope per the task README). This subtask
  delivers the migration foundation, not a working Postgres backend.
- No incident payload in revision messages — schema identifiers only
  (`.claude/CLAUDE.md` §3).

## Test plan

- `tests/integration/backends/storage/test_alembic_migration.py` (new, mocked
  external): run `alembic upgrade head` against an ephemeral SQLite URL (or a
  containerised Postgres if the integration tier provides one) and assert the
  resulting `reports` table and `idx_reports_dump_hash` partial index match the
  model — then `alembic downgrade base` and assert they are gone. Mirrors the
  `.claude/CLAUDE.md` §4 "every external integration ships with an integration
  test (mocked externals)" mandate.
- A unit check that `alembic/env.py` resolves its URL from settings/env and does
  **not** contain a hard-coded credential (grep-style assertion) — enforces the
  §3 security rule as a test, not just a review note.
- `uv run alembic check` (autogenerate-diff is empty after `upgrade head`)
  confirms the migration is a true no-op against the model — the "no-op in
  effect, foundation in practice" acceptance from the plan.
</content>
