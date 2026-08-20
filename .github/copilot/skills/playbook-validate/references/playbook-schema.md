# Playbook schema & validation rules

The authoritative field vocabulary is defined by the Remediation Planner
alignment spec
([docs/roadmap/0002-forensic-agents/07.0-remediation-planner-agent/04-playbook-validate-alignment.md](../../../../../docs/roadmap/0002-forensic-agents/07.0-remediation-planner-agent/04-playbook-validate-alignment.md)).
A validated `RemediationPlan` (via its adapter shim) must satisfy everything below.
This reference is what the `SKILL.md §Checks` steps validate against — keep the two
in sync.

## Playbook-level fields (all required)

| Field | Type | Rule |
|-------|------|------|
| `id` | str | Non-empty. From `RCAReport.incident_id` (UUID str-cast) in the adapter. |
| `name` | str | Human-readable. |
| `trigger` | str | Fault class / `IncidentMode` / signal. Adapter form: `"<mode>/<fault_class>"`, e.g. `crash_dump/memory_access_violation`. Must match a real `IncidentMode` × `FaultClass`. |
| `steps` | list | ≥ 1 step; see step schema. |
| `owner` | str | Team or service. Adapter constant: `aegis_swr:remediation_planner`. |
| `severity` | str | `P0`\|`P1`\|`P2`\|`P3`. Adapter maps `ConfidenceLevel`: HIGH→P1, MEDIUM→P2, LOW→P3. |

## Per-step fields (all required)

| Field | Type | Rule |
|-------|------|------|
| `id` | str | Unique within the playbook. Adapter form `step-NN`. |
| `description` | str | What the step does, in prose. |
| `action` | str | The concrete command/API call/operation. |
| `idempotent` | bool | Explicit. If `false`, see the idempotency rule below. |
| `rollback` | str | How to undo. Read-only steps use the exact sentinel `read-only: no state change`. |
| `requires_authorisation` | bool | `true` for any production-affecting step. Maps from `requires_human_approval`. |
| `timeout` | str | Bounded duration, e.g. `300s`, `5m`. No unbounded/absent timeouts. |

## Validation rules (what makes a playbook INVALID vs a Warning)

### Blocking errors → **INVALID**

1. **Missing required field** — any playbook-level or step-level field above absent.
2. **Rollback gap** — a state-changing step (`idempotent: false` **or**
   `requires_authorisation: true`) whose `rollback` is the read-only sentinel
   `read-only: no state change`. A step that changes state cannot claim to be
   read-only — this is the cross-field validator from the alignment spec §"Idempotency
   and rollback coverage rules".
3. **Ordering violation** — a remediation/containment step runs *before* the
   triggering condition is confirmed. Canonical order:
   `detect/confirm → contain → remediate → verify`.
4. **Unbounded step** — `timeout` missing or non-numeric/duration.
5. **Consensus weights** (`default_weight` ClassVars in `src/aegis_swr/agents/`):
   a registered agent missing a numeric weight, or the built-in roster not
   summing to `1.0 ± 0.01`, or a single agent weight above a sane ceiling (~0.60).

### Non-blocking warnings

- A step with `requires_authorisation: true` but no `AEGIS_PROD_CONFIRMED` context
  documented (advisory-mode reminder).
- A plan derived from a `RemediationPlan` with `confidence < 0.70` — advisory only,
  `requires_human_approval` should already be `true`; flag but do not block.
- A step whose `description` and `action` are identical for every step (adapter
  fallback) — legal but low-signal.

## Ordering heuristic

Classify each step's intent from its `action`/`description`:

- **detect/confirm** — reads state, confirms the trigger fired (no `requires_authorisation`).
- **contain** — limits blast radius (isolate node, disable feature flag).
- **remediate** — the fix that changes production state (`requires_authorisation: true`).
- **verify** — reads state to confirm resolution.

Reject if any `remediate` step precedes the first `detect/confirm`, or if a
`verify` step precedes the `remediate` it verifies.

## Consensus weights

Consensus weight is not a file — it is a `default_weight` `ClassVar` declared on
each agent class in `src/aegis_swr/agents/` (a flat scalar per agent, no longer a
per-fault-class matrix). Validate: every registered agent
(`os_kernel`, `code_analyst`, `log_historian`, `skeptic`) declares a numeric
`default_weight`, and the built-in roster's weights sum to `1.0 ± 0.01`.
