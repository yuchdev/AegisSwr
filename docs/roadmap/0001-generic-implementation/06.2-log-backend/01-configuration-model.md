# 01 – Configuration model extension (`LogBackendSettings`)

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 06, 07

## Objective

Extend `LogBackendSettings` (currently a minimal stub) with the full set of
Fluent-specific connection, query, and multi-service fields needed to make the
adapter production-configurable. No implementation code yet - only the settings
model and its validator coverage.

The existing fields (`fluent_host`, `fluent_port`, `fluent_tag_prefix`) are
already present but unused by the stub; this subtask adds the remaining fields
and tightens the validator.

## Files

- **Modify** `src/aegis_swr/config/settings.py`
- **Modify** `config/config.example.json` (add `backends.log` expanded block)

## Classes / symbols

### `LogBackendSettings(BaseSettings)` - full field table

All new fields in **bold**; existing fields carried over unchanged.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `provider` | `str` | `"file"` | `file \| fluent` (elk deferred). Validated. |
| `file_root` | `Optional[str]` | `None` | Base dir for `FileLogAdapter`. |
| `default_severity_levels` | `list[str]` | `["FATAL","CRITICAL","ERROR","WARNING"]` | Passed as `severity_levels` when the caller supplies none. |
| `elk_url` | `Optional[str]` | `None` | ELK deferred. |
| `fluent_host` | `Optional[str]` | `None` | Fluentd / Fluent Bit hostname or IP. |
| `fluent_port` | `Optional[int]` | `None` | Port (Fluentd default `24224`; Fluent Bit HTTP default `2020`). |
| `fluent_tag_prefix` | `Optional[str]` | `None` | Tag prefix; `{prefix}.{service}` forms the full tag. |
| **`fluent_protocol`** | `str` | `"http"` | `http \| forward`. Chooses the query client. Validated. |
| **`fluent_query_path`** | `str` | `"/api/logs/query"` | HTTP path for log queries (only relevant when `fluent_protocol="http"`). |
| **`fluent_auth_token`** | `Optional[str]` | `None` | Bearer token for HTTP endpoints. Treated as a secret - `SensitiveFilter` must cover this field name. |
| **`fluent_tls_enabled`** | `bool` | `False` | Enable TLS for HTTP or forward protocol. |
| **`fluent_tls_ca_cert`** | `Optional[str]` | `None` | Path to CA bundle (PEM) for TLS verification. |
| **`fluent_tls_client_cert`** | `Optional[str]` | `None` | Path to client cert (PEM) for mutual TLS. |
| **`fluent_tls_client_key`** | `Optional[str]` | `None` | Path to client private key (PEM). Treated as secret. |
| **`fluent_query_timeout_seconds`** | `int` | `10` | Per-request network timeout. |
| **`fluent_connect_timeout_seconds`** | `int` | `5` | TCP connect timeout (forward protocol). |
| **`fluent_max_lines_per_service`** | `int` | `5000` | Hard cap on lines returned per service call (prevents unbounded memory). |
| **`fluent_default_window_minutes`** | `int` | `10` | Default ±window around the incident timestamp when no explicit window is passed. |
| **`fluent_services`** | `list[str]` | `[]` | Optional named list of services/subsystems to query by default in multi-service calls. Empty list means the caller must supply services explicitly. |

### Validator additions

```python
@field_validator("fluent_protocol")
@classmethod
def validate_fluent_protocol(cls, v: str) -> str:
    allowed = {"http", "forward"}
    if v not in allowed:
        raise ValueError(f"fluent_protocol must be one of {allowed}")
    return v
```

### Sensitive field coverage

`_SECRET_KEYS` in `settings.py` currently contains
`{"api_key", "password", "secret", "token", "database_url"}`. Add `"auth_token"`
and `"client_key"` so `redacted_dump()` and `SensitiveFilter` catch the new fields.

```python
_SECRET_KEYS = {
    "api_key", "password", "secret", "token",
    "database_url", "auth_token", "client_key",
}
```

### `config.example.json` block

```jsonc
"backends": {
  "log": {
    "provider": "fluent",
    "fluent_host": "localhost",
    "fluent_port": 9880,
    "fluent_tag_prefix": "aegis",
    "fluent_protocol": "http",
    "fluent_query_path": "/api/logs/query",
    "fluent_auth_token": null,
    "fluent_tls_enabled": false,
    "fluent_tls_ca_cert": null,
    "fluent_query_timeout_seconds": 10,
    "fluent_connect_timeout_seconds": 5,
    "fluent_max_lines_per_service": 5000,
    "fluent_default_window_minutes": 10,
    "fluent_services": ["auth-api", "order-service", "payment-service"]
  }
}
```

## Constraints

- All new `Optional[str]` / `Optional[int]` / `Optional[bool]` fields use
  `Optional[T]`, never `T | None` (project convention).
- No network code in this module; this is purely a data model.
- `fluent_auth_token` and `fluent_tls_client_key` must never surface in log
  output; the `_SECRET_KEYS` addition ensures `redacted_dump()` covers them.
- `AEGIS__backends__log__fluent_*` env overrides work automatically via the
  existing `AEGIS__` + nested delimiter convention.

## Tests

**Unit** (`tests/unit/test_settings.py`):

- `test_fluent_protocol_validator_accepts_http_forward` - `"http"` and
  `"forward"` construct without error; an unknown value raises
  `ValidationError`.
- `test_fluent_defaults` - all new fields equal the documented defaults when
  no kwargs are supplied.
- `test_fluent_services_empty_by_default` - `fluent_services == []`.
- `test_fluent_env_override` - `AEGIS__backends__log__fluent_host` overrides
  the default.
- `test_redacted_dump_hides_auth_token` - `Settings().redacted_dump()` returns
  `"***"` for `fluent_auth_token` when it is set to a non-None value.
- `test_redacted_dump_hides_tls_client_key` - same as above for
  `fluent_tls_client_key`.

No mock or integration tests required (pure model).

## Success criteria

- [ ] All fields in the table above exist on `LogBackendSettings` with correct
      types and defaults.
- [ ] `fluent_protocol` validator rejects unknown values.
- [ ] `_SECRET_KEYS` extended so `auth_token` and `client_key` tokens are
      redacted in `redacted_dump()`.
- [ ] `config.example.json` `backends.log` block matches the table above.
- [ ] `mypy --strict` clean; all unit tests listed above pass.
