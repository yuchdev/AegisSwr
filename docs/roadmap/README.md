# Aegis SWR Roadmap

Planning and progress tracking for Aegis SWR, organised as a three-tier
hierarchy: **Milestone → Task → Subtask**.

## Hierarchy & vocabulary

| Tier          | Meaning                                                                                                       | Lives in                                                |
|---------------|---------------------------------------------------------------------------------------------------------------|---------------------------------------------------------|
| **Milestone** | A large, strategic initiative / development direction (e.g. the generic implementation effort).               | A folder `docs/roadmap/{NNNN}-{milestone-slug}/`.       |
| **Task**      | One deliverable unit of a milestone (e.g. "AWS Bedrock Backend"). Listed in the milestone's `## Tasks` table. | A subfolder `…/{TT.t}-{task-slug}/` with a `README.md`. |
| **Subtask**   | An atomic, implementable spec (one file, one set of classes/tests). Listed in the task's `## Subtasks` table. | A file `…/{TT.t}-{task-slug}/{NN}-{subtask-slug}.md`.   |

A *subtask* is part of a *task*; a *task* is part of a *milestone*.

## File & folder convention

```
docs/roadmap/
  README.md                              ← this index + convention
  {NNNN}-{milestone-slug}/               ← MILESTONE
    plan.md                              ← milestone spec; opens with a `## Tasks` table
    status.md                            ← progress tracker (optional); `## Current status` table
    {TT.t}-{task-slug}/                  ← TASK
      README.md                          ← task spec; opens with a `## Subtasks` table
      {NN}-{subtask-slug}.md             ← SUBTASK spec
```

- `{NNNN}` - zero-padded milestone number (`0001`, `0002`, …).
- `{TT.t}` - task number, carried from the milestone's `## Tasks` table (e.g. `03.2`, `06.1`, `08.0`).
- `{NN}` - zero-padded subtask order (`01`, `02`, …).
- Slugs are kebab-case.

### Heading vocabulary

- A milestone's `plan.md` lists its tasks under a `## Tasks` heading (table column: `Task`).
- A task's `README.md` lists its subtasks under a `## Subtasks` heading.

### Linking convention

When a document references another **specific** document, use an
absolute-from-repo-root Markdown link:

```
[docs/roadmap/0001-generic-implementation/plan.md](/docs/roadmap/0001-generic-implementation/plan.md)
```

- Always a leading `/` (repo root), never relative `../../` chains.
- **Template** paths (containing `{` / `}`, e.g. `` `{NN}-{subtask-slug}.md` ``) stay as
  backtick code spans, not links.
- Run `python scripts/check_doc_links.py docs/` (or the `/link-check` skill) to verify every
  link target and `#heading-anchor` resolves. The `doc_link_check` hook runs it on edits.

## Milestones

| #    | Milestone                                           | Spec                                                          | Status                                                               |
|------|-----------------------------------------------------|---------------------------------------------------------------|----------------------------------------------------------------------|
| 0001 | Generic implementation (backends, MAS, CLI, …)      | [plan.md](/docs/roadmap/0001-generic-implementation/plan.md)  | [status.md](/docs/roadmap/0001-generic-implementation/status.md)     |
| 0002 | Forensic agents (specialist panel + synthesis tier) | [plan.md](/docs/roadmap/0002-forensic-agents/plan.md)         | [status.md](/docs/roadmap/0002-forensic-agents/status.md)            |
| 0003 | LiteLLM model-router integration                    | [plan.md](/docs/roadmap/0003-litellm-routing/plan.md)         | -                                                                    |
| 0004 | OpenClaude integration (Code Intelligence)          | [plan.md](/docs/roadmap/0004-code-intelligence/plan.md)       | [status.md](/docs/roadmap/0004-code-intelligence/status.md)         |
| 0005 | Code Intelligence harness & multi-backend support   | [plan.md](/docs/roadmap/0005-harness-backends/plan.md)        | [status.md](/docs/roadmap/0005-harness-backends/status.md)          |
| 0006 | Improvements & optimizations (quality/operability)  | [plan.md](/docs/roadmap/0006-improvements-and-optimizations/plan.md) | [status.md](/docs/roadmap/0006-improvements-and-optimizations/status.md) |
| 0007 | Harness as the sole LLM gateway                      | [plan.md](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md) | [status.md](/docs/roadmap/0007-harness-sole-llm-gateway/status.md) |
| 0008 | Distributed secure execution (cross-platform sandbox workers) | [plan.md](/docs/roadmap/0008-distributed-secure-execution/plan.md) | [status.md](/docs/roadmap/0008-distributed-secure-execution/status.md) |

> Milestones 0001-0004 and 0007 are decomposed into the full task → subtask tree;
> Milestones 0005 and 0008 are at task-level granularity (subtask decomposition is
> a later pass; for 0008 that pass is gated on ADR 0007's `cluster/` package being
> built).
> Milestone 0006 is fully decomposed into the task → subtask tree — all six
> tasks, 30 subtasks total (Task 01.0: 14; 02.0: 6; 03.0: 3; 04.0: 2; 05.0: 3;
> 06.0: 2).
> Milestone 0004 supersedes an earlier, cancelled Code Intelligence Layer
> design (its plan document has been removed; see
> [0004/status.md](/docs/roadmap/0004-code-intelligence/status.md#notes--decisions)
> for the decision record).
> Milestone 0007 implements [ADR 0006](/docs/adr/0006-harness-as-sole-llm-gateway.md)
> (roadmap and ADR numbers are independent sequences; roadmap number 0006 was
> already taken by the improvements milestone) and retires Milestone 0003's
> LiteLLM-dispatch tasks 03.0-07.0 (see
> [0003/status.md](/docs/roadmap/0003-litellm-routing/status.md)).
> Milestone 0008 implements [ADR 0008](/docs/adr/0008-distributed-secure-execution-sandbox.md)
> (numbers coincide here but the sequences remain independent) and was extracted
> from Milestone 0001's former Task 9 ("Secure Code Sandbox"), expanding it from a
> local patch-compile check into a cross-instance, cross-platform distributed
> execution architecture that **extends ADR 0007's `cluster/` subsystem**.
