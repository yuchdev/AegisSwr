# 03 - `tests/integration/harness/` selection smoke

**Parent task:** 12.0 Test Suite — Integration
**State:** ✅ Complete
**Depends on:** 01 (Claude Code guards), 02 (OpenHands guards), 10.0 (`harness.composition.create_code_intel_backend`, `HarnessSettings`) **live**
**Blocks:** none

## Objective

Prove the milestone's headline change — the neutral composition root and the C2
single-active-backend selection contract — end to end against a **live** backend,
rather than constructing a tool directly as subtasks 01 and 02 do. With exactly
one presence signal configured and that backend actually available, this smoke
test drives the full path an operator's deployment takes:

`HarnessSettings` resolves `active_backend` (C2) → `create_code_intel_backend(...)`
branches to the single active family (C4) → a `CodeAgent` is composed → a real
`delegate()` flows through it and returns a `CodeResult`.

This is deliberately a *single* thin smoke test (one live delegate per available
backend), not a re-run of the per-backend suites: its job is to exercise the
**selection + composition wiring**, not to re-validate each backend's internals.
It reuses the per-backend availability guards from subtasks 01/02 so it inherits
their skip-not-fail behavior verbatim, and it explicitly asserts the
zero-signals and multi-signal outcomes of the C2 truth table (capability
unavailable vs `HarnessConfigError`) without needing any backend to be live.

## File: `tests/integration/harness/conftest.py`

```python
from __future__ import annotations

import os
from typing import Optional

import pytest

from tests.integration.claude_code.conftest import (
    _api_credential_present,
    _binary_present,
    _claude_code_enabled,
)
from tests.integration.openhands.conftest import _docker_available, _server_url_set

from aegis_swr.claude_code.config import ClaudeCodeSettings


def _live_claude_code_available() -> bool:
    """True when Claude Code could actually serve a live delegate (auto/api mode)."""
    return (
        _claude_code_enabled()
        and _binary_present(ClaudeCodeSettings())
        and _api_credential_present()
    )


def _live_openhands_available() -> bool:
    """True when OpenHands could actually serve a live delegate."""
    return _server_url_set() and _docker_available()


def require_single_live_backend() -> None:
    """Skip unless **exactly one** backend is both signalled and live.

    The smoke test asserts auto-selection, which is only well-defined when a
    single presence signal is active (C2). When zero or more than one backend is
    live, this module skips — the multi-signal *rejection* path is asserted
    separately (without any live backend) in the config-outcome test below.
    """
    live = [n for n, ok in (
        ("claude_code", _live_claude_code_available()),
        ("openhands", _live_openhands_available()),
    ) if ok]
    if len(live) != 1:
        pytest.skip(
            f"harness smoke needs exactly one live backend, found {live!r}",
            allow_module_level=True,
        )


@pytest.fixture(scope="module")
def active_backend_name() -> str:
    """The single live backend family name (guaranteed present by the guard)."""
    if _live_claude_code_available():
        return "claude_code"
    return "openhands"
```

## File: `tests/integration/harness/test_selection_smoke.py`

```python
from __future__ import annotations

import uuid
from contextlib import AsyncExitStack
from typing import Optional

import pytest

from aegis_swr.code_intel.backend import CodeTaskContext
from aegis_swr.core.events import EventBus
from aegis_swr.harness.composition import create_code_intel_backend
from aegis_swr.harness.config import HarnessSettings

from tests.integration.harness.conftest import require_single_live_backend

require_single_live_backend()  # module-level: skip unless exactly one live backend

pytestmark = pytest.mark.asyncio


async def test_active_backend_resolves_to_the_single_live_family(
    active_backend_name: str,
):
    """C2: with one presence signal, HarnessSettings.active_backend auto-selects it."""
    settings = HarnessSettings()  # selector unset; sources per-family env signals
    assert settings.active_backend == active_backend_name
    ...


async def test_composition_then_live_delegate_flows_end_to_end(
    active_backend_name: str,
):
    """C4: create_code_intel_backend() composes a CodeAgent whose delegate() works live."""
    settings = HarnessSettings()
    bus = EventBus()
    async with AsyncExitStack() as stack:
        agent = await create_code_intel_backend(
            settings=settings,
            event_bus=bus,
            exit_stack=stack,  # RAII teardown of any sidecar registered here
        )
        result = await agent.delegate(
            task="Report the single token HARNESS_SMOKE_OK.",
            ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
        )
        assert result.available is True
        assert result.content.strip()
        assert result.token_estimate > 0
    ...  # stack exit tears down any sidecar; nothing survives the block
```

## File: `tests/integration/harness/test_selection_outcomes.py`

```python
from __future__ import annotations

from typing import Optional

import pytest

from aegis_swr.harness.config import HarnessSettings
from aegis_swr.harness.exceptions import HarnessConfigError

# NOTE: no live backend needed — these assert the C2 config-shape outcomes only,
# so this module runs unconditionally (it is not behind require_single_live_backend).


def test_zero_signals_is_capability_unavailable(monkeypatch: pytest.MonkeyPatch):
    """C2: selector unset + zero presence signals → no backend, no exception."""
    for var in (
        "AEGIS_CODE_INTEL_BACKEND",
        "OPENCLAUDE_GRPC_URL",
        "CLAUDE_CODE_ENABLED",
        "OPENHANDS_SERVER_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    settings = HarnessSettings()
    assert settings.active_backend is None  # capability unavailable, unchanged from 0004 C4
    ...


def test_multiple_signals_raise_harness_config_error(monkeypatch: pytest.MonkeyPatch):
    """C2: selector unset + more than one signal → HarnessConfigError, fail loud."""
    monkeypatch.delenv("AEGIS_CODE_INTEL_BACKEND", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://localhost:3000")
    with pytest.raises(HarnessConfigError):
        HarnessSettings()  # construction-time ambiguity; never a silent pick
    ...
```

## Test cases

- `test_active_backend_resolves_to_the_single_live_family` — with the selector
  unset and exactly one presence signal live, `HarnessSettings.active_backend`
  auto-selects that family (C2), preserving 0004's zero-change guarantee.
- `test_composition_then_live_delegate_flows_end_to_end` — the neutral
  `create_code_intel_backend(...)` composes a `CodeAgent` for the active backend,
  a real `delegate()` returns an available, non-empty `CodeResult` with a
  positive `token_estimate`, and the `AsyncExitStack` tears down any registered
  sidecar on block exit (C4).
- `test_zero_signals_is_capability_unavailable` — selector unset + zero signals
  yields `active_backend is None` and **no** exception (unchanged from 0004 C4);
  needs no live backend.
- `test_multiple_signals_raise_harness_config_error` — selector unset + more than
  one signal raises `HarnessConfigError` at settings-construction time — fail
  loud, never silently pick one (C2); needs no live backend.

## Implementation notes

- This subtask is optional per the task brief but included for real value: it is
  the **only** integration test that exercises the composition root itself (the
  headline deliverable of this milestone). Subtasks 01/02 construct tools
  directly and never touch `harness/`; this one drives selection → composition →
  delegate exactly as a deployment does.
- The config-outcome tests (`test_selection_outcomes.py`) are pure settings-shape
  assertions and run **unconditionally** — they are not behind the live guard, so
  the C2 truth table's unavailable and ambiguity branches are always covered even
  on a machine with no backend installed. They belong to the integration suite
  only for topical cohesion; if the unit suite (task 11.0) already covers them,
  keep them there and drop this file to avoid duplication — settle during
  implementation with `testing-expert`.
- The exact `create_code_intel_backend(...)` signature (whether it takes an
  `exit_stack`/`AsyncExitStack` and returns a `CodeAgent` or a bare backend) is
  fixed by task 10.0; align the smoke test to whatever 10.0 ships. Whatever the
  shape, the sidecar (OpenHands) must be registered for RAII teardown so nothing
  survives the block.
- The smoke guard requires **exactly one** live backend, so auto-selection is
  well-defined; when two are live it skips (the operator would hit
  `HarnessConfigError` at construction, which the config-outcome test asserts
  directly).

## Constraints

- **Skip, never fail.** The live smoke module skips unless exactly one backend is both signaled and available; the config-outcome module runs unconditionally and asserts pure settings behavior (no backend needed).
- The live delegate path runs with **zero mocks** through the real composition root and a real backend.
- Any sidecar registered on the `AsyncExitStack` is torn down on block exit; **nothing survives** the module (Claude Code reaps its one-shot process; OpenHands' sidecar session closes via the stack).
- No raw response text or credential ever reaches a log sink or event payload (C13); loguru sinks keep `SensitiveFilter`.
- `monkeypatch` is used to clear/set env for the config-outcome tests so they are a hermetic and do not leak signals into other modules.

## Success criteria

- [ ] With exactly one live presence signal, `HarnessSettings.active_backend` auto-selects that family (C2).
- [ ] `create_code_intel_backend(...)` composes a `CodeAgent` whose live `delegate()` returns an available, non-empty `CodeResult` with `token_estimate > 0` (C4).
- [ ] Any registered sidecar is torn down on `AsyncExitStack` exit; no process or sidecar session survives the module.
- [ ] Selector unset plus zero signals → `active_backend is None`, no exception (unchanged from 0004 C4).
- [ ] Selector unset plus more than one signal → `HarnessConfigError` at settings-construction time (C2).
- [ ] The live smoke module reports **skipped** (not failed) unless exactly one backend is signaled and available.
- [ ] `ruff check src/ tests/` - clean.
