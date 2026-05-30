# Aegis SWR — Multi-Step Implementation Plan

**Package:** `aegis-swr` | **Module root:** `src/aegis_swr/`  
**Total estimated timeline:** 16 weeks across 10 phases  
**Reference:** See `PRODUCTION_DESIGN_SPEC.md` for all schema, interface, and algorithm definitions.

---

## Phase Overview

| Phase | Name | Duration | Output |
|---|---|---|---|
| 1 | Foundation & Package Setup | Week 1–2 | Repo skeleton, schemas, ABCs, config, CI |
| 2 | Data Adapter Layer | Week 3–4 | Preprocessing pipeline; token-dense incident brief |
| 3 | AI Backends | Week 5 | Anthropic + OpenAI providers; streaming; structured output |
| 4 | Debug Backends | Week 6 | CDB (Windows), GDB (Linux), LLDB (macOS); FaultClass mapping |
| 5 | Multi-Agent System | Week 7–9 | LangGraph state graph; 4 agents; consensus; HITL trigger |
| 6 | Storage Backends | Week 10 | PostgreSQL, S3/MinIO, Qdrant; dedup by content hash |
| 6.1 | Code Backend | Week 10 | Git + filesystem code adapters; Stage 8 code-history attribution |
| 6.2 | Log Backend | Week 10 | File log adapter + Fluent stub; Stage 4 windowed log queries |
| 7 | CLI & Local Mode | Week 11 | Typer CLI; in-process pipeline without API server |
| 8 | REST API Layer | Week 12–13 | FastAPI app; SSE streaming; auth; rate limiting |
| 9 | Secure Code Sandbox | Week 14 | Docker/gVisor executor; compile + AST validation |
| 10 | Testing & Hardening | Week 15–16 | Ground truth suite; benchmark; security audit; CI gates |

---

## Phase 1: Foundation & Package Setup

**Goal:** Establish a compilable, importable, fully typed Python package. No business logic yet — only structure, contracts, and tooling.

### Deliverables

1. **`pyproject.toml`** — Poetry project configured with all dependencies, `aegis-swr` name, `src/aegis_swr/` package root, and `aegis` CLI entry point.
2. **Directory skeleton** — all `__init__.py` files for `core/`, `agents/`, `backends/` (and subdirs), `sandbox/`, `api/`, `cli/`, `config/`.
3. **`core/schemas.py`** — All Pydantic v2 models: `IncidentSource`, `IncidentBrief`, `DebugExtractionResult`, `StackFrame`, `Hypothesis`, `AgentTurn`, `SkepticVerdict`, `RCAReport`, `HITLRequest`, `InvestigationState` (TypedDict), `RCAHypothesis`.
4. **`core/fault_codes.py`** — `FaultClass` enum and complete platform-to-FaultClass mapping tables for Windows NTSTATUS, Linux signals, macOS exception types.
5. **`backends/base.py`** — All five abstract base classes: `AIAPIBackend`, `DebugBackend`, `RelationalStore`, `ObjectStore`, `VectorStore`, `LogBackend`, `CodeBackend`. Full type hints, docstrings on each abstract method.
6. **`agents/base.py`** — Abstract `BaseAgent` with `system_prompt: str`, `run(state: InvestigationState, ai_backend: AIAPIBackend) -> AgentTurn` abstract method.
7. **`config/settings.py`** — Pydantic Settings v2 class that reads `config.yaml` and `AEGIS__*` environment variables. Includes `CoreSettings`, `AISettings`, `DebugSettings`, `StorageSettings`, `APISettings`, `SandboxSettings`, `AgentWeightsSettings`.
8. **`config.yaml`** — Default configuration with all values from the design spec.
9. **`.env.example`** — Documents `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AEGIS__BACKENDS__STORAGE__DATABASE_URL`, etc.
10. **`tests/` skeleton** — `conftest.py` with pytest fixtures for a default `Settings` object and a mock `IncidentSource`.
11. **CI configuration** — `.github/workflows/ci.yml` (or equivalent): ruff lint, mypy type-check, pytest unit tests on each push.

### Success Criteria

- `poetry install` completes with no errors.
- `python -c "from aegis_swr.core.schemas import RCAReport; print('ok')"` succeeds.
- `mypy src/` passes with zero errors.
- `pytest tests/unit/test_schemas.py` passes (basic Pydantic model creation and serialization tests).

---

## Phase 2: Data Adapter Layer

**Goal:** Implement the full nine-stage preprocessing pipeline that converts raw `IncidentSource` into a structured `IncidentBrief`.

### Deliverables

1. **`core/data_adapter.py`** — `DataAdapter` class with `async def process(source: IncidentSource) -> IncidentBrief` method. Each stage is a private method:
   - `_compute_hash(path: Path) -> str` — SHA-256 in chunks.
   - `_detect_format(path: Path) -> DumpFormat` — magic-byte detection (not extension).
   - `_apply_noise_filter(text: str) -> str` — DBGHELP strip, fill pattern replace, DLL list drop, 8k truncation.
   - `_process_logs(paths: list[Path], timestamp: datetime | None) -> str` — Drain3 clustering, temporal window, severity filter, 2k token budget.
   - `_process_screenshot(path: Path) -> UIContext | None` — OCR via pytesseract with confidence gate.
   - `_scrub_pii(text: str) -> tuple[str, dict]` — Presidio scrubbing; returns scrubbed text + substitution map.
   - `_enforce_assumption_limit(text: str) -> str` — Token count; truncate to 500 with log warning.
   - `_query_code_history(source: IncidentSource) -> list[CommitRecord]` — Optional; only if `CodeBackend` configured.
   - `_assemble_brief(...) -> IncidentBrief` — Final assembly.

2. **Drain3 integration** — Configure `DrainConfig` with appropriate patterns for common log formats (syslog, JSON, Python logging, Windows Event Log).

3. **`tests/unit/test_data_adapter.py`** — Per-stage unit tests:
   - Hash computation consistency.
   - Noise filter removes DBGHELP lines and fill patterns.
   - Temporal windowing slices correctly.
   - Drain3 deduplication reduces repeated lines.
   - Presidio scrubs emails, IP addresses, AWS keys.
   - Assumption token cap triggers at 500.

4. **`tests/unit/fixtures/`** — Sample raw CDB output, sample log files with known PII, sample screenshot.

### Success Criteria

- `DataAdapter.process()` completes on a sample Windows `.dmp` + log file in under 5 seconds (no LLM call).
- All noise filter rules reduce the token count of the canonical test CDB output by ≥60% vs. the raw input.
- Presidio correctly scrubs all entities in `tests/unit/fixtures/sample_logs_with_pii.txt`.
- `pytest tests/unit/test_data_adapter.py` passes.

---

## Phase 3: AI Backends

**Goal:** Implement two production-quality LLM provider backends with structured output, prompt caching, streaming, and retry logic.

### Deliverables

1. **`backends/ai/anthropic_provider.py`** — `AnthropicBackend(AIAPIBackend)`:
   - `generate()`: Uses `client.messages.create()` with `cache_control: {"type": "ephemeral"}` on the system block. If `output_schema` provided, uses tool use pattern with a single tool whose `input_schema` is the Pydantic model's JSON schema. Validates response with Pydantic; on `ValidationError` raises `AIOutputValidationError` and retries once with a correction prompt.
   - `stream()`: Uses `client.messages.stream()` async context manager; yields text deltas.
   - Token tracking: reads `usage` from response and appends to `InvestigationState.token_tracker`.

2. **`backends/ai/openai_provider.py`** — `OpenAIBackend(AIAPIBackend)`:
   - `generate()`: Uses `response_format={"type": "json_schema", "json_schema": {schema dict}}` for structured output. Retry logic same as Anthropic.
   - `stream()`: Uses `stream=True` with `stream_options={"include_usage": True}`.

3. **`backends/ai/__init__.py`** — `create_ai_backend(config: AISettings) -> AIAPIBackend` factory.

4. **Custom exceptions** in `core/exceptions.py`:
   - `AIOutputValidationError(Exception)` — raised when LLM response fails schema validation after one retry.
   - `PlatformNotSupportedError(Exception)`.
   - `SandboxExecutionError(Exception)`.
   - `IncidentNotFoundError(Exception)`.

5. **`tests/unit/test_ai_backends.py`** — Uses `unittest.mock` to patch `anthropic.AsyncAnthropic` and `openai.AsyncOpenAI`. Tests structured output parsing, schema validation retry, stream iteration.

### Success Criteria

- `AnthropicBackend.generate()` with a `Hypothesis` output schema returns a validated `Hypothesis` instance.
- Stream yields at least one non-empty string token before raising `StopAsyncIteration`.
- `AIOutputValidationError` is raised (not silently ignored) when mock LLM returns malformed JSON.
- `pytest tests/unit/test_ai_backends.py` passes with no network calls.

---

## Phase 4: Debug Backends

**Goal:** Implement all three platform debug workers and the platform-adaptive FaultClass mapping.

### Deliverables

1. **`backends/debug/cdb_worker.py`** — `CdbBackend(DebugBackend)`:
   - `SUPPORTED_FORMATS = [DumpFormat.WINDOWS_MINIDUMP]`
   - `SUPPORTED_PLATFORMS = ["Windows"]`
   - Builds command: `["cdb.exe", "-z", str(dump_path), "-y", symbol_path_str, "-c", ".reload /f /i; !analyze -v; q"]`
   - Parses output via regex (ported from prototype's `cdb.py`): extracts `exception_code_raw`, `exception_address`, `faulting_module`, `faulting_function`, stack frames.
   - Maps NTSTATUS codes to `FaultClass` using `fault_codes.py` mapping table.
   - Computes `symbol_resolution_score` by counting frames with non-None `function`.
   - Applies noise filter to `raw_text_excerpt`.

2. **`backends/debug/gdb_worker.py`** — `GdbBackend(DebugBackend)` (Linux):
   - `SUPPORTED_FORMATS = [DumpFormat.LINUX_CORE, DumpFormat.WINDOWS_MINIDUMP]`
   - Command: `["gdb", "--batch", "--quiet", "-ex", "core-file {dump}", "-ex", "bt 20", "-ex", "info registers", "-ex", "quit"]`
   - Parses `bt` output into `StackFrame` list.
   - Maps POSIX signals to `FaultClass`.

3. **`backends/debug/lldb_worker.py`** — `LldbBackend(DebugBackend)` (macOS):
   - Command: `["lldb", "--batch", "-c", str(dump_path), "-o", "bt all", "-o", "register read", "-o", "quit"]`
   - Maps macOS exception types to `FaultClass`.

4. **`backends/debug/__init__.py`** — `create_debug_backend()` factory with engine selection: `auto` tries `WinDbgJSBackend` first on Windows via `_windbg_js_available()` probe, falls back to `CdbBackend`; `cdb` / `windbg_js` force a specific engine. `GdbBackend` / `LldbBackend` are selected on Linux / Darwin as before.

5. **Symbol path resolution** in `backends/debug/_symbol_path.py` — `resolve_symbol_path(config_value: str | None) -> Path` using `pathlib` and the cross-platform defaults from the design spec.

6. **`backends/debug/windbg_js_worker.py`** — `WinDbgJSBackend(DebugBackend)` (Windows only):
   - `SUPPORTED_FORMATS = [DumpFormat.WINDOWS_MINIDUMP]`
   - `SUPPORTED_PLATFORMS = ["Windows"]`
   - `_CallbackBridge` RAII context manager: binds `HTTPServer` to `("127.0.0.1", 0)` (OS-assigned ephemeral port), daemon thread, instance-level `queue.Queue[str]`. **No shared module-level state.**
   - `_make_handler(queue)` closure — returns a `BaseHTTPRequestHandler` subclass that enqueues the raw POST body.
   - `_prepare_js(port, settings) -> str` — reads `backends/debug/assets/windbg_diagnostic.js`, substitutes `__CALLBACK_URL__`, `__MAX_FAULTING_FRAMES__`, `__MAX_OTHER_FRAMES__`.
   - `_build_command_sequence()` — `["cdb.exe", "-z", dump, "-y", sym_chain, "-c", ".scriptload \"{tmp_js}\"; g; q"]`.
   - `_parse(raw_json, source) -> DebugExtractionResult` — parses DDM JSON fields (see spec §6.2.2 mapping table). Faulting-thread frames become `stack_frames`; all-threads summary becomes `raw_text_excerpt`.
   - Raises `DebugExtractionError` when `"JsProvider.dll"` string absent from subprocess output, or callback timeout expires.

7. **`backends/debug/assets/windbg_diagnostic.js`** — Production JS script (see spec §6.2.2). Queries DDM for `ExceptionCode`, `ExceptionAddress`, faulting thread full frames (`maxFaultingFrames`), all other threads summarized (`maxOtherFrames`), module names and base addresses. Calls back via `ActiveXObject("MSXML2.XMLHTTP")` POST.

8. **`config.yaml`** additions to `backends.debug`:
   ```yaml
   engine: "auto"               # auto | cdb | windbg_js
   callback_timeout_seconds: 60
   max_faulting_frames: 20
   max_other_thread_frames: 3
   ```
   `DebugSettings` extended to include these fields.

9. **`tests/unit/test_debug_backends.py`** — existing tests for CDB/GDB/LLDB/factory/symbol-path (already implemented). **New tests for `WinDbgJSBackend`:**
   - `test_windbg_js_parses_ddm_json`: fixture DDM JSON payload → correct `DebugExtractionResult` (NTSTATUS, address, faulting module, frames, score).
   - `test_windbg_js_command_uses_scriptload`: command sequence contains `.scriptload`.
   - `test_windbg_js_callback_bridge_assigns_ephemeral_port`: `_CallbackBridge.__enter__` binds port 0, `bridge.port` is a non-zero integer.
   - `test_windbg_js_per_instance_queue_isolation`: two concurrent `_CallbackBridge` instances have independent queues.
   - `test_windbg_js_raises_on_missing_jsprovider`: stdout without `JsProvider.dll` → `DebugExtractionError`.
   - `test_windbg_js_raises_on_callback_timeout`: bridge `wait_for_payload` with empty queue → `DebugExtractionError`.
   - `test_factory_returns_windbg_js_when_forced`: `engine="windbg_js"` on `win32` → `WinDbgJSBackend`.
   - `test_factory_falls_back_to_cdb_when_js_unavailable`: `engine="auto"`, `_windbg_js_available()` returns False → `CdbBackend`.

10. **`tests/unit/fixtures/sample_windbg_js_payload.json`** — realistic DDM JSON payload with 5 faulting frames (4 resolved), 2 other threads, NTSTATUS `0xC0000005`, ExceptionAddress, FaultingModule.

### Success Criteria

- `CdbBackend.extract()` on the CDB fixture returns a valid `DebugExtractionResult` (already passing).
- `WinDbgJSBackend.extract()` on the DDM JSON fixture returns a valid `DebugExtractionResult` with correct fault class, address, and frames.
- `_CallbackBridge` uses a fresh per-instance queue — two simultaneous instances cannot receive each other's payloads.
- Factory `engine="auto"` selects `WinDbgJSBackend` when available, `CdbBackend` otherwise — without raising.
- Factory raises `PlatformNotSupportedError` on an unsupported platform string.
- `pytest tests/unit/test_debug_backends.py` passes.

---

## Phase 5: Multi-Agent System Engine

**Goal:** Implement the complete LangGraph state graph with four agents, weighted consensus, and HITL trigger.

### Deliverables

1. **`core/consensus.py`** — `ConsensusEvaluator`:
   - `calculate(state: InvestigationState, weights: AgentWeightsSettings) -> float` — implements the weighted CS formula.
   - `is_converged(score: float, threshold: float, previous_score: float | None) -> bool` — True if `score >= threshold` for the same primary hypothesis in the last two consecutive calls.
   - `is_deadlocked(score: float, round: int, max_rounds: int, hitl_threshold: float) -> bool`.

2. **`agents/os_kernel.py`** — `OSKernelAgent(BaseAgent)`:
   - `system_prompt`: verbatim from design spec (kernel debugger persona).
   - `run()`: constructs message context from `incident_brief`; calls `ai_backend.generate()` with `OSKernelOutput` schema; appends resulting `AgentTurn` to `state["discussion_history"]`; updates `state["consensus_score"]`.

3. **`agents/code_analyst.py`** — `CodeAnalystAgent(BaseAgent)`:
   - `run()`: includes `OSKernelOutput` from previous turn in context; injects `user_assumption` if present; generates `CodeAnalystOutput`.

4. **`agents/log_historian.py`** — `LogHistorianAgent(BaseAgent)`:
   - `run()`: queries `VectorStore.search_similar()` with conditional injection rule; builds `LogHistorianOutput`; adjusts confidence.

5. **`agents/skeptic.py`** — `SkepticAgent(BaseAgent)`:
   - `run()`: runs three assertion checks before calling the LLM; if all pass, calls LLM for full `SkepticVerdict`; if any assertion fails programmatically (module not in frames), sets `confirmed=False` immediately without an LLM call (saves tokens on obvious failures).

6. **`core/orchestrator.py`** — `Orchestrator`:
   - Builds LangGraph `StateGraph` with all five nodes (data_adapter, os_kernel, code_analyst, log_historian, skeptic) plus `output_synthesizer` and `hitl_handler`.
   - Conditional edges from `skeptic_node` using `ConsensusEvaluator` results.
   - `async def run(source: IncidentSource) -> RCAReport` — full pipeline entry point.
   - `async def run_streaming(source: IncidentSource) -> AsyncGenerator[dict, None]` — yields SSE-compatible event dicts as each node completes.
   - `async def continue_investigation(state: InvestigationState, user_data: dict) -> RCAReport` — HITL continuation.

7. **`tests/unit/test_orchestrator.py`** — Uses a `MockAIBackend` that returns deterministic pre-scripted agent turns. Tests:
   - Full pipeline converges in ≤4 rounds on a well-structured mock incident.
   - Skeptic `confirmed=False` triggers a second round.
   - Deadlock scenario (4 rounds, CS < 0.50) produces `HITLRequest` not `RCAReport`.
   - Token tracker accumulates correctly across rounds.

8. **`tests/unit/test_consensus.py`** — Tests the CS formula at boundary values (0.00, 0.50, 0.85, 1.00). Tests convergence detection with and without threshold crossing. Tests weight matrix selection by FaultClass.

### Success Criteria

- Full pipeline test (Mock AI + real Data Adapter stub) completes without exception.
- Convergence in 2 rounds when all mock agents return `confidence=0.90`.
- HITL triggered correctly when mock agents return `confidence=0.40` for 4 rounds.
- `pytest tests/unit/test_orchestrator.py tests/unit/test_consensus.py` passes.

---

## Phase 6: Storage Backends

**Goal:** Implement filesystem, SQLite, and S3 storage backends plus a PostgreSQL stub. All four expose the same `RelationalStore`/`ObjectStore` interface so the Orchestrator does not need backend-specific code.

### Deliverables

1. **`backends/storage/filesystem_store.py`** — `FilesystemStore(RelationalStore, ObjectStore)`:
   - Reports stored as `{reports_dir}/{incident_id}.json` using `pathlib.Path`.
   - Hash index at `{reports_dir}/_hash_index/{dump_hash}` for O(1) `find_by_hash`.
   - Raw artifacts stored at `{objects_dir}/{incident_id}/{filename}`; object key = `{incident_id}/{filename}`.
   - All file I/O wrapped in `asyncio.to_thread`; path-traversal guard on every resolved path.
   - `update_hitl_response`: read JSON → update → write back.

2. **`backends/storage/sqlite_store.py`** — `SQLiteStore(RelationalStore)`:
   - Schema: single `reports` table with `(incident_id TEXT PK, dump_hash TEXT, created_at TEXT, mode TEXT, report_json TEXT)` and a unique index on `dump_hash`.
   - All SQLite calls wrapped in `asyncio.to_thread`; new `sqlite3.connect()` per call (thread-safe, no shared connection).
   - `find_by_hash` uses the indexed `WHERE dump_hash = ?` — no full-table scan.
   - `update_hitl_response`: parse JSON → mutate → `UPDATE reports SET report_json = ?`.

3. **`backends/storage/s3_store.py`** — `S3Store(RelationalStore, ObjectStore)`:
   - Sync `boto3` client wrapped in `asyncio.to_thread`.
   - Reports at `reports/{incident_id}.json`; hash index at `hash-index/{dump_hash}`.
   - Raw artifacts at `objects/{incident_id}/{filename}`.
   - `find_by_hash`: GetObject on `hash-index/{dump_hash}` → read incident_id → GetObject on `reports/{incident_id}.json`; `NoSuchKey` → return None.
   - Bucket parsed from `object_store_url`; MinIO endpoint support via `s3_endpoint_url`.

4. **`backends/storage/postgres_store.py`** — `PostgresStore(RelationalStore)` stub:
   - All four `RelationalStore` methods raise `NotImplementedError("PostgresStore is a stub — implement with SQLAlchemy async in a future phase.")`.
   - Class exists so the factory can return it and `config.yaml` can declare `provider: postgres`.

5. **`backends/storage/__init__.py`** — `create_storage_backends(settings: StorageSettings) -> tuple[RelationalStore | None, ObjectStore | None]` factory per spec §8.6.

6. **`StorageSettings` additions** in `config/settings.py`: `provider`, `reports_dir`, `objects_dir`, `db_path`, `s3_endpoint_url` fields; validator for `provider`.

7. **`config.yaml`** — add `provider`, `reports_dir`, `objects_dir`, `db_path`, `s3_endpoint_url` keys under `backends.storage`.

8. **`tests/unit/test_storage_backends.py`** — All backends tested without external services:
   - Filesystem: full round-trip (`save_report → get_report`, `find_by_hash`, `find_by_hash` unknown, `update_hitl_response`, `upload_raw → get_raw`) in `tmp_path`.
   - SQLite: same operations using an in-memory `:memory:` database.
   - S3: same operations with a patched `boto3.client`.
   - PostgresStore stub: all methods raise `NotImplementedError`.
   - Factory: returns correct types for all four providers.

### Success Criteria

- `find_by_hash()` returns an existing `RCAReport` on second call with the same hash for all three implementations (filesystem, sqlite, s3).
- `find_by_hash()` returns `None` for an unknown hash.
- `upload_raw()` then `get_raw()` round-trips the exact bytes.
- `PostgresStore` raises `NotImplementedError` on all methods.
- `pytest tests/unit/test_storage_backends.py` passes with zero external service calls.

---

## Phase 6.1: Code Backend

**Goal:** Implement the optional `CodeBackend` family that attributes a crash to recent source changes (Data Adapter Stage 8). Three adapters expose the same `CodeBackend` interface so the Data Adapter never branches on provider. The PDB adapter provides the highest-fidelity attribution on Windows by reading the exact build revision from the PDB Source Server stream rather than using a time-window approximation.

### Deliverables

1. **`backends/code/git_adapter.py`** — `GitCodeAdapter(CodeBackend)`:
   - `get_commits_before` via `git log --since/--until --max-count --name-only --date=iso-strict` with a `\x1f`/`\x1e`-delimited pretty format → `list[CommitRecord]`.
   - `get_file_diff` via `git show {sha} -- {path}`; `blame` via `git blame -L --line-porcelain`.
   - All Git access through `subprocess.run` list-form argv with `cwd=repo_path` and `git_timeout_seconds`. Missing `.git` or missing `git` binary → `CodeBackendError`. Path-traversal guard on `file_path`.

2. **`backends/code/filesystem_adapter.py`** — `FilesystemCodeAdapter(CodeBackend)` (no VCS):
   - `get_commits_before`: directory walk; synthesize one `CommitRecord` per file modified within the window (`sha="fs:…"`, `author="unknown"`, `authored_at=mtime`).
   - `get_file_diff`: returns current file contents with a `--- (no VCS history)` header.
   - `blame`: one `BlameRecord` per line with `sha="fs:…"`, `authored_at=None`.

3. **`backends/code/pdb_adapter.py`** — `PdbCodeAdapter(CodeBackend)` (Windows-only):
   - Uses `pdbstr.exe -r -p:{pdb_path} -s:srcsrv` (Debugging Tools for Windows, same install as `cdb.exe`) to extract the Source Server stream.
   - Parses the INI-like SrcSrv block: `VERCTRL`, `GITREPO`/repo URL, per-file revision SHAs.
   - `get_commits_before`: ignores `window_hours` — the SrcSrv SHA *is* the build revision. Returns one `CommitRecord` per unique SHA with `author="PdbSourceServer"`.
   - `get_file_diff` / `blame`: delegates to `git show` / `git blame` with the exact SHA from SrcSrv when `VERCTRL=git`; other VCS types return empty (fail open).
   - Constructor raises `CodeBackendError` immediately on non-Windows (`sys.platform != "win32"`).
   - All subprocess calls use list-form argv; `pdbstr_timeout_seconds` config.
   - `pdb_path` resolved from settings or auto-derived from dump path + symbol cache.

4. **`backends/code/_paths.py`** — shared path-traversal guard (`safe_repo_path`), reused by all three adapters.

5. **`backends/code/__init__.py`** — `create_code_backend(settings: CodeBackendSettings) -> CodeBackend | None` (returns `None` when `enabled=false`; routes `git` / `filesystem` / `pdb`).

6. **`CodeBackendSettings`** in `config/settings.py`: `enabled`, `provider` (`git|filesystem|pdb`), `repo_path`, `pdb_path`, `window_hours`, `commit_limit`, `git_timeout_seconds`, `pdbstr_timeout_seconds` + `config.yaml` `backends.code` block. **`CodeBackendError`** added to `core/exceptions.py`.

7. **Stage 8 fail-open** — Data Adapter catches `CodeBackendError`, logs a warning, continues with empty `code_history`.

8. **`tests/unit/test_code_backends.py`** — Git (mocked subprocess: commit/blame parse, missing-repo/binary raises, traversal); Filesystem (`tmp_path`: window selection, diff, blame, traversal); PDB (mocked `pdbstr.exe`: SrcSrv parse, empty-stream graceful, non-Windows raises, missing-binary raises, git diff/blame delegation); factory (disabled → None, git, filesystem, pdb, unknown → ValueError).

9. **`tests/unit/fixtures/sample_srcsrv_stream.txt`** — realistic SrcSrv INI fixture.

### Success Criteria

- `GitCodeAdapter.get_commits_before()` parses a fixture `git log` payload into correct `CommitRecord`s (newest first).
- `FilesystemCodeAdapter` returns only in-window files, capped to `limit`, with no `git` dependency.
- `PdbCodeAdapter.get_commits_before()` parses a fixture SrcSrv stream into one `CommitRecord` with `author="PdbSourceServer"` and all files listed; ignores `window_hours`.
- `PdbCodeAdapter` constructor raises `CodeBackendError` on non-Windows.
- `PdbCodeAdapter` returns `[]` gracefully when `pdbstr.exe` exits non-zero (no SrcSrv stream present).
- `create_code_backend()` returns `None` when `enabled=false`.
- `pytest tests/unit/test_code_backends.py` passes with zero external calls.

---

## Phase 6.2: Log Backend

**Goal:** Implement the optional `LogBackend` family queried in Data Adapter Stage 4. A real local-file adapter plus a Fluent plugin stub; ELK deferred.

### Deliverables

1. **`backends/log/file_adapter.py`** — `FileLogAdapter(LogBackend)`:
   - `async query_window(service, start, end, severity_levels)` resolves `{file_root}/{service}*.{log,txt}`, reads via `asyncio.to_thread`, filters by parsed timestamp window and severity. Returns `[]` when `file_root` is unset (file-path source still applies). Path-traversal guard within `file_root`.

2. **`backends/log/fluent_adapter.py`** — `FluentAdapter(LogBackend)` stub: constructor warns; `query_window` raises `NotImplementedError`. Module docstring documents the intended Fluent forward/HTTP design.

3. **`backends/log/__init__.py`** — `create_log_backend(settings: LogSettings) -> LogBackend | None` (`file`/`fluent`; `elk` → `NotImplementedError`; unknown → `ValueError`).

4. **`LogSettings`** in `config/settings.py` (`provider`, `file_root`, `default_severity_levels`, `fluent_host`, `fluent_port`, `fluent_tag_prefix`) + `config.yaml` `backends.log` block.

5. **Stage 4 wiring** — `DataAdapter.process` gains `log_backend: LogBackend | None = None`. When a `LogBackend`, a `service` (from `IncidentSource.metadata["service"]`), and `incident_timestamp` are all present, `query_window` lines are merged with file lines before Drain3 clustering. The call is wrapped in try/except — a stub `NotImplementedError` or query error degrades to file-only (fail open).

6. **`tests/unit/test_log_backends.py`** — File adapter (time window, severity filter, no-file_root → empty, traversal, missing file skipped); Fluent stub raises; factory mapping. Plus `test_data_adapter_merges_log_backend_lines` in `test_data_adapter.py`.

### Success Criteria

- `FileLogAdapter.query_window()` returns only lines inside the window and matching severity.
- `FluentAdapter.query_window()` raises `NotImplementedError`; the Data Adapter degrades to file-only without failing.
- `create_log_backend()` returns the correct adapter per provider.
- `pytest tests/unit/test_log_backends.py` passes with zero external calls.

---

## Phase 7: CLI & Local Mode

**Goal:** Implement the Typer CLI supporting local (in-process) analysis. Options can come from explicit CLI flags OR a JSON config file with the same key names. Prototype patterns (engine, ai, store, assumption, `--config` / `--save-config`) are carried forward.

### Deliverables

1. **`cli/_config.py`** — JSON config file support:
   - `DEFAULT_CONFIG_PATH: Path = Path("~/.aegis-swr/analyze.json").expanduser()`
   - `load_analyze_config(path: Path | None) -> dict[str, Any]` — reads JSON file; silently returns `{}` if absent.
   - `save_analyze_config(opts: dict[str, Any], path: Path | None = None) -> None` — serialises options to JSON.
   - `merge_options(config: dict, ctx: typer.Context, **cli_values) -> dict` — CLI flag overrides config value; config value overrides hardcoded default.

2. **`cli/_formatters.py`** — output formatters:
   - `json_formatter(report: RCAReport) -> str` — `report.model_dump_json(indent=2)`.
   - `rich_formatter(report: RCAReport) -> None` — rich panel summary: root cause, confidence, agent dialogue timeline (agent name + turn + message + confidence), mitigation instructions, optional code diff.

3. **`cli/_logging.py`** — log level configuration:
   - `configure_logging(severity: str) -> None` — sets loguru sink level.
   - `add_sensitive_filter()` — redacts `sk-ant-*`, `sk-*`, API key patterns from all log output (ported from prototype's `SensitiveFilter`).

4. **`cli/commands.py`** — Typer app with all subcommands per spec §12:

   **`aegis analyze`** — full flag set:
   - `--dump PATH`, `--log PATH` (multiple), `--shot PATH` (multiple), `--sym PATH`, `--assume TEXT`
   - `--engine ENGINE` (auto|cdb|windbg_js), `--ai PROVIDER` (anthropic|openai)
   - `--store TYPE` (filesystem|sqlite|s3|postgres), `--store-config VALUE`
   - `--code-provider TYPE` (none|git|filesystem), `--repo PATH` (sets code backend on + `repo_path`)
   - `--log-provider TYPE` (file|fluent), `--log-service NAME` (service for `LogBackend.query_window`)
   - `--output FORMAT` (rich|json|quiet), `--severity LEVEL` (DEBUG|INFO|WARNING|ERROR)
   - `--config PATH` — load JSON config file; defaults to `DEFAULT_CONFIG_PATH` if it exists
   - `--save-config` — write effective options to JSON file and exit
   - Merge order: CLI flag > JSON config > hardcoded default.
   - Build `IncidentSource` (stash `--log-service` in `metadata["service"]`); create backends via `create_storage_backends`, `create_code_backend`, `create_log_backend`; instantiate `Orchestrator(..., code_backend=..., log_backend=...)`; call `Orchestrator.run()`.
   - Display with `rich_formatter` (spinner during analysis), `json_formatter`, or silent exit.
   - Exit code 1 on `HITLRequest` (prints the structured clarification request to stderr).

   **`aegis export`** — migrate records between stores:
   - `--store TYPE`, `--store-config VALUE` (source)
   - `--to-store TYPE`, `--to-config VALUE` (destination)
   - Loads all reports from source via `load_recent(limit=0)` (unlimited), saves to destination.
   - Requires `load_recent(limit: int = 100) -> list[RCAReport]` on `RelationalStore`.

   **`aegis server`** — stub that prints `"API server not yet implemented — available in Phase 8."` Accepts `--host` and `--port` but ignores them for now.

   **`aegis config show`** — prints `Settings().redacted_dump()` as pretty JSON.

   **`aegis config set KEY VALUE`** — loads `config.yaml`, sets the dotted key, writes back.

5. **`RelationalStore` addition** — `load_recent(limit: int = 100) -> list[RCAReport]` abstract method; implemented in `FilesystemStore` (scan all JSON files), `SQLiteStore` (`SELECT ... ORDER BY created_at DESC LIMIT ?`), `S3Store` (list `reports/` prefix), `PostgresStore` stub (raises `NotImplementedError`).

6. **`tests/unit/test_cli.py`** — `typer.testing.CliRunner` tests:
   - `test_analyze_help`: `aegis analyze --help` exits 0.
   - `test_config_show_redacts_secrets`: output does not contain API key value.
   - `test_save_config_writes_json`: `--save-config` creates a JSON file with expected keys.
   - `test_config_file_sets_defaults`: values in JSON config file appear in the merged options.
   - `test_cli_flag_overrides_config_file`: explicit CLI flag wins over JSON config file.
   - `test_export_help`: `aegis export --help` exits 0.

7. **End-to-end smoke test** — `tests/integration/test_e2e_cli.py`:
   - Patches `Orchestrator.run` to return a pre-built `RCAReport`.
   - Calls `aegis analyze --dump FIXTURE_DUMP --output json`.
   - Asserts stdout is valid `RCAReport` JSON with correct `incident_id` field.
   - Second call: `--output rich` — asserts stdout contains root cause text.

### Success Criteria

- `aegis analyze --help` lists all flags including `--config` and `--save-config`.
- `aegis config show` redacts `database_url` as `***`.
- `--save-config` creates a JSON file at the default path; re-loading it produces the same effective options.
- A JSON config file value is used when no CLI flag is given; a CLI flag overrides a JSON value.
- `pytest tests/unit/test_cli.py` passes with mocked orchestrator.
- `pytest tests/integration/test_e2e_cli.py` produces valid `RCAReport` JSON on stdout.

---

## Phase 8: REST API Layer

**Goal:** Implement the FastAPI application with all endpoints, SSE streaming, auth middleware, and background task management.

### Deliverables

1. **`api/app.py`** — `create_app(settings: Settings) -> FastAPI`:
   - Registers all routers.
   - Attaches `AuthMiddleware`, `RateLimitMiddleware`.
   - On startup: initializes all backends (DB pool, S3 client, Qdrant client, AI client).
   - On shutdown: closes all connections.

2. **`api/routes/incidents.py`** — `POST /v1/incidents/analyze`:
   - Parses `multipart/form-data`; validates files.
   - Uploads raw files to `S3Store`.
   - Creates `incidents` row with `status=pending`.
   - Starts `Orchestrator.run()` as a FastAPI `BackgroundTask`.
   - Returns `{ "incident_id": "...", "status": "analyzing" }` immediately.
   - `POST /v1/incidents/{id}/continue` — HITL continuation.
   - `GET /v1/incidents/` — List with filters.

3. **`api/routes/stream.py`** — `GET /v1/incidents/{id}/stream`:
   - Returns a `StreamingResponse` with `media_type="text/event-stream"`.
   - Subscribes to the orchestrator's event queue (an `asyncio.Queue` keyed by `incident_id`).
   - Formats events as `data: {json}\n\n` with `event: {type}\n`.
   - Sends heartbeat comment every 15 seconds.
   - Returns 404 if `incident_id` not found.

4. **`api/routes/reports.py`** — `GET /v1/incidents/{id}/report`:
   - Checks DB for completed report.
   - Returns 200 + `RCAReport` if complete.
   - Returns 202 + `{ "status": "analyzing" }` if still running.

5. **`api/middleware/auth.py`** — `AuthMiddleware(BaseHTTPMiddleware)`:
   - Reads `X-Aegis-API-Key` header.
   - Hashes with `bcrypt` and checks against `api_keys` table (to be added to migration).
   - Returns 401 on failure.
   - Excludes `/health` endpoint.

6. **`api/middleware/rate_limit.py`** — Using `slowapi` (wraps `limits` library).

7. **Wire `aegis server` command** — Now that Phase 8 exists, complete the `aegis server` command stub from Phase 7 by pointing it at `create_app()`.

8. **`tests/integration/test_api.py`** — Uses `httpx.AsyncClient` with `app` as transport:
   - Full analyze → poll report flow with mock orchestrator.
   - SSE stream receives `agent_turn` and `complete` events.
   - Auth middleware returns 401 on missing key.
   - Rate limiter returns 429 after N requests.

### Success Criteria

- `POST /v1/incidents/analyze` returns within 200 ms (background task started; no LLM called synchronously).
- SSE stream delivers all agent turns in order and closes with a `complete` event.
- Auth middleware blocks all routes except `/health` without a valid key.
- `pytest tests/integration/test_api.py` passes with mocked orchestrator.

---

## Phase 9: Secure Code Sandbox

**Goal:** Implement the Docker-based sandbox executor that compiles and validates AI-generated code patches.

### Deliverables

1. **`sandbox/executor.py`** — `SandboxExecutor`:
   - `async def validate(patch: str, language: str) -> ValidationResult`:
     - Writes patch to a temp file.
     - Builds `docker run` command with all flags from design spec.
     - Runs via `asyncio.create_subprocess_exec` with timeout.
     - Returns `ValidationResult { passed: bool, exit_code: int, compiler_output: str, lint_findings: list[str] }`.
   - If Docker is not available: returns `ValidationResult(passed=None, ...)` with a warning — sandbox is optional.

2. **`sandbox/validators.py`** — Language detection from file extension + MIME type. Maps language string to Docker image tag.

3. **`sandbox/Dockerfile.cpp`**, `sandbox/Dockerfile.python`, `sandbox/Dockerfile.java`, `sandbox/Dockerfile.typescript` — Minimal base images (Alpine + compiler only, no curl/wget/nc). These are built and stored in the local Docker registry during setup.

4. **`Makefile`** target `build-sandbox-images` — Builds all four images.

5. **Integration with `agents/code_analyst.py`** — After producing `probabilistic_fix`, the Code Analyst Agent calls `SandboxExecutor.validate()`. If `passed=False`, the compiler output is added to the agent's context and it retries once. `fix_validation_result` is populated in the final `RCAReport`.

6. **`tests/unit/test_sandbox.py`** — Uses `unittest.mock.patch("asyncio.create_subprocess_exec")` to inject mock Docker output. Tests valid C++ patch (exit 0), invalid Python patch (exit 1 + error message), Docker unavailable path.

### Success Criteria

- Valid C++ patch returns `ValidationResult(passed=True)`.
- Invalid patch (syntax error) returns `ValidationResult(passed=False)` with compiler error text.
- `SandboxExecutor` completes (doesn't hang) when Docker is unavailable — returns graceful error.
- Sandbox containers have no network access (verified by `docker inspect`).

---

## Phase 10: Testing & Hardening

**Goal:** Achieve 80%+ ground-truth accuracy, sub-12k-token average, passing CI, and production-ready security.

### Deliverables

1. **Ground truth incidents** — At minimum 10 incidents in `tests/ground_truth/incidents/`. Each with:
   - Raw input files (dump, log, or both).
   - `expected_output.json`: `{ "fault_class", "faulting_module", "root_cause_keywords": ["list", "of", "expected", "phrases"] }`.
   - `README.md`: human description of the true root cause.

2. **`tests/ground_truth/eval_runner.py`**:
   - Runs all incidents through the full pipeline (real LLM calls; requires API key).
   - Scores each as `PASS` (correct fault class + module + any root_cause_keyword in conclusion), `PARTIAL` (correct class only), `FAIL`.
   - Asserts overall PASS rate ≥ 80%.
   - Prints token usage per incident.

3. **`tests/benchmarks/token_budget.py`** — Runs Data Adapter on 5 canonical dump+log pairs (no LLM call); asserts average incident brief is ≤12,000 tokens when tokenized via `tiktoken`.

4. **Security hardening checklist** (reviewed manually and in CI):
   - `SensitiveFilter` attached to all loggers in `Orchestrator.__init__`.
   - All `subprocess.run()` calls use list-form args (no shell=True).
   - All user-uploaded file paths are validated with `Path.resolve()` inside a configured upload root to prevent path traversal.
   - API key stored as bcrypt hash; never returned in any response.
   - Presidio scrubbing runs before any text is passed to external LLM.
   - Docker sandbox has `--network=none --cap-drop ALL --read-only`.

5. **`docker-compose.yml`** — Full local stack: `aegis-api`, `postgres`, `minio`, `qdrant`. With health checks and restart policies.

6. **`docker-compose.test.yml`** — Test-only stack without `aegis-api`; used by integration tests.

7. **`Makefile`** targets: `install`, `lint`, `typecheck`, `test`, `test-integration`, `test-ground-truth`, `benchmark-tokens`, `build-sandbox-images`, `up`, `down`.

8. **Updated `docs/README.md`** — Add `specs/PRODUCTION_DESIGN_SPEC.md`, `specs/IMPLEMENTATION_PLAN.md`, `specs/AGENTIC_IMPLEMENTATION_PLAN.md` to the documentation registry.

### Success Criteria

- Ground truth eval: ≥8 of 10 incidents score PASS.
- Token benchmark: average incident brief ≤12,000 tokens.
- `mypy src/ --strict` passes with zero errors.
- `pytest tests/unit/` passes with ≥90% line coverage on `core/` and `agents/`.
- `docker-compose up` starts a fully operational local stack.
- `aegis analyze --dump tests/ground_truth/incidents/GTC-001/inputs/dump.dmp` returns a valid `RCAReport` JSON.

---

## Dependency Graph (phases with hard prerequisites)

```
Phase 1 (Foundation)
  │
  ├──► Phase 2 (Data Adapter)          ← needs schemas
  │       │
  │       └──► Phase 5 (MAS)           ← needs adapter output schema
  │
  ├──► Phase 3 (AI Backends)
  │       │
  │       └──► Phase 5 (MAS)           ← needs AIAPIBackend
  │
  ├──► Phase 4 (Debug Backends)
  │       │
  │       └──► Phase 2 (Data Adapter)  ← adapter calls debug backend
  │
  ├──► Phase 6 (Storage)
  │       │
  │       └──► Phase 5 (MAS)           ← orchestrator calls storage
  │
  ├──► Phase 6.1 (Code Backend)        ← optional; Data Adapter Stage 8 calls it
  │       └──► Phase 7 (CLI)           ← --code-provider / --repo wire it in
  │
  ├──► Phase 6.2 (Log Backend)         ← optional; Data Adapter Stage 4 calls it
  │       └──► Phase 7 (CLI)           ← --log-provider / --log-service wire it in
  │
  Phase 5 (MAS Engine)
  │
  ├──► Phase 7 (CLI)                   ← CLI calls orchestrator directly; first E2E test gate
  │       │
  │       └──► Phase 8 (API)           ← API wraps orchestrator; aegis server wired here
  │
  └──► Phase 9 (Sandbox)               ← Code Analyst calls sandbox

  Phases 7, 8, 9 ──► Phase 10 (Testing & Hardening)
```

**Minimum viable working product** (end-to-end pipeline, no API): Phases 1 → 4 → 2 → 3 → 5 → 6 → 7. Phases 6.1 / 6.2 (Code & Log backends) are optional enrichers — they can land alongside Phase 6 or be deferred without blocking the MVP.  
**Full production deployment**: all 10 phases complete.
