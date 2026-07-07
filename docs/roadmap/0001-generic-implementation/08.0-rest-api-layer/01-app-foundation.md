# 01 - App foundation: factory, lifespan/DI, exception handlers, health, server wiring

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** none
**Blocks:** 02-11 (every route mounts on this app)

## Objective

Stand up the FastAPI application skeleton everything else hangs off: a
`create_app(settings)` factory, a lifespan that constructs and disposes the
backend fleet once per process, dependency providers, centralised
domain-exception→HTTP mapping, an unauthenticated `/health` probe, and the
`aegis server` command wired to uvicorn. Add the two missing dependencies.

## Files

- **Create** `src/aegis_swr/api/__init__.py`
- **Create** `src/aegis_swr/api/app.py`
- **Create** `src/aegis_swr/api/dependencies.py`
- **Create** `src/aegis_swr/api/errors.py`
- **Create** `src/aegis_swr/api/routes/__init__.py`
- **Create** `src/aegis_swr/api/routes/health.py`
- **Modify** `src/aegis_swr/cli/commands.py` - wire the `server` command
- **Modify** `pyproject.toml` - add `sse-starlette`, `python-multipart`

## Symbols

### `api/app.py`

```python
def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build the Aegis SWR FastAPI app (routers, middleware, lifespan)."""
```

- `@asynccontextmanager async def _lifespan(app)`: on startup build the backend
  fleet (`create_ai_backend`, `create_debug_backend`, `create_storage_backends`,
  `create_log_backend`, `create_code_backend`) from `settings` and stash them on
  `app.state`; on shutdown close any backends exposing `aclose()`/`close()`.
- registers routers (health now; others added by their subtasks), the exception
  handlers from `errors.py`, and middleware (auth/rate-limit added in 02/03).
- OpenAPI metadata: title `Aegis SWR API`, version, description, tag set.

### `api/dependencies.py`

```python
def get_settings(request: Request) -> Settings: ...
def get_backends(request: Request) -> BackendFleet: ...        # from app.state
def get_orchestrator(request: Request) -> Callable[..., Orchestrator]: ...
```

- `BackendFleet` is a small dataclass holding the constructed backends + a
  per-request `Orchestrator` factory (so each investigation gets a fresh
  `EventBus`). No business logic in routes - they consume these providers.

### `api/errors.py`

```python
def register_exception_handlers(app: FastAPI): ...
```

Maps the `AegisSWRError` hierarchy to HTTP, **with sanitised bodies** (never raw
payloads/secrets):

| Exception | Status |
|-----------|--------|
| `IncidentNotFoundError` | 404 |
| `AIOutputValidationError` | 502 |
| `AIBackendError` | 502 |
| `DebugExtractionError` | 422 |
| `CodeBackendError` | 200-path (fails open) / 502 if surfaced |
| `ValueError` (validation) | 400 |
| `AegisSWRError` (catch-all) | 500 |

### `api/routes/health.py`

- `GET /health` → `{"status": "ok", "version": ...}`; no auth, no rate limit.

### `cli/commands.py`

- Replace the stub body of `server(...)` with
  `uvicorn.run("aegis_swr.api.app:create_app", factory=True, host=..., port=..., reload=...)`
  using `APISettings` defaults; keep the `--host/--port/--reload` flags.

## Constraints

- Backends are built **once per process** in the lifespan, not per request.
- Error bodies are sanitised; no incident payload or secret in any response.
- `streaming requires --workers 1` documented in the `server` help text.
- Full annotations; `replace_optional.py --check` clean.

## Tests

**Unit / mock** (`tests/unit/test_api_app.py`, FastAPI `TestClient`, backends
patched):

- `test_health_ok_no_auth` - `GET /health` → 200 without a key.
- `test_lifespan_builds_and_closes_backends` - startup constructs the fleet,
  shutdown calls close on closeable backends (assert via mocks).
- `test_exception_handler_maps_incident_not_found` - a route raising
  `IncidentNotFoundError` → 404 with a sanitised body.
- `test_exception_handler_sanitises_body` - a raised `AIBackendError` body
  contains no payload/secret text.
- `test_server_command_invokes_uvicorn` - `aegis server` calls `uvicorn.run`
  with the configured host/port (patch `uvicorn.run`).

## Success criteria

- [ ] `create_app()` returns a mountable FastAPI app; `/health` is 200 without auth.
- [ ] Backends are built/closed exactly once via the lifespan.
- [ ] Every `AegisSWRError` subtype maps to a defined, sanitised HTTP response.
- [ ] `aegis server` boots the app via uvicorn.
- [ ] `sse-starlette` and `python-multipart` are in `pyproject.toml`.
- [ ] Unit tests pass with backends mocked (no network).
