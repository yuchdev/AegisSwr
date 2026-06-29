# 04 — Dynamic orchestrator panel

**Parent task:** 02.0 Extensible Panel
**State:** ⬜ Not started
**Depends on:** 01, 02, 03
**Blocks:** 06

## Objective

Replace the four hard-wired debate nodes in `core/orchestrator.py` with a
sub-graph built dynamically from `create_agent_panel()`, while preserving the
exact data-adapter → debate → skeptic → (synthesizer | hitl | next round)
topology. Implements contract **C5** (debate half; the synthesis half is Task 07.0).

## Files

- **Modify** `src/aegis_swr/core/orchestrator.py`

## Current structure (for reference)

The orchestrator today (0001) builds:

```
data_adapter_node → os_kernel_node → code_analyst_node
  → log_historian_node → skeptic_node ──(conditional)──► output_synthesizer_node | hitl_node | os_kernel_node
```

with per-agent node methods (`_os_kernel_node`, …), a shared `_fold_turn(state,
turn, agent_key)` helper, and `_route_after_skeptic`.

## Changes

1. In the constructor, build the panel once (default/fault-agnostic panel is fine
   for graph construction; per-fault panel selection is a follow-on enhancement —
   see "Scope note"): `self._panel = create_agent_panel(ai_backend, settings)`.
   Keep `self._evaluator` (ConsensusEvaluator) and `self._skeptic` references.
2. Build the debate sub-graph dynamically:
   - For each **non-skeptic** panel agent, add a node that calls
     `await agent.run(state)` and folds the turn via the existing `_fold_turn`
     using `agent.agent_key`. A small generic node factory replaces the four
     bespoke `_*_node` methods (keep `log_historian` special-casing for its
     `vector_store`/`history` kwargs — pass them when `agent.agent_key ==
     "log_historian"`).
   - Chain the non-skeptic agents in panel order: `data_adapter_node →
     agent[0] → agent[1] → … → skeptic_node`.
   - `skeptic_node` stays as-is (consensus calc + round increment +
     `_route_after_skeptic`), and routes back to the **first** debate agent for
     the next round (not necessarily `os_kernel_node` — use the panel's first key).
3. `_route_after_skeptic` returns the first debate node's name on "next round"
   instead of the literal `"os_kernel_node"`.
4. Node names: derive from `agent_key` (e.g. `f"{agent_key}_node"`) so the graph
   is inspectable and SSE `AgentSpoke` events keep a stable node label.

## Scope note (per-fault panel)

Constructing the LangGraph once requires a fixed node set, but the *fault class*
is only known after the data-adapter node runs. For this task, build the graph
from the **union default panel** (all enabled debate agents) and have each
specialist node **early-return a no-op turn** when it is not part of the active
fault class's panel (cheap, no LLM call) — OR keep the graph to the default panel
and treat per-fault membership purely as a consensus-weight concern. Pick the
approach in implementation; document it in `status.md`. Either way the
**back-compat gate holds**: default config ⇒ legacy four-node chain ⇒ identical
behavior.

## Constraints

- Default config ⇒ node chain and routing identical to 0001 (same node names,
  same order, same conditional edges).
- `skeptic` always terminal; round-increment and HITL/converge routing unchanged.
- No raw payload logged; existing `EventBus`/`AgentSpoke` contract preserved.
- `Optional[T]`, mypy strict, ruff clean.

## Tests

- Extend `tests/unit/test_orchestrator.py`:
  - `test_default_panel_node_chain` — with default settings the compiled graph has
    the four legacy nodes in order and the skeptic conditional edges.
  - `test_full_pipeline_converges_unchanged` — existing convergence test still
    passes (1–2 rounds, `is_converged`).
  - `test_panel_with_specialist_adds_node` — a config enabling one specialist adds
    a debate node before skeptic and the specialist turn appears in
    `discussion_history`.
  - `test_next_round_targets_first_debate_agent` — `_route_after_skeptic`'s
    next-round target is the panel's first debate node.

## Success criteria

- [ ] Orchestrator builds debate nodes from `create_agent_panel`; skeptic terminal.
- [ ] Default config reproduces the 0001 node chain, routing, and convergence.
- [ ] Enabling a specialist adds a debate node and a turn in history.
- [ ] All orchestrator tests pass; `mypy src/` clean.
