# 01 - `conftest.py` fixtures

**Parent task:** 07.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** 01.0 subtask 01 (`OpenClaudeSettings`), 05.0 subtask 01 (event
dataclasses), 06.0 subtask 01 (`CallBudget`, `ToolContext`, `CodeResult`). No
other test file can run without these fixtures.
**Blocks:** 02, 03, 04, 05, 06 (every test file in this task consumes these
fixtures)

## Objective

Provide the injection seams that let the entire unit suite run with
`OPENCLAUDE_GRPC_URL` unset and no OpenClaude binary on `PATH` — no real gRPC
channel, no Node.js subprocess, no protobuf import. The centrepiece is
`mock_grpc_client`, a factory that turns a list of plain frame dicts into an
`AsyncMock`-based `OpenClaudeGrpcClient` whose `query()` async-generator yields
them in order. All other fixtures (`mock_event_bus`, `settings_no_grpc`,
`settings_with_grpc`, `ample_budget`, `dry_run_ctx`) supply the remaining
constructor arguments so every collaborator is injected, never monkeypatched.

These fixtures live in `tests/openclaude/unit/conftest.py` rather than the
top-level `tests/openclaude/conftest.py`: they are all mock-based and are of no
use to the live-process integration suite, which supplies its own real fixtures
in `tests/openclaude/integration/conftest.py` (task 08.0). Keeping them at the
`unit/` level prevents the integration suite from importing mock seams.

## File: `tests/openclaude/unit/conftest.py`

```python
from __future__ import annotations

from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from aegis.core.events import EventBus
from aegis.code_intel.budget import CallBudget
from aegis.code_intel.agent import ToolContext  # dry_run flag carrier
from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.grpc.client import OpenClaudeGrpcClient


# --- gRPC client seam -------------------------------------------------------

@pytest.fixture
def mock_grpc_client() -> Callable[..., OpenClaudeGrpcClient]:
    """Return a factory that builds an ``AsyncMock`` ``OpenClaudeGrpcClient``.

    The factory takes a list of plain frame dicts, e.g.
    ``[{"type": "TEXT_CHUNK", "content": "def f", "tool": None},
       {"type": "DONE", "content": "def f(): ...", "tool": None}]``,
    and configures ``client.query()`` to return an async generator yielding
    them in order. ``health_check`` and ``close`` are plain ``AsyncMock``s the
    caller can further configure. No protobuf message is ever constructed.

    Optional keyword args let a test script side effects:
      * ``query_raises`` — an exception ``query()`` raises instead of yielding
        (used for the ``UNAVAILABLE`` / ``DEADLINE_EXCEEDED`` client tests).
      * ``health_result`` — the bool ``health_check()`` returns (default
        ``True``).
    """

    def _build(
        frames: list[dict[str, Any]],
        *,
        query_raises: Optional[BaseException] = None,
        health_result: bool = True,
    ) -> OpenClaudeGrpcClient:
        client = AsyncMock(spec=OpenClaudeGrpcClient)

        async def _agen(*_args: Any, **_kwargs: Any) -> Any:
            if query_raises is not None:
                raise query_raises
            for frame in frames:
                yield frame

        # query() is a sync method returning an async iterator in the real
        # client; model that exactly so `async for` in the tool works.
        client.query = MagicMock(side_effect=lambda *a, **k: _agen(*a, **k))
        client.health_check = AsyncMock(return_value=health_result)
        client.close = AsyncMock()
        return client

    return _build


# --- EventBus seam ----------------------------------------------------------

@pytest.fixture
def mock_event_bus() -> EventBus:
    """Return a real ``EventBus`` with a list-collecting subscriber.

    Emitted events are captured on ``bus.captured`` (a plain ``list``) so tests
    can assert on type, ordering, count, and payload fields without mocking the
    bus itself. Mirrors the Milestone 0003 ``capturing_bus`` convention.
    """
    bus = EventBus()
    captured: list[Any] = []
    bus.subscribe(lambda e: captured.append(e))
    bus.captured = captured  # type: ignore[attr-defined]
    return bus


# --- Settings seams ---------------------------------------------------------

@pytest.fixture
def settings_no_grpc() -> OpenClaudeSettings:
    """``OpenClaudeSettings`` with ``grpc_url=None`` (backend not registered)."""
    return OpenClaudeSettings(grpc_url=None)


@pytest.fixture
def settings_with_grpc() -> OpenClaudeSettings:
    """``OpenClaudeSettings`` with a valid bare ``host:port`` and default allowlists."""
    return OpenClaudeSettings(grpc_url="localhost:50051")


# --- Budget seam ------------------------------------------------------------

@pytest.fixture
def ample_budget() -> CallBudget:
    """A ``CallBudget`` large enough never to exhaust during a unit test.

    Used by the happy-path and truncation tests where the pre-check must pass.
    Budget-exhaustion tests construct their own near-zero ``CallBudget`` inline.
    """
    return CallBudget(max_tokens=10_000_000)


# --- Tool context seam ------------------------------------------------------

@pytest.fixture
def dry_run_ctx() -> ToolContext:
    """A ``ToolContext`` with ``dry_run=True`` for the short-circuit test."""
    return ToolContext(run_id="run-dry", dry_run=True)


@pytest.fixture
def live_ctx() -> ToolContext:
    """A ``ToolContext`` with ``dry_run=False`` (the normal execution path)."""
    return ToolContext(run_id="run-1", dry_run=False)
```

## Fixtures provided

| Fixture             | Purpose                                                                                   |
|---------------------|-------------------------------------------------------------------------------------------|
| `mock_grpc_client`  | Factory: `list[dict]` frames → `AsyncMock` `OpenClaudeGrpcClient` with an ordered `query()` async-gen; optional `query_raises` / `health_result` |
| `mock_event_bus`    | Real `EventBus` + list-collecting subscriber exposed on `bus.captured`                    |
| `settings_no_grpc`  | `OpenClaudeSettings(grpc_url=None)` — backend-unavailable case                             |
| `settings_with_grpc`| `OpenClaudeSettings(grpc_url="localhost:50051")` — valid registration case                 |
| `ample_budget`      | `CallBudget` that never exhausts, so the tool pre-check passes                            |
| `dry_run_ctx`       | `ToolContext(dry_run=True)` for the dry-run short-circuit branch                          |
| `live_ctx`          | `ToolContext(dry_run=False)` for all normal-execution branches                            |

## Constraints

- All unit tests must pass with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude
  binary on `PATH` — these fixtures start no real process and open no real
  channel.
- Mock frame sequences are **plain dicts**, never real protobuf messages, so the
  unit suite carries no `grpc` / `_pb2` import at all. `conftest.py` must not
  import `grpc` or any `openclaude_pb2*` module (would break the C3 isolation
  intent and the no-live-process guarantee).
- **No `monkeypatch` of module-level globals.** Every gRPC and process
  dependency is constructor-injected (`from_channel`, `mock_grpc_client`, mock
  event bus). Fixtures never patch `aegis.openclaude.*` module attributes.
- `mock_grpc_client.query` is a **sync** callable returning an async iterator,
  matching the real client (`async for frame in client.query(...)`); do not make
  `query` itself a coroutine.
- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` at the top (C9).

## Success criteria

- [ ] `mock_grpc_client([...])` returns an object where
      `async for f in client.query("t", "run")` yields the exact dicts in order.
- [ ] `mock_grpc_client([], query_raises=exc)` produces a `query()` whose
      async-gen raises `exc` on first iteration.
- [ ] `mock_grpc_client([], health_result=False).health_check()` awaits to
      `False`.
- [ ] `mock_event_bus.captured` collects every event passed to `bus.emit(...)`
      in emission order.
- [ ] `settings_no_grpc.grpc_url is None`; `settings_with_grpc.grpc_url ==
      "localhost:50051"` and neither raises `OpenClaudeConfigError`.
- [ ] `ample_budget` passes an `OpenClaudeTool` pre-check against
      `max_response_tokens // 4`; `dry_run_ctx.dry_run is True`.
- [ ] `conftest.py` imports neither `grpc` nor any `_pb2` module (grep-clean).
- [ ] `mypy --strict`, `ruff`, `replace_optional.py --check` clean.
