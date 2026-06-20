# .claude/loops - loop programs

Loop programs are **multi-iteration orchestration drivers** stored as Markdown
files. Each file defines a self-contained prompt that can be fired repeatedly via
the `/loop` skill, reading project state from files each iteration to decide what
to do next.

## Invocation

```
/loop implement-phases          # self-paced (model chooses delay)
/loop 5m implement-phases       # fixed 5-minute interval
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

| File                  | Purpose                                                                                                                                     | Terminates when                                                              |
|-----------------------|---------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| `implement-phases.md` | Drives sequential phase implementation from `agentic_implementation_plan.md`, one phase per iteration                                       | All phases in `implementation_status.md` show ✅ Complete                     |
| `update-docs.md`      | After editing a doc file, finds and fixes every stale reference to its renamed/removed sections - across docs/ AND src/ docstrings/comments | `python scripts/check_doc_links.py` exits 0 and no stale heading refs remain |

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
