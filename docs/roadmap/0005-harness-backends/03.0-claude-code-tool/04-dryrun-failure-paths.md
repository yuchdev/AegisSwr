# 04 - Dry-run + timeout + failure-path handling

**Parent task:** 03.0 Claude Code Subprocess Tool
**State:** ✅ Complete
**Depends on:** 03
**Blocks:** 04.0, 05.0

## Objective

Finalise `delegate()` as the public entry point that never raises: complete the
`ctx.dry_run` short-circuit (subtask 03 stub), enforce
`settings.request_timeout_s` via `asyncio.wait_for` around the spawn-and-parse
span (C6 / C13), and classify every failure into a typed `CodeResult` -
insufficient budget, timeout, non-zero exit, missing `result` message, and a
defensive catch-all - each charging **zero** tokens (C6.5). Complete the
`_dry_run_result` / `_failure` / `_success` / `_on_result` bodies from subtask 03,
and add the exit-code / timeout wiring in `process.py` that surfaces a non-zero
exit or a killed child as the forward-declared `ClaudeCodeUnavailableError`. The
overriding guarantee: no exception escapes `delegate()`, and no raw task,
response, argv, stderr, or credential text ever reaches a log sink (C13).

## File: `aegis_swr/claude_code/tool.py`

```python
async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
    """Delegate *task* to a one-shot ``claude`` process; return a typed result.

    Ordered gates (load-bearing): budget pre-check (no spawn on insufficient
    budget) -> ``ctx.dry_run`` short-circuit (no spawn, zero tokens) -> the
    timeout-bounded spawn-parse-charge span. The stream span is wrapped in
    :func:`asyncio.wait_for` with ``settings.request_timeout_s``; a timeout, a
    non-zero exit, a missing ``result`` message, or any unexpected error is
    mapped to a typed failure :class:`CodeResult`. Never raises - every path
    returns a typed result (C13).

    :param task: The open-ended code-navigation prompt (fed to stdin, C6.1).
    :param ctx: Per-invocation :class:`CodeTaskContext` carrying ``run_id`` and
        ``dry_run``.
    :return: A success or typed-failure :class:`CodeResult`.
    """
    if not self._budget.can_afford(self._pre_estimate(task)):
        return self._failure("insufficient_budget", retriable=False)

    if ctx.dry_run:
        return self._dry_run_result()

    try:
        result = await asyncio.wait_for(
            self._run_once(task),
            timeout=self._settings.request_timeout_s,
        )
        return self._on_result(result)
    except asyncio.TimeoutError:
        # The async with in _run_once reaps the child on cancellation (RAII,
        # subtask 01), so no process is orphaned by the timeout.
        return self._failure("timeout", retriable=True)
    except ClaudeCodeUnavailableError as exc:
        return self._failure(exc.reason, retriable=exc.retriable)
    except Exception:
        # Defensive final arm (C13): no exception escapes delegate(); every
        # failure returns a typed CodeResult. Payload-free marker only. This is a
        # must-never-raise resilience boundary (X002 exemption, per OpenClaudeTool).
        return self._failure("internal_error", retriable=False)

async def _run_once(self, task: str) -> ClaudeCodeStreamResult:
    """Spawn one ``claude`` process, parse its stream, verify a clean exit.

    Enters :class:`ClaudeCodeProcess` (subtask 01), reduces stdout via
    :func:`parse_stream` (subtask 02), and after the process exits raises
    :class:`ClaudeCodeUnavailableError` on a non-zero exit code
    (``reason="nonzero_exit"``, non-retriable) so :meth:`delegate` maps it to a
    failure. Kept separate from :meth:`delegate` so the whole spawn-parse span is
    the single unit :func:`asyncio.wait_for` bounds.

    :param task: The open-ended prompt (fed to stdin, C6.1).
    :raises ClaudeCodeUnavailableError: On a non-zero child exit code.
    :return: The reduced :class:`ClaudeCodeStreamResult` on a clean exit.
    """
    ...

def _on_result(self, result: ClaudeCodeStreamResult) -> CodeResult:
    """Convert a reduced stream into a success or typed-failure result.

    * ``result.usage is None`` (no terminal ``result`` message - the child died
      before completing) -> non-retriable ``no_result_message`` failure, zero
      tokens.
    * ``result.is_error`` set -> non-retriable ``result_error`` failure, zero
      tokens.
    * otherwise -> charge the **real** ``result.usage.total`` to the budget AFTER
      completion (C6.2, C9) and return :meth:`_success` with that real
      ``token_estimate``.

    :param result: The reduced stream from :func:`parse_stream`.
    :return: A success or typed-failure :class:`CodeResult`.
    """
    if result.usage is None:
        return self._failure("no_result_message", retriable=False)
    if result.is_error:
        return self._failure("result_error", retriable=False)
    token_estimate = result.usage.total          # C6.2 / C9 - REAL tokens
    self._budget.charge(token_estimate)          # charged AFTER completion only
    return self._success(
        result.content,
        token_estimate=token_estimate,
        frame_count=result.frame_count,
    )

def _dry_run_result(self) -> CodeResult:
    """Return the ``[dry-run]`` result: zero tokens, zero spawns (C6.5/C13)."""
    return self._success("[dry-run]", token_estimate=0, frame_count=0)

def _failure(self, reason: str, *, retriable: bool) -> CodeResult:
    """Build a typed failure :class:`CodeResult` with a zero token estimate (C13)."""
    return CodeResult(
        content="",
        token_estimate=0,
        available=True,   # a backend WAS registered; per-call failure (C4)
        truncated=False,
        metadata={"ok": False, "error": reason, "retriable": retriable},
    )

def _success(self, content: str, *, token_estimate: int, frame_count: int) -> CodeResult:
    """Build a success :class:`CodeResult` carrying observability metadata (C9)."""
    return CodeResult(
        content=content,
        token_estimate=token_estimate,
        available=True,
        truncated=False,
        metadata={"ok": True, "frame_count": frame_count},
    )
```

## File: `aegis_swr/claude_code/process.py`

```python
class ClaudeCodeProcess:
    async def wait_exit(self) -> int:
        """Await the child's exit and return its exit code (RAII-safe).

        Called by :meth:`ClaudeCodeTool._run_once` after the stdout stream is
        drained, so the reduced result and the exit code are both available
        before the ``async with`` unwinds. Idempotent with :meth:`_terminate`:
        awaiting a child already reaped by cancellation returns its recorded
        code. Never logs the child's output (C13).

        :return: The process exit code (``0`` on clean completion).
        """
        ...
```

## Implementation notes

- **Gate ordering is load-bearing (mirrors 0004 C5).** Pre-check first (no spawn
  on insufficient budget), then dry-run (no spawn), then the timeout-bounded
  stream. An over-budget dry-run still returns the budget failure because the
  pre-check precedes the dry-run branch.
- **Timeout via `asyncio.wait_for` (C13).** Bound the entire `_run_once` span
  (spawn + parse + exit-code check) with `settings.request_timeout_s`. On
  `asyncio.TimeoutError`, `wait_for` cancels `_run_once`; the `async with
  ClaudeCodeProcess` in subtask 01 reaps the child on cancellation (SIGTERM ->
  grace -> SIGKILL), so a timeout never orphans a process. A timeout is
  **retriable** (transient); classify it distinctly from a deterministic
  non-zero exit.
- **Exit-code classification.** `_run_once` raises `ClaudeCodeUnavailableError`
  (`reason="nonzero_exit"`, non-retriable) on a non-zero child exit. A stream
  that ended with no `result` message is caught in `_on_result` as
  `no_result_message` (also non-retriable). Distinguish the two so operators can
  tell "the CLI errored out" from "the CLI ran but produced no terminal result".
- **Charge is post-completion only, real, and failure-free-charging.** The budget
  is charged the real `usage.total` **only** on the clean success branch, after
  the stream. Insufficient-budget, dry-run, timeout, non-zero-exit,
  no-result-message, result-error, and the defensive catch-all all charge
  **zero** (C6.5).
- **Defensive catch for all exceptions keeps the never-raise guarantee (C13).** The final
  `except Exception` returns a non-retriable `internal_error` failure and is
  covered by a fault-injecting test (mirrors `OpenClaudeTool.delegate`'s final
  arm and its X002 exemption in `pyproject.toml`). No bare `except:`;
  `asyncio.CancelledError` is **not** swallowed (it is a `BaseException`, outside
  `except Exception`).
- **Secrecy across every failure path (C13).** `_failure` markers are fixed,
  payload-free strings (`"timeout"`, `"nonzero_exit"`, `"no_result_message"`,
  `"result_error"`, `"insufficient_budget"`, `"internal_error"`). No task,
  response, argv, stderr, or credential text is ever formatted into a marker, a
  log line, or a `CodeResult`. `SensitiveFilter` on every sink is the backstop;
  the design must not rely on it - it must not attempt to log payload in the
  first place.
- **Truncation is out of scope.** Unlike OpenClaude (which truncates at
  `max_response_tokens`), this task keeps the accumulated answer as-is;
  `CodeResult.truncated` is always `False` here. If a response cap is later
  desired it is a follow-up, not part of this task.
- **No events yet (Task 05.0).** The `claude_code.completed` event that will
  carry the real `token_estimate` (C10) is Task 05.0; do not emit it here. Task
  05.0 also relocates `ClaudeCodeUnavailableError` to `claude_code/exceptions.py`.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- `settings.request_timeout_s` enforced via `asyncio.wait_for`; a timeout reaps the child (no orphan) and returns a retriable failure (C13).
- Non-zero exit / missing-`result` / result-error / internal-error each returns a typed failure charging **zero** tokens; the real `usage` sum is charged only on the clean success path, after completion (C6.2/C6.5/C9).
- No exception escapes `delegate()`; the final `except Exception` is a resilience boundary; `CancelledError` is not swallowed; no bare `except:` (C13).
- Every failure marker and log line is payload-free; no task/response/argv/ stderr/credential text is logged or placed on a `CodeResult` (C13).
- Every branch - insufficient-budget, dry-run, clean-success, timeout, nonzero-exit, no-result-message, result-error, internal-error - is a small single-purpose arm, independently testable to satisfy **100% branch coverage on`tool.py`'s `delegate`** (Task 11.0).
- `ruff check src/ tests/` - clean; no `Any` in any signature; RST docstrings on every public method (C13).

## Success criteria

- [ ] `ctx.dry_run` returns `content == "[dry-run]"`, `token_estimate == 0`, and **no** process is spawned (checked even when budget is ample) (C6.5).
- [ ] A `request_timeout_s` timeout returns a **retriable** `timeout` failure, charges zero tokens, and leaves no orphaned child (RAII reap on cancel).
- [ ] A non-zero child exit returns a **non-retriable** `nonzero_exit` failure, zero tokens.
- [ ] A stream with no terminal `result` message returns a non-retriable `no_result_message` failure, zero tokens.
- [ ] A `result` message with `is_error` set returns a non-retriable `result_error` failure, zero tokens.
- [ ] A clean stream charges exactly `usage.input_tokens + usage.output_tokens` **after** completion and returns success with that real `token_estimate` (C6.2, C9).
- [ ] A fault-injected `_run_once` still yields a typed `internal_error` failure; no exception escapes `delegate()`.
- [ ] Insufficient-budget, dry-run, and every failure path charge **zero** tokens; the budget is charged only on the clean success path.
- [ ] No task/response/argv/stderr/credential text reaches any log sink or `CodeResult` on any path (C13).
- [ ] 100% branch coverage on `tool.py`'s `delegate`; `ruff check src/ tests/` - clean.
