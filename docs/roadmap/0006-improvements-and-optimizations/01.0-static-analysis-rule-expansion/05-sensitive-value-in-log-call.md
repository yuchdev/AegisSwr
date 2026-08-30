# 05 — `X017`: Sensitive-named value in a logging or exception call

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none (Group A subtasks are mutually independent)
**Blocks:** none

## Objective

This is the flagship rule of the milestone: it encodes Aegis SWR's single
most important security invariant in mechanical form.
`.claude/CLAUDE.md` §1 states *"every incident payload is attacker-influenced
and may contain secrets or PII. Treat all of it as hostile and
confidential,"* and §3 repeats: *"Never log secrets… no unredacted
dump/log/stack text in logs, exceptions, stored reports, or API error
bodies."* Today this is enforced entirely by `SensitiveFilter` at the logging
sink and by code review — there is no static check that a variable whose
*name* screams "this is raw incident data" isn't being handed straight to a
logger or exception message. This rule is a best-effort, name-based tripwire,
not a data-flow prover — it catches the common, careless case.

## Detection logic

Maintain a configurable set of **sensitive name fragments** (case-insensitive
substring match against the variable/attribute name), seeded from this
project's own `CrashReportEntity` fields and known secret shapes
(`core/data_schema.py`): `raw_stack`, `raw_log`, `dump`, `payload`,
`secret`, `token`, `password`, `api_key`, `credential`, `oauth`.

For every `ast.Call` whose function is:

- an `ast.Attribute` with `.attr` in `{debug, info, warning, error,
  exception, critical, log}` on any object (mirrors `X009`'s
  `logging_methods` set exactly — reuse it), or
- a call to `raise` an exception constructor (handled via `ast.Raise`, not
  `ast.Call` alone, so the exception's own `args`),

inspect every argument expression (not just the first, unlike `X009`, since a
sensitive value is just as dangerous as an f-string interpolation or a
second positional arg). For each argument, walk its sub-expressions for any
`ast.Name` or `ast.Attribute` whose identifier (`.id` or `.attr`) contains a
sensitive fragment. If found, and the argument is not itself a call to an
approved redaction helper (an allowlisted wrapper name, e.g. `redact(...)`,
`redacted(...)`, or `SensitiveFilter.mask(...)` — configurable, defaulting to
an empty allowlist until Task 03's redaction helper, if any, is named), yield
`X017`.

This deliberately does not attempt inter-procedural data-flow analysis (e.g.
tracing a sensitive value through an intermediate variable rename) — that
is `bandit`/`semgrep` territory, out of scope for a single-pass AST rule. It
catches the direct case, which is also the common one.

## Message

```
X017 Argument `{name}` looks like raw incident payload or secret data based on
its name and is passed directly into a {logging call|raised exception}; wrap
it in the project's redaction helper before it reaches a log sink or
exception message (.claude/CLAUDE.md §1, §3).
```

## Examples

No (flagged):

```python
logger.error(f"analyze failed for stack: {raw_stack}")
```

```python
raise CrashAnalysisError(f"bad dump payload: {dump_bytes!r}")
```

Yes:

```python
logger.error(f"analyze failed for stack: {redact(raw_stack)}")
```

```python
logger.error("analyze failed (report_id={})", report.report_id)
```

## Exclusions

- `tests/` — fixtures constructing sensitive-looking sample data for
  assertions are exempt via the test-module heuristic; a test asserting
  *that* a value is redacted legitimately needs the raw name in scope.
- The sensitive-fragment list and the redaction-helper allowlist are both
  read from a new `[tool.flake8_lint_tests.x017]` sub-table (or a plain
  module-level constant if project-wide config plumbing is overkill for one
  rule) so the vocabulary can grow without a code change.

## Test plan

- `tests/flake8_lint/samples/x017_sensitive_log_value.py` — a `logger.error`
  call interpolating `raw_stack`, and a `raise SomeError(f"...{payload}...")`.
- A companion clean sample: the same two call shapes, wrapping the sensitive
  name in `redact(...)`, and a case where the logged variable's name does
  **not** match any sensitive fragment (proving no over-broad flagging of
  ordinary variables).
- `tests/flake8_lint/test_plugin_direct.py::test_x017_...`.
