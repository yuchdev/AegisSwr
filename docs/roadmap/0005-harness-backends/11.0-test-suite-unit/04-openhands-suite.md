# 04 - `tests/unit/openhands/` suite

**Parent task:** 11.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** 01 (shared fixtures — `mock_openhands_client`, `mock_event_bus`,
`ample_budget`, `dry_run_ctx`, `live_ctx`, `openhands_settings_enabled`), 06.0
(`OpenHandsSettings`, `OpenHandsConfigError`), 07.0 (`OpenHandsClient`,
`OpenHandsProcess`), 08.0 (`OpenHandsTool.delegate()`), 09.0 (`openhands.*`
events, `OpenHandsUnavailableError`).
**Blocks:** none

## Objective

Verify the OpenHands backend at the unit level with a fully injected mock HTTP/WS
client and a fake sidecar — no real server, socket, or Docker container ever
starts. Cover the C5/C8 settings surface (**Docker-sandboxed runtime by
default**; non-sandboxed requires an explicit override), the scripted
Action/Observation event stream, the sidecar lifecycle (mirroring 0004's
`OpenClaudeProcess`), **100% branch coverage on `delegate()`** (mirroring 0004's
`tool.py` gate), the `openhands.*` event taxonomy (C10), and the import-isolation
posture — including that `openhands/client.py` is the **sole** importer of the
OpenHands client library (C3).

## File: `tests/unit/openhands/test_config.py`

```python
from __future__ import annotations

import pytest

from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.exceptions import OpenHandsConfigError


def test_defaults_when_no_env_vars(monkeypatch):
    """No env → server_url is None (presence signal off), runtime_mode is the sandboxed Docker runtime; no raise (C5/C8)."""

def test_server_url_from_env_is_presence_signal(monkeypatch):
    """OPENHANDS_SERVER_URL set → server_url populated (the presence signal, C8)."""

def test_docker_sandbox_is_the_default_runtime():
    """runtime_mode defaults to the Docker-sandboxed runtime (C8 hard requirement)."""

def test_non_sandboxed_runtime_requires_explicit_override():
    """Selecting a non-sandboxed runtime requires an explicit override value, not the default (C8)."""

def test_invalid_server_url_raises_config_error():
    """A malformed server_url → OpenHandsConfigError(field='server_url')."""

def test_comma_separated_allowed_tools_parsed_from_env(monkeypatch):
    """OPENHANDS_ALLOWED_TOOLS CSV → list[str] (C5 env parse)."""

def test_request_timeout_cross_field_validation():
    """request_timeout_s must exceed connect_timeout_s → OpenHandsConfigError otherwise (C5)."""
```

## File: `tests/unit/openhands/test_client.py`

```python
from __future__ import annotations

import pytest

from aegis_swr.openhands.client import OpenHandsClient
from aegis_swr.openhands.exceptions import OpenHandsUnavailableError


async def test_stream_yields_scripted_events_in_order(mock_openhands_client):
    """stream() yields the scripted Action/Observation events in emission order (C8)."""

async def test_health_check_returns_false_when_unreachable(mock_openhands_client):
    """A simulated unreachable server → health_check() returns False, does NOT raise (mirrors 0004)."""

async def test_stream_raises_unavailable_on_connect_error(mock_openhands_client):
    """A connect error during stream() → OpenHandsUnavailableError, not a raw client error (C8)."""

async def test_close_shuts_down_client(mock_openhands_client):
    """close() awaits the client's shutdown exactly once (RAII, C13)."""

def test_client_is_sole_importer_of_openhands_library():
    """openhands/client.py is the ONLY module importing the OpenHands HTTP/WS client library (C3)."""
```

## File: `tests/unit/openhands/test_process.py`

```python
from __future__ import annotations

import pytest

from aegis_swr.openhands.process import OpenHandsProcess
from aegis_swr.openhands.events import OpenHandsConnected, OpenHandsDisconnected
from aegis_swr.openhands.exceptions import OpenHandsUnavailableError


async def test_external_mode_raises_when_health_check_fails(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client,
):
    """External mode + health_check()->False → __aenter__ raises OpenHandsUnavailableError; no Connected event (C8)."""

async def test_external_mode_emits_connected_once(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client,
):
    """Healthy external server → exactly one OpenHandsConnected on entry (C8/C10)."""

async def test_disconnected_emitted_once_on_clean_exit(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client,
):
    """Clean __aexit__ emits exactly one OpenHandsDisconnected (C8/C10)."""

async def test_process_registered_on_exit_stack_for_teardown(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client,
):
    """The sidecar is torn down via the AsyncExitStack (RAII; mirrors 0004 C6)."""

async def test_managed_mode_teardown_when_entry_raises_after_connect(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client,
):
    """__aenter__ raising AFTER connect still tears down the sidecar (0004 always-terminate invariant)."""
```

## File: `tests/unit/openhands/test_tool.py` (100% branch required)

```python
from __future__ import annotations

import pytest

from aegis_swr.openhands.tool import OpenHandsTool
from aegis_swr.openhands.exceptions import (
    OpenHandsUnavailableError,
    OpenHandsPermissionDeniedError,
)
from aegis_swr.openhands.events import (
    OpenHandsAction,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
    OpenHandsStreamCompleted,
    OpenHandsStreamError,
)
from aegis_swr.code_intel.budget import CallBudget


# --- 1. Happy path ----------------------------------------------------------

async def test_delegate_success_accumulates_observations(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, live_ctx,
):
    """Observation stream to the terminal event → CodeResult.text is the accumulated text, success."""


# --- 2. Budget pre-check short-circuit --------------------------------------

async def test_delegate_budget_insufficient_short_circuits(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, live_ctx,
):
    """CallBudget(0) < pre-check → non-retriable failure; client.stream NEVER called."""


# --- 3. Dry-run short-circuit -----------------------------------------------

async def test_delegate_dry_run_short_circuits(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, dry_run_ctx,
):
    """ctx.dry_run → '[dry-run]' result, zero tokens; NO network call (C8/C13)."""


# --- 4. Action / Observation dispatch ---------------------------------------

async def test_delegate_action_event_emits_openhands_action(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, live_ctx,
):
    """An action event emits OpenHandsAction and increments the tool-call count (C10)."""

async def test_delegate_observation_event_emits_openhands_observation(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, live_ctx,
):
    """An observation event emits OpenHandsObservation (C10)."""


# --- 5. Permission-denied branch --------------------------------------------

async def test_delegate_permission_denied_non_retriable(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, live_ctx,
):
    """A permission-denied event → OpenHandsPermissionDenied emitted, non-retriable failure."""


# --- 6. Token accounting: server usage vs boundary estimate -----------------

async def test_delegate_uses_server_usage_when_reported(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, live_ctx,
):
    """Terminal event with server-reported usage → token_estimate == that usage (C9)."""

async def test_delegate_falls_back_to_boundary_estimate(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, live_ctx,
):
    """No server usage → token_estimate == max(1, len(content)//4) (C9 boundary estimate)."""


# --- 7. Error / unavailable paths -------------------------------------------

async def test_delegate_stream_error_returns_non_retriable_failure(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, live_ctx,
):
    """A terminal error event → OpenHandsStreamError, non-retriable failure result."""

async def test_delegate_connect_error_returns_retriable_failure(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, ample_budget, live_ctx,
):
    """stream() raising OpenHandsUnavailableError → retriable failure + OpenHandsStreamError."""


# --- 8. Budget charged after completion -------------------------------------

async def test_budget_charged_after_completion_not_precharged(
    openhands_settings_enabled, mock_event_bus, mock_openhands_client, live_ctx,
):
    """Budget charged AFTER the terminal event, never pre-charged before stream() (C9)."""
```

## File: `tests/unit/openhands/test_events.py`

```python
from __future__ import annotations

import dataclasses

import pytest

from aegis_swr.openhands.events import (
    OpenHandsConnected,
    OpenHandsDisconnected,
    OpenHandsAction,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
    OpenHandsStreamCompleted,
    OpenHandsStreamError,
)

ALL_EVENT_TYPES = [
    OpenHandsConnected,
    OpenHandsDisconnected,
    OpenHandsAction,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
    OpenHandsStreamCompleted,
    OpenHandsStreamError,
]


@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_instantiates(cls):
    """Each openhands.* event constructs (keyword-only) and subclasses DomainEvent (C10)."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_is_frozen(cls):
    """Mutating any field raises FrozenInstanceError (frozen=True, C10)."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_carries_run_id_timestamp_event_type(cls):
    """Each carries run_id, a UTC timestamp, and a ClassVar[str] event_type sentinel (C10)."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_type_sentinel_matches_c10(cls):
    """event_type equals the exact C10 string ('openhands.connected', …, '.error')."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_round_trips_through_bus(cls, mock_event_bus):
    """Emitting the event puts exactly that instance on mock_event_bus.captured (C10)."""

def test_only_stream_completed_carries_token_estimate():
    """OpenHandsStreamCompleted is the ONLY event carrying token_estimate (C10 non-duplication)."""

def test_no_event_has_any_typed_field():
    """No event field is annotated Any and none carries raw payload/observation text (C13)."""
```

## File: `tests/unit/openhands/test_isolation.py`

```python
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "aegis_swr" / "openhands"
SIBLINGS = {"openclaude", "claude_code"}


def test_openhands_imports_no_sibling_backend():
    """No file under aegis_swr/openhands imports aegis_swr.openclaude or aegis_swr.claude_code (C3, AST-based)."""

def test_only_client_imports_openhands_library():
    """The OpenHands client library is imported ONLY by openhands/client.py (C3)."""

def test_openhands_imports_no_grpc():
    """openhands imports neither grpc nor any _pb2 module (C3)."""
```

## Test cases (selected — branch map for `delegate()`)

| Test                                                          | Branch / contract verified                                               |
|---------------------------------------------------------------|--------------------------------------------------------------------------|
| `test_delegate_success_accumulates_observations`              | happy path: observation stream → concatenated `CodeResult.text`, success |
| `test_delegate_budget_insufficient_short_circuits`            | budget pre-check false branch; `client.stream` never called              |
| `test_delegate_dry_run_short_circuits`                        | dry-run branch; `[dry-run]`, zero tokens, no network                     |
| `test_delegate_action_event_emits_openhands_action`           | action dispatch arm → `OpenHandsAction`                                  |
| `test_delegate_observation_event_emits_openhands_observation` | observation dispatch arm → `OpenHandsObservation`                        |
| `test_delegate_permission_denied_non_retriable`               | permission-denied arm → `OpenHandsPermissionDenied`, non-retriable       |
| `test_delegate_uses_server_usage_when_reported`               | C9: server-reported usage used for `token_estimate`                      |
| `test_delegate_falls_back_to_boundary_estimate`               | C9: `max(1, len(content)//4)` boundary estimate branch                   |
| `test_delegate_stream_error_returns_non_retriable_failure`    | terminal error arm → non-retriable failure                               |
| `test_delegate_connect_error_returns_retriable_failure`       | `OpenHandsUnavailableError` arm → **retriable** failure                  |
| `test_budget_charged_after_completion_not_precharged`         | C9: charged after completion, never pre-charged                          |
| `test_client_is_sole_importer_of_openhands_library`           | C3: sole client-library importer                                         |
| `test_only_client_imports_openhands_library`                  | C3: AST-confirmed sole importer                                          |

## Implementation notes

- The mock client comes from the shared `mock_openhands_client` factory
  (subtask 01), the direct analogue of 0004's `mock_grpc_client`; scripted events
  are plain dicts, so no OpenHands SDK object and no socket are involved.
- **100% branch coverage on `openhands/tool.py::delegate()`** is enforced
  `--cov=aegis_swr.openhands.tool --cov-branch --cov-fail-under=100` scoped in
  task 13.0 — every dispatch arm, both budget-check sides, dry-run, both
  token-accounting branches (server-usage vs boundary estimate), and both error
  classes must be hit. `delegate()` must never let an exception escape.
- `test_process.py` mirrors 0004's `test_process.py` external/managed lifecycle
  assertions (connect/disconnect exactly once, always-teardown-on-entry-raise),
  reusing `OpenHandsProcess`'s client-injection seam — no real sidecar.
- `test_client.py::test_client_is_sole_importer_of_openhands_library` and
  `test_isolation.py::test_only_client_imports_openhands_library` both assert the
  sole-importer property; keep the AST helper shared with subtask 02/03 rather
  than duplicating it.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new unit test has a test-specific docstring (`[Unit]`|`[Mock]`|`[Integration]`|`E2E` / `Scenario` / `Boundaries` / `On failuse`)
- All tests pass with `OPENHANDS_SERVER_URL` unset and no Docker / OpenHands server available — no real socket opened and no container started.
- Every collaborator is constructor-injected (`OpenHandsProcess(..., client=...)`, `OpenHandsTool(client=..., settings=..., bus=...)`); `monkeypatch` is used **only** for real `OPENHANDS_*` env vars.
- Assert on the canonical `OpenHandsConfigError` / `OpenHandsUnavailableError` types, not Pydantic `ValidationError`.
- No raw observation / response text is asserted against a log sink; the tool must not log unredacted stream content (C13).
- `test_isolation.py` is AST-based (docstring mentions must not trip it).

## Success criteria

- [ ] `test_config.py`: the Docker-sandboxed runtime is the default; a non-sandboxed runtime requires an explicit override; a malformed `server_url` raises `OpenHandsConfigError`.
- [ ] `test_client.py`: scripted events stream in order; `health_check()` returns `False` (does not raise) when unreachable; a connection error surfaces as `OpenHandsUnavailableError`.
- [ ] `test_process.py`: exactly one `OpenHandsConnected` and one `OpenHandsDisconnected` per cycle; the sidecar is torn down even when `__aenter__` raises after connection.
- [ ] `test_tool.py`: `pytest --cov=aegis_swr.openhands.tool --cov-branch` reports **100%** branch on `delegate()`; budget/dry-run paths make no network call; both token-accounting branches are covered.
- [ ] `test_events.py`: seven `openhands.*` classes instantiate, are frozen, carry `run_id`/UTC `timestamp`/`event_type`; only `StreamCompleted` carries the token figure.
- [ ] `test_isolation.py` / `test_client.py`: `openhands/client.py` is the sole importer of the OpenHands client library; no sibling-backend / grpc import.
- [ ] `ruff check src/ tests/` - clean.
