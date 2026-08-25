# 01 - harness/composition.py factory and delete openclaude/composition.py

**Parent task:** 10.0 Harness Composition Root & CLI
**State:** ✅ Complete
**Depends on:** Task 01.0 (`HarnessSettings`, `active_backend`, `HarnessConfigError`/`HarnessUnavailableError`); Tasks 03.0/04.0 (`ClaudeCodeTool`, auth resolution); Tasks 07.0/08.0 (`OpenHandsClient`/`OpenHandsProcess`/`OpenHandsTool`); Task 02.0/06.0 (per-family settings). Consumes subtask 02 (`Settings.harness`) at wiring time.
**Blocks:** 02, 04; Task 11.0 (composition-root unit tests re-target here)

## Objective

Create `aegis_swr/harness/composition.py` — the generalized C4 composition
factory — and delete `aegis_swr/openclaude/composition.py`. This is the substance
of Task 10.0: it is the **one and only** place in the codebase that branches on
which code-intelligence backend is active. It reads the resolved
`HarnessSettings.active_backend` (Task 01.0 / C2) and assembles exactly one
backend stack (or none), injecting it into a `CodeAgent`. The OpenClaude assembly
logic **moves verbatim** from the deleted `openclaude/composition.py`; the
`claude_code` and `openhands` branches are added alongside it. This module becomes
the only one in the codebase permitted to import more than one backend family
(C3).

## Naming decision (resolves the C4 "settle in task 10.0" open item)

C4 leaves the factory name open: `create_code_intel_backend(...)` **or**
`build_code_agent(...)` (the 0004 name). **Decision: keep `build_code_agent`.**

| Option                          | Pros                                                                                                                                                                                                                                                                       | Cons                                                                                                                                                                                                                         |
|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `build_code_agent` (**chosen**) | Describes the actual return type (`CodeAgent`, not a backend); minimises the migration surface to a module-path change (the CLI already imports `build_code_agent`); best serves C4's "moves verbatim" instruction — same name/signature, only the branch body generalises | Diverges from the `plan.md` Architecture diagram / C4 prose, which lead with `create_code_intel_backend`                                                                                                                     |
| `create_code_intel_backend`     | Matches the plan's leading name; reads as a factory-of-backend                                                                                                                                                                                                             | Misdescribes the return (`CodeAgent`, not `CodeIntelBackend`); the `None` path returns a *backend-less* `CodeAgent`, so "create backend" is wrong for that branch; forces a rename of the CLI import for no behavioural gain |

The counter-argument (diagram naming) is real but cosmetic; accuracy of the
return type and a smaller breaking surface win. The one behavioral axis that
matters — a single auditable branch — is identical under either name.

## File: `src/aegis_swr/harness/composition.py`

```python
"""Neutral code-intelligence composition root (the generalised C4 branch).

This module is the **one and only** place in Aegis SWR that branches on which
code-intelligence backend is active. It reads the resolved
:attr:`HarnessSettings.active_backend` (resolved at settings-construction time
per C2, Task 01.0) and assembles exactly one backend stack — or none — injecting
it into a :class:`CodeAgent`.

Isolation (C3): this is the **only** module in the codebase permitted to import
more than one backend family. It imports all three (``openclaude``,
``claude_code``, ``openhands``); no backend package imports a sibling, and
``code_intel/`` imports none of them. The generalisation is recorded in
`ADR 0004 <docs/adr/0004-harness-composition-generalization.md>`_.
"""
from __future__ import annotations

from contextlib import AsyncExitStack

from loguru import logger

from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.code_intel.backend import CodeIntelBackend
from aegis_swr.config.settings import HarnessSettings
from aegis_swr.core.events import EventBus
from aegis_swr.harness.exceptions import HarnessUnavailableError

# The only cross-family imports in the codebase (C3). Each backend package is
# self-contained; only this module reaches across all three.
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis_swr.openclaude.process import OpenClaudeProcess
from aegis_swr.openclaude.tool import OpenClaudeTool
from aegis_swr.openhands.client import OpenHandsClient
from aegis_swr.openhands.process import OpenHandsProcess
from aegis_swr.openhands.tool import OpenHandsTool


async def build_code_agent(
    harness: HarnessSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    run_id: str,
    dry_run: bool,
) -> CodeAgent:
    """Assemble the active code-intelligence backend and inject it into a CodeAgent.

    This is the sole C4 branch. It dispatches on ``harness.active_backend``
    (resolved per C2 in Task 01.0) and constructs exactly one backend stack, or
    returns a backend-less :class:`CodeAgent` when no backend is active. The
    ``dry_run`` axis is **orthogonal** to backend selection: the graph is fully
    constructed and the backend registered so the composition path is exercised,
    but no sidecar is entered and no outbound call is made (C4 / C13).

    :param harness: The composed ``settings.harness`` sub-settings, whose
        ``active_backend`` was resolved at settings-construction time (C1/C2).
    :param bus: Shared :class:`EventBus` for the run; each backend emits its own
        ``DomainEvent`` taxonomy onto it (C10).
    :param stack: Application-lifetime ``AsyncExitStack``. Only sidecar-bearing
        backends (``openclaude``, ``openhands``) register a process on it for
        RAII teardown; ``claude_code`` (one-shot subprocess) registers nothing.
    :param run_id: Investigation run identifier, threaded onto emitted events.
    :param dry_run: When ``True``, construct + register but enter no sidecar and
        open no connection; ``ctx.dry_run`` short-circuits every ``delegate``.
    :raises HarnessUnavailableError: when an explicitly-selected backend's
        presence signal is absent at composition time (C2 last row).
    :return: A configured :class:`CodeAgent`; ``agent.available`` is ``False``
        only for the no-backend case.
    """
    backend_name = harness.active_backend

    # C2 row 1: selector unset + zero signals -> capability unavailable, no
    # exception. Identical observable behaviour to 0004's unset path.
    if backend_name is None:
        logger.debug("No code-intelligence backend active; capability unavailable")
        return CodeAgent(backend=None)

    if backend_name == "openclaude":
        return await _build_openclaude(harness, bus, stack, dry_run=dry_run)
    if backend_name == "claude_code":
        return await _build_claude_code(harness, bus, stack, dry_run=dry_run)
    if backend_name == "openhands":
        return await _build_openhands(harness, bus, stack, dry_run=dry_run)

    # Unreachable if C2 resolution (Task 01.0) is correct; fail loud rather than
    # silently returning a backend-less agent for an unknown name.
    raise HarnessUnavailableError(backend=backend_name)


async def _build_openclaude(
    harness: HarnessSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    dry_run: bool,
) -> CodeAgent:
    """Assemble the OpenClaude stack (MOVED VERBATIM from openclaude/composition.py).

    This body is the 0004 factory relocated unchanged (C4): the
    ``OpenClaudeGrpcClient`` -> ``OpenClaudeProcess`` -> ``OpenClaudeTool``
    assembly, including the dry-run branch that constructs the client from
    ``settings.grpc_url`` directly and never enters the process (0004 subtask 02).
    """
    settings = harness.openclaude
    process = OpenClaudeProcess(settings, bus)
    if dry_run:
        # Construct + register, never enter the process (no health check, C6
        # skipped); delegate() short-circuits before any RPC. Verbatim 0004.
        client = OpenClaudeGrpcClient(settings.grpc_url, settings)
    else:
        await stack.enter_async_context(process)  # health-check / start (C6)
        client = OpenClaudeGrpcClient(process.grpc_url, settings)
    backend: CodeIntelBackend = OpenClaudeTool(client, settings, bus)
    return CodeAgent(backend=backend)


async def _build_claude_code(
    harness: HarnessSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    dry_run: bool,
) -> CodeAgent:
    """Assemble the Claude Code stack (one-shot subprocess; no sidecar).

    Nothing is registered on *stack*: ``ClaudeCodeTool`` spawns and reaps a
    ``claude`` subprocess per ``delegate()`` call (C6), so there is no long-lived
    resource to enter. The auth mode is resolved per C7 by ``ClaudeCodeTool``
    from ``harness.claude_code`` (already validated at settings-construction
    time). Even under ``dry_run`` the tool is registered so the path is exercised;
    the startup auth-probe (C7) is a runtime concern the tool gates on ``dry_run``.
    """
    settings = harness.claude_code
    backend: CodeIntelBackend = ClaudeCodeTool(settings, bus)
    return CodeAgent(backend=backend)


async def _build_openhands(
    harness: HarnessSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    dry_run: bool,
) -> CodeAgent:
    """Assemble the OpenHands stack (Docker-sandboxed sidecar over REST/WS).

    Mirrors the OpenClaude sidecar pattern (C8): the ``OpenHandsProcess`` is
    registered on *stack* for RAII teardown in a real run; under ``dry_run`` the
    process is not entered (no connection) but the tool is still constructed and
    registered.
    """
    settings = harness.openhands
    process = OpenHandsProcess(settings, bus)
    if not dry_run:
        await stack.enter_async_context(process)  # health-check / start (C8)
    client = OpenHandsClient(settings, process)
    backend: CodeIntelBackend = OpenHandsTool(client, settings, bus)
    return CodeAgent(backend=backend)
```

## File: `src/aegis_swr/openclaude/composition.py` — DELETED

The module is removed in full. Its sole content — the `build_code_agent` factory
and its `grpc_url is not None` branch — has moved verbatim into
`harness/composition.py`'s `_build_openclaude` helper. The rest of the
`openclaude/` package (`config.py`, `tool.py`, `process.py`, `events.py`,
`exceptions.py`, `grpc/`) is untouched. Its 0004 unit tests
(`tests/unit/.../test_composition.py`) are re-targeted to
`tests/unit/harness/test_composition.py` by Task 11.0 — the coverage obligation
(≥90% module, 100% branch on each tool's `delegate`) is unchanged.

## Implementation notes

- **`active_backend` is read, never re-derived.** All selection/ambiguity logic
  (the C2 truth table) lives in `HarnessSettings` (Task 01.0). This module only
  dispatches on the already-resolved value. `HarnessConfigError` (unset + >1
  signal) has already fired at settings-construction time and never reaches here;
  `HarnessUnavailableError` (explicit selector plus absent signal) is raised here /
  at health check time (C2 last row) — the `_build_*` helpers surface it when the
  backend's own settings report the presence signal absent.
- **The OpenClaude branch is a move, not a rewrite (C4).** Copy the 0004 body —
  including the dry-run `settings.grpc_url` vs entered-`process.grpc_url`
  distinction resolved in 0004 subtask 02 — verbatim into `_build_openclaude`.
  Do not "clean it up" while moving; a verbatim move keeps the 0004 tests valid
  after re-targeting.
- **`dry_run` is a separate axis from selection (C4).** Do not fold it into the
  `active_backend` branch. It only decides whether a sidecar-bearing backend
  *enters* its process; `claude_code` has no sidecar so the flag has no assembly
  effect there (its short-circuit is inside `ClaudeCodeTool.delegate`, C6).
- **No second dry-run short-circuit.** As in 0004, the authoritative per-call
  short-circuit is each tool's `delegate` (C6/C8). This factory only decides
  whether to enter the sidecar.
- **Only sidecar-bearing backends touch `stack`.** `openclaude` and `openhands`
  register their process for RAII teardown; `claude_code` registers nothing (the
  subprocess is entered and reaped inside `delegate`).
- **Imports are the isolation surface.** This is the only file that may import
  `openclaude` **and** `claude_code` **and** `openhands`. The Task 11.0/13.0 grep
  isolation job asserts no other module imports more than one family and no
  backend package imports a sibling. Keep imports import-statement-level (no
  lazy in-function imports that would dodge the grep).
- **No secrets in construction.** Auth resolution for Claude Code (C7) happens
  inside `ClaudeCodeTool`/`ClaudeCodeSettings`; this factory never reads
  `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, or any credential, and never
  logs settings values.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- The backend-selection branch appears in **exactly one file** — `harness/composition.py` (generalized C4). Verifiable by grep; no other module branches on `active_backend` or on any per-family presence signal.
- `harness/composition.py` is the **only** module importing more than one backend family (C3, grep-enforced Task 11.0/13.0); no backend package imports a sibling.
- `code_intel/backend.py`, `agent.py`, `budget.py` are **not** modified; `CodeResult.token_estimate` keeps its name and `int` type (C9).
- `openclaude/composition.py` is deleted; its C4 logic is present **verbatim** in `harness/composition.py` (C4).
- `dry_run` never enters a sidecar and never opens a connection for any backend (C4 / C13); the object graph is still fully constructed and registered.

## Success criteria

- [ ] `src/aegis_swr/harness/composition.py` exists and exports `build_code_agent`.
- [ ] `src/aegis_swr/openclaude/composition.py` no longer exists.
- [ ] `build_code_agent` branches over all three backends plus the `None` case; the branch appears in **exactly one file** (grep-verifiable).
- [ ] `grep -R -E "import (aegis_swr\\.(openclaude|claude_code|openhands))"` shows more than one family imported **only** in `harness/composition.py`.
- [ ] `active_backend is None` → `CodeAgent(backend=None)`, `agent.available is False`, no exception (C2 row 1 / 0004 parity).
- [ ] The OpenClaude branch body matches the deleted `openclaude/composition.py` verbatim (diff-verifiable in review), including its dry-run distinction.
- [ ] Under `dry_run`, no sidecar `__aenter__` is called for `openclaude` or `openhands`, and no `Connected`/`Disconnected` event fires; `claude_code` registers no process either way.
- [ ] An explicitly-selected backend whose signal is absent surfaces `HarnessUnavailableError` at composition/health-check time (C2 last row).
- [ ] `code_intel/backend.py`, `agent.py`, `budget.py` are byte-for-byte unchanged (C9).
- [ ] `ruff check src/ tests/` - clean.
