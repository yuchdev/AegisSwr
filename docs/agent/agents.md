# Aegis SWR - Agent Reference

This document describes every agent in the `.claude/agents/` fleet: its
responsibility, the model it uses, which tools it has access to, and exactly
when to delegate to it. For practical examples see `tutorial.md`.

These agents are **not** the same as the Aegis SWR **product**, described in `docs/specs/agentic_fleet_design.md`. 
The product contains its own analytical agents inside `src/aegis_swr/agents/` that run inside the Aegis
pipeline at runtime to produce incident reports. As of Milestone 0002 the product roster is:

| `agent_key`           | Class                        | Category  | Tier          | One-line role |
|-----------------------|------------------------------|-----------|---------------|---------------|
| `os_kernel`           | `OSKernelAgent`              | base      | debate        | OS/kernel environment context; injects arbiter corrections each round |
| `code_analyst`        | `CodeAnalystAgent`           | base      | debate        | Code logic and probabilistic fix encoding |
| `log_historian`       | `LogHistorianAgent`          | base      | debate        | Historical pattern correlation via VectorStore |
| `skeptic`             | `SkepticAgent`               | base      | debate (last) | Programmatic + LLM validation; produces corrections for the next round |
| `memory_forensics`    | `MemoryForensicsAgent`       | forensic  | debate        | Heap corruption, use-after-free, allocator tells, fill-pattern signatures |
| `concurrency_analyst` | `ConcurrencyAnalystAgent`    | forensic  | debate        | Deadlocks, lock-ordering inversions, races, thread wait-chains |
| `exploitability`      | `ExploitabilityAnalystAgent` | forensic  | debate        | Exploit/vuln assessment; attacker-control reach, mitigation state |
| `resource_exhaustion` | `ResourceExhaustionAgent`    | forensic  | debate        | Handle/fd/memory leaks, OOM, connection-pool exhaustion |
| `remediation_planner` | `RemediationPlannerAgent`    | synthesis | post-debate   | Ordered, rollback-covered remediation playbook from the confirmed RCA |

Forensic specialists join the debate panel only for the fault classes they are authoritative for
(fault-aware auto-selection); the four base agents always participate. `remediation_planner` is a
post-debate synthesis agent, never a weighted voter.

The agents described here are **dev-time** assistants that help engineers build and maintain the codebase. 
Never conflate them!

---

## Quick-reference delegation map

| You want to…                                                       | Call this agent       |
|--------------------------------------------------------------------|-----------------------|
| Coordinate a multi-step feature end to end                         | `agent-orchestrator`  |
| Decide how to design something / write an ADR                      | `app-architect`       |
| Write or fix Python code                                           | `python-expert`       |
| Review a PR or diff before merge                                   | `feature-reviewer`    |
| Run a deep audit (deps, secrets, perf, licences) in the background | `background-reviewer` |
| Write or improve tests                                             | `testing-expert`      |
| Update docs, runbooks, or OpenAPI spec                             | `docs-updater`        |
| Check whether incident-lifecycle code is correct and safe          | `incident-analyst`    |
| Threat-model or security-audit a change                            | `security-auditor`    |

---

## `app-architect`

**Model:** claude-opus-4-8
**Tools:** Read, Grep, Glob, Write (docs only), Edit (docs only), WebFetch, WebSearch, TodoWrite

### What it does

The architect owns **every design decision** for Aegis SWR. It reads the
codebase and existing ADRs before proposing anything, presents honest
trade-offs, and writes Architecture Decision Records (ADRs) using the **MADR**
template into `docs/adr/NNNN-kebab-title.md`. It never writes implementation
code - once the decision is made, it hands a list of coding tasks to `python-expert`.

### Domain knowledge it carries

- The full incident lifecycle and `EventBus` contract (`core/events.py`)
- Every backend family under `src/aegis_swr/backends/` and their abstract
  interfaces
- The Pydantic schema set in `core/schemas.py`
- The Factory-Strategy pattern conventions
- The existing ADRs and roadmap in `docs/adr/`

### When to use it

- You're about to make a decision that affects multiple files or teams (e.g.,
  adding a new storage backend, changing the consensus algorithm, restructuring
  the API)
- You need to document an architectural choice formally for the team
- You want a ranked tech-debt list with recommended sequencing
- You need a new abstract base class interface or Pydantic schema defined before
  anyone codes it

### Hard limits

- Never produces Python implementation code - it writes Markdown in `docs/`
  only
- Every ADR is created with status `Proposed`; a human or the team must promote
  it to `Accepted`

### Example prompt

```
Use the architect agent to design how we should add a new OTLP (OpenTelemetry)
log adapter backend. I want an ADR and a list of tasks for coder.
```

---

## `python-expert`

**Model:** claude-sonnet-4-6
**Tools:** Read, Grep, Glob, Edit, Write, Bash, TodoWrite

### What it does

The coder turns agreed designs into working, tested Python. Before touching a
file it reads the governing ADR and/or GitHub issue, captures a green test
baseline, then implements to project conventions. After every change it runs
`pytest` and `ruff` and blocks itself if any check fails. It commits
with Conventional Commits (`feat:`, `fix:`, `refactor:`, etc.) and never pushes
directly to `master`.

### Project rules it enforces

- `Optional[T]` from `typing`, never `T | None`
- full annotations on public surfaces
- ruff lint clean (the post-edit hook formats automatically)
- RAII via context managers for subprocess/socket/file resources
- `SensitiveFilter` on all loggers - never logs secrets or raw payloads
- Thin CLI actions; business logic in `core/` and `backends/`

### When to use it

- Implementing any story, feature, or bugfix that touches `src/` or `tests/`
- Refactoring code to match an ADR or the project's conventions
- Fixing a failing test or type error

### What it will NOT do

- Author ADRs (architect's job)
- Self-approve its own diff (feature-reviewer's job)
- Ignore a failing test to get green

### Example prompt

```
Use the coder agent to implement the OTLP log adapter following ADR 0004.
Create the adapter at src/aegis_swr/backends/log/otlp_adapter.py.
```

---

## `feature-reviewer`

**Model:** claude-sonnet-4-6
**Tools:** Read, Grep, Glob, Bash (read-only: git diff, gh pr)

### What it does

The feature reviewer is the gate between a finished change and `master`. It reads
the diff, checks for correctness and security issues, verifies domain accuracy
against the Aegis lifecycle, and emits a structured review with a single
**LGTM** or **REQUEST_CHANGES** verdict. It never edits code.

### Checks it runs (in priority order)

1. **Correctness** - logic errors, resource leaks, unhandled errors, wrong
   async/await
2. **Security** - injection paths in payload handling, missing auth, secrets in
   logs or responses
3. **Domain accuracy** - correct lifecycle state transitions, Factory-Strategy
   contract, valid `RCAReport`/`SkepticVerdict` shapes
4. **Conventions** - `Optional[T]`, `ruff`, `replace_optional.py --check`, docstrings on public APIs,
   commit message format
5. **Test coverage** - does the change ship with meaningful tests?

### Output format (always this shape)

```
## Feature Review - <branch/PR>
**Verdict: LGTM | REQUEST_CHANGES**

### Blocking issues
### Non-blocking suggestions
### Security notes
### Test coverage
```

### When to use it

- Before every merge, on any branch - run via `/pr-review` for the full
  parallel review, or directly for a quick focused pass
- After `python-expert` completes a change and says it's ready

### Example prompt

```
Use the feature-reviewer agent to review the diff on branch feat/otlp-adapter.
```

---

## `background-reviewer`

**Model:** claude-sonnet-4-6
**Tools:** Read, Grep, Glob, Bash, Write, WebFetch, WebSearch

### What it does

The background reviewer runs **asynchronously, off the hot path**. Its job is
deep audits that would be too slow or distracting inline: dependency CVE scans,
secret sweeps across new files, performance-regression hunting, and license
compatibility checks. It writes a dated report to `docs/reviews/YYYY-MM-DD-
<topic>.md` rather than issuing a blocking verdict.

### Tasks it performs

- **Dependency audit** - `pip-audit`, advisory CVE lookups, outdated pins
- **Secret scanning** - runs the shared `secret_scan.py` engine across new
  and changed files
- **Performance regression** - looks for O(n²) over stack frames, sync I/O on
  async paths, unbounded memory, missing pagination, missing token budgeting
- **License compatibility** - flags GPL/AGPL or unknown-license direct
  dependencies

### When to use it

- Before a major release to sweep the whole repo
- When a dependency bump introduces many new transitive packages
- When performance metrics look suspicious in CI
- Scheduled weekly (`/dep-audit` skill); also triggered automatically by the
  `dep_audit.py` hook when `pyproject.toml` changes

### Example prompt

```
Use the background-reviewer agent to audit all dependencies added in the last
two weeks and check for licence conflicts.
```

---

## `testing-expert`

**Model:** claude-sonnet-4-6
**Tools:** Read, Grep, Glob, Edit, Write, Bash, TodoWrite

### What it does

The QA agent owns test quality. For every new feature it writes unit tests
(pure logic, no network/disk), integration tests (mocked externals), and a
manual test checklist in `docs/qa/<feature>.md`. It also runs the full suite and
reports the coverage delta vs. the previous baseline.

### Test principles

- Assert real behavior - not just "does not raise"
- Precise assertions on `RCAReport`, `SkepticVerdict`, `ConfidenceLevel` fields
- Mock every external: AI providers, debugger subprocesses, DB engines, S3,
  Qdrant, EventBus consumers
- Never weaken or delete a failing test - fix the cause

### Coverage priority (the highest risk first)

1. Consensus/skeptic logic and payload parsing
2. Backend strategies and orchestrator state transitions
3. Schema validation and HITL escalation paths
4. CLI/view formatting (the lowest risk)

### When to use it

- Alongside `python-expert` whenever a feature ships (or ask the `agent-orchestrator` to coordinate both)
- `/test-gap` skill to find the highest-value missing tests on any module
- After a refactor to verify behavior was preserved

### Example prompt

```
Use the qa agent to write unit tests for the new OTLP adapter and report the
coverage delta.
```

---

## `docs-writer`

**Model:** claude-sonnet-4-6
**Tools:** Read, Grep, Glob, Edit, Write, Bash, WebFetch

### What it does

The agent writes **documentation** for the project. It produces runbooks, API references, on-call guides, post-mortem templates, and docstrings. It uses the `/runbook-write` skill template and the Aegis RST docstring convention (`:param:`, `:ivar:`, `:return:`).

### Output locations

- `docs/runbooks/` - operational guides per incident type
- `docs/api/` - REST reference and OpenAPI JSON
- `docs/README.md` - index (always updated when a new doc is added)
- `docs/post-mortems/` - blameless post-mortem template instances
- Inline docstrings in changed `src/` files

---

## `docs-updater`

**Model:** claude-sonnet-4-6
**Tools:** Read, Grep, Glob, Edit, Write, Bash, WebFetch

### What it does

The docs agent keeps `docs/` synchronised with code changes. It writes README
sections, API references, runbooks, on-call guides, post-mortem templates, and
docstrings. When `api/routes/` changes it refreshes the OpenAPI artifact. It
uses the `/runbook-write` skill template and the Aegis RST docstring convention
(`:param:`, `:ivar:`, `:return:`).

### Output locations

- `docs/runbooks/` - operational guides per incident type
- `docs/api/` - REST reference and OpenAPI JSON
- `docs/README.md` - index (always updated when a new doc is added)
- `docs/post-mortems/` - blameless post-mortem template instances
- Inline docstrings in changed `src/` files

### When to use it

- After `python-expert` completes any public-API change
- Before a release to refresh runbooks and the API reference
- When an on-call engineer reports that a runbook is wrong or incomplete

### Example prompt

```
Use the docs agent to update the runbook for memory-access-violation incidents
to cover the new OTLP log correlation step.
```

---

## `incident-analyst`

**Model:** claude-opus-4-8 *(Aegis-specific)*
**Tools:** Read, Grep, Glob, Bash, Write

### What it does

The incident analyst is the **domain safety guard** for the investigation
pipeline. It validates that code changes correctly implement the incident
lifecycle, checks that escalation paths are always reachable, and reviews
playbook/consensus logic for correctness and safety. It catches the two
failure modes that matter most in an on-call tool:
- **Missed escalation** - a real incident that never pages anyone
- **Alert fatigue** - an incident that pages the same person 50 times

### Invariants it checks

- Every pipeline state has a defined exit (success and failure)
- `ConfidenceLevel.LOW` + rejected `SkepticVerdict` → always produces a
  `HITLRequest`, never a silent weak RCA
- Every external call has a timeout and a defined fallback
- `incident_similarity.py` dedup logic does not over-suppress or under-suppress
- Playbook steps are idempotent and rollback-covered

### When to use it

- Before merging any change to `core/orchestrator.py`, `core/consensus.py`,
  `core/incident_similarity.py`, `core/schemas.py` (Hypothesis/SkepticVerdict/
  HITLRequest), or any playbook file
- When a new `IncidentMode` or fault class is added
- Part of the orchestrator's default pipeline for lifecycle-touching PRs

### Example prompt

```
Use the incident-analyst agent to verify that the new low-confidence escalation
path in PR #47 is correct and cannot cause a missed page.
```

---

## `security-auditor`

**Model:** claude-opus-4-8 *(Aegis-specific)*
**Tools:** Read, Grep, Glob, Bash, Write, WebFetch, WebSearch

### What it does

The security auditor performs threat modeling using a STRIDE-lite, payload-centric 
approach. It treats every incident artifact as attacker-influenced and
every external integration as a trust-boundary crossing. Findings are written
to `docs/security/YYYY-MM-DD-<feature>.md`. A **CRITICAL** finding produces
verdict `BLOCK` - the PR must not merge until the issue is resolved.

### What it looks for

- **Injection** - untrusted dump/log/stack text reaching a shell, SQL, `eval`,
  or an AI prompt
- **Auth** - unprotected API routes, missing authorization checks
- **Disclosure** - secrets or PII in logs, exception messages, API errors
- **DoS** - unbounded memory on large dumps, missing rate limits, token-budget
  exhaustion
- **Elevation** - automated remediation without `AEGIS_PROD_CONFIRMED` guard

### Threat model output

```
# Threat Model - <feature> - <date>
## Assets & trust boundaries
## Findings
### [CRITICAL|HIGH|MEDIUM|LOW] <title>
- Vector / evidence:
- Impact:
- Mitigation:
## Verdict: PASS | PASS_WITH_FOLLOWUP | BLOCK
```

### When to use it

- Any change touching `backends/debug/` (debugger subprocesses), `backends/ai/`
  (prompts built from payloads), auth routes, secrets handling, external
  integrations, or payload ingestion
- Part of `/pr-review` for any security-adjacent diff
- Run the `security-auditor` before deploying a new integration

### Example prompt

```
Use the security-auditor agent to threat-model the new API route that accepts
raw log payloads from external agents (PR #51).
```

---

## `agent-orchestrator`

**Model:** claude-opus-4-8
**Tools:** Read, Grep, Glob, Bash, TodoWrite, Write (docs only)

### What it does

The orchestrator coordinates **multistep flows** that span several specialist
agents - typically "ticket → merged PR". It decomposes the request, runs
independent steps in parallel, serializes where there are real dependencies,
stops at human decision gates, and hands each task to the right specialist.

### Canonical sequence: ticket → merged PR

1. `app-architect` writes/updates an ADR (gate: human approves)
2. `python-expert` implements on a feature branch
3. `testing-expert` writes tests and reports coverage delta
4. `incident-analyst` and `security-auditor` run **in parallel** (only for relevant surfaces; CRITICAL ⇒ stop)
5. `feature-reviewer` issues LGTM / REQUEST_CHANGES (loops to `python-expert` until LGTM)
6. `background-reviewer` runs background audits
7. `docs-writer` writes docs
8. `docs-updater` updates docs/OpenAPI/docstrings
9. Open PR - never push to `master`

### When to use it

- When a request is large enough that you would otherwise have to manually
  juggle several agents and track state across them
- For greenfield features, complex refactors, or any change with both domain
  and security implications

### When NOT to use it

- For simple one-agent tasks - just call the relevant agent directly
- When you need fine-grained control over each step (call agents individually)

### Example prompt

```
Use the orchestrator agent to take GitHub issue #38 (add S3 export for RCA
reports) all the way from ADR through merged PR.
```

---

## How agents are invoked in Claude Code

In a Claude Code session, there are two ways to use agents:

**Inline delegation** - ask Claude to delegate to a specific agent in your
prompt:
```
Use the coder agent to implement the change described in ADR 0004.
```

**Direct subagent spawn** - Claude Code can spawn an agent as a subagent using
the `Agent` tool internally. You do not need to do anything special; Claude
orchestrates this when you name an agent.

The agent definition files in `.claude/agents/*.md` are picked up
automatically by Claude Code. They define the model, tools, and system prompt
for each agent.

See `tutorial.md` for end-to-end examples of real workflows.
