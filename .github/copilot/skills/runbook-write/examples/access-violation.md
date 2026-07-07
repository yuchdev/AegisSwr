# Runbook - Memory Access Violation

<!-- Worked example for /runbook-write. Shows the template filled with real Aegis
     fields (FaultClass, IncidentMode, RCAReport fields, consensus weights). Copy
     this shape; do not copy the content verbatim for a different fault class. -->

- Fault class / mode: `memory_access_violation` / `crash_dump`
- Severity default: P1
- Owner / escalation: platform on-call → `incident-analyst` for RCA sign-off

## Detection signals

- Aegis classifies the dump as `memory_access_violation` from the exception code:
  Windows `0xc0000005` (also `0xc0000374` heap corruption, `0xc0000409` stack
  buffer overrun), Linux SIGSEGV (`11`) / SIGBUS (`7`), macOS EXC_BAD_ACCESS (`1`).
- `RCAReport.confidence_level` HIGH with a populated `faulting_module` is the
  clean case; a LOW report with a `hitl_request` means the panel could not
  converge — treat as "diagnosis incomplete", not "no bug".
- `ConsensusEvaluated` events stall or oscillate across rounds → the two dominant
  agents disagree; expect HITL.

## Triage (first 5 minutes)

1. `aegis report show --incident <id> --field fault_class,faulting_module,exception_code_raw`
   - expected: `memory_access_violation` + a resolved module name.
2. Check `symbol_resolution_score` on the report - expected: ≥ 0.7. Below that,
   the stack is unreliable; pull symbols and re-run before trusting the module.
3. Confirm whether `hitl_request` is set - expected: null for a HIGH-confidence
   report. If set, read `context_summary` and gather the `requested_data`.

## Investigation

- Dominant consensus agents for this class: **os_kernel 0.40, code_analyst 0.35**
  (see [../references/fault-class-catalog.md](../references/fault-class-catalog.md)).
  os_kernel-dominant → trust the exception code, faulting module, and raw stack
  first; then read `primary_hypothesis.root_cause` and the code analyst's
  `code_location`.
- Read `skeptic_challenges` before acting - they list the alternative
  explanations the panel could not rule out.
- Pull the crash dump and (if present) the matching prior incident the Log
  Historian surfaced, to confirm recurrence vs first occurrence.

## Mitigation

1. Drain traffic from the faulting node - idempotent: yes; rollback:
   `aegis fleet undrain`; requires `AEGIS_PROD_CONFIRMED`: yes.
2. Roll the faulting service back to last known-good build - idempotent: no;
   rollback: redeploy current build; requires `AEGIS_PROD_CONFIRMED`: yes.
3. If `probabilistic_fix` is present and confidence is HIGH, route it to
   `python-expert` for a real patch - never auto-apply.

## Escalation

- Raise a `HITLRequest` / page platform on-call when: `confidence_level` is LOW,
  the Skeptic rejected the consensus, or `symbol_resolution_score` stays below
  0.7 after re-symbolication.
- Post to the incident Slack channel with the incident id and dominant hypothesis.

## Verification & resolution

- Confirm no new `memory_access_violation` crashes for the fault signature over a
  10-minute window post-mitigation.
- Mark resolved once a completed `RCAReport` (not a HITL one) is stored and the
  fix is merged; then file a post-mortem via `/post-mortem <incident-id>`.

## Related

- Fault catalog: [../references/fault-class-catalog.md](../references/fault-class-catalog.md)
- Consensus weights: `default_weight` ClassVars in `src/aegis_swr/agents/`
- ADRs / playbooks / prior post-mortems for this fault class (link as they exist).
