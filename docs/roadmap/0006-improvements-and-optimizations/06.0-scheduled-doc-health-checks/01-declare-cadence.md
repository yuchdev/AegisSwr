# 01 — Declare the weekly doc-health cadence (mirror `/dep-audit`)

**Parent task:** [06.0 Scheduled Documentation Health Checks](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** [02 — Report only on a finding](02-report-on-finding.md)

## Objective

`/dep-audit` has a weekly cadence declared in three documentation artifacts and
wired through a trigger; the doc-health skills have none. Replicate the exact
same declaration for `/doc-registry` + `/link-check` so the cadence is recorded
where every other recurring task is recorded, and choose the trigger mechanism
subtask 02 will implement.

## The three declarations to add (one-for-one with `/dep-audit`)

1. **Skill frontmatter.** `/dep-audit`'s `description` reads *"Invoke on changes
   to pyproject.toml / uv.lock / requirements.txt, **or on a weekly cadence**, or
   manually as /dep-audit"* (`.claude/skills/dep-audit/SKILL.md:3`). Add the
   matching clause to both doc-health skills:
   - `.claude/skills/doc-registry/SKILL.md` frontmatter `description` (currently
     SKILL.md:3-9) gains "…or on a weekly cadence…".
   - `.claude/skills/link-check/SKILL.md` frontmatter `description` (SKILL.md:3)
     gains the same clause.

2. **`.claude/CLAUDE.md` §12.** The manual's "Recurring / scheduled work" list
   currently has `dep-audit`, `Coverage report`, and `Daily incident-metric
   summary`. Add a bullet:
   > - **doc-health** — weekly; runs `/doc-registry` then `/link-check`, opening
   >   an issue only on a finding (`/doc-health-weekly` loop).

3. **`docs/specs/agentic_fleet_design.md` §12 table.** The canonical "Scheduled /
   recurring tasks (proposed)" table (agentic_fleet_design.md:246-256) has
   columns `Cadence | Task | Mechanism`. Add a row mirroring the dep-audit row's
   form:
   > | Weekly | Documentation health (missing refs + broken anchors) | `/doc-registry` + `/link-check` via `/loop doc-health-weekly`; `doc_link_check.py` hook covers the per-edit path |

## Trigger mechanism (the choice subtask 02 implements)

`/dep-audit` splits its triggering: the `dep_audit.py` **hook** handles the
event-driven (manifest-change) path, and the *weekly* deep run is set up "with
the Claude Code `/schedule` (cron) or `/loop` facilities" (agentic_fleet_design.md:254-256).
The doc-health analogue already has its event-driven half — the
`doc_link_check.py` PostToolUse/Stop hook (`.claude/settings.json:52,66`) runs
`scripts/check_doc_links.py` on every edit and at session end. What is missing is
the **weekly corpus-wide pass**. Choose one, and record the choice here so
subtask 02 builds it:

- **Option A — `/loop doc-health-weekly`** (recommended): a new loop file under
  `.claude/loops/` modelled on `update-docs.md`, rescheduled weekly via
  `ScheduleWakeup` (the mechanism `.claude/loops/README.md:14-18` documents).
  Stays entirely inside the existing fleet tooling, no new infra.
- **Option B — a scheduled GitHub Actions workflow** (`on: schedule: cron`), like
  `ci.yml`'s existing nightly `cron: "0 3 * * *"` (ci.yml:7-9), running the two
  backing scripts and opening an issue on non-zero exit.

Recommendation: **Option A** for parity with `/dep-audit` (which lives in the
`.claude/` fleet, not in CI), falling back to B only if the team wants the pass
to run independent of any agent session.

## Exclusions

- `/doc-xref` is **not** added to the cadence (it is a reactive, single-target
  inbound patcher — see the task README note).
- This subtask only *declares* the cadence and picks the mechanism; the
  find-then-report behaviour and the loop/workflow file itself are subtask 02.
- No `src/` change.

## Test plan

- Documentation/config change — verification is:
  - `python scripts/check_doc_links.py` exits 0 after the §12 table row and the
    `.claude/CLAUDE.md` bullet are added (new cross-references resolve).
  - A `docs-updater` pass confirms the three declarations match `/dep-audit`'s
    wording pattern (so the convention is recognisably the same one).
  - The two skill frontmatters still parse (valid YAML frontmatter, `name` /
    `description` / `invocation` intact).
</content>
