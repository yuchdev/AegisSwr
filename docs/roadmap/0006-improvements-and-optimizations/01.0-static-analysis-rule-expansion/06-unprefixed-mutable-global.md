# 06 — `X018`: Unprefixed mutable module-level global

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none (Group A subtasks are mutually independent)
**Blocks:** none

## Objective

Flag a module-level assignment of a mutable literal (`list`, `dict`, `set`,
or a call to `list()`/`dict()`/`set()`) to a name that is **not**
underscore-prefixed. `docs/dev/python_language_rules.md` §5.4 states the
convention directly: *"mutable global entities should be declared at the
module level or as a class attribute and made internal by prepending an `_`
to the name."* Ruff's `B006`/`B008` catch mutable *default arguments*, which
is a different bug class (a different default object shared across calls) —
neither ruff nor any commonly-enabled plugin encodes this *naming*
convention for module-level state, so it stays a custom rule.

## Detection logic

Walk direct children of `ast.Module.body` (module-level statements only —
this rule is not about class attributes or function locals) for `ast.Assign`
or `ast.AnnAssign` where:

- the target is a single `ast.Name` (skip tuple/starred unpacking — rare at
  module level and not worth the complexity here), and
- the target name does **not** start with `_`, and
- the target name is not all-uppercase (an all-caps name is the project's
  own constant convention, §5.4's `SIR_LANCELOTS_FAVORITE_COLOR` example —
  constants are expected to be public and are exempted even when their value
  happens to be a literal `list`/`dict`, since a constant used as an
  immutable-in-practice lookup table is a different, accepted pattern from
  genuine mutable global state), and
- the assigned value is a `list`/`dict`/`set` literal (`ast.List`,
  `ast.Dict`, `ast.Set`) or a call to the builtin `list`/`dict`/`set`.

## Message

```
X018 Module-level mutable global `{name}` is not underscore-prefixed; either
prefix it (`_{name}`) to mark it internal, or, if it's meant to be immutable,
use an ALL_CAPS constant name and a `tuple`/`frozenset`/`MappingProxyType`
instead (docs/dev/python_language_rules.md §5).
```

## Examples

No (flagged):

```python
active_sessions = {}

def register(session_id: str) -> None:
    active_sessions[session_id] = time.monotonic()
```

Yes:

```python
_active_sessions: dict[str, float] = {}

def register(session_id: str) -> None:
    _active_sessions[session_id] = time.monotonic()
```

Yes (constant, exempted by the ALL_CAPS carve-out):

```python
DEFAULT_ALLOWED_TOOLS = ["Read", "Grep", "Glob"]
```

## Exclusions

- `tests/` — module-level fixture containers in test files are common and
  low-risk; excluded via the test-module heuristic.
- `__all__` is always exempted regardless of case, since it is a language-
  level export list, not application mutable state.

## Test plan

- `tests/flake8_lint/samples/x018_unprefixed_mutable_global.py` — a
  lowercase module-level `= {}` and a lowercase `= []`.
- A companion clean sample with the underscore-prefixed form and an
  ALL_CAPS constant list, proving both carve-outs work.
- `tests/flake8_lint/test_plugin_direct.py::test_x018_...`.
