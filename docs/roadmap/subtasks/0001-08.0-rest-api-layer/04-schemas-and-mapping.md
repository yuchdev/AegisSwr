# 04 - Request/response schemas + options→source mapping

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 01
**Blocks:** 05, 06, 07, 08, 09, 10, 11

## Objective

Define the API's Pydantic request/response models - the HTTP mirror of
`AnalyzeConfig` plus result envelopes - and the pure mapping that turns an
`AnalyzeOptions` payload (+ uploaded file paths) into an `IncidentSource` and the
backend selection the orchestrator needs.

## Files

- **Create** `src/aegis_swr/api/schemas.py`
- **Create** `src/aegis_swr/api/mapping.py`

## Symbols

### `api/schemas.py`

- `AnalyzeOptions(BaseModel)` - 1:1 with the **non-file** `AnalyzeConfig` fields
  (`assume`, `engine`, `ai`, `store`, `store_config`, `code_provider`, `repo`,
  `log_provider`, `log_service`, `output`, severities, `log_sink`, …). Field
  validators mirror the CLI: `evidence_severity`/`process_severity` ∈
  `{INFO, TRACE}`, `log_sink` ∈ `{file, elk, fluent}`, enums for engine/ai/store.
- `AnalyzeAccepted(BaseModel)` - `incident_id: str`, `status: Literal["running"]`,
  `stream_url: str`, `report_url: str`.
- `ReportEnvelope(BaseModel)` - `status: Literal["running","complete","hitl","error"]`,
  `report: Optional[RCAReport]`, `error: Optional[str]`.
- `ContinueRequest(BaseModel)` - `responses: dict[str, Any]` (answers to the
  `HITLRequest`).
- `ConfigView` / `ConfigUpdate` - for subtask 11 (config endpoints).
- `ErrorResponse(BaseModel)` - `detail: str` (sanitised).
- SSE event doc-models (`SseDataAdapterComplete`, `SseAgentTurn`,
  `SseConsensusUpdate`, `SseComplete`, `SseHitlRequest`) for OpenAPI only - the
  wire shape stays the `run_streaming()` dicts.

### `api/mapping.py`

```python
def options_to_analyze_config(opts: AnalyzeOptions, uploads: UploadedPaths) -> AnalyzeConfig: ...
def build_source(config: AnalyzeConfig) -> IncidentSource: ...
def build_backends(config: AnalyzeConfig, settings: Settings) -> BackendFleet: ...
```

- reuse the **existing** `analyze` assembly logic (mode from dump presence;
  `metadata["repo_path"]`/`metadata["service"]`) so CLI and API produce identical
  sources; do not fork the logic.

## Constraints

- `AnalyzeOptions` rejects unknown fields (`extra="forbid"`) so typos surface as
  422 rather than silently ignored.
- Validation parity with the CLI (same allowed values, same error semantics).
- Pure functions; no I/O in `mapping.py` beyond reading the already-saved upload
  paths.

## Tests

**Unit** (`tests/unit/test_api_schemas.py`):

- `test_analyze_options_defaults_match_config` - unset options equal
  `AnalyzeConfig` defaults.
- `test_analyze_options_rejects_unknown_field` - extra key → `ValidationError`.
- `test_severity_validation` - `evidence_severity="DEBUG"` rejected;
  `INFO`/`TRACE` accepted.
- `test_options_to_source_crash_mode` - dump upload → `IncidentMode.CRASH_DUMP`,
  paths populated, `repo`/`service` land in `metadata`.
- `test_options_to_source_log_mode` - no dump → `IncidentMode.LOG_FORENSICS`.
- `test_build_source_matches_cli` - given the same inputs, the API source equals
  the CLI-assembled source field-for-field.

## Success criteria

- [ ] `AnalyzeOptions` covers every non-file `AnalyzeConfig` field with matching
      validation, rejecting unknown fields.
- [ ] `build_source`/`build_backends` reproduce the CLI's assembly exactly.
- [ ] Response envelopes serialise `RCAReport` and the HITL/error states.
- [ ] Unit tests pass.
