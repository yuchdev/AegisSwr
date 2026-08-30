# Milestone 0006 — Improvements & Optimizations

**Package:** `aegis-swr` | **Module roots:** `flake8_project_rules/` (extended);
touches `ruff.toml`, `mypy.ini`, `.github/workflows/`,
`src/aegis_swr/backends/storage/`, `docs/`.
**Depends on:** Milestone 0005 (Harness & multi-backend support), complete.

This milestone is a **quality and operability pass** across the codebase
rather than a new feature. It does not add a product capability; it closes
gaps in the tooling and infrastructure that catches regressions before they
ship. Six tasks are proposed. **Task 01.0 is fully decomposed** into
subtasks (the work explicitly requested); Tasks 02.0–06.0 are recorded at
task level only — each is a verified, evidence-backed gap worth fixing, but
subtask decomposition is a later pass, following the same staged convention
[Milestone 0003](/docs/roadmap/0003-litellm-routing/plan.md) used.

---

## Background

Milestone 0005 closed out with a clean bill of health (ruff clean, custom
flake8 X-rules passing, 91.44% coverage, two security threat models cleared —
see [0005 status.md](/docs/roadmap/0005-harness-backends/status.md)). That
clean state is a snapshot, not a guarantee: it reflects what the *existing*
gates check, not what a lint/CI/storage audit would find if someone looked
harder. This milestone is that harder look. Every task below is grounded in
something read directly out of this repository during planning (`ruff.toml`,
`mypy.ini`, `.github/workflows/ci.yml`, `src/flake8_project_rules/rules.py`,
`src/aegis_swr/backends/storage/sqlite_store.py`) — not a generic best-practice
checklist applied blind.

---

## Tasks

| Task | Name                                              | Category       | Output                                                                                                       |
|------|----------------------------------------------------|----------------|---------------------------------------------------------------------------------------------------------------|
| 01.0 | Static Analysis Rule Expansion                    | quality        | 6 new custom Flake8 X-rules (`X013`–`X018`) + 8 native ruff rule-category additions — 14 rules total; see the task's own [README.md](01.0-static-analysis-rule-expansion/README.md) |
| 02.0 | Close the mypy Enforcement Gap                    | quality        | `mypy` CI job; a plan to retire the four disabled error codes in `mypy.ini`                                    |
| 03.0 | Storage Layer Durability & Concurrency            | optimization   | SQLite WAL mode + busy-timeout pragmas; an Alembic migration harness for the Postgres/SQLAlchemy path         |
| 04.0 | CI Supply-Chain Integrity                          | quality        | `uv sync --locked` across every workflow job; a lockfile-drift CI check                                        |
| 05.0 | Cost & Latency Telemetry for Router/Harness Events | optimization   | An opt-in metrics exporter surfacing `RouterCallCompleted` / backend `*.completed` events beyond ephemeral logs |
| 06.0 | Scheduled Documentation Health Checks              | quality        | `/doc-registry` + `/link-check` wired into the existing weekly cron cadence (mirrors `/dep-audit`)             |

Tasks are independent of each other — none blocks another — so they can be
picked up in any order. 01.0 is recommended first since it was the explicit
ask and is the only one with atomic, immediately-implementable subtasks.

---

## Task 01.0 — Static Analysis Rule Expansion

**Fully decomposed.** See
[01.0-static-analysis-rule-expansion/README.md](01.0-static-analysis-rule-expansion/README.md)
for the task scope, the design principle behind the custom-vs-native split,
and the 14-subtask table (one subtask per rule).

**Why 14 rules split across two mechanisms, not 14 custom `X`-codes.**
`docs/dev/python_language_rules.md` §1.4 states the project's own standing
rule: *"Do not use Flake8 to re-implement checks ruff already performs — that
just produces duplicate or conflicting diagnostics."* Cross-checking each
originally-brainstormed rule against ruff's native plugin catalogue (bandit
`S`, flake8-print `T20`, flake8-future-annotations `FA`, flake8-datetimez
`DTZ`, pylint `PLR`/`C90`) showed most of the "obviously useful" quality
rules already exist as flags ruff can enable with zero custom code — they are
simply not turned on in this repository's `ruff.toml` yet. Writing bespoke AST
checks for those would be redundant tooling this project's own standard
explicitly forbids. The 14 rules below are honestly split:

- **6 new custom `X013`–`X018` rules** in `src/flake8_project_rules/rules.py`
  — genuinely project-specific checks (this repo's settings/env convention,
  its timeout mandate, its TODO format, its sensitive-logging invariant) that
  no ruff plugin can express, because they require knowledge of *this*
  codebase's own architecture, not generic Python hygiene.
- **8 ruff-native rule-category additions** to `ruff.toml`'s `[lint] select`
  — configuration-only, no new code, delivered as subtasks so each gets its
  own rollout plan (a newly-enabled category can surface a backlog of
  pre-existing violations that need triage, exactly as `SIM102`/`SIM108` were
  onboarded one code at a time rather than the whole `SIM` category at once).

## Task 02.0 — Close the mypy Enforcement Gap

**Verified gap.** `mypy.ini` exists, sets `strict = true`, and
`docs/dev/python_language_rules.md` §1.4 lists `mypy` as one of three tools
"every project must run… in CI; do not merge a change that introduces a new
mypy error." In practice: `.github/workflows/ci.yml` has no `mypy` step at
all (only `ruff check` in the `lint` job), and `mypy.ini` itself disables four
error codes (`no-untyped-def`, `no-untyped-call`, `arg-type`, `type-arg`) that
`strict = true` would otherwise enable — so even a local `mypy` run is
checking a materially weaker contract than the config's headline setting
implies. `.claude/CLAUDE.md`'s own "Unconditional after every task" gate (§4)
never invokes `mypy` either.

Proposed shape once decomposed: (a) add a `mypy` CI job scoped to
`src/aegis_swr/` running against the *current* `mypy.ini` so it starts green
on day one; (b) baseline the error count that appears when each of the four
disabled codes is re-enabled one at a time; (c) burn down each baseline to
zero and drop it from `disable_error_code`, so `strict = true` becomes true
in practice, not just in the config file's name.

## Task 03.0 — Storage Layer Durability & Concurrency

**Verified gap.** `src/aegis_swr/backends/storage/sqlite_store.py` opens every
connection with `sqlite3.connect(str(self._db_path), timeout=30)` and issues
no `PRAGMA` statements at all — no `journal_mode=WAL`, no
`synchronous=NORMAL`, no `busy_timeout`. Every read/write goes through
`asyncio.to_thread`, meaning concurrent report saves and cache lookups
(`find_by_hash`, called on every orchestrator run before the cache-hit check)
already compete for the connection under SQLite's default rollback-journal
locking, which serializes writers against readers more aggressively than WAL
does. Separately, `../../CLAUDE.md` and `pyproject.toml` both name
`asyncpg`/SQLAlchemy as the Postgres-backed storage path, but no
`alembic/` (or any other migrations) directory exists anywhere in the
repository — schema evolution for that path currently has no framework at
all, forcing any future column/index change onto ad-hoc manual SQL.

Proposed shape once decomposed: (a) set `journal_mode=WAL`,
`synchronous=NORMAL`, and an explicit `busy_timeout` on every SQLite
connection, with a regression test asserting the pragma took effect; (b)
stand up an Alembic environment against the existing SQLAlchemy models for
the Postgres path, with an initial migration matching the current schema
exactly (a no-op in effect, a foundation in practice).

## Task 04.0 — CI Supply-Chain Integrity

**Verified gap.** `uv.lock` is committed, but every `uv sync` invocation
across both workflow files (`.github/workflows/ci.yml`,
`.github/workflows/coverage.yml` — eight call sites total) runs unlocked. If
`pyproject.toml` and `uv.lock` ever drift (a manual edit to one without
re-running `uv lock`), CI silently resolves whatever satisfies the drifted
`pyproject.toml` instead of failing loudly — the exact opposite of the
reproducible-build guarantee a committed lockfile exists to provide.

Proposed shape once decomposed: switch every `uv sync` call to
`uv sync --locked` (fails instead of silently re-resolving on drift), and add
a dedicated fast-failing CI step that runs first in the `lint` job so a
drifted lockfile is reported once, clearly, rather than as a confusing
downstream dependency-resolution difference in some other job.

## Task 05.0 — Cost & Latency Telemetry for Router/Harness Events

**Proposal, not a verified defect.** Milestone 0003's `RouterCallCompleted`
and each harness backend's `*.completed` event (Milestone 0005 C10) already
carry token/cost/latency figures, but today they are only ever emitted onto
the in-process `EventBus` for the live UI and, at most, logged. There is no
place an operator can go after the fact to see "cost per incident over the
last 30 days" or "which backend family is slowest under load" without
grepping structured logs. This is an optimization opportunity, not a bug: the
data already exists at the event-emission boundary, it just isn't persisted
anywhere queryable.

Proposed shape once decomposed: an opt-in metrics sink (e.g. a
Prometheus textfile exporter or a StatsD client) subscribed to the same
`EventBus`, gated behind its own presence-signal env var following the C2
selection convention Milestone 0005 established, with a `docs/runbooks/`
entry for the on-call dashboard this unlocks.

## Task 06.0 — Scheduled Documentation Health Checks

**Verified gap.** `/doc-registry`, `/doc-xref`, and `/link-check` all exist
as user-invoked skills (`.claude/`), and `.claude/CLAUDE.md` §12 already
documents a weekly cron cadence for `/dep-audit`. No equivalent cadence
exists for the doc-health skills — they only run when someone remembers to
type the slash command, typically right after a large restructuring (as with
this very milestone's own files). `docs/` has grown past 280 files
([0005 status.md](/docs/roadmap/0005-harness-backends/status.md) reports
283 at that milestone's close) with an absolute-link convention
(`docs/roadmap/README.md`) that a missed rename can silently break.

Proposed shape once decomposed: add a scheduled cron entry (mirroring
`/dep-audit`'s) that runs `/doc-registry` then `/link-check`, opening an issue
(or posting to the docs channel) only when either finds a problem — quiet
when clean, loud when not.

---

## Global acceptance criteria

- [ ] All 6 new custom X-rules (`X013`–`X018`) pass their dedicated samples in
      `tests/flake8_lint/samples/` and the whole-project scan in
      `tests/flake8_lint/test_project_lint.py`, with zero new suppressions
      needed outside the documented exclusion lists.
- [ ] All 8 newly-enabled ruff categories are clean across `src/` and `tests/`
      (either the codebase was already clean, or violations were fixed —
      never suppressed wholesale via a blanket `ignore`).
- [ ] `ruff.toml`, `pyproject.toml` (`[tool.flake8_lint_tests]`), and
      `tests/flake8_lint/config.py`'s `KNOWN_RULE_CODES` stay in sync with the
      new rule set.
- [ ] No task in this milestone touches `code_intel/`, `harness/`, or any
      backend's `CodeIntelBackend` contract — this is a tooling/infrastructure
      milestone, not a product-behavior change.
- [ ] Every claim of "verified gap" above remains true at the time each task
      is actually decomposed (re-check `ci.yml`, `mypy.ini`, and
      `sqlite_store.py` before writing that task's subtasks — this plan's
      evidence has a shelf life).
