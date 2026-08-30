# 13 — `C901`: Cyclomatic complexity (mccabe)

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none
**Mechanism:** `ruff.toml` config only — no code in `flake8_project_rules`.

## Objective

Enable ruff's native mccabe complexity check, `C901`
(`complex-structure`) — **not** to be confused with the already-enabled `C4`
(`flake8-comprehensions`) category; they share the `C` letter but are
unrelated rule families. A high-complexity function (many nested
`if`/`elif`/`for`/`except` branches) is exactly the shape of code most likely
to hide the bug class this codebase cares most about: an unhandled branch in
incident-lifecycle or consensus logic that silently mishandles a low-
confidence case instead of escalating it (`.claude/CLAUDE.md` §1's
`HITLRequest` escalation path exists precisely because that logic must not
have a silent fall-through).

## Config change

```toml
[lint]
select = [
    "E", "F", "I", "B", "SIM102", "SIM108", "C4", "UP017", "UP037",
    "C901",
]

[lint.mccabe]
max-complexity = 12
```

`max-complexity = 12` (above ruff's stricter default of 10) is a deliberately
gentle starting threshold given this codebase has never been measured
against it before; tighten it in a follow-up once the initial baseline is
clean, rather than picking an aggressive number that forces a large
first-pass refactor bundled into this task.

## Rollout

1. Run `uv run ruff check --select C901 src/ tests/` to baseline at
   `max-complexity = 12`.
2. Prioritize any hit inside `core/orchestrator.py`'s pipeline
   (`INITIALIZING → EXTRACTING → PARSING → ANALYZING → STORING`) or the
   multi-agent consensus/skeptic path — per the delegation map
   (`.claude/CLAUDE.md` §7), a fix there needs an `incident-analyst` pass
   before merge, same as any other change to investigation flow, since
   splitting a complex function can subtly change its branch behavior.
3. Every other hit: extract named helper functions for the branches that
   push complexity over the threshold, favoring early-return guard clauses
   over deep nesting (this is also `SIM102`'s existing spirit — collapsed
   nested `if`s reduce complexity for free).
