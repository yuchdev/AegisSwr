# 02 — `docs/README.md` + roadmap README sync

**Parent task:** 10.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** none (co-landed at closeout)
**Contracts:** —

## Objective

Keep the two documentation indices current: add the Milestone 0007 row to the
roadmap README's `## Milestones` table and update its decomposition footnote, and
add the matching row to `docs/README.md`'s roadmap table.

> These index edits are also made in the planning pass that creates this milestone
> (so the new milestone is discoverable immediately); this subtask is the closeout
> verification that they are present and correct, plus the config-doc index rows
> for the new `docs/config/` files (subtask 01).

## Scope

- `docs/roadmap/README.md`:
  - Add a `0007 | Harness as the sole LLM gateway | plan.md | status.md` row to the
    `## Milestones` table.
  - Update the decomposition footnote to note Milestone 0007 is decomposed to the
    full task → subtask tree (10 tasks / 44 subtasks).
- `docs/README.md`:
  - Add the `0007-harness-sole-llm-gateway/plan.md` and `status.md` rows to the
    roadmap table, with a one-line description.
  - Add the new `docs/config/` files (`harness-gateway.md`, `mcp-tool-surface.md`,
    `autonomy-stages.md`) to the config-docs index section.
- Run `/doc-registry` + `/link-check` to confirm the indices and all new links
  resolve.

## Acceptance criteria

- [ ] Roadmap README `## Milestones` table has the 0007 row; the decomposition
      footnote names it (10 tasks / 44 subtasks).
- [ ] `docs/README.md` roadmap table has the 0007 plan.md + status.md rows.
- [ ] The new `docs/config/` files are indexed in `docs/README.md`.
- [ ] `/doc-registry` + `check_doc_links.py` clean.
