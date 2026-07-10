"""Application composition root for Aegis SWR code intelligence.

This module is the **single place** where the optional OpenClaude code-
intelligence backend is wired into the generic ``code_intel`` scaffolding
(contract C4). The ``settings.grpc_url is not None`` branch that decides whether
a backend is registered lives here and **nowhere else**; no other module
branches on OpenClaude's presence.

Because ``app.py`` is the composition root, it is the only module (besides the
``openclaude`` package itself) permitted to import ``aegis_swr.openclaude``
(contract C3). The isolated ``aegis_swr.code_intel`` scaffolding never imports
its concrete backend; the backend is injected via constructor here.

Run directly as a smoke test of the wiring::

    python -m aegis_swr.app --dry-run

With ``OPENCLAUDE_GRPC_URL`` unset this reports code intelligence as
unavailable and exits cleanly. With it set and ``--dry-run`` supplied it builds
and registers the full OpenClaude object graph **without** entering the process
(no health check, no managed subprocess start) and without opening any gRPC
connection (contract C6 / the dry-run acceptance criteria).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from contextlib import AsyncExitStack
from typing import Optional, Sequence
from uuid import uuid4

from loguru import logger

from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.code_intel.backend import CodeBackend
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus

# OpenClaude imports are confined to this composition root (C3/C4). No other
# hand-written module imports ``aegis_swr.openclaude`` or ``grpc``.
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
    tool is injected as the sole :class:`CodeBackend`.

    ``dry_run`` is a separate axis from the ``grpc_url`` branch and must not be
    folded into it. Under ``dry_run`` the object graph is fully constructed and
    the backend registered (so composition is exercised), but the
    :class:`OpenClaudeProcess` is **not** entered — no C6 health check, no
    managed subprocess start, and therefore no ``OpenClaudeConnected`` /
    ``OpenClaudeDisconnected`` events. The gRPC channel is lazy (no socket until
    the first RPC) and ``OpenClaudeTool.delegate`` short-circuits on
    ``ctx.dry_run`` before any RPC, so the graph stays connection-free.

    The started :class:`OpenClaudeProcess` (non-dry-run only) is registered on
    *stack* so its shutdown — which emits ``OpenClaudeDisconnected`` (C6) — is
    tied to application lifetime (RAII), including on a startup failure raised
    after the port opened.

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
    backend: CodeBackend = OpenClaudeTool(client, settings, bus, budget)
    return CodeAgent(backend=backend)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse the composition-root smoke-test arguments.

    :param argv: Argument vector without the program name.
    :return: Parsed namespace carrying ``dry_run``.
    """
    parser = argparse.ArgumentParser(
        prog="python -m aegis_swr.app",
        description="Aegis SWR composition-root smoke test: build the code-intelligence agent.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exercise wiring only: register the backend without entering the "
        "OpenClaude process or opening any gRPC connection.",
    )
    return parser.parse_args(argv)


async def _amain(argv: Sequence[str]) -> int:
    """Async entry point: build the code agent and report its availability.

    :param argv: Argument vector without the program name.
    :return: Process exit code (``0`` on success).
    """
    args = _parse_args(argv)
    settings = OpenClaudeSettings()
    bus = EventBus()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(
            settings,
            bus,
            stack,
            run_id=str(uuid4()),
            dry_run=args.dry_run,
        )
        if agent.available:
            logger.info(
                "Code intelligence backend registered (OpenClaude){}.",
                " [dry-run: process not started]" if args.dry_run else "",
            )
        else:
            logger.info("Code intelligence unavailable (OPENCLAUDE_GRPC_URL unset).")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Synchronous console entry point wrapping :func:`_amain`.

    :param argv: Optional argument vector; defaults to ``sys.argv[1:]``.
    :return: Process exit code.
    """
    return asyncio.run(_amain(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
