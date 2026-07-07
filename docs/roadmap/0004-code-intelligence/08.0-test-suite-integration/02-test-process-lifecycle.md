# 02 - `test_process_lifecycle.py`

**Parent task:** 08.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** 01 (skip guards / fixtures), 03.0 `OpenClaudeProcess` (managed mode) live
**Blocks:** none

## Objective

Prove the managed-mode process lifecycle contract (C6) against a real OpenClaude
sidecar: that `__aenter__` brings a subprocess to a connectable gRPC port within
`connect_timeout_s`, that `OpenClaudeConnected` fires exactly once, that
`__aexit__` terminates the process inside the SIGTERM grace period and emits
`OpenClaudeDisconnected` exactly once, and — the load-bearing safety assertion —
that no OpenClaude process survives the test. These tests construct their **own**
`OpenClaudeProcess` (they do not use the shared `live_openclaude_process` fixture)
because they must observe the start/stop transitions rather than inherit an
already-running process.

## File: `tests/openclaude/integration/test_process_lifecycle.py`

```python
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import psutil  # or os-level PID probe; process-table check for the leak assertion
import pytest
import pytest_asyncio

from aegis.core.events import EventBus
from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected
from aegis.openclaude.process import OpenClaudeProcess

from tests.openclaude.integration.conftest import require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent

pytestmark = pytest.mark.asyncio


def _managed_settings() -> OpenClaudeSettings:
    return OpenClaudeSettings(auto_start=True, grpc_url="localhost:0")


async def test_managed_start_connects_within_timeout(stub_project: Path) -> None:
    """__aenter__ exposes a ready grpc_url within connect_timeout_s."""
    settings = _managed_settings()
    bus = EventBus()
    start = time.monotonic()
    async with OpenClaudeProcess(settings, bus, cwd=stub_project) as proc:
        assert proc.grpc_url  # resolved, non-zero port
        assert (time.monotonic() - start) <= settings.connect_timeout_s
    ...


async def test_connected_event_emitted_exactly_once(stub_project: Path) -> None:
    """Exactly one OpenClaudeConnected is emitted on successful entry."""
    ...  # subscribe a recorder to the bus; count OpenClaudeConnected == 1


async def test_aexit_stops_process_within_grace_period(stub_project: Path) -> None:
    """__aexit__ terminates the subprocess within the SIGTERM grace period."""
    ...  # capture PID inside the block; assert not psutil.pid_exists(pid) after,
         # within grace; assert SIGKILL was not required for a clean shutdown


async def test_disconnected_event_emitted_exactly_once(stub_project: Path) -> None:
    """Exactly one OpenClaudeDisconnected is emitted on exit."""
    ...


async def test_no_process_survives_session(stub_project: Path) -> None:
    """After context exit, no OpenClaude child process remains running."""
    ...  # record child PID(s); after __aexit__, assert none are alive
```

## Test cases

- `test_managed_start_connects_within_timeout` — managed `__aenter__` resolves a
  live `grpc_url` (free-port selection when `localhost:0`) and returns inside
  `connect_timeout_s`.
- `test_connected_event_emitted_exactly_once` — exactly one `OpenClaudeConnected`
  on the bus for one successful entry (never zero, never duplicated).
- `test_aexit_stops_process_within_grace_period` — the subprocess PID captured
  inside the block is gone after `__aexit__`, terminated by SIGTERM within the
  grace period (no SIGKILL escalation needed for a healthy process).
- `test_disconnected_event_emitted_exactly_once` — exactly one
  `OpenClaudeDisconnected` on exit.
- `test_no_process_survives_session` — a process-table/PID probe confirms no
  OpenClaude process remains after the context closes.

## Constraints

- Tests that run pass with **zero mocks** — a real managed-mode subprocess.
- No integration test may leave a running OpenClaude process; the `async with`
  block plus an explicit finalizer path guarantees teardown even on failure.
- Uses the temp-dir `stub_project`, never the Aegis SWR source tree; runs
  read-only under the default allowlist.
- Gated behind `OPENCLAUDE_INTEGRATION` via `require_managed_openclaude()`;
  skipped by default on PRs, optional on main (task 09.0 CI wiring).
- The leak assertion uses a PID/process-table probe (e.g. `psutil.pid_exists`) —
  the child PID is captured inside the block before exit.
- `from __future__ import annotations`; `Optional[T]`, never `T | None`;
  `asyncio.sleep` (never `time.sleep`) if any polling is needed; `ruff`
  and `replace_optional.py --check` clean.

## Success criteria

- [ ] Managed `__aenter__` yields a ready `grpc_url` within `connect_timeout_s`.
- [ ] `OpenClaudeConnected` asserted emitted **exactly once** per successful entry.
- [ ] `__aexit__` stops the subprocess within the SIGTERM grace period without
      requiring SIGKILL for a healthy process.
- [ ] `OpenClaudeDisconnected` asserted emitted **exactly once** per exit.
- [ ] A PID/process-table check confirms **no** OpenClaude process survives.
- [ ] All tests report **skipped** (not failed) when the binary or signal is absent.
- [ ] `ruff`, `replace_optional.py --check` clean.
