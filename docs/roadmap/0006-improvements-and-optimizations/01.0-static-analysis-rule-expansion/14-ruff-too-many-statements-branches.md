# 14 — `PLR0912`/`PLR0915`: Too many branches / statements

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none
**Mechanism:** `ruff.toml` config only — no code in `flake8_project_rules`.

## Objective

Enable ruff's native pylint-derived codes, the size-based companions to
subtask 13's *shape*-based `C901`:

- **`PLR0912`** (`too-many-branches`) — counts `if`/`elif`/`for`/`while`/
  `except` branches directly (a simpler, more literal cousin of mccabe
  complexity).
- **`PLR0915`** (`too-many-statements`) — flags a function body with more
  total statements than the threshold, independent of branching — catches
  the "does everything in one long linear sequence" case `C901` alone would
  miss (a 150-line function with no branches at all has `C901` complexity of
  1, but is still a maintainability problem).

Landed together with `C901` (subtask 13) because both are pylint/mccabe
size-and-shape guards against the same underlying failure mode — a
maintenance-hostile function — from two different angles.

## Config change

```toml
[lint]
select = [
    "E", "F", "I", "B", "SIM102", "SIM108", "C4", "UP017", "UP037",
    "PLR0912", "PLR0915",
]

[lint.pylint]
max-branches = 15
max-statements = 60
```

Both thresholds are ruff's own defaults, kept as a first-pass baseline for
the same reason `C901`'s threshold starts gentle — measure before tightening.

## Rollout

1. Run `uv run ruff check --select PLR0912,PLR0915 src/ tests/` to baseline.
2. Expect overlap with subtask 13's `C901` hit list — fix both codes in the
   same function-extraction pass rather than as two separate changes to the
   same lines.
3. As with `C901`, a hit inside incident-lifecycle/consensus code
   (`core/orchestrator.py`, the multi-agent debate/skeptic path) needs an
   `incident-analyst` pass before merge (`.claude/CLAUDE.md` §7) — splitting
   a long function can change which branch a given input actually takes if
   the extraction isn't done carefully.
