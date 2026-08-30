# 10 — `DTZ001`/`DTZ003`/`DTZ005`/`DTZ011`: Naive-datetime ban

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none
**Mechanism:** `ruff.toml` config only — no code in `flake8_project_rules`.

## Objective

Enable ruff's native `flake8-datetimez` codes:

- **`DTZ001`** — `datetime.datetime(...)` constructed without `tzinfo`.
- **`DTZ003`** — `datetime.utcnow()` (deprecated and naive; the stdlib itself
  recommends `datetime.now(timezone.utc)` instead).
- **`DTZ005`** — `datetime.now()` called without an explicit `tz=`.
- **`DTZ011`** — `date.today()` (naive by construction; flag the call site
  so a reviewer confirms date-only precision was actually intended).

Milestone 0005's own event-taxonomy contract (C10) requires every
`DomainEvent` subclass to carry *"a UTC `timestamp`"* — a naive
`datetime.now()` call is exactly the bug this contract exists to prevent
(it silently produces a local-time value that looks correct until it is
compared against another backend's UTC timestamp, or persisted and read back
in a different timezone).

## Config change

```toml
[lint]
select = [
    "E", "F", "I", "B", "SIM102", "SIM108", "C4", "UP017", "UP037",
    "DTZ001", "DTZ003", "DTZ005", "DTZ011",
]
```

## Rollout

1. Run `uv run ruff check --select DTZ001,DTZ003,DTZ005,DTZ011 src/ tests/`
   to baseline.
2. Every `src/` hit inside an event dataclass or anything feeding
   `CrashReportEntity`/`RCAReport` timestamps must become
   `datetime.now(timezone.utc)` (`DTZ005`/`DTZ003`) or
   `datetime(..., tzinfo=timezone.utc)` (`DTZ001`) — this is the one code in
   this subtask where "just silence it" is never acceptable, since it is
   this project's own documented event contract.
3. A genuine `DTZ011` (`date.today()`) hit that is intentionally date-only
   (e.g. a daily-rollup report key) may keep the naive `date`, with a
   `# noqa: DTZ011` and a one-line comment explaining why date-only
   precision is correct there — do not silently reach for
   `datetime.now(timezone.utc).date()` where local-date-boundary semantics
   were actually wanted (that would be a real behavior change, not a lint
   fix), but confirm on a case-by-case basis rather than blanket-suppressing.
