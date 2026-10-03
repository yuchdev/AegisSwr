# 04 — Cross-milestone amendment notes

**Parent task:** 10.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** Tasks 01.0 (subtask 03), 04.0, 03.0 (the events the note points at)
**Contracts:** C3, C10

## Objective

Land the cross-milestone amendment this milestone owes to Milestone 0006, and
verify the Milestone 0003 retirement pointer (owned by Task 01.0 subtask 03)
resolves — so no reader chases the dead `RouterCallCompleted` event or the retired
LiteLLM dispatch tasks.

## Scope

### Milestone 0006 `plan.md` Task 05.0 amendment (this subtask owns the edit)

[Milestone 0006 plan.md](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
Task 05.0 ("Cost & Latency Telemetry for Router/Harness Events") proposes
subscribing to `RouterCallCompleted` — an event of the **never-built** Model Router
(Milestone 0003 Task 04.0, retired by this milestone). Add a **short amendment note**
(one or two sentences, not a rewrite) to that Task 05.0 section:

> **Amended (Milestone 0007 / ADR 0006).** `RouterCallCompleted` belongs to the
> LiteLLM Model Router retired by ADR 0006 (see
> [Milestone 0007](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)); it will
> never be emitted. Telemetry should subscribe instead to the per-role
> harness-session `*.completed` / adapter-completion events this gateway milestone
> introduces (token/cost flow through `CodeResult.token_estimate`, C10) alongside
> the existing backend `*.completed` events.

Do **not** otherwise touch Milestone 0006's scope — its acceptance criteria state
it does not touch `harness/`/`code_intel/`, which this milestone does; the two are
independent, the note is only a pointer.

### Milestone 0003 retirement pointer (verify; edit owned by Task 01.0 subtask 03)

Confirm Task 01.0 subtask 03's edit to
[Milestone 0003 status.md](/docs/roadmap/0003-litellm-routing/status.md) is present
(Tasks 03.0–07.0 marked "Superseded by ADR 0006 / Milestone 0007") and that its
links to this milestone resolve under `check_doc_links.py`.

## Constraints

- The Milestone 0006 edit is **additive and minimal** — one amendment note in the
  Task 05.0 section; no change to its acceptance criteria or other tasks.
- Do **not** touch Milestone 0001 or 0002 (unrelated/historical).
- `check_doc_links.py` clean on both edited milestone files.

## Acceptance criteria

- [ ] Milestone 0006 `plan.md` Task 05.0 carries the one/two-sentence amendment note
      pointing at the per-role harness-session completion events (C10).
- [ ] Milestone 0006's scope, acceptance criteria, and other tasks are untouched.
- [ ] Milestone 0003's retirement edit (Task 01.0 subtask 03) is present and its
      links resolve.
- [ ] Milestones 0001/0002 are untouched.
- [ ] `check_doc_links.py` clean on both files.
