# 02 - Agent implementation

**Parent task:** 07.0 Remediation Planner Agent
**State:** ⬜ Not started
**Depends on:** 01 (schema)
**Blocks:** 03

## Objective

Implement `RemediationPlannerAgent` in a new module
`src/aegis_swr/agents/synthesis/remediation_planner.py`. The agent consumes a
confirmed `RCAReport` (already built by `_build_report`) and returns an
`AgentTurn` whose associated `RemediationPlan` is accessible for the orchestrator
to attach to the final report.

## Files

- **Create** `src/aegis_swr/agents/synthesis/__init__.py` (package stub; re-exports `RemediationPlannerAgent`)
- **Create** `src/aegis_swr/agents/synthesis/remediation_planner.py`

## Class contract

```
class RemediationPlannerAgent(BaseAgent):
    agent_key:    ClassVar[str] = "remediation_planner"
    category:     ClassVar[str] = "synthesis"
    display_name: ClassVar[str] = "Remediation Planner Agent"

    async def run_synthesis(
        self,
        report: RCAReport,
    ) -> tuple[AgentTurn, RemediationPlan]:
        ...
```

`run_synthesis` is the synthesis-specific entry point. The inherited `run(state)`
method raises `NotImplementedError` to make the exclusion from debate explicit
and catch any accidental wiring at test time.

## System prompt (authoritative persona)

The system prompt MUST contain all of the following directives:

1. **Role**: "You are a remediation engineer specializing in post-incident
   playbook construction. Your sole task is to convert a confirmed Root Cause
   Analysis into a structured, executable remediation plan."
2. **Step idempotency mandate**: "Every step in your plan MUST be idempotent.
   A step is idempotent when running it a second time produces no additional
   side-effects. If you cannot make a step idempotent, you MUST explain why in
   the `risk` field and provide a precise `rollback` action."
3. **Rollback mandate**: "Every step MUST include a `rollback` field. For
   read-only verification steps, use the literal `rollback` value
   `\"read-only: no state change\"`. An empty `rollback` is never acceptable."
4. **Step ordering**: "Order steps in the sequence: contain → remediate →
   verify. Do not include any detection steps (the RCA already confirms the
   fault). Do not include steps that require information not present in the
   provided RCA."
5. **Production gate**: "Any step that modifies production state MUST set
   `requires_human_approval` to `true`. When in doubt, require approval."
6. **Output format**: "Respond with a JSON object matching the `RemediationPlan`
   schema exactly. Do not include commentary outside the JSON object."

The prompt must end with `cache_control: {"type": "ephemeral"}` applied per
the `_BaseAIBackend` convention (passed transparently when `system_prompt` is
set as a property).

## `run_synthesis` implementation

1. Build a context dict from the confirmed `RCAReport` containing only the
   fields needed for planning. Do NOT include `raw_text_excerpt`, full
   `agent_dialogue`, or any stack frame text - those are untrusted payload.
   Safe fields to include: `root_cause`, `faulting_module`, `faulting_function`,
   `confidence_score`, `confidence_level`, `primary_hypothesis.root_cause`,
   `primary_hypothesis.evidence`, and `mitigation_instructions`.
2. Serialize the context dict to JSON and place it in a single `user` message.
3. Call `await self._ai.generate(self.system_prompt, messages, RemediationPlan)`.
4. Assert the result is `RemediationPlan`. If `generate` raises, propagate the
   exception - the synthesizer node handles degraded-mode logic.
5. Construct and return an `AgentTurn` with:
   - `agent = self.display_name`
   - `turn_number = 0` (synthesis runs outside the debate round counter)
   - `message` = a one-line summary derived from `plan.summary`
   - `confidence_score = plan.confidence`
   - No `hypotheses` (the synthesis tier does not re-debate)
6. Return `(turn, plan)` as a tuple.

## Token accumulation

Call `self._accumulate_tokens(state)` is not applicable here (no
`InvestigationState` is passed). Instead, the orchestrator is responsible for
extracting token counts from the AI backend after the call and updating the
report's `total_input_tokens` / `total_output_tokens` fields.

## Constraints

- `Optional[T]` from `typing`; never `T | None`.
- `mypy --strict` clean; no bare `except:`.
- Incident payload fields (`raw_text_excerpt`, raw stack frames, log lines) must
  not appear in the messages list or in any log statement. Use `loguru` with
  `SensitiveFilter`; log only the `incident_id` and `confidence_score`.
- `run()` raises `NotImplementedError("RemediationPlannerAgent is synthesis-tier; call run_synthesis()")`.

## Success criteria

- [ ] `src/aegis_swr/agents/synthesis/remediation_planner.py` exists with
      `RemediationPlannerAgent` implementing the contract above.
- [ ] `src/aegis_swr/agents/synthesis/__init__.py` re-exports `RemediationPlannerAgent`.
- [ ] `agent_key`, `category`, `display_name` are `ClassVar[str]` with the
      specified values.
- [ ] `run()` raises `NotImplementedError`.
- [ ] `run_synthesis()` signature matches `(self, report: RCAReport) -> tuple[AgentTurn, RemediationPlan]`.
- [ ] System prompt contains all six directives listed above.
- [ ] No raw payload field (stack frames, dump text) is placed in the messages list.
- [ ] `mypy --strict` and `ruff` clean.
