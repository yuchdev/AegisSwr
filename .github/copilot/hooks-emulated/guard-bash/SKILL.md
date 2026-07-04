---
name: guard-bash
description: Reference for the destructive-command guard rules originally enforced by the Claude guard_bash.py PreToolUse hook. In Copilot, these are advisory rules — no automatic blocking. Invoke /guard-bash to review the blocked-pattern list before running risky commands.
allowed-tools: Read
invocation: /guard-bash
# Ported from Claude (.claude/hooks/guard_bash.py) on 2026-07-03
# Original hook type: PreToolUse(Bash) - EXIT 2 blocking
# Copilot equivalent: Advisory reference — no automatic blocking possible in Copilot CLI
---

# Bash Guard Reference

Lists the destructive and production-targeting command patterns that the original
Claude `guard_bash.py` hook blocked automatically. In Copilot CLI there is no
automatic blocking — these rules are **advisory**.

> **Ported from Claude `guard_bash.py` (PreToolUse Bash hook) on 2026-07-03.**
> In Claude Code this hook ran before every Bash tool call and exited with code 2
> (blocking the call) if a dangerous pattern matched. In Copilot CLI, automatic
> blocking is not available. Agents must self-enforce these rules; humans must
> review before running risky commands.

## Blocked patterns (originally auto-blocked)

| Pattern | Reason |
|---------|--------|
| `rm -rf`, `rm -f -r` | Recursive force delete |
| `DROP TABLE` | Destructive SQL |
| `DROP DATABASE` | Destructive SQL |
| `TRUNCATE TABLE` | Destructive SQL |
| `git push --force` / `git push -f` | Force-push (rewrites remote history) |
| `git reset --hard` | Hard reset (destroys uncommitted work) |
| `> /dev/sd*` | Raw disk overwrite |
| `mkfs` | Filesystem format |
| Any command containing `prod` or `production` | Production-targeting command |

## Production override

The original hook checked `AEGIS_PROD_CONFIRMED=1` environment variable before
allowing production-targeting commands. This convention is preserved:

```
# Only do this deliberately, in a known-safe context:
$env:AEGIS_PROD_CONFIRMED = "1"
<your production command>
```

Every block was logged to `.claude/logs/bash-guard.log`. Maintain this audit
trail manually by documenting production actions in `.github/copilot/hooks-emulated/`
audit notes.

## What to do before running a risky command

1. Read this reference (`/guard-bash`).
2. Confirm the command is not in the blocked list.
3. If it targets production, confirm `AEGIS_PROD_CONFIRMED=1` is appropriate.
4. If destructive, ask the user to confirm before executing.
5. Log the action with date and rationale if it involves production data.
