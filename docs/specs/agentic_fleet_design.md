# Aegis SWR - Agentic Fleet Design

NOTE: The agentic operating layer for **Aegis SWR (Synthetic War Room)** - an incident-response forensics platform. 
This document describes agents required for the application of the Aegis SWR, not for the development process!

---

## 0. What the repo actually is

The design is grounded in the real repository, not a generic template:

| Signal                  | Finding                                                                                                                   |
|-------------------------|---------------------------------------------------------------------------------------------------------------------------|
| Language                | **Python 3.12**, managed by **uv** (`pyproject.toml`)                                                                 |
| Frameworks              | FastAPI, Typer (CLI `aegis`), Pydantic v2, **LangGraph**                                                                  |
| Data layer              | SQLAlchemy + asyncpg (**Postgres**), **SQLite**, **Qdrant**, S3 (boto3)                                                   |
| LLM SDKs                | `anthropic`, `openai`                                                                                                     |
| Lint/type/test          | **ruff** (`E,F,I,UP,B,SIM`, len 100), **full annotations**, **pytest** (+asyncio, +cov)                                        |
| Formatter               | `ruff format` - **no Black/Prettier present**                                                                             |
| CI                      | GitHub Actions: lint → typecheck → unit-test w/ coverage (`.github/workflows/ci.yml`)                                     |
| Domain                  | Crash/incident forensics: debugger backends → multi-agent LLM debate → consensus → skeptic → `RCAReport`, HITL escalation |
| Pre-existing `.claude/` | none - this is a greenfield agentic setup                                                                                 |

---

## 1. Domain glossary (always-in-context)

- **Investigation / incident lifecycle**: `detected/ingested → triaged
  (extracted+classified) → analysed (multi-agent debate) → validated (skeptic)
  → reported (RCAReport) → resolved → post-mortem`. HITL escalation branches
  from any stage.
- **Pipeline states**: `INITIALIZING → EXTRACTING → PARSING → ANALYZING →
  STORING` (`core/orchestrator.py`), surfaced as `DomainEvent`s on the
  `EventBus` (`core/events.py`).
- **Modes** (`IncidentMode`): `crash_dump`, `log_forensics`, `live_process`,
  `telemetry_anomaly`.
- **Consensus**: `core/consensus.py` blends the active debate panel's hypotheses,
  weighted by each agent's own declared `default_weight` class property, and
  normalized over the live panel. The panel is data-driven: the default panel is
  the four base agents (`os_kernel`, `code_analyst`, `log_historian`, `skeptic`);
  specialist forensic agents (`memory_forensics`, `concurrency_analyst`,
  `exploitability`, `resource_exhaustion`) join for the fault classes where they
  carry authority. `remediation_planner` is a post-debate synthesis agent and is
  not a weighted voter.
- **Agent panel**: the ordered list of debate agents assembled per incident from
  `AGENT_REGISTRY` by fault-aware auto-selection (`AgenticManagerStrategy` +
  `resolve_panel`), keyed off each agent's `authoritative_fault_classes`; the
  arbiter (`skeptic`) is always last. Synthesis agents (`remediation_planner`)
  are never part of the panel.
- **Key schemas** (`core/schemas.py`): `Hypothesis`, `SkepticVerdict`,
  `RCAReport`, `ConfidenceLevel`, `HITLRequest`, `RemediationPlan`, per-agent outputs.

---

## 2. CLAUDE.md (`.claude/CLAUDE.md`)

The agent operating manually, loaded every session. It codifies: project purpose &
security sensitivity; coding conventions (Python 3.12, `Optional[T]` never
`T | None`, full annotations, ruff, RAII, `SensitiveFilter`); the security rules
(never log secrets, no hard-coded creds, all payloads sensitive); the testing
mandate (unit per feature, integration per external, Stop-hook gate); commit
discipline (Conventional Commits, atomic PRs, no direct pushes to `master`); the
docs mandate; the **delegation map**; **model tiering**; **worktree policy**;
**context seeding**; the **audit trail** format; and **scheduled work**.

See §8–§12 below for the cross-cutting policies it encodes.

---

## 3. Agent fleet (`.claude/agents/*.md`)

Each agent is a Markdown file with YAML front-matter (`name`, `description`,
`model`, `tools`, `allowed-tools`) and a detailed system prompt.

| Agent                 | Model             | Role (one line)                                                                                                            |
|-----------------------|-------------------|----------------------------------------------------------------------------------------------------------------------------|
| `app-architect`       | claude-opus-4-8   | Design, ADRs (MADR → `docs/adr/`), interface contracts, tech-debt. Never writes impl code.                                 |
| `python-expert`       | claude-sonnet-4-6 | Implements features/fixes/refactors; reads ADR first; runs tests before+after; conventional commits.                       |
| `feature-reviewer`    | claude-sonnet-4-6 | Pre-merge review (correctness, injection in payload handling, missing auth, unhandled errors); LGTM / REQUEST_CHANGES.     |
| `background-reviewer` | claude-sonnet-4-6 | Async dep audit, secret scan, perf-regression, licence checks → `docs/reviews/`.                                           |
| `testing-expert`      | claude-sonnet-4-6 | Unit + integration (mocked externals) tests, manual checklist in `docs/qa/`, coverage delta.                               |
| `docs-updater`        | claude-sonnet-4-6 | Docs, runbooks, OpenAPI refresh, docstrings; keeps `docs/` in sync.                                                        |
| `incident-analyst`    | claude-opus-4-8   | *(Aegis-specific)* Validates lifecycle states, escalation paths, playbook safety; flags alert-fatigue / missed escalation. |
| `security-auditor`    | claude-opus-4-8   | *(Aegis-specific)* Threat models → `docs/security/`; CRITICAL ⇒ merge BLOCK.                                               |
| `agent-orchestrator`  | claude-opus-4-8   | *(added)* Coordinates multi-agent "ticket → merged PR" flows.                                                              |

> On front-matter: Claude Code reads `tools` for subagents; `allowed-tools` is
> included alongside it to satisfy the brief and is harmless where unused.

---

## 4. Skills (`.claude/skills/<name>/SKILL.md`)

| Skill               | Invocation                            | Purpose                                                                              |
|---------------------|---------------------------------------|--------------------------------------------------------------------------------------|
| `incident-triage`   | auto (lifecycle code)                 | State-machine completeness, escalation paths, timeout handling.                      |
| `playbook-validate` | `/playbook-validate <path>`           | Step ordering, required fields, idempotency, rollback, auth, weight sums.            |
| `adr-write`         | `/adr-write <title>`                  | Scaffold a MADR ADR, seeded from git log + open issues.                              |
| `pr-review`         | `/pr-review [pr]`                     | Fan out `feature-reviewer` + `security-auditor` in parallel; synthesise one verdict. |
| `test-gap`          | `/test-gap [path]`                    | Spawn `testing-expert`; risk-ranked list of missing tests.                           |
| `runbook-write`     | `/runbook-write <type>`               | Draft a runbook from the Aegis template.                                             |
| `post-mortem`       | `/post-mortem [id]`                   | Blameless timeline (git + incident data), five-whys, action items.                   |
| `dep-audit`         | auto (manifest change) + `/dep-audit` | CVE scan + licence check; deep write-up via `background-reviewer`.                   |
| `secret-scan`       | auto (PostToolUse) + `/secret-scan`   | Pattern-match secrets; shares engine with the blocking hook.                         |

> Truly automatic behaviors (`secret-scan`, `dep-audit`, `incident-triage`)
> are enforced by **hooks**, because Claude Code skills are model-invoked by
> description rather than event-triggered. The skill files document the manual
> entry point; the hooks provide the deterministic trigger.

---

## 5. Hooks (`.claude/settings.json` → `.claude/hooks/*.py`)

All hooks are **Python** (Windows-first host; Python is a hard dependency) and
share `_common.py` (stdin parsing, path resolution, logging, block/allow). Exit
code 2 blocks the tool call.

| Event / matcher                            | Script                | Behaviour                                                                                                                                               |
|--------------------------------------------|-----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| `SessionStart`                             | `session_start.py`    | Injects branch, last 5 commits, open P0/P1 issues (via `gh` if authed).                                                                                 |
| `PreToolUse / Bash`                        | `guard_bash.py`       | Blocks `rm -rf`, `DROP/TRUNCATE TABLE`, force-push, hard-reset, disk overwrite; blocks any `prod`/`production` command unless `AEGIS_PROD_CONFIRMED=1`. |
| `PreToolUse / Write or Edit or MultiEdit`  | `secret_scan.py`      | Scans pending content; **exit 2** if a secret pattern matches.                                                                                          |
| `PostToolUse / Write or Edit or MultiEdit` | `post_edit_format.py` | `ruff format` + `ruff check --fix` on `.py`; logs path to `edits.log`.                                                                                  |
| `PostToolUse / Write or Edit or MultiEdit` | `dep_audit.py`        | On manifest change, advisory `pip-audit` → `dep-audit.log`.                                                                                             |
| `PostToolUse / mcp__github__.*`            | `github_audit.py`     | Logs every GitHub MCP call (timestamp + safe arg summary) → `github-actions.log`.                                                                       |
| `Stop`                                     | `run_tests.py`        | Runs `uv run pytest tests/unit/ -q`; **exit 2** on failure (respects `stop_hook_active`; skip with `AEGIS_SKIP_TESTS=1`).                           |

All seven hooks were smoke-tested: destructive/prod commands block, secrets
block, clean writes pass, session context renders, GitHub calls and edits log.

---

## 6. MCP server connections (`.mcp.json`)

Tokens are supplied by **`${VAR}` environment expansion** - no secret ever lives
in the file (see §11, secrets management).

### Required

- **`github`** (`@modelcontextprotocol/server-github`) - PR management, issue
  tracking, code search, Actions log inspection. Drives `/pr-review`,
  `/adr-write` seeding, and post-mortem action-item creation. Token:
  `${GITHUB_PERSONAL_ACCESS_TOKEN}`.
- **`slack`** (`@modelcontextprotocol/server-slack`) - monitor the incident
  channel, post automated RCA/incident summaries, page on-call via a Slack
  workflow. Tokens: `${SLACK_BOT_TOKEN}`, `${SLACK_TEAM_ID}`.
- **`postgres`** (`@modelcontextprotocol/server-postgres`) - direct inspection
  of stored incidents/`RCAReport`s (the project's primary store is asyncpg/
  Postgres via `postgres_store.py`); used for incident-state queries and schema
  validation during dev. Connection: `${AEGIS_DATABASE_URL}`. *(SQLite is also a
  product store backend; swap to a `sqlite` MCP for local-only dev DBs.)*

### Strongly recommended for Aegis SWR

- **`sentry`** (`@sentry/mcp-server`) - pull error events, link runtime errors to
  stored incidents, track regression rates. Token: `${SENTRY_AUTH_TOKEN}`.
- **`pagerduty`** (`@pagerduty/mcp-server`) - read on-call schedules, acknowledge
  / escalate alerts from agentic flows (feeds the on-call name into context).
  Token: `${PAGERDUTY_USER_API_TOKEN}`.
- **`context7`** (`@upstash/context7-mcp`) - up-to-date docs for libraries in the
  stack (FastAPI, LangGraph, Pydantic, SQLAlchemy, Qdrant) injected per task, so
  agents code against current APIs. Key: `${CONTEXT7_API_KEY}`.
- **`playwright`** (`@playwright/mcp`) - E2E verification of any Aegis web UI and
  post-deploy smoke tests.

### Optional / deferred

- **`linear`** - add if the team adopts Linear; today issues are in GitHub.
- **`filesystem`** - intentionally **skipped**; Claude Code has native file tools.

---

## 7. Settings & permissions (`.claude/settings.json`)

Beyond hooks, `settings.json` pre-allows safe, high-frequency commands (pytest,
ruff, common git/gh read+commit verbs) to reduce prompt friction, and
**denies reads** of `.env*` and `*.dmp` dumps

---

## 8. Model tiering (cost vs capability)

- **Opus 4.8** - safety-critical / high-ambiguity reasoning: `app-architect`,
  `incident-analyst`, `security-auditor`, `agent-orchestrator`.
- **Sonnet 4.6** - high-throughput execution and review: `python-expert`, `testing-expert`,
  `feature-reviewer`, `background-reviewer`, `docs-updater`.
- **Haiku** - reserved for cheap mechanical jobs (log triage, formatting
  sweeps); never for incident-safety logic.

Principle: the cheapest tier that does the job correctly; escalate to Opus only when
a wrong decision is expensive (domain safety, security, architecture).

---

## 9. Orchestration: ticket → merged PR

The `agent-orchestrator` agent runs the canonical sequence, parallelizing independent steps:

1. **architect** → ADR (gate: human approves) - *if non-trivial*.
2. **coder** → branch plus implementation against the ADR; tests before/after.
3. **qa** → unit plus integration tests; coverage delta.
4. **incident-analyst** ∥ **security-auditor** → run in parallel; lifecycle
   safety and threat model. *(only for relevant surfaces; CRITICAL ⇒ stop.)*
5. **feature-reviewer** → LGTM / REQUEST_CHANGES; loop to coder until LGTM.
6. **docs** → docs / OpenAPI / docstrings.
7. **Land** → open PR (never push to `master`); summarize the audit trail.

For a single small change, skip the orchestrator and delegate directly per the
map in `.claude/CLAUDE.md` §7.

---

## 10. Worktree policy & `.worktreeinclude`

- The **coding session (Terminal 1) should use `--worktree`** for any
  non-trivial feature, isolating its edits, formatter runs, and the Stop-hook
  test gate.
- `.worktreeinclude` (repo root) propagates `.claude/CLAUDE.md`,
  `settings.json`, `agents/**`, `skills/**`, `hooks/**`, `.mcp.json`, and the
  root `CLAUDE.md` into worktrees, so hooks and skills work in isolation.
  `.claude/logs/` is **excluded** (per-worktree local logs, git-ignored).

---

## 11. Secrets management & audit trail

- **Secrets**: agents never read `.env` (denied in `settings.json`). MCP servers
  receive tokens via `${VAR}` expansion in `.mcp.json`, resolved from the shell
  environment / a secrets manager at launch. The `secret_scan` hook blocks any
  credential from being written into the repo. Product code already redacts via
  `SensitiveFilter`.
- **Audit trail**: every production-touching or GitHub-touching action appends a
  line to `.claude/logs/` - format `<ISO-8601-UTC> <event>`:
  - `github-actions.log` - every GitHub MCP call plus safe arg summary
  - `bash-guard.log` - every blocked destructive/prod command
  - `secret-scan.log` - every blocked writing w/ finding type plus location (never
    the value)
  - `edits.log` - every file written/edited
  - `tests.log` - Stop-hook PASS/FAIL/SKIP
  - `dep-audit.log` - manifest-change advisory audits
  Log **contents** are git-ignored; the directory is kept via `.gitkeep`.

---

## 12. Scheduled / recurring tasks (proposed)

| Cadence                     | Task                                                  | Mechanism                                                 |
|-----------------------------|-------------------------------------------------------|-----------------------------------------------------------|
| Weekly + on manifest change | Dependency CVE + licence audit                        | `/dep-audit` (skill) + `dep_audit.py` (hook)              |
| Every PR                    | Coverage / test-gap report                            | `/test-gap` in the PR flow                                |
| Daily                       | Incident-metric summary to the incident Slack channel | a scheduled `loop`/cron agent posting via the `slack` MCP |

Set these up with the Claude Code `/schedule` (cron) or `/loop` facilities;
they are documented here as the intended recurring backbone rather than
hard-coded, since cadence is a team/ops decision.

---

## 13. Agentic Checklist

## Agent Description Review Checklist

### Identity

- [ ] Has a clear role.
- [ ] Avoids theatrical persona.
- [ ] Names the project/domain.

### Scope

- [ ] Says when to use the agent.
- [ ] Says when not to use the agent.
- [ ] Lists allowed actions.
- [ ] Lists forbidden actions.

### Context

- [ ] Says what to read first.
- [ ] Identifies important project files.
- [ ] Avoids unnecessary full-repo scanning.

### Workflow

- [ ] Has an operating loop.
- [ ] Has stop/escalation conditions.
- [ ] Defines handoff rules.

### Output

- [ ] Requires structured output.
- [ ] Requires a changed file list.
- [ ] Requires a test/verification report.
- [ ] Requires explicit exit condition status.

### Quality

- [ ] Has test requirements.
- [ ] Has documentation requirements.
- [ ] Has verification commands.
- [ ] Forbids pretending tests passed.

### Maintainability

- [ ] Has a clear entry point.
- [ ] Has a clear exit point.
- [ ] Has a clear error handling policy.
- [ ] Has a clear logging policy.
- [ ] Is short enough to be reused.
- [ ] Does not duplicate large project docs.
- [ ] Links to shared policies instead of copying them.

---

## 14. File manifest

Created under `.claude/` and the repo root (see the closing list in the session
output for one-line descriptions of each).
