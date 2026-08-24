# 04 - `health_check()` + timeout handling

**Parent task:** 02.0 gRPC Proto & Client
**State:** ⬜ Not started
**Depends on:** 03, 05.0 (imports `OpenClaudeUnavailableError` from `aegis.openclaude.exceptions`)
**Blocks:** 03.0 (Process Lifecycle: external-mode readiness probe and managed-mode port wait call `health_check()`), 04.0 (OpenClaudeTool relies on `query()` raising `OpenClaudeUnavailableError`)

## Objective

Complete the reachability and timeout behaviour of `OpenClaudeGrpcClient`
(subtask 03): implement `health_check()` so it probes the sidecar and returns a
plain `bool` - `True` only when a terminal `DONE` frame arrives within
`connect_timeout_s`, `False` on any unreachability or timeout, **never
raising**. Implement `query()`'s status-error translation so gRPC `UNAVAILABLE`
and `DEADLINE_EXCEEDED` become `OpenClaudeUnavailableError` (a retriable
transport failure), while the per-request deadline is enforced from
`settings.request_timeout_s`. `OpenClaudeUnavailableError` is defined in Task
05.0 and imported, never redefined here.

## File: `aegis/openclaude/grpc/client.py` (methods added to the subtask-03 class)

```python
from __future__ import annotations

import grpc  # (already imported in subtask 03; this file remains the sole importer, C3)

from aegis.openclaude.exceptions import OpenClaudeUnavailableError

_HEALTH_PROBE_PROMPT = "ping"  # inert probe; never reaches a shell or a tool


class OpenClaudeGrpcClient:  # methods appended to the subtask-03 definition
    async def health_check(self) -> bool:
        """Probe the sidecar; return whether it answered within the timeout.

        Issues a minimal ``Query`` probe and consumes the stream up to
        ``settings.connect_timeout_s``. Returns ``True`` only if a terminal
        ``DONE`` frame is observed inside that window. Any transport failure,
        timeout, ``ERROR`` frame, or protocol violation yields ``False``.

        This method **never raises** - it is the readiness predicate used by the
        process lifecycle manager (Task 03.0) and must be safe to poll.

        :return: ``True`` if a terminal ``DONE`` arrived within
            ``connect_timeout_s``; ``False`` otherwise.
        """
        ...

    def _request_deadline(self) -> float:
        """Per-request gRPC deadline in seconds from ``settings.request_timeout_s``.

        :return: The stream deadline passed as ``timeout=`` to the RPC.
        """
        ...

    @staticmethod
    def _translate_status(error: grpc.aio.AioRpcError) -> OpenClaudeUnavailableError:
        """Map a gRPC status error onto a domain exception.

        ``UNAVAILABLE`` and ``DEADLINE_EXCEEDED`` map to
        :class:`OpenClaudeUnavailableError` (retriable transport failure). Other
        status codes are wrapped in the same type but flagged non-retriable, so
        no bare ``grpc`` exception escapes this file (C3).

        :param error: The gRPC status error raised by the stream.
        :return: An :class:`OpenClaudeUnavailableError` carrying the status code
            (never the response payload).
        """
        ...
```

## Implementation notes

- **`health_check()` timeout.** Wrap the probe stream consumption in
  `asyncio.wait_for(..., timeout=settings.connect_timeout_s)` **and** pass the
  same value as the gRPC call `timeout=` so both the transport and the coroutine
  are bounded. On `asyncio.TimeoutError`, `grpc.aio.AioRpcError`, a terminal
  `ERROR` frame, or a stream that ends without `DONE`, return `False`. Catch
  narrowly (no bare `except:`); log the failure reason at `DEBUG` using the
  status code / exception class only - never the probe response text.
- **Probe cost.** The probe sends `_HEALTH_PROBE_PROMPT` (an inert string that
  triggers no `Bash`/tool use) so a health check never charges the token budget
  and never exercises the allowlist. Budget accounting is a Task 04.0 concern at
  the delegation boundary (C5); `health_check()` is outside it.
- **`query()` deadline & translation.** `query()` (subtask 03) passes
  `timeout=self._request_deadline()` to the streaming RPC. Wrap the
  `async for` over the stub stream in a `try/except grpc.aio.AioRpcError`; on
  catch, call `_translate_status(err)` and `raise` the returned
  `OpenClaudeUnavailableError from err`. `UNAVAILABLE` (server down / port not
  open) and `DEADLINE_EXCEEDED` (request exceeded `request_timeout_s`) are the
  two explicitly-named retriable codes per the task README; both map to
  `OpenClaudeUnavailableError`.
- **Terminal `ERROR` frame vs status error.** A gRPC status error is a transport
  failure (`OpenClaudeUnavailableError`). A terminal `ERROR` *frame* (the stream
  opened fine but OpenClaude reported a logical error) is surfaced to the caller
  as a normal terminal `AgentFrame` in `query()` and mapped to an
  `OpenClaudeStreamError` event by Task 04.0 - it is **not** an
  `OpenClaudeUnavailableError`. Keep these two failure modes distinct.
- **No retry loop here.** This subtask only surfaces the classified failure;
  retry/backoff (with `asyncio.sleep`, never `time.sleep`) is an
  `OpenClaudeTool` / process-lifecycle policy decision (Tasks 03.0/04.0). Any
  backoff added later uses `asyncio.sleep`.
- **`OpenClaudeUnavailableError` ownership.** Imported from
  `aegis.openclaude.exceptions` (Task 05.0). Do **not** define or forward-declare
  it here; Task 02.0 depends on 05.0 for this symbol.
- **Logging.** Emit only status codes and lifecycle facts at `DEBUG`. Never
  include the probe prompt, response `content`, or `run_id`-linked payloads in
  logs or in the exception message (C9, security).

## Constraints

- `health_check()` returns `bool` and **never raises** (guaranteed by narrow,
  exhaustive exception handling).
- `query()` raises `OpenClaudeUnavailableError` on `UNAVAILABLE` /
  `DEADLINE_EXCEEDED`; no raw `grpc.aio.AioRpcError` escapes this file (C3).
- `import grpc` remains confined to this file; the exception type is imported,
  not redefined.
- `asyncio.sleep` for any backoff, never `time.sleep` (C9).
- `from __future__ import annotations`; `Optional[T]` from `typing`; `ruff`
  and `ruff check src/ tests/` - clean; zero new `# type: ignore` (C9).
- No raw payload/response text in any log sink or exception message.

## Success criteria

- [ ] `health_check()` returns `True` when a scripted mock channel yields a
      terminal `DONE` within `connect_timeout_s`.
- [ ] `health_check()` returns `False` (does not raise) on `UNAVAILABLE`,
      `DEADLINE_EXCEEDED`, `asyncio.TimeoutError`, a terminal `ERROR` frame, or a
      stream with no terminal frame.
- [ ] `query()` raises `OpenClaudeUnavailableError` when the mock channel raises
      an `AioRpcError` with `UNAVAILABLE` or `DEADLINE_EXCEEDED`.
- [ ] A terminal `ERROR` *frame* is yielded to the caller, not converted to
      `OpenClaudeUnavailableError`.
- [ ] The per-request RPC deadline is set from `settings.request_timeout_s`.
- [ ] No `grpc` exception type escapes `client.py`; `OpenClaudeUnavailableError`
      is imported from `aegis.openclaude.exceptions`, not redefined.
- [ ] No probe prompt or response text appears in any log line.
- [ ] `ruff check src/ tests/` - clean.
