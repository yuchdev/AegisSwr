# .claude/loops - loop programs

Loop programs are **multi-iteration orchestration drivers** stored as Markdown
files. Each file defines a self-contained prompt that can be fired repeatedly via
the `/loop` skill, reading project state from files each iteration to decide what
to do next.

## Invocation

```
/loop implement-subtasks 3.2          # self-paced (model chooses delay)
/loop 5m implement-subtasks 3.2       # fixed 5-minute interval
```

Under the hood, `/loop` fires the prompt text via `ScheduleWakeup`. Each wakeup
re-reads the loop file, checks current state, acts, and reschedules - until the
termination condition is met.

## File format

```yaml
---
name: short-kebab-name
description: one-line summary of what this loop drives
invoke: /loop <name>            # how the user calls it
terminates-when: <condition>    # plain-English stop criterion
---
```

Body: a structured Markdown prompt using H2/H3 sections for each algorithm step.
The last section should explain how the loop relates to skills.

## Available loops

| File                     | Mode | Purpose                                                                                                                                                                                      | Terminates when                                                                                        |
|--------------------------|------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| `implement-subtasks.md`  | —    | Drives one task to completion (resolved from a milestone's `plan.md`, gated on `status.md`), implementing one subtask per iteration                                                          | The target task's row in the milestone `status.md` shows ✅ Complete                                   |
| `update-docs.md`         | scan | No-arg full-corpus audit: builds a `.md` file registry, finds broken cross-references, auto-fixes high-confidence link targets via `docs-updater`, writes a review report for the rest      | `scripts/doc_registry.py` exits 0 (no missing .md refs) and no high-confidence pending items remain   |
| `update-docs.md`         | path | After editing a specific doc, finds and fixes every stale reference to its renamed/removed headings across `docs/` AND `src/` docstrings/comments                                           | `python scripts/check_doc_links.py` exits 0 and no stale heading refs remain                          |

## Token economy (loop-authoring conventions)

A loop re-fires via `ScheduleWakeup` into the **same growing conversation** - it is not N
independent runs. So the cost that compounds iteration-over-iteration is **whatever
permanently lands in the main-loop context**. A subagent's internal reads and reasoning are
discarded with its context; only its final message persists in the parent. Every optimization
below follows from that one asymmetry. `implement-subtasks.md` is the reference implementation
(see its "Per-run state cursor" and "Token-economy invariants" sections).

1. **Resolve once, cache in a state cursor.** State that doesn't change within a run (paths,
   the work queue, resolved IDs) should be derived **once** and persisted to a small JSON
   cursor under `.claude/state/<loop-name>-<arg>.json`, then read (~hundreds of tokens) on
   every subsequent wakeup instead of re-parsing the large source docs. The cursor is a
   *derived cache* - the project files stay authoritative; refresh the cursor when an item
   closes, and delete it when the loop terminates. `.claude/state/` is already git-ignored
   (`.gitignore`), so per-run state never gets committed.

2. **Do first-iteration discovery inside a subagent.** Cold-start resolution that must read big
   files (a 500-line `plan.md`, a long status table) should run in a spawned agent that returns
   **only** the distilled cursor JSON - the file bodies never enter the persistent context.

3. **Read narrow from the main loop.** When the loop itself needs one field, `grep` the single
   row or use `offset`+`limit` to a table; never full-`Read` a large doc. The only justified
   full read is the *current* work item's spec (different each iteration - necessary, not
   repeated, cost).

4. **Delegate, then demand terse returns.** Push reads/analysis into subagents; instruct them
   to return compact structured summaries (files changed, pass/fail, deltas) and to **never
   echo diffs, file bodies, or full logs**. Pass downstream agents **paths and section
   anchors, not pasted text** - pasting bills the same content in both contexts. Report a
   green/PASS gate as a single line; spend tokens on the full matrix only when there is
   something to act on.

5. **Run the minimum gate.** Scope tests to the changed module with `-q` (full suite once, at
   completion - the Stop hook gates session end regardless); skip any quality-gate skill whose
   trigger condition is false rather than spawning an agent that can only find nothing.

6. **Stay in the cache window, but don't rely on it.** A reschedule delay under the 300 s
   prompt-cache TTL (e.g. `270`) lets the cached prefix (system prompt + loop file +
   `CLAUDE.md`) be reused at ~10× lower cost. A single agent step longer than ~5 min blows the
   TTL anyway, so treat the cache as a bonus - the **cursor** is what guarantees cheap
   rediscovery. Keep per-iteration narration terse and lean on `/compact` for long runs.

## Loops vs. skills

|                  | Skills (`.claude/skills/`)                | Loops (`.claude/loops/`)                     |
|------------------|-------------------------------------------|----------------------------------------------|
| **Invocation**   | `/skill-name` - once, by the user         | `/loop name` - repeatedly, self-scheduled    |
| **Scope**        | One atomic task (audit, scaffold, review) | A sequence of tasks across multiple sessions |
| **State**        | Stateless                                 | Stateful via project files                   |
| **Calls**        | Direct actions                            | Often calls skills as sub-steps              |
| **Relationship** | Vocabulary                                | Sentences that use the vocabulary            |

Loops **supplement** skills - a loop invokes skills at the right checkpoint in a
longer sequence. Neither substitutes the other.
