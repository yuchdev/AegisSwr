# Aegis SWR - Implementation Plan & Backend / Data-Adapter Specification

**Package:** `aegis-swr` | **Module root:** `src/aegis_swr/`
**Total estimated timeline:** 16 weeks across 10 phases

This document is the execution brief for the 16-week build plan (Part I) and records
the completed three-channel logging redesign (Part III). The authoritative engineering
specification — schemas, backend ABCs, MAS engine, storage topology, REST API, sandbox,
CLI, and logging architecture — lives in
[`docs/specs/implementation-spec.md`](../../specs/implementation-spec.md).

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
   - `_process_screenshot(path: Path) -> UIContext | None` - OCR via pytesseract with the confidence gate.
   - `_scrub_pii(text: str) -> tuple[str, dict]` - Presidio scrubbing; returns scrubbed text and substitution map.
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

**Goal:** Implement two production-quality LLM provider backends with structured output, prompt caching, streaming, and retry logic. (Interface and as-built behavior in [Part II §C.1](#c1-aiapibackend).)

### Deliverables

1. **`backends/ai/anthropic_provider.py`** - `AnthropicBackend(AIAPIBackend)`:
   - `generate()`: Uses `client.messages.create()` with `cache_control: {"type": "ephemeral"}` on the system block. If `output_schema` provided, uses a tool use pattern with a single tool whose `input_schema` is the Pydantic model's JSON schema. Validates response with Pydantic; on `ValidationError` raises `AIOutputValidationError` and retries once with a correction prompt.
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
   - `_parse(raw_json, source) -> DebugExtractionResult` - parses DDM JSON fields (see [Part II payload mapping](#c2-debugbackend)). Faulting-thread frames become `stack_frames`; all-thread's summary becomes `raw_text_excerpt`.
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

**Goal:** Implement the complete LangGraph state graph with four agents, weighted consensus, and HITL trigger. (Full MAS spec: `docs/specs/implementation-spec.md` §7.)

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

**Goal:** Implement the optional `CodeBackend` family (Data Adapter Stage 8). Three adapters behind one interface; PDB gives highest-fidelity attribution on Windows. (Interface and adapters in [Part II §C.5](#c5-codebackend).)

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
- `PdbCodeAdapter.get_commits_before()` parses a fixture SrcSrv stream into one `CommitRecord`; constructor raises exception on non-Windows; returns `[]` when `pdbstr.exe` exits non-zero.
- `create_code_backend()` returns `None` when disabled.
- `pytest tests/unit/test_code_backends.py` passes with zero external calls.

---

## Phase 6.2: Log Backend

**Goal:** Implement the optional `LogBackend` family queried in Data Adapter Stage 4 - a real local-file adapter plus a Fluent stub; ELK deferred. (Interface and adapters in [Part II §C.4](#c4-logbackend).)

### Deliverables

1. **`backends/log/file_adapter.py`** - `FileLogAdapter(LogBackend)`: `query_window` resolves `{file_root}/{service}*.{log,txt}`, reads via `asyncio.to_thread`, filters by timestamp window and severity; returns `[]` when `file_root` unset; traversal guard.
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
3. **`cli/aegis_logging.py`** - `configure_logging()` (loguru sink level and sensitive-data redaction filter; clamps noisy third-party loggers to WARNING).
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

**Goal:** Implement the FastAPI application with all endpoints, SSE streaming, auth middleware, and background task management. (Full API spec: `docs/specs/implementation-spec.md` §9.)

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

**Goal:** Implement the Docker-based sandbox executor that compiles and validates AI-generated patches. (Full sandbox spec: `docs/specs/implementation-spec.md` §10.)

### Deliverables

1. **`sandbox/executor.py`** - `SandboxExecutor.validate(patch, language) -> ValidationResult` via `asyncio.create_subprocess_exec` with timeout; `passed=None` + warning when Docker is unavailable (sandbox is optional).
2. **`sandbox/validators.py`** - language detection (extension and MIME) → Docker image tag.
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
4. **Security-hardening checklist** - `SensitiveFilter` on all loggers; list-form `subprocess` everywhere; path-traversal validation; bcrypt-hashed API keys; Presidio before any external LLM call; sandbox `--network=none --cap-drop ALL --read-only`.
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

> The specifications previously inlined here have been consolidated into
> [`docs/specs/implementation-spec.md`](../../specs/implementation-spec.md),
> which is now the single authoritative source. Quick-reference index:

| Topic | Spec section |
|---|---|
| Shared data types (`IncidentSource`, `FaultClass`, `DebugExtractionResult`, Code Backend record types) | §4 |
| Data Adapter pipeline (9 stages) | §5 |
| `AIAPIBackend` ABC + provider notes + as-built (Phase 3) | §6.1 |
| `DebugBackend` ABC + WinDbg JS backend + as-built (Phase 4) | §6.2 |
| `StorageBackend` ABCs (`RelationalStore`, `ObjectStore`, `VectorStore`) | §6.3 |
| `LogBackend` (`FileLogAdapter`, `FluentAdapter`) + factory | §6.4 |
| `CodeBackend` (`GitCodeAdapter`, `FilesystemCodeAdapter`, `PdbCodeAdapter`) | §6.5 |
| Three-channel logging architecture | §15 |

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

> `<config-dir>` = `~/.aegis-swr/`

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
    "dir": "<config-dir>/logs",
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
    _DEFAULT_EVIDENCE_DIR` (`<config-dir>/evidence`) and passes the flags
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
    and `<config-dir>/config.json`.

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
    mock + integration coverage (B: schema/IO + flatten/nest; C: validation and
    independent threading; D: pane split + collapse + independence; E: sinks; F:
    evidence transcript + persistence; J: legacy migration). Full suite green throughout.

### Phase J - Backward-compatibility & migration ✅

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
    new sections suppress migration and no warning), integration (legacy config.json
    flows through the CLI and `logging.service` reaches `metadata["service"]`).

**Sequencing (as built).** The core split landed A→B→C→D, wiring folded into C/E/F
(no separate **Phase G**), and tests shipped per-phase (no separate **Phase I**).
Phase E's real elk/fluent emitters remain the only deferred item (stubs in place).
