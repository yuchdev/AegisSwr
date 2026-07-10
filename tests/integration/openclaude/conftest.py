"""Fixtures and skip guards for the live OpenClaude integration suite (Task 08.0).

Single source of truth for *when* the integration suite runs and *how* a live
OpenClaude sidecar is stood up and guaranteed to be torn down. Every downstream
integration module calls one of the module-level guards
(:func:`require_managed_openclaude` / :func:`require_external_openclaude`) at
import time, so an absent binary or an unset ``OPENCLAUDE_INTEGRATION`` signal
produces exactly **one** clean ``skipped`` line per module — never a failure.

The suite is gated behind ``OPENCLAUDE_INTEGRATION`` (the CI wiring that sets it
lives in Task 09.0); this module only *reads* the signal. Live fixtures use the
real, shipped APIs — ``OpenClaudeProcess(settings, bus, run_id)``,
``OpenClaudeGrpcClient(settings)`` — with **zero** mocks, and every process is
terminated in a ``finally`` finalizer even when the consuming test raises.
"""

from __future__ import annotations

import os
import shutil
import textwrap
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from aegis_swr.core.events import EventBus
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis_swr.openclaude.process import OpenClaudeProcess


# --------------------------------------------------------------------------- #
# Skip-guard predicates
# --------------------------------------------------------------------------- #
def _integration_enabled() -> bool:
    """True only when the CI/local signal opts into live integration (Task 09.0)."""
    return bool(os.environ.get("OPENCLAUDE_INTEGRATION"))


def _binary_present(settings: OpenClaudeSettings) -> bool:
    """True when ``settings.process_binary`` resolves on PATH or as an absolute path."""
    return shutil.which(settings.process_binary) is not None


def _grpc_url_set() -> bool:
    """True when ``OPENCLAUDE_GRPC_URL`` is set in the environment."""
    return bool(os.environ.get("OPENCLAUDE_GRPC_URL"))


def require_managed_openclaude() -> None:
    """Module-level guard for managed-mode tests.

    Call once at the top of a test module (after imports). Emits a single
    module-level skip when the integration signal is off or the ``openclaude``
    binary is missing. Never apply per-test.
    """
    if not _integration_enabled():
        pytest.skip("OPENCLAUDE_INTEGRATION not set", allow_module_level=True)
    if not _binary_present(OpenClaudeSettings()):
        pytest.skip("openclaude binary not on PATH", allow_module_level=True)


def require_external_openclaude() -> None:
    """Module-level guard for external-mode-only tests.

    As :func:`require_managed_openclaude`, but additionally requires a set
    ``OPENCLAUDE_GRPC_URL`` since these tests do not start their own process.
    """
    require_managed_openclaude()
    if not _grpc_url_set():
        pytest.skip("OPENCLAUDE_GRPC_URL not set", allow_module_level=True)


# --------------------------------------------------------------------------- #
# Throwaway stub project (never the Aegis SWR source tree)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def stub_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tiny, disposable Python project for OpenClaude to navigate read-only.

    Contains a uniquely named symbol (``compute_checksum``) the model must
    *discover* via ``Read``/``Grep``/``Glob`` rather than guess from priors.
    """
    root = tmp_path_factory.mktemp("openclaude_stub")
    (root / "app.py").write_text(
        textwrap.dedent(
            '''\
            """Throwaway stub for OpenClaude integration navigation."""


            def compute_checksum(payload: bytes) -> int:
                """A uniquely named function the model must FIND, not guess."""
                return sum(payload) % 65521
            '''
        ),
        encoding="utf-8",
    )
    (root / "helpers.py").write_text("# calls compute_checksum somewhere\n", encoding="utf-8")
    return root


# --------------------------------------------------------------------------- #
# Live managed-mode process + connected client
# --------------------------------------------------------------------------- #
def managed_settings() -> OpenClaudeSettings:
    """Managed-mode settings with free-port selection and the read-only allowlist."""
    return OpenClaudeSettings(auto_start=True, grpc_url="localhost:0")


@pytest_asyncio.fixture(scope="module")
async def live_openclaude_process(stub_project: Path) -> AsyncIterator[OpenClaudeProcess]:
    """A real managed-mode :class:`OpenClaudeProcess`, torn down unconditionally.

    Module-scoped because starting a real Node.js sidecar and warming a model is
    expensive; shared across a module's read-only tests. The ``finally`` block
    drives ``__aexit__`` even on test failure, upholding the "no surviving
    process" guarantee. Lifecycle tests that must observe start/stop construct
    their own process instead of using this fixture.

    **Working-directory note.** The sidecar process always runs under
    ``_SAFE_CWD`` (``tempfile.gettempdir()`` — a fixed, attacker-neutral
    directory defined in ``aegis_swr.openclaude.process``). It does **not**
    run from ``stub_project``. Navigation tasks must therefore reference stub
    files by their *absolute* path in the task prompt so the sidecar can
    locate them without assuming a particular cwd.

    The ``stub_project`` dependency is declared here only to guarantee the
    stub tree is created and lives on disk for the full duration of this
    module's test run.

    # NOTE: rooting the sidecar at the stub project (i.e. passing ``cwd``
    # to ``OpenClaudeProcess``) is the proper long-term fix, but that
    # requires a ``cwd`` seam on :class:`OpenClaudeProcess.__init__` in
    # ``src/aegis_swr/openclaude/process.py``.  Until that seam is added,
    # callers must embed the absolute stub path in their task prompts.
    """
    process = OpenClaudeProcess(managed_settings(), EventBus(), run_id=str(uuid.uuid4()))
    await process.__aenter__()
    try:
        yield process
    finally:
        await process.__aexit__(None, None, None)


@pytest_asyncio.fixture(scope="module")
async def live_grpc_client(
    live_openclaude_process: OpenClaudeProcess,
) -> AsyncIterator[OpenClaudeGrpcClient]:
    """An :class:`OpenClaudeGrpcClient` connected to the running managed process."""
    client = OpenClaudeGrpcClient(OpenClaudeSettings(grpc_url=live_openclaude_process.grpc_url))
    try:
        yield client
    finally:
        await client.close()
