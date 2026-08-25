"""Fixtures and skip guards for the live OpenHands integration suite (Task 12.0/02).

Single source of truth for *when* the OpenHands integration suite runs and
*how* a live sidecar process and client are stood up and guaranteed to be torn
down. Every downstream test module calls :func:`require_openhands` at import
time, so an absent ``OPENHANDS_SERVER_URL``, an unreachable Docker daemon, or a
missing ``python-socketio`` package produces exactly **one** clean ``skipped``
line per module — never a failure or a collection crash.

**Wire-shape caveat.** The OpenHands REST/WS shapes used by
:class:`~aegis_swr.openhands.client.OpenHandsClient` (``POST /api/conversations``,
Socket.IO ``oh_event`` / ``oh_user_action`` messages, and the raw event dict
projected by ``_to_event``) follow the researched V1-server names recorded in
Task 07.0 but have **never been validated against a live OpenHands server**.
The first successful run of this integration suite should be treated as a
**contract-discovery exercise**: treat any assertion failure as a potential
wire-shape mismatch before assuming a test bug.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess  # nosec B404 — fixed argv "docker info" probe, no shell, no payload
import textwrap
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from loguru import logger

from aegis_swr.core.events import EventBus
from aegis_swr.openhands.client import OpenHandsClient
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.process import OpenHandsProcess

# Module-level socketio availability check — uses importlib.util.find_spec to
# avoid a try/except ImportError (which would trip X010). The OpenHands client
# guards its own import the same way; we mirror that check here so the guard
# can skip before any socketio-dependent code path is exercised.
_SOCKETIO_AVAILABLE: bool = importlib.util.find_spec("socketio") is not None


# --------------------------------------------------------------------------- #
# Skip-guard predicates
# --------------------------------------------------------------------------- #


def _server_url_set() -> bool:
    """True when the ``OPENHANDS_SERVER_URL`` presence signal is set (C8).

    :return: Whether the server URL env var is configured.
    """
    return bool(os.environ.get("OPENHANDS_SERVER_URL"))


def _docker_available() -> bool:
    """True only when a Docker daemon is actually reachable.

    Probes ``docker info`` under a short timeout. Any failure — ``docker`` not on
    PATH, daemon down, permission denied, or timeout — returns ``False`` so the
    guard **skips** rather than **fails**. The probe uses a fixed argv (no shell,
    no payload text) and never raises out of this function.

    :return: Whether the Docker daemon is reachable at probe time.
    """
    if shutil.which("docker") is None:
        return False
    outcome = False
    try:
        completed = subprocess.run(  # nosec B603 — fixed argv, no shell, no untrusted input
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        outcome = completed.returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug(
            "Docker probe failed ({}); treating daemon as unreachable",
            type(exc).__name__,
        )
    return outcome


# --------------------------------------------------------------------------- #
# Module-level guard (one clean skip line per module; never per-test)
# --------------------------------------------------------------------------- #


def require_openhands():
    """Guard: skip unless all three conditions are met.

    1. ``OPENHANDS_SERVER_URL`` is set (C8 presence signal).
    2. A Docker daemon is reachable (the suite's defining security property).
    3. ``python-socketio`` is installed (the OpenHands transport library).

    Call once at the top of a test module, after imports. Emits a single
    module-level skip for the first unmet condition — never a failure, never a
    collection crash, even when the daemon is completely down.
    """
    if not _server_url_set():
        pytest.skip("OPENHANDS_SERVER_URL not set", allow_module_level=True)
    if not _docker_available():
        pytest.skip("Docker daemon not reachable", allow_module_level=True)
    if not _SOCKETIO_AVAILABLE:
        pytest.skip("python-socketio not installed", allow_module_level=True)


# --------------------------------------------------------------------------- #
# Disposable stub project (never the Aegis SWR source tree)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def stub_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tiny, disposable Python project mounted into the sandbox for navigation.

    Contains a uniquely named symbol (``compute_checksum``) the model must
    *discover* via read-only tools rather than guess from priors. Task prompts
    reference stub files by absolute path so the sandboxed runtime can locate
    them without assuming a particular working directory.

    :param tmp_path_factory: pytest temporary-path factory (module-scoped).
    :return: Path to the created stub project root.
    """
    root = tmp_path_factory.mktemp("openhands_stub")
    (root / "app.py").write_text(
        textwrap.dedent(
            '''\
            """Throwaway stub for OpenHands integration navigation."""


            def compute_checksum(payload: bytes) -> int:
                """A uniquely named function the model must FIND, not guess."""
                return sum(payload) % 65521
            '''
        ),
        encoding="utf-8",
    )
    return root


# --------------------------------------------------------------------------- #
# Live sidecar process + connected client
# --------------------------------------------------------------------------- #


def _external_settings() -> OpenHandsSettings:
    """Return external-mode settings pointing at the already-running server URL (C8).

    Uses the Docker-sandboxed runtime by default; no non-sandboxed override.

    :return: :class:`OpenHandsSettings` sourced from ``OPENHANDS_SERVER_URL``.
    """
    return OpenHandsSettings(server_url=os.environ["OPENHANDS_SERVER_URL"])


@pytest_asyncio.fixture(scope="module")
async def live_openhands_process() -> AsyncIterator[OpenHandsProcess]:
    """A real :class:`OpenHandsProcess` health-checking the running sidecar.

    Module-scoped because connecting and warming a sandboxed runtime is
    expensive; shared across the module's read-only tests. The ``finally`` block
    drives ``__aexit__`` even on test failure, upholding the "no surviving
    session" guarantee. Lifecycle tests that must observe start/stop must
    construct their own process instead of using this fixture.

    :return: An async iterator yielding the live sidecar process for the module.
    """
    process = OpenHandsProcess(_external_settings(), EventBus(), "integration-run")
    await process.__aenter__()
    try:
        yield process
    finally:
        await process.__aexit__(None, None, None)


@pytest_asyncio.fixture(scope="module")
async def live_openhands_client(
    live_openhands_process: OpenHandsProcess,
) -> AsyncIterator[OpenHandsClient]:
    """An :class:`OpenHandsClient` connected to the running sidecar.

    Depends on ``live_openhands_process`` to ensure the sidecar is healthy
    before the client is used. The ``finally`` block closes the client even on
    test failure (no lingering connection).

    :param live_openhands_process: The live sidecar process fixture.
    :return: An async iterator yielding the connected client for the module.
    """
    client = OpenHandsClient(_external_settings())
    try:
        yield client
    finally:
        await client.close()
