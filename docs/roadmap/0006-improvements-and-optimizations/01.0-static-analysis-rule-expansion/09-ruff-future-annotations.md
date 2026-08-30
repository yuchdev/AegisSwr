# 09 — `FA100`/`FA102`: Future-annotations required

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none
**Mechanism:** `ruff.toml` config only — no code in `flake8_project_rules`.

## Objective

Enable ruff's native `flake8-future-annotations` codes:

- **`FA100`** — a type annotation could be simplified if
  `from __future__ import annotations` were present (i.e. it's missing where
  it would help).
- **`FA102`** — `from __future__ import annotations` is missing entirely in
  a module that uses annotations ruff's target Python version would
  otherwise need it for.

Every milestone plan in this repository's `docs/roadmap/` repeats the same
cross-cutting convention verbatim: *"`from __future__ import annotations` in
every new file"* (0003 C5, 0005 C13, and others). It has been enforced by
convention and review for five milestones; `FA100`/`FA102` make it
mechanical for every file going forward, including ones this rule set
predates.

## Config change

```toml
[lint]
select = [
    "E", "F", "I", "B", "SIM102", "SIM108", "C4", "UP017", "UP037",
    "FA100", "FA102",
]
```

No `per-file-ignores` expected — this convention has had zero named
exceptions across five milestones' worth of contracts.

## Rollout

1. Run `uv run ruff check --select FA100,FA102 src/ tests/` to baseline.
2. `uv run ruff check --select FA100,FA102 --fix src/ tests/` — both codes
   are auto-fixable (ruff inserts the missing future import), so this is
   expected to be a single mechanical pass rather than manual triage.
3. Spot-check the auto-fix diff for import-ordering conflicts with `isort`
   (`I001`) — the future import must sort to the very top of the file, above
   `__future__`-adjacent stdlib imports; ruff's fixer handles this correctly
   in the overwhelming majority of cases, but a generated `*_pb2.py` file is
   already excluded from `ruff.toml`'s `extend-exclude` and needs no action.
