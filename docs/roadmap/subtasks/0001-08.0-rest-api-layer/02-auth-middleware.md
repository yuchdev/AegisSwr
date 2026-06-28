# 02 - API-key authentication (bcrypt)

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 01
**Blocks:** 06-10 (all protected routes)

## Objective

Gate every endpoint except the public probes behind an `X-Aegis-API-Key` header,
compared against bcrypt-hashed key(s) from settings/env. No plaintext key is ever
stored in config or logged.

## Files

- **Create** `src/aegis_swr/api/middleware/__init__.py`
- **Create** `src/aegis_swr/api/middleware/auth.py`
- **Modify** `src/aegis_swr/config/settings.py` - `APISettings` hashed-key field
- **Modify** `src/aegis_swr/api/app.py` - attach the auth dependency/middleware

## Symbols

### `APISettings` addition

- `api_key_hashes: list[str] = Field(default_factory=list)` - bcrypt hashes of
  accepted keys, read from env (`AEGIS__API__API_KEY_HASHES`); **never** plaintext.
- keep existing `api_key_header: str = "X-Aegis-API-Key"`.

### `api/middleware/auth.py`

```python
def verify_api_key(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """FastAPI dependency: 401 unless a valid X-Aegis-API-Key is presented."""

_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})
```

- read the header named by `settings.api.api_key_header`; missing → 401.
- `bcrypt.checkpw(presented, hash)` against each configured hash; constant-time,
  no early "which key" disclosure; no match → 401.
- exempt the probe/docs paths.
- attach as a router-level dependency (preferred) or `BaseHTTPMiddleware`; the
  dependency form composes with per-route `Depends`.

## Constraints

- Never log the presented key or the hashes; log only `auth ok/denied` + path.
- 401 body is generic (`{"detail": "invalid or missing API key"}`) - no hint
  about which check failed.
- When `api_key_hashes` is empty, fail **closed** (401) unless a documented
  `AEGIS__API__AUTH_DISABLED=1` dev escape is set (logged as a warning).

## Tests

**Unit / mock** (`tests/unit/test_api_auth.py`, `TestClient`):

- `test_missing_key_401` - protected route without the header → 401.
- `test_invalid_key_401` - wrong key → 401.
- `test_valid_key_passes` - a key whose bcrypt hash is configured → 200.
- `test_health_exempt` - `/health` works with no key.
- `test_key_never_logged` - captured logs contain neither the key nor the hash.
- `test_empty_hashes_fail_closed` - no configured hashes → 401 (unless dev escape).

## Success criteria

- [ ] All non-exempt routes require a valid `X-Aegis-API-Key`.
- [ ] Keys are compared via bcrypt against hashes from env; no plaintext stored.
- [ ] 401 bodies are generic; keys/hashes never logged.
- [ ] Empty-hash config fails closed.
- [ ] Unit tests pass.
