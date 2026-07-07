# 04 - `test_process.py`

**Parent task:** 07.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** 01 (fixtures), 03.0 subtask 01 (external mode), 03.0 subtask 02
(managed mode), 05.0 (events + `OpenClaudeUnavailableError`).
**Blocks:** none

## Objective

Verify `OpenClaudeProcess` lifecycle (contract C6) in both modes with a fully
injected gRPC client and a **fake subprocess** — no real Node.js process is ever
spawned. Cover: external-mode health-check failure raises
`OpenClaudeUnavailableError`; managed-mode clean exit terminates the mocked
subprocess; managed-mode SIGKILL escalation after the grace period; connect/
disconnect emitted exactly once per cycle in both modes; and the critical
always-terminate invariant when `__aenter__` raises after the port opened.

## File: `tests/openclaude/unit/test_process.py`

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from aegis.openclaude.process import OpenClaudeProcess
from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected
from aegis.openclaude.exceptions import OpenClaudeUnavailableError


@pytest.fixture
def fake_subprocess():
    """A fake asyncio subprocess: terminate()/kill()/wait() are observable.

    * returncode starts None (alive).
    * wait() awaits until terminate() or kill() flips returncode.
    * A `never_dies` variant leaves wait() pending until kill(), to force the
      SIGKILL escalation path.
    """
    ...


@pytest.fixture
def patched_create_subprocess(monkeypatch, fake_subprocess):
    """Inject the fake process for managed-mode tests.

    Managed mode calls asyncio.create_subprocess_exec internally; since it is
    NOT a constructor seam, it is replaced here at the asyncio boundary only
    (not an aegis.openclaude module global) so no real Node.js process starts.
    Port-readiness is driven by a stubbed _await_port_open / TCP-accept probe.
    """
    ...


# --- External mode ----------------------------------------------------------

async def test_external_mode_raises_when_health_check_fails(
    settings_no_grpc, mock_event_bus, mock_grpc_client,
) -> None:
    """auto_start=False + health_check()->False → __aenter__ raises OpenClaudeUnavailableError, no connect event."""

async def test_external_mode_success_emits_connected_once(
    settings_with_grpc, mock_event_bus, mock_grpc_client,
) -> None:
    """auto_start=False + healthy endpoint → exactly one OpenClaudeConnected; grpc_url readable inside block."""

async def test_external_mode_never_spawns_subprocess(
    settings_with_grpc, mock_event_bus, mock_grpc_client, monkeypatch,
) -> None:
    """External mode never calls asyncio.create_subprocess_exec."""

async def test_grpc_url_before_enter_raises_runtime_error(
    settings_with_grpc, mock_event_bus, mock_grpc_client,
) -> None:
    """Reading .grpc_url before __aenter__ raises RuntimeError (programming error)."""

async def test_external_mode_disconnected_emitted_once_on_clean_exit(
    settings_with_grpc, mock_event_bus, mock_grpc_client,
) -> None:
    """Clean __aexit__ emits exactly one OpenClaudeDisconnected in external mode."""


# --- Managed mode -----------------------------------------------------------

async def test_managed_mode_terminates_subprocess_on_clean_exit(
    mock_event_bus, mock_grpc_client, patched_create_subprocess, fake_subprocess,
) -> None:
    """auto_start=True, normal exit → SIGTERM sent, process reaped, no SIGKILL needed."""

async def test_managed_mode_sigkill_after_grace_period(
    mock_event_bus, mock_grpc_client, patched_create_subprocess, fake_subprocess,
) -> None:
    """A process that ignores SIGTERM is SIGKILLed after the grace period and reaped."""

async def test_managed_mode_connected_and_disconnected_each_once(
    mock_event_bus, mock_grpc_client, patched_create_subprocess, fake_subprocess,
) -> None:
    """One full context cycle emits exactly one Connected and one Disconnected."""

async def test_managed_mode_terminates_when_entry_raises_after_port_open(
    mock_event_bus, mock_grpc_client, patched_create_subprocess, fake_subprocess,
) -> None:
    """__aenter__ raising AFTER the process started still terminates it (03.0/02 invariant)."""

async def test_managed_mode_port_never_opens_raises_and_terminates(
    mock_event_bus, mock_grpc_client, patched_create_subprocess, fake_subprocess,
) -> None:
    """Port not open within connect_timeout_s → OpenClaudeUnavailableError AND the started process is terminated."""
```

## Test cases

| Test | Contract verified |
|------|-------------------|
| `test_external_mode_raises_when_health_check_fails` | C6 external: failed health check → `OpenClaudeUnavailableError`; **no** `OpenClaudeConnected` emitted |
| `test_external_mode_success_emits_connected_once` | C6/C8: exactly one `OpenClaudeConnected` on entry; `grpc_url` readable inside the block |
| `test_external_mode_never_spawns_subprocess` | C6: external mode issues no `create_subprocess_exec` |
| `test_grpc_url_before_enter_raises_runtime_error` | 03.0/01: `grpc_url` accessor guard raises `RuntimeError` (not `OpenClaudeUnavailableError`) before entry |
| `test_external_mode_disconnected_emitted_once_on_clean_exit` | C6/C8: exactly one `OpenClaudeDisconnected` on clean external exit |
| `test_managed_mode_terminates_subprocess_on_clean_exit` | C6 managed: `SIGTERM` (`terminate()`) on exit; process reaped; no `SIGKILL` on a cooperative process |
| `test_managed_mode_sigkill_after_grace_period` | C6: escalate to `SIGKILL` (`kill()`) after the grace period when `SIGTERM` is ignored; process reaped (no zombie) |
| `test_managed_mode_connected_and_disconnected_each_once` | C6/C8: exactly-once emission of both lifecycle events across one full cycle |
| `test_managed_mode_terminates_when_entry_raises_after_port_open` | 03.0/02 critical invariant: entry-raised-after-start still terminates the subprocess before the exception propagates |
| `test_managed_mode_port_never_opens_raises_and_terminates` | C6: port-open timeout → `OpenClaudeUnavailableError` **and** the started process is terminated |

## Constraints

- All tests pass with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude binary on
  `PATH`; no real subprocess is spawned and no real socket opened.
- The gRPC client is injected via the `OpenClaudeProcess(..., client=...)`
  constructor seam using `mock_grpc_client`. The subprocess seam
  (`asyncio.create_subprocess_exec`) is **not** a constructor argument, so it is
  replaced at the `asyncio` boundary only — never patch an
  `aegis.openclaude.process` module global. If 03.0's final implementation
  exposes a subprocess-factory injection point, prefer that over the `asyncio`
  patch and flag it back to 03.0.
- Assert `asyncio.sleep` is used for backoff (not `time.sleep`) where the
  readiness/grace timing is exercised — patch `asyncio.sleep` with an
  `AsyncMock` to keep the suite fast.
- Managed-mode subprocess stderr forwarding (03.0/04) must not leak raw payload
  text to a log sink under assertion (C9).
- `Optional[T]` from `typing`; `from __future__ import annotations` (C9).

## Success criteria

- [ ] All 10 test functions present and passing.
- [ ] Emission-count assertions use `mock_event_bus.captured` and assert
      **exactly one** `OpenClaudeConnected` and **exactly one**
      `OpenClaudeDisconnected` per cycle (both modes).
- [ ] `test_managed_mode_terminates_when_entry_raises_after_port_open` asserts
      `fake_subprocess.terminate()` (or `kill()`) was called even though
      `__aenter__` raised.
- [ ] `test_managed_mode_sigkill_after_grace_period` asserts `kill()` was
      called and `wait()` was awaited (process reaped).
- [ ] `test_external_mode_never_spawns_subprocess` asserts
      `create_subprocess_exec` was never called.
- [ ] No `grpc` / `_pb2` import in this file; no real process spawned.
- [ ] `ruff`, `replace_optional.py --check` clean.
