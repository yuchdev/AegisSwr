# Subtask set 0001-08.0 - REST API Layer

Atomic decomposition of milestone **8 REST API Layer** from
[`docs/roadmap/tasks/0001-generic_implementation_plan.md`](../../tasks/0001-generic_implementation_plan.md).
Progress is tracked in
[`docs/roadmap/progress/implementation_status.md`](../../progress/implementation_status.md).

## Goal

Expose every capability currently reachable through the CLI/config as REST calls,
and stream the **full War Room discussion** - every intermediary agent step - back
to clients. The FastAPI layer is a thin transport over the existing engine: the
`Orchestrator` already emits a JSON-serializable event stream
(`run_streaming()`), so the API becomes a second consumer of the same `EventBus`
the CLI's `WarRoomView` subscribes to. No orchestration logic is duplicated.

## Confirmed design decisions

- **Execution model: background + SSE.** `POST /analyze` starts the run
  asynchronously and returns `202 {incident_id}`; `GET /{id}/stream` relays every
  War Room step live; `GET /{id}/report` returns `202` while running and `200`
  with the `RCAReport` when done.
- **Ingestion: multipart upload.** Clients upload artifact bytes (dump, logs,
  screenshots, pcaps, symbols) plus an `options` JSON field; the server persists
  them and builds an `IncidentSource`.
- **Endpoint scope:** analyze + stream + report-fetch-by-id, raw-artifact
  download, and config read/write. **No list/history endpoint** (report fetch is
  by id only).
- **HITL:** `POST /{id}/continue` validates and persists the human response via
  `RelationalStore.update_hitl_response()` and returns `202`; the actual graph
  resume is deferred until `continue_investigation()` lands (Phase 6).
- **Auth:** `X-Aegis-API-Key` header, bcrypt-hashed key compare; `/health`,
  `/docs`, `/openapi.json` exempt.
- **Concurrency:** single-process in-memory job registry (per-incident
  `asyncio.Queue`). SSE streaming and background jobs require **`--workers 1`**;
  multi-worker shared-state is a documented, deferred follow-up.

## Why "all intermediary steps" is already satisfiable

`Orchestrator.run_streaming()` yields exactly these dict shapes, in order:

```
{"type": "data_adapter_complete", "data": <IncidentBrief dict>}
{"type": "agent_turn", "node": "<os_kernel|code_analyst|log_historian|skeptic>_node",
                        "data": <AgentTurn JSON>}     # one per agent, per round
{"type": "consensus_update", "data": {"score": float, "round": int}}
{"type": "complete",     "data": <RCAReport JSON>}    # terminal, OR
{"type": "hitl_request", "data": <RCAReport JSON>}    # terminal
```

The terminal `RCAReport` also embeds `agent_dialogue: list[AgentTurn]`, so the
full step record is recoverable from the stored report as well as live.

## Design agreements honoured (from `.claude/CLAUDE.md` & root `CLAUDE.md`)

- **Thin transport / Factory-Strategy**: routes assemble sources + backends via
  the existing factories and call the orchestrator; no business logic in routes.
- **Typing**: full annotations, `mypy --strict` clean, always `Optional[T]`.
- **Error handling**: every external call has a defined failure path; domain
  exceptions map to HTTP status via centralised handlers; no bare `except:`.
- **Security**: treat every uploaded payload as hostile - size caps, content
  allowlist, traversal-safe filenames; never log secrets or raw payloads;
  `SensitiveFilter` covers new sinks; bcrypt-hashed API keys; config read
  redacts secrets and config write is allowlisted + audited.
- **Testing**: every feature ships unit tests; every endpoint ships an
  integration test with the orchestrator/backends mocked (zero network, no LLM).
- **Docs**: refresh the OpenAPI artifact and API reference when `api/routes/`
  changes; keep `docs/README.md` index current.

## Subtasks

| # | Subtask | Primary files | State |
|---|---------|---------------|-------|
| [01](01-app-foundation.md) | App factory, lifespan/DI, exception handlers, `/health`, server wiring, deps | `api/app.py`, `api/dependencies.py`, `api/errors.py`, `api/routes/health.py` | ⬜ Pending |
| [02](02-auth-middleware.md) | API-key authentication (bcrypt) | `api/middleware/auth.py`, `config/settings.py` | ⬜ Pending |
| [03](03-rate-limiting.md) | Rate limiting (slowapi) | `api/middleware/rate_limit.py` | ⬜ Pending |
| [04](04-schemas-and-mapping.md) | Request/response schemas + options→source mapping | `api/schemas.py`, `api/mapping.py` | ⬜ Pending |
| [05](05-multipart-ingestion.md) | Multipart upload ingestion | `api/ingestion.py` | ⬜ Pending |
| [06](06-job-registry-and-runner.md) | In-memory job registry + background streaming runner | `api/jobs.py` | ⬜ Pending |
| [07](07-analyze-endpoint.md) | `POST /v1/incidents/analyze` | `api/routes/incidents.py` | ⬜ Pending |
| [08](08-sse-stream-endpoint.md) | SSE `GET /{id}/stream` | `api/routes/stream.py`, `api/sse.py` | ⬜ Pending |
| [09](09-report-and-artifact-endpoints.md) | `GET /{id}/report` + raw-artifact download | `api/routes/reports.py`, `api/routes/artifacts.py` | ⬜ Pending |
| [10](10-hitl-continue-endpoint.md) | `POST /{id}/continue` (HITL persist) | `api/routes/incidents.py` | ⬜ Pending |
| [11](11-config-endpoints-and-integration-docs.md) | Config read/write + E2E integration tests + OpenAPI/API docs | `api/routes/config.py`, `tests/integration/test_api.py`, `docs/api/` | ⬜ Pending |

## Dependency / sequencing

```
01 App foundation ─┬─► 02 Auth ──┐
                   ├─► 03 Rate limit ─┤
                   ├─► 04 Schemas/mapping ─► 05 Ingestion ─► 06 Job registry ─► 07 Analyze
                   │                                                              │
                   │                                              07 ─► 08 SSE stream
                   │                                              06 ─► 09 Report + artifact
                   │                                              06 ─► 10 HITL continue
                   └─► 11 Config + integration tests + OpenAPI/API docs  (last)
```

**Definition of done for the milestone:** 01-11 satisfied and green under
`poetry run pytest tests/unit/ tests/integration/ -q`; `mypy --strict` clean;
`ruff` clean; `aegis server` boots a working app; the OpenAPI artifact and API
reference are refreshed. When all land, flip the `8 REST API Layer` status row
from ⬜ Not started to ✅ Complete.
