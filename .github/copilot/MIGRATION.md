# Aegis SWR — Claude → Copilot Migration Report

**Date**: 2026-07-04  
**Source**: `.claude/`  
**Destinations**: `.github/copilot/` and `.github/hooks/`  
**Status**: Corrected

## Executive summary

The original migration report was wrong about Copilot hooks.

GitHub Copilot now supports repository-native hooks in `.github/hooks/*.json`, with
blocking `preToolUse` decisions, `sessionStart` context injection, and `Stop`
(`agentStop`) turn-gating. Aegis SWR now uses those native hooks directly:

- `.github/hooks/aegis-hooks.json` defines the hook metadata.
- `.github/hooks/*.py` contains the Copilot hook commands.
- `.github/copilot/hooks-emulated/` is removed because it was no longer the right model.

The `.claude/` directory still remains for Claude Code compatibility.

## Current structure

| Path | Purpose |
|---|---|
| `.github/copilot/agents/` | Copilot custom agents |
| `.github/copilot/skills/` | Copilot skills plus copied `references/` and `examples/` assets |
| `.github/copilot/loops-emulated/` | The only remaining emulation layer; Copilot still has no `ScheduleWakeup` equivalent |
| `.github/hooks/aegis-hooks.json` | Repository-native Copilot hook configuration |
| `.github/hooks/*.py` | Cross-platform Python hook commands for Copilot |
| `.claude/hooks/` | Legacy Claude hook implementations kept for Claude Code |
| `.claude/logs/` | Shared audit logs written by both Claude and Copilot hooks |

## Hook migration map

The Copilot hook file uses **PascalCase** event names (`SessionStart`, `PreToolUse`,
`PostToolUse`, `Stop`, etc.) so the payloads stay Claude-compatible (`tool_input`,
`tool_name`, `stop_hook_active`) while running as native Copilot hooks.

| Claude hook | Claude trigger | Native Copilot trigger | Copilot command |
|---|---|---|---|
| `.claude/hooks/session_start.py` | `SessionStart` | `SessionStart` | `.github/hooks/session_start.py` |
| `.claude/hooks/guard_bash.py` | `PreToolUse(Bash)` | `PreToolUse` matcher `Bash` | `.github/hooks/guard_bash.py` |
| `.claude/hooks/secret_scan.py` | `PreToolUse(Write\|Edit\|MultiEdit)` | `PreToolUse` matcher `Write\|Edit` | `.github/hooks/secret_scan.py` |
| `.claude/hooks/post_edit_format.py` | `PostToolUse(Write\|Edit\|MultiEdit)` | `PostToolUse` matcher `Write\|Edit` | `.github/hooks/post_edit_format.py` |
| `.claude/hooks/dep_audit.py` | `PostToolUse(manifest edit)` | `PostToolUse` matcher `Write\|Edit` | `.github/hooks/dep_audit.py` |
| `.claude/hooks/doc_link_check.py` | `PostToolUse(Markdown edit)` | `PostToolUse` matcher `Write\|Edit` | `.github/hooks/doc_link_check.py` |
| `.claude/hooks/doc_link_check.py` | `Stop` | `Stop` | `.github/hooks/doc_link_check.py` |
| `.claude/hooks/run_tests.py` | `Stop` | `Stop` | `.github/hooks/run_tests.py` |

## Copilot-native improvements applied

1. **Blocking write guards are back.**  
   `guard_bash.py` and `secret_scan.py` now emit Copilot JSON permission decisions,
   so destructive bash commands and secret-bearing writes are denied natively.

2. **Session context is injected automatically again.**  
   `SessionStart` now adds branch, recent commits, and open P0/P1 issues through
   Copilot `additionalContext`, instead of relying on a manual skill substitute.

3. **The unit-test gate is restored.**  
   `Stop` now blocks turn completion with a structured Copilot decision when the
   unit suite is red, preserving the old Claude behavior.

4. **GitHub audit logging matches real Copilot usage.**  
   The old migration assumed `mcp__github__*` tools. In this repo, GitHub work is
   done through `gh`, so the native Copilot hook now audits `bash` commands that
   invoke `gh`, including failed commands via `PostToolUseFailure`.

5. **New lifecycle audit hooks are enabled.**  
   Copilot-specific `UserPromptSubmit`, `SessionEnd`, and `ErrorOccurred` hooks now
   write prompt, session, and error audit records to `.claude/logs/`.

6. **Broken Copilot content structure is repaired.**  
   The migration originally moved only `SKILL.md` files. Supporting `references/`
   and `examples/` assets have now been copied under `.github/copilot/skills/`, and
   internal docs now point at `.github/copilot/...` instead of the nonexistent
   `.copilot/...` tree.

7. **Future syncs are codified.**  
   Use `/sync-migration` plus `python scripts/sync_copilot_migration.py` to
   compare the migration boundary date with `.claude/` git history and resync only
   the changed Claude files.

## Remaining gap

Loops are still emulated.

Copilot hooks do **not** replace Claude's `ScheduleWakeup`, so
`.github/copilot/loops-emulated/` remains valid until Copilot gains a native
rescheduling primitive.
