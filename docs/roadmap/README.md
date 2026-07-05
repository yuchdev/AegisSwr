# Aegis SWR Roadmap

Planning and progress tracking for Aegis SWR, organised as a three-tier
hierarchy: **Milestone → Task → Subtask**.

## Hierarchy & vocabulary

| Tier | Meaning | Lives in |
|------|---------|----------|
| **Milestone** | A large, strategic initiative / development direction (e.g. the generic implementation effort). | A folder `docs/roadmap/{NNNN}-{milestone-slug}/`. |
| **Task** | One deliverable unit of a milestone (e.g. "AWS Bedrock Backend"). Listed in the milestone's `## Tasks` table. | A subfolder `…/{TT.t}-{task-slug}/` with a `README.md`. |
| **Subtask** | An atomic, implementable spec (one file, one set of classes/tests). Listed in the task's `## Subtasks` table. | A file `…/{TT.t}-{task-slug}/{NN}-{subtask-slug}.md`. |

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
- Avoid "Phase" for these tiers - it is reserved for the product-vision phases in
  [docs/roadmap/roadmap.md](/docs/roadmap/roadmap.md) (usually require months) and would otherwise be ambiguous.

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

| #    | Milestone                                           | Spec                                                          | Status                                                           |
|------|-----------------------------------------------------|---------------------------------------------------------------|------------------------------------------------------------------|
| 0001 | Generic implementation (backends, MAS, CLI, …)      | [plan.md](/docs/roadmap/0001-generic-implementation/plan.md)  | [status.md](/docs/roadmap/0001-generic-implementation/status.md) |
| 0002 | Forensic agents (specialist panel + synthesis tier) | [plan.md](/docs/roadmap/0002-forensic-agents/plan.md)         | [status.md](/docs/roadmap/0002-forensic-agents/status.md)        |
| 0003 | LiteLLM model-router integration                    | [plan.md](/docs/roadmap/0003-litellm-routing/plan.md)         | -                                                                |
| 0004 | Code Intelligence Layer                             | [plan.md](/docs/roadmap/0004-code-intelligence-layer/plan.md) | ⛔ Superseded by [0005](/docs/roadmap/0004-code-intelligence/plan.md)   |
| 0005 | OpenClaude integration (Code Intelligence)          | [plan.md](/docs/roadmap/0004-code-intelligence/plan.md)              | [status.md](/docs/roadmap/0004-code-intelligence/status.md)             |

> Milestones 0001-0003 are decomposed into the full task → subtask tree; 0005
> is decomposed to the task level (each task has a `README.md`; numbered subtask
> specs are deferred). Milestone 0004 is **superseded by 0005** and frozen as a
> single notice document.
