# 09 - `GET /{id}/report` + raw-artifact download

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 06
**Blocks:** 11

## Objective

Serve the final result by id (the `RCAReport`, which already embeds the full
`agent_dialogue`), and let clients download the stored raw artifacts they
uploaded. No list/history endpoint (out of scope per the milestone decision).

## Files

- **Create** `src/aegis_swr/api/routes/reports.py`
- **Create** `src/aegis_swr/api/routes/artifacts.py`

## Symbols

### `api/routes/reports.py`

```python
@router.get("/v1/incidents/{incident_id}/report", response_model=ReportEnvelope)
async def get_report(incident_id: str, _: None = Depends(verify_api_key)) -> JSONResponse: ...
```

- if the job is still `RUNNING` → `202` with `{"status": "running"}`.
- if `COMPLETE`/`HITL` → `200` with the `RCAReport` (from the job, else
  `relational_store.get_report(UUID(incident_id))`).
- if `ERROR` → `200`/`500` envelope with sanitised `error`.
- unknown id (no job and no stored report) → `404`.

### `api/routes/artifacts.py`

```python
@router.get("/v1/incidents/{incident_id}/artifacts/{object_key:path}")
async def get_artifact(incident_id: str, object_key: str, _: None = Depends(verify_api_key)) -> StreamingResponse: ...
```

- fetch bytes via `object_store.get_raw(object_key)`; stream back with a generic
  `application/octet-stream` content type.
- `object_key` must be validated to belong to `incident_id` (prefix check) - no
  cross-incident or traversal access.
- 404 when the key is unknown or no object store is configured.

## Constraints

- The report is served from the in-memory job first, then the relational store
  (covers post-restart retrieval when persisted).
- Artifact access is auth-gated and incident-scoped; never serve arbitrary keys.
- Report bodies are already sanitised at creation (PII scrubbed upstream); do not
  re-expose raw payload beyond the stored artifact the uploader provided.

## Tests

**Integration / mock** (`tests/integration/test_api.py`):

- `test_report_202_while_running`.
- `test_report_200_when_complete` - returns the `RCAReport` incl. `agent_dialogue`.
- `test_report_from_store_after_job_gone` - job removed, report still served from
  the relational store.
- `test_report_unknown_404`.
- `test_artifact_roundtrip` - upload key → `get_raw` bytes returned (mock store).
- `test_artifact_cross_incident_denied` - a key not prefixed by the incident →
  404/403.
- `test_artifact_requires_auth`.

## Success criteria

- [ ] `GET /{id}/report` returns 202 while running, 200 with the full report when
      done, 404 for unknown ids.
- [ ] Reports are served from the job and fall back to the relational store.
- [ ] Artifact download is auth-gated, incident-scoped, and traversal-safe.
- [ ] Integration tests pass with mocked stores (no network).
