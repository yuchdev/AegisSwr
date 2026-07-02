# Fault-class catalog (for runbook authoring)

Cross-reference for `/runbook-write`. Maps each `FaultClass`
(`src/aegis_swr/core/fault_codes.py`) to the incident modes it appears in, the
consensus agents that dominate its analysis (from
[`agents.example.json`](../../../../agents.example.json)), and a **suggested**
default severity.

> The dominant-agent column is authoritative — it is read directly from the
> weight matrix. The severity column is a *starting recommendation only*; the
> product does not hard-code severity per fault class, so tune it per deployment
> and let `incident-analyst` confirm.

## IncidentMode values

`crash_dump`, `log_forensics`, `live_process`, `telemetry_anomaly`
(`schemas.IncidentMode`). A runbook's `trigger` is usually `<mode>/<fault_class>`.

## Fault classes → dominant agents → suggested severity

| FaultClass | Dominant agents (weight) | Suggested default | Typical mode |
|------------|--------------------------|-------------------|--------------|
| `memory_access_violation` | os_kernel 0.40, code_analyst 0.35 | P1 | crash_dump |
| `null_pointer_dereference` | os_kernel 0.40, code_analyst 0.35 | P2 | crash_dump |
| `use_after_free` | code_analyst 0.40, os_kernel 0.35 | P1 | crash_dump |
| `stack_overflow` | os_kernel 0.45, code_analyst 0.30 | P2 | crash_dump |
| `integer_divide_by_zero` | code_analyst 0.40, os_kernel 0.35 | P2 | crash_dump |
| `deadlock` | os_kernel 0.35, code_analyst 0.30, log_historian 0.20 | P1 | live_process |
| `assertion_failure` | code_analyst 0.45, os_kernel 0.25 | P2 | crash_dump |
| `resource_exhaustion` | os_kernel 0.35, log_historian 0.30, code_analyst 0.25 | P1 | telemetry_anomaly |
| `unhandled_exception` | code_analyst 0.35, os_kernel 0.30 | P2 | crash_dump / log_forensics |
| `unknown` | code_analyst 0.35, os_kernel 0.30 | P2 | any |

**Reading the dominant-agent column into a runbook:** the highest-weighted agent
tells you which analysis to trust first. `os_kernel`-dominant faults
(access violations, stack overflow) → read `RCAReport.faulting_module`,
`exception_code_raw`, and the raw stack first. `code_analyst`-dominant faults
(use-after-free, assertion, unhandled exception) → read the primary
`Hypothesis.root_cause`, `code_location`, and any `probabilistic_fix`.
`log_historian` weight ≥ 0.20 (deadlock, resource exhaustion) → the recurrence
history and temporal pattern matter; check for a matching prior incident.

## Native fault-code sources (for the Detection signals section)

`fault_codes.py` maps platform codes to `FaultClass`:

- **Windows NTSTATUS/HRESULT** (`map_windows_ntstatus`): e.g. `0xc0000005`,
  `0xc0000374` (heap corruption), `0xc0000409` (stack buffer overrun) →
  `memory_access_violation`; `0xc00000fd` → `stack_overflow`.
- **Linux signals** (`map_linux_signal`): `11` SIGSEGV / `7` SIGBUS →
  `memory_access_violation`; `8` SIGFPE → `integer_divide_by_zero`;
  `6` SIGABRT → `assertion_failure`.
- **macOS Mach exceptions** (`map_macos_exception`): `1` EXC_BAD_ACCESS →
  `memory_access_violation`; `3` EXC_ARITHMETIC → `integer_divide_by_zero`.

Cite the specific code(s) in the runbook's **Detection signals** so on-call can
recognise the fault from the raw dump.

## RCAReport fields worth naming in a runbook

`root_cause`, `faulting_module`, `faulting_function`, `confidence_level`
(HIGH ≥ 0.80 / MEDIUM ≥ 0.50 / LOW), `primary_hypothesis`, `skeptic_challenges`,
`mitigation_instructions`, `probabilistic_fix`, and `hitl_request` (present only
when the panel escalated). Point on-call at the ones that matter for this fault.
