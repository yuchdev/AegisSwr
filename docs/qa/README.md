# Manual QA Scenarios

Step-by-step walkthroughs that trace a complete Aegis SWR investigation from raw
artifacts through the final RCA report. Each scenario is self-contained and
illustrative: data is clearly fabricated; no real customer incidents or sensitive
payloads appear.

Use scenarios to validate end-to-end pipeline behaviour after significant changes,
onboard contributors who are unfamiliar with the processing pipeline, and serve as
living examples of what the system produces for specific fault classes.

## Naming convention

`NNNN-kebab-slug.md` — sequential, zero-padded to four digits, followed by a
concise slug describing the affected component and fault type.

Examples:

- `0001-audacity4-corrupted-vst3-plugin-startup-crash.md`
- `0002-webserver-use-after-free-on-tls-teardown.md`
- `0003-linux-oom-kill-in-batch-processor.md`

## Required sections

Every walkthrough document must contain the following sections in this order.
Section headings must match exactly (anchor slugs are linked from the index).

### 1. Scenario Summary

One paragraph: what software, what fault, what artifacts are provided, and what
outcome the investigation is expected to reach. Explicitly state that the scenario
is illustrative and the data is fabricated.

### 2. Artifacts Provided

A table of every input file passed to `aegis analyze`. For each artifact:

| Field | Value |
|---|---|
| Type | `dump` / `log` / `screenshot` / `code` |
| Filename | Descriptive filename (fabricated) |
| Description | What the artifact contains |

### 3. CLI Invocation

The exact `aegis analyze` command an operator would run, using placeholder paths.
Refer to [docs/config/cli.md](../config/cli.md) for option definitions.

```bash
aegis analyze \
  --dump <path/to/dump.dmp> \
  --log  <path/to/app.log>  \
  ...
```

### 4. Pipeline Trace — INITIALIZING

Cover:

- `IncidentSource` construction: which fields are populated.
- `Settings` overrides applied (engine, AI provider, storage backend).
- `Orchestrator` instantiation: which backends are passed in.

### 5. Pipeline Trace — EXTRACTING (Data Adapter)

Trace all nine `DataAdapter.process()` stages:

| Stage | What it does | Illustrative output |
|---|---|---|
| 1 | Source validation + SHA-256 hash | `sha256:<hex>`, `DumpFormat.WINDOWS_MINIDUMP` |
| 2 | Dump extraction (DebugBackend / cdb.exe) | Exception code, faulting module, stack frames |
| 3 | Noise pre-filter | Lines removed, fill patterns collapsed |
| 4 | Log processing (temporal window + Drain3 dedup) | Windowed + clustered log lines |
| 5 | Screenshot OCR (Tesseract + Pillow) | Extracted UI text |
| 6 | PII scrubbing (regex baseline + optional Presidio) | Redacted tokens, if any |
| 7 | User-assumption token cap | Truncated / unchanged |
| 8 | Code-history query (CodeBackend) | `CommitRecord` list |
| 9 | `IncidentBrief` assembly | Key `IncidentBrief` fields populated |

Note any `low_symbol_coverage_warning` that is generated.

### 6. Pipeline Trace — ANALYZING (Panel Resolution)

Cover:

- Which `AgentSpec` objects the `PanelResolver` selects and why (fault class,
  tags).
- The resolved panel in priority order (investigators descending priority,
  arbiter last).
- The consensus weight map (`resolve_consensus_weights` output).
- The compiled LangGraph node chain.

### 7. Pipeline Trace — ANALYZING (Agent Debate)

For each debate round, document every agent turn:

- **Agent name and role** (`INVESTIGATOR` or `ARBITER`).
- **Input context**: what the agent received (brief excerpt, preceding turn,
  arbiter feedback if round > 1).
- **Output summary**: hypothesis, confidence score, corrections / fix annotation
  (redact any payload text).
- **Round consensus score** (`ConsensusEvaluator.calculate` result) and whether
  convergence criteria were met.

Repeat for each round until convergence or HITL escalation.

### 8. Pipeline Trace — STORING (Output Synthesis)

Cover:

- Route taken: `output_synthesizer_node` (converged) or `hitl_node` (limit
  reached).
- `RCAReport` fields populated (see `core/schemas.py`).
- Persistence: relational store and vector store (best-effort; note any stubs).
- `RemediationPlannerAgent.run_synthesis()` invocation and the resulting
  `RemediationPlan` (if `remediation_planner` is in `settings.panel.enabled_synthesis`).

### 9. Final RCA Report

Show the key `RCAReport` fields in a structured block. Do not include raw stack
text or log excerpts — reference the fabricated values established in §5.

```json
{
  "incident_id": "<uuid4>",
  "mode": "crash_dump",
  "root_cause": "...",
  "faulting_module": "...",
  "faulting_function": "...",
  "confidence_score": 0.0,
  "confidence_level": "high|medium|low",
  "consensus_rounds": 0,
  "hitl_request": null
}
```

### 10. Suggested Remediation

The `RemediationPlan` produced by the synthesis tier:

- `summary` paragraph.
- Each `RemediationStep` (order, action, idempotent, rollback,
  `requires_human_approval`).
- Confirmation that the plan is **advisory** — no step is auto-dispatched
  without operator confirmation (`AEGIS_PROD_CONFIRMED=1`).

### 11. Security and Redaction Notes

Summarise how the scenario demonstrates Aegis SWR's security posture:

- What PII scrubbing tokens (if any) were emitted.
- That no raw stack text, log payloads, or user data appears in the report.
- Any `SensitiveFilter` or sandbox-boundary notes relevant to the scenario.

## Relationship to automated tests

Manual QA scenarios are not unit or integration tests. They complement the
`tests/` suite by covering the full observable pipeline with human-readable
narrative. When a scenario reveals a defect, the fix must be accompanied by a
regression test in `tests/unit/` or `tests/integration/`; the scenario itself
is updated to note the resolution.

## Adding a new scenario

1. Choose the next sequence number and create
   `docs/qa/NNNN-descriptive-slug.md`.
2. Follow the required sections above.
3. Add a row to the **Manual QA Scenarios** table in
   [docs/README.md](../README.md).
4. Run `python scripts/check_doc_links.py` to verify all relative links
   resolve.

<!-- SME REVIEW NEEDED: confirm the Drain3 clustering and Presidio NER
     sections accurately reflect production configuration once those
     backends are exercised in a live environment. -->
