# Aegis SWR - Hooks Reference

Hooks are Python scripts that run automatically at specific points in a Claude
Code session - before a tool runs, after it finishes, when the session starts,
or when Claude tries to stop. They are the **invisible enforcement layer** of
the agentic fleet: no agent needs to remember to run them, they just happen.

All hook scripts live under `.claude/hooks/` and are wired into Claude Code via
`.claude/settings.json`. They share a small common library (`_common.py`) and
write an audit log under `.claude/logs/`.

---

## How hooks work (the basics)

When Claude Code is about to call a tool (e.g., run a shell command or write a
file), it first fires the matching **PreToolUse** hooks. Each hook receives the
pending tool call as JSON on stdin and exits with one of:

| Exit code | Meaning |
|---|---|
| `0` | Allow - tool call proceeds |
| `2` | **Block** - tool call is cancelled; Claude sees the stderr message and must find another approach |
| Other | Non-fatal warning; surfaced to the user but does not block |

**PostToolUse** hooks run after a tool succeeds, for side effects (formatting,
logging). **SessionStart** hooks run once at the beginning of a session to seed
context. **Stop** hooks run when Claude tries to end a session.

Hooks are **deterministic** - unlike agents or skills, they are not LLM calls.
They run at machine speed and always produce the same result for the same input.

---

## Hook scripts

### `_common.py` - shared library

Not a hook itself; imported by every hook. Provides:
- `read_event()` - parse the hook JSON from stdin
- `tool_input(event)` - extract the `tool_input` dict
- `edited_path(event)` - resolve the target file path from Write/Edit events
- `block(message)` - print to stderr and exit 2
- `allow()` - exit 0
- `append_log(filename, line)` - write a timestamped line to `.claude/logs/`
- `now_iso()` - current UTC timestamp in ISO-8601

---

### `guard_bash.py` - destructive command guard

**Hook event:** `PreToolUse` on `Bash`
**Log:** `.claude/logs/bash-guard.log`

Runs before every shell command. Blocks two categories:

**1. Destructive operations** (always blocked, no override):
- `rm -rf` / `rm -fr` - recursive force delete
- `DROP TABLE`, `DROP DATABASE`, `TRUNCATE TABLE` - database destruction
- `git push --force` / `git push -f` - force-push (can overwrite upstream)
- `git reset --hard` - discards uncommitted work
- `> /dev/sdX` - raw disk overwrite
- `mkfs` - filesystem format

**2. Production-targeting commands** (blocked unless `AEGIS_PROD_CONFIRMED=1`):
Any command containing the word `prod` or `production` (case-insensitive) is
blocked unless the environment variable `AEGIS_PROD_CONFIRMED=1` is set.

**When you hit it legitimately:**
If you genuinely need to run a destructive command, the hook will tell you so
and ask you to run it manually. This is intentional - the guard is there to
prevent an automated slip, not to stop you from doing your job. For production
actions, export `AEGIS_PROD_CONFIRMED=1` in your terminal before starting the
Claude Code session.

**Example block message:**
```
Blocked by aegis bash-guard: recursive force delete (rm -rf).
Command: rm -rf build/
This operation is destructive and is never allowed automatically.
If you are certain, ask the user to run it manually.
```

---

### `secret_scan.py` - secret detector (write guard)

**Hook event:** `PreToolUse` on `Write`, `Edit`, `MultiEdit`
**Log:** `.claude/logs/secret-scan.log`

Scans the **content about to be written** for hardcoded credentials before the
file is saved. Blocks the write (exit 2) if a match is found.

**Credential patterns detected:**
- `AKIA…` - AWS access key IDs
- `sk-ant-…` - Anthropic API keys
- `sk-…` - OpenAI API keys
- `AIza…` - Google API keys
- `ghp_`, `ghs_`, `ghu_`, `ghr_`, `gho_` - GitHub tokens
- `xox…` - Slack tokens
- `-----BEGIN … PRIVATE KEY-----` - PEM private key blocks
- `password = "…"` / `token = "…"` / `api_key = "…"` - generic assignments
  with values 8+ chars that are not placeholder patterns
- DB connection strings with embedded credentials in the URL (`scheme://user:secret@host`)

**Allowlisted patterns** (not flagged): any line containing `example`,
`placeholder`, `your-`, `your_`, `changeme`, `dummy`, `xxxx`, `${`, `<your`,
`redacted`, `fake`, or `test`.

**Skipped file types:** `.lock`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.pdf`,
`.dmp`, `.db` - binary/lock files that would produce false positives.

**When you hit it:**
1. Remove the credential from the proposed content
2. Replace with `${ENV_VAR_NAME}` (the canonical pattern used in `.mcp.json`)
3. If Claude keeps trying to write it, check whether the credential crept in
   from another file or context window; use `/secret-scan` to sweep the tree

The same script runs as a CLI for manual sweeps:
```
python .claude/hooks/secret_scan.py src/aegis_swr/config/
```

---

### `post_edit_format.py` - auto-formatter

**Hook event:** `PostToolUse` on `Write`, `Edit`, `MultiEdit`
**Log:** `.claude/logs/edits.log`

Runs after every file write:
1. **For `.py` files:** runs `ruff format <file>` then `ruff check --fix
   --quiet <file>` to auto-format and fix lint issues.
2. **For all files:** appends the relative path to `.claude/logs/edits.log`
   with a timestamp (the edit audit trail).

This is why you should **not fight the formatter** - if your code looks
different after a write, it is because ruff re-formatted it. The result is
always correct; the before-state was not ruff-canonical.

**Formatting is advisory-non-blocking:** if `ruff` is not on `PATH`, the hook
logs a note and exits 0 rather than blocking. Install it with the project dev
group: `uv sync`.

---

### `dep_audit.py` - dependency audit trigger

**Hook event:** `PostToolUse` on `Write`, `Edit`, `MultiEdit`
**Log:** `.claude/logs/dep-audit.log`

Activates only when the edited file is `pyproject.toml`, `uv.lock`,
`requirements.txt`, or `requirements-dev.txt`. Runs `pip-audit
--progress-spinner off` as a best-effort advisory scan and records the result.

**This hook is advisory, not blocking.** It is a lightweight early-warning
signal. The authoritative dependency audit is the `/dep-audit` skill, which
delegates a full CVE+licence report to `background-reviewer`.

**What to do when it logs a finding:** run `/dep-audit` to get the full report
with recommended version bumps, then have `python-expert` apply them.

---

### `doc_link_check.py` - documentation reference integrity

**Hook event:** `PostToolUse` on `Write`, `Edit`, `MultiEdit`, **and** `Stop`
**Log:** `.claude/logs/doc-link-check.log`

Runs `scripts/check_doc_links.py` so a docs edit never silently leaves a dangling
relative link or a missing heading anchor.

- **PostToolUse:** when the edited file is Markdown, checks that file's *outbound*
  links/anchors immediately.
- **Stop:** if any Markdown changed in the working tree this session, runs the full
  repo doc-link scan - which also catches *inbound* breakage (e.g. a renamed heading
  that other docs still link to).

**Advisory, non-blocking** (always exits 0): it surfaces dangling references to the
agent/user as a reminder but never wedges a session. The same script powers the
`/link-check` skill; `/doc-xref` handles the inbound-rename half (finding who points
at a moved doc/heading/symbol). Make it a hard gate by switching its reporting to
`block` (exit 2).

---

### `github_audit.py` - GitHub MCP audit logger

**Hook event:** `PostToolUse` on `mcp__github__*` (any GitHub MCP tool call)
**Log:** `.claude/logs/github-actions.log`

Logs every GitHub MCP operation with a timestamp and a compact, non-sensitive
summary of the call arguments (owner, repo, PR/issue number, branch, title,
query, state). The full payload is never logged - only fields that identify the
action without leaking content.

**Example log line:**
```
2026-06-14T14:04:01Z mcp__github__create_pull_request :: owner=AcmeCorp repo=aegis-swr title=feat: add OTLP adapter
```

This hook never blocks. Its sole purpose is the **audit trail** - a durable
record of every GitHub action taken by any agent in any session.

---

### `session_start.py` - context seeding

**Hook event:** `SessionStart`

Runs once at the beginning of every session. Prints to stdout (which Claude
Code injects into the session context):

1. **Current branch** - from `git rev-parse --abbrev-ref HEAD`
2. **Last 5 commits** - from `git log -5 --pretty=format:…`
3. **Open P0/P1 issues** - from `gh issue list --label P0,P1` (silent if `gh`
   is not authenticated)
4. **A reminder** about incident-payload sensitivity and the agent delegation map

This means every session starts knowing what branch it is on, what was recently
committed, and what fires are burning - without the engineer having to paste
this into the chat.

**If `gh` is not authenticated:** the issues section reads "none found (or gh
not authenticated)". Authenticate with `gh auth login` to get the P0/P1 feed.

---

### `run_tests.py` - session exit gate

**Hook event:** `Stop`
**Log:** `.claude/logs/tests.log`

Runs `uv run pytest tests/unit/ -q` when Claude tries to end the session.
If the suite fails, **exit 2** prevents the session from closing and Claude is
told to fix the regression.

**Two escape hatches:**

1. **`stop_hook_active`** - if Claude Code already blocked a session for a
   failing test and the Stop hook fires again in the same context, this flag is
   set. The hook detects it and exits 0 to avoid an infinite loop. Claude Code
   handles this automatically.

2. **`AEGIS_SKIP_TESTS=1`** - export this environment variable before starting
   a session to skip the Stop-hook gate entirely. Use only for intentional WIP
   sessions where you know tests are red and you're not ready to fix them:
   ```powershell
   $env:AEGIS_SKIP_TESTS = "1"
   claude
   ```

**Why it matters:** without this gate, an agent could land a change, commit it,
and end the session - leaving broken tests in the branch that CI catches only
minutes later. The Stop hook moves the detection into the session itself.

---

## Log files (`.claude/logs/`)

All logs are git-ignored (see `.gitignore`) but the directory is kept via
`.gitkeep`. They persist across sessions within the same working tree.

| File | Written by | Content |
|---|---|---|
| `edits.log` | `post_edit_format.py` | Every file written/edited with timestamp |
| `tests.log` | `run_tests.py` | PASS / FAIL / SKIPPED per session stop |
| `bash-guard.log` | `guard_bash.py` | Every blocked destructive or prod command |
| `secret-scan.log` | `secret_scan.py` | Every blocked write: finding type + location |
| `dep-audit.log` | `dep_audit.py` | Advisory audit results on manifest changes |
| `github-actions.log` | `github_audit.py` | Every GitHub MCP tool call with args summary |
| `doc-link-check.log` | `doc_link_check.py` | Dangling doc links/anchors found on edit or at session stop |

**Log format:** `<ISO-8601-UTC> <event description>`

To inspect recent activity across all logs (PowerShell):
```powershell
Get-Content .claude\logs\*.log | Sort-Object | Select-Object -Last 50
```

---

## Overrides summary

| Situation | What to do |
|---|---|
| Need to run a destructive command (e.g., `rm -rf dist/`) | Run it manually in your terminal; do not ask Claude |
| Need to run a production-targeting command | `$env:AEGIS_PROD_CONFIRMED = "1"` before launching Claude Code |
| Tests are intentionally red (WIP session) | `$env:AEGIS_SKIP_TESTS = "1"` before launching Claude Code |
| Secret scanner fires on legitimate placeholder | Ensure the line contains `${`, `example`, or another allowlisted marker |
| Formatter changes your code unexpectedly | This is correct; ruff-canonical format is the project standard |

---

## Permissions (`settings.json`)

Beyond hooks, `.claude/settings.json` also carries permission rules that
reduce prompt friction and protect sensitive files:

**Pre-allowed (no prompt):**
```
uv run pytest, uv run ruff
ruff, pytest
git status, diff, log, add, commit
gh pr, gh issue
```

**Denied (Claude cannot read these files):**
```
.env, .env.*           ← secrets
**/*.dmp               ← crash dump payloads
```

These denials protect against an agent accidentally pulling raw incident data
or credentials into its context window.
