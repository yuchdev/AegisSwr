# Incident lifecycle invariants (code-anchored)

Ground truth for the `incident-triage` checks. Sourced from
`src/aegis_swr/core/orchestrator.py`, `core/consensus.py`, `core/events.py`,
`core/schemas.py`, and `config/settings.py`. When the code and this file
disagree, the code wins — update this file (that drift is itself a finding).

## The state machine

The live orchestrator runs a LangGraph `StateGraph`(`Orchestrator._build_graph`). 
Verify against the nodes and edges below.

```
START
  → data_adapter_node          # DataAdapter.process → IncidentBrief (fault_class, symbols, evidence)
  → os_kernel_node             # OSKernelAgent      → hypotheses + confidence
  → code_analyst_node          # CodeAnalystAgent   → hypotheses + probabilistic fix
  → log_historian_node         # LogHistorianAgent  → recurrence match vs prior reports
  → skeptic_node               # SkepticAgent       → challenges; consensus computed here
  → _route_after_skeptic  ┬──→ output_synthesizer_node → END   (converged)
                          ├──→ hitl_node             → END   (max rounds hit)
                          └──→ os_kernel_node                 (loop: next debate round)
```

- Every node returns an update dict that is folded into `InvestigationState`.
- The **only** cycle is skeptic → os_kernel (a new debate round). Every other edge
  is forward to `END`. There is no state without an exit: the graph terminates at
  `output_synthesizer_node` or `hitl_node`, both of which edge to `END`.

## Convergence rule (exact, from `_skeptic_node` + `ConsensusEvaluator`)

Convergence requires **all three**:

1. `skeptic_confirmed` — the Skeptic turn's `confidence_score >= 0.65` (MEDIUM+).
2. Weighted consensus `>= consensus_threshold` (`CoreSettings.consensus_threshold`,
   default **0.85**), where consensus = per-agent scores weighted by the fault
   class's row in the agent-weight matrix.
3. `same_hypothesis` — the primary hypothesis `root_cause` is unchanged from the
   previous round (`previous_hypothesis_key`).

If not converged and `rounds_completed >= max_debate_rounds`
(`CoreSettings.max_debate_rounds`, default **4**) → route to `hitl_node`.
Otherwise loop back for another round.

## Escalation invariants (must hold after any change)

- **No silent weak report.** A run that cannot converge must reach `hitl_node`,
  which builds an `RCAReport` carrying a non-null `HITLRequest`. It must never
  emit a low-confidence `RCAReport` with `hitl_request = None` down the
  `output_synthesizer_node` path.
- **There is always a human route.** The `_route_after_skeptic` fallback on
  max-rounds is the guaranteed escalation path; a change that can bypass it (e.g.
  raising `max_debate_rounds` unbounded, or routing to the synthesizer on a
  non-converged state) removes the safety net.
- `ConfidenceLevel.from_score` thresholds: `>= 0.80` HIGH, `>= 0.50` MEDIUM, else
  LOW. `RCAReport.confidence_level` is derived from the consensus score via this.

## EventBus invariants (`core/events.py`)

Views stay in sync only if each meaningful transition publishes a `DomainEvent`.
The six event types and when they must fire:

| Event | Fires when |
|-------|-----------|
| `InvestigationStarted` | run begins (before `data_adapter_node`) |
| `EvidenceExtracted` | `data_adapter_node` produced an `incident_brief` |
| `AgentSpoke` | any agent node appended a turn to `discussion_history` |
| `ConsensusEvaluated` | `skeptic_node` computed a `consensus_score` |
| `InvestigationCompleted` | `output_synthesizer_node` produced a report, `hitl_pending=False` |
| `HumanInputRequired` | `hitl_node` produced a report, `hitl_pending=True` |

A new terminal or branch that does not publish the matching event will leave the
CLI/TUI/GUI showing a stalled investigation — treat a missing publish as a ✗.

## Timeout & failure handling

- Every external call (debugger subprocess, AI backend, relational/object/vector
  store, log/code backend) must have an explicit timeout and a defined fallback.
- Store writes in `output_synthesizer_node` / `hitl_node` are **best-effort**:
  wrapped in `try/except`, failures logged (without payload) and not fatal. A
  change that makes a store failure abort the run, or that drops the report on a
  store failure, is a regression.
- No unbounded waits, no half-written reports.

## De-duplication safety (`incident_similarity.py` / cache gate)

- `Orchestrator.run` short-circuits on a relational-store cache hit by `dump_hash`.
  A change here must not: (a) drop a genuinely new incident as a duplicate
  (missed escalation), nor (b) fail to suppress an identical recurring root cause
  (alert fatigue). Both directions are safety issues.

## Payload safety (cross-cuts every check)

Incident payloads are attacker-influenced. No unredacted dump/log/stack text may
reach logs, exceptions, stored report error fields, or an AI prompt without
sanitisation. The store-failure `logger.warning` calls above deliberately log the
exception, not the report — keep it that way.
