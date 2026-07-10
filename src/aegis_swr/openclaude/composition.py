"""Composition factory for the OpenClaude code-intelligence stack.

This module is the **single place** where the optional OpenClaude backend is
wired into the generic :mod:`aegis_swr.code_intel` scaffolding (contract C4).
The ``settings.grpc_url is not None`` branch that decides whether a backend is
registered lives here and **nowhere else**; no other module branches on
OpenClaude's presence.

It is deliberately located inside the ``openclaude`` package — the concrete
backend family — mirroring the repository's Factory-Strategy convention where
each backend family owns its ``create_*`` factory (e.g.
:func:`aegis_swr.backends.ai.create_ai_backend`). Because
:mod:`aegis_swr.code_intel` may **not** import ``aegis_swr.openclaude`` (C3
isolation, enforced by ``tests/unit/openclaude/test_isolation.py`` and the CI
``openclaude-isolation`` job), the factory that needs both cannot live in
``code_intel/``; it belongs here, alongside the stack it assembles. The CLI
(:mod:`aegis_swr.cli`) is the composition root that calls it.

The generic :mod:`aegis_swr.code_intel` scaffolding never imports its concrete
backend; the backend is injected via constructor here.
"""

from __future__ import annotations

from contextlib import AsyncExitStack

from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.code_intel.backend import CodeIntelBackend
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis_swr.openclaude.process import OpenClaudeProcess
from aegis_swr.openclaude.tool import OpenClaudeTool


async def build_code_agent(
    settings: OpenClaudeSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    run_id: str,
    dry_run: bool = False,
) -> CodeAgent:
    """Construct the :class:`CodeAgent`, wiring OpenClaude when configured.

    The ``settings.grpc_url is not None`` branch lives **only here** (C4). When
    it is ``None`` the agent is built with no backend and the capability is
    reported unavailable — there are no sibling backends to fall back to.

    When ``grpc_url`` is set, the OpenClaude stack
    (:class:`~aegis_swr.openclaude.grpc.client.OpenClaudeGrpcClient` →
    :class:`~aegis_swr.openclaude.process.OpenClaudeProcess` →
    :class:`~aegis_swr.openclaude.tool.OpenClaudeTool`) is constructed and the
    tool is injected as the sole :class:`CodeIntelBackend`.

    ``dry_run`` is a separate axis from the ``grpc_url`` branch and must not be
    folded into it. Under ``dry_run`` the object graph is fully constructed and
    the backend registered (so composition is exercised), but the
    :class:`~aegis_swr.openclaude.process.OpenClaudeProcess` is **not** entered —
    no C6 health check, no managed subprocess start, and therefore no
    ``OpenClaudeConnected`` / ``OpenClaudeDisconnected`` events. The gRPC channel
    is lazy (no socket until the first RPC) and ``OpenClaudeTool.delegate``
    short-circuits on ``ctx.dry_run`` before any RPC, so the graph stays
    connection-free.

    The started :class:`~aegis_swr.openclaude.process.OpenClaudeProcess`
    (non-dry-run only) is registered on *stack* so its shutdown — which emits
    ``OpenClaudeDisconnected`` (C6) — is tied to application lifetime (RAII),
    including on a startup failure raised after the port opened.

    :param settings: The composed ``settings.openclaude`` sub-settings.
    :param bus: Shared :class:`~aegis_swr.core.events.EventBus` for the run.
    :param stack: Application-lifetime :class:`~contextlib.AsyncExitStack`.
    :param run_id: Investigation run identifier stamped onto lifecycle events.
    :param dry_run: When ``True``, register the backend but neither enter the
        process nor open any gRPC connection.
    :return: A configured :class:`CodeAgent`.
    """
    if settings.grpc_url is None:
        return CodeAgent(backend=None)

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
