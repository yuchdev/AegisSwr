# 07 - `POST /v1/incidents/analyze`

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 02, 03, 04, 05, 06
**Blocks:** 08 (stream consumes the job this creates)

## Objective

The entry point: accept a multipart investigation request, kick off the run in
the background, and return `202` with an `incident_id` and the stream/report URLs
**fast** (no synchronous LLM call on the request path).

## Files

- **Create** `src/aegis_swr/api/routes/incidents.py` (the `analyze` route; the
  `continue` route is subtask 10)

## Symbols

```python
router = APIRouter(prefix="/v1/incidents", tags=["incidents"])

@router.post("/analyze", status_code=202, response_model=AnalyzeAccepted)
async def analyze(
    request: Request,
    _: None = Depends(verify_api_key),
    settings: Settings = Depends(get_settings),
) -> AnalyzeAccepted: ...
```

Flow:
1. generate `incident_id` (UUID4).
2. `uploads, options = await ingest_upload(incident_id, await request.form(), settings, object_store)`.
3. `config = options_to_analyze_config(options, uploads)`;
   `source = build_source(config)`; `fleet = build_backends(config, settings)`.
4. `job = registry.create(incident_id)`; build `Orchestrator(...)` with a fresh
   `EventBus`; `asyncio.create_task(run_investigation_job(job, orch, source, relational_store, uploads))`.
5. return `AnalyzeAccepted(incident_id, status="running", stream_url=..., report_url=...)`.

Rate-limited (subtask 03); auth-gated (subtask 02).

## Constraints

- Must return within ~200 ms: no `await orchestrator.run(...)` on the request
  path - only task creation.
- Validation errors (bad options, oversize upload) surface as 422/413 **before**
  a job is created (no orphan jobs).
- On ingestion failure, `cleanup_uploads` runs before returning the error.

## Tests

**Integration / mock** (`tests/integration/test_api.py`, orchestrator faked):

- `test_analyze_returns_202_fast` - multipart with a dummy dump → 202 +
  `incident_id`; assert no synchronous orchestrator.run call.
- `test_analyze_creates_job` - a `JobState` exists in the registry afterwards.
- `test_analyze_requires_auth` - no key → 401, no job created.
- `test_analyze_invalid_options_422` - bad `options` JSON → 422, no job created.
- `test_analyze_oversize_413` - oversize upload → 413, no job created.

## Success criteria

- [ ] `POST /analyze` returns 202 with `incident_id` + stream/report URLs quickly.
- [ ] A background job is created and starts draining `run_streaming`.
- [ ] Auth/rate-limit/validation enforced before job creation.
- [ ] Integration tests pass with a mocked orchestrator (no network/LLM).
