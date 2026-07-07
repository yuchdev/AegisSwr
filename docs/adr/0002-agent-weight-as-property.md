# 0002 - Consensus weight is a property of the agent, not an external config file

> **Status:** Accepted
>
> **Date:** 2026-07-08
>
> **Supersedes:** _(none)_
>
> **Superseded by:** _(none)_

## Context

The agentic system was refactored so that `Orchestrator` is a thin container for
agents and each agent carries its own identity/behaviour as class-level
`ClassVar` descriptors on `BaseAgent` (`agent_key`, `display_name`, `category`,
`role`, `contributes_fix`). One piece of agent policy was left behind in an
external, ops-curated JSON file: the **consensus weight**.

That policy lived in two places that both hardcoded the agent roster:

- `AgentWeightsSettings` (`config/settings.py`) - a ten-field, per-fault-class
  weight *matrix* (`memory_access_violation`, `null_pointer_dereference`, ...,
  `unknown`), each field an `AgentWeightEntry` (`weights: dict[str, float]`).
- `AgentPanelSettings` - a candidate-pool policy (`default_panel`,
  `per_fault_class`).

Both were sourced from a single `agents.json` file (`agents.example.json` is the
shipped template) via `AegisJsonSettingsSource`, which merged `config.json` +
`agents.json` and mounted `agents.json`'s `"weights"` key under
`Settings.agent_weights` and its `"panel"` key under `Settings.agent_panel`.

`agents/panel.py::resolve_consensus_weights` then applied a **three-tier
precedence** per agent: (1) explicit `AgentSpec.weight` override, (2) curated
per-fault-class value from the matrix, (3) `spec.priority` normalized over the
other tier-3 agents.

This contradicts the "each agent carries its own properties" design: weight is
an intrinsic property of what an agent *is* (how much its confidence should
count), yet it was declared far away in an external file keyed by a hardcoded
roster. Adding an agent meant editing `agents.json`; the matrix could silently
drift from the registry.

Key finding: the shipped `agents.example.json` `panel` section is
`{"default_panel": [all four registered agents], "per_fault_class": {}}` - i.e.
today it is exactly "every registered agent, no override." So the panel-curation
feature carried no information the registry does not already have.

## Decision

**Weight becomes an intrinsic, self-declared property of each agent class**, and
the `agents.json` file concept is eliminated wholesale.

1. Add `default_weight: ClassVar[float]` to `BaseAgent`, declared (no base
   default) by every concrete agent - exactly like `role`/`display_name`. The
   four agents declare the mean of their historical per-fault-class weights:

   | Agent | `default_weight` | Historical column mean |
   |---|---|---|
   | `os_kernel` | `0.35` | 3.50 / 10 = 0.35 |
   | `code_analyst` | `0.35` | 3.50 / 10 = 0.35 |
   | `log_historian` | `0.17` | 1.70 / 10 = 0.17 |
   | `skeptic` | `0.13` | 1.30 / 10 = 0.13 |

   These are the exact per-agent averages across the old ten-fault-class matrix
   (each column of which summed to 1.0), so they sum to exactly `1.0`, preserve
   the relative authority ordering (`os_kernel = code_analyst > log_historian >
   skeptic`), and require no arbitrary rounding.

2. `resolve_consensus_weights(panel, specs)` collapses from three tiers to two:
   (1) explicit `AgentSpec.weight` override when set, else (2) the agent's own
   `default_weight`. The fault-class parameter and the `AgentWeightsSettings`
   parameter are removed. `ConsensusEvaluator.calculate` still normalizes by the
   summed weights of whatever panel it receives, so no whole-map
   renormalization is needed.

3. **The tier-3 priority-normalization fallback is removed.** `AgentSpec.priority`
   remains, but now serves a single purpose - debate/speaking order (descending
   priority, arbiter last) - decoupled from consensus influence.

4. Delete `AgentWeightsSettings`, `AgentWeightEntry`, `AgentPanelSettings`, the
   `AGENTS_JSON` constant, the `Settings.agent_weights` / `Settings.agent_panel`
   fields, and the `agents.json`-reading half of `AegisJsonSettingsSource`
   (`config.json` reading is unchanged). Delete `agents.example.json`.

5. Panel candidate-pool selection becomes **registry-driven**:
   `AgenticManagerStrategy.select()` returns one default-priority `AgentSpec`
   per key in `AGENT_REGISTRY` (insertion order preserves the historical
   `os_kernel → code_analyst → log_historian → skeptic` sequence). This is
   behaviour-preserving given the shipped example's "all agents, no override"
   panel, and removes the per-fault-class panel-curation feature.

## Alternatives Considered

| Alternative | Pros | Cons | Reason rejected |
|-------------|------|------|-----------------|
| Keep `agents.json`, just document weight better | No code churn | Leaves weight as external hardcoded-roster policy; contradicts the refactor's "agent owns its properties" principle; the user explicitly asked to eliminate the file | Rejected - does not satisfy the requirement |
| `default_weight` optional on base + keep tier-3 priority fallback as a safety net | Tolerates an agent that forgets to declare a weight | Reintroduces silent misweighting (an under-configured agent gets a plausible-but-wrong weight instead of failing loudly); consensus-safety prefers loud failure | Rejected - a missing weight should fail like a missing `role`, not be papered over |
| Per-agent `weight_for(fault_class)` method (keep fault-class differentiation, move it into each class) | Preserves per-fault-class specialization | Just re-encodes the matrix inside each class; still a "roster" of weights; against the "eliminate the matrix" intent | Rejected - a single scalar per agent is the faithful reading of "weight is a property of the agent" |
| Registry-driven panel with a scalar default weight (chosen) | Fully self-declared; no external file; loud on misconfig | Loses per-fault-class weight differentiation (see Negative) | **Accepted** |

## Consequences

### Positive

- Weight is now co-located with the agent it describes; adding an agent means
  declaring one more `ClassVar`, with nothing to edit in an external file.
- The agent roster has a single source of truth (`AGENT_REGISTRY`); weight and
  panel can no longer drift from it.
- A concrete agent that omits `default_weight` fails loudly at panel resolution
  (`AttributeError`) rather than being silently mis-weighted.
- `AgentSpec.priority` now has one clear meaning (ordering), not two.
- Settings loading is simpler: one file (`config.json`), one settings source.

### Negative

- **Per-fault-class weight differentiation is lost.** Previously, e.g., a
  `stack_overflow` weighted `os_kernel` at `0.45` vs `code_analyst` `0.30`; now
  both are a flat `0.35` regardless of fault class. The chosen defaults are the
  mean across all fault classes, so aggregate behaviour is preserved, but a
  fault class that historically leaned hard on one agent now blends more evenly.
  This is an accepted trade-off of the "weight is a scalar property" decision;
  it is called out for the `incident-analyst` review and should be revisited if
  fault-class-specific consensus miscalibration (missed escalation / false
  convergence) is later observed.
- Per-fault-class **panel curation** is removed. Behaviour-preserving today
  (the shipped example used "all agents, no override"), but a future need to
  restrict the panel by fault class would require re-introducing a mechanism.
- An operator can no longer retune weights without a code change + redeploy.
  Explicit per-incident overrides via `AgentSpec.weight` (CLI `--agent`,
  `config.json` `panel.explicit`) remain available.

## Validation / Rollout

- Unit: `resolve_consensus_weights` two-tier precedence (explicit override beats
  `default_weight`; `default_weight` used otherwise); each agent's declared
  weight; `AGENT_REGISTRY`-driven panel selection.
- Integration: `test_orchestrator_dynamic_panel.py` re-premised on the
  agent-declared weights (no `agents.json` load); explicit-panel weight-tier
  behaviour retained; default 4-agent debate order/report values preserved.
- `incident-analyst` pass on the consensus-weight collapse for
  investigation-flow safety.
- Full suite + ruff after implementation.

## Links

- **Requirement:** eliminate `AgentWeightsSettings` / `agents.json`; make weight
  a property of the agent.
- **Touched code:** `agents/base.py`, `agents/{os_kernel,code_analyst,log_historian,skeptic}.py`,
  `agents/panel.py`, `config/settings.py`, `core/panel_strategy.py`,
  `core/orchestrator.py`, `cli/config.py`.
- **Deleted:** `agents.example.json`.
