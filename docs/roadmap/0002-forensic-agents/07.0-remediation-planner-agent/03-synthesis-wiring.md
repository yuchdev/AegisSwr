# 03 — Synthesis-tier wiring

**Parent task:** 07.0 Remediation Planner Agent
**State:** ⬜ Not started
**Depends on:** 02 (agent implementation)
**Blocks:** 05

## Objective

Wire `RemediationPlannerAgent` into the orchestrator's `_output_synthesizer_node`
so that converged investigations automatically receive a `RemediationPlan` on
the confirmed `RCAReport`. Gate the call on convergence: the HITL path must not
invoke the agent under any circumstances.

## Files

- **Modify** `src/aegis_swr/core/orchestrator.py`
- **Modify** `src/aegis_swr/agents/registry.py`
- **Modify** `src/aegis_swr/agents/synthesis/__init__.py` (confirm re-export)
- **Modify** `src/aegis_swr/config/settings.py` (add `enabled_synthesis` field)

## Settings change (`AgentPanelSettings`)

Add one field to the existing `AgentPanelSettings` (introduced by Task 02.0):

```
enabled_synthesis: list[str] = Field(default_factory=lambda: ["remediation_planner"])
```

The default includes `"remediation_planner"` so that the agent is on by default
for converged investigations. Operators can disable it by setting
`enabled_synthesis: []` in config or via the `AEGIS__agents__enabled_synthesis`
env override.

## Registry change (`AGENT_REGISTRY`)

In `src/aegis_swr/agents/registry.py`, add the entry:

```
"remediation_planner": RemediationPlannerAgent,
```

`create_agent_panel` already filters by `category != "synthesis"` (per C4), so
this entry is visible to the registry but never returned by the panel factory.
The registry entry is needed for discoverability (e.g. Task 08.0 docs tooling,
validation scripts).

## Orchestrator change (`_output_synthesizer_node`)

The synthesizer node must be extended as follows, in order:

1. Build the `RCAReport` as today: `report = self._build_report(state, hitl_pending=False)`.
2. Check whether synthesis is enabled:
   `"remediation_planner" in self._settings.agents.enabled_synthesis`.
3. If enabled, instantiate `RemediationPlannerAgent(ai_backend=self._ai)` (or
   hold a pre-constructed instance on `self` — implementation choice; document
   in `status.md`).
4. Call `turn, plan = await planner.run_synthesis(report)`.
5. If `plan.requires_human_approval` is `True`, emit a `loguru` warning at
   `WARNING` level: `"Remediation plan requires human approval for incident
   {report.incident_id}"`. Do NOT log the plan steps (payload risk).
6. Attach the plan: `report = report.model_copy(update={"remediation_plan": plan})`.
7. Proceed with existing storage calls (`self._relational.save_report(report)`,
   `self._vector.upsert_incident(report)`).
8. If `run_synthesis` raises any exception, log the error (without payload) and
   continue without a plan (`report.remediation_plan` remains `None`). This is
   a soft failure: a synthesis error must not block delivery of the confirmed RCA.

`_hitl_node` is NOT modified. It calls `_build_report(state, hitl_pending=True)`,
which sets `remediation_plan=None` by default, and returns immediately. No
synthesis agent is ever referenced in `_hitl_node`.

## Routing: no change

`_route_after_skeptic` returns `"output_synthesizer_node"` on convergence and
`"hitl_node"` on max-rounds-exceeded. Both strings are unchanged. The synthesis
invocation is internal to `_output_synthesizer_node` and invisible to the router.

## EventBus: synthesis spoke

After a successful `run_synthesis` call, emit an `AgentSpoke` event on
`self._event_bus` (if present) using the returned `AgentTurn`. This keeps the
SSE stream consistent: consumers see the remediation turn appear after the
skeptic confirmation, labelled `"Remediation Planner Agent"`.

## Constraints

- `_hitl_node` must not reference `RemediationPlannerAgent` in any code path.
- Synthesis failure (exception from `run_synthesis`) is a soft error: log and
  continue, `remediation_plan` stays `None`.
- `report.model_copy(update=...)` is the correct Pydantic v2 pattern for
  producing an updated immutable copy; do not mutate the report in place.
- `Optional[T]`, `mypy --strict`, `ruff` clean.
- No raw incident payload in any log statement emitted by the synthesizer path.

## Success criteria

- [ ] `AgentPanelSettings.enabled_synthesis: list[str]` exists with default
      `["remediation_planner"]`.
- [ ] `"remediation_planner"` is registered in `AGENT_REGISTRY` with
      `RemediationPlannerAgent`.
- [ ] `_output_synthesizer_node` calls `run_synthesis` when `"remediation_planner"`
      is in `enabled_synthesis`, and attaches the result to `RCAReport.remediation_plan`.
- [ ] `_output_synthesizer_node` skips synthesis gracefully on exception;
      `RCAReport.remediation_plan` is `None` in that case.
- [ ] `_hitl_node` is unchanged and never references `RemediationPlannerAgent`.
- [ ] An `AgentSpoke` event is emitted on the `EventBus` for the synthesis turn.
- [ ] `mypy --strict` and `ruff` clean on all modified files.
