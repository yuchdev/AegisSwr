# 01 - Tool skeleton + input schema

**Parent task:** 04.0 OpenClaudeTool Implementor
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03, 04

## Objective

Stand up `aegis/openclaude/tool.py` with the `OpenClaudeTool` class shell: the
sole `CodeBackend` implementation (C4). This subtask defines construction and
the protocol-conformant surface only — it holds the injected collaborators
(`OpenClaudeGrpcClient`, `OpenClaudeSettings`, `EventBus`, `CallBudget`),
advertises `name` / `description` marking it as the open-ended multi-file
navigation backend, and declares the public `run()` entry method plus the
private helper stubs that subtasks 02–04 flesh out. No stream is opened and no
budget is touched here; every body is `...`. The point is a compiling,
typing-clean skeleton whose signatures the later subtasks fill in
without changing.

## File: `aegis/openclaude/tool.py`

```python
from __future__ import annotations

from typing import ClassVar, Optional

from aegis.code_intel.backend import CodeBackend, CodeContext, CodeResult
from aegis.code_intel.budget import CallBudget
from aegis.core.events import EventBus
from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.grpc.client import AgentMessage, OpenClaudeGrpcClient


class OpenClaudeTool(CodeBackend):
    """The sole :class:`CodeBackend`: delegates an open-ended code-navigation
    task to the OpenClaude sidecar over gRPC and returns a single text result.

    There is no multi-tool selection on the Aegis SWR side (C4). The class owns
    an injected gRPC client, settings, event bus, and per-call budget; it never
    reads ``os.environ`` and never imports ``grpc`` (C3). All failure paths
    return a typed :class:`CodeResult`; no exception escapes :meth:`run` (C9).

    :cvar name: Stable backend identifier used by ``CodeAgent`` registration.
    :cvar description: Human-readable capability advertised to the agent layer.
    :ivar _client: gRPC stream adapter (task 02.0); the only path to OpenClaude.
    :ivar _settings: Immutable configuration, including the allowlists (C1).
    :ivar _bus: EventBus for per-frame observability emissions (C8).
    :ivar _budget: Boundary-level token/cost accounting for one delegated call.
    """

    name: ClassVar[str] = "openclaude"
    description: ClassVar[str] = (
        "Open-ended multi-file code navigation backed by OpenClaude's own "
        "agentic loop (Read/Grep/Glob/Bash over the repository under analysis)."
    )

    def __init__(
        self,
        client: OpenClaudeGrpcClient,
        settings: OpenClaudeSettings,
        bus: EventBus,
        budget: CallBudget,
    ):
        """Store injected collaborators; open no connection and touch no budget.

        :param client: gRPC stream adapter that yields parsed agent-message
            frames (task 02.0).
        :param settings: OpenClaude configuration and allowlists (task 01.0).
        :param bus: EventBus for ``openclaude.*`` emissions (task 05.0 events).
        :param budget: Per-call boundary budget (task 06.0 ``CallBudget``).
        """
        self._client = client
        self._settings = settings
        self._bus = bus
        self._budget = budget

    async def run(self, task: str, ctx: CodeContext) -> CodeResult:
        """Delegate *task* to OpenClaude and return a single text result.

        Behaviour is layered across subtasks 02–04: stream iteration and
        content accumulation (02), permission and tool-event handling (03),
        and budget pre-check / dry-run / truncation / terminal-frame handling
        (04). Never raises: every failure path returns a typed
        :class:`CodeResult` (C9).

        :param task: The open-ended code-navigation prompt.
        :param ctx: Per-invocation context carrying ``run_id`` and ``dry_run``.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        ...

    async def _delegate(self, task: str, ctx: CodeContext) -> CodeResult:
        """Open the stream and consume frames to a result (subtasks 02–04)."""
        ...

    def _is_allowlisted(self, command: str) -> bool:
        """Return whether *command*'s binary is in ``settings.bash_allowlist``
        (subtask 03)."""
        ...

    def _truncate(self, content: str) -> tuple[str, bool]:
        """Clamp *content* to ``max_response_tokens`` (subtask 04).

        :return: ``(possibly_truncated_content, was_truncated)``.
        """
        ...

    def _failure(self, reason: str, *, retriable: bool) -> CodeResult:
        """Build a typed failure result with zero token estimate."""
        ...

    def _success(
        self,
        content: str,
        *,
        truncated: bool,
        token_estimate: int,
        tool_call_count: int,
        tool_result_count: int,
        frame_count: int,
    ) -> CodeResult:
        """Build a success result carrying observability metadata."""
        ...
```

## Implementation notes

- The `CodeBackend` protocol, `CodeContext`, and `CodeResult` are stood up by
  task 06.0 in `aegis/code_intel/backend.py` — imported here, never redefined.
  plan.md's Architecture describes the contract only as
  `delegate(task) → CodeResult` (token-accounting seam). The 04.0 README (the
  authoritative task spec) instead names the method `run()` and references
  `ctx.dry_run` and `client.query(task, run_id)`. This subtask adopts the
  README wording (`run(task, ctx)`) and assumes the minimal protocol-conformant
  shapes below; task 06.0 must reconcile the exact names. See the
  inconsistency flag in the task summary.
- **Assumed `CodeContext` shape** (minimal, protocol-conformant): a small
  frozen carrier with `run_id: str` and `dry_run: bool`. It carries no payload
  text.
- **Assumed `CodeResult` shape**: `text: str`, `ok: bool`,
  `retriable: bool` (meaningful only when `ok is False`), `token_estimate: int`,
  and `metadata: dict[str, object]` holding `truncated`, `tool_call_count`,
  `tool_result_count`, and `frame_count`. `_failure` / `_success` are the two
  tool-local constructors so callers never build `CodeResult` inline (keeps the
  success/failure branches single-purpose for coverage).
- **Assumed protocol surface**: `CodeBackend` exposes `name` and `description`
  class attributes plus the async `run`. If task 06.0's contract omits
  `name`/`description`, keep them as harmless extras.
- `AgentMessage` (the parsed frame type) and its `FrameType` enum are
  re-exported by `aegis/openclaude/grpc/client.py` (task 02.0), so `tool.py`
  imports frame types from the client module and never touches the `_pb2`
  stubs or `grpc` directly (C3).
- Constructor performs no I/O; the gRPC channel is created lazily inside the
  client on first `query()` (task 02.0), so building an `OpenClaudeTool` in a
  unit test starts no process.

## Constraints

- `from __future__ import annotations` at the top; `Optional[T]` from `typing`,
  never `T | None` (C9).
- No `import grpc` and no `_pb2` import in this file (C3); frame types come
  from the client module only.
- No `Any` in any signature; `ruff` clean.
- Every public class/method has an RST-style docstring (C9).
- Constructor opens no connection, starts no process, and does not touch the
  budget.

## Success criteria

- [ ] `OpenClaudeTool(client, settings, bus, budget)` constructs with all four
      collaborators injected and performs no I/O.
- [ ] `OpenClaudeTool` is a structural/nominal `CodeBackend` and is accepted where a `CodeBackend` is expected.
- [ ] `name` and `description` are class attributes; `description` advertises
      open-ended multi-file navigation.
- [ ] `run`, `_delegate`, `_is_allowlisted`, `_truncate`, `_failure`,
      `_success` exist with the signatures above and `...` bodies.
- [ ] No `import grpc` / `_pb2` import appears in the file (C3 grep check).
- [ ] `ruff check src/ tests/` - clean; no
      `Any` in any signature.
