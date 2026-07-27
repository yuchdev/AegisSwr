# AegisSwr — Milestone 0002 Exit-Gate Threat Model

**Scope:** Forensic/synthesis agent surface + panel selection
**Reviewer role:** Security exit-gate audit (crash-dump forensics; all incident payload treated as hostile)
**Date:** 2026-07-10
**Change set:** Milestone 0002 diff (`agents/forensic/`, `agents/synthesis/`, `core/panel_strategy.py`, `core/orchestrator.py` synthesizer path)

## 1. Assets & Trust Boundaries

**Assets**
- Analyst host / operator environment (RCE target).
- Secrets & PII embedded in attacker-influenced crash payload (crash addresses, register values, stack frames, logs).
- Integrity of the RCA verdict and the remediation dispatch decision (elevation target).
- LLM instruction channel (prompt-injection target).

**Trust boundaries**
- **B1 — Payload ingress → brief:** Raw `IncidentSource` crosses into the system only through `core/data_adapter.py`, which performs the *single* payload transformation: noise filter + PII scrub. Downstream agents receive an already-scrubbed `incident_brief` dict.
- **B2 — Deterministic pre-check → LLM prompt:** Each forensic agent runs a string/regex pre-check, then hands `incident_brief` + derived pre-check to `self._ai.generate`. The LLM is the intended consumer of scrubbed payload.
- **B3 — Debate consensus → synthesis:** Only a converged `RCAReport` (safe fields) crosses into `RemediationPlannerAgent`. Raw `ExploitabilityOutput` never crosses this boundary.
- **B4 — Plan → execution:** No boundary is crossed automatically; execution is gated behind operator-set `AEGIS_PROD_CONFIRMED=1` and advisory `requires_human_approval`.
- **B5 — Fault classification → panel:** `FaultClass` is computed inside the debug backends (`windbg_js_worker`, `cdb_worker`, `gdb_worker`, `lldb_worker`) from platform fault-code maps *before* payload enters the LLM path; it gates panel composition.

## 2. Threat Assessment

### T1 — INJECTION (untrusted payload → shell/SQL/eval/subprocess/unsanitised sink)
**Result: No finding.**
- `exploitability_analyst.py`: `_classify_access` (substring `in` checks), `_classify_address` (`int(str(address),16)` + string inspection), `_is_repetitive_hex` (pure slicing). No dynamic sink.
- `memory_forensics.py`: `_FILL_PATTERN_RE` static, compiled at import; `_detect_fill_patterns` does `json.dumps` + `re.findall` only.
- `concurrency_analyst.py`: `_THREAD_RE` static; keyword membership + regex only.
- `resource_analyst.py`: `_LEAK_PATTERNS` all static, compiled at import; `finditer` + slice; `re.error` caught.
- No payload-derived regex is ever compiled. The Data Adapter scrub is the only payload transformation.

### T2 — DISCLOSURE (raw payload / address / registers → loguru / exception / output)
**Result: No finding.**
- The Exploitability agent logs only `pre_check = {access_type, address_class}` — derived classification strings. `_classify_address` returns `"near_null" | "attacker_pattern" | "unknown_wild"`; the raw address value is never logged or returned.
- No forensic pre-check logs raw brief text. `resource_analyst._extract_leak_indicators` on failure logs only `type(exc).__name__` — no payload.
- `_synthesize_remediation` logs only `incident_id` + `type(exc).__name__` on soft-failure — no payload.
- Transcript `message` fields carry LLM analyst prose (`attacker_control`) whose system prompt forbids verbatim payload/PII/credential echo; the underlying payload is already PII-scrubbed at B1.

### T3 — ELEVATION (exploitability verdict → automated remediation)
**Result: No finding.**
- `RemediationPlannerAgent.run_synthesis` consumes only safe `RCAReport` fields (`root_cause`, `faulting_module/function`, `confidence_score/level`, `primary_hypothesis.{root_cause,evidence}`, `mitigation_instructions`). No `ExploitabilityOutput`, no `exploitable`/`severity`, no raw payload.
- The Exploitability agent participates only as a weighted debate voter (weight 0.20); its verdict influences consensus, not dispatch.
- The synthesizer node only *attaches* an advisory plan; no step is dispatched. `requires_human_approval` plans are surfaced advisory-only; execution requires `AEGIS_PROD_CONFIRMED=1`. `run()` raises `NotImplementedError`, forcing the synthesis-only path.

### T4 — PANEL INTEGRITY (attacker free-text driving panel selection)
**Result: No finding.**
- `AgenticManagerStrategy.select` gates forensic-specialist inclusion via `_fault_class_of(incident_brief)` → `incident_brief["fault_class"]`, a `FaultClass` enum produced by the debug backend (B5), not attacker-controllable free-text. Unrecognized/None values fall back to `None` (base-only panel). Synthesis agents are never debate candidates.

## 3. Findings

No high-confidence security findings.

## 4. Verdict

**VERDICT: PASS**

---

## Lifecycle gate (incident-analyst)

**Scope:** the two escalation-touching changes — data-driven consensus (Task 02.0)
and the remediation-planner synthesis path (Task 07.0).

**Findings**

1. **HITL path always reachable.** `Orchestrator._make_router._route` routes the
   arbiter to `hitl_node` whenever `rounds_completed >= core.max_debate_rounds`
   without convergence — independent of panel size. `ConsensusEvaluator` normalizes
   by the summed live-panel weights (`CS = Σ(Wᵢ·Sᵢ)/Σ(Wᵢ)`), so a larger panel
   cannot dilute the score above threshold; deadlock detection is unchanged.
   Verified by `tests/integration/test_remediation_planner_integration.py::test_hitl_investigation_yields_no_remediation_plan`
   and the existing `test_orchestrator.py` deadlock/HITL tests.
2. **Planner skipped on HITL.** `_synthesize_remediation` is called only from the
   convergence (`output_synthesizer`) node; `_hitl_node` builds its report with
   `hitl_pending=True` and never references the planner. `RCAReport.remediation_plan`
   is `None` on every HITL outcome (asserted by the integration test above).
3. **Planner never escalates.** `run_synthesis` failure is a soft error: the
   exception is caught, logged without payload, and the confirmed report is
   returned with `remediation_plan=None`. A synthesis error neither blocks RCA
   delivery nor triggers HITL. Low-confidence plans (`confidence < 0.70`) set
   `requires_human_approval=True` (advisory) rather than escalating.

**VERDICT: PASS** — the HITL path is always reachable, an escalated incident
carries no auto-remediation plan, and the planner fails open without escalating a
converged investigation.
