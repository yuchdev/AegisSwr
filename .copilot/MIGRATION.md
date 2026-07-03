# Aegis SWR — Claude → Copilot Migration Report

**Date**: 2026-07-03  
**Source**: `.claude/` (Claude Code agent configuration)  
**Destination**: `.copilot/` (GitHub Copilot CLI configuration)  
**Status**: Complete

---

## Executive Summary

All 12 Claude agents, 14 Claude skills, 8 Claude hooks, and 2 Claude loops have been
ported to their closest Copilot CLI equivalents. Agents and skills have **direct
equivalents** and were ported 1:1. Hooks and loops have **no native equivalent** in
Copilot CLI and were emulated as invocable skills with explicit documentation of the
capability gap.

The `.claude/` directory is **not removed** — it coexists with `.copilot/` so the project
works with either Claude Code or Copilot CLI.

---

## Entity Map

### Agents (12 — Direct port)

Copilot agents use the same Markdown frontmatter format as Claude agents. Model names
were updated from hyphenated (`claude-opus-4-8`) to dot-notation (`claude-opus-4.8`).

| Claude agent | Copilot agent | Model | Notes |
|---|---|---|---|
| `.claude/agents/agent-orchestrator.md` | `.copilot/agents/agent-orchestrator.md` | claude-opus-4.8 | Direct port |
| `.claude/agents/app-architect.md` | `.copilot/agents/app-architect.md` | claude-opus-4.8 | Direct port |
| `.claude/agents/background-reviewer.md` | `.copilot/agents/background-reviewer.md` | claude-sonnet-4.6 | Direct port |
| `.claude/agents/docs-updater.md` | `.copilot/agents/docs-updater.md` | claude-sonnet-4.6 | Direct port |
| `.claude/agents/docs-writer.md` | `.copilot/agents/docs-writer.md` | claude-sonnet-4.6 | Direct port |
| `.claude/agents/feature-reviewer.md` | `.copilot/agents/feature-reviewer.md` | claude-sonnet-4.6 | Direct port |
| `.claude/agents/incident-analyst.md` | `.copilot/agents/incident-analyst.md` | claude-opus-4.8 | Direct port |
| `.claude/agents/python-expert.md` | `.copilot/agents/python-expert.md` | claude-sonnet-4.6 | Direct port; model downgraded from opus to sonnet (sufficient for implementation) |
| `.claude/agents/security-auditor.md` | `.copilot/agents/security-auditor.md` | claude-opus-4.8 | Direct port |
| `.claude/agents/subtask-verifier.md` | `.copilot/agents/subtask-verifier.md` | claude-sonnet-4.6 | Direct port |
| `.claude/agents/test-documenter.md` | `.copilot/agents/test-documenter.md` | claude-sonnet-4.6 | Direct port |
| `.claude/agents/testing-expert.md` | `.copilot/agents/testing-expert.md` | claude-sonnet-4.6 | Direct port |

### Skills (14 — Direct port)

Skills use the same `SKILL.md` frontmatter + Markdown body format. Invocation syntax
(`/skill-name`) is identical. References to `.claude/` paths were updated to `.copilot/`.

| Claude skill | Copilot skill | Notes |
|---|---|---|
| `.claude/skills/adr-write/SKILL.md` | `.copilot/skills/adr-write/SKILL.md` | Direct port |
| `.claude/skills/dep-audit/SKILL.md` | `.copilot/skills/dep-audit/SKILL.md` | Auto-trigger note added (see Hooks) |
| `.claude/skills/doc-registry/SKILL.md` | `.copilot/skills/doc-registry/SKILL.md` | Direct port |
| `.claude/skills/doc-xref/SKILL.md` | `.copilot/skills/doc-xref/SKILL.md` | Direct port |
| `.claude/skills/document-tests/SKILL.md` | `.copilot/skills/document-tests/SKILL.md` | Direct port |
| `.claude/skills/incident-triage/SKILL.md` | `.copilot/skills/incident-triage/SKILL.md` | Auto-trigger note added (see Hooks) |
| `.claude/skills/link-check/SKILL.md` | `.copilot/skills/link-check/SKILL.md` | Auto-trigger note added (see Hooks) |
| `.claude/skills/playbook-validate/SKILL.md` | `.copilot/skills/playbook-validate/SKILL.md` | Direct port |
| `.claude/skills/post-mortem/SKILL.md` | `.copilot/skills/post-mortem/SKILL.md` | Direct port |
| `.claude/skills/pr-review/SKILL.md` | `.copilot/skills/pr-review/SKILL.md` | Direct port |
| `.claude/skills/runbook-write/SKILL.md` | `.copilot/skills/runbook-write/SKILL.md` | Direct port |
| `.claude/skills/secret-scan/SKILL.md` | `.copilot/skills/secret-scan/SKILL.md` | Auto-block note added (see Hooks) |
| `.claude/skills/test-gap/SKILL.md` | `.copilot/skills/test-gap/SKILL.md` | Direct port |
| `.claude/skills/verify-subtask/SKILL.md` | `.copilot/skills/verify-subtask/SKILL.md` | Direct port |

### Hooks (8 — Emulated as skills or documented guidelines)

Claude Code hooks run Python scripts automatically at lifecycle events.
**Copilot CLI has no native hook system.** Each hook was emulated as the closest
possible Copilot entity.

| Claude hook | Trigger | Blocking? | Copilot emulation | Location |
|---|---|---|---|---|
| `session_start.py` | SessionStart | No | `/session-context` skill (manual) | `.copilot/hooks-emulated/session-context/SKILL.md` |
| `guard_bash.py` | PreToolUse(Bash) | **YES** | `/guard-bash` reference + agent instructions | `.copilot/hooks-emulated/guard-bash/SKILL.md` |
| `secret_scan.py` | PreToolUse(Write\|Edit\|MultiEdit) | **YES** | `/secret-scan` skill (manual) | `.copilot/skills/secret-scan/SKILL.md` |
| `post_edit_format.py` | PostToolUse(Write\|Edit\|MultiEdit) | No | `/post-edit-format` skill (manual) | `.copilot/hooks-emulated/post-edit-format/SKILL.md` |
| `dep_audit.py` | PostToolUse(manifest edit) | No | `/dep-audit` skill already exists (invoke manually on manifest change) | `.copilot/skills/dep-audit/SKILL.md` |
| `doc_link_check.py` | PostToolUse(Markdown edit) + Stop | No | `/link-check` skill already exists (invoke manually after Markdown edits) | `.copilot/skills/link-check/SKILL.md` |
| `github_audit.py` | PostToolUse(mcp__github__\*) | No | `/github-audit` skill (manual) | `.copilot/hooks-emulated/github-audit/SKILL.md` |
| `run_tests.py` | Stop | **YES** | `/run-tests` skill (manual; honor its result) | `.copilot/hooks-emulated/run-tests/SKILL.md` |

#### Critical capability gap: automatic blocking

Three Claude hooks blocked operations by exiting with code 2:

| Hook | What it blocked |
|---|---|
| `guard_bash.py` | Destructive shell commands (rm -rf, DROP TABLE, git push --force, production targets) |
| `secret_scan.py` | File writes containing detected credentials |
| `run_tests.py` | Session end on a red test suite |

**Copilot CLI cannot block tool calls.** Mitigations:
1. Agent system prompts (`.copilot/agents/`) include explicit rules matching the hook logic.
2. `/guard-bash` documents the blocked patterns for human review.
3. `/secret-scan` is recommended before every commit (add to PR checklist).
4. `/run-tests` should be run before ending every session (honor: do not commit on red).
5. Consider adding a `pre-commit` framework hook for `ruff format` + secret scanning to
   recover some of the automatic behavior at the git layer.

#### hook script reuse

The Python scripts in `.claude/hooks/` are reused directly by the Copilot skills:
- `/secret-scan` invokes `python .claude/hooks/secret_scan.py`
- The log files are written to `.claude/logs/` (same as before)

This avoids duplicating the logic while the project runs both Claude Code and Copilot CLI.

### Loops (2 — Emulated as iterative skills)

Claude loops used `ScheduleWakeup` to self-reschedule in the same growing conversation.
**Copilot CLI has no `ScheduleWakeup` equivalent.**

| Claude loop | Copilot emulation | Re-invocation |
|---|---|---|
| `.claude/loops/implement-subtasks.md` | `.copilot/loops-emulated/implement-subtasks/SKILL.md` | User re-invokes `/implement-subtasks <task>` after each subtask |
| `.claude/loops/update-docs.md` (scan) | `.copilot/loops-emulated/update-docs/SKILL.md` | User re-invokes `/update-docs` until `doc_registry` exits 0 |
| `.claude/loops/update-docs.md` (path) | Same skill with path arg | User re-invokes `/update-docs <path>` until `check_doc_links` exits 0 |

The `.claude/state/` cursor mechanism is preserved — successive invocations are cheap
because resolved data (milestone path, task folder, subtask queue) is read from the
cursor rather than re-parsed from large source files.

**Termination conditions** are identical to the Claude loops; they're simply enforced
by the user/agent returning "done" instead of by `ScheduleWakeup` not being called.

### Settings / Permissions

The Claude `settings.json` permissions (`allow`/`deny` lists for Bash) have no direct
Copilot equivalent. These rules are now:

1. Documented in `/guard-bash` as the reference for what commands are blocked.
2. Encoded in agent system prompts (especially `python-expert` and `agent-orchestrator`).
3. The `deny` entries (`.env` files, `.dmp` files, `.db` files) are advisory — agents
   are instructed never to read those paths.

---

## Capability Gap Summary

| Claude feature | Copilot equivalent | Gap severity |
|---|---|---|
| Sub-agent spawning (`Task` tool) | ✅ Available (`task` tool with same agents) | None |
| `/skill-name` invocation | ✅ Available | None |
| Agent frontmatter (name, model, tools) | ✅ Same format | None |
| Skill SKILL.md format | ✅ Same format | None |
| PreToolUse blocking hooks | ❌ Not available | **HIGH** — manual discipline required |
| PostToolUse auto-callbacks | ❌ Not available | Medium — manual skill invocation |
| SessionStart auto-injection | ❌ Not available | Low — `/session-context` as manual substitute |
| Stop hook (session gate) | ❌ Not available | Medium — `/run-tests` as manual substitute |
| `ScheduleWakeup` (loop rescheduling) | ❌ Not available | Medium — user re-invokes iterative skill |
| `settings.json` permissions | ❌ Not available | Medium — documented as advisory rules |

---

## Recommended Mitigations

1. **Pre-commit hook**: install `pre-commit` with hooks for `ruff format`, `ruff check`,
   and `python .claude/hooks/secret_scan.py` to recover automatic formatting and
   secret-scanning at the git layer.

2. **PR checklist**: add to PR template:
   ```
   - [ ] /secret-scan run (no findings)
   - [ ] /run-tests passed
   - [ ] /link-check passed (if Markdown changed)
   - [ ] /dep-audit run (if manifests changed)
   ```

3. **Session discipline**: follow the habit list in
   `.copilot/hooks-emulated/README.md` to replicate the hook cadence manually.

4. **CI enforcement**: `.github/workflows/ci.yml` already runs `ruff`, `mypy`, and
   `pytest` — these serve as the backstop for everything the hooks did automatically.

---

## File Inventory

```
.copilot/
├── MIGRATION.md                              ← this file
├── agents/                                   ← 12 agent files
│   ├── agent-orchestrator.md
│   ├── app-architect.md
│   ├── background-reviewer.md
│   ├── docs-updater.md
│   ├── docs-writer.md
│   ├── feature-reviewer.md
│   ├── incident-analyst.md
│   ├── python-expert.md
│   ├── security-auditor.md
│   ├── subtask-verifier.md
│   ├── test-documenter.md
│   └── testing-expert.md
├── skills/                                   ← 14 skill directories
│   ├── adr-write/SKILL.md
│   ├── dep-audit/SKILL.md
│   ├── doc-registry/SKILL.md
│   ├── doc-xref/SKILL.md
│   ├── document-tests/SKILL.md
│   ├── incident-triage/SKILL.md
│   ├── link-check/SKILL.md
│   ├── playbook-validate/SKILL.md
│   ├── post-mortem/SKILL.md
│   ├── pr-review/SKILL.md
│   ├── runbook-write/SKILL.md
│   ├── secret-scan/SKILL.md
│   ├── test-gap/SKILL.md
│   └── verify-subtask/SKILL.md
├── hooks-emulated/                           ← 5 hook emulations + README
│   ├── README.md
│   ├── session-context/SKILL.md
│   ├── guard-bash/SKILL.md
│   ├── post-edit-format/SKILL.md
│   ├── run-tests/SKILL.md
│   └── github-audit/SKILL.md
└── loops-emulated/                           ← 2 loop emulations + README
    ├── README.md
    ├── implement-subtasks/SKILL.md
    └── update-docs/SKILL.md
```

---

*Migration performed by GitHub Copilot CLI (claude-sonnet-4.6) on 2026-07-03.*
