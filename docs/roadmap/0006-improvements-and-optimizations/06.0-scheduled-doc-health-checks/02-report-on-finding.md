# 02 — Quiet-when-clean, loud-on-finding reporting

**Parent task:** [06.0 Scheduled Documentation Health Checks](README.md)
**State:** ⬜ Not started
**Depends on:** [01 — Declare the cadence](01-declare-cadence.md) (needs the
chosen trigger mechanism)
**Blocks:** none

## Objective

Build the scheduled driver that runs `/doc-registry` then `/link-check` weekly and
reports **only** when there is a finding — opening a GitHub issue (or posting to
the docs channel), and staying completely silent on a clean run. A pass that
posts on every clean week trains reviewers to ignore it; the value is a
notification that means "something is actually broken."

## The clean/dirty signal (grounded in the backing scripts)

Both skills wrap scripts with explicit all-clear outputs — use these as the
machine-readable signal, not log scraping:

- `/doc-registry` → `scripts/doc_registry.py`. Clean when its loop-termination
  condition is met: it "exits 0 (no missing .md refs)"
  (`.claude/loops/update-docs.md` termination column) and prints *"All .md
  cross-references resolve correctly."* (`.claude/skills/doc-registry/SKILL.md:60`).
- `/link-check` → `scripts/check_doc_links.py`. Clean when it "exits `0`"
  (`.claude/skills/link-check/SKILL.md:36`); the same checker the `doc_link_check`
  hook runs, so a scheduled failure matches what the hook would have caught.

Decision rule: **clean iff both scripts exit 0**. Any non-zero exit (missing
file, broken anchor) is a finding.

## Implementation approach (for the chosen mechanism)

### If Option A — `/loop doc-health-weekly` (recommended)

Add `.claude/loops/doc-health-weekly.md`, a loop file in the format
`.claude/loops/README.md:20-31` defines, modelled on `update-docs.md`:

```yaml
---
name: doc-health-weekly
description: Weekly corpus doc-health pass; opens an issue only on a finding.
invoke: /loop doc-health-weekly
terminates-when: never (reschedules weekly) — or when disabled by the operator
---
```

Body algorithm, each wakeup:
1. Run `python scripts/doc_registry.py` then `python scripts/check_doc_links.py`,
   capturing exit codes (do **not** auto-fix — this pass reports, it does not
   mutate docs; `/loop update-docs` is the separate auto-fix driver).
2. If both exited 0: write one terse "clean" line to `.claude/logs/` for the audit
   trail (`.claude/CLAUDE.md` §11) and reschedule ~1 week out via `ScheduleWakeup`.
   Open nothing.
3. If either failed: open a single GitHub issue titled e.g. *"Doc-health: N
   broken references / anchors (week of <date>)"* with the findings list, label
   `docs`, then reschedule. The `gh issue` action is already permitted
   (`.claude/settings.json:15`) and is logged by `github_audit.py`
   (`.claude/settings.json:57-58`).
4. Dedupe: if an open `docs`-labelled doc-health issue already exists, comment on
   it rather than opening a duplicate.

Follow the loop token-economy conventions (`.claude/loops/README.md:41-82`):
run the two scripts, report a green pass as a single line, and only spend tokens
enumerating findings when there are some.

### If Option B — scheduled GitHub Actions workflow

A `.github/workflows/doc-health.yml` with `on: schedule: cron: "0 6 * * 1"`
(weekly Monday) running the two scripts; on non-zero exit, `gh issue create` the
findings (quiet on success because the job simply passes). Use `uv sync --locked`
if [Task 04.0](/docs/roadmap/0006-improvements-and-optimizations/04.0-ci-supply-chain-integrity/README.md)
has landed, for lockfile consistency with the other workflows.

## Constraints

- **No auto-fixing** in the scheduled pass — it reports only. Auto-fix stays the
  domain of the human-driven `/loop update-docs`. Conflating them would let a
  scheduled job rewrite docs unreviewed.
- **No incident payload / secrets** in issue titles or bodies — doc-health deals
  only with file paths and anchor slugs, but the issue text must still pass the
  secret-scan discipline (`.claude/CLAUDE.md` §3).
- Quiet-when-clean is mandatory (see Objective).

## Test plan

- Config/driver change — verification:
  - **Dirty-path proof**: on a scratch branch, introduce a deliberately broken
    `[text](/docs/does-not-exist.md)` link, run the pass manually, and confirm it
    detects the finding and would open exactly one issue (dry-run / `--what-if`
    the `gh` call). Remove the broken link.
  - **Clean-path proof**: on a clean corpus, run the pass and confirm it opens
    nothing and writes only the single audit-log line.
  - **Dedupe proof**: with an open `docs` doc-health issue present, confirm a
    second finding comments rather than opening a duplicate.
  - `scripts/check_doc_links.py` over the new loop/workflow file exits 0.
</content>
