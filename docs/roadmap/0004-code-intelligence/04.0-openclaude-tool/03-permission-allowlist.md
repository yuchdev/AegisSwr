# 03 - Permission request handling + allowlist

**Parent task:** 04.0 OpenClaudeTool Implementor
**State:** ⬜ Not started
**Depends on:** 02
**Blocks:** 04

## Objective

Implement the tool-side permission gate and the tool-frame observability
emissions wired in subtask 02. On a `PERMISSION_REQ` frame, extract the
requested command's binary and auto-approve when it is in
`settings.bash_allowlist`; when it is **not**, raise `PermissionDeniedError`
(task 05.0 — imported), which `run()` translates to a **non-retriable** failure,
and emit `OpenClaudePermissionDenied` (task 05.0 event — imported). On
`TOOL_CALL` / `TOOL_RESULT` frames emit `OpenClaudeToolCall` /
`OpenClaudeToolResult` (C8). This keeps forensic analysis read-only (C7): the
allowlist is the mechanism that guarantees OpenClaude cannot mutate the
repository under analysis, and a denial never corrupts budget accounting
(the charge in subtask 04 happens only on the success path).

## File: `aegis/openclaude/tool.py`

```python
def _emit_tool_call(self, msg: AgentMessage, ctx: CodeContext) -> None:
    """Emit :class:`OpenClaudeToolCall` for a ``TOOL_CALL`` frame (C8).

    :param msg: The ``TOOL_CALL`` frame; ``msg.tool`` names the invoked tool.
    :param ctx: Per-invocation context supplying ``run_id``.
    """
    self._bus.publish(OpenClaudeToolCall(run_id=ctx.run_id, tool=msg.tool))

def _emit_tool_result(self, msg: AgentMessage, ctx: CodeContext) -> None:
    """Emit :class:`OpenClaudeToolResult` for a ``TOOL_RESULT`` frame (C8).

    :param msg: The ``TOOL_RESULT`` frame.
    :param ctx: Per-invocation context supplying ``run_id``.
    """
    self._bus.publish(OpenClaudeToolResult(run_id=ctx.run_id, tool=msg.tool))

def _check_permission(self, msg: AgentMessage, ctx: CodeContext) -> None:
    """Allow an allowlisted ``PERMISSION_REQ``; deny anything else.

    Auto-approval is implicit: an allowlisted command returns and stream
    iteration continues (the approval handshake back to OpenClaude is the gRPC
    client's responsibility, task 02.0). A non-allowlisted command emits
    :class:`OpenClaudePermissionDenied` and raises so the invocation halts
    read-only (C7); :meth:`run` maps the raise to a non-retriable failure.

    :param msg: The ``PERMISSION_REQ`` frame; ``msg.content`` carries the
        requested command.
    :raises PermissionDeniedError: When the command's binary is not in
        ``settings.bash_allowlist``.
    """
    command = self._requested_command(msg)
    if self._is_allowlisted(command):
        return
    self._bus.publish(
        OpenClaudePermissionDenied(run_id=ctx.run_id, command=command)
    )
    raise PermissionDeniedError(command=command)

def _requested_command(self, msg: AgentMessage) -> str:
    """Extract the human-readable command string from a permission frame."""
    ...

def _is_allowlisted(self, command: str) -> bool:
    """Return whether *command*'s leading binary is in the bash allowlist.

    :param command: The requested shell command (e.g. ``"rg -n foo src/"``).
    :return: ``True`` iff the first whitespace-delimited token (basename) is a
        member of ``settings.bash_allowlist``.
    """
    ...
```

## Implementation notes

- **Binary extraction**: take the first whitespace-delimited token of the
  requested command and reduce it to its basename before membership-testing
  against `settings.bash_allowlist`, so `/usr/bin/rg` and `rg` both match the
  `rg` entry. Do not attempt full shell parsing; a command that cannot be
  reduced to a bare binary name is treated as **not** allowlisted (deny).
- The allowlist comparison is exact-match on the basename against
  `settings.bash_allowlist` (the C1 default is
  `gtags,global,semgrep,rg,find,cat`). Case-sensitive.
- `PermissionDeniedError` and the `OpenClaude*` events are defined in task 05.0
  and imported here — never redefined. Add
  `from aegis.openclaude.exceptions import PermissionDeniedError` and
  `from aegis.openclaude.events import (OpenClaudePermissionDenied,
  OpenClaudeToolCall, OpenClaudeToolResult)`.
- `_check_permission` raises; the `try/except PermissionDeniedError` that
  converts the raise into a non-retriable `CodeResult` lives in `run()` and is
  finalised in subtask 04. Raising (rather than returning) keeps the deny path
  a single exit point that subtask 04's outer guard catches.
- Event payloads carry only `run_id`, the tool name, or the command string —
  never response/output text (C9). The command string is a shell invocation
  (`rg -n foo`), not incident payload, but keep it short and do not attach
  frame `content` (which may include tool output) to any event.
- **Contract divergence to carry**: C2 states the gRPC *client* auto-approves
  allowlisted `PERMISSION_REQ` and raises `PermissionDeniedError` for
  non-allowlisted ones. The 04.0 README (authoritative task spec) and this
  subtask place that decision in the *tool*. Implemented tool-side per the
  README; see the inconsistency flag in the task summary. The approval
  handshake mechanics remain the client's concern either way.

## Constraints

- `from __future__ import annotations`; `Optional[T]` never `T | None` (C9).
- `PermissionDeniedError` and all events are imported from task 05.0 — not
  redefined here.
- Deny path must not touch `CallBudget` (no charge, no refund) — budget is only
  charged on the success path in subtask 04 (C5/C7).
- Allowlist check and permission decision are separate, flat branches (one for
  allowlisted-return, one for denied-raise) so both are independently coverable
  (task 07.0).
- No `msg.content` / tool output is logged or attached to events (C9).

## Success criteria

- [ ] `TOOL_CALL` frame publishes exactly one `OpenClaudeToolCall(run_id, tool)`.
- [ ] `TOOL_RESULT` frame publishes exactly one
      `OpenClaudeToolResult(run_id, tool)`.
- [ ] A `PERMISSION_REQ` whose binary is in `bash_allowlist` returns without
      raising and stream iteration continues.
- [ ] A `PERMISSION_REQ` whose binary is **not** in `bash_allowlist` emits
      `OpenClaudePermissionDenied(run_id, command)` and raises
      `PermissionDeniedError`.
- [ ] Full-path binaries (`/usr/bin/rg`) match their allowlist basename entry.
- [ ] A command that cannot be reduced to a bare binary is denied.
- [ ] The deny path performs zero `CallBudget` mutations.
- [ ] No frame content / tool output is logged or placed on an event.
- [ ] `mypy --strict`, `ruff`, `replace_optional.py --check` clean.
