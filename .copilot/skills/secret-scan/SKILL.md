---
name: secret-scan
description: Scans files for hardcoded secrets, API keys, and passwords using pattern matching. Runs automatically on every Write/Edit via the secret_scan.py PreToolUse hook (which blocks on a hit); invoke manually as /secret-scan [paths] to sweep existing files on demand.
allowed-tools: Read, Grep, Glob, Bash
invocation: /secret-scan [paths]
# Ported from Claude (.claude/skills/secret-scan/SKILL.md) on 2026-07-03
# Note: In Claude this also ran automatically as a PreToolUse hook before every Write/Edit,
#       blocking the write if secrets were detected. In Copilot, the script is available
#       for manual sweeps. Copilot CLI has no automatic pre-tool blocking capability.
---

# Secret Scan

Detect committed credentials. This skill uses the same Python detection engine as
the original Claude `secret_scan.py` hook. The script is at
`.claude/hooks/secret_scan.py` and can also be run directly.

> **Copilot note**: In Claude Code, `secret_scan.py` ran as a PreToolUse hook
> before every Write/Edit/MultiEdit, automatically **blocking** the operation if
> a credential was detected. Copilot CLI has no equivalent automatic hook trigger.
> Instead, run `/secret-scan` manually:
> - Before every commit (`git diff --cached`)
> - After adding new config files or `.env`-like files
> - As part of the `/dep-audit` flow

## How it works

- Runs `python .claude/hooks/secret_scan.py <files>` (shared scanner).
- Findings logged to `.claude/logs/secret-scan.log`.
- The Aegis codebase redacts secrets at runtime via `SensitiveFilter` - this scan
  stops them entering the repo at all.

## Steps

1. Resolve targets from `$ARGUMENTS`. If empty, sweep changed files:
   `git diff --name-only` + `git diff --cached --name-only` + untracked.
2. Run the shared scanner:
   `python .claude/hooks/secret_scan.py <file> [<file> ...]`
3. For each hit, report `file:line: <type>: <excerpt>`. Never print the full
   secret value.

## Detected shapes

AWS keys, Anthropic/OpenAI/Google API keys, GitHub & Slack tokens, private-key
blocks, Postgres URLs with embedded passwords, and generic `password=`/`token=`
assignments. Obvious placeholders (`example`, `${VAR}`, `your-…`, `changeme`)
are ignored.

The full pattern table is in `.copilot/skills/secret-scan/references/pattern-catalog.md`.

## Output

```
## Secret Scan - <N files>
- <file:line>: <type>
**Result: CLEAN | N FINDING(S)**
```

On any finding: instruct the user to remove the secret, rotate it if it ever
reached a remote, and replace it with an env var / `${VAR}` reference (see
`.mcp.json`) or a secrets manager. Recommend `git filter-repo`/history rewrite
if it was already committed.

## Completion checklist

- [ ] Targets resolved from `$ARGUMENTS`, or changed+untracked files when empty
- [ ] Shared scanner (`.claude/hooks/secret_scan.py`) run
- [ ] Each finding reported as `file:line: <type>: <short excerpt>` - full secret value never printed
- [ ] Placeholder/allowlisted lines correctly treated as clean
- [ ] For real hits: remove + rotate + replace with `${VAR}`/secrets-manager advised
- [ ] Result line emitted: `CLEAN` or `N FINDING(S)`
