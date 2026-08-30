# 01 — `X013`: Direct environment access outside settings modules

**Parent task:** [01.0 Static Analysis Rule Expansion](README.md)
**State:** ⬜ Not started
**Depends on:** none (Group A subtasks are mutually independent)
**Blocks:** none

## Objective

Flag any `os.environ[...]`, `os.environ.get(...)`, or `os.getenv(...)` call
made **outside** a settings/config module. Every backend contract this
project has shipped so far (`OpenClaudeSettings`, `ClaudeCodeSettings`,
`OpenHandsSettings`, `HarnessSettings`) is built on the same convention:
*one* Pydantic `BaseSettings` class per family owns that family's env vars,
and nothing else reads `os.environ` directly. Milestone 0005's own contract
C1 states it as a hard requirement — "`HarnessSettings` … never reads
`os.environ` inside composition or tool code; each nested settings object
sources its own family's variables." Today that discipline is enforced only
by review; this rule makes it mechanical.

## Detection logic

Walk the AST for:

- `ast.Subscript` where the value is `os.environ` (i.e. `os.environ["X"]`)
  or a bare `environ["X"]` when `environ` was imported via
  `from os import environ`.
- `ast.Call` where the function is `os.environ.get`, `environ.get`, or
  `os.getenv`/`getenv`.

For each match, resolve the containing module's path (the same `filename`
`check_tree` already receives) and check it against an **allowlist** of
settings-module path patterns:

- Any path whose filename is exactly `config.py`.
- Any path matching `*_settings.py`.
- `tests/` (test fixtures legitimately construct env scenarios directly).

If the file does not match, yield `X013`. This mirrors `_is_test_module`'s
existing path-heuristic style (`rules.py:185`) — reuse that function's
"is this under `tests/`" check rather than duplicating it.

## Message

```
X013 Do not read `os.environ`/`os.getenv` directly outside a settings module
(`config.py` or `*_settings.py`); add or extend a Pydantic `BaseSettings`
field instead so the variable has one owner, one default, and one place
validation can reject a malformed value.
```

## Examples

No (flagged, in `src/aegis_swr/claude_code/tool.py`):

```python
import os

def _resolve_binary() -> str:
    return os.environ.get("CLAUDE_CODE_BINARY", "claude")
```

Yes (in `src/aegis_swr/claude_code/config.py`):

```python
class ClaudeCodeSettings(BaseSettings):
    binary_path: str = Field(default="claude", validation_alias="CLAUDE_CODE_BINARY")
```

Yes (a one-off script under `scripts/`, out of scope for this rule by design
— see Exclusions):

```python
# scripts/proto_gen.py
protoc_path = os.environ.get("PROTOC", "protoc")
```

## Exclusions

- `scripts/` is excluded via `[tool.flake8_lint_tests] exclude` (not a
  hard-coded exception in `rules.py` itself) — one-off developer tooling is
  not part of the runtime settings contract this rule protects. Add
  `"scripts/"` to the milestone's `exclude` list when this subtask lands.
- `tests/` is excluded by the existing test-module heuristic.

## Test plan

- `tests/flake8_lint/samples/x013_env_access.py` — a bare module-level
  function reading `os.environ.get(...)`; expect one `X013` at that line.
- Extend `valid_clean_module.py` (or add a sibling clean sample) with a
  `config.py`-shaped file reading `os.environ` directly, to prove the
  allowlist path match works, not just the negative case.
- `tests/flake8_lint/test_plugin_direct.py::test_x013_...` — both the flagged
  and the allowlisted case.
