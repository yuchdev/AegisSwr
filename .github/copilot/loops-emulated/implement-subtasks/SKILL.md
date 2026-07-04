---
name: implement-subtasks
description: >
  Drives one task to completion, implementing exactly one subtask per invocation.
  Resolves the task from a milestone's plan.md, gates on status.md, then walks
  the task README's subtask queue - implementing, verifying, and running quality
  gates per subtask. Re-invoke until the task row in status.md shows ✅ Complete.
  Re-invoke as /implement-subtasks <task> to continue after each iteration.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent, TodoWrite
invocation: /implement-subtasks <task>
# Ported from Claude (.claude/loops/implement-subtasks.md) on 2026-07-03
# Original entity type: Loop (ScheduleWakeup-based, self-rescheduling)
# Copilot equivalent: Iterative skill — user re-invokes; same state cursor mechanics
---

# implement-subtasks — per-subtask implementation (one iteration)

> **Ported from Claude loop `implement-subtasks.md` on 2026-07-03.**
> In Claude Code this was a `ScheduleWakeup`-driven loop that re-fired itself
> automatically every ~270 s. In Copilot CLI, each invocation handles **one**
> subtask and returns a status line. Re-invoke `/implement-subtasks <task>` to
> advance to the next subtask.

This skill takes **one task** (e.g. "AWS Bedrock Backend", task `3.2`) and
implements the next pending subtask. State is persisted to
`.claude/state/implement-subtasks-{task-slug}.json` so re-invocations are cheap.

## Argument

`<task>` accepted forms (most specific wins):
- `0001/3.2` or `0001 3.2` — explicit milestone + task number.
- `3.2` — task number; resolve milestone by scanning `docs/roadmap/*/plan.md`.
- `"AWS Bedrock Backend"` — task name; matched case-insensitively.

If the argument matches zero or more than one task, **stop** and ask the user to disambiguate.

**Number → folder mapping**: `3.2 → 03.2`, `6.1 → 06.1`.

## Per-run state cursor

Cursor location: `.claude/state/implement-subtasks-{task-slug}.json`

```json
{
  "milestone_path": "docs/roadmap/0001-generic-implementation",
  "task_number": "3.2",
  "task_name": "AWS Bedrock Backend",
  "task_folder": "docs/roadmap/0001-generic-implementation/03.2-aws-bedrock-backend",
  "subtask_queue": [
    {"nn": "01", "slug": "configuration-model", "status": "complete"},
    {"nn": "02", "slug": "...", "status": "not_started"}
  ],
  "next_index": 1
}
```

## Iteration algorithm (one invocation = one subtask)

### Step 1 — Load or build cursor

- **Warm path (cursor exists)**: read it (~300 tokens), skip to Step 2.
- **Cold path (no cursor)**: spawn a Haiku-tier `explore` agent to resolve:
  `milestone_path`, `task_folder`, `subtask_queue`, `status_gate`. The agent
  returns only JSON — file bodies never enter the persistent context. Write cursor.

Branch on `status_gate`:
- `⬜ Not started` / `🔶 In progress` → continue.
- `✅ Complete` → spawn `subtask-verifier`, report verdict, **stop**.
- Ambiguous match → **stop**, ask user to disambiguate.

### Step 2 — Pick the next pending subtask

First `🔶 Partial`, else first `⬜ Not started`. Read only that subtask's spec.

### Step 3 — Implement via dev-fleet agents

| Spec role | Fleet agent | Action |
|-----------|-------------|--------|
| Architect | `app-architect` | Evaluate design |
| Python Expert | `python-expert` | Implement |
| Testing Expert | `testing-expert` → `python-expert` | QA then fix |
| Security Auditor | `security-auditor` → `python-expert` | Advisory then implement |
| Docs | `docs-writer` / `docs-updater` | Write or update |

Brief each agent with **paths**, not pasted file bodies. Require compact summaries back.

Security-sensitive subtasks: spawn `security-auditor` first; CRITICAL finding → stop.

### Step 4 — Ask when ambiguous

Use `ask_user` for genuine design forks. Continue for routine work.

### Step 5 — Verification gate

```bash
poetry run pytest <subtask-test-files> -q
poetry run mypy src/aegis_swr/<subtask-module>/ --strict
python scripts/replace_optional.py --check
```

On failure: delegate fix to `python-expert`, re-run. Max 1 retry; then stop.

### Step 6 — Spec-compliance gate

Run `/verify-subtask {subtask-path}`:
- **PASS** → note one line, continue.
- **PARTIAL** → log deviations, continue, feed to `/pr-review`.
- **FAIL** → delegate gaps to `python-expert` (max 1 retry). Stop if still FAIL.

Also run scoped quality gates:
| Condition | Gate |
|-----------|------|
| Always | `/test-gap src/aegis_swr/<subtask-module>/` |
| Manifest changed | `/dep-audit` |
| API/sandbox file changed | `/secret-scan src/aegis_swr/<changed-module>/` |
| Docs/public API changed | `/link-check docs/` |

### Step 7 — Record subtask; check task completion

1. Edit task README — set this subtask row to `✅ Complete`.
2. Refresh cursor (`next_index` + updated status).
3. Check if all major subtasks are `✅ Complete`.

**If task complete**: run full suite once:
```bash
poetry run pytest tests/unit/ -q --cov=aegis_swr
```
Then run `/pr-review` (must reach LGTM). Update `status.md` task row to `✅ Complete`.
Run `/link-check docs/roadmap/`. Delete the cursor. **Stop — task is done.**

**If task not complete**: print:
```
Subtask {NN} complete. {N} subtasks remain. Re-invoke /implement-subtasks <task> to continue.
```
**Stop** (no ScheduleWakeup — user re-invokes manually).

## Termination conditions

| Condition | Action |
|-----------|--------|
| Task reaches `✅ Complete` | Update status.md, print summary, stop |
| Task already `✅ Complete` | Run subtask-verifier, report, stop |
| Ambiguous argument | Stop, ask user |
| Verification fails after retry | Surface blocker, stop |
| `subtask-verifier` FAIL after retry | Surface gaps, stop |
| `security-auditor` CRITICAL | Stop, require human sign-off |
| `/pr-review` REQUEST_CHANGES after 2 rounds | Stop, surface diff |
