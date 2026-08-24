# 01 - Shared fixtures / `conftest.py`

**Parent task:** 11.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** 01.0 (`HarnessSettings`, `HarnessConfigError`,
`HarnessUnavailableError`), 02.0/04.0 (`ClaudeCodeSettings` incl. `auth_mode`),
06.0 (`OpenHandsSettings`), 05.0/09.0 (event dataclasses), and the unchanged
0004 `CallBudget` / `ToolContext` / `CodeResult`. No other test file in this task
can run without these fixtures.
**Blocks:** 02, 03, 04 (every test file in this task consumes these fixtures)

## Objective

Provide the injection seams that let the entire multi-backend unit suite run with
`AEGIS_CODE_INTEL_BACKEND` unset, all three presence signals unset, and no
`claude` binary / Docker daemon / OpenHands server available — no real
subprocess, no socket, no container, no `grpc` import, no OpenHands client
library import. This generalises 0004's single `mock_grpc_client` seam
([0004 07.0/01](/docs/roadmap/0004-code-intelligence/07.0-test-suite-unit/01-conftest-fixtures.md))
to three backends:

- **`mock_claude_subprocess`** — a factory that turns a scripted list of NDJSON
  lines (plain dicts serialised to `stream-json`) into a fake one-shot `claude`
  process **and records the exact `argv` and `env` it was invoked with**, so the
  argv-safety (C6) and auth-mode (C7) tests inspect a real recorded call. It
  never spawns a real process.
- **`mock_openhands_client`** — the direct analogue of 0004's `mock_grpc_client`:
  a factory turning a list of plain Action/Observation event dicts into an
  `AsyncMock` `OpenHandsClient` whose event stream yields them in order, with
  optional `connect_raises` / `health_result` scripting.
- **`mock_event_bus`** — a real `EventBus` with a list-collecting subscriber on
  `bus.captured` (carried over verbatim from 0004).
- **C2 settings fixtures** — one `HarnessSettings` (or the raw env scenario) per
  ambiguity case: zero signals, each single signal, multiple signals, and
  selector-set-signal-absent — plus `ample_budget`, `dry_run_ctx`, `live_ctx`.

These fixtures live in `tests/unit/conftest.py` (or a shared helper module
imported by each package's own `conftest.py`) so all three packages consume the
identical seams. They are mock-based and of no use to the live integration suite
(task 12.0), which supplies its own real fixtures.

## File: `tests/unit/conftest.py`

```python
from __future__ import annotations

import json
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from aegis_swr.core.events import EventBus
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.code_intel.agent import ToolContext  # dry_run flag carrier
from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.client import OpenHandsClient


# --- Claude Code one-shot subprocess seam -----------------------------------

class RecordingClaudeProcess:
    """A fake one-shot ``claude`` process that records its argv/env.

    :ivar argv: the exact argument vector the process was constructed with, so
        argv-safety tests (C6) can assert the task text never appears in it.
    :ivar env: the environment mapping the subprocess would inherit, so C7 auth
        tests can assert on credential-variable presence/absence.
    :ivar stdin_text: whatever was written to the process's stdin (the task text
        travels here, never via argv).
    """

    def __init__(
        self,
        argv: list[str],
        env: dict[str, str],
        ndjson_lines: list[dict[str, Any]],
    ) -> None:
        self.argv = argv
        self.env = env
        self.stdin_text: Optional[str] = None
        self._lines = ndjson_lines
        self.returncode: Optional[int] = None

    async def communicate(self, stdin: Optional[bytes] = None) -> tuple[bytes, bytes]:
        """Record stdin, then replay the scripted NDJSON as stdout."""
        if stdin is not None:
            self.stdin_text = stdin.decode()
        self.returncode = 0
        stdout = "\n".join(json.dumps(line) for line in self._lines).encode()
        return stdout, b""


@pytest.fixture
def mock_claude_subprocess() -> Callable[..., RecordingClaudeProcess]:
    """Return a factory building a ``RecordingClaudeProcess`` from NDJSON lines.

    The factory takes the scripted ``stream-json`` line dicts (e.g. a run of
    ``{"type": "text", ...}`` messages then a terminal
    ``{"type": "result", "usage": {"input_tokens": 12, "output_tokens": 8}}``)
    and returns a fake process whose ``communicate()`` replays them on stdout and
    records the task text written to stdin. No real ``claude`` process is spawned.

    :param exit_code: overrides ``returncode`` for error-path tests.
    :param nonzero_stderr: bytes to return on stderr for the failure path.
    """

    def _build(
        ndjson_lines: list[dict[str, Any]],
        *,
        argv: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
    ) -> RecordingClaudeProcess:
        return RecordingClaudeProcess(
            argv=argv if argv is not None else [],
            env=env if env is not None else {},
            ndjson_lines=ndjson_lines,
        )

    return _build


# --- OpenHands HTTP/WS client seam ------------------------------------------

@pytest.fixture
def mock_openhands_client() -> Callable[..., OpenHandsClient]:
    """Return a factory building an ``AsyncMock`` ``OpenHandsClient``.

    The direct analogue of 0004's ``mock_grpc_client``. The factory takes a list
    of plain Action/Observation event dicts, e.g.
    ``[{"kind": "action", "name": "read", "path": "a.py"},
       {"kind": "observation", "content": "def f(): ..."},
       {"kind": "done", "usage": {"tokens": 20}}]``
    and configures ``client.stream()`` to return an async generator yielding them
    in order. No real HTTP/WS socket is opened and the OpenHands client library is
    never imported by the test.

    :param connect_raises: an exception ``connect()``/``stream()`` raises instead
        of yielding (for the unavailable / disconnect tests).
    :param health_result: the bool ``health_check()`` returns (default ``True``).
    """

    def _build(
        events: list[dict[str, Any]],
        *,
        connect_raises: Optional[BaseException] = None,
        health_result: bool = True,
    ) -> OpenHandsClient:
        client = AsyncMock(spec=OpenHandsClient)

        async def _agen(*_args: Any, **_kwargs: Any) -> Any:
            if connect_raises is not None:
                raise connect_raises
            for event in events:
                yield event

        # stream() is a sync method returning an async iterator in the real
        # client; model that exactly so `async for` in the tool works.
        client.stream = MagicMock(side_effect=lambda *a, **k: _agen(*a, **k))
        client.health_check = AsyncMock(return_value=health_result)
        client.close = AsyncMock()
        return client

    return _build


# --- EventBus seam ----------------------------------------------------------

@pytest.fixture
def mock_event_bus() -> EventBus:
    """Return a real ``EventBus`` with a list-collecting subscriber.

    Emitted events are captured on ``bus.captured`` (a plain ``list``) so tests
    assert on type, ordering, count, and payload fields without mocking the bus.
    Carried over verbatim from the 0004 convention.
    """
    bus = EventBus()
    captured: list[Any] = []
    bus.subscribe(lambda e: captured.append(e))
    bus.captured = captured  # type: ignore[attr-defined]
    return bus


# --- C2 selection-scenario settings seams -----------------------------------

@pytest.fixture
def env_no_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the selector and all three presence signals (C2 row 1)."""
    for var in (
        "AEGIS_CODE_INTEL_BACKEND",
        "OPENCLAUDE_GRPC_URL",
        "CLAUDE_CODE_ENABLED",
        "OPENHANDS_SERVER_URL",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def env_openclaude_only(env_no_signals: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only ``OPENCLAUDE_GRPC_URL`` set — the 0004 preserved-guarantee case."""
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")


@pytest.fixture
def env_claude_code_only(env_no_signals: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only ``CLAUDE_CODE_ENABLED=true`` set (C2 single-signal auto-select)."""
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")


@pytest.fixture
def env_openhands_only(env_no_signals: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only ``OPENHANDS_SERVER_URL`` set (C2 single-signal auto-select)."""
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://localhost:3000")


@pytest.fixture
def env_multiple_signals(env_no_signals: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two signals set with the selector unset (C2 ambiguity → HarnessConfigError)."""
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")


# --- Backend settings seams -------------------------------------------------

@pytest.fixture
def claude_code_settings_enabled() -> ClaudeCodeSettings:
    """A valid ``ClaudeCodeSettings`` with ``enabled=True`` and defaults."""
    return ClaudeCodeSettings(enabled=True)


@pytest.fixture
def openhands_settings_enabled() -> OpenHandsSettings:
    """A valid ``OpenHandsSettings`` with a bare ``server_url`` and defaults."""
    return OpenHandsSettings(server_url="http://localhost:3000")


# --- Budget / context seams -------------------------------------------------

@pytest.fixture
def ample_budget() -> CallBudget:
    """A ``CallBudget`` large enough never to exhaust during a unit test."""
    return CallBudget(max_tokens=10_000_000)


@pytest.fixture
def dry_run_ctx() -> ToolContext:
    """A ``ToolContext`` with ``dry_run=True`` for the short-circuit tests."""
    return ToolContext(run_id="run-dry", dry_run=True)


@pytest.fixture
def live_ctx() -> ToolContext:
    """A ``ToolContext`` with ``dry_run=False`` (the normal execution path)."""
    return ToolContext(run_id="run-1", dry_run=False)
```

## Fixtures provided

| Fixture | Purpose |
|---------|---------|
| `mock_claude_subprocess` | Factory: NDJSON line dicts → `RecordingClaudeProcess` replaying `stream-json` on stdout and **recording argv/env/stdin**; no real process spawned |
| `mock_openhands_client` | Factory: Action/Observation dicts → `AsyncMock` `OpenHandsClient` with an ordered `stream()` async-gen; optional `connect_raises` / `health_result` |
| `mock_event_bus` | Real `EventBus` + list-collecting subscriber on `bus.captured` |
| `env_no_signals` | Clears selector + all three signals (C2 row 1) |
| `env_openclaude_only` | Only `OPENCLAUDE_GRPC_URL` — the 0004 preserved-guarantee case |
| `env_claude_code_only` | Only `CLAUDE_CODE_ENABLED=true` (single-signal auto-select) |
| `env_openhands_only` | Only `OPENHANDS_SERVER_URL` (single-signal auto-select) |
| `env_multiple_signals` | Two signals, selector unset (ambiguity → `HarnessConfigError`) |
| `claude_code_settings_enabled` | Valid `ClaudeCodeSettings(enabled=True)` |
| `openhands_settings_enabled` | Valid `OpenHandsSettings(server_url=...)` |
| `ample_budget` | `CallBudget` that never exhausts |
| `dry_run_ctx` / `live_ctx` | `ToolContext(dry_run=True)` / `(dry_run=False)` |

## Implementation notes

- Model `mock_claude_subprocess` on how 03.0's `process.py` actually spawns the
  one-shot `claude` process. If 03.0 exposes a subprocess-factory injection
  point, prefer that seam over any `asyncio.create_subprocess_exec` patch, and
  the fixture should return `RecordingClaudeProcess` from that factory. Flag any
  coupling that forces an `asyncio`-boundary patch back to 03.0.
- `RecordingClaudeProcess.communicate` intentionally records `stdin_text`: the
  argv-safety test (subtask 03) asserts the task text appears in `stdin_text`
  **and never** in `argv`.
- `mock_openhands_client.stream` is a **sync** callable returning an async
  iterator, matching 0004's `mock_grpc_client.query` — do not make it a coroutine.
- The env-scenario fixtures set/clear **real** environment variables that Pydantic
  Settings read. This is the one legitimate `monkeypatch` use; never patch an
  `aegis_swr.*` module global or class attribute.

## Constraints

- All unit tests must pass with `AEGIS_CODE_INTEL_BACKEND` unset, all three
  presence signals unset, and no `claude` binary / Docker / OpenHands server
  available — these fixtures start no real process, open no socket, and launch no
  container.
- `conftest.py` must import **neither** `grpc`/`_pb2` **nor** the OpenHands client
  library at module scope; the OpenHands seam is an `AsyncMock(spec=OpenHandsClient)`
  and the Claude Code seam is a plain in-process object (would otherwise break the
  C3 isolation intent and the no-live-process guarantee).
- **No `monkeypatch` of module-level globals.** Every subprocess / client /
  process / bus dependency is constructor-injected. Env-var `monkeypatch` is the
  only permitted use.
- Mock NDJSON lines and Action/Observation frames are **plain dicts / strings** —
  never a real `stream-json` proto or OpenHands SDK object.
- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` at the top (C13).

## Success criteria

- [ ] `mock_claude_subprocess([...])` returns an object whose `communicate()`
      replays the scripted NDJSON on stdout and exposes `argv`, `env`, and the
      recorded `stdin_text`.
- [ ] `mock_openhands_client([...])` returns an object where
      `async for e in client.stream(...)` yields the exact dicts in order.
- [ ] `mock_openhands_client([], connect_raises=exc)` produces a `stream()` whose
      async-gen raises `exc` on first iteration; `health_result=False` awaits to
      `False`.
- [ ] `mock_event_bus.captured` collects every event passed to `bus.emit(...)` in
      emission order.
- [ ] `env_openclaude_only` leaves exactly one presence signal set; the other
      `env_*` fixtures set the scenario they name and clear the rest.
- [ ] `claude_code_settings_enabled` and `openhands_settings_enabled` construct
      without raising their backend's config error.
- [ ] `conftest.py` imports neither `grpc`/`_pb2` nor the OpenHands client library
      (grep-clean).
- [ ] `ruff`, `replace_optional.py --check` clean.
