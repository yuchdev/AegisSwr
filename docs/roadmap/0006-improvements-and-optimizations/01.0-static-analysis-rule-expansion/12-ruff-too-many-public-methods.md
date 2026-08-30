# 12 — `PLR0904`: Too many public methods

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none
**Mechanism:** `ruff.toml` config only — no code in `flake8_project_rules`.

## Objective

Enable ruff's native pylint-derived `PLR0904` (`too-many-public-methods`) —
a "god object" guard. This project's own Factory-Strategy convention
(`root CLAUDE.md`: "every backend type has an abstract base class, concrete
implementations, and a factory function") is specifically designed to keep
any one class's public surface small and single-purpose; a class quietly
accumulating public methods is a signal that convention is eroding, before
it becomes hard to review.

## Config change

```toml
[lint]
select = [
    "E", "F", "I", "B", "SIM102", "SIM108", "C4", "UP017", "UP037",
    "PLR0904",
]

[lint.pylint]
max-public-methods = 20
```

`max-public-methods = 20` (ruff's default) is the starting threshold; adjust
only with a named justification if the initial baseline pass shows a
legitimately-cohesive class (e.g. a Pydantic `Settings` subclass with many
`@field_validator`s, which are not really "behavior" methods in the same
sense) sitting just over the line.

## Rollout

1. Run `uv run ruff check --select PLR0904 src/ tests/` to baseline at the
   default threshold.
2. For a genuine hit, prefer splitting the class along an existing seam
   (e.g. separating validation from behavior, or extracting a helper class)
   over raising the threshold. If a `Settings`/config class is the only
   offender and its "methods" are mostly `@field_validator`s, that is the
   one case where a per-file or per-class `# noqa: PLR0904` with a one-line
   rationale is preferable to bumping the project-wide threshold.
