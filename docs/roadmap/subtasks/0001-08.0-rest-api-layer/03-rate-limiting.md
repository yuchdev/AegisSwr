# 03 - Rate limiting (slowapi)

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 01
**Blocks:** 06-10 (applied to mutating/expensive routes)

## Objective

Protect the expensive endpoints (analyze, continue) from abuse with a
per-client request cap, returning `429` with a `Retry-After` hint.

## Files

- **Create** `src/aegis_swr/api/middleware/rate_limit.py`
- **Modify** `src/aegis_swr/api/app.py` - register the limiter + 429 handler

## Symbols

### `api/middleware/rate_limit.py`

```python
def build_limiter(settings: Settings) -> Limiter: ...
def install_rate_limiting(app: FastAPI, settings: Settings) -> None: ...
```

- `slowapi.Limiter(key_func=...)`: key by API key when present, else client host.
- default limit from `APISettings.rate_limit_per_minute` (10/min).
- register `_rate_limit_exceeded_handler` → `429` with `Retry-After`.
- expose a `limit` decorator/marker applied to `POST /analyze` and
  `POST /{id}/continue`; read-only GETs (report, stream, health) are exempt or
  use a looser bucket (SSE must not be throttled mid-stream).

## Constraints

- Keying by API key (not just IP) so shared-NAT clients aren't collectively
  throttled; fall back to host when unauthenticated.
- The SSE stream endpoint is **not** rate-limited per-event (long-lived
  connection); only its initial open counts.
- 429 body is generic, no internal counters leaked.

## Tests

**Unit / mock** (`tests/unit/test_api_rate_limit.py`, `TestClient`):

- `test_under_limit_passes` - N calls within the window all succeed.
- `test_over_limit_429` - the (limit+1)th call in the window → 429 with
  `Retry-After`.
- `test_limit_keyed_by_api_key` - two different keys have independent buckets.
- `test_stream_not_throttled` - opening the SSE stream is not blocked by the
  analyze bucket.

## Success criteria

- [ ] Analyze/continue enforce `rate_limit_per_minute`; excess → 429 + `Retry-After`.
- [ ] Buckets key by API key, falling back to host.
- [ ] The SSE stream is not throttled per-event.
- [ ] Unit tests pass.
