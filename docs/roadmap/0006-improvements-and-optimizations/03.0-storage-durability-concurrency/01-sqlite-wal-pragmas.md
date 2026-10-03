# 01 — SQLite WAL + `synchronous=NORMAL` + `busy_timeout` pragmas

**Parent task:** [03.0 Storage Layer Durability & Concurrency](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none

## Objective

`sqlite_store.py` opens connections with no pragmas. `_connect`
(sqlite_store.py:72-74) is:

```python
def _connect(self) -> sqlite3.Connection:
    """Open a new SQLite connection to the backing database file."""
    return sqlite3.connect(str(self._db_path), timeout=30)
```

and `_init_db` (sqlite_store.py:64-70) opens its own connection the same way.
Under SQLite's default `journal_mode=DELETE` (rollback journal), a writer takes
an exclusive lock that blocks every reader for the duration of the write. Because
`find_by_hash` runs on **every** orchestrator cache-check before the LLM call,
and `save_report` runs at the end of each investigation, concurrent
investigations serialise against each other more than they need to. WAL lets
readers proceed concurrently with a single writer; `synchronous=NORMAL` is the
safe-with-WAL durability setting; `busy_timeout` replaces silent lock contention
with a bounded wait.

## Implementation approach

Apply the three pragmas on **every** connection — both `_connect` and the one
`_init_db` opens — because pragmas like `busy_timeout` are per-connection, and
`journal_mode=WAL` must be set on a connection to the database file (it persists
in the DB header once set, but setting it defensively on each open is harmless
and keeps new connections correct even on a fresh file).

```python
_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=30000",   # ms; mirrors the existing timeout=30 (s)
)

def _connect(self) -> sqlite3.Connection:
    """Open a tuned SQLite connection (WAL, NORMAL sync, bounded busy wait)."""
    conn = sqlite3.connect(str(self._db_path), timeout=30)
    for pragma in _PRAGMAS:
        conn.execute(pragma)
    return conn
```

Have `_init_db` route through the same helper (or a shared `_apply_pragmas(conn)`
function) so the pragma set has a single source of truth and cannot drift between
the two open sites. Keep the existing `timeout=30` kwarg — `busy_timeout` and
the Python-level `timeout` cover overlapping-but-distinct waits; keeping both
matches the current 30 s intent.

The RAII `with sqlite3.connect(...)` context-manager usage already present
(sqlite_store.py:94, 106, 121, 144, 168) stays — this change only adds pragma
execution inside the helper, honouring the RAII convention (`.claude/CLAUDE.md`
§2).

## Edge cases / exclusions

- `journal_mode=WAL` is a no-op for an in-memory DB; if any test uses
  `:memory:`, assert the returned mode is `wal` only for file-backed DBs.
- WAL writes `<db>-wal` and `<db>-shm` sidecar files. Confirm `.gitignore`
  already covers them under the existing `prototype/*.db` pattern or extend it;
  note them in any teardown that deletes the DB file.
- No method signature or `RelationalStore` contract changes — connection setup
  only.

## Test plan

- `tests/unit/backends/storage/test_sqlite_pragmas.py` (new): construct a
  `SQLiteStore` against a temp-file DB, open a connection via the store's own
  helper, and assert the pragmas took effect:
  ```python
  assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
  assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1   # NORMAL
  assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
  ```
  This is the regression test `plan.md`'s proposed shape (a) explicitly calls
  for — "asserting the pragma took effect."
- A concurrency smoke test is optional but valuable: two `asyncio.gather`-ed
  `save_report`/`find_by_hash` calls against the same store complete without a
  `database is locked` error within `busy_timeout`.
- Existing `sqlite_store` unit tests must stay green (contract unchanged).
</content>
