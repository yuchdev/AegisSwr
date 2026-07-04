---
name: github-audit
description: Emulates the Claude github_audit.py PostToolUse hook. Logs every GitHub MCP tool invocation to the audit trail. In Claude this ran automatically after every mcp__github__* call. In Copilot, invoke /github-audit after making GitHub API calls to maintain the audit record.
allowed-tools: Bash, Read, Write
invocation: /github-audit
# Ported from Claude (.claude/hooks/github_audit.py) on 2026-07-03
# Original hook type: PostToolUse(mcp__github__*) - audit logging
# Copilot equivalent: Manual skill — invoke after GitHub MCP calls
---

# GitHub Audit Log

Log GitHub API actions to the audit trail. Maintains the durable record that
the original `github_audit.py` hook produced automatically.

> **Ported from Claude `github_audit.py` (PostToolUse mcp__github__* hook) on 2026-07-03.**
> In Claude Code this ran automatically after every GitHub MCP tool call and logged
> a compact, secret-free summary. In Copilot CLI, call `/github-audit` after
> making significant GitHub API calls (creating PRs, posting comments, merging, etc.).

## Steps

1. Identify the GitHub action just performed (PR creation, issue comment, merge, etc.).
2. Extract key non-sensitive arguments: `owner`, `repo`, `pull_number`,
   `issue_number`, `branch`, `ref`, `state`, `title`, `path`, `sha`.
3. Write a log line to `.claude/logs/github-actions.log`:
   ```
   <ISO-8601-UTC> <tool-name> :: <key>=<value> [<key>=<value> ...]
   ```
   Example:
   ```
   2026-07-03T15:30:00Z mcp__github__create_pull_request :: owner=yuchdev repo=AegisSwr title=feat: new backend branch=feat/bedrock
   ```

## Audit fields (always include when present)

| Field | Example |
|-------|---------|
| `owner` | `yuchdev` |
| `repo` | `AegisSwr` |
| `pull_number` | `42` |
| `issue_number` | `17` |
| `branch` | `feat/bedrock` |
| `state` | `open` / `merged` |
| `title` | First 80 chars of title |
| `sha` | Commit SHA |

## What NOT to log

- Authentication tokens
- Webhook secrets
- Full PR descriptions or issue bodies (reference by number only)
- Any content that may contain PII or incident payload fragments

## Log file

`.claude/logs/github-actions.log` (git-ignored, kept via `.gitkeep`). If the
log file does not exist, create it. Append; never truncate.
