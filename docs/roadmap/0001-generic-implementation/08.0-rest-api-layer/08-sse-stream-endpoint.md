# 08 - SSE `GET /v1/incidents/{id}/stream`

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 06, 07
**Blocks:** 11

## Objective

Relay the **entire War Room discussion** - every intermediary agent step - to the
client as Server-Sent Events, in order, terminating on the final report or HITL
request. This is the headline requirement: all agents' intermediary steps stream
live.

## Files

- **Create** `src/aegis_swr/api/routes/stream.py`
- **Create** `src/aegis_swr/api/sse.py`

## Symbols

### `api/sse.py`

```python
def to_sse_event(event: dict[str, Any]) -> ServerSentEvent: ...
async def event_source(job: JobState, heartbeat_s: int = 15) -> AsyncGenerator[ServerSentEvent, None]: ...
```

- `to_sse_event`: map each `run_streaming` dict to an SSE frame whose `event:` is
  the dict's `type` (`data_adapter_complete`, `agent_turn`, `consensus_update`,
  `complete`, `hitl_request`) and `data:` is the JSON-encoded `data` (+ `node`
  for `agent_turn`).
- `event_source`: `await job.queue.get()` in a loop; yield each as SSE; on the
  `_end` sentinel (or a `complete`/`hitl_request`/`error`) close the stream; emit
  a heartbeat comment (`:keep-alive`) every `heartbeat_s` seconds while waiting.

### `api/routes/stream.py`

```python
@router.get("/v1/incidents/{incident_id}/stream")
async def stream(incident_id: str, _: None = Depends(verify_api_key)) -> EventSourceResponse: ...
```

- 404 when the registry has no such incident.
- returns `sse_starlette.EventSourceResponse(event_source(job))`.
- a late subscriber (job already complete) still receives the terminal
  `complete`/`hitl_request` then closes (the queue replays remaining items; if the
  queue was drained, fall back to emitting the stored `job.report`).

## Constraints

- Not per-event rate-limited (long-lived); only the initial open is auth-checked.
- Heartbeats keep proxies from closing idle connections.
- No payload/secret in SSE error frames; an `ERROR` job emits a sanitised
  `error` event then closes.
- Ordering is exactly the engine's emission order.

## Tests

**Integration / mock** (`tests/integration/test_api.py`, faked job queue):

- `test_stream_event_order` - events arrive as
  `data_adapter_complete → agent_turn (xN) → consensus_update (xN) → complete`.
- `test_stream_includes_every_agent_turn` - one `agent_turn` per agent per round
  is delivered (os_kernel, code_analyst, log_historian, skeptic).
- `test_stream_hitl_terminal` - a `hitl_request` closes the stream.
- `test_stream_unknown_id_404`.
- `test_stream_heartbeat_emitted` - a keep-alive comment appears during a gap.
- `test_stream_error_event_sanitised` - an `ERROR` job emits a sanitised error
  frame, no payload.

## Success criteria

- [ ] The SSE stream relays every War Room event in engine order and closes on
      the terminal event.
- [ ] Every agent's turn for every round is delivered.
- [ ] Unknown id → 404; heartbeats present; error frames sanitised.
- [ ] Integration tests pass with a faked job queue (no network/LLM).
