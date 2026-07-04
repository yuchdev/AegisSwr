# .github/copilot/hooks-emulated — Hook Emulation for Copilot CLI

**Ported from Claude on 2026-07-03.**

Claude Code has a native hook system (`settings.json` → `hooks`) that fires
Python scripts at lifecycle events. Copilot CLI has no equivalent automatic
hook mechanism. This directory emulates each hook as an **invocable skill** or
**documented guideline** that must be triggered manually.

## Original Claude hooks and their Copilot equivalents

| Hook | Trigger | Copilot equivalent | Invoke as |
|------|---------|--------------------|-----------|
| `session_start.py` | SessionStart | `/session-context` skill | `/session-context` at start of work |
| `guard_bash.py` | PreToolUse(Bash) - blocking | `/guard-bash` reference | Check before destructive commands |
| `secret_scan.py` | PreToolUse(Write\|Edit\|MultiEdit) - blocking | `/secret-scan` skill (manual) | `/secret-scan` before commit |
| `post_edit_format.py` | PostToolUse(Write\|Edit\|MultiEdit) | `/post-edit-format` skill | Run after editing Python files |
| `dep_audit.py` | PostToolUse(manifest edit) | `/dep-audit` skill (manual) | `/dep-audit` after manifest changes |
| `doc_link_check.py` | PostToolUse(markdown edit) + Stop | `/link-check` skill (manual) | `/link-check` after editing Markdown |
| `github_audit.py` | PostToolUse(mcp__github__*) | `/github-audit` skill | Run after GitHub MCP calls |
| `run_tests.py` | Stop - blocking | `/run-tests` skill | `/run-tests` before ending a session |

## Critical gap: automatic blocking

The most significant capability gap between Claude hooks and Copilot skills is
**automatic blocking**. Claude hooks could exit with code `2` to prevent a tool
call from completing. In Copilot, this is not possible — all guards are advisory.

**Mitigation**: Copilot CLI agents are instructed to follow these rules in their
system prompts (`.github/copilot/agents/`). The human reviewer and `/pr-review` skill
serve as the merge gate.

## Periodic reminders

Instead of automatic triggers, adopt these habits:
- **Before each commit**: run `/secret-scan` + `/link-check` (if markdown changed)
- **After manifest changes**: run `/dep-audit`
- **When touching lifecycle code**: run `/incident-triage`
- **Before ending a work session**: run `/run-tests`
- **After GitHub MCP calls**: run `/github-audit`

## Hook scripts preserved

The original hook Python scripts are still present in `.claude/hooks/` and remain
functional for use with Claude Code. The `.claude/` directory is NOT removed — it
coexists with `.github/copilot/`. See the root `MIGRATION.md` for the full picture.
