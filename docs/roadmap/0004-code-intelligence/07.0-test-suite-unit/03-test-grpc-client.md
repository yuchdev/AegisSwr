# 03 - `test_grpc_client.py`

**Parent task:** 07.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** 01 (fixtures), 02.0 (`OpenClaudeGrpcClient`, `from_channel`),
05.0 subtask 02 (`OpenClaudeUnavailableError`).
**Blocks:** none

## Objective

Verify `OpenClaudeGrpcClient` against a **mock gRPC channel** injected via
`from_channel(channel, settings)`, with zero real network I/O and no live
OpenClaude process. Cover the three behaviours 02.0 promises: a scripted frame
sequence is yielded from `query()` in order; `health_check()` returns `False`
(does not raise) when the channel reports `UNAVAILABLE`; and `query()` raises
`OpenClaudeUnavailableError` when the channel raises `DEADLINE_EXCEEDED`. This
is the only unit test file that touches the client, and even here the mock
channel returns objects that the client parses — the test itself constructs no
protobuf message and imports no `_pb2` module (the client owns that translation;
the mock stub returns simple namespace-style frames).

## File: `tests/openclaude/unit/test_grpc_client.py`

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from aegis.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis.openclaude.exceptions import OpenClaudeUnavailableError


class _FakeRpcError(Exception):
    """Stand-in for grpc.aio.AioRpcError carrying a .code() -> status.

    Avoids importing grpc in the test; the client's except clause matches on
    the injected error type / code the mock stub raises. The exact seam
    (matching grpc.StatusCode) is finalised by 02.0's implementation; this
    fake mirrors the `.code()` accessor the client reads.
    """

    def __init__(self, code: str):
        self._code = code

    def code(self) -> str:
        return self._code


@pytest.fixture
def fake_channel_factory():
    """Build a mock channel whose streaming stub replays scripted frames.

    The factory accepts a list of frame objects (SimpleNamespace mirroring the
    proto message: .type / .content / .tool) or an exception to raise, and
    returns a MagicMock channel that `from_channel` accepts verbatim.
    """
    ...


async def test_query_yields_scripted_frames_in_order(fake_channel_factory):
    """query() yields the scripted TEXT_CHUNK...DONE frames in emission order."""

async def test_from_channel_construction_no_network(fake_channel_factory):
    """from_channel(channel, settings) builds a client without opening a socket."""

async def test_health_check_returns_false_on_unavailable(fake_channel_factory):
    """A simulated UNAVAILABLE status makes health_check() return False, not raise."""

async def test_query_raises_on_deadline_exceeded(fake_channel_factory):
    """A simulated DEADLINE_EXCEEDED makes query() raise OpenClaudeUnavailableError."""

async def test_query_raises_unavailable_error_on_unavailable(fake_channel_factory):
    """A simulated UNAVAILABLE during query() raises OpenClaudeUnavailableError."""

async def test_close_shuts_down_channel(fake_channel_factory):
    """close() awaits the channel's close/shutdown exactly once."""
```

## Test cases

| Test | Contract verified |
|------|-------------------|
| `test_query_yields_scripted_frames_in_order` | C2 stream contract: `query()` async-generator yields every scripted frame (`TEXT_CHUNK` … `DONE`) in order via the injected mock stub |
| `test_from_channel_construction_no_network` | `from_channel(channel, settings)` builds a usable client with zero real network I/O; the injected channel is used verbatim |
| `test_health_check_returns_false_on_unavailable` | 02.0/04: `health_check()` returns `False` (does **not** raise) when the channel is unreachable / `UNAVAILABLE` within `connect_timeout_s` |
| `test_query_raises_on_deadline_exceeded` | `DEADLINE_EXCEEDED` during the stream is surfaced as `OpenClaudeUnavailableError`, not a raw gRPC error |
| `test_query_raises_unavailable_error_on_unavailable` | `UNAVAILABLE` during the stream is likewise surfaced as `OpenClaudeUnavailableError` |
| `test_close_shuts_down_channel` | `close()` shuts the channel down (RAII/cleanup path) |

## Constraints

- All tests pass with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude binary on
  `PATH`; the channel is a `MagicMock`, so no socket is opened.
- The channel/stub is injected via `from_channel` — **no `monkeypatch`** of the
  `grpc` module or of client module globals.
- The test file must not import `grpc` or any `_pb2` module. The status codes
  (`UNAVAILABLE`, `DEADLINE_EXCEEDED`) are simulated via the `_FakeRpcError`
  helper's `.code()` accessor; the exact match seam is whatever 02.0's client
  reads (`err.code() == grpc.StatusCode.*`). If 02.0's final client cannot be
  driven without a real `grpc.StatusCode`, that status-code seam is imported
  from the client module, never from `grpc` directly — flag any such coupling
  back to 02.0.
- No raw response text is asserted against a log sink; the client must not log
  unredacted stream content (C9).
- `Optional[T]` from `typing`; `from __future__ import annotations` (C9).

## Success criteria

- [ ] All 6 test functions present and passing.
- [ ] `test_query_yields_scripted_frames_in_order` asserts the collected frame
      list equals the scripted input order and length.
- [ ] `test_health_check_returns_false_on_unavailable` asserts the return value
      is exactly `False` and that **no** exception propagates.
- [ ] `test_query_raises_on_deadline_exceeded` and
      `test_query_raises_unavailable_error_on_unavailable` assert
      `OpenClaudeUnavailableError` (not a raw gRPC error) is raised.
- [ ] No `grpc` / `_pb2` import anywhere in the file.
- [ ] `ruff`, `replace_optional.py --check` clean.
