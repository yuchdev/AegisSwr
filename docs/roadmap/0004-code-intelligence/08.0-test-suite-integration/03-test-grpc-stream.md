# 03 - `test_grpc_stream.py`

**Parent task:** 08.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** 01 (skip guards / fixtures), 02.0 `OpenClaudeGrpcClient` live
**Blocks:** none

## Objective

Prove the gRPC stream contract (C2) end to end against the live process: that a
real `query()` call drives the `Query` server-streaming RPC and yields a
well-formed frame sequence — at least one `TEXT_CHUNK` frame followed by a
terminal, non-empty `DONE` frame — and that `health_check()` returns `True`
against the running sidecar. This validates the client's frame parsing and stream
consumption against a genuine OpenClaude server rather than the scripted mock
channel used in the unit suite (task 07.0).

## File: `tests/openclaude/integration/test_grpc_stream.py`

```python
from __future__ import annotations

import uuid
from typing import Optional

import pytest

from aegis.openclaude.grpc.client import OpenClaudeGrpcClient

from tests.openclaude.integration.conftest import require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent

pytestmark = pytest.mark.asyncio


async def test_query_yields_text_chunk_then_done(
    live_grpc_client: OpenClaudeGrpcClient,
) -> None:
    """A real query returns a non-empty terminal DONE preceded by >=1 TEXT_CHUNK."""
    run_id = str(uuid.uuid4())
    prompt = "Find the function named compute_checksum and report the file it lives in."
    frames = [frame async for frame in live_grpc_client.query(prompt, run_id)]

    text_chunks = [f for f in frames if f.type == "TEXT_CHUNK"]
    assert text_chunks, "expected at least one TEXT_CHUNK frame"

    terminal = frames[-1]
    assert terminal.type == "DONE"
    assert terminal.content.strip(), "DONE frame content must be non-empty"
    ...


async def test_health_check_true_against_live_process(
    live_grpc_client: OpenClaudeGrpcClient,
) -> None:
    """health_check() returns True against the running sidecar."""
    assert await live_grpc_client.health_check() is True
    ...
```

## Test cases

- `test_query_yields_text_chunk_then_done` — a live `query(prompt, run_id)` over
  the real stream yields at least one `TEXT_CHUNK` frame and terminates with a
  `DONE` frame whose `content` is non-empty (the concatenated response text per
  C2). The frame ordering (chunks before the terminal frame) is asserted.
- `test_health_check_true_against_live_process` — `health_check()` sends its ping
  request and observes a terminal `DONE` within `connect_timeout_s`, returning
  `True` for the reachable live endpoint.

## Constraints

- Tests that run pass with **zero mocks** — a live gRPC channel to the real
  process supplied by the `live_grpc_client` fixture (subtask 01).
- No integration test may leave a running OpenClaude process; teardown is owned by
  the module-scoped fixtures' finalizers.
- Uses the temp-dir `stub_project` as navigation target, never the Aegis SWR
  source tree; the query is a read-only navigation task under the default allowlist.
- Gated behind `OPENCLAUDE_INTEGRATION`; skipped by default on PRs, optional on
  main (task 09.0 CI wiring).
- No raw stub content or streamed response text is logged (C9).
- `from __future__ import annotations`; `Optional[T]`, never `T | None`;
  `ruff` clean.

## Success criteria

- [ ] A live `query()` yields >= 1 `TEXT_CHUNK` frame.
- [ ] The stream terminates with a `DONE` frame carrying non-empty content.
- [ ] `TEXT_CHUNK` frame(s) precede the terminal `DONE` frame.
- [ ] `health_check()` returns `True` against the live process.
- [ ] Tests report **skipped** (not failed) when the binary or signal is absent.
- [ ] No OpenClaude process survives the run.
- [ ] `ruff`, `replace_optional.py --check` clean.
