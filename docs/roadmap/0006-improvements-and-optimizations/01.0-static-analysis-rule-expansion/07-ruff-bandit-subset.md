# 07 — `S101`/`S102`/`S307`: Bandit subset (assert / exec / eval)

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none
**Mechanism:** `ruff.toml` config only — no code in `flake8_project_rules`.

## Objective

Enable three `flake8-bandit` codes ruff already implements natively:

- **`S101`** (`assert-used`) — flags a bare `assert` statement outside
  `tests/`. `docs/dev/python_language_rules.md` §4.4 already states asserts
  "must not be critical to the application logic" and are expected in
  pytest-based tests only; `S101` mechanizes exactly that split.
- **`S102`** (`exec-builtin`) — flags `exec(...)`.
- **`S307`** (`suspicious-eval-usage`) — flags `eval(...)`.

Both `exec`/`eval` are a direct risk for a codebase whose defining property
is that "every incident payload is attacker-influenced" (`.claude/CLAUDE.md`
§1) — untrusted dump/log text must never reach a code-execution sink.

## Config change

```toml
[lint]
select = [
    "E", "F", "I", "B", "SIM102", "SIM108", "C4", "UP017", "UP037",
    "S101", "S102", "S307",
]

[lint.per-file-ignores]
"tests/**" = ["S101"]
```

`S102`/`S307` are **not** ignored in `tests/` — there is no legitimate reason
for a test to call `exec`/`eval` either, and `assert` is the one exception
tests get because it is pytest's own assertion mechanism (§4.4).

## Rollout

1. Run `uv run ruff check --select S101,S102,S307 src/ tests/` before adding
   the codes to `select`, to baseline existing hits.
2. Fix every `src/` hit for `S102`/`S307` (expected to be zero or near-zero —
   this codebase has no legitimate `exec`/`eval` use case named anywhere in
   its docs).
3. For `S101` hits in `src/`, either the `assert` genuinely was decorative
   (safe to delete, per §4.4's litmus test: "could be removed without
   breaking the code") or it was load-bearing (convert to an explicit
   `if not cond: raise ValueError(...)`, per the same section's worked
   example).
4. Land the `select` addition and the `per-file-ignores` entry together with
   the fixes, in one PR — never land the `select` addition first with a
   temporary blanket ignore "to fix later."
