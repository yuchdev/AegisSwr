# 04 - `test_tool_live.py`

**Parent task:** 08.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** 01 (skip guards / fixtures), 04.0 `OpenClaudeTool` live (with 02.0/03.0/05.0)
**Blocks:** none

## Objective

Prove the full delegation path through the sole `CodeBackend` against a live model:
`OpenClaudeTool.run()` returns a non-empty result, `OpenClaudeStreamCompleted`
carries a **positive** boundary token estimate (C5), and — the load-bearing
assertion — **at least one `OpenClaudeToolCall` event is emitted**. That last check
is the whole point of a live integration test: it proves OpenClaude actually
navigated the stub project via its own `Read`/`Grep`/`Glob` tool calls rather than
fabricating an answer from its training-data priors. A response with zero tool
calls would look plausible but would mean the model guessed; asserting on emitted
tool-call events is what distinguishes genuine forensic navigation from a
confident hallucination. This is also the runtime-quality gate flagged in the
milestone Background — a model too weak to sustain multi-step tool flows fails
here rather than silently degrading in production.

## File: `tests/openclaude/integration/test_tool_live.py`

```python
from __future__ import annotations

import uuid
from typing import Optional

import pytest

from aegis.code_intel.budget import CallBudget
from aegis.core.events import EventBus
from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.events import OpenClaudeStreamCompleted, OpenClaudeToolCall
from aegis.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis.openclaude.tool import OpenClaudeTool

from tests.openclaude.integration.conftest import require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent

pytestmark = pytest.mark.asyncio


def _build_tool(client: OpenClaudeGrpcClient, bus: EventBus) -> OpenClaudeTool:
    return OpenClaudeTool(
        client=client,
        settings=OpenClaudeSettings(grpc_url=client.grpc_url),
        event_bus=bus,
    )


async def test_run_returns_non_empty_result(
    live_grpc_client: OpenClaudeGrpcClient,
) -> None:
    """A live run() over a real navigation task returns non-empty result text."""
    bus = EventBus()
    tool = _build_tool(live_grpc_client, bus)
    result = await tool.run(
        task="Locate compute_checksum and describe what module it is defined in.",
        ctx=...,  # non-dry-run ToolContext with a real run_id + ample CallBudget
    )
    assert result.text.strip()
    ...


async def test_stream_completed_carries_positive_token_estimate(
    live_grpc_client: OpenClaudeGrpcClient,
) -> None:
    """OpenClaudeStreamCompleted carries a positive boundary token estimate."""
    ...  # record events; find OpenClaudeStreamCompleted; assert token_estimate > 0


async def test_at_least_one_tool_call_emitted(
    live_grpc_client: OpenClaudeGrpcClient,
) -> None:
    """>=1 OpenClaudeToolCall proves real navigation, not an answer from priors."""
    ...  # record events; assert any(isinstance(e, OpenClaudeToolCall) for e in seen)
```

## Test cases

- `test_run_returns_non_empty_result` — `OpenClaudeTool.run()` against the live
  process/model returns a result whose text is non-empty.
- `test_stream_completed_carries_positive_token_estimate` — exactly one
  `OpenClaudeStreamCompleted` is emitted on `DONE` and its `token_estimate` is
  strictly positive (the `max(1, len(content) // 4)` boundary estimate, C5).
- `test_at_least_one_tool_call_emitted` — at least one `OpenClaudeToolCall` event
  is emitted during the run, proving OpenClaude drove its own tool loop over the
  stub project rather than answering from priors.

## Constraints

- Tests that run pass with **zero mocks** — real client, real process, real model.
- No integration test may leave a running OpenClaude process; the module-scoped
  fixtures' finalizers own teardown, including on failure.
- Uses the temp-dir `stub_project` (a uniquely named symbol the model must
  *discover*), never the Aegis SWR source tree; runs read-only under the default
  allowlist.
- `run()` is called with a **non-dry-run** `ToolContext` (dry-run would
  short-circuit and emit no tool calls) carrying a real `run_id` and an ample
  `CallBudget` so the budget pre-check does not block the call (C5).
- Gated behind `OPENCLAUDE_INTEGRATION`; skipped by default on PRs, optional on
  main (task 09.0 CI wiring).
- No raw stub content or streamed response text is logged (C9); tool-call events
  carry only tool names/counts/estimates, never payload text.
- `from __future__ import annotations`; `Optional[T]`, never `T | None`;
  `mypy --strict` and `ruff` clean.

## Success criteria

- [ ] Live `OpenClaudeTool.run()` returns a non-empty result.
- [ ] Exactly one `OpenClaudeStreamCompleted` is emitted with `token_estimate > 0`.
- [ ] At least one `OpenClaudeToolCall` event is emitted (real navigation proven).
- [ ] The run uses a non-dry-run context with sufficient budget.
- [ ] Tests report **skipped** (not failed) when the binary or signal is absent.
- [ ] No OpenClaude process survives the run.
- [ ] `mypy --strict`, `ruff`, `replace_optional.py --check` clean.
