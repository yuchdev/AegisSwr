# Configuration Reference (`config.json`)

> `<config-dir>` = `~/.aegis-swr/`

Runtime configuration lives in a single **unified** JSON file:

```
<config-dir>/config.json
```

It carries two kinds of keys:

1. **Analyze keys** - the `aegis analyze` startup options ([`AnalyzeConfig`](#analyze-keys)):
   flat top-level keys plus the grouped `ingest` / `logging` / `evidence` / `process`
   logging sections.
2. **Nested runtime sections** - `core`, `backends`, `sandbox`, `api`, read by the
   Pydantic [`Settings`](#nested-runtime-sections) model.

The two key sets do not overlap, so they coexist in one object. A template lives
at [`config.example.json`](../../config.example.json) - copy it to the default
path to get started:

```bash
cp config.example.json <config-dir>/config.json
```

The agent weight matrix is **not** stored here - it lives in a sibling file,
[`agents.json`](agents.md).

---

## Sources & precedence

`Settings` resolves each field from the first source that provides it, the highest
priority first:

```
explicit init kwargs  >  AEGIS__* environment variables  >  config.json  >  field defaults
```

- A missing, unreadable, or malformed `config.json` never aborts startup - the
  defaults below take over. An **unreadable or malformed** file (unlike a simply
  missing one) logs a warning that is captured in the application log file as well
  as on stderr - at the effective `logging.dir` / `logging.severity`, which are the
  defaults precisely because the file failed to load.
- Unknown nested sections are ignored (`extra="ignore"`); the flat keys
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

## Analyze keys

Consumed by `aegis analyze` (and `--save-config`). The non-logging options are the flat
top-level keys (below); the logging-related options are grouped into four nested
sections (see [Log-related analyze sections](#log-related-analyze-sections)). Each
maps to a CLI flag - see [cli.md](cli.md#aegis-analyze).

| Key             | Type           | Default        | Allowed values                           |
|-----------------|----------------|----------------|------------------------------------------|
| `dump`          | string or null | `null`         | -                                        |
| `logs`          | string[]       | `[]`           | -                                        |
| `shots`         | string[]       | `[]`           | -                                        |
| `pcaps`         | string[]       | `[]`           | -                                        |
| `sym`           | string or null | `null`         | -                                        |
| `assume`        | string or null | `null`         | -                                        |
| `engine`        | string         | `"auto"`       | `auto`, `cdb`, `windbg_js`               |
| `store`         | string         | `"filesystem"` | `filesystem`, `sqlite`, `s3`, `postgres` |
| `store_config`  | string or null | `null`         | -                                        |
| `code_provider` | string         | `"none"`       | `none`, `git`, `filesystem`              |
| `repo`          | string or null | `null`         | -                                        |
| `output`        | string         | `"rich"`       | `rich`, `json`, `json-full`, `quiet`     |

> Unknown flat keys (typos) are loaded-but-ignored with a warning. The runtime
> section names (`core`, `backends`, `sandbox`, `api`, `agent_weights`) are
> recognized and ignored by the analysis loader without warning.

### Log-related analyze sections

These options separate three concerns a single `log_*` group used to conflate. They
are grouped into four nested sections; each subkey maps 1:1 to a CLI flag (the schema
keeps flat `log_*` / `evidence_*` / `process_*` field names internally and translates
to/from this layout at the JSON boundary).

#### `ingest.log_source` - log ingestion (the *investigated system's* logs)

```json
"ingest": { "log_source": { "provider": "file", "service": null } }
```

| Key        | CLI flag         | Type           | Default  | Notes                                                               |
|------------|------------------|----------------|----------|---------------------------------------------------------------------|
| `provider` | `--log-provider` | string         | `"file"` | `file`, `fluent`; overrides [`backends.log.provider`](#backendslog) |
| `service`  | `--log-service`  | string or null | `null`   | Service name → `metadata["service"]` (Data Adapter Stage 4)         |

#### `logging` - Aegis's *own* application diagnostics

```json
"logging": {
  "severity": "INFO",
  "sink": "file",
  "dir": "<config-dir>/logs",
  "elk_url": null,
  "fluent_host": null,
  "fluent_port": null
}
```

| Key           | CLI flag         | Type           | Default                           | Notes                                                                          |
|---------------|------------------|----------------|-----------------------------------|--------------------------------------------------------------------------------|
| `severity`    | `--log-severity` | string         | `"INFO"`                          | `TRACE`,`DEBUG`,`INFO`,`WARNING`,`ERROR` (full loguru range)                   |
| `sink`        | `--log-sink`     | string         | `"file"`                          | `file`, `elk`, `fluent`; `elk`/`fluent` are stubs → warn + fall back to `file` |
| `dir`         | `--log-dir`      | string         | `"<config-dir>/logs"`             | Directory for the rotating `aegis-swr.log` file                                |
| `elk_url`     | *(config-only)*  | string or null | `null`                            | ELK endpoint (reserved; emitter not yet implemented)                           |
| `fluent_host` | *(config-only)*  | string or null | `null`                            | Fluent host (reserved)                                                         |
| `fluent_port` | *(config-only)*  | int or null    | `null`                            | Fluent port (reserved)                                                         |

#### `evidence` - the war-room Evidence Stream (left pane)

```json
"evidence": { "severity": "INFO", "persist": false, "dir": null }
```

| Key        | CLI flag              | Type           | Default  | Notes                                                                                     |
|------------|-----------------------|----------------|----------|-------------------------------------------------------------------------------------------|
| `severity` | `--evidence-severity` | string         | `"INFO"` | `INFO` (curated summary) or `TRACE` (every evidence detail)                               |
| `persist`  | `--evidence-persist`  | bool           | `false`  | Write the stream to `<dir>/evidence-<incident_id>.log` after the run (war-room view only) |
| `dir`      | *(config-only)*       | string or null | `null`   | Evidence transcript dir (default `<config-dir>/evidence`)                                 |

#### `process` - the war-room Investigation Process pane (right pane)

```json
"process": { "severity": "INFO" }
```

| Key        | CLI flag             | Type   | Default  | Notes                                                |
|------------|----------------------|--------|----------|------------------------------------------------------|
| `severity` | `--process-severity` | string | `"INFO"` | `INFO` (headlines) or `TRACE` (full agent reasoning) |

> **Not to be confused with [`backends.log`](#backendslog)** - the *log-ingestion*
> backend that reads the investigated system's logs. Here, `ingest.log_source`
> selects/feeds that backend; `logging` is Aegis's *own* diagnostics; `evidence` /
> `process` are the live war-room panes. For the two war-room channels, `DEBUG`
> collapses into `TRACE` and any other unrecognized value falls back to `INFO`.

---

## Nested runtime sections

### `core`

Investigation/debate tuning.

| Field                         | Type  | Default | Description                                                   |
|-------------------------------|-------|---------|---------------------------------------------------------------|
| `max_debate_rounds`           | int   | `4`     | Maximum agent debate rounds before deadlock handling.         |
| `consensus_threshold`         | float | `0.85`  | Weighted consensus score required to converge.                |
| `hitl_confidence_threshold`   | float | `0.50`  | Below this after max rounds → human-in-the-loop is requested. |
| `log_window_seconds`          | int   | `30`    | Temporal window (seconds) for log correlation.                |
| `user_assumption_token_limit` | int   | `500`   | Token cap on the user-supplied assumption text.               |
| `stack_frames_limit`          | int   | `20`    | Max stack frames retained for analysis.                       |

### `backends.ai`

| Field         | Type   | Default               | Notes                                                  |
|---------------|--------|-----------------------|--------------------------------------------------------|
| `provider`    | string | `"anthropic"`         | Allowed: `anthropic`, `openai`, `bedrock` (validated). |
| `model`       | string | `"claude-sonnet-4-6"` | See model resolution below.                            |
| `temperature` | float  | `0.2`                 |                                                        |
| `max_tokens`  | int    | `4096`                |                                                        |
| `stream`      | bool   | `true`                | Stream tokens from the provider.                       |
| `bedrock`     | object | (see below)           | Amazon Bedrock-specific settings; only used when `provider == "bedrock"`. |

**Model resolution** - the effective model reconciles `model` with `provider`.
If `provider` is switched but `model` still names the other vendor's model, the
provider's default is substituted; an explicit, provider-matching model is always
respected:

- `provider: openai` + a non-`gpt-*`/`o1`/`o3`/`o4` model → `gpt-5.4`.
- `provider: anthropic` + a non-`claude*` model → `claude-sonnet-4-6`.
- `provider: bedrock` → the model identity comes from `backends.ai.bedrock.model_id`
  (an inference-profile ID); the top-level `model` field is ignored.

#### `backends.ai.bedrock`

Amazon Bedrock is reached through the **Converse API**, giving a single
request/response shape across hosted Claude, Nova, and other model families.
Structured output uses Converse forced tool-use (`toolConfig`); free-form
generation streams via `converse_stream`. boto3 is synchronous, so every call is
dispatched to a worker thread to keep the event loop free.

| Field                     | Type   | Default                            | Notes                                                                       |
|---------------------------|--------|------------------------------------|-----------------------------------------------------------------------------|
| `region`                  | string | `"ap-southeast-2"`                 | AWS region. Falls back to `AWS_DEFAULT_REGION` only when blank.             |
| `model_id`                | string | `"au.anthropic.claude-sonnet-4-6"` | Model ID or cross-region inference profile. Direct IDs need provisioned throughput. |
| `thinking_budget_tokens`  | int    | `0`                                | Extended-thinking budget. `0` disables; sub-1024 is treated as disabled. Applied to free-form output only - never forced tool use. |
| `connect_timeout_seconds` | int    | `10`                               | bedrock-runtime TCP connect timeout.                                        |
| `read_timeout_seconds`    | int    | `300`                              | Socket read timeout (reasoning can be slow).                                |
| `max_attempts`            | int    | `3`                                | botocore standard-mode retry attempts (throttling / 5xx).                   |

**Authentication** (dual-mode, read from the environment, never logged):

- If `AWS_BEARER_TOKEN_BEDROCK` is set, an `Authorization: Bearer <token>` header
  is injected on every request (Bedrock API-key auth).
- Otherwise the standard boto3 credential chain (env vars / shared config / IAM
  role) is used via SigV4.

```bash
export AEGIS__backends__ai__provider=bedrock
export AEGIS__backends__ai__bedrock__model_id=au.anthropic.claude-sonnet-4-6
export AWS_BEARER_TOKEN_BEDROCK=<your-bedrock-api-key>   # or use ~/.aws credentials
```

### `backends.debug`

| Field                      | Type           | Default  | Notes                                            |
|----------------------------|----------------|----------|--------------------------------------------------|
| `engine`                   | string         | `"auto"` | Allowed: `auto`, `cdb`, `windbg_js` (validated). |
| `timeout_seconds`          | int            | `300`    | Overall debugger subprocess timeout.             |
| `callback_timeout_seconds` | int            | `60`     | HTTP-bridge callback timeout (JS provider).      |
| `max_faulting_frames`      | int            | `20`     | Frames kept for the faulting thread.             |
| `max_other_thread_frames`  | int            | `3`      | Frames kept per non-faulting thread.             |
| `symbol_cache`             | string or null | `null`   | Local symbol cache directory.                    |
| `symbol_server_url`        | string or null | `null`   | Symbol server URL.                               |

### `backends.storage`

| Field                 | Type           | Default                                                   | Notes                                                          |
|-----------------------|----------------|-----------------------------------------------------------|----------------------------------------------------------------|
| `provider`            | string         | `"filesystem"`                                            | Allowed: `filesystem`, `sqlite`, `s3`, `postgres` (validated). |
| `reports_dir`         | string         | `"<config-dir>/reports"`                                  | filesystem: report JSON files.                                 |
| `objects_dir`         | string         | `"<config-dir>/objects"`                                  | filesystem: raw binary artifacts.                              |
| `db_path`             | string         | `"<config-dir>/db/reports.db"`                            | sqlite: database file.                                         |
| `database_url`        | string         | `"postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"` | postgres DSN. **Redacted** in `config show`.                   |
| `object_store_url`    | string         | `"s3://aegis-raw-inputs"`                                 | S3 bucket URL.                                                 |
| `object_store_region` | string         | `"us-east-1"`                                             | S3 region.                                                     |
| `s3_endpoint_url`     | string or null | `null`                                                    | MinIO / custom S3-compatible endpoint.                         |
| `vector_store_url`    | string         | `"http://localhost:6333"`                                 | Vector store (incident history).                               |
| `vector_collection`   | string         | `"incident_history"`                                      | Vector collection name.                                        |

### `backends.log`

| Field                     | Type           | Default                                     | Notes                                                         |
|---------------------------|----------------|---------------------------------------------|---------------------------------------------------------------|
| `provider`                | string         | `"file"`                                    | Allowed: `file`, `fluent`, `elk` (validated; `elk` deferred). |
| `file_root`               | string or null | `null`                                      | Base dir for service→file resolution (file provider).         |
| `default_severity_levels` | string[]       | `["FATAL", "CRITICAL", "ERROR", "WARNING"]` | Severities pulled by default.                                 |
| `elk_url`                 | string or null | `null`                                      | ELK endpoint (deferred).                                      |
| `fluent_host`             | string or null | `null`                                      | Fluent host (stub).                                           |
| `fluent_port`             | int or null    | `null`                                      | Fluent port (stub).                                           |
| `fluent_tag_prefix`       | string or null | `null`                                      | Fluent tag prefix (stub).                                     |

### `backends.code`

| Field                 | Type           | Default | Notes                                                   |
|-----------------------|----------------|---------|---------------------------------------------------------|
| `enabled`             | bool           | `false` | `false` → no CodeBackend; Data Adapter Stage 8 skipped. |
| `provider`            | string         | `"git"` | Allowed: `git`, `filesystem` (validated).               |
| `repo_path`           | string or null | `null`  | Working tree / source root.                             |
| `window_hours`        | int            | `2`     | Default look-back for `get_commits_before`.             |
| `commit_limit`        | int            | `10`    | Max commits returned.                                   |
| `git_timeout_seconds` | int            | `30`    | git subprocess timeout (git provider).                  |

### `sandbox`

Secure code-validation sandbox.

| Field             | Type   | Default    | Description                    |
|-------------------|--------|------------|--------------------------------|
| `enabled`         | bool   | `true`     | Enable the validation sandbox. |
| `runtime`         | string | `"docker"` | Container runtime.             |
| `memory_mb`       | int    | `256`      | Memory cap (MB).               |
| `cpu_limit`       | float  | `0.5`      | CPU share limit.               |
| `timeout_seconds` | int    | `60`       | Per-run timeout.               |

### `api`

FastAPI server settings (Phase 8).

| Field                   | Type   | Default             | Description                          |
|-------------------------|--------|---------------------|--------------------------------------|
| `host`                  | string | `"0.0.0.0"`         | Bind host.                           |
| `port`                  | int    | `8000`              | Bind port.                           |
| `workers`               | int    | `4`                 | Worker processes.                    |
| `api_key_header`        | string | `"X-Aegis-API-Key"` | Header carrying the API key.         |
| `rate_limit_per_minute` | int    | `10`                | Analyze requests/minute per API key. |

---

## Editing

- `aegis config set <dotted.key> <value>` - set one key (see
  [cli.md](cli.md#aegis-config-set)).
- `aegis config show` - print the resolved, redacted settings.
- Or edit `<config-dir>/config.json` directly (required for lists such as
  `backends.log.default_severity_levels`).
