# 04 - Budget pre-check + truncation

**Parent task:** 04.0 OpenClaudeTool Implementor
**State:** ⬜ Not started
**Depends on:** 03
**Blocks:** 06.0, 07.0

## Objective

Finalise `run()` as the public entry point that orchestrates the layers built
in 02–03 and adds boundary budget accounting (C5), the dry-run short-circuit
(C9), truncation, and terminal-frame / gRPC-error handling. In order: pre-check
`CallBudget` against `max_response_tokens // 4` and return a **non-retriable**
failure with **zero gRPC calls** if insufficient (C5 step 1); short-circuit
`ctx.dry_run` to a `[dry-run]` result with `token_estimate=0` and **no gRPC
call** (C5 step 3); otherwise delegate to the stream loop, catching
`PermissionDeniedError` (→ non-retriable) and `OpenClaudeUnavailableError`
(→ retriable/non-retriable per gRPC status). After a clean `DONE`, truncate the
accumulated content at `max_response_tokens`, charge `max(1, len(content) // 4)`
tokens (C5 step 2 — never pre-charged), emit `OpenClaudeStreamCompleted` with
that boundary estimate (C8 — the only event carrying it), and return success.
On `ERROR` frame or gRPC error, emit `OpenClaudeStreamError` and return the
appropriate failure. No exception escapes `run()` (C9).

## File: `aegis/openclaude/tool.py`

```python
async def run(self, task: str, ctx: CodeContext) -> CodeResult:
    """Delegate *task* to OpenClaude; return a typed :class:`CodeResult`.

    Ordered gates (C5): budget pre-check, then dry-run, then the gRPC stream.
    Never raises — every failure path returns a typed result (C9).

    :param task: The open-ended code-navigation prompt.
    :param ctx: Per-invocation context carrying ``run_id`` and ``dry_run``.
    :return: A success or typed-failure :class:`CodeResult`.
    """
    # C5 step 1 — pre-check before any connection is opened.
    pre_estimate = self._settings.max_response_tokens // 4
    if not self._budget.can_afford(pre_estimate):
        return self._failure("insufficient budget", retriable=False)

    # C9 — dry-run short-circuits with zero gRPC calls and zero tokens.
    if ctx.dry_run:
        return self._failure("[dry-run]", retriable=False) if False else (
            self._dry_run_result()
        )

    try:
        return await self._delegate(task, ctx)
    except PermissionDeniedError:
        # Event already emitted in _check_permission (subtask 03).
        return self._failure("permission denied", retriable=False)
    except OpenClaudeUnavailableError as exc:
        self._bus.publish(
            OpenClaudeStreamError(run_id=ctx.run_id, reason="grpc_unavailable")
        )
        return self._failure("grpc error", retriable=exc.retriable)

def _dry_run_result(self) -> CodeResult:
    """Return the ``[dry-run]`` result with a zero token estimate (C5/C9)."""
    return self._success(
        "[dry-run]",
        truncated=False,
        token_estimate=0,
        tool_call_count=0,
        tool_result_count=0,
        frame_count=0,
    )

def _on_done(
    self,
    content: str,
    ctx: CodeContext,
    *,
    tool_call_count: int,
    tool_result_count: int,
    frame_count: int,
) -> CodeResult:
    """Truncate, charge the boundary estimate, emit completion, return success.

    :param content: The accumulated ``TEXT_CHUNK`` concatenation.
    :param ctx: Per-invocation context supplying ``run_id``.
    :return: A success :class:`CodeResult` with observability metadata.
    """
    text, truncated = self._truncate(content)            # C5 step 4
    token_estimate = max(1, len(text) // 4)              # C5 step 2
    self._budget.charge(token_estimate)                  # charged AFTER stream
    self._bus.publish(
        OpenClaudeStreamCompleted(
            run_id=ctx.run_id,
            token_estimate=token_estimate,
            frame_count=frame_count,
        )
    )
    return self._success(
        text,
        truncated=truncated,
        token_estimate=token_estimate,
        tool_call_count=tool_call_count,
        tool_result_count=tool_result_count,
        frame_count=frame_count,
    )

def _on_error_frame(self, msg: AgentMessage, ctx: CodeContext) -> CodeResult:
    """Handle a terminal ``ERROR`` frame: emit and fail non-retriably.

    :param msg: The ``ERROR`` frame (a terminal error message).
    :param ctx: Per-invocation context supplying ``run_id``.
    :return: A non-retriable failure :class:`CodeResult`.
    """
    self._bus.publish(
        OpenClaudeStreamError(run_id=ctx.run_id, reason="error_frame")
    )
    return self._failure("stream error", retriable=False)

def _truncate(self, content: str) -> tuple[str, bool]:
    """Clamp *content* to ``max_response_tokens`` characters-equivalent.

    :return: ``(text, truncated)`` — ``text`` is ``content`` unchanged when
        within budget, else clipped; ``truncated`` reflects whether clipping
        occurred.
    """
    ...
```

> `_delegate` (subtask 02) is finalised here to call `_on_done(...)` at its
> `DONE` exit instead of the placeholder `_success(...)`, passing the
> accumulated content and counts.

## Implementation notes

- **Ordering is load-bearing (C5)**: budget pre-check first (no connection on
  insufficient budget), then dry-run (no connection), then the stream. A
  dry-run with an over-budget account still returns the non-retriable
  budget failure — the pre-check runs before the dry-run branch.
- The `ctx.dry_run` block above is written awkwardly for illustration; the
  real body is simply `if ctx.dry_run: return self._dry_run_result()`. Keep it
  a single flat branch (the `False`-guarded ternary is not real code).
- **Charge is post-completion only (C5 step 2)**: `max(1, len(content) // 4)`
  after truncation, never pre-charged. The pre-check (`max_response_tokens //
  4`) reserves nothing — it only gates entry — so a denied permission, an
  `ERROR` frame, or a gRPC failure charges **zero** tokens.
- **Truncation (C5 step 4)** clips the accumulated text to a
  `max_response_tokens`-derived length and sets `truncated=True` in
  `CodeResult.metadata`; `token_estimate` is computed on the truncated text so
  it never exceeds the cap. (Assumption: the cap is in token-equivalents; using
  the same `//4` char/token approximation, the char clamp is
  `max_response_tokens * 4`. Note this and let task 06.0/07.0 pin the exact
  unit.)
- **Retriable classification** comes from the exception, not from `grpc`
  (which `tool.py` must not import, C3). The client raises
  `OpenClaudeUnavailableError` for both `UNAVAILABLE` and `DEADLINE_EXCEEDED`
  (task 02.0); this subtask assumes that exception exposes a
  `retriable: bool` attribute (`True` for `UNAVAILABLE`, `False` for
  `DEADLINE_EXCEEDED` / other). **Flag**: task 05.0's `OpenClaudeUnavailableError`
  must expose this attribute, since `tool.py` cannot inspect the raw gRPC
  status code. See the task summary.
- `OpenClaudeStreamCompleted` is the **only** event carrying `token_estimate`
  (C8); do not attach it to any other event. It also carries `frame_count`
  (task 05.0).
- All emitted `OpenClaudeStreamError` payloads carry only `run_id` and a short
  status `reason` string — never the raw error message, which may echo payload
  (C9).
- The outer `try/except` in `run()` catches the two expected typed exceptions;
  a defensive final `except Exception` returning a non-retriable failure keeps
  the "no exception escapes `run()`" guarantee (C9) — implement it as the last
  arm and cover it with a fault-injecting test.

## Constraints

- `from __future__ import annotations`; `Optional[T]` never `T | None` (C9).
- No `import grpc` / `_pb2` in this file (C3); retriability comes from the
  exception attribute.
- Budget charged **after** `DONE` only; pre-check reserves nothing; failure
  paths charge zero (C5).
- `--dry-run` and insufficient-budget paths make **zero** calls to
  `client.query` (assert via mock call-count in task 07.0).
- Every branch — budget-insufficient, dry-run, allowlisted-permission,
  denied-permission, truncated, `ERROR`-frame, `UNAVAILABLE`-retriable,
  `DONE`-success — is a small single-purpose arm, independently testable to
  satisfy **100% branch coverage on `tool.py`** (task 07.0). No nested
  compound conditionals.
- No exception escapes `run()`; no unredacted response/error text is logged or
  placed on an event (C9).

## Success criteria

- [ ] Insufficient budget returns a non-retriable failure and `client.query`
      is **never** called.
- [ ] `ctx.dry_run` returns `text == "[dry-run]"`, `token_estimate == 0`, and
      `client.query` is **never** called (checked even when budget is ample).
- [ ] The pre-check runs before the dry-run branch (over-budget + dry-run still
      returns the budget failure).
- [ ] A clean `DONE` charges exactly `max(1, len(text) // 4)` tokens **after**
      the stream, emits one `OpenClaudeStreamCompleted(token_estimate,
      frame_count)`, and returns success.
- [ ] Content exceeding `max_response_tokens` is truncated, `metadata`
      `truncated` is `True`, and `token_estimate` is computed on the truncated
      text.
- [ ] A `PERMISSION_REQ` denial returns a non-retriable failure and charges
      zero tokens.
- [ ] An `ERROR` frame emits `OpenClaudeStreamError` and returns a
      non-retriable failure with zero tokens charged.
- [ ] `OpenClaudeUnavailableError` with `retriable=True` returns a retriable
      failure; with `retriable=False` returns non-retriable — both emit
      `OpenClaudeStreamError` and charge zero.
- [ ] `OpenClaudeStreamCompleted` is the only event carrying `token_estimate`.
- [ ] No exception escapes `run()`; a fault-injected `_delegate` still yields a
      typed failure.
- [ ] 100% branch coverage on `tool.py`; `ruff` and
      `ruff check src/ tests/` - clean.
