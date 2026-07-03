# .copilot/loops-emulated — Loop Emulation for Copilot CLI

**Ported from Claude on 2026-07-03.**

Claude Code has a `ScheduleWakeup` primitive that lets a loop reschedule itself
into the same conversation after a delay, enabling multi-iteration stateful
orchestration. Copilot CLI has no equivalent.

## What Claude loops were

Claude loops (`.claude/loops/`) were Markdown programs that:
1. Read project state (e.g. `status.md`, subtask queue)
2. Did one unit of work (implement one subtask, fix one link)
3. Called `ScheduleWakeup` to re-fire themselves N seconds later
4. Terminated when a completion condition was met

They were self-scheduling, stateful across iterations, and ran in the same
growing conversation (sharing context cheaply via a `.claude/state/` cursor).

## Copilot emulation

Without `ScheduleWakeup`, loops become **iterative skills**: the user invokes
the skill, it does one pass, reports what remains, and instructs the user to
re-invoke if more work is needed. State is still persisted to
`.claude/state/<loop-name>.json` so successive runs are cheap.

| Claude loop | Copilot emulation | Invoke as |
|-------------|-------------------|-----------|
| `implement-subtasks.md` | `/implement-subtasks <task>` skill | Re-invoke until task is ✅ Complete |
| `update-docs.md` (scan) | `/update-docs` skill (no arg) | Re-invoke until doc_registry exits 0 |
| `update-docs.md` (path) | `/update-docs <path>` skill | Re-invoke until check_doc_links exits 0 |

## Usage pattern

```
/implement-subtasks 3.2        # one iteration: picks next pending subtask, implements it
→ "Subtask 01 complete. 3 remain. Re-run /implement-subtasks 3.2 to continue."

/implement-subtasks 3.2        # next iteration
→ "Subtask 02 complete. 2 remain. ..."
```

Compared to Claude loops:
- **Manual re-invocation** replaces `ScheduleWakeup`.
- **`.claude/state/` cursor** still provides the warm-path benefit (no re-parsing large docs).
- **Termination conditions** are the same; the skill just returns "done" instead of not rescheduling.
