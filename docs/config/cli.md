# CLI Reference

> `<config-dir>` = `~/.aegis-swr/`

The Aegis SWR command-line interface. Invoke it as `aegis <command>` (installed
entry point) or `python -m aegis_swr.cli <command>`.

```
aegis [--help] <command> [options]
```

`aegis --help` prints the top-level summary **and** walks the whole command tree,
emitting the full help (usage, description, every option) for each subcommand.

Commands: [`analyze`](#aegis-analyze) · [`export`](#aegis-export) ·
[`server`](#aegis-server) · [`config show`](#aegis-config-show) ·
[`config set`](#aegis-config-set).

---

## `aegis analyze`

Run an investigation in-process (no API server required). Reads the dump / logs /
other evidence, runs the multi-agent debate, persists the report through the
configured storage backend, and prints where the result was saved.

Options can come from two sources that share one schema
([`AnalyzeConfig`](config.md#analyze-keys)): the JSON config file is applied
first, then explicit CLI flags on top. Precedence (low → high):

```
dataclass defaults  <  config.json  <  CLI flags
```

| Option                               | Type              | Default                            | Description                                                                                                                          |
|--------------------------------------|-------------------|------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `--dump`                             | path              | `None`                             | Crash dump file (`.dmp` / `.core` / `.ips`). Presence selects **crash-dump** mode; absence selects **log-forensics** mode.           |
| `--log`                              | path (repeatable) | `[]`                               | Log file. Repeat for multiple files.                                                                                                 |
| `--shot`                             | path (repeatable) | `[]`                               | Screenshot file. Repeat for multiple files.                                                                                          |
| `--pcap`                             | path (repeatable) | `[]`                               | Network traffic capture file (e.g. `.pcap`). Repeat for multiple files.                                                              |
| `--sym`                              | path              | `None`                             | Symbol path / symbol directory.                                                                                                      |
| `--assume`                           | str               | `None`                             | User context / assumption text fed to the agents.                                                                                    |
| `--engine`                           | str               | `auto`                             | Debug engine: `auto` or `cdb` or `windbg_js`. Overrides `backends.debug.engine`.                                                     |
| `--ai`                               | str               | `anthropic`                        | AI provider: `anthropic`, `openai`, or `bedrock`. Overrides `backends.ai.provider`. For `bedrock`, set `backends.ai.bedrock.model_id` and `AWS_BEARER_TOKEN_BEDROCK` (or AWS credentials). |
| `--store`                            | str               | `filesystem`                       | Storage backend: `filesystem` or `sqlite` or `s3` or `postgres`. Overrides `backends.storage.provider`.                              |
| `--store-config`                     | str               | `None`                             | Storage config value (path / bucket URL). Routed to the matching `backends.storage.*` field by `--store` (see note below).           |
| `--code-provider`                    | str               | `none`                             | Code backend: `none` or `git` or `filesystem`. `none` disables the code backend (Stage 8 skipped).                                   |
| `--repo`                             | path              | `None`                             | Repo / source root. Supplying it **enables** the code backend (defaulting its provider to `git`) and sets `backends.code.repo_path`. |
| `--log-provider`                     | str               | `file`                             | Log-**ingestion** backend (reads the *investigated system's* logs): `file` or `fluent`. Sets `ingest.log_source.provider` → `backends.log.provider`. |
| `--log-service`                      | str               | `None`                             | Service name for `LogBackend.query_window` (Data Adapter Stage 4). Sets `ingest.log_source.service` → `metadata["service"]`.         |
| `--output`                           | str               | `rich`                             | Output format: `rich` or `json` or `json-full` or `quiet`. See [Output modes](#output-modes).                                       |
| `--log-severity`                     | str               | `INFO`                             | **Application** log verbosity (Aegis's own diagnostics): `TRACE` or `DEBUG` or `INFO` or `WARNING` or `ERROR`. Maps to `logging.severity`. |
| `--log-sink`                         | str               | `file`                             | Application log sink: `file` or `elk` or `fluent`. `elk`/`fluent` are stubs (warn + fall back to `file`). Maps to `logging.sink`.    |
| `--log-dir`                          | path              | `<config-dir>/logs`                | Directory for the rotating application log file (`aegis-swr.log`), written at `--log-severity`. Maps to `logging.dir`.               |
| `--evidence-severity`                | str               | `INFO`                             | Evidence Stream (war-room **left** pane) verbosity: `INFO` or `TRACE`. Maps to `evidence.severity`.                                  |
| `--process-severity`                 | str               | `INFO`                             | Investigation Process (war-room **right** pane) verbosity: `INFO` or `TRACE` (TRACE prints each agent's full reasoning). Maps to `process.severity`. |
| `--evidence-persist` / `--no-evidence-persist` | flag    | `--no-evidence-persist`            | After the run, write the Evidence Stream to `<evidence dir>/evidence-<incident_id>.log` (war-room view only). Maps to `evidence.persist`. |
| `--config`                           | path              | `<config-dir>/config.json`              | JSON config file to load options from.                                                                                               |
| `--save-config` / `--no-save-config` | flag              | `--no-save-config`                 | Write the current CLI options to the JSON file and exit (writes to `--config` if given, else the default path).                      |

**`--store-config` routing** - the value is written to a different storage field
depending on `--store`:

| `--store` | field set from `--store-config` |
|---|---|
| `filesystem` | `backends.storage.reports_dir` |
| `sqlite` | `backends.storage.db_path` |
| `s3` | `backends.storage.object_store_url` |

**Logging channels** - the three verbosity channels are independent (the
log-subsystem split): `--log-severity` / `--log-sink` / `--log-dir` configure Aegis's
own **application** logging; `--evidence-severity` and `--process-severity` configure
the two war-room panes. `--evidence-severity` and `--process-severity` accept only
`INFO` or `TRACE` (any other value - on the CLI **or** in `config.json` - exits with
code `2`); `--log-severity` accepts the full loguru range. `--evidence-persist` needs
the war-room view, so it has no effect with `--output quiet` or on a narrow terminal
(a warning is logged). `--log-provider` / `--log-service` are unrelated - they select
the *log-ingestion* backend (`ingest.log_source`), not Aegis's own logging.

### Output modes

| `--output` | Behaviour |
|---|---|
| `rich` | Live agent dialogue, then the final conclusion + fix panels, then the saved-report path. |
| `json` | Live display streamed to **stderr**; **stdout** carries a machine-readable locator only (`incident_id`, `mode`, `status`, `storage`, `report_path`). |
| `quiet` | No display - just run and store. |

> The full report is persisted **exclusively** as a result file by the storage
> backend; it is never dumped to stdout, regardless of `--output` or `--log-severity`.
> Only the location is surfaced.

**Exit codes** - `0` on success; `1` when human input is required
(`report.hitl_request` set) or the investigation ended without a report; `2` on an
invalid logging-channel value (`--evidence-severity` / `--process-severity` not
`INFO`/`TRACE`, or an unknown `--log-sink`).

### Examples

```bash
# Crash-dump analysis with CDB + OpenAI, JSON output
aegis analyze --dump ./CrashUi.dmp --sym ./symbols --engine cdb --ai openai --output json

# Log-forensics with the git code backend enabled via --repo
aegis analyze --log ./app.log --log-service render-svc --repo ./src

# Verbose war room: full evidence detail + full agent reasoning, quiet app log,
# and persist the evidence transcript
aegis analyze --dump ./CrashUi.dmp --evidence-severity TRACE --process-severity TRACE \
              --log-severity WARNING --evidence-persist

# Persist current flags as the default config and exit
aegis analyze --ai openai --engine cdb --store sqlite --save-config
```

---

## `aegis export`

Migrate stored reports between storage backends. Reads every report from the
source relational store and writes it to the destination store.

| Option | Type | Default | Description |
|---|---|---|---|
| `--store` | str | `filesystem` | Source storage backend. |
| `--store-config` | str | `None` | Source config value (routed by `--store`, as above). |
| `--to-store` | str | `filesystem` | Destination storage backend. |
| `--to-config` | str | `None` | Destination config value (routed by `--to-store`). |

Exits `1` if either side has no relational store; otherwise prints the count of
exported reports.

```bash
aegis export --store filesystem --store-config <config-dir>/reports \
             --to-store sqlite --to-config ./reports.db
```

---

## `aegis server`

Start the FastAPI API server.

| Option | Type | Default | Description |
|---|---|---|---|
| `--host` | str | `0.0.0.0` | Bind host. |
| `--port` | int | `8000` | Bind port. |
| `--reload` / `--no-reload` | flag | `--no-reload` | Enable hot-reload. |

> **Not yet implemented** (Phase 8). The command currently echoes the configured
> bind address and exits.

---

## `aegis config show`

Print the resolved runtime settings - `config.json` merged with `AEGIS__*`
environment overrides - as JSON. Secret values are redacted to `***` (keys
containing `api_key`, `password`, `secret`, `token`, or `database_url`).

```bash
aegis config show
```

---

## `aegis config set`

Set a single value in `<config-dir>/config.json`, creating the file (and
its parent directory) if needed.

| Argument | Description |
|---|---|
| `KEY` | Dotted key path, e.g. `backends.ai.anthropic.model`. Intermediate objects are created as needed. |
| `VALUE` | New value (written as a JSON string; Pydantic coerces it to the field's type on load). |

```bash
aegis config set backends.ai.anthropic.model claude-opus-4-8
aegis config set core.max_debate_rounds 6
```

> Because values are stored as strings, `aegis config show` (which loads through
> the typed `Settings` model) reflects the coerced value - e.g. `"0.7"` →
> `0.7`. To edit lists or deeply nested structures, edit `config.json` directly.

---

See also: [config.md](config.md) for the full option/field reference, and
[agents.md](agents.md) for the agent weight matrix.
