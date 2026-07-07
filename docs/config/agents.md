# Agent consensus weight

> There is **no `agents.json` file** and no agent-weight config section. This
> page explains where consensus weight now lives.

Each forensic agent's **consensus weight** - how much its confidence counts when
the debate's consensus score is computed - is an **intrinsic property of the
agent class**, not an external configuration file. Weight is declared alongside
the agent's other self-describing `ClassVar` descriptors (`agent_key`,
`display_name`, `category`, `role`, `contributes_fix`) on
[`BaseAgent`](../../src/aegis_swr/agents/base.py):

```python
class BaseAgent(ABC):
    agent_key: ClassVar[str]
    display_name: ClassVar[str]
    category: ClassVar[AgentCategory]
    role: ClassVar[AgentRole]
    contributes_fix: ClassVar[bool] = False
    default_weight: ClassVar[float]   # ← the agent's intrinsic consensus weight
```

Every concrete agent declares its own `default_weight`. A concrete agent that
forgets to declare one fails loudly at panel resolution rather than being
silently mis-weighted (the same contract as `role`).

---

## The four built-in agents and their weights

| Agent | Key | `default_weight` | Role |
|---|---|---|---|
| **OS Kernel** | `os_kernel` | `0.35` | System-environment specialist. Focuses on memory-allocation state, I/O latency, driver conflicts, thread-blocking primitives, and hardware-signal mapping. Maps raw exception codes to a `FaultClass` and forms the first structural hypothesis. |
| **Code Analyst** | `code_analyst` | `0.35` | Software-architecture / logic-error specialist. Pinpoints the code-level root cause - faulting function, line, and logical path - and may emit a probabilistic fix (unified diff). |
| **Log Historian** | `log_historian` | `0.17` | Historical-pattern correlator. Compares the current signature to historical baselines, decides first-occurrence vs. recurrence, and adjusts confidence (±0.2). |
| **Skeptic** | `skeptic` | `0.13` | Adversarial moderator / arbiter. Challenges the primary hypothesis - verifies the faulting module appears in the stack, checks exception-code consistency, surfaces overlooked evidence - and confirms (HIGH/MEDIUM) or rejects (LOW). |

The four built-in weights are authored to sum to exactly `1.0`. They are the mean
of the agents' historical per-fault-class weights (see the
[ADR](../adr/0002-agent-weight-as-property.md)), so `os_kernel = code_analyst >
log_historian > skeptic` preserves the previous relative authority ordering.

The weights need **not** sum to any particular total in general - the consensus
math normalises by the summed weights of whatever panel is live (see below), so
adding an agent does not require rebalancing the others.

---

## How weights are used

The [`ConsensusEvaluator`](../../src/aegis_swr/core/consensus.py) computes a
weighted consensus score each debate round:

```
CS = Σ(Wᵢ · Sᵢ) / Σ(Wᵢ)
```

where `Wᵢ` is the resolved weight of agent *i* and `Sᵢ` is that agent's
confidence score (`[0.0, 1.0]`) this round. Agents missing from a round
contribute `0.0`. The round converges when `CS ≥` `core.consensus_threshold`
(default `0.85`) on a stable hypothesis; it deadlocks into a human-in-the-loop
request when rounds are exhausted with `CS <` `core.hitl_confidence_threshold`
(default `0.50`). See [config.md](config.md#core).

### Two-tier weight precedence

When building the weight map for a resolved panel
([`resolve_consensus_weights`](../../src/aegis_swr/agents/panel.py)), the
following precedence applies **per agent** (highest wins):

1. **Per-incident override** - `AgentSpec.weight` when set via the CLI
   (`--agent key::0.7`) or `config.json`'s `panel.explicit` list. Use this to
   retune influence for a single investigation without changing code.
2. **The agent's own declared weight** - `agent.default_weight` otherwise.

No pre-normalization is needed - `ConsensusEvaluator` divides by `Σ(Wᵢ)`.

> **Note:** weight no longer varies by fault class. Prior to
> [ADR 0002](../adr/0002-agent-weight-as-property.md) an ops-curated
> `agents.json` file held a per-fault-class weight matrix; that file and its
> `AgentWeightsSettings` / `AgentPanelSettings` models were removed. `AgentSpec.priority`
> now controls debate/speaking order only, and no longer contributes to weight.

---

## Changing an agent's weight

- **Permanently, for an agent:** edit that agent's `default_weight` `ClassVar` in
  `src/aegis_swr/agents/<agent>.py` (a code change + review + redeploy).
- **For a single investigation:** pass an explicit override -
  `aegis analyze --agent os_kernel::0.5 ...` - or set `panel.explicit` in
  `config.json`.

See also: [config.md](config.md) (`core.consensus_threshold`,
`core.hitl_confidence_threshold`), [cli.md](cli.md), and
[ADR 0002](../adr/0002-agent-weight-as-property.md).
