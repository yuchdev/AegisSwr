# 02 - `test_config.py`

**Parent task:** 07.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** 01 (fixtures — none strictly required here, but co-located),
01.0 subtask 01 (`OpenClaudeSettings` + `OpenClaudeConfigError`), 01.0 subtask
03 (`RouterConfig.enabled_when`).
**Blocks:** none

## Objective

Verify the OpenClaude configuration surface: `OpenClaudeSettings` parses valid
input and applies documented defaults, rejects every malformed field with
`OpenClaudeConfigError`, and `RouterConfig.from_yaml()` honours the new
`enabled_when` gate so the `openclaude_agent` role is omitted when
`OPENCLAUDE_GRPC_URL` is absent and included when it is set. These are the
acceptance tests named in Task 01.0 subtasks 01 and 03; they run entirely
in-process with no network and no OpenClaude binary.

## File: `tests/openclaude/unit/test_config.py`

```python
from __future__ import annotations

import pytest

from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.exceptions import OpenClaudeConfigError
from aegis.router.config import RouterConfig


# --- OpenClaudeSettings: valid parse + defaults -----------------------------

def test_defaults_when_no_env_vars(monkeypatch) -> None:
    """No env vars set → grpc_url is None and all C1 defaults apply, no raise.

    (monkeypatch clears the OPENCLAUDE_* env, not any module global — this is
    the one legitimate env-clearing use, not a module-global patch.)
    """

def test_valid_bare_host_port_accepted() -> None:
    """grpc_url='localhost:50051' parses and round-trips unchanged."""

def test_comma_separated_allowlists_parsed_from_env(monkeypatch) -> None:
    """OPENCLAUDE_ALLOWED_TOOLS='Read,Grep' → allowed_tools == ['Read','Grep']."""


# --- OpenClaudeSettings: invalid input raises OpenClaudeConfigError ----------

def test_scheme_prefixed_grpc_url_raises() -> None:
    """grpc_url='https://bad' raises OpenClaudeConfigError(field='grpc_url')."""

def test_http_scheme_grpc_url_raises() -> None:
    """grpc_url='http://host:1' is rejected — the URL field carries no scheme."""

def test_unknown_allowed_tool_raises() -> None:
    """allowed_tools=['Read','WriteFile'] raises — 'WriteFile' is not canonical."""

def test_write_capable_tool_warns_but_does_not_raise(caplog) -> None:
    """allowed_tools=['Read','Write'] parses but logs a read-only-compromise warning."""

def test_max_tokens_below_range_raises() -> None:
    """max_response_tokens=100 (< 256) raises OpenClaudeConfigError."""

def test_max_tokens_above_range_raises() -> None:
    """max_response_tokens=70000 (> 65536) raises OpenClaudeConfigError."""

def test_request_timeout_not_greater_than_connect_raises() -> None:
    """connect_timeout_s=100, request_timeout_s=10 raises (must be strictly greater)."""


# --- RouterConfig.enabled_when gate -----------------------------------------

def test_enabled_when_absent_env_omits_role(monkeypatch, tmp_path) -> None:
    """OPENCLAUDE_GRPC_URL unset → 'openclaude_agent' absent from RouterConfig.agents, no raise."""

def test_enabled_when_present_env_includes_role(monkeypatch, tmp_path) -> None:
    """OPENCLAUDE_GRPC_URL set → 'openclaude_agent' present in RouterConfig.agents."""

def test_role_without_enabled_when_always_included(monkeypatch, tmp_path) -> None:
    """A role lacking enabled_when is parsed identically regardless of env (no regression)."""
```

## Test cases

| Test | Contract verified |
|------|-------------------|
| `test_defaults_when_no_env_vars` | C1 defaults: `grpc_url=None`, `allowed_tools=[Read,Grep,Glob,Bash]`, `bash_allowlist=[gtags,global,semgrep,rg,find,cat]`, `max_response_tokens=4096`, `connect_timeout_s=10`, `request_timeout_s=120`, `auto_start=False`, `process_binary` default; no raise |
| `test_valid_bare_host_port_accepted` | `grpc_url` regex `^[A-Za-z0-9.\-]+(:[0-9]+)?$` accepts bare host:port (01.0/01 criterion) |
| `test_comma_separated_allowlists_parsed_from_env` | Pydantic Settings comma-split of `list[str]` fields from env |
| `test_scheme_prefixed_grpc_url_raises` | `https://` prefix rejected → `OpenClaudeConfigError(field='grpc_url')` |
| `test_http_scheme_grpc_url_raises` | `http://` prefix likewise rejected |
| `test_unknown_allowed_tool_raises` | unknown Claude Code tool name → `OpenClaudeConfigError(field='allowed_tools')` |
| `test_write_capable_tool_warns_but_does_not_raise` | `Write`/`Edit` allowed by validator but emit `logger.warning`; no raise |
| `test_max_tokens_below_range_raises` | `max_response_tokens` lower bound 256 enforced |
| `test_max_tokens_above_range_raises` | upper bound 65536 enforced |
| `test_request_timeout_not_greater_than_connect_raises` | `request_timeout_s > connect_timeout_s` cross-field validation |
| `test_enabled_when_absent_env_omits_role` | 01.0/03: role silently omitted from `RouterConfig.agents`, no `ConfigValidationError` |
| `test_enabled_when_present_env_includes_role` | 01.0/03: role included with `provider="openclaude"` when `OPENCLAUDE_GRPC_URL` set |
| `test_role_without_enabled_when_always_included` | additive `enabled_when` field does not alter the parse path for other roles |

## Constraints

- All tests pass with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude binary on
  `PATH`. `monkeypatch` here is used **only** to set/clear real environment
  variables that Pydantic Settings and `from_yaml()` read — never to patch a
  module-level global or a class attribute.
- Assert on `OpenClaudeConfigError` (the canonical Task 05.0 type) — not
  Pydantic's `ValidationError` — since 01.0 raises the project error, and 05.0
  keeps the import path stable.
- The `enabled_when` tests write a minimal `agents.yaml` (one plain role + the
  `openclaude_agent` role with `enabled_when: OPENCLAUDE_GRPC_URL`) into
  `tmp_path` and call `RouterConfig.from_yaml(that_path)`; no network.
- `Optional[T]` from `typing`; `from __future__ import annotations` (C9).

## Success criteria

- [ ] All 13 test functions present and passing.
- [ ] Each invalid-input test asserts `OpenClaudeConfigError` is raised (and,
      where applicable, `exc.field` names the offending field).
- [ ] `test_write_capable_tool_warns_but_does_not_raise` asserts a warning
      record exists AND that no exception was raised.
- [ ] `test_enabled_when_absent_env_omits_role` asserts
      `'openclaude_agent' not in cfg.agents` and that `from_yaml` did not raise.
- [ ] `test_enabled_when_present_env_includes_role` asserts the role is present
      with `provider == "openclaude"`.
- [ ] No `grpc` / `_pb2` import in this file.
- [ ] `ruff`, `replace_optional.py --check` clean.
