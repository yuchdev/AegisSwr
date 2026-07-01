# Subtask set 0001-11.0 — Documentation

Atomic decomposition of task **11 Documentation** from
[`docs/roadmap/0001-generic-implementation/plan.md`](/docs/roadmap/0001-generic-implementation/plan.md).
Progress is tracked in
[`docs/roadmap/0001-generic-implementation/status.md`](/docs/roadmap/0001-generic-implementation/status.md).

## Goal

Establish complete, accurate source-of-truth documentation across all `docs/`
tracks so that:

- the `docs-updater` agent can maintain it autonomously after code changes
- new contributors can be onboarded without asking engineers for context
- the `.claude/` fleet operating manual stays in sync with the actual agents, skills, and loops in use.

This is a **demotion from milestone** — documentation was deferred from the
original 10-task plan because it depends on all other tasks having stabilised
their APIs and conventions. It runs after Task 10 (Testing & Hardening).

## Scope

Two parallel tracks:

- **`docs/`** — user- and developer-facing documentation (dev guides, agent
  references, config, runbooks, security, test strategy, reviews).
- **`.claude/`** — internal fleet operating manual (agent definitions, skills,
  hooks, loops, and [CLAUDE.md](/.claude/CLAUDE.md) files).

## Subtasks

| Track  | Deliverable                    | Status         | Notes                                           |
|--------|--------------------------------|----------------|-------------------------------------------------|
| Claude | Agents                         | ✅ Complete     | All agent definitions complete.                 |
| Claude | Hooks                          | ✅ Complete     | —                                               |
| Claude | Loops                          | 🔶 In progress | Need documentation update and background review |
| Claude | Skills                         | ✅ Complete     | —                                               |
| Docs   | ADR                            | ✅ Complete     | Review complete.                                |
| Docs   | Agent (`docs/agent/agents.md`) | ⬜ Not started  | —                                               |
| Docs   | Config (`docs/config/`)        | ⬜ Not started  | —                                               |
| Docs   | Dev (`docs/dev/`)              | 🔶 In progress | Python style rules partial; others not started. |
| Docs   | Post Mortems                   | ✅ Complete     | Review complete.                                |
| Docs   | Reviews (`docs/reviews/`)      | ⬜ Not started  | —                                               |
| Docs   | Roadmap                        | ✅ Complete     | Review complete.                                |
| Docs   | Runbooks (`docs/runbooks/`)    | 🔶 Partial     | Stubs exist; lack operational content.          |
| Docs   | Security (`docs/security/`)    | 🔶 Partial     | Only Bedrock threat model exists.               |
| Docs   | Specs                          | ✅ Complete     | Review complete.                                |
| Docs   | Test (`docs/test/`)            | ⬜ Not started  | —                                               |

## Detailed progress

### `docs/dev/` (In progress)

- `python_style_rules.md` — currently ends at `### 3.8 Comments and Docstrings`; remaining sections not yet written.
- `python_language_rules.md` — not started.
- `python_coding_standard.md` — not started.

### `.claude/` Loops (Not started)

No loop definitions documented yet. Loop scripts and their invocation patterns
need to be documented alongside agent and skill entries.

## Dependency / sequencing

This task has no hard code prerequisites — it runs concurrently with or after
any task whose outputs it documents. However, a doc entry written before the
implementation stabilises will drift; the recommended order is:

```
Tasks 1–10 implementation stabilised
    │
    └──► 11.0 Documentation
              │
              ├── docs/dev/ (python_style_rules complete → language rules → coding standard)
              ├── docs/agent/ (after agents/base.py and all agent modules settle)
              ├── docs/config/ (after config/settings.py and CLI flags settle)
              ├── docs/runbooks/ (after REST API layer lands)
              ├── docs/security/ (per integration surface, as each backend lands)
              ├── docs/test/ (after Testing & Hardening baseline is set)
              ├── docs/reviews/ (index + template can land any time)
              └── .claude/ loops (after loop usage patterns are established)
```

## Definition of done

All rows in the subtask table above show ✅ Complete **and**:

- [ ] `docs-updater` can process a code change and update the relevant doc
      without a human authoring the prose from scratch.
- [ ] Every debate agent in `aegis_swr/agents/` has an entry in
      `docs/agent/agents.md`.
- [ ] `docs/dev/` contains `python_style_rules.md` (complete),
      `python_language_rules.md`, and `python_coding_standard.md`.
- [ ] `docs/README.md` index links to every file added by this task.
- [ ] Flip the `11 Documentation` row in `status.md` to ✅ Complete.
