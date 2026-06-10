# CLI Reference

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
([`AnalyzeConfig`](config.md#flat-analyze-keys)): the JSON config file is applied
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
| `--engine`                           | str               | `auto`                             | Debug engine: `auto` \| `cdb` \| `windbg_js`. Overrides `backends.debug.engine`.                                                     |
| `--ai`                               | str               | `anthropic`                        | AI provider: `anthropic` \| `openai`. Overrides `backends.ai.provider`.                                                              |
| `--store`                            | str               | `filesystem`                       | Storage backend: `filesystem` \| `sqlite` \| `s3` \| `postgres`. Overrides `backends.storage.provider`.                              |
| `--store-config`                     | str               | `None`                             | Storage config value (path / bucket URL). Routed to the matching `backends.storage.*` field by `--store` (see note below).           |
| `--code-provider`                    | str               | `none`                             | Code backend: `none` \| `git` \| `filesystem`. `none` disables the code backend (Stage 8 skipped).                                   |
| `--repo`                             | path              | `None`                             | Repo / source root. Supplying it **enables** the code backend (defaulting its provider to `git`) and sets `backends.code.repo_path`. |
| `--log-provider`                     | str               | `file`                             | Log backend: `file` \| `fluent`. Overrides `backends.log.provider`.                                                                  |
| `--log-service`                      | str               | `None`                             | Service name passed to `LogBackend.query_window` (Data Adapter Stage 4).                                                             |
| `--output`                           | str               | `rich`                             | Output format: `rich` \| `json` \| `quiet`. See [Output modes](#output-modes).                                                       |
| `--log-severity`                     | str               | `INFO`                             | Log verbosity: `TRACE` \| `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`. `DEBUG` adds per-artifact evidence to the stream; `TRACE` additionally streams the full debugger `!analyze` output. |
| `--log-dir`                          | path              | `~/.local/state/aegis-swr/logs`    | Directory for the classic rotating application log file (`aegis-swr.log`), written at `--log-severity`. Overrides `log_dir`.         |
| `--config`                           | path              | `~/.local/state/.aegis-swr/config.json` | JSON config file to load options from.                                                                                               |
| `--save-config` / `--no-save-config` | flag              | `--no-save-config`                 | Write the current CLI options to the JSON file and exit (writes to `--config` if given, else the default path).                      |

**`--store-config` routing** - the value is written to a different storage field
depending on `--store`:

| `--store` | field set from `--store-config` |
|---|---|
| `filesystem` | `backends.storage.reports_dir` |
| `sqlite` | `backends.storage.db_path` |
| `s3` | `backends.storage.object_store_url` |

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
(`report.hitl_request` set) or the investigation ended without a report.

### Examples

```bash
# Crash-dump analysis with CDB + OpenAI, JSON output
aegis analyze --dump ./CrashUi.dmp --sym ./symbols --engine cdb --ai openai --output json

# Log-forensics with the git code backend enabled via --repo
aegis analyze --log ./app.log --log-service render-svc --repo ./src

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
aegis export --store filesystem --store-config ~/.local/share/.aegis-swr/reports \
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

Set a single value in `~/.local/state/.aegis-swr/config.json`, creating the file (and
its parent directory) if needed.

| Argument | Description |
|---|---|
| `KEY` | Dotted key path, e.g. `backends.ai.model`. Intermediate objects are created as needed. |
| `VALUE` | New value (written as a JSON string; Pydantic coerces it to the field's type on load). |

```bash
aegis config set backends.ai.model claude-opus-4-8
aegis config set core.max_debate_rounds 6
```

> Because values are stored as strings, `aegis config show` (which loads through
> the typed `Settings` model) reflects the coerced value - e.g. `"0.7"` →
> `0.7`. To edit lists or deeply nested structures, edit `config.json` directly.

---

See also: [config.md](config.md) for the full option/field reference, and
[agents.md](agents.md) for the agent weight matrix.
