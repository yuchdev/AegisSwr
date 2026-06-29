# 10 - `POST /{id}/continue` (HITL persist)

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 06, 09
**Blocks:** 11

## Objective

Accept a human's answers to a `HITLRequest`, validate them, and persist them
against the paused incident, returning `202 Accepted`. The actual graph resume is
deferred until `Orchestrator.continue_investigation()` is implemented (Phase 6);
this endpoint defines the contract and stores the response without faking a run.

## Files

- **Modify** `src/aegis_swr/api/routes/incidents.py` (add the `continue` route)

## Symbols

```python
@router.post("/{incident_id}/continue", status_code=202)
async def continue_investigation(
    incident_id: str,
    body: ContinueRequest,
    _: None = Depends(verify_api_key),
) -> JSONResponse: ...
```

Flow:
1. resolve the job/report; require its state to be `HITL` (else `409 Conflict`
   "incident is not awaiting human input").
2. `await relational_store.update_hitl_response(UUID(incident_id), body.responses)`.
3. return `202 {"status": "accepted", "note": "resume deferred to Phase 6"}`.

Rate-limited (subtask 03), auth-gated (subtask 02).

## Constraints

- Do **not** call `Orchestrator.continue_investigation()` yet (it raises
  `NotImplementedError`); only persist via the existing
  `RelationalStore.update_hitl_response`.
- Validate `responses` shape against the pending `HITLRequest.requested_data`
  where available (reject empty/irrelevant payloads with 422).
- 404 for unknown incident; 409 when not in HITL state.
- The persisted response must not be logged in full (may contain user data).

## Tests

**Integration / mock** (`tests/integration/test_api.py`):

- `test_continue_persists_response_202` - a HITL-state incident → 202 and
  `update_hitl_response` called with the body (mock store).
- `test_continue_not_hitl_409` - a running/complete incident → 409.
- `test_continue_unknown_404`.
- `test_continue_requires_auth`.
- `test_continue_invalid_body_422` - empty/malformed `responses` → 422.

## Success criteria

- [ ] `POST /{id}/continue` persists the human response via
      `update_hitl_response` and returns 202.
- [ ] Returns 409 when the incident is not awaiting input, 404 when unknown.
- [ ] Does not invoke the unimplemented `continue_investigation()`.
- [ ] Integration tests pass with a mocked store.
