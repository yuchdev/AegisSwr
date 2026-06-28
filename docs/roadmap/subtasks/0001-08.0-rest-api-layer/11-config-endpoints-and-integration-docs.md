# 11 - Config read/write + E2E integration tests + OpenAPI/API docs

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 01-10
**Blocks:** none (final subtask; flips the milestone to ✅)

## Objective

Expose server configuration over REST (the `config show`/`config set` equivalent),
add the cross-cutting end-to-end integration suite, and produce the OpenAPI
artifact + API reference per the docs mandate.

## Files

- **Create** `src/aegis_swr/api/routes/config.py`
- **Create** `tests/integration/test_api.py` (if not already started in 07-10;
  otherwise extend - this subtask owns the full-flow tests)
- **Create** `docs/api/rest-reference.md`
- **Create** `docs/api/openapi.json` (generated artifact)
- **Modify** `docs/README.md` - index the API docs

## Symbols

### `api/routes/config.py`

```python
@router.get("/v1/config", response_model=ConfigView)
async def get_config(_: None = Depends(verify_api_key), settings: Settings = Depends(get_settings)) -> ConfigView: ...

@router.put("/v1/config", status_code=200)
async def update_config(body: ConfigUpdate, _: None = Depends(verify_api_key)) -> JSONResponse: ...
```

- **GET**: return the effective config with **secrets redacted** (`***`), mirroring
  `aegis config show` (reuse its redaction helper).
- **PUT**: validate `ConfigUpdate` against the `AnalyzeConfig`/`Settings` schema;
  write to `~/.aegis-swr/config.json` via the existing `save_analyze_config`
  path; **allowlist** mutable keys and **reject** any secret-bearing field (API
  keys, AWS creds) with `403`; append an audit line to `.claude/logs` per the
  audit-trail mandate.

## Constraints (security-sensitive - this is the riskiest endpoint)

- Read redacts every secret; write is allowlisted, validated, and audited.
- Writing a secret-bearing field over REST is rejected (`403`) - secrets stay in
  env only.
- Both require auth; `PUT` is rate-limited.

## Tests

### Config (`tests/integration/test_api.py`)

- `test_config_get_redacts_secrets` - GET shows `***` for secret fields.
- `test_config_put_updates_allowed_key` - a safe key round-trips to the file.
- `test_config_put_rejects_secret_field_403`.
- `test_config_put_invalid_422`.

### Full-flow integration (the milestone's headline tests)

- `test_analyze_to_stream_to_report` - `POST /analyze` → consume SSE
  (`data_adapter_complete → agent_turn xN → consensus_update → complete`) →
  `GET /report` returns the same `RCAReport` with full `agent_dialogue`.
- `test_auth_401_across_routes` - every protected route rejects a missing key.
- `test_rate_limit_429` - analyze beyond the cap → 429.
- `test_hitl_flow` - a HITL-terminating run streams `hitl_request`, and
  `POST /continue` persists the response (202).
- `test_artifact_download_roundtrip`.
- All with a mocked orchestrator/backends - **zero network, no real LLM**.

### OpenAPI

- `test_openapi_lists_all_routes` - the generated schema includes analyze,
  stream, report, artifacts, continue, config, health.

## Docs

- `docs/api/rest-reference.md` - endpoint table (method, path, auth, request,
  responses, SSE event catalogue), the `--workers 1` streaming caveat, and the
  HITL-resume-deferred note.
- `docs/api/openapi.json` - exported from `create_app().openapi()`.
- refresh `docs/README.md` index.

## Success criteria

- [ ] `GET /v1/config` redacts secrets; `PUT /v1/config` is allowlisted,
      validated, audited, and rejects secret-bearing fields.
- [ ] The end-to-end analyze→stream→report flow passes with a mocked engine,
      asserting all intermediary agent steps stream and the final report carries
      `agent_dialogue`.
- [ ] Auth/rate-limit/HITL/artifact flows covered.
- [ ] OpenAPI artifact + API reference produced; `docs/README.md` updated.
- [ ] `poetry run pytest tests/integration/test_api.py -q` passes with no network.
