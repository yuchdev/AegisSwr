# 03 — Retire Milestone 0003 Tasks 03.0–07.0

**Parent task:** 01.0 Router Reframing & Milestone 0003 Retirement
**State:** ⬜ Not started
**Depends on:** none (docs-only edit)
**Blocks:** none
**Contracts:** C3 (the reframe this retirement is the corollary of)

## Objective

Discharge **cross-milestone conflict 1**: formally retire the five Milestone 0003
tasks that ADR 0006 §A.3 makes permanently obsolete, so the roadmap stops
misrepresenting intent by leaving them perpetually "Not started."

Milestone 0003 exists to build real LiteLLM-dispatched model routing. ADR 0006
§A.3 declares "Aegis SWR takes no runtime dependency on `litellm`" permanently —
that dispatch path will never be built. Tasks 03.0 (LiteLLM Client), 04.0 (Model
Router), 05.0 (Test Suite), 06.0 (Agent Wiring), 07.0 (Documentation) are
superseded. Tasks 01.0–02.0 (the `agents.yaml` / `RouterConfig` config slice)
**survive**, repurposed by this milestone's Task 01.0 as the role →
harness-session binding table (C3).

## Edit to make

In [docs/roadmap/0003-litellm-routing/status.md](/docs/roadmap/0003-litellm-routing/status.md):

1. In the `## Current status` table, change the **Status** cell of Tasks 03.0,
   04.0, 05.0, 06.0, 07.0 from `⬜ Not started` to
   **`⛔ Superseded by ADR 0006 / Milestone 0007`** (add the legend entry).
2. Add a short note under the table (one or two sentences), mirroring the
   supersession-record style Milestone 0004 used in its `status.md` "Notes &
   decisions": explain that ADR 0006 makes the LiteLLM dispatch path permanently
   dead (all external-model access now goes through harnesses), that these five
   tasks are retired rather than left pending, and that Tasks 01.0–02.0 survive
   repurposed as the role → harness-session binding table — link to
   [Milestone 0007 plan.md §C3](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
   and this task.
3. Do **not** alter the "Decomposition tree (as built)" section or the Tasks
   01.0–02.0 rows — those remain accurate and in force.

## Constraints

- **Docs-only.** No `src/` change; the already-built `router/` config slice is
  untouched by this subtask (it is repurposed by subtasks 01/02, not here).
- Keep the edit minimal and surgical — change the five status cells, add the
  legend entry, add the note. Do not rewrite Milestone 0003's plan.md.
- Run `python scripts/check_doc_links.py docs/` (or `/link-check`) after the edit;
  the new links to Milestone 0007 must resolve.

## Acceptance criteria

- [ ] Milestone 0003 `status.md` marks Tasks 03.0–07.0 "Superseded by ADR 0006 /
      Milestone 0007" with a legend entry.
- [ ] A one/two-sentence supersession note links to this milestone and explains
      the reframe-vs-retire split (01.0–02.0 survive; 03.0–07.0 retired).
- [ ] Tasks 01.0–02.0 rows and the decomposition tree are unchanged.
- [ ] `check_doc_links.py` is clean on the edited file.
