# 05 - `test_allowlist_enforcement.py`

**Parent task:** 08.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** 01 (skip guards / fixtures), 04.0 `OpenClaudeTool` + C7 allowlist enforcement live
**Blocks:** none

## Objective

Prove the forensic read-only guarantee (C7) holds against a **real** OpenClaude
process, not just against unit-suite mocks. A task that requires a write-capable
tool (asking OpenClaude to edit a file in the stub project) must be **denied**
under the default allowlist (`Read,Grep,Glob,Bash` — no `Write`/`Edit`), surfacing
a `PermissionDeniedError` / `OpenClaudePermissionDenied` and leaving the stub
project unmodified; a `Read`/`Grep`-only navigation task against the same process
must succeed normally. This is the concrete, end-to-end evidence that OpenClaude
cannot mutate the repository under analysis — the single most important security
property of the integration.

## File: `tests/openclaude/integration/test_allowlist_enforcement.py`

```python
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import pytest

from aegis.core.events import EventBus
from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.events import OpenClaudePermissionDenied
from aegis.openclaude.exceptions import PermissionDeniedError
from aegis.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis.openclaude.tool import OpenClaudeTool

from tests.openclaude.integration.conftest import require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent

pytestmark = pytest.mark.asyncio


def _build_tool(client: OpenClaudeGrpcClient, bus: EventBus) -> OpenClaudeTool:
    return OpenClaudeTool(
        client=client,
        settings=OpenClaudeSettings(grpc_url=client.grpc_url),  # default allowlist
        event_bus=bus,
    )


async def test_write_task_denied_under_default_allowlist(
    live_grpc_client: OpenClaudeGrpcClient,
    stub_project: Path,
) -> None:
    """A task needing a write tool is denied; PermissionDenied surfaces."""
    bus = EventBus()
    tool = _build_tool(live_grpc_client, bus)
    target = stub_project / "app.py"
    before = target.read_bytes()

    with pytest.raises(PermissionDeniedError):
        await tool.run(
            task="Edit app.py: rename compute_checksum to compute_crc and save.",
            ctx=...,  # non-dry-run ToolContext, real run_id, ample CallBudget
        )

    assert target.read_bytes() == before  # stub project unmodified
    # and OpenClaudePermissionDenied emitted on the bus
    ...


async def test_read_only_task_succeeds(
    live_grpc_client: OpenClaudeGrpcClient,
) -> None:
    """A Read/Grep-only navigation task succeeds under the same allowlist."""
    ...  # tool.run("Grep for compute_checksum and report its file") → non-empty result
```

## Test cases

- `test_write_task_denied_under_default_allowlist` — a task that can only be
  satisfied with a write-capable tool (edit/save a stub file) triggers a
  non-allowlisted `PERMISSION_REQ`; the tool raises `PermissionDeniedError`,
  emits `OpenClaudePermissionDenied`, and the stub file on disk is byte-identical
  before and after (no mutation).
- `test_read_only_task_succeeds` — a `Read`/`Grep`-only navigation task against
  the same live process and default allowlist returns a non-empty result,
  confirming the allowlist denies writes without breaking legitimate read-only work.

## Constraints

- Tests that run pass with **zero mocks** — real process enforcing the real
  allowlist; the deny path is exercised against genuine OpenClaude permission
  requests, not scripted frames.
- No integration test may leave a running OpenClaude process; the module-scoped
  fixtures' finalizers own teardown, including after the deny-path test raises.
- Uses the temp-dir `stub_project`, never the Aegis SWR source tree; the write
  attempt targets the throwaway stub only, and the read-only guarantee is asserted
  by comparing file bytes before/after.
- The tool is constructed with the **default** allowlist (`Read,Grep,Glob,Bash` —
  no `Write`/`Edit`); no allowlist relaxation is applied.
- The deny must not corrupt boundary budget accounting (C5/C7) — it is a
  non-retriable failure, not a crash.
- Gated behind `OPENCLAUDE_INTEGRATION`; skipped by default on PRs, optional on
  main (task 09.0 CI wiring).
- No raw stub content or streamed response text is logged (C9).
- `from __future__ import annotations`; `Optional[T]`, never `T | None`;
  `mypy --strict` and `ruff` clean.

## Success criteria

- [ ] A write-requiring task is **denied**, raising
      `PermissionDeniedError` / emitting `OpenClaudePermissionDenied`.
- [ ] The stub file is byte-identical before and after the denied task (no mutation).
- [ ] A `Read`/`Grep`-only navigation task succeeds with a non-empty result under
      the same default allowlist.
- [ ] The deny path leaves budget accounting intact (non-retriable failure, no crash).
- [ ] Tests report **skipped** (not failed) when the binary or signal is absent.
- [ ] No OpenClaude process survives the run.
- [ ] `mypy --strict`, `ruff`, `replace_optional.py --check` clean.
