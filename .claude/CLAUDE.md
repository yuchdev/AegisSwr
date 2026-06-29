# CLAUDE.md - Aegis SWR agentic operating manual

This file governs how Claude Code agents work in this repository. It is loaded
into context every session. The root `../CLAUDE.md` describes the product
architecture; this file describes **how the agent fleet behaves**.

## 1. Project purpose & domain

**Aegis SWR (Synthetic War Room)** is a crash-dump and incident-response
forensics platform. It ingests untrusted artifacts (crash dumps, core files,
logs, telemetry), extracts crash data via debugger backends, runs a multi-agent
LLM debate (`os_kernel`, `code_analyst`, `log_historian`, `skeptic`) to a
weighted `consensus`, validates with a skeptic, and emits a Root-Cause-Analysis
report (`RCAReport`) - escalating to a human (`HITLRequest`) when confidence is
low.

**Security sensitivity is the defining property.** Every incident payload is
attacker-influenced and may contain secrets or PII. Treat all of it as hostile
and confidential.

> Note: the product's internal analysis agents (`src/aegis_swr/agents/`) are
> NOT the same as this `.claude/` dev fleet. Never conflate them.

## 2. Coding conventions agents must honour

- **Language/stack**: Python 3.12, Poetry, FastAPI, Typer, Pydantic v2,
  LangGraph, SQLAlchemy/asyncpg (Postgres), SQLite, Qdrant, boto3/S3,
  anthropic + openai SDKs, loguru.
- **Typing**: full annotations; **mypy `strict` must pass**. Always
  `Optional[T]` (import from `typing`) - never `T | None`, including in
  subscripts and `Annotated[...]`. Enforce with
  `python scripts/replace_optional.py --check`.
- **Lint/format**: ruff (`select = E,F,I,UP,B,SIM`, line length 100).
  `ruff format` is the formatter (no Black/Prettier). The post-edit hook formats
  automatically.
- **Error handling**: every external call (debugger subprocess, AI backend, DB,
  S3, Qdrant) gets a timeout and a defined failure path. RAII via context
  managers for all subprocess/socket/file resources. No bare `except:`.
- **Logging**: `loguru` with the project `SensitiveFilter`. **Never log secrets
  or raw incident payloads.** No `print` for diagnostics in product code.
- **Patterns**: Factory-Strategy for every backend family; thin CLI actions
  (logic lives in `core/`/`backends/`); view-facing progress via the `EventBus`.

## 3. Security rules (non-negotiable)

- **Never log secrets**; rely on `SensitiveFilter` and verify it covers new
  sinks.
- **Never hard-code credentials.** Read from settings/env. MCP servers receive
  tokens via `${VAR}` expansion in `.mcp.json` - agents never read `.env`.
- **Treat all incident payloads as sensitive** - no unredacted dump/log/stack
  text in logs, exceptions, stored reports, or API error bodies.
- Untrusted payload text must never reach a shell, SQL string, `eval`, or an AI
  prompt without sanitisation/parameterisation.
- The `secret_scan` hook blocks writes containing credentials; the `guard_bash`
  hook blocks destructive/production commands unless `AEGIS_PROD_CONFIRMED=1`.

## 4. Testing mandate

- **Every feature ships with unit tests**; **every external integration ships
  with an integration test** (mocked externals).
- Tests live in `tests/unit/` (CI-gated) and `tests/integration/`. Run:
  `poetry run pytest tests/unit/ -q --cov=aegis_swr --cov-report=term-missing`.
- The **Stop hook runs the unit suite**; a red suite blocks ending the session.
- Never weaken/`xfail`/delete a test to go green - fix the cause.

## 5. Commit & PR discipline

- **Conventional Commits**: `feat|fix|refactor|test|docs|chore|perf(scope): …`.
- **Atomic PRs** - one logical change per PR; keep diffs reviewable.
- **No direct pushes to `master`/`master`.** Branch → PR → review → merge.
- A change touching investigation flow needs an `incident-analyst` pass; one
  touching auth/secrets/integrations/payload ingestion needs a
  `security-auditor` pass (CRITICAL ⇒ merge blocked).

## 6. Docs mandate

- Public APIs and agent interfaces get docstrings (RST style: `:param:`,
  `:ivar:`, `:return:`) on **every** change.
- When `api/routes/` changes, refresh the OpenAPI artifact and the API
  reference. Keep `docs/README.md` index current. Runbooks in `docs/runbooks/`,
  ADRs in `docs/adr/` (MADR), threat models in `docs/security/`, reviews in
  `docs/reviews/`, post-mortems in `docs/post-mortems/`, manual QA in `docs/qa/`.

## 7. Agent delegation map

| Task                                                   | Delegate to           |
|--------------------------------------------------------|-----------------------|
| Design decisions, ADRs, interface contracts, tech-debt | `app-architect`           |
| Implementation, bug fixes, refactors                   | `python-expert`       |
| Tests, coverage, test-gap                              | `testing-expert`      |
| Pre-merge correctness/domain review                    | `feature-reviewer`    |
| Async dep/secret/perf/licence audits                   | `background-reviewer` |
| Docs, runbooks, OpenAPI, docstrings                    | `docs-updater`        |
| Lifecycle/escalation/playbook safety                   | `incident-analyst`    |
| Threat models, security gate                           | `security-auditor`    |
| Multi-step "ticket → merged PR" coordination           | `agent-orchestrator`        |

## 8. Model tiering (cost vs capability)

- **Opus 4.8** - deep reasoning where a wrong call is expensive: `app-architect`,
  `incident-analyst`, `security-auditor`, `agent-orchestrator`.
- **Sonnet 4.6** - high-throughput execution & review: `python-expert`, `testing-expert`,
  `feature-reviewer`, `background-reviewer`, `docs-updater`.
- **Haiku** - reserve for cheap mechanical jobs (log triage, formatting sweeps,
  one-line lookups). Don't use it for anything touching incident-safety logic.

Rule of thumb: route to the cheapest tier that can do the job correctly;
escalate to Opus only for safety-critical or genuinely ambiguous decisions.

## 9. Worktree policy

The **coding session (Terminal 1) should run in a git worktree** (`--worktree`)
for any non-trivial feature so its edits, formatter runs, and the Stop-hook test
gate are isolated from other work. `.worktreeinclude` (repo root) lists which
`.claude/` assets propagate into worktrees so hooks and skills keep working
there. The `.claude/` architect session does **not** edit `src/`.

## 10. Context seeding

Every session is seeded by the `SessionStart` hook with: current branch, last 5
commits, and open P0/P1 issues. Always-in-context: this file, the product
`../CLAUDE.md`, and the domain glossary in `agentic_fleet_design.md`. When acting
on a live incident, also surface the active on-call name and open incident count
(via the `pagerduty`/`slack` MCP).

## 11. Audit trail

Every agent action touching production data or GitHub leaves a log line under
`.claude/logs/` (`github-actions.log`, `bash-guard.log`, `secret-scan.log`,
`edits.log`, `tests.log`, `dep-audit.log`, `doc-link-check.log`). Format:
`<ISO-8601-UTC> <event>`.
Log contents are git-ignored; the directory is kept via `.gitkeep`.

## 12. Recurring / scheduled work

- **dep-audit** - weekly and on manifest change (`/dep-audit`).
- **Coverage report** - on every PR (`/test-gap`).
- **Daily incident-metric summary** - optional cron posting to the incident Slack channel.
See `agentic_fleet_design.md` §Scheduled tasks for the proposed cron/loop setup.
