# 01 - `integration/conftest.py` + skip guards

**Parent task:** 08.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** none upstream (this subtask is the foundation); exercises 01.0 (`OpenClaudeSettings`), 03.0 (`OpenClaudeProcess`), 02.0 (`OpenClaudeGrpcClient`) live
**Blocks:** 02, 03, 04, 05 (every other integration subtask depends on these fixtures and guards)

## Objective

Provide the single source of truth for *when the integration suite runs* and *how a
live OpenClaude process is stood up and guaranteed to be torn down*. This subtask
authors `tests/openclaude/integration/conftest.py`: a **module-level** skip guard
that removes the entire suite from a run when the `openclaude` binary is absent
from `PATH`/`settings.process_binary`, when the `OPENCLAUDE_INTEGRATION` signal is
unset, or (for external-mode-only tests) when `OPENCLAUDE_GRPC_URL` is unset; a
`live_openclaude_process` managed-mode fixture that launches a real
`OpenClaudeProcess` against a disposable Python stub project generated in a temp
directory and tears it down in a finalizer even on test failure; and a
`live_grpc_client` fixture bound to that running process. Every downstream
integration test consumes these fixtures rather than starting its own process, so
that "no OpenClaude process survives the session" is enforced in exactly one place.

## File: `tests/openclaude/integration/conftest.py`

```python
from __future__ import annotations

import os
import shutil
import textwrap
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from aegis.core.events import EventBus
from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis.openclaude.process import OpenClaudeProcess

# --- Skip-guard predicates -------------------------------------------------

def _integration_enabled() -> bool:
    """True only when the CI/local signal opts into live integration (task 09.0)."""
    return bool(os.environ.get("OPENCLAUDE_INTEGRATION"))


def _binary_present(settings: OpenClaudeSettings) -> bool:
    """True when settings.process_binary resolves on PATH or as an absolute path."""
    return shutil.which(settings.process_binary) is not None


def _grpc_url_set() -> bool:
    return bool(os.environ.get("OPENCLAUDE_GRPC_URL"))


def require_managed_openclaude():
    """Module-level guard for managed-mode tests.

    Call once at the top of a test module (after imports). Raises a single
    module-level skip — producing ONE clean "skipped" summary line for the whole
    module — when the integration signal is off or the binary is missing. Do NOT
    apply this per-test.
    """
    if not _integration_enabled():
        pytest.skip("OPENCLAUDE_INTEGRATION not set", allow_module_level=True)
    if not _binary_present(OpenClaudeSettings()):
        pytest.skip("openclaude binary not on PATH", allow_module_level=True)


def require_external_openclaude():
    """Module-level guard for external-mode-only tests.

    Same as :func:`require_managed_openclaude` but also requires a reachable
    OPENCLAUDE_GRPC_URL, since these tests do not start their own process.
    """
    require_managed_openclaude()
    if not _grpc_url_set():
        pytest.skip("OPENCLAUDE_GRPC_URL not set", allow_module_level=True)


# --- Throwaway stub project ------------------------------------------------

@pytest.fixture(scope="module")
def stub_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tiny, disposable Python project OpenClaude will navigate.

    NEVER the Aegis SWR source tree. Contains a couple of files with a known
    symbol so a navigation task has something real to discover via Read/Grep.
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
        )
    )
    (root / "helpers.py").write_text("# calls compute_checksum somewhere\n")
    return root


# --- Live process + client -------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def live_openclaude_process(stub_project: Path) -> AsyncIterator[OpenClaudeProcess]:
    """A real OpenClaudeProcess in MANAGED mode against the stub project.

    Module-scoped by deliberate choice: starting a real Node.js OpenClaude
    sidecar, waiting for its gRPC port, and warming a model is multi-second and
    expensive, so it is shared across a module's read-only tests. A finalizer
    always drives __aexit__, so the process is terminated (SIGTERM→SIGKILL) even
    if a test raises inside the `with`-equivalent body. Tests that must assert on
    start/stop themselves (subtask 02) do NOT use this fixture — they construct
    their own OpenClaudeProcess.
    """
    settings = OpenClaudeSettings(
        auto_start=True,
        grpc_url="localhost:0",  # free-port selection (C6 / task 03.0)
        # default allowed_tools = Read,Grep,Glob,Bash — read-only forensic set
    )
    bus = EventBus()
    process = OpenClaudeProcess(settings=settings, event_bus=bus, cwd=stub_project)
    await process.__aenter__()
    try:
        yield process
    finally:
        # Runs even on test failure — the "no surviving process" guarantee.
        await process.__aexit__(None, None, None)


@pytest_asyncio.fixture(scope="module")
async def live_grpc_client(
    live_openclaude_process: OpenClaudeProcess,
) -> AsyncIterator[OpenClaudeGrpcClient]:
    """An OpenClaudeGrpcClient connected to the running managed process."""
    client = OpenClaudeGrpcClient.from_url(
        live_openclaude_process.grpc_url,
        OpenClaudeSettings(grpc_url=live_openclaude_process.grpc_url),
    )
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture(scope="module")
def event_bus_from_process(live_openclaude_process: OpenClaudeProcess) -> EventBus:
    """The EventBus the live process emits lifecycle events on (recording)."""
    ...
```

## Test cases

This subtask ships no test functions of its own — it is pure fixture/guard
infrastructure. Its behavior is validated indirectly by subtasks 02–05:

- `require_managed_openclaude()` / `require_external_openclaude()` — invoked at the
  top of every downstream test module; when the guard fires, the module reports a
  single skip line rather than N per-test skips.
- `live_openclaude_process` — provides a warmed, real managed-mode process to
  subtasks 03, 04, 05; guarantees teardown via the `finally` finalizer.
- `live_grpc_client` — provides a connected client to subtask 03.
- `stub_project` — provides the disposable navigation target for 03, 04, 05.

## Constraints

- Skip logic is **module-level** (`pytest.skip(..., allow_module_level=True)`),
  never per-test, so one absent binary yields one clean "skipped" line per module.
- Gated behind `OPENCLAUDE_INTEGRATION`; the CI wiring that sets it is added in
  task 09.0. This subtask only *reads* the signal and documents the dependency —
  it does not add the CI job.
- Tests that DO run must be fully live — zero mocks in the fixtures here.
- No integration run may leave a running OpenClaude process: teardown is a
  `finally`/finalizer that drives `__aexit__` even when the test body raises.
- The stub project is generated in a `tmp_path_factory` temp directory, is
  **never** the Aegis SWR source tree, and the process runs strictly read-only
  under the default allowlist (`Read,Grep,Glob,Bash`; no `Write`/`Edit`).
- `from __future__ import annotations`; `Optional[T]` from `typing`, never
  `T | None`; `ruff` clean (test tree still linted).
- No raw stub-file contents or streamed response text is logged (C9); loguru sinks
  keep `SensitiveFilter`.

## Success criteria

- [ ] `tests/openclaude/integration/conftest.py` exists with
      `require_managed_openclaude()` and `require_external_openclaude()` guards.
- [ ] With `OPENCLAUDE_INTEGRATION` unset, the whole integration suite reports
      **skipped** (one line per module), never failed.
- [ ] With the signal set but no `openclaude` binary on `PATH`, the suite still
      reports skipped, never failed or errored.
- [ ] `live_openclaude_process` starts a real managed-mode process and its
      finalizer terminates it even when the consuming test raises.
- [ ] After a full integration run, no OpenClaude process remains (verifiable by
      PID/process-table check in subtask 02).
- [ ] `live_grpc_client` connects to the managed process and is closed on teardown.
- [ ] `stub_project` is created under a temp dir and is never the repo source tree.
- [ ] `ruff check src/ tests/` - clean on the file.
