# 08 — `T201`/`T203`: Print-ban (flake8-print)

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none
**Mechanism:** `ruff.toml` config only — no code in `flake8_project_rules`.

## Objective

Enable `T201` (`print`) and `T203` (`p-print`), ruff's native
`flake8-print` codes. `.claude/CLAUDE.md` §2 states: *"No `print` for
diagnostics in product code."* `loguru` (with `SensitiveFilter` attached to
every sink) is the one approved diagnostic channel; a stray `print()` bypasses
that filter entirely, which is a direct risk given this project's
never-log-secrets invariant.

## Config change

```toml
[lint]
select = [
    "E", "F", "I", "B", "SIM102", "SIM108", "C4", "UP017", "UP037",
    "T201", "T203",
]

[lint.per-file-ignores]
"src/aegis_swr/cli/**" = ["T201"]   # CLI output IS stdout by design
```

## Rollout

1. Run `uv run ruff check --select T201,T203 src/ tests/` to baseline.
2. `src/aegis_swr/cli/` is the one legitimate exception — a CLI's job is to
   print to stdout for the human operator; scope the `per-file-ignores`
   entry there specifically, not project-wide.
3. Every other hit gets converted to the equivalent `loguru` call
   (`logger.debug`/`.info` as appropriate) or removed if it was leftover
   debugging output.
4. `tests/` is deliberately **not** exempted — pytest's own output capture
   makes stray `print()` in tests noisy without being useful; prefer
   `caplog`/assertions over printf-debugging even there.
