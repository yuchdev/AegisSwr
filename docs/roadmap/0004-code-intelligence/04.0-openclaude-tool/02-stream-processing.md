# 02 - Stream processing and content accumulation

**Parent task:** 04.0 OpenClaudeTool Implementor
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 03, 04

## Objective

Flesh out `_delegate()` — the core stream loop. It calls
`client.query(task, run_id)` and iterates the async stream of parsed
agent-message frames (C2), accumulating `TEXT_CHUNK` content into the result
text and tracking counts of `TOOL_CALL` and `TOOL_RESULT` frames plus a total
frame count for observability metadata. This subtask handles the happy-path
frame types (`TEXT_CHUNK`, `TOOL_CALL`, `TOOL_RESULT`, `DONE`) and returns a
preliminary success `CodeResult`; permission handling (03) and budget /
truncation / terminal-error emission (04) layer onto the same loop without
changing its shape. Keep each frame branch a single, flat `if/elif` arm so the
100% branch requirement (task 07.0) stays tractable.

## File: `aegis/openclaude/tool.py`

```python
async def _delegate(self, task: str, ctx: CodeContext) -> CodeResult:
    """Consume the OpenClaude stream to a single text result.

    Iterates the frames yielded by :meth:`OpenClaudeGrpcClient.query`,
    concatenating ``TEXT_CHUNK`` content and counting tool frames. Returns on
    the terminal ``DONE`` frame. Permission handling (subtask 03) and the
    terminal ``ERROR`` / gRPC-error, truncation, charge, and
    ``OpenClaudeStreamCompleted`` emission paths (subtask 04) are added to this
    method by the later subtasks.

    :param task: The open-ended code-navigation prompt.
    :param ctx: Per-invocation context carrying ``run_id``.
    :return: A success :class:`CodeResult` on ``DONE``.
    """
    chunks: list[str] = []
    tool_call_count = 0
    tool_result_count = 0
    frame_count = 0

    async def _handle_text_chunk(msg: AgentMessage) -> Optional[CodeResult]:
        chunks.append(msg.content)
        return None

    async def _handle_tool_call(msg: AgentMessage) -> Optional[CodeResult]:
        nonlocal tool_call_count
        tool_call_count += 1
        self._emit_tool_call(msg, ctx)  # subtask 03
        return None

    async def _handle_tool_result(msg: AgentMessage) -> Optional[CodeResult]:
        nonlocal tool_result_count
        tool_result_count += 1
        self._emit_tool_result(msg, ctx)  # subtask 03
        return None

    async def _handle_permission_req(msg: AgentMessage) -> Optional[CodeResult]:
        self._check_permission(msg, ctx)  # subtask 03 (may raise)
        return None

    async def _handle_done(msg: AgentMessage) -> Optional[CodeResult]:
        return "DONE"  # sentinel: break from loop

    handlers: dict[FrameType, Callable[[AgentMessage], Awaitable[Optional[CodeResult]]]] = {
        FrameType.TEXT_CHUNK: _handle_text_chunk,
        FrameType.TOOL_CALL: _handle_tool_call,
        FrameType.TOOL_RESULT: _handle_tool_result,
        FrameType.PERMISSION_REQ: _handle_permission_req,
        FrameType.DONE: _handle_done,
        FrameType.ERROR: self._on_error_frame,  # subtask 04
    }

    async for msg in self._client.query(task, ctx.run_id):
        frame_count += 1
        handler = handlers.get(msg.type)
        if handler is None:
            continue  # unknown frame type; skip silently
        result = await handler(msg)
        if result == "DONE":
            break
        elif result is not None:
            return result  # early exit (error or other terminal state)

    content = "".join(chunks)
    # subtask 04 truncates + charges + emits OpenClaudeStreamCompleted here.
    return self._success(
        content,
        truncated=False,
        token_estimate=0,
        tool_call_count=tool_call_count,
        tool_result_count=tool_result_count,
        frame_count=frame_count,
    )
```

## Implementation notes

- The stream is server-streaming (C2): `client.query()` is an async generator
  yielding `AgentMessage` frames with `.type: FrameType`, `.content: str`, and
  `.tool: Optional[str]`. The tool consumes; it never constructs proto messages
  (task 02.0 owns that).
- `TEXT_CHUNK` content is appended verbatim to `chunks`; the join is deferred
  to loop exit so accumulation is O(n) and truncation (subtask 04) operates on
  the full string once.
- `DONE` is the normal terminal frame — returns the sentinel `"DONE"` to break
  from the loop; the full text is the concatenation of `TEXT_CHUNK` content,
  matching the client's own contract (C2). Per C2 the `DONE` frame also carries
  the full response text; Aegis SWR trusts the accumulated `TEXT_CHUNK`
  concatenation as the authoritative content and does not read `DONE.content`
  (flag: mild redundancy in the proto contract, harmless here).
- **Handler dict pattern**: Frame types are dispatched via a `dict[FrameType, Handler]`
  that maps each frame type to its async handler function. This is more maintainable
  than a chain of `elif` statements and allows handlers to be tested independently.
  Each handler returns either `None` (continue processing), the sentinel string
  `"DONE"` (normal termination), or a `CodeResult` (early exit for errors).
- `_emit_tool_call`, `_emit_tool_result`, and `_check_permission` are declared
  and implemented in subtask 03; `_on_error_frame` in subtask 04. This subtask
  wires the call sites so the handler dispatch structure is fixed early.
- The counters and `chunks` list live as function-local variables with `nonlocal`
  bindings in nested handlers. `OpenClaudeTool` remains stateless between
  invocations.
- Never log `msg.content` or the accumulated text: it is untrusted response
  payload (C9). Emissions carry counts and ids only (subtask 03 / C8).


## Constraints

- `from __future__ import annotations`; `Optional[T]` never `T | None` (C9).
- Frame handlers are nested async functions within `_delegate`, each handling a
  single frame type. Each is independently testable and coverable (task 07.0).
- No `Any`; `ruff` clean.
- No unredacted `TEXT_CHUNK` / accumulated content reaches any log sink (C9).
- Counters and `chunks` list are function-local with `nonlocal` bindings; the
  tool holds no per-call mutable state.
- Handler dict never references unknown frame types; any unhandled type is
  silently skipped via `.get()` + None check.

## Success criteria

- [ ] `_delegate` calls `self._client.query(task, ctx.run_id)` exactly once and
      iterates it with `async for`.
- [ ] `TEXT_CHUNK` frames are concatenated in order into the result text.
- [ ] `TOOL_CALL` and `TOOL_RESULT` frames increment their respective counters.
- [ ] A total `frame_count` is tracked across every frame type.
- [ ] `DONE` terminates the loop and yields a success `CodeResult` whose
      metadata carries `tool_call_count`, `tool_result_count`, and
      `frame_count`.
- [ ] A stream of only `TEXT_CHUNK` + `DONE` returns the joined text with zero
      tool counts.
- [ ] No `msg.content` or accumulated content is logged.
- [ ] `ruff check src/ tests/` - clean.
