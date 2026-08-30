# 04 — `X016`: Malformed `# TODO` annotation

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none (Group A subtasks are mutually independent)
**Blocks:** none

## Objective

Flag a `# TODO` (or `# FIXME`) comment that does not carry an owner, a date,
and an issue reference. `docs/dev/python_language_rules.md` §21.4 already
requires this shape for the one case it names explicitly (an un-annotatable
type): *"Track it as a `TODO` with an owner, date, and issue link."* This
rule generalizes that requirement to every `TODO`/`FIXME` in the codebase, not
just the type-annotation-gap case — an untracked `TODO` is a permanent one.

This is a **text-level** check over raw source lines, following the same
approach `X009` (percent-formatting) already uses for its printf-style-format
regex — it does not need the AST at all, only `source.splitlines()`.

## Detection logic

For every physical line containing `# TODO` or `# FIXME` (case-insensitive,
optionally followed by `(...)`), require the comment to match:

```
#\s*(?:TODO|FIXME)\(([\w.\-]+),\s*(\d{4}-\d{2}-\d{2}),\s*([A-Z][A-Z0-9]*-\d+)\)\s*:\s*\S
```

i.e. `# TODO(username-or-handle, YYYY-MM-DD, PROJECTKEY-123): <non-empty
description>`. Lines matching this are clean. A bare `# TODO: fix this later`
or `# TODO(alice): investigate` (missing the date/issue parts) is flagged.

Run this as a whole-module source scan (like `_check_percent_formatting`'s
sibling text checks), independent of AST node position — attribute the
violation to the 1-indexed line number directly.

## Message

```
X016 Malformed TODO/FIXME annotation: must be
`# TODO(owner, YYYY-MM-DD, ISSUE-123): description` so it can be tracked and
triaged later, not `# TODO: <free text>`.
```

## Examples

No (flagged):

```python
# TODO: revisit this once the OpenHands sandbox lands
```

```python
# FIXME(yurii): this leaks a file handle
```

Yes:

```python
# TODO(ycherkasov, 2026-09-15, AEGIS-482): revisit once OpenHands sandbox lands
```

## Exclusions

- None by file — this convention should hold everywhere, `tests/` included,
  since an untracked `TODO` in a test file rots exactly the same way.
- `# noqa: X016` remains available for a rare pre-existing `TODO` a team
  chooses to grandfather rather than immediately re-date; new code should
  never need the suppression.

## Test plan

- `tests/flake8_lint/samples/x016_malformed_todo.py` — a bare `# TODO: ...`
  line and a `# FIXME(name)` line missing the date/issue parts.
- A companion clean sample with a fully-formed `# TODO(owner, date, ISSUE-1):
  ...` line.
- `tests/flake8_lint/test_plugin_direct.py::test_x016_...`; also verify a
  `# noqa: X016` on the malformed line suppresses it, exercising the existing
  `_is_noqa_suppressed` plumbing for a text-only (non-AST-anchored) rule.
