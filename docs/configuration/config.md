# Configuration Reference (`config.json`)

Runtime configuration lives in a single **unified** JSON file:

```
~/.local/state/.aegis-swr/config.json
```

It carries two kinds of keys:

1. **Flat analyze keys** - the `aegis analyze` startup options
   ([`AnalyzeConfig`](#flat-analyze-keys)).
2. **Nested runtime sections** - `core`, `backends`, `sandbox`, `api`, read by the
   Pydantic [`Settings`](#nested-runtime-sections) model.

The two key sets do not overlap, so they coexist in one object. A template lives
at [`config.example.json`](../../config.example.json) - copy it to the default
path to get started:

```bash
cp config.example.json ~/.local/state/.aegis-swr/config.json
```

The agent weight matrix is **not** stored here - it lives in a sibling file,
[`agents.json`](agents.md).

---

## Sources & precedence

`Settings` resolves each field from the first source that provides it, highest
priority first:

```
explicit init kwargs  >  AEGIS__* environment variables  >  config.json  >  field defaults
```

- A missing, unreadable, or malformed `config.json` never aborts startup - the
  defaults below take over.
- Unknown nested sections are ignored (`extra="ignore"`); the flat analyze keys
  in the same file are likewise ignored by `Settings`.

### Environment overrides

Override any nested field with the `AEGIS__` prefix and `__` as the nesting
delimiter:

```bash
export AEGIS__core__max_debate_rounds=6
export AEGIS__backends__ai__provider=openai
export AEGIS__backends__storage__database_url='postgresql+asyncpg://u:p@db/aegis'
```

### Secret redaction

`aegis config show` prints settings with secrets masked as `***`. A key is
treated as secret when its name contains any of: `api_key`, `password`, `secret`,
`token`, `database_url`.

---

## Flat analyze keys

Consumed by `aegis analyze` (and `--save-config`). Each key maps 1:1 to a CLI
flag - see [cli.md](cli.md#aegis-analyze) for the corresponding `--flag` and the
overrides each one applies to the nested sections.

| Key             | Type           | Default        | Allowed values                           |
|-----------------|----------------|----------------|------------------------------------------|
| `dump`          | string \| null | `null`         | -                                        |
| `logs`          | string[]       | `[]`           | -                                        |
| `shots`         | string[]       | `[]`           | -                                        |
| `pcaps`         | string[]       | `[]`           | -                                        |
| `sym`           | string \| null | `null`         | -                                        |
| `assume`        | string \| null | `null`         | -                                        |
| `engine`        | string         | `"auto"`       | `auto`, `cdb`, `windbg_js`               |
| `ai`            | string         | `"anthropic"`  | `anthropic`, `openai`                    |
| `store`         | string         | `"filesystem"` | `filesystem`, `sqlite`, `s3`, `postgres` |
| `store_config`  | string \| null | `null`         | -                                        |
| `code_provider` | string         | `"none"`       | `none`, `git`, `filesystem`              |
| `repo`          | string \| null | `null`         | -                                        |
| `log_provider`  | string         | `"file"`       | `file`, `fluent`                         |
| `log_service`   | string \| null | `null`         | -                                        |
| `output`        | string         | `"rich"`       | `rich`, `json`, `json-full`, `quiet`     |
| `log_severity`  | string         | `"INFO"`       | `TRACE`, `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `log_dir`       | string         | `"~/.local/state/aegis-swr/logs"` | Directory for the rotating `aegis-swr.log` file |

> Unknown flat keys (typos) are loaded-but-ignored with a warning. The nested
> section names (`core`, `backends`, `sandbox`, `api`, `agent_weights`) are
> recognised and ignored silently.

---

## Nested runtime sections

### `core`

Investigation/debate tuning.

| Field | Type | Default | Description |
|---|---|---|---|
| `max_debate_rounds` | int | `4` | Maximum agent debate rounds before deadlock handling. |
| `consensus_threshold` | float | `0.85` | Weighted consensus score required to converge. |
| `hitl_confidence_threshold` | float | `0.50` | Below this after max rounds → human-in-the-loop is requested. |
| `log_window_seconds` | int | `30` | Temporal window (seconds) for log correlation. |
| `user_assumption_token_limit` | int | `500` | Token cap on the user-supplied assumption text. |
| `stack_frames_limit` | int | `20` | Max stack frames retained for analysis. |

### `backends.ai`

| Field | Type | Default | Notes |
|---|---|---|---|
| `provider` | string | `"anthropic"` | Allowed: `anthropic`, `openai` (validated). |
| `model` | string | `"claude-sonnet-4-6"` | See model resolution below. |
| `temperature` | float | `0.2` | |
| `max_tokens` | int | `4096` | |
| `stream` | bool | `true` | Stream tokens from the provider. |

**Model resolution** - the effective model reconciles `model` with `provider`.
If `provider` is switched but `model` still names the other vendor's model, the
provider's default is substituted; an explicit, provider-matching model is always
respected:

- `provider: openai` + a non-`gpt-*`/`o1`/`o3`/`o4` model → `gpt-5.4`.
- `provider: anthropic` + a non-`claude*` model → `claude-sonnet-4-6`.

### `backends.debug`

| Field | Type | Default | Notes |
|---|---|---|---|
| `engine` | string | `"auto"` | Allowed: `auto`, `cdb`, `windbg_js` (validated). |
| `timeout_seconds` | int | `300` | Overall debugger subprocess timeout. |
| `callback_timeout_seconds` | int | `60` | HTTP-bridge callback timeout (JS provider). |
| `max_faulting_frames` | int | `20` | Frames kept for the faulting thread. |
| `max_other_thread_frames` | int | `3` | Frames kept per non-faulting thread. |
| `symbol_cache` | string \| null | `null` | Local symbol cache directory. |
| `symbol_server_url` | string \| null | `null` | Symbol server URL. |

### `backends.storage`

| Field | Type | Default | Notes |
|---|---|---|---|
| `provider` | string | `"filesystem"` | Allowed: `filesystem`, `sqlite`, `s3`, `postgres` (validated). |
| `reports_dir` | string | `"~/.local/share/.aegis-swr/reports"` | filesystem: report JSON files. |
| `objects_dir` | string | `"~/.local/share/.aegis-swr/objects"` | filesystem: raw binary artifacts. |
| `db_path` | string | `"~/.local/db/.aegis-swr/reports.db"` | sqlite: database file. |
| `database_url` | string | `"postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"` | postgres DSN. **Redacted** in `config show`. |
| `object_store_url` | string | `"s3://aegis-raw-inputs"` | S3 bucket URL. |
| `object_store_region` | string | `"us-east-1"` | S3 region. |
| `s3_endpoint_url` | string \| null | `null` | MinIO / custom S3-compatible endpoint. |
| `vector_store_url` | string | `"http://localhost:6333"` | Vector store (incident history). |
| `vector_collection` | string | `"incident_history"` | Vector collection name. |

### `backends.log`

| Field | Type | Default | Notes |
|---|---|---|---|
| `provider` | string | `"file"` | Allowed: `file`, `fluent`, `elk` (validated; `elk` deferred). |
| `file_root` | string \| null | `null` | Base dir for service→file resolution (file provider). |
| `default_severity_levels` | string[] | `["FATAL", "CRITICAL", "ERROR", "WARNING"]` | Severities pulled by default. |
| `elk_url` | string \| null | `null` | ELK endpoint (deferred). |
| `fluent_host` | string \| null | `null` | Fluent host (stub). |
| `fluent_port` | int \| null | `null` | Fluent port (stub). |
| `fluent_tag_prefix` | string \| null | `null` | Fluent tag prefix (stub). |

### `backends.code`

| Field | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | `false` | `false` → no CodeBackend; Data Adapter Stage 8 skipped. |
| `provider` | string | `"git"` | Allowed: `git`, `filesystem` (validated). |
| `repo_path` | string \| null | `null` | Working tree / source root. |
| `window_hours` | int | `2` | Default look-back for `get_commits_before`. |
| `commit_limit` | int | `10` | Max commits returned. |
| `git_timeout_seconds` | int | `30` | git subprocess timeout (git provider). |

### `sandbox`

Secure code-validation sandbox.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable the validation sandbox. |
| `runtime` | string | `"docker"` | Container runtime. |
| `memory_mb` | int | `256` | Memory cap (MB). |
| `cpu_limit` | float | `0.5` | CPU share limit. |
| `timeout_seconds` | int | `60` | Per-run timeout. |

### `api`

FastAPI server settings (Phase 8).

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | string | `"0.0.0.0"` | Bind host. |
| `port` | int | `8000` | Bind port. |
| `workers` | int | `4` | Worker processes. |
| `api_key_header` | string | `"X-Aegis-API-Key"` | Header carrying the API key. |
| `rate_limit_per_minute` | int | `10` | Analyze requests/minute per API key. |

---

## Editing

- `aegis config set <dotted.key> <value>` - set one key (see
  [cli.md](cli.md#aegis-config-set)).
- `aegis config show` - print the resolved, redacted settings.
- Or edit `~/.local/state/.aegis-swr/config.json` directly (required for lists such as
  `backends.log.default_severity_levels`).
