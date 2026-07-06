# Aegis SWR - Skills Reference

Skills are pre-packaged instruction sets that Claude follows when you invoke a
slash command (`/skill-name args`). Unlike agents (which are autonomous
specialists with their own model and context), skills are instruction scripts
that run **inside your current session**, directing Claude to follow a specific
procedure. Some skills also fan out to agents as sub-steps.

This document covers every skill in `.claude/skills/`, its invocation syntax,
what it does step by step, and when to reach for it.

---

## Quick reference

| Skill | Invocation | Mode | Purpose |
|---|---|---|---|
| `incident-triage` | automatic | auto | Checks lifecycle completeness when you touch investigation-flow code |
| `playbook-validate` | `/playbook-validate <path>` | manual | Validates a playbook or weight file |
| `adr-write` | `/adr-write <title>` | manual | Scaffolds a MADR ADR in `docs/adr/` |
| `pr-review` | `/pr-review [pr or branch]` | manual | Parallel feature+security review |
| `test-gap` | `/test-gap [path]` | manual | Risk-ranked list of missing tests |
| `runbook-write` | `/runbook-write <type>` | manual | Drafts a runbook from the Aegis template |
| `post-mortem` | `/post-mortem [incident-id]` | manual | Blameless post-mortem from git+incident data |
| `dep-audit` | `/dep-audit` (also auto) | manual + auto | CVE scan + licence check |
| `secret-scan` | `/secret-scan [paths]` | manual + auto | Detect hardcoded secrets |
| `link-check` | `/link-check [path]` (also auto) | manual + auto | Validate doc links + heading anchors resolve |
| `doc-xref` | `/doc-xref <target>` | manual | Find/fix inbound references to a doc/heading/symbol |

---

## `incident-triage`

**Invocation:** automatic - triggered when Claude touches files in the
investigation pipeline
**Relevant files:** `core/orchestrator.py`, `core/consensus.py`,
`core/incident_similarity.py`, `core/events.py`, `core/schemas.py`
(Hypothesis, SkepticVerdict, HITLRequest)

### What happens

Runs a structured checklist against the change before it is considered done:

1. **State-machine completeness** - every pipeline state
   (`INITIALIZING → EXTRACTING → PARSING → ANALYZING → STORING`) has a defined
   success exit and a defined failure exit; no state is a dead end.
2. **EventBus coverage** - each state transition emits the correct `DomainEvent`
   so views stay in sync.
3. **Escalation paths** - `ConfidenceLevel.LOW` or a rejected `SkepticVerdict`
   always produces a `HITLRequest`; there is never a silent, weak RCA.
4. **Timeout coverage** - every external call has an explicit timeout.
5. **De-duplication safety** - changes to `incident_similarity.py` don't over-
   or under-suppress real incidents.

Each check is reported as ✓/✗ with a `file:line` citation. Failures produce a
recommendation for `python-expert` and a `testing-expert` regression test suggestion.

### Why it's automatic (not manual)

The lifecycle invariants are easy to break inadvertently during refactors. An
automatic trigger ensures the check happens before code leaves the session.

---

## `playbook-validate`

**Invocation:** `/playbook-validate <path>`

**Example:**
```
/playbook-validate docs/runbooks/memory-access-violation.md
```

### What happens

Validates a remediation playbook (YAML/JSON) or consensus-weight file:

1. **Required fields** - checks that each step has `id`, `description`,
   `action`, `idempotent`, `rollback`, `requires_authorisation`, `timeout`.
2. **Step ordering** - verify the sequence: confirm trigger → contain →
   remediate → verify. No remediation before confirmation.
3. **Idempotency** - any non-idempotent step must document why and how it is
   guarded.
4. **Rollback coverage** - every state-changing step must have a rollback or
   an explicit `rollback: none` with justification.
5. **Authorisation** - production-affecting steps set
   `requires_authorisation: true`.
6. **Weight files** - for `agents.example.json`-style files, each fault class's
   agent weights must sum to 1.0 ± 0.01.

### Output

```
## Playbook Validation - <file>
**Verdict: VALID | INVALID**
### Errors (blocking)
### Warnings
### Coverage
- steps: N | with rollback: N | idempotent: N | needs-auth: N
```

### When to use it

Before trusting a playbook to drive any automated remediation, and after every
edit to `agents.example.json`.

---

## `adr-write`

**Invocation:** `/adr-write <title>`

**Examples:**
```
/adr-write add-otlp-log-adapter
/adr-write replace-sqlite-with-postgres-as-primary-store
```

### What happens

Scaffolds a new Architecture Decision Record:

1. Determines the next sequence number by listing `docs/adr/` and incrementing
   the highest `NNNN-` prefix.
2. Runs `git log --oneline -10` and (if `gh` is authenticated) lists open
   issues to seed the **Context** section.
3. Creates `docs/adr/NNNN-<kebab-title>.md` using the MADR template with
   status `Proposed` and today's date.
4. Adds an index line to `docs/README.md`.

### The MADR sections scaffolded

- Title, Status, Date, Deciders
- Context and Problem Statement *(seeded from git log)*
- Decision Drivers
- Considered Options (with placeholder labels)
- Decision Outcome with consequences
- Pros and Cons per option

### What it does NOT do

It scaffolds and seeds - it does not make the decision. The `app-architect` agent
(or a human) fills in the options and writes the outcome. The skill is
deliberately a scaffold, not a generator.

### When to use it

Before starting any non-trivial change. Even if the decision is obvious, having
an ADR provides a paper trail for future engineers and for the `python-expert`/`testing-expert`
agents to reference.

---

## `pr-review`

**Invocation:** `/pr-review [pr-number | branch]`

**Examples:**
```
/pr-review 47
/pr-review feat/otlp-adapter
/pr-review                   ← reviews current working-tree diff
```

### What happens

Runs a **parallel** review using two specialist agents:

1. **Resolves the diff** - fetches from GitHub (PR number), runs `git diff
   main...<branch>`, or uses the current working-tree diff.
2. **Fans out in parallel** - spawns `feature-reviewer` and `security-auditor`
   simultaneously, both given the same diff scope and file list.
3. **Synthesises** their outputs into a single unified review comment.

### Output shape

```
## Aegis PR Review - <PR/branch>
**Merge verdict: APPROVE | REQUEST_CHANGES | BLOCK (security)**

### Feature review (feature-reviewer)
### Security review (security-auditor)
### Combined blocking items
### Non-blocking suggestions
```

Verdict rules:
- Any CRITICAL security finding → **BLOCK** regardless of feature verdict
- Any feature blocking issue → at minimum **REQUEST_CHANGES**

### When to use it

Before merging any PR. Replaces running `feature-reviewer` and
`security-auditor` separately - the two reviews run in parallel so total time
is roughly that of one review.

---

## `test-gap`

**Invocation:** `/test-gap [path]`

**Examples:**
```
/test-gap
/test-gap src/aegis_swr/core/consensus.py
/test-gap src/aegis_swr/backends/log/
```

### What happens

1. Runs `uv run pytest tests/unit/ -q --cov=aegis_swr --cov-report=term-
   missing` (scoped to the target path if given).
2. Spawns the `testing-expert` agent with the coverage output. The agent maps uncovered
   lines to behaviours and **risk-ranks** them:
   - **P0** - consensus/skeptic logic, payload parsing, escalation/HITL paths,
     security-relevant branches
   - **P1** - backend strategies, orchestrator transitions, schema validation
   - **P2** - CLI/view formatting, logging helpers

### Output

```
## Test Gap - <target> (coverage: NN%)
### P0 - must test
- path:line-range - <untested behaviour> - <why risky> - <suggested test>
### P1 - should test
### P2 - nice to have
```

The skill then offers to have `testing-expert` write the P0 tests immediately.

### When to use it

- When inheriting a module and wanting to know where to start with tests
- After a large refactor to verify coverage did not drop
- On every PR as part of the `/pr-review` flow

---

## `runbook-write`

**Invocation:** `/runbook-write <incident-type>`

**Examples:**
```
/runbook-write memory-access-violation
/runbook-write deadlock
/runbook-write resource-exhaustion
/runbook-write log-forensics-anomaly
```

### What happens

1. Cross-references the incident type against `agents.example.json`
   (consensus weights), `core/fault_codes.py`, and `IncidentMode` so the
   runbook matches real product classifications.
2. Writes `docs/runbooks/<incident-type>.md` using the Aegis runbook template.
3. Adds an index line to `docs/README.md`.

### Template sections

- Fault class / mode, severity default, owner / escalation
- **Detection signals** - how Aegis surfaces this in the UI/events
- **Triage (first 5 minutes)** - numbered steps with expected results
- **Investigation** - which analysis agents dominate, which RCAReport fields
  to read first
- **Mitigation** - idempotency, rollback, `AEGIS_PROD_CONFIRMED` note
- **Escalation** - when to raise a HITLRequest / page on-call
- **Verification & resolution** - confirming close and moving to post-mortem
- **Related** - ADRs, playbooks, prior post-mortems

### When to use it

When a new fault class or `IncidentMode` is added, or when an on-call engineer
reports a gap in existing operational knowledge.

---

## `post-mortem`

**Invocation:** `/post-mortem [incident-id]`

**Examples:**
```
/post-mortem INC-2024-0112
/post-mortem                 ← uses most recent incident in storage
```

### What happens

Guides a **blameless** post-mortem (blameless = focus on systems, never on
individuals):

1. **Timeline reconstruction** - `git log` around the incident window +
   queries stored `RCAReport`s via the `postgres`/`sqlite` MCP for detection
   time, consensus outcome, `SkepticVerdict`, `ConfidenceLevel`, and any
   `HITLRequest`.
2. **Five whys** - iterative drill from symptom to root cause with evidence at
   each level.
3. **Contributing factors** - what made detection/diagnosis/remediation slower.
4. **Action items** - concrete, each with an owner routed to the right agent:
   code fixes → `python-expert`, tests → `testing-expert`, docs/runbook updates → `docs-updater`, design
   changes → `app-architect`.

### Output location

`docs/post-mortems/YYYY-MM-DD-<incident-id>.md`

### When to use it

After any incident that was mitigated in production, regardless of severity.
Even a near-miss is worth a brief post-mortem to capture the learning.

---

## `dep-audit`

**Invocation:** `/dep-audit`
**Also triggered automatically** by `dep_audit.py` hook when `pyproject.toml`,
`uv.lock`, or `requirements*.txt` changes (advisory-only automatic pass;
the full skill is the authoritative version).

### What happens

1. **CVE scan** - `uv run pip-audit --progress-spinner off`; lists package,
   version, CVE/GHSA id, severity, and fixed version.
2. **Outdated pins** - `uv tree --outdated`; flags majors behind with
   security relevance.
3. **Licence audit** - enumerates direct dependencies, identifies each licence,
   flags GPL/AGPL or unknown-licence packages.
4. **Report** - spawns `background-reviewer` to compile findings into
   `docs/reviews/YYYY-MM-DD-dep-audit.md` with severities and recommended
   version bumps.

### When to use it

- Weekly (or set up as a scheduled cron - see [agentic_fleet_design.md](/docs/specs/agentic_fleet_design.md))
- When adding a significant number of new dependencies
- Before any external release

---

## `secret-scan`

**Invocation:** `/secret-scan [paths]`
**Also runs automatically** as a `PreToolUse` hook on every Write/Edit/MultiEdit
- it **blocks** the write if a secret is found (exit code 2).

**Examples:**
```
/secret-scan                        ← scans changed/untracked files
/secret-scan src/aegis_swr/config/  ← scans a directory
/secret-scan src/aegis_swr/backends/ai/anthropic_provider.py
```

### Detection patterns

The scanner detects (not exhaustive):
- AWS access key ids (`AKIA…`)
- Anthropic API keys (`sk-ant-…`)
- OpenAI API keys (`sk-…`)
- Google API keys (`AIza…`)
- GitHub tokens (`ghp_`, `ghs_`, `ghr_`, `ghu_`, `gho_`)
- Slack tokens (`xox…`)
- Private key PEM blocks (`-----BEGIN … PRIVATE KEY-----`)
- Generic assignments (`password = "…"`, `token = "…"`, `api_key = "…"`)
- Postgres connection strings with embedded passwords

### Allowlisted (not flagged)

Lines containing obvious placeholder markers are skipped: `example`,
`placeholder`, `your-`, `your_`, `changeme`, `dummy`, `xxxx`, `${`, `<your`,
`redacted`, `fake`, `test`.

### What to do when it fires

1. Remove the credential from the file
2. If it was already committed, rotate the credential immediately
3. Replace with a `${VAR_NAME}` reference (resolved from environment; see
   `.mcp.json` for the pattern)
4. If the commit is already in remote history, use `git filter-repo` to rewrite
   history (ask the team before doing this)

### When to use it manually

Before a first PR, to sweep all files you changed. The automatic hook covers
new writes, but the manual scan catches credentials that already existed.

---

## `link-check`

**Invocation:** `/link-check [path ...]`
**Also runs automatically** via the `doc_link_check` hook (PostToolUse on Markdown
edits, and at session Stop for docs changed in the working tree) - advisory,
non-blocking.

### What happens

1. Runs `python scripts/check_doc_links.py [paths]` - the single source of truth for
   link/anchor integrity (the hook calls the same script).
2. Reports each dangling relative link (`missing file`) and missing heading anchor
   (`missing anchor`) as `file:line`.
3. You fix each (correct the path, update the GitHub-style anchor, or repoint) and
   re-run until it exits `0`. For a renamed heading, also run `/doc-xref` to fix
   *inbound* links.

### Scope

`docs/**`, repo-root `*.md`, and `.claude/**` by default; or only the paths you pass.
External links (http/https/mailto) and fenced code blocks are ignored.

### When to use it

After editing, splitting, merging, or renaming any doc or heading - and as the final
step of any `docs-updater`-agent task.

---

## `doc-xref`

**Invocation:** `/doc-xref <target>` - a doc path, heading text/anchor, or public symbol

### What happens

Finds every **inbound** reference to the target across both `docs/**` (+ repo-root
`*.md`, `.claude/**`) and `src/**` / `tests/**` docstrings & comments, then updates
them so a rename/move/split/rewording propagates everywhere instead of leaving stale
pointers. Complements `/link-check` (which validates a file's *outbound* links).

### Steps

1. `git grep -nF "<target>"` for the path / anchor / symbol (and any old name).
2. Update each hit; `git mv` when renaming a whole file so history follows.
3. Refresh the `docs/README.md` registry line if a file changed.
4. Verify with `/link-check`.

### When to use it

**Before** renaming/moving/splitting a doc, heading, or public symbol - the inbound
half of reference integrity that the (outbound) link checker can't see.

---

## How skills differ from agents

| | Skills | Agents |
|---|---|---|
| Lives in | `.claude/skills/<name>/SKILL.md` | `.claude/agents/<name>.md` |
| Runs on | Current session model | Own model (as defined in front-matter) |
| Invoked by | `/skill-name` or automatic trigger | Explicit delegation in prompt |
| Context | Shares session context | Gets a fresh context window |
| Produces | Output in current conversation | Output returned to orchestrating session |
| Good for | Structured procedures, scaffolding | Autonomous specialist work |

In practice: use a skill for a well-defined, short procedure. Use an agent for
work that requires deep reasoning, an independent perspective, or a different
model tier.
