# 02 - `delegate()`: budget pre-check, token-estimate resolution, dry-run, truncation

**Parent task:** 08.0 OpenHands Tool Implementor
**State:** ✅ Complete
**Depends on:** 01
**Blocks:** 09.0, 11.0

## Objective

Finalise `delegate()` as the public `CodeIntelBackend` entry point that
orchestrates the stream loop built in subtask 01 and adds boundary budget
accounting, the dry-run short-circuit, **dual-source token-estimate resolution**
(C9), truncation, and terminal-event / transport-error handling. In order:
pre-check `CallBudget` against `max_response_tokens // 4` and return a
**non-retriable** failure with **zero REST/WS calls** if insufficient (C5 step 1
equivalent); short-circuit `ctx.dry_run` to a `[dry-run]` result with
`token_estimate=0` and **no network call** (C8 item 6); otherwise delegate to
`_consume_stream`, catching `OpenHandsPermissionDeniedError` (→ non-retriable)
and `OpenHandsUnavailableError` (→ retriable/non-retriable per its `retriable`
attribute). After a clean `FINISH`, `_on_finish` **resolves the token estimate**
(server-reported real usage if the stream carried it, else the boundary estimate
`max(1, len(content) // 4)`), truncates the accumulated content, charges that
estimate **after** the stream (never pre-charged), emits
`OpenHandsStreamCompleted` (`openhands.completed`, the only event carrying the
token figure, C10), and returns success. On an `ERROR` event or a transport
error, emit `OpenHandsStreamError` and return the appropriate failure. **No
exception escapes `delegate()`** (C13).

This is the direct sibling of `OpenClaudeTool.delegate` / `_on_done` (0004 task
04.0, subtask 04). The **only structural difference** is C9's dual token source:
where OpenClaude always computes the boundary estimate, OpenHands prefers the
server's real usage when present and falls back to the same boundary estimate
otherwise — still through the unchanged `CodeResult.token_estimate` `int` field.

## File: `aegis_swr/openhands/tool.py`

```python
async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
    """Delegate *task* to OpenHands; return a typed :class:`CodeResult`.

    Ordered gates: budget pre-check, then dry-run, then the REST/WS stream.
    Never raises - every failure path returns a typed result (C13).

    :param task: The open-ended code-navigation prompt.
    :param ctx: Per-invocation :class:`CodeTaskContext` carrying ``run_id`` and
        ``dry_run``.
    :return: A success or typed-failure :class:`CodeResult`.
    """
    # Step 1 - pre-check BEFORE any connection is opened. An insufficient budget
    # returns a non-retriable failure with ZERO REST/WS calls; the pre-check
    # reserves nothing (charge is post-completion only). Optimistic floor, as in
    # OpenClaude: the worst-case post-charge is ~max_response_tokens (~4x this).
    pre_estimate = self._settings.max_response_tokens // 4
    if not self._budget.can_afford(pre_estimate):
        return self._failure("insufficient_budget", retriable=False)

    # C8 item 6 - dry-run short-circuits with ZERO network calls and zero tokens.
    # Runs AFTER the pre-check, so an over-budget dry-run still returns the
    # budget failure (pre-check precedence).
    if ctx.dry_run:
        return self._dry_run_result()

    try:
        return await self._consume_stream(task, ctx)
    except OpenHandsPermissionDeniedError:
        # Event already emitted in _check_action (subtask 01).
        return self._failure("permission_denied", retriable=False)
    except OpenHandsUnavailableError as exc:
        self._bus.publish(
            OpenHandsStreamError(
                run_id=str(ctx.run_id),
                error_type="transport",
                code=exc.status_code or "UNAVAILABLE",
                event_count=0,
            )
        )
        return self._failure("transport_error", retriable=exc.retriable)
    except Exception:
        # Defensive final arm (C13): no exception escapes delegate(); every
        # failure returns a typed CodeResult. Must-never-raise resilience
        # boundary (mirrors OpenClaudeTool's X002-exempt final arm).
        return self._failure("internal_error", retriable=False)

def _dry_run_result(self) -> CodeResult:
    """Return the ``[dry-run]`` result with a zero token estimate (C8/C13).

    Short-circuits every external call: no ``client.stream`` is issued and the
    budget is untouched. ``content`` is a fixed non-payload marker and
    ``token_estimate`` is ``0``.

    :return: A success :class:`CodeResult` marking a suppressed call.
    """
    return self._success(
        "[dry-run]",
        truncated=False,
        token_estimate=0,
        action_count=0,
        observation_count=0,
        event_count=0,
    )

def _on_finish(
    self,
    content: str,
    ctx: CodeTaskContext,
    *,
    server_usage: Optional[OpenHandsUsage],
    action_count: int,
    observation_count: int,
    event_count: int,
) -> CodeResult:
    """Resolve tokens, truncate, charge, emit completion, and succeed.

    Runs only on the clean ``FINISH`` success path. Truncates the accumulated
    text, resolves ``token_estimate`` on the *truncated* text (C9 - server usage
    if present, else the boundary estimate), charges the budget AFTER the stream
    (never pre-charged), and emits the sole event carrying the token figure
    (:class:`OpenHandsStreamCompleted`, C10).

    :param content: The accumulated agent-text concatenation.
    :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
    :param server_usage: Server-reported usage captured on the ``FINISH`` event,
        or ``None`` when the server reported none (C9).
    :param action_count: Number of ``ACTION`` events observed.
    :param observation_count: Number of ``OBSERVATION`` events observed.
    :param event_count: Total number of events observed in the stream.
    :return: A success :class:`CodeResult` with observability metadata.
    """
    text, truncated = self._truncate(content)
    token_estimate = self._resolve_token_estimate(text, server_usage)  # C9
    self._budget.charge(token_estimate)  # charged AFTER stream, success only
    self._bus.publish(
        OpenHandsStreamCompleted(
            run_id=str(ctx.run_id),
            token_estimate=token_estimate,
            event_count=event_count,
            truncated=truncated,
        )
    )
    return self._success(
        text,
        truncated=truncated,
        token_estimate=token_estimate,
        action_count=action_count,
        observation_count=observation_count,
        event_count=event_count,
    )

def _resolve_token_estimate(
    self, content: str, server_usage: Optional[OpenHandsUsage]
) -> int:
    """Resolve ``CodeResult.token_estimate`` from real usage or the estimate (C9).

    Prefers the server-reported real usage when the stream carried it; otherwise
    falls back to the boundary estimate ``max(1, len(content) // 4)`` - the same
    OpenClaude convention. Either way the return is a plain ``int`` on the
    unchanged ``token_estimate`` field, so ``CodeAgent`` / ``CallBudget`` stay
    fully backend-agnostic (C9 hard invariant).

    :param content: The accumulated (already truncated) response text.
    :param server_usage: Real usage from the terminal event, or ``None``.
    :return: ``server_usage.input_tokens + server_usage.output_tokens`` when
        usage is present, else ``max(1, len(content) // 4)``.
    """
    if server_usage is not None:
        return server_usage.input_tokens + server_usage.output_tokens
    return max(1, len(content) // 4)

def _on_error_event(self, ctx: CodeTaskContext, event_count: int) -> CodeResult:
    """Handle a terminal ``ERROR`` event: emit and fail non-retriably (C13).

    Emits :class:`OpenHandsStreamError` carrying only a classification, a status
    code, and the event count (never the raw error text, C13), then returns a
    non-retriable failure. The budget is untouched: an ``ERROR`` event charges
    zero tokens.

    :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
    :param event_count: Number of events consumed up to and including the
        terminal ``ERROR`` event.
    :return: A non-retriable failure :class:`CodeResult`.
    """
    self._bus.publish(
        OpenHandsStreamError(
            run_id=str(ctx.run_id),
            error_type="stream_error",
            code="error_event",
            event_count=event_count,
        )
    )
    return self._failure("stream_error", retriable=False)

def _truncate(self, content: str) -> tuple[str, bool]:
    """Clamp *content* to ``settings.max_response_tokens`` (character-equivalent).

    Uses the same ``//4`` char/token approximation as the boundary estimate, so
    the character clamp is ``max_response_tokens * 4``. Content within the clamp
    is returned unchanged; longer content is clipped and flagged.

    :param content: The accumulated response text.
    :return: ``(possibly_truncated_content, was_truncated)``.
    """
    clamp = self._settings.max_response_tokens * 4
    if len(content) <= clamp:
        return content, False
    return content[:clamp], True

def _failure(self, reason: str, *, retriable: bool) -> CodeResult:
    """Build a typed failure :class:`CodeResult` with a zero token estimate.

    Carries an empty non-payload ``content``, ``token_estimate=0``, and encodes
    ``{"ok": False, "error": reason, "retriable": retriable}`` in ``metadata``
    (never raw payload text, C13). ``available=True``: a backend WAS registered;
    this is a per-call failure recorded in metadata (C4), not an
    unavailable-capability result.

    :param reason: Short, payload-free failure marker.
    :param retriable: Whether the caller may retry the delegation.
    :return: A typed-failure :class:`CodeResult`.
    """
    return CodeResult(
        content="",
        token_estimate=0,
        available=True,
        truncated=False,
        metadata={"ok": False, "error": reason, "retriable": retriable},
    )

def _success(
    self,
    content: str,
    *,
    truncated: bool,
    token_estimate: int,
    action_count: int,
    observation_count: int,
    event_count: int,
) -> CodeResult:
    """Build a success :class:`CodeResult` carrying observability metadata.

    Records ``{"ok": True, "action_count": ..., "observation_count": ...,
    "event_count": ...}`` in ``metadata`` (counts only, never payload, C13).

    :param content: The accumulated (already truncated) response text.
    :param truncated: Whether ``content`` was clipped at the response cap.
    :param token_estimate: Resolved token estimate for the call (C9).
    :param action_count: Number of ``ACTION`` events observed.
    :param observation_count: Number of ``OBSERVATION`` events observed.
    :param event_count: Total number of events observed in the stream.
    :return: A success :class:`CodeResult`.
    """
    return CodeResult(
        content=content,
        token_estimate=token_estimate,
        available=True,
        truncated=truncated,
        metadata={
            "ok": True,
            "action_count": action_count,
            "observation_count": observation_count,
            "event_count": event_count,
        },
    )
```

> `_consume_stream` (subtask 01) is finalized here to call `_on_finish(...)` at
> its `FINISH`/loop exit (passing `server_usage` and the counts) and
> `_on_error_event(...)` at its `ERROR` handler.

## Implementation notes

- **Ordering is load-bearing:** budget pre-check first (no connection on
  insufficient budget), then dry-run (no connection), then the stream. A dry-run
  with an over-budget account still returns the non-retriable budget failure —
  the pre-check runs before the dry-run branch. Assert both `client.stream` is
  **never** called on the insufficient-budget and dry-run paths (mock call-count,
  task 11.0), exactly as 0004 asserts for `client.query`.
- **Token estimate is dual-source (C9) — the one genuine deviation from
  OpenClaude.** `_resolve_token_estimate` prefers the server's real usage
  (`usage.input_tokens + usage.output_tokens`) captured on the `FINISH` event in
  subtask 01; it falls back to `max(1, len(content) // 4)` only when the server
  reported none. Both are plain `int`s on the unchanged `token_estimate` field
  (C9 hard invariant). **Flag:** task 07.0/09.0 must pin `OpenHandsUsage`'s field
  names (`input_tokens`/`output_tokens` vs a single `total_tokens`); this subtask
  assumes the two-field split and sums them — reconcile if the client exposes a
  precomputed total.
- **Charge is post-completion only:** the resolved estimate is charged after
  truncation, never pre-charged. The pre-check (`max_response_tokens // 4`)
  reserves nothing — it only gates entry — so a denied action, an `ERROR` event,
  or a transport failure charges **zero** tokens.
- **`max_response_tokens` is assumed on `OpenHandsSettings`.** The pre-check and
  `_truncate` both read `settings.max_response_tokens`. C5 requires every backend
  settings class to mirror `OpenClaudeSettings`' proven shape (which defines
  `max_response_tokens`), so this subtask assumes task 06.0's `OpenHandsSettings`
  defines it. **Flag:** C8 item 5's enumerated field list does **not** name
  `max_response_tokens` explicitly — task 06.0 must add it (mirroring OpenClaude)
  or this task and the pre-check/truncation must be reconciled. Do not silently
  invent a literal default in `tool.py`; the cap belongs in settings.
- **Retriable classification comes from the exception, not from any transport
  library** (which `tool.py` must not import, C3). `OpenHandsUnavailableError`
  (task 09.0, mirroring `OpenClaudeUnavailableError`) must expose a
  `retriable: bool` and an `Optional[str] status_code`; the tool reads those and
  never inspects a raw HTTP/WS status. **Flag** this required attribute shape to
  task 09.0.
- **`OpenHandsStreamCompleted` is the only event carrying `token_estimate`**
  (C10); do not attach it to any other event. It also carries `event_count` and
  `truncated`.
- All emitted `OpenHandsStreamError` payloads carry only `run_id`, an
  `error_type` classification, a short `code`, and `event_count` — **never** the
  raw error message, which may echo response/payload text (C13).
- The outer `try/except` catches the two expected typed exceptions; the
  defensive final `except Exception` returning a non-retriable failure preserves
  the "no exception escapes `delegate()`" guarantee (C13) — implement it as the
  last arm and cover it with a fault-injecting test (task 11.0).

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- No import of the OpenHands client library, `httpx`, `websockets`, or any transport stub in this file (C3); retriability comes from the exception attribute, not a status enum.
- Budget charged **after** `FINISH` only; the pre-check reserves nothing; every failure path (insufficient budget, dry-run, denial, `ERROR`, transport) charges **zero** tokens.
- `--dry-run` and insufficient-budget paths make **zero** calls to `client.stream` (assert via mock call-count, task 11.0).
- Every branch — budget-insufficient, dry-run, allowlisted-action, denied-action, truncated, real-usage-token, boundary-estimate-token, `ERROR`-event, transport-retriable, transport-non-retriable, `FINISH`-success, defensive-`Exception` — is a small single-purpose arm, independently testable to satisfy **100% branch coverage on `tool.py`** (task 11.0). No nested compound conditionals.
- No exception escapes `delegate()`; no unredacted response/error/usage text is logged or placed on an event (C13).

## Success criteria

- [ ] Insufficient budget returns a non-retriable failure and `client.stream` is **never** called.
- [ ] `ctx.dry_run` returns `content == "[dry-run]"`, `token_estimate == 0`, and `client.stream` is **never** called (checked even when the budget is ample).
- [ ] The pre-check runs before the dry-run branch (over-budget plus dry-run still returns the budget failure).
- [ ] A clean `FINISH` **with** server usage sets `token_estimate == usage.input_tokens + usage.output_tokens`, charges exactly that after the stream, emits one `OpenHandsStreamCompleted`, and returns success.
- [ ] A clean `FINISH` **without** server usage sets `token_estimate == max(1, len(text) // 4)` on the truncated text and charges exactly that.
- [ ] Content exceeding `max_response_tokens` is truncated, `metadata` `truncated` is `True`, and the boundary estimate (when used) is computed on the truncated text.
- [ ] A denied action returns a non-retriable failure and charges zero tokens.
- [ ] An `ERROR` event emits `OpenHandsStreamError` and returns a non-retriable failure with zero tokens charged.
- [ ] `OpenHandsUnavailableError` with `retriable=True` returns a retriable failure; with `retriable=False` returns non-retriable — both emit `OpenHandsStreamError` and charge zero.
- [ ] `OpenHandsStreamCompleted` is the only event carrying `token_estimate`.
- [ ] No exception escapes `delegate()`; a fault-injected `_consume_stream` still yields a typed failure.
- [ ] 100% branch coverage on `tool.py`; `ruff check src/ tests/` - clean.
