# Aegis SWR - Agentic Fleet Tutorial

Welcome. This tutorial assumes you have just joined the Aegis SWR project and
have little or no prior experience with Claude Code's agentic features. By the
end you will know how to use the fleet for every common task a developer faces
on this codebase.

---

## Part 1 - What is happening and why

### The short version

Claude Code is not just a chat assistant. In this project it is configured with
a **fleet of specialised agents**, a set of **skills** you can invoke with
slash commands, and **hooks** that run automatically to enforce quality and
security. Together these make Claude Code behave like a small, specialised
engineering team sitting inside your terminal.

### The two things you must keep straight

**Product agents** (`src/aegis_swr/agents/`) are parts of the Aegis SWR
application itself. They analyse crashes at runtime - `os_kernel`,
`code_analyst`, `log_historian`, `skeptic`. You work on their code. You do not
call them in your terminal.

**Dev agents** (`.claude/agents/`) are assistants that help you build the
product. `app-architect`, `python-expert`, `testing-expert`, `feature-reviewer`, `docs-updater`, etc. You call
these in your Claude Code session. This tutorial is about these.

---

## Part 2 - Getting started

### Opening a session

```powershell
# From the repo root:
claude
```

The very first thing you will see (before any response to your message) is
output from the `session_start.py` hook:

```
# Aegis SWR - session context
Branch: feat/my-new-feature

Recent commits:
  f940c14 Cover code with docstring
  fa44033 Main CLI
  ...

Open P0/P1 issues: none found (or gh not authenticated).

Reminder: incident payloads are sensitive. Never log secrets or raw PII.
Delegate per .claude/CLAUDE.md ...
```

This is automatic. Every session starts with the current branch and recent
history already in context, so you do not need to explain "we are on branch X
and recently did Y."

### Authenticating GitHub (once, recommended)

Some skills and hooks become much more useful when `gh` is authenticated:
- `session_start.py` lists open P0/P1 issues
- `/adr-write` seeds context from open issues
- `/pr-review` can post review comments directly
- `/post-mortem` can open follow-up issues

```powershell
gh auth login
```

---

## Part 3 - The hooks (things that happen automatically)

Before you start asking Claude to do things, know what runs in the background
without you asking.

### The formatter runs after every file edit

Whenever Claude writes or edits a `.py` file, `ruff format` and `ruff check
--fix` run automatically. You might see your code re-indented or imports
reordered. That is correct behaviour, not a bug. Do not try to undo it.

### The secret scanner runs before every file write

If Claude ever tries to write something that looks like a real API key,
database password, or private key into a file, the write is blocked. You will
see:

```
Blocked by aegis secret-scan: possible secret in config.py:
  - line 12: Anthropic API key
Never commit credentials. Use environment variables / ${VAR} references.
```

If you hit this legitimately (e.g., you're writing test fixtures that mention
the word "token"), just make sure the value contains one of the allowlisted
markers: `example`, `placeholder`, `${`, `your-`, `changeme`, etc.

### Destructive shell commands are blocked

Claude will never run `rm -rf`, `DROP TABLE`, `git push --force`, or
`git reset --hard` without you noticing. These are blocked automatically. If
you need to run one yourself, do it in a separate terminal - do not ask Claude.

### The test suite runs when the session ends

When Claude finishes and tries to stop, `pytest tests/unit/ -q` runs. If any
test is red, Claude is blocked from closing and must fix the regression first.

If your tests are intentionally broken (you are mid-feature and not ready to
fix them), start the session with:
```powershell
$env:AEGIS_SKIP_TESTS = "1"
claude
```

---

## Part 4 - Agents in practice

You delegate to an agent by saying "use the X agent to …" in your message.
Claude spawns the agent, lets it work, and returns the result.

### Scenario 1: You are asked to add a new feature

**Situation:** The ticket says "Add support for exporting RCA reports as CSV".
You have no idea where to start.

**Step 1 - Get a design first**

Ask the `app-architect` agent to design it before anyone writes code:

```
Use the architect agent to design how we should add CSV export for RCA reports.
I want an ADR and a task list for coder.
```

The architect will:
1. Read the existing storage backends (`filesystem_store.py`, etc.)
2. Look at the `RCAReport` Pydantic schema
3. Check existing ADRs for precedent
4. Propose 2–3 options with honest trade-offs
5. Write an ADR to `docs/adr/NNNN-csv-export-for-rca-reports.md`
6. List tasks for `python-expert` and `testing-expert`

**Step 2 - Implement against the ADR**

Once you (and optionally the team) approve the ADR:

```
Use the coder agent to implement the CSV export feature following the ADR
at docs/adr/0004-csv-export-for-rca-reports.md. Start with the CLI command.
```

The coder will:
1. Read the ADR
2. Run the tests to capture a green baseline
3. Implement the feature
4. Run `pytest`, `mypy`, and `ruff` after
5. Propose a conventional commit message (`feat(cli): add CSV export command`)

**Step 3 - Add tests**

```
Use the qa agent to write unit tests for the CSV export feature.
Report the coverage delta.
```

**Step 4 - Review before merge**

```
/pr-review feat/csv-export
```

This fans out `feature-reviewer` and `security-auditor` in parallel. Two
reviewers run simultaneously; you get one synthesised verdict.

**Step 5 - Update docs**

```
Use the docs agent to update the CLI reference (docs/configuration/cli.md)
for the new export command and add a runbook entry if needed.
```

---

### Scenario 2: Fixing a bug

**Situation:** A user reports that the `skeptic` agent sometimes produces a
`SkepticVerdict` with `verdict = None` when the consensus confidence is
`HIGH`. This should never happen.

**Step 1 - Ask the coder to investigate and fix**

```
Use the coder agent to investigate and fix the bug where SkepticVerdict.verdict
is None even when consensus confidence is HIGH. The relevant code is in
src/aegis_swr/agents/skeptic.py and src/aegis_swr/core/consensus.py.
```

The coder will read the code, find the bug, fix it, and ensure `pytest` passes.

**Step 2 - Ask the incident-analyst to validate**

Because this touches the skeptic/consensus path, the incident-analyst should
confirm the fix does not break any lifecycle invariants:

```
Use the incident-analyst agent to verify that the SkepticVerdict fix in the
current diff does not break any escalation paths or introduce a scenario where
a LOW-confidence result could bypass HITL escalation.
```

**Step 3 - Run the full review**

```
/pr-review
```

---

### Scenario 3: You inherited code and want to know where the tests are weak

**Situation:** You have been assigned to improve the reliability of
`core/incident_similarity.py`. You suspect test coverage is thin.

```
/test-gap src/aegis_swr/core/incident_similarity.py
```

You will get a risk-ranked list:

```
## Test Gap - src/aegis_swr/core/incident_similarity.py (coverage: 61%)
### P0 - must test
- incident_similarity.py:45-72 - similarity threshold boundary: what happens
  at exactly 0.5 similarity - risky: could cause alert-fatigue or missed
  escalation - suggested: parametrize over similarity scores near threshold
### P1 - should test
...
```

Follow up:
```
Use the qa agent to write the P0 tests identified in the test gap for
incident_similarity.py.
```

---

### Scenario 4: Adding a new integration (security-sensitive)

**Situation:** You need to add a webhook endpoint that receives incident signals
from an external monitoring tool. It accepts raw JSON payloads.

This change touches **payload ingestion and auth** - it needs a security review.

**Step 1 - Design**

```
Use the architect agent to design the external signal webhook endpoint.
The payload is untrusted JSON. Write an ADR covering auth, input validation,
rate limiting, and how we prevent injection via log/stack-trace fields.
```

**Step 2 - Implement**

```
Use the coder agent to implement the webhook endpoint following ADR 0005.
```

**Step 3 - Security review before any PR**

```
Use the security-auditor agent to threat-model the new webhook endpoint
in PR #55. The endpoint accepts raw external JSON payloads.
```

The security-auditor will apply STRIDE-lite analysis. If it issues a `BLOCK`
verdict, **do not merge until the issue is resolved**, even if the
feature-reviewer says LGTM. A BLOCK from security overrides everything.

**Step 4 - Full review**

```
/pr-review 55
```

---

### Scenario 5: An incident just happened

**Situation:** A memory-access-violation crash in production was mitigated an
hour ago. The team wants a post-mortem.

**Step 1 - Capture the post-mortem**

```
/post-mortem INC-2024-0112
```

The skill will:
1. Reconstruct the timeline from git log and stored `RCAReport`s
2. Walk through the five-whys with you
3. Produce `docs/post-mortems/2024-01-12-INC-2024-0112.md`
4. List action items routed to `python-expert`, `testing-expert`, `docs-updater`, `app-architect`

**Step 2 - Update the runbook if it was missing a step**

```
Use the docs agent to update docs/runbooks/memory-access-violation.md
to cover the log-correlation step we missed during triage.
```

**Step 3 - Validate the updated runbook**

```
/playbook-validate docs/runbooks/memory-access-violation.md
```

---

### Scenario 6: Weekly dependency health check

**Situation:** It's Monday morning. Run the dependency audit.

```
/dep-audit
```

If it finds vulnerabilities:
```
Use the coder agent to bump <package> from <old-version> to <new-version>
as recommended by the dep-audit report at docs/reviews/2026-06-14-dep-audit.md.
Run the test suite after and ensure everything is green.
```

---

### Scenario 7: The orchestrator handling everything

**Situation:** You have a well-defined ticket and just want Claude to handle
the whole lifecycle - design, code, tests, review, and docs - with appropriate
checkpoints.

```
Use the orchestrator agent to implement GitHub issue #38:
"Add S3 export destination for RCA reports". Take it from ADR through
merged PR, pausing for my approval after the ADR and before merge.
```

The orchestrator will:
1. Have `app-architect` write an ADR - then **pause and ask you to approve**
2. Have `python-expert` implement it
3. Have `testing-expert` write tests in parallel with `incident-analyst` and
   `security-auditor` validation
4. Have `feature-reviewer` review (loop to `python-expert` if REQUEST_CHANGES)
5. Have `docs-updater` update the reference
6. **Pause and ask you to approve before opening the PR**

Use the orchestrator when you want the full pipeline with guardrails, not when
you want fine-grained control.

---

## Part 5 - Slash commands at a glance

Type these directly in the Claude Code chat:

```
/adr-write <title>          Scaffold a new ADR in docs/adr/
/pr-review [pr|branch]      Full parallel PR review
/test-gap [path]            Risk-ranked missing tests
/playbook-validate <path>   Validate a playbook or weight file
/runbook-write <type>       Draft a runbook from the Aegis template
/post-mortem [incident-id]  Run a blameless post-mortem
/dep-audit                  CVE + licence dependency audit
/secret-scan [paths]        Manual sweep for hardcoded credentials
```

---

## Part 6 - Common mistakes and how to avoid them

### "Claude tried to write an API key into a file and was blocked"

Expected behaviour - the secret scanner caught it. Tell Claude to use
`${VARIABLE_NAME}` instead and store the actual value in the environment. Look
at how `.mcp.json` uses `${GITHUB_PERSONAL_ACCESS_TOKEN}` for the pattern.

### "Claude can't run `rm -rf dist/` and is stuck"

The bash guard blocks this. Run it yourself in a separate terminal. Destructive
commands are intentionally excluded from automation.

### "The session ended but the tests are failing"

The Stop hook detected failing tests and blocked the session. Claude must fix
them before it can close. If you genuinely want to end the session with red
tests (e.g., mid-refactor), run:
```powershell
$env:AEGIS_SKIP_TESTS = "1"
claude
```

### "The coder keeps changing the code style and ruff keeps reformatting it"

Do not fight `ruff format` - it is the project standard. If a specific
formatting decision looks wrong, check the ruff configuration in `pyproject.toml`
under `[tool.ruff]`. Never ask Claude to disable the formatter.

### "I asked the architect to write code and it refused"

Correct behaviour. The architect writes Markdown (ADRs and docs) only. To get
code, tell `python-expert` to implement what the `app-architect` designed.

### "The feature-reviewer approved but security-auditor said BLOCK"

Do not merge. The security verdict overrides the feature verdict in `/pr-review`.
Fix the security finding and re-run `/pr-review`.

### "I want Claude to touch a `.dmp` file but it's denied"

`.dmp` files are in the deny list because they are incident payloads that may
contain PII. If you genuinely need to inspect a dump, do it in a separate tool
(`cdb.exe`, WinDbg, `gdb`) - do not load it into Claude's context.

---

## Part 7 - Reading the audit logs

Everything Claude does leaves a trace in `.claude/logs/`. You can review what
happened in a session after the fact:

```powershell
# What files did Claude edit?
Get-Content .claude\logs\edits.log

# Were any tests failing at session end?
Get-Content .claude\logs\tests.log

# Did Claude try any destructive commands?
Get-Content .claude\logs\bash-guard.log

# Which GitHub actions were taken?
Get-Content .claude\logs\github-actions.log
```

These logs are git-ignored, so they never enter the repo. They are per
working-tree, local only.

---

## Part 8 - Quick-reference card

```
AGENTS (call with "use the X agent to…")
  architect         Design, ADRs, contracts        Opus 4.8
  coder             Implement, fix, refactor        Sonnet 4.6
  feature-reviewer  PR correctness/domain review    Sonnet 4.6
  background-reviewer Dep/secret/perf/licence audit Sonnet 4.6
  qa                Tests, coverage, test-gap       Sonnet 4.6
  docs              Docs, runbooks, OpenAPI         Sonnet 4.6
  incident-analyst  Lifecycle/escalation safety     Opus 4.8
  security-auditor  Threat models, merge gate       Opus 4.8
  orchestrator      Full-lifecycle coordination     Opus 4.8

SKILLS (type as /command)
  /adr-write <title>           Scaffold MADR ADR
  /pr-review [pr|branch]       Parallel feature+security review
  /test-gap [path]             Risk-ranked missing tests
  /playbook-validate <path>    Validate playbook
  /runbook-write <type>        Draft runbook
  /post-mortem [id]            Blameless post-mortem
  /dep-audit                   CVE + licence audit
  /secret-scan [paths]         Sweep for hardcoded secrets

HOOKS (automatic)
  SessionStart   → seeds branch, commits, P0/P1 issues
  PreToolUse/Bash → blocks rm -rf, DROP TABLE, prod commands
  PreToolUse/Write → blocks if secret pattern found
  PostToolUse/Write → ruff format, edits.log
  PostToolUse/Write → dep-audit on manifest changes
  PostToolUse/github → logs every GitHub MCP call
  Stop            → runs pytest; blocks on failure

OVERRIDES
  AEGIS_SKIP_TESTS=1      skip Stop-hook test gate (WIP sessions)
  AEGIS_PROD_CONFIRMED=1  allow production-targeting commands
```

---

## Where to go next

- **`docs/agent/agents.md`** - deep reference for every agent
- **`docs/agent/skills.md`** - deep reference for every skill
- **`docs/agent/hooks.md`** - deep reference for every hook and its logs
- **`/docs/specs/agentic_fleet_design.md`** - architectural design decisions behind the fleet
- **`.claude/CLAUDE.md`** - the operating manual loaded into every session
- **`CLAUDE.md`** (repo root) - the product architecture guide
- **`docs/README.md`** - index of all project docs
