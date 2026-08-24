# 02 - `tests/integration/openhands/` live suite

**Parent task:** 12.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** none upstream (self-contained infrastructure and tests); exercises 06.0 (`OpenHandsSettings`), 07.0 (`OpenHandsClient`/`process.py`), 08.0 (`OpenHandsTool`), 09.0 (`openhands.*` events) **live**
**Blocks:** none

## Objective

Stand up the live OpenHands integration suite and its skip guards, and prove a
real `OpenHandsTool.delegate()` flows end to end through a running OpenHands
sidecar over REST/WS to a well-formed `CodeResult`. Two availability conditions
gate the suite, and both must **skip, never fail** when unmet:

1. The `OPENHANDS_SERVER_URL` presence signal must be set (C8) — mirroring
   OpenClaude's URL-presence guard.
2. A **Docker daemon must be reachable** — OpenHands' distinguishing property is
   that it runs its navigation tools inside a Docker-sandboxed runtime (C8), so
   the guard probes the daemon (`docker info` under a timeout inside a `try`) and
   maps any failure — daemon down, `docker` not installed, permission error — to
   a clean module-level skip rather than a collection crash. Docker-on-Windows is
   a new operator prerequisite for this backend (flagged for the README in task
   13.0).

The load-bearing assertion is **sandbox verification**: the suite proves the
delegated task genuinely executed inside the Docker runtime, not on the host. It
does so by asking the runtime to report a container-only signal (the presence of
`/.dockerenv`, which Docker always creates inside a container) and asserting that
 the signal is observed **while the same file does not exist on the test host** — so a
pass cannot be explained by the task having run on the host.

## File: `tests/integration/openhands/conftest.py`

```python
from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - fixed argv "docker info" probe, no shell, no payload
import textwrap
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from aegis_swr.core.events import EventBus
from aegis_swr.openhands.client import OpenHandsClient
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.process import OpenHandsProcess


# --------------------------------------------------------------------------- #
# Skip-guard predicates
# --------------------------------------------------------------------------- #
def _server_url_set() -> bool:
    """True when the ``OPENHANDS_SERVER_URL`` presence signal is set (C8)."""
    return bool(os.environ.get("OPENHANDS_SERVER_URL"))


def _docker_available() -> bool:
    """True only when a Docker daemon is actually reachable.

    Probes ``docker info`` under a short timeout. Any failure — ``docker`` not on
    PATH, daemon down, permission denied, or timeout — returns ``False`` so the
    guard SKIPS rather than FAILS. The probe uses a fixed argv (no shell, no
    payload text) and never raises out of this function.
    """
    if shutil.which("docker") is None:
        return False
    try:
        completed = subprocess.run(  # nosec B603 - fixed argv, no shell, no untrusted input
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


# --------------------------------------------------------------------------- #
# Module-level guard (one clean skip line per module; never per-test)
# --------------------------------------------------------------------------- #
def require_openhands() -> None:
    """Guard: skip unless the server URL is set AND a Docker daemon is reachable.

    Call once at the top of a test module, after imports. Emits a single
    module-level skip when ``OPENHANDS_SERVER_URL`` is unset or Docker is
    unreachable — never a failure, even when the daemon is down.
    """
    if not _server_url_set():
        pytest.skip("OPENHANDS_SERVER_URL not set", allow_module_level=True)
    if not _docker_available():
        pytest.skip("Docker daemon not reachable", allow_module_level=True)


# --------------------------------------------------------------------------- #
# Disposable stub project (never the Aegis SWR source tree)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def stub_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tiny, disposable Python project mounted into the sandbox for navigation.

    Contains a uniquely named symbol (``compute_checksum``) the model must
    *discover* via read-only tools rather than guess from priors.
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
    """External-mode settings pointing at the already-running server URL (C8).

    Uses the Docker-sandboxed runtime by default; no non-sandboxed override.
    """
    return OpenHandsSettings(server_url=os.environ["OPENHANDS_SERVER_URL"])


@pytest_asyncio.fixture(scope="module")
async def live_openhands_process() -> AsyncIterator[OpenHandsProcess]:
    """A real :class:`OpenHandsProcess` health-checking the running sidecar.

    Module-scoped because connecting and warming a sandboxed runtime is
    expensive; shared across the module's read-only tests. The ``finally`` block
    drives ``__aexit__`` even on test failure, so no sidecar session survives.
    """
    process = OpenHandsProcess(_external_settings(), EventBus())
    await process.__aenter__()
    try:
        yield process
    finally:
        await process.__aexit__(None, None, None)


@pytest_asyncio.fixture(scope="module")
async def live_openhands_client(
    live_openhands_process: OpenHandsProcess,
) -> AsyncIterator[OpenHandsClient]:
    """An :class:`OpenHandsClient` connected to the running sidecar."""
    client = OpenHandsClient(_external_settings())
    try:
        yield client
    finally:
        await client.close()
```

## File: `tests/integration/openhands/test_delegate_live.py`

```python
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

import pytest

from aegis_swr.code_intel.backend import CodeTaskContext
from aegis_swr.core.events import EventBus
from aegis_swr.openhands.client import OpenHandsClient
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.events import OpenHandsAction, OpenHandsCompleted
from aegis_swr.openhands.tool import OpenHandsTool

from tests.integration.openhands.conftest import require_openhands

require_openhands()  # module-level: one skip line when URL unset or Docker unreachable

pytestmark = pytest.mark.asyncio


def _build_tool(client: OpenHandsClient, bus: EventBus) -> OpenHandsTool:
    return OpenHandsTool(
        client=client,
        settings=OpenHandsSettings(server_url=os.environ["OPENHANDS_SERVER_URL"]),
        event_bus=bus,
    )


async def test_delegate_returns_code_result_shape(
    live_openhands_client: OpenHandsClient,
    stub_project: Path,
):
    """A live delegate() against the running sidecar returns a real CodeResult."""
    bus = EventBus()
    tool = _build_tool(live_openhands_client, bus)
    result = await tool.delegate(
        task=f"Find compute_checksum under {stub_project} and name its file.",
        ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
    )
    assert result.available is True
    assert result.content.strip()
    assert result.token_estimate > 0
    ...


async def test_at_least_one_action_emitted(
    live_openhands_client: OpenHandsClient,
    stub_project: Path,
):
    """>=1 openhands.action proves real navigation, not an answer from priors."""
    bus = EventBus()
    seen: list[object] = []
    bus.subscribe(seen.append)

    tool = _build_tool(live_openhands_client, bus)
    await tool.delegate(
        task=f"Grep for compute_checksum under {stub_project} and report its file.",
        ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
    )
    assert any(isinstance(e, OpenHandsAction) for e in seen)
    ...


async def test_task_executes_inside_docker_sandbox(
    live_openhands_client: OpenHandsClient,
):
    """Sandbox verification: the task ran INSIDE the container, not on the host.

    ``/.dockerenv`` exists inside every Docker container but not on a normal host.
    First assert the host does not have it (sanity), then ask the runtime to
    report whether it can see ``/.dockerenv`` and assert it does — a pass that
    cannot be explained by the task having executed on the host.
    """
    assert not Path("/.dockerenv").exists(), "test host unexpectedly looks containerised"

    bus = EventBus()
    tool = _build_tool(live_openhands_client, bus)
    result = await tool.delegate(
        task=(
            "Report exactly whether the file /.dockerenv exists in your working "
            "environment. Answer with the single token DOCKERENV_PRESENT if it "
            "exists, or DOCKERENV_ABSENT if it does not."
        ),
        ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
    )
    assert "DOCKERENV_PRESENT" in result.content, (
        "task did not run inside the Docker sandbox (C8)"
    )
    ...


async def test_completed_event_carries_token_estimate(
    live_openhands_client: OpenHandsClient,
    stub_project: Path,
):
    """Exactly one openhands.completed carries the token figure (C9)."""
    bus = EventBus()
    seen: list[object] = []
    bus.subscribe(seen.append)

    tool = _build_tool(live_openhands_client, bus)
    await tool.delegate(
        task=f"Locate compute_checksum under {stub_project}.",
        ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
    )
    completed = [e for e in seen if isinstance(e, OpenHandsCompleted)]
    assert len(completed) == 1
    assert completed[0].token_estimate > 0  # server usage when available, else boundary
    ...
```

## Test cases

- `test_delegate_returns_code_result_shape` — a live `delegate()` against the
  running sidecar returns a `CodeResult` with `available is True`, non-empty
  `content`, and a positive `token_estimate`.
- `test_at_least_one_action_emitted` — at least one `openhands.action` event is
  emitted, proving the runtime drove its own tool loop over the stub project
  rather than answering from priors.
- `test_task_executes_inside_docker_sandbox` — the **sandbox-verification**
  assertion: the host lacks `/.dockerenv`, yet the runtime reports it presents,
  proving the task executed inside the Docker container, not on the host (C8).
- `test_completed_event_carries_token_estimate` — exactly one
  `openhands.completed` event carries the token figure, and it is strictly
  positive (server-reported usage when available, else the boundary estimate, C9).

## Implementation notes

- The Docker probe deliberately lives in the guard, not the test body: an
  unreachable daemon must skip the whole module, not fail a test mid-run. It uses
  a fixed argv (`docker info`) with a timeout and swallows every failure into a
  `False` return, so a broken Docker environment cannot crash a collection.
- The suite runs in **external mode** — it health checks the already-running
  server at `OPENHANDS_SERVER_URL` rather than launching one — because the
  operator (or the task-13.0 CI job) stands up the sidecar. `OpenHandsProcess`
  and `OpenHandsClient` are entered/closed via `finally` finalizers so no sidecar
  session survives the module.
- The sandbox-verification test asserts on `result.content` 
  (a stable, model-agnostic sentinel), not on a specific tool-call shape, so it stays robust
  across OpenHands runtime versions while still being load-bearing.
- The `OpenHandsClient` is the only importer of the OpenHands HTTP/WS client
  library (C3); the test imports the tool/client/process public surfaces only.
- The `EventBus` recorder API mirrors the 0004 OpenClaude live suite; settle the
  exact recorder against the shipped `aegis_swr.core.events` API.

## Constraints

- **Skip, never fail.** With `OPENHANDS_SERVER_URL` unset or the Docker daemon unreachable, the module reports one clean module-level skip — never a failure, an error, or a collection crash.
- Tests that run pass with **zero mocks** — a real sidecar, a real sandboxed runtime, and a real model call.
- No integration run may leave an OpenHands sidecar session alive; the module-scoped process/client fixtures' `finally` finalizers own teardown, including on failure.
- The stub project is created in a temp dir and mounted into the sandbox; it is **never** the Aegis SWR source tree, and the task is a read-only navigation under the default allowlist and the Docker-sandboxed runtime (no non-sandboxed override, C8).
- No raw stub content, streamed observation text, or server credential ever reaches a log sink or an event payload (C13); loguru sinks keep `SensitiveFilter`.

## Success criteria

- [ ] With `OPENHANDS_SERVER_URL` unset, the suite reports **skipped** (one line per module), never failed.
- [ ] With the URL set but the Docker daemon unreachable (down / not installed / permission denied / timeout), the suite still reports **skipped**, never failed, or errored.
- [ ] A live `delegate()` returns a `CodeResult` with `available is True`, non-empty `content`, and `token_estimate > 0`.
- [ ] At least one `openhands.action` event is emitted (real navigation proven).
- [ ] Sandbox verification passes: the host lacks `/.dockerenv` but the runtime reports it presents, proving in-container execution (C8).
- [ ] Exactly one `openhands.completed` event carries a positive `token_estimate`.
- [ ] No OpenHands sidecar session survives the run; no credential is logged.
- [ ] `ruff check src/ tests/` - clean.
