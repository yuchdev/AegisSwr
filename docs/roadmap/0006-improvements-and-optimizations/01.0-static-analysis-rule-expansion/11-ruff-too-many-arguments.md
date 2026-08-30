# 11 — `PLR0913`/`PLR0917`: Too many function arguments

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none
**Mechanism:** `ruff.toml` config only — no code in `flake8_project_rules`.

## Objective

Enable ruff's native pylint-derived codes:

- **`PLR0913`** (`too-many-arguments`) — a function/method signature with
  more positional-or-keyword parameters than the configured threshold.
- **`PLR0917`** (`too-many-positional-arguments`) — the positional-only
  subset of the same complaint, useful because this codebase's settings
  classes and event dataclasses are typically constructed with keyword
  arguments (Pydantic/`dataclass`), so the positional-specific variant
  targets plain functions where argument order is easy to get wrong at the
  call site.

Every backend family this project has shipped (`OpenClaudeTool`,
`ClaudeCodeTool`, `OpenHandsTool`) constructs its settings via a single typed
object rather than a long parameter list — this rule mechanizes that
already-established convention so a future function doesn't quietly grow a
seven-parameter signature instead of taking a settings/context object.

## Config change

```toml
[lint]
select = [
    "E", "F", "I", "B", "SIM102", "SIM108", "C4", "UP017", "UP037",
    "PLR0913", "PLR0917",
]

[lint.pylint]
max-args = 6
```

`max-args = 6` (ruff's own default is 5) gives one slot of headroom for
`self`/`cls` plus five real parameters before the rule fires, matching this
codebase's observed style (most `__init__` methods sit at 4-6 parameters
once a settings object is threaded through).

## Rollout

1. Run `uv run ruff check --select PLR0913,PLR0917 src/ tests/` to baseline
   at `max-args = 6`.
2. For each hit, prefer bundling related parameters into an existing (or new)
   settings/context dataclass over just raising the threshold locally — that
   is the pattern this rule exists to encourage. Reserve
   `# noqa: PLR0913` for a genuine one-off (e.g. a test factory function)
   rather than reaching for it as the default fix.
