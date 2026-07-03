---
name: session-context
description: Emulates the Claude SessionStart hook (session_start.py). Prints current branch, last 5 commits, and open P0/P1 GitHub issues to seed the session context. Invoke at the start of any work session.
allowed-tools: Bash, Read
invocation: /session-context
# Ported from Claude (.claude/hooks/session_start.py) on 2026-07-03
# Original hook type: SessionStart (auto-injected into conversation context)
# Copilot equivalent: Manual skill invocation — call /session-context at session start
---

# Session Context

Seed the session with live repository context: current branch, recent commits,
and open P0/P1 issues.

> **Ported from Claude `session_start.py` (SessionStart hook) on 2026-07-03.**
> In Claude Code this ran automatically when a session started and injected
> context into the conversation. In Copilot CLI, invoke `/session-context`
> manually at the start of a work session.

## Steps

1. Get the current branch:
   ```bash
   git rev-parse --abbrev-ref HEAD
   ```

2. Get the last 5 commits:
   ```bash
   git log -5 --pretty=format:"  %h %s"
   ```

3. Get open P0/P1 issues (if `gh` is authenticated):
   ```bash
   gh issue list --state open --label "P0,P1" --limit 20 --json number,title,labels \
     --template "{{range .}}  #{{.number}} {{.title}}\n{{end}}"
   ```

4. Print a formatted context block:

```
# Aegis SWR - session context
Branch: <branch>

Recent commits:
  <hash> <message>
  ...

Open P0/P1 issues:
  #<n> <title>
  ...

Reminder: incident payloads are sensitive. Never log secrets or raw PII.
Delegate per .copilot/agents/ (architect/coder/test/reviewers/incident-analyst/security-auditor).
```

## Output

Print the context block to the conversation. If `gh` is not authenticated,
note "Open P0/P1 issues: none found (or gh not authenticated)."
