# Aegis SWR - Implementation Plan & Backend / Data-Adapter Specification

**Package:** `aegis-swr` | **Module root:** `src/aegis_swr/`
**Total estimated timeline:** 16 weeks across 10 phases

This document is self-contained for the **Data Adapter** and **Backend** layers:
their specifications are inlined in [Part II](#part-ii--data-adapter--backend-specifications)
(merged here from the design spec, with code/config/directory-tree examples trimmed
to leave the interface contracts and algorithms). The remaining specifications -
Multi-Agent System engine, storage topology, REST API, sandbox, CLI, and the full
configuration system - continue to live in `PRODUCTION_DESIGN_SPEC.md`.

- [Part I - Phase Plan](#part-i--phase-plan)
- [Part II - Data Adapter & Backend Specifications](#part-ii--data-adapter--backend-specifications)
- [Part III - New Task: Three-Channel Logging](#part-iii--new-task-three-channel-logging-application--evidence--investigation-process)

---

# Part I - Phase Plan

## Phase Overview

| Phase | Name                       | Duration   | Output                                                           |
|-------|----------------------------|------------|------------------------------------------------------------------|
| 1     | Foundation & Package Setup | Week 1–2   | Repo skeleton, schemas, ABCs, config, CI                         |
| 2     | Data Adapter Layer         | Week 3–4   | Preprocessing pipeline; token-dense incident brief               |
| 3     | AI Backends                | Week 5     | Anthropic + OpenAI providers; streaming; structured output       |
| 4     | Debug Backends             | Week 6     | CDB (Windows), GDB (Linux), LLDB (macOS); FaultClass mapping     |
| 5     | Multi-Agent System         | Week 7–9   | LangGraph state graph; 4 agents; consensus; HITL trigger         |
| 6     | Storage Backends           | Week 10    | PostgreSQL, S3/MinIO, Qdrant; dedup by content hash              |
| 6.1   | Code Backend               | Week 10    | Git + filesystem code adapters; Stage 8 code-history attribution |
| 6.2   | Log Backend                | Week 10    | File log adapter + Fluent stub; Stage 4 windowed log queries     |
| 7     | CLI & Local Mode           | Week 11    | Typer CLI; in-process pipeline without API server                |
| 8     | REST API Layer             | Week 12–13 | FastAPI app; SSE streaming; auth; rate limiting                  |
| 9     | Secure Code Sandbox        | Week 14    | Docker/gVisor executor; compile + AST validation                 |
| 10    | Testing & Hardening        | Week 15–16 | Ground truth suite; benchmark; security audit; CI gates          |

---

## Phase 1: Foundation & Package Setup

**Goal:** Establish a compilable, importable, fully typed Python package. No business logic yet - only structure, contracts, and tooling.

### Deliverables

1. **`pyproject.toml`** - Poetry project configured with all dependencies, `aegis-swr` name, `src/aegis_swr/` package root, and `aegis` CLI entry point.
2. **Directory skeleton** - all `__init__.py` files for `core/`, `agents/`, `backends/` (and subdirs), `sandbox/`, `api/`, `cli/`, `config/`.
3. **`core/schemas.py`** - All Pydantic v2 models: `IncidentSource`, `IncidentBrief`, `DebugExtractionResult`, `StackFrame`, `Hypothesis`, `AgentTurn`, `SkepticVerdict`, `RCAReport`, `HITLRequest`, `InvestigationState` (TypedDict), `RCAHypothesis`.
4. **`core/fault_codes.py`** - `FaultClass` enum and complete platform-to-FaultClass mapping tables for Windows NTSTATUS, Linux signals, macOS exception types.
5. **`backends/base.py`** - All five abstract base classes: `AIAPIBackend`, `DebugBackend`, `RelationalStore`, `ObjectStore`, `VectorStore`, `LogBackend`, `CodeBackend`. Full type hints, docstrings on each abstract method.
6. **`agents/base.py`** - Abstract `BaseAgent` with `system_prompt: str`, `run(state: InvestigationState, ai_backend: AIAPIBackend) -> AgentTurn` abstract method.
7. **`config/settings.py`** - Pydantic Settings v2 class that reads `config.yaml` and `AEGIS__*` environment variables. Includes `CoreSettings`, `AISettings`, `DebugSettings`, `StorageSettings`, `APISettings`, `SandboxSettings`, `AgentWeightsSettings`.
8. **`config.yaml`** - Default configuration with all values from the design spec.
9. **`.env.example`** - Documents `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AEGIS__BACKENDS__STORAGE__DATABASE_URL`, etc.
10. **`tests/` skeleton** - `conftest.py` with pytest fixtures for a default `Settings` object and a mock `IncidentSource`.
11. **CI configuration** - `.github/workflows/ci.yml` (or equivalent): ruff lint, mypy type-check, pytest unit tests on each push.

### Success Criteria

- `poetry install` completes with no errors.
- `python -c "from aegis_swr.core.schemas import RCAReport; print('ok')"` succeeds.
- `mypy src/` passes with zero errors.
- `pytest tests/unit/test_schemas.py` passes (basic Pydantic model creation and serialization tests).

---

## Phase 2: Data Adapter Layer

**Goal:** Implement the full nine-stage preprocessing pipeline that converts raw `IncidentSource` into a structured `IncidentBrief`. (Full algorithm in [Part II §B](#b-data-adapter-layer-coredata_adapterpy).)

### Deliverables

1. **`core/data_adapter.py`** - `DataAdapter` class with `async def process(source: IncidentSource) -> IncidentBrief` method. Each stage is a private method:
   - `_compute_hash(path: Path) -> str` - SHA-256 in chunks.
   - `_detect_format(path: Path) -> DumpFormat` - magic-byte detection (not extension).
   - `_apply_noise_filter(text: str) -> str` - DBGHELP strip, fill pattern replace, DLL list drop, 8k truncation.
   - `_process_logs(paths: list[Path], timestamp: datetime | None) -> str` - Drain3 clustering, temporal window, severity filter, 2k token budget.
   - `_process_screenshot(path: Path) -> UIContext | None` - OCR via pytesseract with confidence gate.
   - `_scrub_pii(text: str) -> tuple[str, dict]` - Presidio scrubbing; returns scrubbed text + substitution map.
   - `_enforce_assumption_limit(text: str) -> str` - Token count; truncate to 500 with log warning.
   - `_query_code_history(source: IncidentSource) -> list[CommitRecord]` - Optional; only if `CodeBackend` configured.
   - `_assemble_brief(...) -> IncidentBrief` - Final assembly.

2. **Drain3 integration** - Configure `DrainConfig` with appropriate patterns for common log formats (syslog, JSON, Python logging, Windows Event Log).

3. **`tests/unit/test_data_adapter.py`** - Per-stage unit tests:
   - Hash computation consistency.
   - Noise filter removes DBGHELP lines and fill patterns.
   - Temporal windowing slices correctly.
   - Drain3 deduplication reduces repeated lines.
   - Presidio scrubs emails, IP addresses, AWS keys.
   - Assumption token cap triggers at 500.

4. **`tests/unit/fixtures/`** - Sample raw CDB output, sample log files with known PII, sample screenshot.

### Success Criteria

- `DataAdapter.process()` completes on a sample Windows `.dmp` + log file in under 5 seconds (no LLM call).
- All noise filter rules reduce the token count of the canonical test CDB output by ≥60% vs. the raw input.
- Presidio correctly scrubs all entities in `tests/unit/fixtures/sample_logs_with_pii.txt`.
- `pytest tests/unit/test_data_adapter.py` passes.

---

## Phase 3: AI Backends

**Goal:** Implement two production-quality LLM provider backends with structured output, prompt caching, streaming, and retry logic. (Interface + as-built behavior in [Part II §C.1](#c1-aiapibackend).)

### Deliverables

1. **`backends/ai/anthropic_provider.py`** - `AnthropicBackend(AIAPIBackend)`:
   - `generate()`: Uses `client.messages.create()` with `cache_control: {"type": "ephemeral"}` on the system block. If `output_schema` provided, uses tool use pattern with a single tool whose `input_schema` is the Pydantic model's JSON schema. Validates response with Pydantic; on `ValidationError` raises `AIOutputValidationError` and retries once with a correction prompt.
   - `stream()`: Uses `client.messages.stream()` async context manager; yields text deltas.
   - Token tracking: reads `usage` from response and appends to `InvestigationState.token_tracker`.

2. **`backends/ai/openai_provider.py`** - `OpenAIBackend(AIAPIBackend)`:
   - `generate()`: Uses `response_format={"type": "json_schema", "json_schema": {schema dict}}` for structured output. Retry logic same as Anthropic.
   - `stream()`: Uses `stream=True` with `stream_options={"include_usage": True}`.

3. **`backends/ai/__init__.py`** - `create_ai_backend(config: AISettings) -> AIAPIBackend` factory.

4. **Custom exceptions** in `core/exceptions.py`:
   - `AIOutputValidationError(Exception)` - raised when LLM response fails schema validation after one retry.
   - `PlatformNotSupportedError(Exception)`.
   - `SandboxExecutionError(Exception)`.
   - `IncidentNotFoundError(Exception)`.

5. **`tests/unit/test_ai_backends.py`** - Uses `unittest.mock` to patch `anthropic.AsyncAnthropic` and `openai.AsyncOpenAI`. Tests structured output parsing, schema validation retry, stream iteration.

### Success Criteria

- `AnthropicBackend.generate()` with a `Hypothesis` output schema returns a validated `Hypothesis` instance.
- Stream yields at least one non-empty string token before raising `StopAsyncIteration`.
- `AIOutputValidationError` is raised (not silently ignored) when mock LLM returns malformed JSON.
- `pytest tests/unit/test_ai_backends.py` passes with no network calls.

---

## Phase 4: Debug Backends

**Goal:** Implement all three platform debug workers and the platform-adaptive FaultClass mapping. (Interface, WinDbg-JS design, and as-built behavior in [Part II §C.2](#c2-debugbackend).)

### Deliverables

1. **`backends/debug/cdb_worker.py`** - `CdbBackend(DebugBackend)`:
   - `SUPPORTED_FORMATS = [DumpFormat.WINDOWS_MINIDUMP]`
   - `SUPPORTED_PLATFORMS = ["Windows"]`
   - Builds command: `["cdb.exe", "-z", str(dump_path), "-y", symbol_path_str, "-c", ".reload /f /i; !analyze -v; q"]`
   - Parses output via regex (ported from prototype's `cdb.py`): extracts `exception_code_raw`, `exception_address`, `faulting_module`, `faulting_function`, stack frames.
   - Maps NTSTATUS codes to `FaultClass` using `fault_codes.py` mapping table.
   - Computes `symbol_resolution_score` by counting frames with non-None `function`.
   - Applies noise filter to `raw_text_excerpt`.

2. **`backends/debug/gdb_worker.py`** - `GdbBackend(DebugBackend)` (Linux):
   - `SUPPORTED_FORMATS = [DumpFormat.LINUX_CORE, DumpFormat.WINDOWS_MINIDUMP]`
   - Command: `["gdb", "--batch", "--quiet", "-ex", "core-file {dump}", "-ex", "bt 20", "-ex", "info registers", "-ex", "quit"]`
   - Parses `bt` output into `StackFrame` list.
   - Maps POSIX signals to `FaultClass`.

3. **`backends/debug/lldb_worker.py`** - `LldbBackend(DebugBackend)` (macOS):
   - Command: `["lldb", "--batch", "-c", str(dump_path), "-o", "bt all", "-o", "register read", "-o", "quit"]`
   - Maps macOS exception types to `FaultClass`.

4. **`backends/debug/__init__.py`** - `create_debug_backend()` factory with engine selection: `auto` tries `WinDbgJSBackend` first on Windows via `_windbg_js_available()` probe, falls back to `CdbBackend`; `cdb` / `windbg_js` force a specific engine. `GdbBackend` / `LldbBackend` are selected on Linux / Darwin as before.

5. **Symbol path resolution** in `backends/debug/_symbol_path.py` - `resolve_symbol_path(config_value: str | None) -> Path` using `pathlib` and the cross-platform defaults from the design spec.

6. **`backends/debug/windbg_js_worker.py`** - `WinDbgJSBackend(DebugBackend)` (Windows only):
   - `SUPPORTED_FORMATS = [DumpFormat.WINDOWS_MINIDUMP]`, `SUPPORTED_PLATFORMS = ["Windows"]`
   - `_CallbackBridge` RAII context manager: binds `HTTPServer` to `("127.0.0.1", 0)` (OS-assigned ephemeral port), daemon thread, instance-level `queue.Queue[str]`. **No shared module-level state.**
   - `_make_handler(queue)` closure - returns a `BaseHTTPRequestHandler` subclass that enqueues the raw POST body.
   - `_prepare_js(port, settings) -> str` - reads `backends/debug/assets/windbg_diagnostic.js`, substitutes `__CALLBACK_URL__`, `__MAX_FAULTING_FRAMES__`, `__MAX_OTHER_FRAMES__`.
   - `_build_command_sequence()` - `["cdb.exe", "-z", dump, "-y", sym_chain, "-c", ".scriptload \"{tmp_js}\"; g; q"]`.
   - `_parse(raw_json, source) -> DebugExtractionResult` - parses DDM JSON fields (see [Part II payload mapping](#c2-debugbackend)). Faulting-thread frames become `stack_frames`; all-threads summary becomes `raw_text_excerpt`.
   - Raises `DebugExtractionError` when `"JsProvider.dll"` string absent from subprocess output, or callback timeout expires.

7. **`backends/debug/assets/windbg_diagnostic.js`** - Production JS script. Queries DDM for `ExceptionCode`, `ExceptionAddress`, faulting thread full frames (`maxFaultingFrames`), all other threads summarized (`maxOtherFrames`), module names and base addresses. Calls back via `ActiveXObject("MSXML2.XMLHTTP")` POST.

8. **`DebugSettings`** extended with `engine` (`auto|cdb|windbg_js`), `callback_timeout_seconds`, `max_faulting_frames`, `max_other_thread_frames`.

9. **`tests/unit/test_debug_backends.py`** - existing CDB/GDB/LLDB/factory/symbol-path tests, plus new `WinDbgJSBackend` tests:
   - DDM JSON fixture → correct `DebugExtractionResult` (NTSTATUS, address, faulting module, frames, score).
   - command sequence contains `.scriptload`.
   - `_CallbackBridge.__enter__` binds port 0; `bridge.port` is non-zero.
   - two concurrent bridges have independent queues.
   - stdout without `JsProvider.dll` → `DebugExtractionError`; empty queue → `DebugExtractionError`.
   - `engine="windbg_js"` on `win32` → `WinDbgJSBackend`; `engine="auto"` with unavailable JS → `CdbBackend`.

10. **`tests/unit/fixtures/sample_windbg_js_payload.json`** - realistic DDM JSON payload (5 faulting frames, 4 resolved; 2 other threads; NTSTATUS `0xC0000005`; ExceptionAddress; FaultingModule).

### Success Criteria

- `CdbBackend.extract()` on the CDB fixture returns a valid `DebugExtractionResult`.
- `WinDbgJSBackend.extract()` on the DDM JSON fixture returns a valid `DebugExtractionResult` with correct fault class, address, and frames.
- `_CallbackBridge` uses a fresh per-instance queue - two simultaneous instances cannot receive each other's payloads.
- Factory `engine="auto"` selects `WinDbgJSBackend` when available, `CdbBackend` otherwise - without raising; raises `PlatformNotSupportedError` on an unsupported platform.
- `pytest tests/unit/test_debug_backends.py` passes.

---

## Phase 5: Multi-Agent System Engine

**Goal:** Implement the complete LangGraph state graph with four agents, weighted consensus, and HITL trigger. (Full MAS spec remains in `PRODUCTION_DESIGN_SPEC.md` §7.)

### Deliverables

1. **`core/consensus.py`** - `ConsensusEvaluator`:
   - `calculate(state, weights) -> float` - weighted CS formula.
   - `is_converged(score, threshold, previous_score) -> bool` - True if `score >= threshold` for the same primary hypothesis in the last two consecutive calls.
   - `is_deadlocked(score, round, max_rounds, hitl_threshold) -> bool`.

2. **`agents/os_kernel.py`** - `OSKernelAgent(BaseAgent)`: kernel-debugger persona; builds context from `incident_brief`; calls `ai_backend.generate()` with `OSKernelOutput` schema; appends `AgentTurn`; updates `consensus_score`.

3. **`agents/code_analyst.py`** - `CodeAnalystAgent(BaseAgent)`: includes previous `OSKernelOutput`; injects `user_assumption`; generates `CodeAnalystOutput`.

4. **`agents/log_historian.py`** - `LogHistorianAgent(BaseAgent)`: queries `VectorStore.search_similar()` with the conditional-injection rule; builds `LogHistorianOutput`.

5. **`agents/skeptic.py`** - `SkepticAgent(BaseAgent)`: three assertion checks before the LLM; a failed programmatic assertion (module not in frames) sets `confirmed=False` with no LLM call.

6. **`core/orchestrator.py`** - `Orchestrator`: builds the `StateGraph` (data_adapter, os_kernel, code_analyst, log_historian, skeptic, output_synthesizer, hitl_handler); conditional edges from `skeptic_node`; `run()`, `run_streaming()`, `continue_investigation()`.

7. **`tests/unit/test_orchestrator.py`** + **`tests/unit/test_consensus.py`** - mock-AI pipeline convergence, skeptic-triggered re-round, deadlock → HITL, token accounting, CS-formula boundaries.

### Success Criteria

- Full pipeline (Mock AI + Data Adapter stub) completes without exception; converges in 2 rounds at `confidence=0.90`; HITL at `confidence=0.40` for 4 rounds.
- `pytest tests/unit/test_orchestrator.py tests/unit/test_consensus.py` passes.

---

## Phase 6: Storage Backends

**Goal:** Implement filesystem, SQLite, and S3 storage backends plus a PostgreSQL stub, all behind the same `RelationalStore`/`ObjectStore` interface. (Interface in Part II C.3.)

### Deliverables

1. **`backends/storage/filesystem_store.py`** - `FilesystemStore(RelationalStore, ObjectStore)`: reports at `{reports_dir}/{incident_id}.json`; hash index at `{reports_dir}/_hash_index/{dump_hash}` for O(1) `find_by_hash`; raw artifacts at `{objects_dir}/{incident_id}/{filename}`; all I/O via `asyncio.to_thread`; path-traversal guard on every resolved path.
2. **`backends/storage/sqlite_store.py`** - `SQLiteStore(RelationalStore)`: single `reports` table `(incident_id PK, dump_hash, created_at, mode, report_json)` + unique index on `dump_hash`; new `sqlite3.connect()` per call wrapped in `asyncio.to_thread`; indexed `find_by_hash`.
3. **`backends/storage/s3_store.py`** - `S3Store(RelationalStore, ObjectStore)`: sync `boto3` wrapped in `asyncio.to_thread`; reports at `reports/{id}.json`, hash index at `hash-index/{hash}`, artifacts at `objects/{id}/{file}`; MinIO via `s3_endpoint_url`.
4. **`backends/storage/postgres_store.py`** - `PostgresStore(RelationalStore)` stub: all methods raise `NotImplementedError`.
5. **`backends/storage/__init__.py`** - `create_storage_backends(settings) -> tuple[RelationalStore | None, ObjectStore | None]`.
6. **`StorageSettings`** additions: `provider`, `reports_dir`, `objects_dir`, `db_path`, `s3_endpoint_url` + validator.
7. **`tests/unit/test_storage_backends.py`** - all backends round-tripped without external services (filesystem in `tmp_path`, sqlite `:memory:`, s3 patched `boto3.client`, postgres stub raises, factory type checks).

### Success Criteria

- `find_by_hash()` returns the stored `RCAReport` on a second same-hash call for filesystem/sqlite/s3, `None` for an unknown hash.
- `upload_raw()` → `get_raw()` round-trips exact bytes.
- `PostgresStore` raises `NotImplementedError` on all methods.
- `pytest tests/unit/test_storage_backends.py` passes with zero external calls.

---

## Phase 6.1: Code Backend

**Goal:** Implement the optional `CodeBackend` family (Data Adapter Stage 8). Three adapters behind one interface; PDB gives highest-fidelity attribution on Windows. (Interface + adapters in [Part II §C.5](#c5-codebackend).)

### Deliverables

1. **`backends/code/git_adapter.py`** - `GitCodeAdapter(CodeBackend)`: `get_commits_before` via `git log` with `\x1f`/`\x1e`-delimited pretty format; `get_file_diff` via `git show`; `blame` via `git blame --line-porcelain`. All access via list-form `subprocess.run` with `cwd=repo_path` + timeout; missing `.git`/binary → `CodeBackendError`; path-traversal guard.
2. **`backends/code/filesystem_adapter.py`** - `FilesystemCodeAdapter(CodeBackend)`: directory walk synthesizing one `CommitRecord` per in-window file (`sha="fs:…"`); `get_file_diff` returns current contents with a `--- (no VCS history)` header; per-line `BlameRecord` with `authored_at=None`.
3. **`backends/code/pdb_adapter.py`** - `PdbCodeAdapter(CodeBackend)` (Windows-only): `pdbstr.exe -r -s:srcsrv` extracts the SrcSrv stream; one `CommitRecord` per unique SrcSrv SHA (`author="PdbSourceServer"`, ignores `window_hours`); diff/blame delegate to `git` with the exact SHA; non-Windows → `CodeBackendError`.
4. **`backends/code/_paths.py`** - shared `safe_repo_path` traversal guard.
5. **`backends/code/__init__.py`** - `create_code_backend(settings) -> CodeBackend | None` (`None` when disabled; routes `git`/`filesystem`/`pdb`).
6. **`CodeBackendSettings`** + **`CodeBackendError`** in `core/exceptions.py`.
7. **Stage 8 fail-open** - Data Adapter catches `CodeBackendError`, logs a warning, continues with empty `code_history`.
8. **`tests/unit/test_code_backends.py`** + **`tests/unit/fixtures/sample_srcsrv_stream.txt`**.

### Success Criteria

- `GitCodeAdapter.get_commits_before()` parses a fixture `git log` payload (newest first).
- `FilesystemCodeAdapter` returns only in-window files capped to `limit`, no `git` dependency.
- `PdbCodeAdapter.get_commits_before()` parses a fixture SrcSrv stream into one `CommitRecord`; constructor raises on non-Windows; returns `[]` when `pdbstr.exe` exits non-zero.
- `create_code_backend()` returns `None` when disabled.
- `pytest tests/unit/test_code_backends.py` passes with zero external calls.

---

## Phase 6.2: Log Backend

**Goal:** Implement the optional `LogBackend` family queried in Data Adapter Stage 4 - a real local-file adapter plus a Fluent stub; ELK deferred. (Interface + adapters in [Part II §C.4](#c4-logbackend).)

### Deliverables

1. **`backends/log/file_adapter.py`** - `FileLogAdapter(LogBackend)`: `query_window` resolves `{file_root}/{service}*.{log,txt}`, reads via `asyncio.to_thread`, filters by timestamp window + severity; returns `[]` when `file_root` unset; traversal guard.
2. **`backends/log/fluent_adapter.py`** - `FluentAdapter(LogBackend)` stub: constructor warns; `query_window` raises `NotImplementedError`; intended design documented in the module docstring.
3. **`backends/log/__init__.py`** - `create_log_backend(settings) -> LogBackend | None` (`file`/`fluent`; `elk` → `NotImplementedError`; unknown → `ValueError`).
4. **`LogSettings`** in `config/settings.py` (`provider`, `file_root`, `default_severity_levels`, `fluent_host`, `fluent_port`, `fluent_tag_prefix`).
5. **Stage 4 wiring** - `DataAdapter.process` gains `log_backend`; when a backend, `service`, and `incident_timestamp` are all present, `query_window` lines merge with file lines before Drain3 clustering; wrapped in try/except (fail open to file-only).
6. **`tests/unit/test_log_backends.py`** + `test_data_adapter_merges_log_backend_lines`.

### Success Criteria

- `FileLogAdapter.query_window()` returns only lines inside the window and matching severity.
- `FluentAdapter.query_window()` raises `NotImplementedError`; the Data Adapter degrades to file-only.
- `create_log_backend()` returns the correct adapter per provider.
- `pytest tests/unit/test_log_backends.py` passes with zero external calls.

---

## Phase 7: CLI & Local Mode

**Goal:** Implement the Typer CLI supporting local (in-process) analysis. Options come from explicit CLI flags OR a JSON config file with the same key names; CLI flag > JSON config > hardcoded default.

### Deliverables

1. **`cli/_config.py`** - JSON config support: `DEFAULT_CONFIG_PATH`, `load_analyze_config()`, `save_analyze_config()`, and the `AnalyzeConfig` schema that is the single source of truth for option keys/types/defaults.
2. **`cli/_formatters.py`** - `json_formatter()` and the live-display driver `stream_and_display()` that attaches a `views.RichView`/`WarRoomView` to the orchestrator event bus.
3. **`cli/aegis_logging.py`** - `configure_logging()` (loguru sink level + sensitive-data redaction filter; clamps noisy third-party loggers to WARNING).
4. **`cli/commands.py`** - Typer app with `analyze`, `export`, `server`, `config show`, `config set`. `analyze` assembles `IncidentSource` (stashing the log service in `metadata["service"]`), creates backends via the factories, instantiates the `Orchestrator`, and renders `rich`/`json`/`json-full`/`quiet` output. Exit 1 on `HITLRequest`.
5. **`RelationalStore.load_recent(limit=100)`** added and implemented across stores; powers `aegis export`.
6. **`tests/unit/test_cli.py`** - `CliRunner` tests for help, config-show redaction, `--save-config`, config-file defaults, CLI-over-config precedence.
7. **End-to-end smoke test** (`tests/integration/test_e2e_cli.py`) with a mocked `Orchestrator.run`.

### Success Criteria

- `aegis analyze --help` lists all flags including `--config` and `--save-config`.
- `aegis config show` redacts secrets as `***`.
- `--save-config` round-trips to the same effective options.
- A JSON config value is used absent a flag; a flag overrides it.
- `pytest tests/unit/test_cli.py` and `tests/integration/test_e2e_cli.py` pass with a mocked orchestrator.

> The logging/evidence/process configuration consumed by this phase is being
> restructured into three independent channels - see
> [Part III](#part-iii--new-task-three-channel-logging-application--evidence--investigation-process).

---

## Phase 8: REST API Layer

**Goal:** Implement the FastAPI application with all endpoints, SSE streaming, auth middleware, and background task management. (Full API spec in `PRODUCTION_DESIGN_SPEC.md` §9.)

### Deliverables

1. **`api/app.py`** - `create_app(settings) -> FastAPI`: registers routers, attaches auth + rate-limit middleware, initializes/closes backends on startup/shutdown.
2. **`api/routes/incidents.py`** - `POST /v1/incidents/analyze` (multipart, uploads raw to object store, starts `Orchestrator.run()` as a background task, returns immediately); `POST /{id}/continue` (HITL); `GET /` (list).
3. **`api/routes/stream.py`** - `GET /v1/incidents/{id}/stream`: SSE `StreamingResponse`, subscribes to the per-incident event queue, heartbeat every 15 s, 404 on unknown id.
4. **`api/routes/reports.py`** - `GET /v1/incidents/{id}/report`: 200 + report when complete, 202 while running.
5. **`api/middleware/auth.py`** - `X-Aegis-API-Key` header, bcrypt-hashed compare, 401 on failure, excludes `/health`.
6. **`api/middleware/rate_limit.py`** - via `slowapi`.
7. **Wire `aegis server`** to `create_app()`.
8. **`tests/integration/test_api.py`** - analyze→poll flow, SSE ordering, auth 401, rate-limit 429 (mocked orchestrator).

### Success Criteria

- `POST /analyze` returns within 200 ms (no synchronous LLM call).
- SSE stream delivers agent turns in order and closes with `complete`.
- Auth blocks all routes except `/health` without a valid key.
- `pytest tests/integration/test_api.py` passes with a mocked orchestrator.

---

## Phase 9: Secure Code Sandbox

**Goal:** Implement the Docker-based sandbox executor that compiles and validates AI-generated patches. (Full sandbox spec in `PRODUCTION_DESIGN_SPEC.md` §10.)

### Deliverables

1. **`sandbox/executor.py`** - `SandboxExecutor.validate(patch, language) -> ValidationResult` via `asyncio.create_subprocess_exec` with timeout; `passed=None` + warning when Docker is unavailable (sandbox is optional).
2. **`sandbox/validators.py`** - language detection (extension + MIME) → Docker image tag.
3. **`sandbox/Dockerfile.{cpp,python,java,typescript}`** - minimal compiler-only images, no network tools.
4. **`Makefile`** target `build-sandbox-images`.
5. **Integration with `agents/code_analyst.py`** - validate after producing `probabilistic_fix`; on `passed=False`, feed compiler output back and retry once; populate `fix_validation_result`.
6. **`tests/unit/test_sandbox.py`** - mocked `asyncio.create_subprocess_exec` for valid/invalid/no-Docker paths.

### Success Criteria

- Valid C++ patch → `passed=True`; syntax error → `passed=False` with compiler text.
- Executor returns gracefully (no hang) when Docker is unavailable.
- Containers have no network access (`docker inspect`).

---

## Phase 10: Testing & Hardening

**Goal:** Achieve 80%+ ground-truth accuracy, sub-12k-token average, passing CI, and production-ready security.

### Deliverables

1. **Ground truth incidents** - ≥10 in `tests/ground_truth/incidents/`, each with raw inputs, `expected_output.json`, and a `README.md`.
2. **`tests/ground_truth/eval_runner.py`** - runs the full pipeline (real LLM), scores PASS/PARTIAL/FAIL, asserts ≥80% PASS, prints token usage.
3. **`tests/benchmarks/token_budget.py`** - asserts the average incident brief ≤12,000 tokens (`tiktoken`).
4. **Security hardening checklist** - `SensitiveFilter` on all loggers; list-form `subprocess` everywhere; path-traversal validation; bcrypt-hashed API keys; Presidio before any external LLM call; sandbox `--network=none --cap-drop ALL --read-only`.
5. **`docker-compose.yml`** + **`docker-compose.test.yml`** - full local stack and test-only stack.
6. **`Makefile`** targets: `install`, `lint`, `typecheck`, `test`, `test-integration`, `test-ground-truth`, `benchmark-tokens`, `build-sandbox-images`, `up`, `down`.
7. **Updated `docs/README.md`** documentation registry.

### Success Criteria

- Ground truth eval: ≥8 of 10 PASS; token benchmark average ≤12,000 tokens.
- `mypy src/ --strict` passes; `pytest tests/unit/` ≥90% line coverage on `core/` and `agents/`.
- `docker-compose up` starts a fully operational local stack.

---

## Dependency Graph (phases with hard prerequisites)

```
Phase 1 (Foundation)
  │
  ├──► Phase 2 (Data Adapter)          ← needs schemas
  │       └──► Phase 5 (MAS)           ← needs adapter output schema
  ├──► Phase 3 (AI Backends)
  │       └──► Phase 5 (MAS)           ← needs AIAPIBackend
  ├──► Phase 4 (Debug Backends)
  │       └──► Phase 2 (Data Adapter)  ← adapter calls debug backend
  ├──► Phase 6 (Storage)
  │       └──► Phase 5 (MAS)           ← orchestrator calls storage
  ├──► Phase 6.1 (Code Backend)        ← optional; Stage 8 calls it
  │       └──► Phase 7 (CLI)           ← --code-provider / --repo wire it in
  ├──► Phase 6.2 (Log Backend)         ← optional; Stage 4 calls it
  │       └──► Phase 7 (CLI)           ← log ingestion wired in
  Phase 5 (MAS Engine)
  ├──► Phase 7 (CLI)                   ← CLI calls orchestrator; first E2E gate
  │       └──► Phase 8 (API)           ← API wraps orchestrator
  └──► Phase 9 (Sandbox)               ← Code Analyst calls sandbox
  Phases 7, 8, 9 ──► Phase 10 (Testing & Hardening)
```

**Minimum viable product** (end-to-end pipeline, no API): Phases 1 → 4 → 2 → 3 → 5 → 6 → 7. Phases 6.1 / 6.2 are optional enrichers.
**Full production deployment:** all 10 phases.

---

# Part II - Data Adapter & Backend Specifications

> Merged from the design spec. Code, `config.yaml`, JavaScript, and directory-tree
> examples have been trimmed; what remains is the **interface contracts, data
> shapes, and algorithms** for the Data Adapter and the backend families. All
> inter-component types are **Pydantic v2** models.

## A. Shared Data Types (backend / adapter I/O)

### A.1 IncidentSource (Data Adapter input)

```python
class IncidentMode(str, Enum):
    CRASH_DUMP        = "crash_dump"        # Binary .dmp/.core file provided
    LOG_FORENSICS     = "log_forensics"     # Log files only, no binary dump
    LIVE_PROCESS      = "live_process"      # PID or service name
    TELEMETRY_ANOMALY = "telemetry_anomaly" # Metric threshold breach

class DumpFormat(str, Enum):
    WINDOWS_MINIDUMP  = "windows_minidump"  # .dmp - MiniDumpWriteDump()
    LINUX_CORE        = "linux_core"        # .core - ELF core dump
    APPLE_CRASHREPORT = "apple_crashreport" # .ips / .crash
    BREAKPAD          = "breakpad"          # .dmp - Google Breakpad

class IncidentSource(BaseModel):
    mode: IncidentMode
    incident_timestamp: datetime | None = None  # UTC - anchor for temporal windowing
    dump_path: Path | None = None
    dump_format: DumpFormat | None = None
    dump_hash: str | None = None                 # SHA-256, computed before any backend call
    log_paths: list[Path] = []
    screenshot_paths: list[Path] = []
    network_capture_paths: list[Path] = []       # .pcap - metadata shown in TRACE evidence
    symbol_path: Path | None = None
    user_assumption: str | None = None           # Capped to 500 tokens by the adapter
    metadata: dict[str, str] = {}                # repo tags, environment, app type, "service"
```

### A.2 FaultClass and platform mapping (`core/fault_codes.py`)

`FaultClass` values: `MEMORY_ACCESS_VIOLATION`, `NULL_POINTER_DEREFERENCE`,
`USE_AFTER_FREE`, `STACK_OVERFLOW`, `INTEGER_DIVIDE_BY_ZERO`, `DEADLOCK`,
`ASSERTION_FAILURE`, `UNHANDLED_EXCEPTION`, `RESOURCE_EXHAUSTION`, `UNKNOWN`.

Each `DebugBackend` maps its platform-native fault indicator to `FaultClass`;
agent prompts use `FaultClass` names, never raw hex/signal codes.

| Platform | Native Code | FaultClass |
|---|---|---|
| Windows NTSTATUS | `0xC0000005` | `MEMORY_ACCESS_VIOLATION` |
| Windows NTSTATUS | `0xC00000FD` | `STACK_OVERFLOW` |
| Windows NTSTATUS | `0xC0000094` | `INTEGER_DIVIDE_BY_ZERO` |
| Linux signal | `SIGSEGV (11)` | `MEMORY_ACCESS_VIOLATION` |
| Linux signal | `SIGBUS (7)` | `MEMORY_ACCESS_VIOLATION` |
| Linux signal | `SIGFPE (8)` | `INTEGER_DIVIDE_BY_ZERO` |
| macOS exception | `EXC_BAD_ACCESS (1)` | `MEMORY_ACCESS_VIOLATION` |
| macOS exception | `EXC_ARITHMETIC (3)` | `INTEGER_DIVIDE_BY_ZERO` |

### A.3 DebugExtractionResult (DebugBackend output)

```python
class StackFrame(BaseModel):
    frame_number: int
    module: str | None           # Resolved module name
    function: str | None         # Resolved function name (None if no symbols)
    source_file: str | None
    source_line: int | None
    instruction_address: str     # Hex address always preserved

class DebugExtractionResult(BaseModel):
    fault_class: FaultClass
    exception_code_raw: str      # Native hex or signal string
    exception_address: str       # Instruction pointer (RIP/PC/LR)
    faulting_module: str | None
    faulting_function: str | None
    stack_frames: list[StackFrame]   # Top 20 frames default
    debug_timestamp: datetime | None
    symbol_resolution_score: float   # 0.0–1.0: fraction of resolved frames
    raw_text_excerpt: str            # ≤8,000 chars after the adapter noise filter
```

### A.4 Code Backend record types (`CodeBackend` output)

Consumed by Data Adapter Stage 8; serialize into `IncidentBrief.code_history`.

```python
class CommitRecord(BaseModel):
    sha: str                     # Full/short SHA; "fs:" pseudo-id for FilesystemCodeAdapter
    author: str                  # "name <email>"; "unknown" when VCS metadata absent
    authored_at: datetime        # UTC; file mtime for FilesystemCodeAdapter
    message: str                 # First line / subject; "" when unavailable
    changed_files: list[str]     # Repo-relative paths

class BlameRecord(BaseModel):
    line_number: int             # 1-based
    sha: str                     # Commit that last touched the line; "fs:" when no VCS
    author: str                  # "unknown" when no VCS
    authored_at: datetime | None # None when no VCS metadata
    line_content: str
```

`LogBackend` returns plain `list[str]` log lines - no dedicated record type; the
lines flow straight into the Stage 4 log pipeline.

---

## B. Data Adapter Layer (`core/data_adapter.py`)

A **non-LLM preprocessing pipeline** that converts raw telemetry into a
token-dense incident brief. It runs synchronously before any agent is invoked.

### B.1 Pipeline stages (in order)

```
IncidentSource
    │
    ▼ Stage 1: Source Validation & Hash Computation
    │   - Verify file existence and magic bytes; compute dump_hash = SHA-256
    │     before any backend call; determine DumpFormat by magic bytes (not extension)
    │
    ▼ Stage 2: Dump Extraction (Debug Backend call)
    │   - DebugBackend.extract() → DebugExtractionResult; compute symbol_resolution_score
    │   - If score < 0.50: prepend [LOW SYMBOL COVERAGE: {score:.0%}] to the brief
    │
    ▼ Stage 3: Global Noise Pre-Filter (text normalization)
    │   - Strip DBGHELP "file not found" lines; replace fill patterns
    │     (0xCCCCCCCC/0xDDDDDDDD/0xFEEEFEEE → <fill>); drop the DLL load list
    │     ("*** WARNING:" … "EXCEPTION_ANALYSIS:"); 8,000-char head+tail truncation (4k/4k)
    │
    ▼ Stage 4: Log Processing
    │   - Source lines from (a) IncidentSource.log_paths and (b) a configured
    │     LogBackend.query_window(service, t−window, t+window, severity_levels)
    │     when service + incident_timestamp are present; merge both streams
    │   - Temporal window ±30 s; Drain3 clustering; dedup heartbeats >3× → "msg (×N)";
    │     severity isolation (keep FATAL/CRITICAL/ERROR/WARNING; drop INFO/DEBUG unless
    │     within ±5 s of the incident); enforce a 2,000-token budget
    │
    ▼ Stage 5: Screenshot OCR (optional)
    │   - pytesseract/EasyOCR → UIContext { error_message, visible_timestamp, ui_elements }
    │   - Discard OCR output when confidence < 0.60
    │
    ▼ Stage 6: PII Scrubbing (always runs, before any text leaves the adapter)
    │   - Presidio recognizers: EMAIL, PHONE, CREDIT_CARD, CRYPTO, US_SSN, IP_ADDRESS,
    │     URL, AWS_KEY, DB_CONNECTION_STRING → stable hash tokens ([REDACTED_EMAIL_1])
    │   - Substitution audit map stored separately; never sent to the LLM
    │
    ▼ Stage 7: User Assumption Enforcement
    │   - Tokenize user_assumption; truncate to 500 tokens with a warning
    │
    ▼ Stage 8: Code History Query (if CodeBackend configured)
    │   - CodeBackend.get_commits_before(repo_path, incident_timestamp, window_hours=2)
    │   - Extract changed files, authors, messages - top 5 by proximity
    │
    ▼ Stage 9: Assemble Incident Brief (JSON-serializable)
    └──► IncidentBrief (passed to the MAS as the incident_brief field)
```

### B.2 IncidentBrief structure (Data Adapter output)

```json
{
  "mode": "crash_dump",
  "dump_hash": "sha256:...",
  "fault_class": "memory_access_violation",
  "exception_code_raw": "0xC0000005",
  "exception_address": "0x00007ff8ab12c3f0",
  "faulting_module": "db_writer.dll",
  "faulting_function": "db_writer::serialize",
  "symbol_resolution_score": 0.87,
  "stack_frames": [
    {"frame": 0, "module": "db_writer.dll", "function": "db_writer::serialize", "line": 142}
  ],
  "log_summary": "14:01:58 WARN: DB write latency 480ms ...\n(compressed: 3 INFO heartbeat templates)",
  "ui_context": null,
  "code_history": [
    {"sha": "a1b2c3", "message": "Increase timeout threshold", "author": "dev@corp", "files": ["db_writer.cpp"]}
  ],
  "user_assumption": "The DB write pool was reduced from 10 to 5 connections in yesterday's deploy.",
  "low_symbol_coverage_warning": null
}
```

### B.3 Conditional history injection (Log Historian trigger)

The Log Historian Agent queries the Qdrant vector store for semantically similar
historical incidents. Injection is conditional:

- Inject if `faulting_module` appears in ≥2 of the last 10 stored incidents, **or**
- Inject if `fault_class` matches ≥3 of the last 10 stored incidents.
- Otherwise omit (saves ~300 input tokens on non-recurring crashes).

Implemented as the pure helper `DataAdapter.should_inject_history(brief, recent)`;
the Log Historian Agent supplies `recent` from the vector store.

### B.4 Implementation notes (authoritative behavior)

1. **`IncidentBrief` is a Pydantic model** (`core/schemas.py`), not a bare dict.
   `process()` returns an `IncidentBrief`; the orchestrator serializes it with
   `model_dump(mode="json")` into `InvestigationState["incident_brief"]`. The JSON
   shape in §B.2 is unchanged.
2. **PII scrubbing always runs via a deterministic regex baseline**, with Presidio
   NER layered on when the `pii` extra is installed - emails, IPv4, AWS keys,
   credit-cards, and DB connection strings are always scrubbed. The substitution
   map is **never** placed in the `IncidentBrief`; it is exposed via
   `DataAdapter.last_pii_substitution_map` for out-of-band (encrypted) persistence.
3. **`process()` signature:** `async def process(source, debug_backend=None,
   code_backend=None, log_backend=None) -> IncidentBrief`. All three backends are
   optional (log-only mode, pre-Phase-4 usage). `code_backend` drives Stage 8;
   `log_backend` is queried in Stage 4 and merged before clustering. The reusable
   noise filter is the module-level `apply_noise_filter(text)`, imported directly
   by Phase 4 debug backends.
4. **Token counting** uses `tiktoken` (`cl100k_base`) with an offline-safe `chars/4`
   fallback (`core/tokens.py`), so budgeting never breaks in air-gapped environments.

---

## C. Backend Interfaces (`backends/base.py`)

All backend ABCs are defined here using Python's `abc` module.

### C.1 AIAPIBackend

```python
class AIAPIBackend(ABC):
    model_name: str

    @abstractmethod
    async def generate(self, system_prompt: str, messages: list[dict],
                       output_schema: type[BaseModel] | None = None) -> BaseModel | str:
        """Validated Pydantic instance if output_schema given, else raw string.
        Raises AIOutputValidationError on schema mismatch after one correction
        retry. Uses provider prompt-caching on the system_prompt block."""

    @abstractmethod
    def stream(self, system_prompt: str, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Token-by-token stream for live UI display."""
```

**Provider notes.** Anthropic: `cache_control:{"type":"ephemeral"}` on the system
block; structured output via a `tools` `input_schema` matching the model's JSON
schema; default model `claude-sonnet-4-6`. OpenAI: `response_format={"type":
"json_schema", ...}`; `stream=True` + `stream_options={"include_usage": True}`.

**As-built (Phase 3):**
1. **Shared base class** `_BaseAIBackend` owns structured-output validation, the
   one-shot correction retry, and token accounting; each provider implements only
   `_invoke()` and `stream()` - identical retry/validation semantics across providers.
2. **`stream()` is a plain `def` returning `AsyncGenerator`** in the ABC; call it
   without `await`: `async for token in backend.stream(...)`.
3. **Token tracking via `last_usage`** (`{"input_tokens","output_tokens"}`,
   accumulated across the retry); the calling agent adds it to `state["token_tracker"]`.
4. **Correction retry:** on `ValidationError`/`JSONDecodeError`, append the invalid
   output + a user turn naming the schema and errors, re-invoke once; a second
   failure raises `AIOutputValidationError`.
5. **OpenAI strict schema:** `_to_openai_strict_schema()` sets `additionalProperties:
   false` recursively, lists all properties as `required`, strips `default`.
6. **SDK clients typed as `Any`** to avoid coupling to SDK `TypedDict`s under
   `mypy --strict`; API keys read from the environment by the SDKs.
7. **Provider-aware model resolution:** `AISettings.resolved_model` substitutes the
   provider's default (`gpt-5.4` / `claude-sonnet-4-6`) only when the configured
   model does not belong to the selected provider; an explicit, provider-matching
   model is always respected.
8. **OpenAI reasoning-model contract:** gpt-5-class / o-series reject `max_tokens`
   and non-default `temperature`; `_completion_kwargs()` sends `max_completion_tokens`
   (floored at 16,000) and omits `temperature` for those.
9. **OpenAI client resilience:** constructed with `timeout=300s`, `max_retries=4`
   (SDK backoff on timeout/429/5xx) so one transient timeout cannot abort the graph.

### C.2 DebugBackend

```python
class DebugBackend(ABC):
    SUPPORTED_FORMATS: ClassVar[list[DumpFormat]]
    SUPPORTED_PLATFORMS: ClassVar[list[str]]   # "Windows", "Linux", "Darwin"

    @abstractmethod
    def extract(self, source: IncidentSource, symbol_path: Path | None) -> DebugExtractionResult:
        """Opens the dump via the native debugger; maps native fault codes to
        FaultClass; runs in a RAII subprocess. Timeout 300 s (configurable)."""

    @abstractmethod
    def _build_command_sequence(self, source: IncidentSource, symbol_path: Path) -> list[str]: ...
```

**Factory** (`backends/debug/__init__.py`): selects by `sys.platform` -
`win32`→`CdbBackend`/`WinDbgJSBackend`, `linux`→`GdbBackend`, `darwin`→`LldbBackend`;
unknown → `PlatformNotSupportedError`. Engine `auto` probes for `JsProvider.dll`
and prefers `WinDbgJSBackend` on Windows, else `CdbBackend`; `cdb`/`windbg_js` force one.

**Symbol path defaults** (via `pathlib`): Windows `%LOCALAPPDATA%\AegisSWR\symbols`;
Linux/macOS `~/.cache/aegis-swr/symbols`; override with `AEGIS_SYMBOL_CACHE`.

> **PDB dual-use note.** A `.pdb` carries two information classes used at different
> stages: address→symbol (function/line/type) used by the **Debug Backend** in
> Stage 2 (`cdb.exe -y`), and the Source Server (SrcSrv) stream → exact VCS revision
> used by the **Code Backend** (§C.5.4) in Stage 8 (`pdbstr.exe -r -s:srcsrv`). Both
> read the same file for orthogonal purposes; the dual reference is intentional.

**As-built (Phase 4):**
1. **Shared base class** `_BaseDebugBackend` owns the `extract()` template:
   `_validate` → `_build_command_sequence` → `_run` (RAII subprocess + timeout) →
   `_parse`. Each worker implements only `_build_command_sequence` and `_parse`.
2. **Errors:** missing/absent dump → `DebugExtractionError`; missing debugger binary
   → `PlatformNotSupportedError`; timeout → `DebugExtractionError`.
3. **`extract` is synchronous** (per the ABC); the Data Adapter calls it inline. All
   `subprocess.run` calls use list-form argv - never `shell=True`.
4. **Fault mapping:** CDB via `map_windows_ntstatus`; GDB via signal name→number +
   `map_linux_signal`; LLDB via `EXC_*` name→code + `map_macos_exception`; unmapped →
   `FaultClass.UNKNOWN`. **CDB fault-code extraction is multi-key** -
   `_extract_exception_code()` tries `EXCEPTION_CODE:`, `ERROR_CODE:`,
   `EXCEPTION_CODE_STR:`, and `ExceptionCode:` in order (a prototype defect matched
   only `EXCEPTION_CODE:` and yielded `0x0 → UNKNOWN` for real null-write dumps).
5. **Parsers are module-level functions** (`parse_cdb_frames`, etc.), unit-testable
   in isolation; `symbol_resolution_score = resolved / total`; `apply_noise_filter`
   applied to `raw_text_excerpt`.
6. **Factory** `create_debug_backend(settings, platform=None)` accepts a platform
   override for tests; `settings` is the `DebugSettings` section.

**WinDbg JavaScript backend** (`windbg_js_worker.py`) - preferred Windows engine
when `JsProvider.dll` is present; `CdbBackend` is the fallback. It accesses the
**Debugger Data Model (DDM)** directly for typed JSON (no text parsing), exposes
all threads, module load addresses, and richer frame metadata, and is the path
toward live-process analysis. Architecture - the **Callback Bridge pattern**:

1. `_CallbackBridge` (RAII) binds an `HTTPServer` to `127.0.0.1:0` (OS-assigned
   ephemeral port) on a daemon thread, with an **instance-level** `queue.Queue[str]`
   (no shared module state). `_make_handler(queue)` closes over that queue.
2. The JS asset is written to a `NamedTemporaryFile` with `__CALLBACK_URL__`
   substituted to `http://127.0.0.1:{port}/`.
3. `subprocess.run(["cdb.exe","-z",dump,"-y",sym_chain,"-c",".scriptload …; g; q"])` -
   `FileNotFoundError`→`PlatformNotSupportedError`; `TimeoutExpired`→`DebugExtractionError`;
   `JsProvider.dll` not loaded → `DebugExtractionError`.
4. `bridge.wait_for_payload(timeout)` - empty queue → `DebugExtractionError`.
5. Parse JSON → `DebugExtractionResult`; `__exit__` shuts the server down and
   deletes the temp JS.

**JSON payload → `DebugExtractionResult` mapping:**

| JSON field | Result field | Notes |
|---|---|---|
| `ExceptionCode` | `exception_code_raw`, `fault_class` | via `map_windows_ntstatus` |
| `ExceptionAddress` | `exception_address` | from `exc.Address`; more reliable than frame[0] |
| `FaultingModule` | `faulting_module` | DDM knows the module directly |
| `FaultingThread.Frames[0].Function` | `faulting_function` | top faulting-thread frame |
| `FaultingThread.Frames[:N]` | `stack_frames` | top `N` faulting frames |
| `AllThreadsSummary` (JSON string) | `raw_text_excerpt` | via `apply_noise_filter`; multi-thread context |
| faulting frames w/ non-empty Function | `symbol_resolution_score` | fraction resolved |

`DebugSettings` adds `engine` (`auto|cdb|windbg_js`), `callback_timeout_seconds`,
`max_faulting_frames`, `max_other_thread_frames` (plus `timeout_seconds`,
`symbol_cache`, `symbol_server_url`). **Prototype defects fixed:** shared
module-level callback queue → per-instance queue; fixed port-fallback chain →
`port=0`; embedded JS string → versioned asset file; missing `ExceptionAddress` →
`exc.Address`; all-threads-at-full-depth → capped frame counts; symbol path now
passed to the JS engine; raw-dict return → typed `DebugExtractionResult`; stdout
string-match for `JsProvider.dll` → explicit check with actionable error.

### C.3 StorageBackend (four concrete backends)

The ABCs are unchanged; the four concrete implementations differ only in where
data lives. The `VectorStore` (Qdrant) is a separate optional backend, not part of
the four-provider selection. `create_storage_backends(settings)` returns
`(RelationalStore | None, ObjectStore | None)`; the Orchestrator handles `None`.

| Backend | RelationalStore | ObjectStore | When to use |
|---|---|---|---|
| `FilesystemStore` | ✅ JSON files | ✅ binary files | Local dev, CI, single-host |
| `SQLiteStore` | ✅ SQLite DB | ✗ | Local dev; no binary artifacts |
| `S3Store` | ✅ JSON objects | ✅ binary objects | Cloud / MinIO without PostgreSQL |
| `PostgresStore` | ✅ (stub) | ✗ | Full production with PostgreSQL |

```python
class RelationalStore(ABC):
    async def save_report(self, report: RCAReport) -> None: ...
    async def get_report(self, incident_id: UUID) -> RCAReport | None: ...
    async def find_by_hash(self, dump_hash: str) -> RCAReport | None: ...
    async def update_hitl_response(self, incident_id: UUID, response: dict) -> None: ...

class ObjectStore(ABC):
    async def upload_raw(self, incident_id: UUID, filename: str, data: bytes) -> str: ...
    async def get_raw(self, object_key: str) -> bytes: ...

class VectorStore(ABC):
    async def upsert_incident(self, report: RCAReport) -> None: ...
    async def search_similar(self, fault_class: FaultClass,
                             faulting_module: str | None, top_k: int = 5) -> list[RCAReport]: ...
```

### C.4 LogBackend

```python
class LogBackend(ABC):
    @abstractmethod
    async def query_window(self, service: str, start_time: datetime, end_time: datetime,
                           severity_levels: list[str] | None = None) -> list[str]:
        """Returns filtered log lines from the configured source."""
```

**Always optional.** Queried in Data Adapter Stage 4 and merged with file-based
logs before clustering; `query_window` is `async` (sources may be network-backed).

| Adapter | File | Source | Status |
|---|---|---|---|
| `FileLogAdapter` | `log/file_adapter.py` | Local `.log`/`.txt` | Full implementation |
| `FluentAdapter` | `log/fluent_adapter.py` | Fluentd / Fluent Bit | **Stub** (deferred) |
| `ELKAdapter` | `log/elk_adapter.py` | Elasticsearch / ELK | Deferred - not implemented |

- **`FileLogAdapter`** - `service` maps to files under `settings.file_root`
  (globs `{file_root}/{service}*.log` and `*.txt`); when `file_root` is null it
  falls back to `IncidentSource.log_paths`. Best-effort ISO-8601/syslog timestamp
  parse; unparseable lines kept only when `incident_timestamp` is unknown.
  Case-insensitive severity filter. Reads via `asyncio.to_thread`; resolved paths
  guarded within `file_root` (traversal → `ValueError`).
- **`FluentAdapter`** (stub) - constructor warns; `query_window` raises
  `NotImplementedError`. Intended design: connect to `fluent_host:fluent_port`,
  issue a tag-scoped (`fluent_tag_prefix.{service}`) time-range query, map records
  to lines.
- **Factory** `create_log_backend(settings)` - `file`/`fluent`; `elk` →
  `NotImplementedError`; unknown → `ValueError`. The adapter is only *queried* when
  a `service` and `incident_timestamp` are both present.

`LogSettings` (`backends.log`): `provider` (`file|fluent`; elk deferred),
`file_root`, `default_severity_levels` (default `["FATAL","CRITICAL","ERROR",
"WARNING"]`), `fluent_host`, `fluent_port`, `fluent_tag_prefix`.

> **Note - this is log *ingestion*** (reading the investigated system's logs),
> distinct from Aegis's own application logging. See
> [Part III](#part-iii--new-task-three-channel-logging-application--evidence--investigation-process).

### C.5 CodeBackend

```python
class CodeBackend(ABC):
    @abstractmethod
    def get_commits_before(self, repo_path: Path, before: datetime,
                           window_hours: int = 2, limit: int = 10) -> list[CommitRecord]: ...
    @abstractmethod
    def get_file_diff(self, repo_path: Path, file_path: str, commit_sha: str) -> str: ...
    @abstractmethod
    def blame(self, repo_path: Path, file_path: str, line_range: tuple[int, int]) -> list[BlameRecord]: ...
```

**Always optional**, consumed only by Data Adapter Stage 8. All methods are
**synchronous** (called inline, like `DebugBackend.extract`); record types in §A.4.

| Adapter                 | File                         | Source of truth            | When to use                                                  |
|-------------------------|------------------------------|----------------------------|--------------------------------------------------------------|
| `GitCodeAdapter`        | `code/git_adapter.py`        | A real Git working tree    | Service built from a Git repo on the analyzer host           |
| `FilesystemCodeAdapter` | `code/filesystem_adapter.py` | A plain source dir, no VCS | Vendored/exported trees, air-gapped drops                    |
| `PdbCodeAdapter`        | `code/pdb_adapter.py`        | Windows PDB SrcSrv stream  | Windows crash with SrcSrv-indexed `.pdb`; exact build commit |

- **`GitCodeAdapter`** - all access via list-form `subprocess.run` (`cwd=repo_path`,
  `git_timeout_seconds`). `get_commits_before` uses `git log --since/--until
  --max-count --date=iso-strict --name-only` with a `%H%x1f%an <%ae>%x1f%aI%x1f%s%x1e`
  pretty format → `CommitRecord`s (newest first). `get_file_diff` → `git show {sha}
  -- {path}`. `blame` → `git blame -L --line-porcelain`. Missing `.git`/binary →
  `CodeBackendError`; repo-relative path-traversal guard.
- **`FilesystemCodeAdapter`** - no-VCS fallback: walk the tree (skip `.git`,
  `node_modules`, dot-dirs), synthesize one `CommitRecord` per in-window file
  (`sha="fs:"+sha1(relpath)[:12]`, `author="unknown"`, `authored_at=mtime`); diff
  returns full current contents with a `--- (no VCS history)` header; blame emits one
  `BlameRecord` per line (`authored_at=None`). Same traversal guard.
- **Factory** `create_code_backend(settings)` - `None` when disabled; routes
  `git`/`filesystem`/`pdb`; unknown → `ValueError`. `CodeSettings` (`backends.code`):
  `enabled`, `provider`, `repo_path`, `window_hours`, `commit_limit`,
  `git_timeout_seconds` (+ `pdb_path`, `pdbstr_timeout_seconds` for PDB). `--repo`
  supplies `repo_path` and flips `enabled=true`.

**C.5.4 PdbCodeAdapter** (Windows; SrcSrv indexing required) - derives source
attribution from the PDB's Source Server stream, eliminating the time-window
heuristic. **Prerequisites:** a readable `.pdb`; `pdbstr.exe` from Debugging Tools
for Windows on PATH (same install as `cdb.exe`); non-Windows → `CodeBackendError`.

The SrcSrv stream records `VERCTRL` (git|tfvc|svn|…), the repo URL, and per-file
revision SHAs. Behaviour: `get_commits_before` **ignores `before`/`window_hours`** -
runs `pdbstr.exe -r -p:{pdb_path} -s:srcsrv`, returns one `CommitRecord` per unique
SHA (`author="PdbSourceServer"`, mtime fallback); absent/empty stream → `[]`.
`get_file_diff`/`blame` delegate to the `VERCTRL`-specific VCS with the exact SHA
(git → `git show`/`git blame -L … {sha}`); any failure → fail open. `pdb_path`
resolution: explicit setting → auto-resolve from `dump_path` + symbol cache →
`CodeBackendError`. *Why Code, not Debug Backend:* the Debug Backend reads PDB for
"what function is at this address?" (Stage 2); the Code Backend reads it for "what
VCS revision was compiled in?" (Stage 8) - orthogonal questions, same file.

---

# Part III - New Task: Three-Channel Logging (Application / Evidence / Investigation-Process)

**Status: COMPLETE.** All phases landed - A–F (the split), H (docs), and J (legacy
migration); Phase G (wiring) was absorbed into C/E/F and Phase I (tests) shipped
per-phase. The single remaining *deferred* item is the real ELK/Fluent application-log
emitters (Phase E step 9) - accepted by schema + CLI today as warn-and-fall-back stubs.
This chapter splits today's single, overloaded severity knob into three channels:
application logging, the Evidence Stream, and the Investigation Process pane.

## III.0 Motivation - the current conflation

Today one value (`--log-severity` → the `logging.severity` config key) is fed to
**both** of these unrelated consumers:

- `configure_logging(severity, log_dir)` in `cli/aegis_logging.py` - Aegis's **own**
  diagnostic logging (a loguru stderr sink plus a single rotating *file*; there is
  no ELK/fluent emit sink today), and
- `stream_and_display(level=…)` → `make_view(console, level=…)` in `views/rich_view.py`
  - the war-room **Evidence Stream** verbosity (left pane; `EvidenceLevel` =
  INFO/DEBUG/TRACE), which *also* currently gates the agent-reasoning detail shown
  in the **Investigation Process** pane (right pane).

Worse, the `logging.provider`/`logging.service` keys are not application logging at
all - they configure the **log-ingestion** backend (`backends.log.provider` and the
`metadata["service"]` passed to `LogBackend.query_window`; see [Part II §C.4](#c4-logbackend)).
So the single `logging` section mixes three concerns. This task separates them.

## III.1 The three channels

| Channel                           | What it controls                                   | UI surface                                      | Severity range                                       |
|-----------------------------------|----------------------------------------------------|-------------------------------------------------|------------------------------------------------------|
| **Application logging**           | Aegis's own diagnostics, for later troubleshooting | file / elk / fluent sink                        | `ERROR … TRACE` (full loguru range)                  |
| **Evidence logging**              | Investigation evidence events                      | war-room **left** pane (Evidence Stream)        | `INFO` (general) or `TRACE` (everything)             |
| **Investigation-process logging** | Agent deliberation & reasoning                     | war-room **right** pane (Investigation Process) | `INFO` (headlines) or `TRACE` (full agent reasoning) |

Evidence and process are configured **independently** (D4): turning on full agent
reasoning at `process.severity = TRACE` is orthogonal to the evidence verbosity.

## III.2 Target configuration shape

```jsonc
{
  // INGESTION - config for reading the *investigated system's* logs (D1)
  "ingest": {
    "log_source": {
      "provider": "file",     // file | fluent | elk   → backends.log.provider
      "service": null         // → metadata["service"] for query_window
    }
  },

  // APPLICATION logging - Aegis's own diagnostics
  "logging": {
    "severity": "INFO",       // TRACE | DEBUG | INFO | WARNING | ERROR
    "sink": "file",           // file | elk | fluent   (elk/fluent = stubs, D3)
    "dir": "~/.local/state/aegis-swr/logs",
    "elk_url": null,          // accepted by schema; emitter not yet implemented
    "fluent_host": null,
    "fluent_port": null
  },

  // EVIDENCE logging - war-room left pane, investigation-only
  "evidence": {
    "severity": "INFO",       // INFO | TRACE
    "persist": false,         // off by default (D5); when true, write to a file
    "dir": null               // evidence log dir when persist = true
  },

  // INVESTIGATION-PROCESS logging - war-room right pane (agent reasoning)
  "process": {
    "severity": "INFO"        // INFO (headlines) | TRACE (full agent reasoning)
  }
}
```

**CLI surface.** Application: `--log-severity`, `--log-sink`, `--log-dir`. Evidence:
`--evidence-severity` *(INFO|TRACE)*, `--evidence-persist/--no-evidence-persist`.
Process: `--process-severity` *(INFO|TRACE)*. Ingestion: `--log-provider`,
`--log-service` (→ `ingest.log_source.*`).

Internally `AnalyzeConfig` keeps **flat** field names (`log_provider`, `log_service`,
`log_severity`, `log_sink`, `log_dir`, `log_elk_url`, `log_fluent_host`,
`log_fluent_port`, `evidence_severity`, `evidence_persist`, `evidence_dir`,
`process_severity`), each 1:1 with its CLI option; the nesting is purely a
JSON-layout translation at the file boundary (dotted-path flatten/nest).

## III.3 Resolved decisions

- **D1** - ingestion `provider`/`service` live under `ingest.log_source` (so `logging`
  is application diagnostics only).
- **D2** - evidence has exactly two levels; the former `DEBUG` evidence detail folds
  into `TRACE`.
- **D3** - `logging.sink = elk|fluent` is accepted by schema + CLI but the emitters
  are **stubs** (warn + fall back to file/stderr); real sinks land later.
- **D4** - evidence and investigation-process are **separate** channels; agent
  reasoning prints at `process.severity = TRACE`, toggled independently of evidence.
- **D5** - evidence persistence is **configurable, off by default**; agent dialogue
  is already persisted in the report files, so no separate process sink is added.

## III.4 Development phases

### Phase A - Internal decoupling (no behavior change) ✅
1. Thread **three** distinct levels through the call chain in place of the single
   reused `config.log_severity`: an application severity into `configure_logging`,
   and separate evidence/process levels into `stream_and_display`/`make_view`
   (temporarily sourced from one value). Files: `cli/commands.py`, `cli/_formatters.py`.

   *As built:* `commands.analyze` now derives `app_severity` / `evidence_severity` /
   `process_severity` (all from `config.log_severity` for now); `app_severity` feeds
   `configure_logging`, and `evidence_severity` + `process_severity` feed
   `stream_and_display`. `stream_and_display` takes `evidence_level` + `process_level`
   and forwards both to `make_view`; `WarRoomView` stores `_process_level` alongside
   `_level` (not yet consulted by the renderers - Phase D switches the process pane to
   it). The existing `level=` parameter on `make_view`/`WarRoomView` is retained for
   backward compatibility. No behavior change; all suites green.

### Phase B - Config schema split (`cli/_config.py`) ✅
2. Add `AnalyzeConfig` fields: `evidence_severity`, `evidence_persist`, `evidence_dir`,
   `process_severity`, `log_sink`, `log_elk_url`, `log_fluent_host`, `log_fluent_port`
   (keep `log_severity`, `log_dir`, `log_provider`, `log_service`).
3. Generalize the flatten/nest helpers to **dotted section paths** via a
   flat-field → JSON-path map (`log_provider → ingest.log_source.provider`,
   `log_severity → logging.severity`, `evidence_severity → evidence.severity`,
   `process_severity → process.severity`, …). Update `from_dict`/`merge`/`load`/`save`;
   register `ingest`/`logging`/`evidence`/`process` so they are consumed before
   unknown-key detection. *Done when* save↔load round-trips all four sections and the
   legacy-flat-key-wins rule still holds.

   *As built:* `_FIELD_TO_PATH` maps each flat field to a dotted path; generic
   `_dig`/`_bury` + `_flatten_sections`/`_nest_sections` replace the single-section
   helpers; consumed sections are derived into `_ANALYZE_SECTION_KEYS` and popped
   during flatten (so they never read as unknown keys). The strict CLI↔schema
   equality test was relaxed to *CLI ⊆ schema* with an explicit pending-flags set
   (Phase C restores equality). Config data files (`config.example.json`, user
   `config.json`) and the test fixtures moved to the four-section layout; prose docs
   (`config.md`/`cli.md`) remain for Phase H. **No runtime behavior change** (the
   three channels still derive from `log_severity`). Coverage: unit (all-section
   flatten, partial-defaults, save↔load round-trip, flat-key-wins, legacy
   provider/service-not-read), mock (`test_cli.py` config→metadata), integration
   (`test_e2e_cli.py` nested-sections flow-through + `--save-config` nesting).
   Full suite green (393 passed).

### Phase C - CLI surface (`cli/commands.py`)
4. Add `--evidence-severity`, `--evidence-persist/--no-evidence-persist`,
   `--process-severity`, `--log-sink`; keep `--log-severity`/`--log-dir`; clarify that
   `--log-provider`/`--log-service` configure `ingest.log_source`.
5. Validate ranges: evidence and process accept only `INFO|TRACE` (clear error
   otherwise); application accepts the full loguru range.

### Phase D - Evidence & process severity model (`views/rich_view.py`) ✅
6. Split `WarRoomView._level` into `_evidence_level` and `_process_level`; pass each to
   the corresponding `_StreamLog.visible(...)` call. Gate `_on_evidence` /
   `_emit_trace_evidence` on the evidence level and the agent-reasoning detail in
   `_on_agent` on the process level.
7. Collapse `EvidenceLevel` to **INFO/TRACE** (D2): update `_LEVEL_RANK`,
   `_normalize_evidence_level`, the `("DEBUG","TRACE")` branches, and
   `make_view`/`RichView` signatures. (RichView fallback maps both panes' levels.)

   *As built:* `self._level` became `self._evidence_level`; the Evidence Stream
   renderer + `_on_evidence`/`_emit_trace_evidence` read it, while
   `_render_process` + the `_on_agent` reasoning gate read `self._process_level` -
   so `--evidence-severity` and `--process-severity` now drive their panes
   independently. `EvidenceLevel` is `Literal["INFO","TRACE"]` with
   `_LEVEL_RANK={"INFO":0,"TRACE":1}`; `_normalize_evidence_level` maps `DEBUG`→`TRACE`
   (collapse, D2) and anything else unknown→`INFO`. The former `_emit_debug_evidence`
   is now `_emit_trace_evidence` (all lines tagged TRACE; the 40-line excerpt cap and
   `_DEBUG_EXCERPT_LINES` are gone - TRACE streams the full `!analyze -v`). The stale
   `--process-severity` help note was removed. Coverage: rewrote the view verbosity
   tests onto TRACE; added independence tests both ways (evidence TRACE+process INFO →
   evidence detail shown, reasoning hidden; evidence INFO+process TRACE → reasoning
   shown); 2-level rank test; `make_view` DEBUG→TRACE collapse test; removed the
   obsolete excerpt-cap test. Full suite green.

### Phase E - Application logging sinks (`cli/aegis_logging.py`) ✅
8. Refactor `configure_logging(severity, *, sink="file", dir=None, elk_url=None,
   fluent_host=None, fluent_port=None)`; `file` keeps current rotating-file behavior;
   stderr always on; `_sensitive_filter` + the noisy-logger clamp apply to every sink.
9. `sink in {elk, fluent}` → warn "not yet implemented, falling back" and keep
   stderr/file, leaving a `_register_<sink>_sink` extension seam (D3; no network code).

   *As built:* `configure_logging` is now keyword-only `sink`/`elk_url`/`fluent_host`/
   `fluent_port` (kept the existing `log_dir` name to avoid breaking callers). The
   file-sink body was extracted to `_add_file_sink` (returns False on `OSError`, with
   the never-lose-stderr guarantee). `_register_elk_sink` / `_register_fluent_sink` are
   the seams - they return `False` for now, so the caller adds the file sink as a
   fallback and emits a "not yet implemented" warning (an unknown sink warns "using the
   file sink"); the warning is logged *after* the file sink attaches so it is captured
   there too. **Phase G's `--log-sink` wiring was pulled forward**: `commands.analyze`
   now passes `sink`/`elk_url`/`fluent_host`/`fluent_port` to the re-apply
   `configure_logging`, and the Phase-C placeholder `--log-sink` warning was removed
   (configure_logging owns it). No behavior change for the default `file` sink.
   Coverage: unit (file-no-warning, elk/fluent warn+fallback parametrized, unknown-sink
   fallback, seams return False), mock (`--log-sink elk` reaches `configure_logging`
   with `sink="elk"`), integration (`--log-sink elk` completes end-to-end and the
   fallback file log captures the stub warning). Full suite green.

### Phase F - Evidence persistence (D5) ✅
10. When `evidence.persist` is true, attach a file sink for the evidence stream under
    `evidence.dir` (default off). The full investigation trail already lives in the
    report files, so process-pane persistence is **not** added.

    *As built (post-run dump, not a streaming sink):* `WarRoomView.evidence_transcript()`
    returns the plain-text Evidence Stream record (full record at the active level;
    `_plain_text` renders each Rich line via a wide no-colour capture console).
    `stream_and_display` gained `evidence_persist`/`evidence_dir` and, after the run,
    calls `_persist_evidence(view, evidence_dir, report)` which writes
    `<evidence_dir>/evidence-<incident_id>.log` (fails open with a warning on `OSError`).
    `commands.analyze` resolves `evidence_dir` to `config.evidence_dir or
    _DEFAULT_EVIDENCE_DIR` (`~/.local/state/aegis-swr/evidence`) and passes the flags
    through. **Limitations surfaced, not silent:** persistence is a WarRoomView feature
    (terminal width ≥ 80) - on the narrow-terminal RichView fallback it is skipped with
    a warning; and `--output quiet` (no rendered stream) also warns. Coverage: unit
    (`evidence_transcript` TRACE-full vs INFO-summary; `_persist_evidence` writes the
    file / no-ops without a dir), mock (`--evidence-persist` reaches `stream_and_display`
    with a resolved dir; quiet-mode warning), integration (CLI run with a wide terminal
    drives the real view via a mocked event stream and writes the transcript file).
    Full suite green.

### Phase G - Wiring (`cli/commands.py`) ✅ (absorbed into C/E/F)
11. `configure_logging(config.log_severity, sink=config.log_sink, dir=config.log_dir, …)`
    for diagnostics; `stream_and_display(evidence_level=config.evidence_severity,
    process_level=config.process_severity)` for the war room; evidence persistence per
    Phase F. Ingestion wiring (`backends.log.provider`, `metadata["service"]`) unchanged.

    *As built:* there was no separate wiring step left - evidence/process severities
    were wired in Phase C, the `--log-sink`/elk/fluent params in Phase E, and
    `evidence_persist`/`evidence_dir` in Phase F. Nothing remained for a standalone G.

### Phase H - Docs & config files ✅
12. Update `docs/configuration/config.md` (four sections: `ingest.log_source`,
    `logging`, `evidence`, `process`, and the distinction from `backends.log`),
    `docs/configuration/cli.md` (new flag rows + validation), `config.example.json`,
    and `~/.local/share/aegis-swr/config.json`.

    *As built:* `config.md` - the "Flat analyze keys" section became "Analyze keys"
    (flat table trimmed to the non-logging options) followed by a new "Log-related
    analyze sections" block documenting all four sections, each with its sub-keys, CLI
    flag (or *config-only* marker for `elk_url`/`fluent_host`/`fluent_port`/`evidence.dir`),
    defaults, and the `backends.log` disambiguation note; the intro now calls them
    "Analyze keys". `cli.md` - `--log-provider`/`--log-service` reworded as ingestion
    (`ingest.log_source`), `--log-severity` reworded as *application* only, added
    `--log-sink` / `--evidence-severity` / `--process-severity` / `--evidence-persist`
    rows, a "Logging channels" validation note, exit-code `2`, and a verbose-war-room
    example. The two JSON config files already carried the four-section layout (Phase B).
    Docs-only - no Python/tests changed; verified `config.example.json` still parses into
    the four-section schema and all doc anchors resolve.

### Phase I - Tests ✅ (delivered incrementally with B–F, not as a separate phase)
13. **Schema/IO** (`test_analyze_config.py`): dotted-path flatten/nest for all four
    sections; round-trip; legacy-flat-key-wins; defaults; legacy migration.
14. **CLI** (`test_cli.py`): evidence/process severities independent of `--log-severity`
    and of each other; both reject `DEBUG`; ingestion flags reach `backends.log`/metadata.
15. **Logging** (`test_logging.py`): file sink; `--log-sink elk|fluent` warns + falls
    back without raising; redaction/clamp across sinks.
16. **View:** evidence INFO = headlines only; evidence TRACE = former DEBUG+TRACE
    detail; process TRACE prints full agent reasoning while evidence stays INFO (and
    vice versa); two-level ranking.

    *As built:* rather than a trailing test phase, each phase shipped its own unit +
    mock + integration coverage (B: schema/IO + flatten/nest; C: validation +
    independent threading; D: pane split + collapse + independence; E: sinks; F:
    evidence transcript + persistence; J: legacy migration). Full suite green throughout.

### Phase J - Back-compat & migration ✅
17. If a legacy conflated `logging.severity` exists and `evidence`/`process` are absent,
    seed both from it (clamped to INFO/TRACE) with a one-time deprecation warning; old
    flat `log_*` keys still load via the override-wins path.

    *As built:* `_migrate_legacy(data)` (run first in `_flatten_sections`) upgrades a
    pre-split `logging` block - `logging.provider`/`service` → `ingest.log_source.*`,
    and `logging.severity` additionally seeds `evidence.severity`/`process.severity`
    via `_clamp_stream_level` (DEBUG/TRACE→TRACE, else INFO) - **only when the matching
    new keys are absent**, so current configs are untouched. One deprecation warning
    lists what migrated. `logging.severity`/`logging.dir` still map to the unchanged
    `logging` section, and top-level flat `log_*` keys still win via the override path.
    Coverage: unit (conflated section migrated; non-stream severity clamped to INFO;
    new sections suppress migration + no warning), integration (legacy config.json
    flows through the CLI and `logging.service` reaches `metadata["service"]`).

**Sequencing (as built).** The core split landed A→B→C→D, wiring folded into C/E/F
(no separate **Phase G**), and tests shipped per-phase (no separate **Phase I**).
Phase E's real elk/fluent emitters remain the only deferred item (stubs in place).
