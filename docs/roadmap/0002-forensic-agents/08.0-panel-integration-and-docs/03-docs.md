# 03 — Docs

**Parent task:** Task 08.0 — Panel Integration, Docs & Hardening
**Status:** ⬜ Not started
**Depends on:** 01-default-panels-and-weight-audit.md
**Blocks:** 05-milestone-closeout.md

---

## Objective

Update the four documentation targets to reflect the full nine-agent roster
delivered by Milestone 0002. Run `/link-check` (`scripts/check_doc_links.py`)
after all edits to confirm every Markdown link and heading anchor resolves.

---

## 1. `docs/agent/agents.md`

**What to change:** The "product agents" notice near the top currently names four
agents: `os_kernel`, `code_analyst`, `log_historian`, `skeptic`. Expand this
notice to list the full roster with one-line roles.

**Exact location in file:** The paragraph beginning "The product contains its
own analytical agents inside `src/aegis_swr/agents/`" — replace the inline
parenthetical that lists four agents with the expanded table below. Do not alter
the dev-fleet content that follows.

**Expanded product agent roster (insert as a table after the notice paragraph):**

| `agent_key`           | Class                          | Category   | Tier        | One-line role |
|-----------------------|--------------------------------|------------|-------------|---------------|
| `os_kernel`           | `OSKernelAgent`                | base       | debate      | OS/kernel environment context; injects Skeptic corrections each round |
| `code_analyst`        | `CodeAnalystAgent`             | base       | debate      | Code logic and probabilistic fix encoding |
| `log_historian`       | `LogHistorianAgent`            | base       | debate      | Historical pattern correlation via VectorStore |
| `skeptic`             | `SkepticAgent`                 | base       | debate (last) | Programmatic + LLM validation; produces corrections for next round |
| `memory_forensics`    | `MemoryForensicsAgent`         | forensic   | debate      | Heap corruption, use-after-free, allocator tells, fill-pattern signatures |
| `concurrency_analyst` | `ConcurrencyAnalystAgent`      | forensic   | debate      | Deadlocks, lock-ordering inversions, race conditions, thread wait-chains |
| `exploitability`      | `ExploitabilityAnalystAgent`   | forensic   | debate      | Exploit/vuln assessment; attacker-control reach, mitigation state |
| `resource_exhaustion` | `ResourceExhaustionAgent`      | forensic   | debate      | Handle/fd/memory leaks, OOM, connection-pool exhaustion |
| `remediation_planner` | `RemediationPlannerAgent`      | synthesis  | post-debate | Ordered, rollback-covered remediation playbook from confirmed RCA |

---

## 2. `docs/config/agents.md`

**What to change:** The file currently describes "the four forensic agents" and
the ten fault-class weight keys using the legacy four-field flat format
(`os_kernel`, `code_analyst`, `log_historian`, `skeptic`). Update it to reflect
the data-driven `weights` dict format (plan.md C3) and the new per-fault panel
configuration.

**Specific updates required:**

- Replace the introductory sentence "The `agents.json` weight matrix: the four
  forensic agents…" with "The `agents.json` weight matrix: up to nine debate
  agents, keyed by `agent_key`, with normalized per-fault weight vectors."
- Add a section "Panel configuration" describing `AgentPanelSettings`:
  `default_panel` (list of `agent_key` strings, defaults to the legacy four)
  and `per_fault_class` (map from `FaultClass` value to ordered agent list,
  `skeptic` always last).
- Update the weight-format example to show the data-driven `weights` dict
  for one fault class (e.g. `use_after_free`) instead of the four-field flat
  example.
- Note that `remediation_planner` does not appear in weight vectors (it is a
  post-debate synthesis agent, not a voter).
- Update the "Default weights" table to include specialist agent columns for
  all ten fault classes, sourced from subtask 01's ratified table.

---

## 3. `docs/specs/agentic_fleet_design.md` — §1 Domain glossary

**What to change:** The glossary entry for "Consensus" currently reads:

> `core/consensus.py` blends the four product agents' hypotheses, weighted per
> fault class (`agents.example.json`).

Replace with:

> `core/consensus.py` blends the active debate panel's hypotheses, weighted per
> fault class (`agents.example.json`). The panel is data-driven: the default
> panel is the four base agents (`os_kernel`, `code_analyst`, `log_historian`,
> `skeptic`); specialist forensic agents (`memory_forensics`,
> `concurrency_analyst`, `exploitability`, `resource_exhaustion`) join the panel
> for the fault classes where they carry authority. `remediation_planner` is a
> post-debate synthesis agent and is not a weighted voter.

Also add a new bullet to the glossary for "Agent panel":

> **Agent panel**: the ordered list of debate agents assembled by
> `create_agent_panel()` for a given `FaultClass`. Built from `AgentPanelSettings`;
> `skeptic` is always last. Synthesis agents (`remediation_planner`) are never
> part of the panel.

No other §1 content changes. Do not alter §2 onwards.

---

## 4. `docs/README.md`

**What to change:** In the "Roadmap" section table, the row for Milestone 0002
currently reads:

```
| 0002 | Forensic agents (agentic execution brief) | plan.md | — |
```

The `—` in the Status column should be replaced with a link to `status.md` once
Task 08.0 subtask 05 flips all rows to complete. However, this subtask (03) only
updates the description to reflect the decomposed state. Change the row to:

```
| 0002 | Forensic agents | plan.md | status.md |
```

where `status.md` links to `/docs/roadmap/0002-forensic-agents/status.md`. The
description is simplified from "agentic execution brief" to "Forensic agents" to
match the milestone title from plan.md.

---

## Link-check gate

After all four document edits are complete, run:

```
python scripts/check_doc_links.py docs/
```

All anchors and file links in the modified documents must resolve. Common failure
modes to watch for:

- The new heading "Panel configuration" in `docs/config/agents.md` must be
  spelled exactly as any inbound link expects.
- The `plan.md` links in this task's own subtask files use absolute paths
  (`/docs/roadmap/0002-forensic-agents/plan.md`) — verify they resolve.
- The `agent_key` anchor links in the new agents table must not conflict with
  existing heading IDs in `docs/agent/agents.md`.

---

## Success criteria

- [ ] `docs/agent/agents.md` product agent notice is updated to the nine-agent
      roster table with accurate one-line roles.
- [ ] `docs/config/agents.md` weight-format example, introductory sentence,
      panel-configuration section, and the default-weights table are all updated.
- [ ] `docs/specs/agentic_fleet_design.md` §1 "Consensus" bullet is updated and
      an "Agent panel" bullet is added.
- [ ] `docs/README.md` Milestone 0002 row has a `status.md` link and an updated
      description.
- [ ] `python scripts/check_doc_links.py docs/` exits 0 with no broken links.
- [ ] No prose in the dev-fleet agent descriptions (`.claude/agents/`) is
      modified — those describe dev-time assistants, not the product roster.
