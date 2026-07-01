# 09 – Factory update and CLI wiring

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Blocked - depends on 08
**Depends on:** 01, 08
**Blocks:** 10

---

## Objective

Wire the completed `FluentAdapter` into the existing factory and CLI surface.
The factory already returns `FluentAdapter` for `provider="fluent"`, but the stub
currently immediately raises `NotImplementedError` when queried. After subtask 08,
it works. This subtask covers the two remaining integration points:

1. **Factory** - remove the `NotImplementedError` guard comment; confirm the
   factory returns a ready-to-use `FluentAdapter`.
2. **CLI flags** - expose the new Fluent-specific settings as CLI options so
   operators can configure the Fluent backend from the command line without
   editing `config.json`.
3. **`config.example.json`** - ensure the Fluent block is complete and correct.

## Files

- **Modify** `src/aegis_swr/backends/log/__init__.py`
- **Modify** `src/aegis_swr/cli/commands.py`
- **Modify** `src/aegis_swr/cli/_config.py`
- **Modify** `config/config.example.json`
- **Modify** `docs/configuration/cli.md`

## Factory changes (`backends/log/__init__.py`)

The factory body requires no logic change - it already routes `"fluent"` to
`FluentAdapter`. Remove the module docstring comment that says the adapter is a
stub. Add `FluentHttpClient`, `FluentForwardClient`, and `FluentRecordParser` to
`__all__` so they are accessible for testing.

```python
__all__ = [
    "FileLogAdapter",
    "FluentAdapter",
    "FluentHttpClient",        # new
    "FluentForwardClient",     # new
    "FluentRecordParser",      # new
    "create_log_backend",
]
```

## CLI flags (`cli/commands.py` + `cli/_config.py`)

### New `AnalyzeConfig` fields (in `_config.py`)

Extend the flat field table with Fluent-specific options. All map to the
`ingest.log_source.*` config section (per the three-channel logging redesign
from Phase III of the plan).

| Flat field | JSON path | CLI flag | Default |
|------------|-----------|----------|---------|
| `log_fluent_protocol` | `ingest.log_source.fluent_protocol` | `--log-fluent-protocol` | `"http"` |
| `log_fluent_timeout` | `ingest.log_source.fluent_query_timeout_seconds` | `--log-fluent-timeout` | `10` |
| `log_fluent_window_minutes` | `ingest.log_source.fluent_default_window_minutes` | `--log-fluent-window` | `10` |
| `log_fluent_services` | `ingest.log_source.fluent_services` | `--log-fluent-services` | `""` (empty) |
| `log_fluent_tls` | `ingest.log_source.fluent_tls_enabled` | `--log-fluent-tls / --no-log-fluent-tls` | `False` |

> **Note:** `fluent_auth_token`, `fluent_tls_client_key`, and
> `fluent_tls_client_cert` are intentionally *not* exposed as CLI flags (they
> contain secrets and paths; use env overrides or `config.json`).

### `--log-fluent-services` parsing

The flag accepts a comma-separated list:
`--log-fluent-services auth-api,order-service,db-proxy`

`AnalyzeConfig` stores this as `list[str]` (split on comma, stripped). The config
file form is a JSON array.

### Validation

```python
@field_validator("log_fluent_protocol")
@classmethod
def validate_log_fluent_protocol(cls, v: str) -> str:
    allowed = {"http", "forward"}
    if v not in allowed:
        raise ValueError(f"--log-fluent-protocol must be 'http' or 'forward'")
    return v
```

### `commands.py` additions

In `analyze`:

```python
# Build LogBackendSettings from config (existing path)
log_settings = LogBackendSettings(
    provider=config.log_provider,
    file_root=config.log_file_root,
    fluent_host=config.log_fluent_host,   # existing
    fluent_port=config.log_fluent_port,   # existing
    fluent_tag_prefix=config.log_fluent_tag_prefix,  # existing
    fluent_protocol=config.log_fluent_protocol,      # new
    fluent_query_timeout_seconds=config.log_fluent_timeout,  # new
    fluent_default_window_minutes=config.log_fluent_window_minutes,  # new
    fluent_services=config.log_fluent_services,      # new
    fluent_tls_enabled=config.log_fluent_tls,        # new
)
```

Multi-service wiring: when `log_settings.fluent_services` is non-empty,
store it in `source.metadata["services"]` so `DataAdapter` Stage 4 triggers
`query_window_multi`. Also accept `--log-service` as a single-service shortcut
(existing flag).

### `config.example.json` update

Expand the `ingest.log_source` block:

```jsonc
"ingest": {
  "log_source": {
    "provider": "fluent",
    "service": "auth-api",
    "fluent_host": "localhost",
    "fluent_port": 9880,
    "fluent_tag_prefix": "aegis",
    "fluent_protocol": "http",
    "fluent_query_timeout_seconds": 10,
    "fluent_default_window_minutes": 10,
    "fluent_tls_enabled": false,
    "fluent_services": ["auth-api", "order-service"]
  }
}
```

## Tests

**Unit** (`tests/unit/test_cli.py`):

- `test_log_fluent_protocol_flag_reaches_settings` - `--log-fluent-protocol
  forward` parsed and forwarded to `LogBackendSettings`.
- `test_log_fluent_services_comma_list` - `--log-fluent-services a,b,c` → stored
  as `["a","b","c"]` in `AnalyzeConfig`.
- `test_log_fluent_protocol_invalid_exits_2` - `--log-fluent-protocol banana`
  exits with code 2.
- `test_log_fluent_services_stored_in_metadata` - when `fluent_services` is set,
  `source.metadata["services"]` is populated.

**Integration** (`tests/integration/test_e2e_cli.py`):

- `test_analyze_with_fluent_provider_falls_back_gracefully` - `--log-provider
  fluent` with a non-existent host; assert the CLI completes (does not crash),
  logs a warning about the connection failure, and produces an output report
  using file-only logs.

## Success criteria

- [ ] Factory `__all__` updated; no stub comment remaining.
- [ ] All five new flat fields present in `AnalyzeConfig`.
- [ ] `--log-fluent-services` parses comma-separated list correctly.
- [ ] `commands.py` passes new fields to `LogBackendSettings`.
- [ ] Multi-service list stored in `source.metadata["services"]` when set.
- [ ] CLI validation rejects unknown `--log-fluent-protocol`.
- [ ] Integration test confirms graceful fail-open when Fluent is unreachable.
- [ ] `docs/configuration/cli.md` updated with new flag rows.
- [ ] `mypy --strict` clean; all tests pass.
