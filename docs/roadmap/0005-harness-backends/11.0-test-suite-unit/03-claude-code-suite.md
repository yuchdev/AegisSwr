# 03 - `tests/unit/claude_code/` suite

**Parent task:** 11.0 Test Suite — Unit
**State:** ✅ Complete
**Depends on:** 01 (shared fixtures — `mock_claude_subprocess`, `mock_event_bus`,
`ample_budget`, `dry_run_ctx`, `live_ctx`), 02.0 (`ClaudeCodeSettings`,
`ClaudeCodeConfigError`), 03.0 (`ClaudeCodeTool.delegate()`, `process.py`
argv/env helper, NDJSON parse, real token accounting), 04.0 (`auth_mode` field,
auth-probe, `ClaudeCodeUnavailableError`), 05.0 (`claude_code.*` events).
**Blocks:** none

## Objective

Verify the Claude Code backend end to end at the unit level with a fully injected
fake one-shot subprocess — no real `claude` process ever spawns. Cover the C5/C6
settings surface (including the `--dangerously-skip-permissions` rejection), the
**argv-safety invariant** (task text never in argv; C6), **100% branch coverage on
`delegate()`** (mirroring 0004's `tool.py` gate) with real token accounting (C9),
the **full C7 auth-mode matrix** (with the no-secret-in-logs guarantee), the
`claude_code.*` event taxonomy (C10), and the import-isolation posture (C3).

## File: `tests/unit/claude_code/test_config.py`

```python
from __future__ import annotations

import pytest

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.exceptions import ClaudeCodeConfigError


def test_defaults_when_no_env_vars(monkeypatch):
    """No env → enabled=False (presence signal off), allowed_tools=[Read,Grep,Glob], non-bypassing permission_mode; no raise (C5/C6)."""

def test_enabled_true_from_env(monkeypatch):
    """CLAUDE_CODE_ENABLED=true → enabled is True (the presence signal)."""

def test_read_only_allowlist_default_is_read_only():
    """Default allowed_tools contains no write-capable tool (C6)."""

def test_write_capable_tool_warns_but_does_not_raise(caplog):
    """allowed_tools including Write parses but logs a read-only-compromise warning (mirrors OpenClaude)."""

def test_dangerously_skip_permissions_rejected():
    """A permission_mode / value that would emit --dangerously-skip-permissions → ClaudeCodeConfigError (C6)."""

def test_bypass_permission_mode_rejected():
    """Any bypass-permissions permission_mode value is rejected at validation (C6)."""

def test_scratch_cwd_is_mandatory():
    """A missing/empty scratch_cwd → ClaudeCodeConfigError (mandatory disposable cwd, C6)."""

def test_comma_separated_allowed_tools_parsed_from_env(monkeypatch):
    """CLAUDE_CODE_ALLOWED_TOOLS='Read,Grep' → ['Read','Grep'] (CSV env parse, C5)."""
```

## File: `tests/unit/claude_code/test_process.py`

```python
from __future__ import annotations

import pytest

from aegis_swr.claude_code.process import build_claude_argv  # argv/env helper (C6)


DISTINCTIVE_TASK = (
    "Explain crash in mod.dll; secret=hunter2 & `rm -rf /` \"quoted\" $VAR\n"
    "second line with unicode ☠ and --allowedTools=Write"
)


def test_task_text_never_in_argv():
    """The task string (and distinctive substrings) NEVER appears in the constructed argv (C6)."""

def test_argv_uses_p_and_stream_json():
    """argv carries `-p` and `--output-format stream-json` (the one-shot headless invocation, C6)."""

def test_task_text_travels_via_stdin(mock_claude_subprocess):
    """The task text is written to stdin (recorded on RecordingClaudeProcess.stdin_text), never argv (C6)."""

def test_allowed_tools_rendered_into_argv():
    """settings.allowed_tools → --allowedTools flag in argv (read-only guard surfaced)."""

def test_scratch_cwd_used_as_process_cwd():
    """The disposable scratch_cwd is passed as the subprocess cwd (C6)."""

def test_ndjson_result_message_yields_real_usage(mock_claude_subprocess):
    """A terminal `result` message's usage.input_tokens+output_tokens is parsed as the token figure (C9)."""
```

## File: `tests/unit/claude_code/test_tool.py` (100% branch required)

```python
from __future__ import annotations

import pytest

from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.claude_code.exceptions import (
    ClaudeCodeUnavailableError,
    ClaudeCodePermissionDeniedError,
)
from aegis_swr.claude_code.events import (
    ClaudeCodeToolCall,
    ClaudeCodeToolResult,
    ClaudeCodePermissionDenied,
    ClaudeCodeStreamCompleted,
    ClaudeCodeStreamError,
)
from aegis_swr.code_intel.budget import CallBudget


# --- 1. Happy path ----------------------------------------------------------

async def test_delegate_success_returns_text_and_real_tokens(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, ample_budget, live_ctx,
):
    """text messages + terminal result → CodeResult.text concatenated; token_estimate == real usage sum (C9)."""


# --- 2. Budget pre-check short-circuit --------------------------------------

async def test_delegate_budget_insufficient_short_circuits(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, live_ctx,
):
    """CallBudget(0) < pre-check → non-retriable failure, NO subprocess spawned."""


# --- 3. Dry-run short-circuit -----------------------------------------------

async def test_delegate_dry_run_short_circuits(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, ample_budget, dry_run_ctx,
):
    """ctx.dry_run → '[dry-run]' result, zero tokens, NO subprocess spawned (C6/C13)."""


# --- 4. Tool-call / tool-result dispatch ------------------------------------

async def test_delegate_tool_call_message_emits_event(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, ample_budget, live_ctx,
):
    """A tool_use message emits ClaudeCodeToolCall and increments the tool-call count (C10)."""

async def test_delegate_tool_result_message_emits_event(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, ample_budget, live_ctx,
):
    """A tool_result message emits ClaudeCodeToolResult (C10)."""


# --- 5. Permission-denied branch --------------------------------------------

async def test_delegate_permission_denied_non_retriable(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, ample_budget, live_ctx,
):
    """A permission-denied message → ClaudeCodePermissionDenied emitted, non-retriable failure."""


# --- 6. Non-zero exit / stream error ----------------------------------------

async def test_delegate_nonzero_exit_returns_failure(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, ample_budget, live_ctx,
):
    """Non-zero exit / error result message → ClaudeCodeStreamError, failure CodeResult (no exception escapes)."""

async def test_delegate_malformed_ndjson_returns_failure(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, ample_budget, live_ctx,
):
    """Unparseable NDJSON line → handled failure result, not an unhandled exception."""


# --- 7. Timeout / unavailable -----------------------------------------------

async def test_delegate_timeout_returns_retriable_failure(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, ample_budget, live_ctx,
):
    """Subprocess timeout → retriable failure CodeResult + ClaudeCodeStreamError."""


# --- 8. Budget charged after completion, real usage -------------------------

async def test_budget_charged_real_usage_after_completion(
    claude_code_settings_enabled, mock_event_bus, mock_claude_subprocess, live_ctx,
):
    """Budget charged the REAL usage sum AFTER the result message, never pre-charged (C9)."""
```

## File: `tests/unit/claude_code/test_auth_modes.py` (C7 matrix)

```python
from __future__ import annotations

import pytest

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.exceptions import (
    ClaudeCodeConfigError,
    ClaudeCodeUnavailableError,
)


# --- subscription mode: ambiguous-credential rejection (construction time) --

def test_subscription_mode_rejects_when_anthropic_api_key_present(monkeypatch):
    """auth_mode=subscription + ANTHROPIC_API_KEY set → ClaudeCodeConfigError at construction (C7)."""

def test_subscription_mode_rejects_when_anthropic_auth_token_present(monkeypatch):
    """auth_mode=subscription + ANTHROPIC_AUTH_TOKEN set → ClaudeCodeConfigError at construction (C7)."""

def test_subscription_mode_constructs_clean_when_no_api_key(monkeypatch):
    """auth_mode=subscription + neither key present → settings construct without error (C7)."""


# --- subscription mode: --bare exclusion ------------------------------------

def test_subscription_mode_never_passes_bare(monkeypatch, mock_claude_subprocess):
    """In subscription mode --bare is NEVER in argv (bare mode ignores OAuth/login, C7)."""


# --- subscription mode: CLAUDE_CODE_OAUTH_TOKEN precedence -------------------

def test_subscription_mode_uses_oauth_token_when_set(monkeypatch, mock_claude_subprocess):
    """CLAUDE_CODE_OAUTH_TOKEN set → used as the CI-friendly credential (C7)."""

def test_subscription_mode_falls_back_to_stored_login_probe(monkeypatch):
    """No OAUTH token → the startup auth-probe verifies a stored `claude login` session before first delegate (C7)."""

def test_subscription_mode_probe_failure_raises_unavailable(monkeypatch):
    """A failing auth-probe → ClaudeCodeUnavailableError (runtime capability), distinct from ClaudeCodeConfigError (C7)."""


# --- api_key mode -----------------------------------------------------------

def test_api_key_mode_may_pass_bare(monkeypatch, mock_claude_subprocess):
    """auth_mode=api_key → --bare MAY be added for reproducibility (C7)."""


# --- auto mode (default) ----------------------------------------------------

def test_auto_mode_adds_no_extra_validation(monkeypatch):
    """auth_mode=auto (default) + ANTHROPIC_API_KEY present → no rejection; Task 03.0 behaviour unchanged (C7)."""

def test_auto_is_the_default_mode(monkeypatch):
    """auth_mode defaults to 'auto' when CLAUDE_CODE_AUTH_MODE is unset (C7)."""


# --- Secrecy across every auth path -----------------------------------------

@pytest.mark.parametrize(
    "credential_var",
    ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"],
)
def test_no_credential_value_in_logs_or_exceptions(monkeypatch, caplog, credential_var):
    """No OAuth token / credential-file content / API-key VALUE ever appears in a log record, exception message, or auth_failed event payload (C7/C13)."""
```

## File: `tests/unit/claude_code/test_events.py`

```python
from __future__ import annotations

import dataclasses

import pytest

from aegis_swr.claude_code.events import (
    ClaudeCodeSpawned,
    ClaudeCodeExited,
    ClaudeCodeToolCall,
    ClaudeCodeToolResult,
    ClaudeCodePermissionDenied,
    ClaudeCodeAuthFailed,
    ClaudeCodeStreamCompleted,
    ClaudeCodeStreamError,
)

ALL_EVENT_TYPES = [
    ClaudeCodeSpawned,
    ClaudeCodeExited,
    ClaudeCodeToolCall,
    ClaudeCodeToolResult,
    ClaudeCodePermissionDenied,
    ClaudeCodeAuthFailed,
    ClaudeCodeStreamCompleted,
    ClaudeCodeStreamError,
]


@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_instantiates(cls):
    """Each claude_code.* event constructs (keyword-only) and subclasses DomainEvent (C10)."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_is_frozen(cls):
    """Mutating any field raises FrozenInstanceError (frozen=True, C10)."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_carries_run_id_timestamp_event_type(cls):
    """Each carries run_id, a UTC timestamp, and a ClassVar[str] event_type sentinel (C10)."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_type_sentinel_matches_c10(cls):
    """event_type equals the exact C10 string ('claude_code.spawned', …, '.auth_failed')."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_round_trips_through_bus(cls, mock_event_bus):
    """Emitting the event puts exactly that instance on mock_event_bus.captured (C10)."""

def test_only_stream_completed_carries_token_estimate():
    """ClaudeCodeStreamCompleted is the ONLY event carrying token_estimate (C10 non-duplication)."""

def test_auth_failed_carries_reason_no_credential():
    """ClaudeCodeAuthFailed carries only a reason enum ('ambiguous_credential' / 'no_stored_login' / 'token_rejected') — never a credential value (C7/C10)."""

def test_no_event_has_any_typed_field():
    """No event field is annotated Any and none carries raw payload/response/credential text (C13)."""
```

## File: `tests/unit/claude_code/test_isolation.py`

```python
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "aegis_swr" / "claude_code"
SIBLINGS = {"openclaude", "openhands"}


def test_claude_code_imports_no_sibling_backend():
    """No file under aegis_swr/claude_code imports aegis_swr.openclaude or aegis_swr.openhands (C3, AST-based)."""

def test_claude_code_imports_no_grpc_or_openhands_client():
    """claude_code imports neither grpc/_pb2 nor the OpenHands client library (C3)."""
```

## Test cases (selected — branch map for `delegate()`)

| Test                                                            | Branch / contract verified                                                    |
|-----------------------------------------------------------------|-------------------------------------------------------------------------------|
| `test_delegate_success_returns_text_and_real_tokens`            | happy path; `token_estimate` == real `usage` sum (C9)                         |
| `test_delegate_budget_insufficient_short_circuits`              | budget pre-check false branch; NO subprocess spawned                          |
| `test_delegate_dry_run_short_circuits`                          | dry-run branch; `[dry-run]`, zero tokens, NO subprocess                       |
| `test_delegate_tool_call_message_emits_event`                   | `tool_use` dispatch arm → `ClaudeCodeToolCall`                                |
| `test_delegate_tool_result_message_emits_event`                 | `tool_result` dispatch arm → `ClaudeCodeToolResult`                           |
| `test_delegate_permission_denied_non_retriable`                 | permission-denied arm → `ClaudeCodePermissionDenied`, non-retriable           |
| `test_delegate_nonzero_exit_returns_failure`                    | non-zero exit / error arm → `ClaudeCodeStreamError`, failure result           |
| `test_delegate_malformed_ndjson_returns_failure`                | parse-error arm → handled failure, no exception escapes                       |
| `test_delegate_timeout_returns_retriable_failure`               | timeout arm → retriable failure                                               |
| `test_budget_charged_real_usage_after_completion`               | budget charged real usage **after** completion, never pre-charged (C9)        |
| `test_task_text_never_in_argv`                                  | **C6 argv-safety**: task text (and distinctive substrings) absent from argv   |
| `test_task_text_travels_via_stdin`                              | C6: task text on stdin, not argv                                              |
| `test_subscription_mode_rejects_when_anthropic_api_key_present` | C7: ambiguous-credential rejection at construction                            |
| `test_subscription_mode_never_passes_bare`                      | C7: `--bare` excluded in subscription mode                                    |
| `test_subscription_mode_uses_oauth_token_when_set`              | C7: `CLAUDE_CODE_OAUTH_TOKEN` precedence                                      |
| `test_subscription_mode_probe_failure_raises_unavailable`       | C7: probe failure → `ClaudeCodeUnavailableError` (distinct from config error) |
| `test_auto_mode_adds_no_extra_validation`                       | C7: `auto` unchanged from Task 03.0                                           |
| `test_no_credential_value_in_logs_or_exceptions`                | C7/C13: no credential value in any log / exception / event                    |

## Implementation notes

- `test_process.py` uses one **distinctive** task string containing shell
  metacharacters, quotes, a fake `secret=`, a newline, Unicode, and a flag-like
  substring (`--allowedTools=Write`). The argv-safety assertion checks the whole
  string **and** each distinctive substring is absent from every argv element,
  and present in `RecordingClaudeProcess.stdin_text`.
- **100% branch coverage on `claude_code/tool.py::delegate()`** is enforced
  `--cov=aegis_swr.claude_code.tool --cov-branch --cov-fail-under=100` scoped in
  task 13.0 — every dispatch arm, both budget-check sides, dry-run, and every
  error class must be hit. `delegate()` must never let an exception escape; each
  error path returns a `CodeResult` with the correct `retriable` flag.
- The C7 secrecy test sets a sentinel credential value (e.g.
  `"SENTINEL-DO-NOT-LOG"`) in each credential var, exercises the auth-resolution
  path, and asserts that literal never appears in `caplog.text`, in any raised
  exception's `str()`, or in any captured `ClaudeCodeAuthFailed` event payload.
- `test_isolation.py` reuses the AST helper pattern from the harness suite
  (subtask 02); it may import that helper rather than duplicate it.
- Model the auth-probe tests on 04.0's actual probe seam — inject the probe
  result, do not run a real `claude` invocation.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new unit test has a test-specific docstring (`[Unit]`|`[Mock]`|`[Integration]`|`E2E` / `Scenario` / `Boundaries` / `On failuse`)
- All tests pass with `CLAUDE_CODE_ENABLED` unset and no `claude` binary on `PATH` — no real subprocess is ever spawned (the fake process comes from `mock_claude_subprocess`).
- Every collaborator is constructor-injected; `monkeypatch` is used **only** for real env vars (`CLAUDE_CODE_*`, `ANTHROPIC_*`, `CLAUDE_CODE_OAUTH_TOKEN`).
- Assert on the canonical `ClaudeCodeConfigError` / `ClaudeCodeUnavailableError` types, not Pydantic `ValidationError`; keep the config-shape vs. runtime-capability distinction (C7) crisp in every auth test.
- No credential value, argv secret, or raw response text is asserted against a log sink; the secrecy test proves the negative (C7/C13).
- `test_isolation.py` is AST-based (docstring mentions must not trip it).

## Success criteria

- [ ] `test_config.py`: `--dangerously-skip-permissions` / bypass permission modes and a missing `scratch_cwd` each raise `ClaudeCodeConfigError`.
- [ ] `test_process.py`: the distinctive task string and each distinctive substring are **absent from every argv element** and present in `stdin_text`; argv carries `-p --output-format stream-json`.
- [ ] `test_tool.py`: `pytest --cov=aegis_swr.claude_code.tool --cov-branch` reports **100%** branch on `delegate()`; budget/dry-run paths spawn no subprocess; `token_estimate` equals the real `usage` sum.
- [ ] `test_auth_modes.py`: the full C7 matrix passes — subscription rejects a present `ANTHROPIC_API_KEY`/`AUTH_TOKEN` at construction, never passes `--bare`, honours `CLAUDE_CODE_OAUTH_TOKEN`, falls back to a probed stored login, and `auto` adds no extra validation.
- [ ] `test_no_credential_value_in_logs_or_exceptions` passes for all three credential vars: the sentinel value appears in no log, exception, or event.
- [ ] `test_events.py`: eight `claude_code.*` classes instantiate, are frozen, carry `run_id`/UTC `timestamp`/`event_type`; only `StreamCompleted` carries the token figure; `auth_failed` carries a reason enum only.
- [ ] `test_isolation.py`: no sibling-backend / grpc / OpenHands-client import.
- [ ] `ruff check src/ tests/` - clean.
