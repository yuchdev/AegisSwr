"""Neutral code-intelligence composition root (the generalised C4 branch).

This module is the **one and only** place in Aegis SWR that branches on which
code-intelligence backend is active. It reads the resolved
:attr:`~aegis_swr.harness.config.HarnessSettings.active_backend` (resolved at
settings-construction time per C2, Task 01.0) and assembles exactly one backend
stack - or none - injecting it into a :class:`~aegis_swr.code_intel.agent.CodeAgent`.

Isolation (C3): this is the **only** module in the codebase permitted to import
more than one backend family. It imports all three (``openclaude``,
``claude_code``, ``openhands``) runtime classes; no backend package imports a
sibling, and ``code_intel/`` imports none of them. The generalisation is recorded
in `ADR 0004 <docs/adr/0004-harness-composition-generalization.md>`_.

``dry_run`` is **orthogonal** to backend selection: the object graph is fully
constructed and the backend registered so the composition path is exercised, but
no sidecar is entered and no outbound call is made (C4 / C13). For
``openclaude`` / ``openhands`` this means the sidecar ``__aenter__`` is skipped;
``claude_code`` has no sidecar, so the flag has no assembly-time effect there
(its short-circuit lives inside :meth:`ClaudeCodeTool.delegate`).
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Final

from loguru import logger

# The only cross-family imports in the codebase (C3). Each backend package is
# self-contained; only this module reaches across all three. Import-statement
# level (never lazy in-function) so the C3 isolation grep can see them.
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.code_intel.backend import CodeIntelBackend
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus
from aegis_swr.harness.config import HarnessSettings
from aegis_swr.harness.exceptions import HarnessUnavailableError
from aegis_swr.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis_swr.openclaude.process import OpenClaudeProcess
from aegis_swr.openclaude.tool import OpenClaudeTool
from aegis_swr.openhands.client import OpenHandsClient
from aegis_swr.openhands.process import OpenHandsProcess
from aegis_swr.openhands.tool import OpenHandsTool

#: Interim per-call boundary token ceiling for the Claude Code backend. Unlike
#: OpenClaude / OpenHands, ``ClaudeCodeSettings`` carries no ``max_response_tokens``
#: field (its token accounting is the *real* ``usage`` sum charged after
#: completion, C6.2/C9), so the composition root supplies a generous, non-limiting
#: single-call ceiling here. A configurable cap is deferred to app-wiring budget
#: scoping; this value only gates the ``delegate`` pre-check and is never a
#: credential or payload value.
_CLAUDE_CODE_BUDGET_TOKENS: Final[int] = 1_000_000


async def build_code_agent(
    harness: HarnessSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    run_id: str,
    dry_run: bool = False,
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
    :param bus: Shared :class:`~aegis_swr.core.events.EventBus` for the run; each
        backend emits its own ``DomainEvent`` taxonomy onto it (C10).
    :param stack: Application-lifetime :class:`~contextlib.AsyncExitStack`. Only
        sidecar-bearing backends (``openclaude``, ``openhands``) register a
        process on it for RAII teardown; ``claude_code`` (one-shot subprocess)
        registers nothing.
    :param run_id: Investigation run identifier, threaded onto emitted events.
    :param dry_run: When ``True``, construct + register but enter no sidecar and
        open no connection; each tool's ``delegate`` short-circuits on
        ``ctx.dry_run``.
    :raises HarnessUnavailableError: When an explicitly-selected backend's
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
        return await _build_openclaude(harness, bus, stack, run_id=run_id, dry_run=dry_run)
    if backend_name == "claude_code":
        return await _build_claude_code(harness, bus, stack, run_id=run_id, dry_run=dry_run)
    if backend_name == "openhands":
        return await _build_openhands(harness, bus, stack, run_id=run_id, dry_run=dry_run)

    # Unreachable while C2 resolution (Task 01.0) is correct; fail loud rather
    # than silently returning a backend-less agent for an unknown family name.
    raise HarnessUnavailableError(backend=backend_name, signals=harness.presence_signals)


async def _build_openclaude(
    harness: HarnessSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    run_id: str,
    dry_run: bool,
) -> CodeAgent:
    """Assemble the OpenClaude stack (assembly moved verbatim from 0004, C4).

    The ``OpenClaudeGrpcClient`` -> ``OpenClaudeProcess`` -> ``OpenClaudeTool``
    assembly - including the dry-run branch that constructs the graph but never
    enters the process (no C6 health check, no ``OpenClaudeConnected`` event) - is
    the 0004 factory body relocated unchanged. An explicitly-selected OpenClaude
    whose ``grpc_url`` presence signal is absent raises
    :class:`HarnessUnavailableError` here (C2 last row); the no-signal
    auto-select case never reaches this helper (handled by the ``None`` branch).

    :param harness: The composed ``settings.harness`` sub-settings.
    :param bus: Shared :class:`EventBus` for the run.
    :param stack: Application-lifetime :class:`AsyncExitStack`; the started
        process is registered for RAII teardown (non-dry-run only).
    :param run_id: Investigation run identifier stamped onto lifecycle events.
    :param dry_run: When ``True``, register the backend but neither enter the
        process nor open any gRPC connection.
    :raises HarnessUnavailableError: When ``grpc_url`` is unset for an
        explicitly-selected OpenClaude backend.
    :return: A :class:`CodeAgent` wired to the OpenClaude backend.
    """
    settings = harness.openclaude
    if settings.grpc_url is None:
        raise HarnessUnavailableError(backend="openclaude", signals=harness.presence_signals)

    client = OpenClaudeGrpcClient(settings)
    process = OpenClaudeProcess(settings, bus, run_id=run_id, client=client)
    if not dry_run:
        # Health-check (external) or start (managed) the sidecar; register the
        # process so __aexit__ (OpenClaudeDisconnected, C6) always runs on
        # shutdown, even if a later startup step raises after the port opened.
        await stack.enter_async_context(process)

    budget = CallBudget(max_tokens=settings.max_response_tokens)
    backend: CodeIntelBackend = OpenClaudeTool(client, settings, bus, budget)
    return CodeAgent(backend=backend)


async def _build_claude_code(
    harness: HarnessSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    run_id: str,
    dry_run: bool,
) -> CodeAgent:
    """Assemble the Claude Code stack (one-shot subprocess; no sidecar).

    Nothing is registered on *stack*: :class:`ClaudeCodeTool` spawns and reaps a
    ``claude`` subprocess per ``delegate()`` call (C6), so there is no long-lived
    resource to enter - *stack* and *run_id* are accepted only for dispatch
    uniformity. The auth mode is resolved per C7 inside the tool from
    ``harness.claude_code`` (already validated at settings-construction time);
    this helper never reads a credential. Even under ``dry_run`` the tool is
    constructed so the composition path is exercised; the startup auth-probe (C7)
    is a runtime concern the tool gates on ``dry_run``. An explicitly-selected
    Claude Code backend whose ``enabled`` presence signal is absent raises
    :class:`HarnessUnavailableError` (C2 last row).

    :param harness: The composed ``settings.harness`` sub-settings.
    :param bus: Shared :class:`EventBus` for the run.
    :param stack: Unused; Claude Code registers no sidecar (kept for dispatch
        uniformity).
    :param run_id: Unused at construction; the tool stamps run ids per call.
    :param dry_run: Accepted for signature uniformity; has no assembly-time
        effect (the tool short-circuits ``dry_run`` inside ``delegate``).
    :raises HarnessUnavailableError: When ``enabled`` is ``False`` for an
        explicitly-selected Claude Code backend.
    :return: A :class:`CodeAgent` wired to the Claude Code backend.
    """
    settings = harness.claude_code
    if not settings.enabled:
        raise HarnessUnavailableError(backend="claude_code", signals=harness.presence_signals)

    budget = CallBudget(max_tokens=_CLAUDE_CODE_BUDGET_TOKENS)
    backend: CodeIntelBackend = ClaudeCodeTool(settings, bus, budget)
    return CodeAgent(backend=backend)


async def _build_openhands(
    harness: HarnessSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    run_id: str,
    dry_run: bool,
) -> CodeAgent:
    """Assemble the OpenHands stack (Docker-sandboxed sidecar over REST/WS).

    Mirrors the OpenClaude sidecar pattern (C8): the :class:`OpenHandsProcess` is
    registered on *stack* for RAII teardown in a real run; under ``dry_run`` the
    process is not entered (no connection) but the tool is still constructed and
    registered so the composition path is exercised. An explicitly-selected
    OpenHands backend whose ``server_url`` presence signal is absent raises
    :class:`HarnessUnavailableError` here (C2 last row).

    :param harness: The composed ``settings.harness`` sub-settings.
    :param bus: Shared :class:`EventBus` for the run.
    :param stack: Application-lifetime :class:`AsyncExitStack`; the started
        process is registered for RAII teardown (non-dry-run only).
    :param run_id: Investigation run identifier stamped onto lifecycle events.
    :param dry_run: When ``True``, register the backend but neither enter the
        process nor open any REST/WS connection.
    :raises HarnessUnavailableError: When ``server_url`` is unset for an
        explicitly-selected OpenHands backend.
    :return: A :class:`CodeAgent` wired to the OpenHands backend.
    """
    settings = harness.openhands
    if settings.server_url is None:
        raise HarnessUnavailableError(backend="openhands", signals=harness.presence_signals)

    process = OpenHandsProcess(settings, bus, run_id)
    if not dry_run:
        # Health-check (external) or start (managed) the sidecar; register the
        # process so __aexit__ (OpenHandsDisconnected, C8) always runs on shutdown.
        await stack.enter_async_context(process)

    client = OpenHandsClient(settings)
    budget = CallBudget(max_tokens=settings.max_response_tokens)
    backend: CodeIntelBackend = OpenHandsTool(client, settings, bus, budget)
    return CodeAgent(backend=backend)
