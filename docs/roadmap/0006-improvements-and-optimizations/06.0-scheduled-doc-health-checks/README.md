# Task 06.0 — Scheduled Documentation Health Checks

**Parent milestone:** [Milestone 0006 — Improvements & Optimizations](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
**Status:** ⬜ Not started

## Scope

The doc-health skills — `/doc-registry` (`.claude/skills/doc-registry/SKILL.md`),
`/doc-xref` (`.claude/skills/doc-xref/SKILL.md`), and `/link-check`
(`.claude/skills/link-check/SKILL.md`) — only run when someone remembers to type
the slash command, typically right after a large restructuring. `/dep-audit`,
by contrast, has a documented **weekly cadence**. This task gives the doc-health
skills the same recurring cadence `/dep-audit` already has, reporting only on a
finding (open an issue / post to the docs channel) and staying silent when clean.

### Re-verification note — mirror the mechanism that actually exists

`plan.md`'s Task 06.0 proposed "add a scheduled cron entry (mirroring
`/dep-audit`'s)." There is **no OS crontab** in this repo. The `/dep-audit`
cadence is expressed through four concrete, co-operating artifacts — these are
exactly what this task mirrors for the doc-health skills, not an invented cron:

| Artifact | How `/dep-audit` uses it | Evidence |
|----------|--------------------------|----------|
| Skill frontmatter `description` | declares the cadence in prose ("…or on a weekly cadence, or manually as /dep-audit") | `.claude/skills/dep-audit/SKILL.md:3` |
| `.claude/CLAUDE.md` §12 bullet | lists the cadence in the agent operating manual | `.claude/CLAUDE.md` §12 "dep-audit — weekly and on manifest change" |
| `docs/specs/agentic_fleet_design.md` §12 table | the canonical "Scheduled / recurring tasks" table (Cadence \| Task \| Mechanism) | agentic_fleet_design.md:246-256 |
| A deterministic trigger | the `dep_audit.py` PostToolUse hook fires the *advisory* run on manifest change; the weekly deep run is set up "with the Claude Code `/schedule` (cron) or `/loop` facilities" | `.claude/hooks/dep_audit.py`; agentic_fleet_design.md:254-256 |

The doc-health equivalents already partly exist: the `doc_link_check.py`
PostToolUse/Stop hook (`.claude/settings.json:52,66`) is the event-driven
analogue of `dep_audit.py`, and `/loop update-docs` (`.claude/loops/update-docs.md`)
is a ready-made iterative driver. What is missing is the **scheduled, quiet-when-
clean weekly pass** and its declaration in the three documentation artifacts
above. This task adds exactly that, mirroring the `/dep-audit` pattern
one-for-one.

> Note on `/doc-xref`: `plan.md`'s proposed shape names only `/doc-registry` +
> `/link-check` (file-existence + anchor/link resolution — the two corpus-wide
> health checks). `/doc-xref` is a *targeted* inbound-reference patcher for a
> single renamed target (`.claude/skills/doc-xref/SKILL.md`), not a corpus scan,
> so it is intentionally **not** part of the scheduled pass — it is invoked
> reactively during a rename, not on a cadence. This task keeps the scheduled
> pass to `/doc-registry` then `/link-check`, matching the plan.

## Subtasks

| #  | Name                                                         | Document                                                            | Status         |
|----|-------------------------------------------------------------|--------------------------------------------------------------------|----------------|
| 01 | Declare the weekly doc-health cadence (mirror `/dep-audit`)  | [Declare the cadence](01-declare-cadence.md)                        | ⬜ Not started |
| 02 | Quiet-when-clean, loud-on-finding reporting                  | [Report only on a finding](02-report-on-finding.md)                 | ⬜ Not started |

**Sequencing.** 01 declares *that* the cadence exists and where (the three doc
artifacts + a `/loop` or scheduled-workflow trigger). 02 defines the *behaviour*
of the scheduled run — how it decides there is a finding and how it reports (issue
vs docs-channel) without noise when clean. 01 → 02; 02 depends on 01's chosen
trigger mechanism.

## Key constraints

- **Mirror `/dep-audit`, do not invent a parallel mechanism.** The cadence lives
  in the same three places `/dep-audit`'s does (skill frontmatter, `.claude/CLAUDE.md`
  §12, `agentic_fleet_design.md` §12 table) plus a `/schedule` or `/loop` trigger
  — not a new bespoke scheduler.
- **Quiet when clean.** A green run (both skills report their all-clear:
  `scripts/doc_registry.py` prints *"All .md cross-references resolve correctly."*
  and `scripts/check_doc_links.py` exits `0`) opens **no** issue and posts
  nothing. Noise on every clean run would train reviewers to ignore it.
- **Reuse the existing scripts.** `/doc-registry` is backed by
  `scripts/doc_registry.py` and `/link-check` by `scripts/check_doc_links.py`
  (the same checker the `doc_link_check` hook runs) — the scheduled pass calls
  these, it does not reimplement link checking.
- No `src/` or product change — this is `.claude/` fleet-config + docs only.
- If the pass opens a GitHub issue, that action routes through the `github_audit.py`
  PostToolUse hook's audit trail (`.claude/CLAUDE.md` §11) like every other
  GitHub action.

## Files created or modified by this task

```
.claude/skills/doc-registry/SKILL.md   ← frontmatter `description` gains the
                                          weekly-cadence clause (mirrors dep-audit)
.claude/skills/link-check/SKILL.md      ← same cadence clause in its description

.claude/CLAUDE.md                       ← §12 gains a "doc-health — weekly"
                                          recurring-work bullet

docs/specs/agentic_fleet_design.md      ← §12 "Scheduled / recurring tasks" table
                                          gains a doc-health row (Cadence |
                                          Task | Mechanism)

.claude/loops/doc-health-weekly.md      ← NEW (subtask 02): the scheduled driver
                                          (or a scheduled GitHub workflow), running
                                          /doc-registry then /link-check and
                                          reporting only on a finding
```
</content>
