# Aegis SWR — Agentic Implementation Plan

**Purpose:** Each section below is a self-contained agentic execution brief for one implementation phase. Each brief specifies which AI agents to use, what to give them, what they must produce, and how to verify the output before moving on.

**Reference documents:**
- `docs/specs/PRODUCTION_DESIGN_SPEC.md` — schemas, interfaces, algorithms
- `docs/specs/IMPLEMENTATION_PLAN.md` — phase deliverables and success criteria
- `docs/prototype-analysis-specs/` — gap analysis and prototype heuristics

---

## Step 1: Foundation & Package Setup

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `PackageArchitect` | Creates `pyproject.toml`, all `__init__.py` skeletons, CI config |
| `SchemaEngineer` | Implements all Pydantic v2 models in `core/schemas.py` and `core/fault_codes.py` |
| `InterfaceDesigner` | Implements all abstract base classes in `backends/base.py` and `agents/base.py` |
| `ConfigEngineer` | Implements `config/settings.py` + `config.yaml` |

### Agentic Execution Brief

#### Agent: PackageArchitect

**Inputs provided:**
- Target directory: `src/aegis_swr/`
- Package name: `aegis-swr`, module root: `aegis_swr`
- Dependency list from `PRODUCTION_DESIGN_SPEC.md §3`
- Full directory tree from `PRODUCTION_DESIGN_SPEC.md §2`

**Instructions:**
1. Create `pyproject.toml` at repo root with exact content from spec §3. Include all dependencies, extras, dev group, and the `aegis` CLI script entry point.
2. Create all `__init__.py` files for every directory in the tree. Each `__init__.py` is empty except for a module-level `__all__ = []`.
3. Create `src/aegis_swr/py.typed` (empty marker file for PEP 561).
4. Create `.env.example` documenting all required environment variables.
5. Create `.github/workflows/ci.yml` with three jobs: `lint` (ruff), `typecheck` (mypy), `unit-test` (pytest tests/unit/).
6. Create `Makefile` with targets: `install`, `lint`, `typecheck`, `test`.

**Verification:** Run `poetry install` and `python -c "import aegis_swr; print('ok')"`. Must succeed.

---

#### Agent: SchemaEngineer

**Inputs provided:**
- Full schema definitions from `PRODUCTION_DESIGN_SPEC.md §4`
- Pydantic v2 docs context (model validators, field definitions, `model_dump_json`)

**Instructions:**
1. Implement `src/aegis_swr/core/schemas.py` with all models exactly as specified in §4: `IncidentMode`, `DumpFormat`, `IncidentSource`, `StackFrame`, `DebugExtractionResult`, `ConfidenceLevel`, `Hypothesis`, `AgentTurn`, `SkepticVerdict`, `HITLRequest`, `RCAReport`, `InvestigationState` (TypedDict), `OSKernelOutput`, `CodeAnalystOutput`, `LogHistorianOutput`, `ValidationResult`, `UIContext`, `CommitRecord`, `BlameRecord`.
2. All models use Pydantic v2 syntax (`model_config = ConfigDict(...)` not class `Config`).
3. All `datetime` fields are `datetime` with `timezone.utc` default factory where auto-populated.
4. Add `model_json_schema()` class method verification: call it on each model at import time in tests.
5. Implement `src/aegis_swr/core/fault_codes.py` with `FaultClass` enum and the full platform mapping table from spec §4.2. Include `map_windows_ntstatus(code: str) -> FaultClass`, `map_linux_signal(signal: int) -> FaultClass`, `map_macos_exception(code: int) -> FaultClass` functions.
6. Write `tests/unit/test_schemas.py`: test that each model can be instantiated with required fields, serialized to JSON, and deserialized back without data loss. Test all three FaultClass mapping functions with boundary inputs.

**Verification:** `pytest tests/unit/test_schemas.py -v` must pass. `mypy src/aegis_swr/core/schemas.py` must pass.

---

#### Agent: InterfaceDesigner

**Inputs provided:**
- All ABC definitions from `PRODUCTION_DESIGN_SPEC.md §6`
- `BaseAgent` spec from `PRODUCTION_DESIGN_SPEC.md §7.3`
- Type hints from schemas (available after SchemaEngineer completes)

**Instructions:**
1. Implement `src/aegis_swr/backends/base.py` with all ABCs: `AIAPIBackend`, `DebugBackend`, `RelationalStore`, `ObjectStore`, `VectorStore`, `LogBackend`, `CodeBackend`. Use Python `abc.ABC` and `abc.abstractmethod`. Include `ClassVar` annotations on `DebugBackend.SUPPORTED_FORMATS` and `SUPPORTED_PLATFORMS`. Full docstrings on every abstract method.
2. Implement `src/aegis_swr/agents/base.py` with `BaseAgent(ABC)`: constructor takes `ai_backend: AIAPIBackend`, `settings: Settings`; abstract method `run(state: InvestigationState) -> AgentTurn`; protected helper `_append_turn(state: InvestigationState, turn: AgentTurn) -> None` that appends to `state["discussion_history"]`.
3. Implement `src/aegis_swr/core/exceptions.py` with: `AegisSWRError(Exception)`, `AIOutputValidationError(AegisSWRError)`, `PlatformNotSupportedError(AegisSWRError)`, `SandboxExecutionError(AegisSWRError)`, `IncidentNotFoundError(AegisSWRError)`.
4. Write `tests/unit/test_interfaces.py`: verify that instantiating any ABC directly raises `TypeError`. Verify that a minimal concrete subclass satisfying all abstract methods can be instantiated.

**Verification:** `mypy src/aegis_swr/backends/base.py src/aegis_swr/agents/base.py` passes. Tests pass.

---

#### Agent: ConfigEngineer

**Inputs provided:**
- Full config schema from `PRODUCTION_DESIGN_SPEC.md §11`

**Instructions:**
1. Implement `src/aegis_swr/config/settings.py` using Pydantic Settings v2. Define nested `BaseSettings` subclasses: `CoreSettings`, `AISettings`, `DebugSettings`, `StorageSettings`, `APISettings`, `SandboxSettings`, `AgentWeightsSettings`. Compose into `Settings(BaseSettings)` with `model_config = SettingsConfigDict(yaml_file="config.yaml", env_prefix="AEGIS__", env_nested_delimiter="__")`.
2. Create `config.yaml` at repo root with all default values from spec §11.
3. Add `tests/unit/test_settings.py` that creates a `Settings` object with `config.yaml` defaults and asserts key values (max_debate_rounds=4, consensus_threshold=0.85).

**Verification:** `python -c "from aegis_swr.config.settings import Settings; s = Settings(); print(s.core.max_debate_rounds)"` prints `4`.

---

### Step 1 Integration Check

After all four agents complete, run:
```bash
poetry install
mypy src/ --strict --ignore-missing-imports
pytest tests/unit/ -v
```
All must pass before proceeding to Step 2.

---

## Step 2: Data Adapter Layer

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `PipelineEngineer` | Core `DataAdapter` class with all nine stages |
| `NLPEngineer` | Drain3 clustering, Presidio PII scrubbing, OCR integration |
| `TestEngineer` | Fixtures and unit tests for all pipeline stages |

### Agentic Execution Brief

#### Agent: PipelineEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §5` — full pipeline stage definitions, `IncidentBrief` structure
- `docs/prototype-analysis-specs/TOKEN_WASTE_REPORT.md` — all 6 algorithmic rules for the Data Adapter
- `docs/prototype-analysis-specs/PROMPT_HEURISTICS.md §4` — all regex patterns for noise removal

**Instructions:**
1. Implement `src/aegis_swr/core/data_adapter.py` — `DataAdapter(settings: Settings)` with `async def process(source: IncidentSource, debug_backend: DebugBackend | None) -> IncidentBrief`.
2. Implement `_compute_hash()`: SHA-256 in 8192-byte chunks using `hashlib`.
3. Implement `_detect_format()`: read first 8 bytes; check magic bytes — Windows minidump: `MDMP`; ELF core: `\x7fELF`; Apple crashreport: JSON starting with `{`; default to `WINDOWS_MINIDUMP` on `.dmp` extension.
4. Implement `_apply_noise_filter()` using the exact regex patterns from `PROMPT_HEURISTICS.md §4`: DBGHELP strip, fill pattern replace (`0xCCCCCCCC`, `0xDDDDDDDD`, `0xFEEEFEEE`, `0xABABABAB`, `0xBAADF00D` → `<fill>`), DLL list drop (between `*** WARNING:` and `EXCEPTION_ANALYSIS:`), head+tail truncation at 8,000 chars (4,000 / 4,000 split).
5. Implement `_enforce_assumption_limit()` using `tiktoken` (cl100k_base encoding) to count tokens.
6. Implement `_assemble_brief()` that constructs the `IncidentBrief` dict matching the JSON structure in spec §5.2.
7. Implement conditional history injection logic check in `_should_inject_history(source, recent_incidents)`.

**Verification:** `mypy src/aegis_swr/core/data_adapter.py` passes.

---

#### Agent: NLPEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §5.1` — stages 4 (log processing), 5 (OCR), 6 (PII scrubbing)
- `TOKEN_WASTE_REPORT.md` — Rule 2 (temporal windowing), Rule 3 (noise filter)

**Instructions:**
1. Implement `DataAdapter._process_logs()`:
   - For each log path, open and read lines.
   - Apply temporal window: keep lines within ±30 seconds of `incident_timestamp`. If no timestamp: keep last 500 lines with warning.
   - Apply Drain3: `TemplateMiner` with `SimpleProfiler()`. Group lines by template; for each template appearing >3 times, replace with `"{template} (×{count})"`.
   - Severity filter: discard `INFO`/`DEBUG` lines outside the ±5 s window. Keep all `WARNING`/`ERROR`/`FATAL`/`CRITICAL` lines regardless of timestamp.
   - Enforce 2,000-token budget on combined log output (truncate oldest lines first).
2. Implement `DataAdapter._process_screenshot()`:
   - Conditionally import `pytesseract` (guarded with `try/except ImportError`).
   - Run `pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)`.
   - Filter to words with `conf > 60`.
   - Assemble into `UIContext { error_message: str, visible_timestamp: str | None, ui_elements: list[str] }`.
   - Return `None` if pytesseract not installed or confidence too low.
3. Implement `DataAdapter._scrub_pii()`:
   - Conditionally import `presidio_analyzer` and `presidio_anonymizer`.
   - Configure `AnalyzerEngine` with entity types from spec §5.1 stage 6.
   - Run `analyzer.analyze()` then `anonymizer.anonymize()`.
   - Build substitution map `{ "[REDACTED_EMAIL_1]": "user@example.com", ... }`.
   - Return scrubbed text + substitution map.
   - If Presidio not installed: log warning and return original text + empty map (fail open — never block analysis).

**Verification:** Write a test string with known PII; assert all entities are replaced and the substitution map has correct entries.

---

#### Agent: TestEngineer (Data Adapter)

**Inputs provided:**
- All implemented pipeline stages from PipelineEngineer and NLPEngineer
- Sample files needed for fixtures

**Instructions:**
1. Create `tests/unit/fixtures/` directory with:
   - `sample_cdb_output.txt` — realistic 200-line CDB `!analyze -v` output containing DBGHELP noise, DLL list, fill patterns, and an EXCEPTION_ANALYSIS block.
   - `sample_logs_with_pii.txt` — 50 lines including email addresses, IP addresses, an AWS key pattern, and heartbeat repetitions.
   - `sample_logs_timestamped.txt` — 200 lines with ISO timestamps spanning 10 minutes; known crash at line 100.
2. Write `tests/unit/test_data_adapter.py` with these test cases:
   - `test_noise_filter_removes_dbghelp`: assert zero DBGHELP lines in output.
   - `test_noise_filter_replaces_fill_patterns`: assert no `0xCCCCCCCC` in output; `<fill>` present.
   - `test_noise_filter_truncates_to_8k`: input > 8k chars → output ≤ 8k chars with truncation marker.
   - `test_temporal_window_slices_correctly`: logs from `±30s` window kept; logs from `±2min` discarded.
   - `test_drain3_deduplicates_heartbeats`: 100 identical heartbeat lines → one template line with count.
   - `test_pii_scrubbing_emails`: all emails replaced with `[REDACTED_EMAIL_*]`.
   - `test_pii_scrubbing_aws_keys`: AWS key pattern replaced.
   - `test_assumption_token_cap`: 1000-token assumption string truncated to ≤500 tokens.
   - `test_hash_consistency`: same file hashed twice → same SHA-256.
   - `test_format_detection_minidump`: file with `MDMP` magic → `DumpFormat.WINDOWS_MINIDUMP`.
   - `test_full_pipeline_produces_brief`: end-to-end with mock DebugBackend returning fixture result; assert `IncidentBrief` has all required fields.

**Verification:** `pytest tests/unit/test_data_adapter.py -v` passes. Coverage on `data_adapter.py` ≥ 85%.

---

## Step 3: AI Backends

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `AnthropicEngineer` | `anthropic_provider.py` with caching, structured output, streaming |
| `OpenAIEngineer` | `openai_provider.py` with JSON schema output, streaming |
| `BackendTestEngineer` | Unit tests with mocked LLM clients |

### Agentic Execution Brief

#### Agent: AnthropicEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §6.1` — AIAPIBackend interface and implementation notes
- Claude API documentation context: `cache_control`, tool use pattern for structured output, `messages.stream()`

**Instructions:**
1. Implement `src/aegis_swr/backends/ai/anthropic_provider.py` — `AnthropicBackend(AIAPIBackend)`.
2. Constructor: `__init__(self, settings: AISettings)` — creates `anthropic.AsyncAnthropic()` client; sets `model_name = settings.model`.
3. Implement `generate()`:
   - Build system message with `cache_control: {"type": "ephemeral"}`.
   - If `output_schema` is not None: define a single tool with `name="structured_output"`, `description="Output the analysis as structured JSON"`, `input_schema=output_schema.model_json_schema()`. Add `tool_choice={"type": "tool", "name": "structured_output"}`.
   - Call `await self._client.messages.create(...)`.
   - If structured output: extract `tool_use` block, parse JSON, validate with `output_schema.model_validate(json_data)`. On `ValidationError`: construct a correction message and retry once.
   - Update `state["token_tracker"]` with `response.usage`.
   - Raise `AIOutputValidationError` if retry also fails.
4. Implement `stream()`: use `async with self._client.messages.stream(...) as stream: async for text in stream.text_stream: yield text`.
5. Implement `src/aegis_swr/backends/ai/__init__.py` factory.

**Key invariant:** The system prompt block MUST always include `cache_control: {"type": "ephemeral"}`. Never omit it — this is the primary token-cost reduction mechanism (system prompt re-billed at ~10% on cache hits).

**Verification:** `mypy src/aegis_swr/backends/ai/anthropic_provider.py` passes.

---

#### Agent: OpenAIEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §6.1` — OpenAI implementation notes
- OpenAI structured output documentation context

**Instructions:**
1. Implement `src/aegis_swr/backends/ai/openai_provider.py` — `OpenAIBackend(AIAPIBackend)`.
2. Constructor: `__init__(self, settings: AISettings)` — creates `openai.AsyncOpenAI()` client.
3. Implement `generate()`:
   - If `output_schema`: use `response_format={"type": "json_schema", "json_schema": {"name": output_schema.__name__, "schema": output_schema.model_json_schema(), "strict": True}}`.
   - Parse response JSON and validate with Pydantic. Same retry logic as Anthropic.
4. Implement `stream()`: `async for chunk in await self._client.chat.completions.create(..., stream=True, stream_options={"include_usage": True}): if chunk.choices[0].delta.content: yield chunk.choices[0].delta.content`.

**Verification:** mypy passes on the file.

---

#### Agent: BackendTestEngineer (AI Backends)

**Instructions:**
1. Write `tests/unit/test_ai_backends.py` using `unittest.mock.AsyncMock` to patch `anthropic.AsyncAnthropic` and `openai.AsyncOpenAI`.
2. Test cases:
   - `test_anthropic_structured_output_valid`: mock returns valid JSON matching `Hypothesis` schema → `generate()` returns `Hypothesis` instance.
   - `test_anthropic_retry_on_invalid_schema`: first mock call returns malformed JSON; second returns valid → retried once successfully.
   - `test_anthropic_raises_validation_error_after_retry`: both calls return malformed JSON → `AIOutputValidationError` raised.
   - `test_anthropic_stream_yields_tokens`: mock stream yields 3 text deltas → `stream()` yields same 3 strings.
   - `test_openai_structured_output_valid`: same pattern for OpenAI.
   - `test_factory_returns_anthropic`: `create_ai_backend(AISettings(provider="anthropic"))` returns `AnthropicBackend`.
   - `test_factory_returns_openai`: returns `OpenAIBackend`.

**Verification:** `pytest tests/unit/test_ai_backends.py -v` passes with no network calls.

---

## Step 4: Debug Backends

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `WindowsDebugEngineer` | `cdb_worker.py` — full CDB implementation with all regex parsers |
| `WinDbgJSEngineer` | `windbg_js_worker.py` + `assets/windbg_diagnostic.js` — WinDbg JS engine backend |
| `LinuxDebugEngineer` | `gdb_worker.py` and `lldb_worker.py` — Linux/macOS stubs |
| `DebugTestEngineer` | Unit tests with fixture subprocess output for all backends |

### Agentic Execution Brief

#### Agent: WindowsDebugEngineer

**Inputs provided:**
- `docs/prototype-analysis-specs/WIN_DEPENDENCIES.md` — full CDB command sequence and all regex patterns
- `docs/prototype-analysis-specs/PROMPT_HEURISTICS.md §4` — extraction regexes
- `PRODUCTION_DESIGN_SPEC.md §6.2` — DebugBackend interface

**Instructions:**
1. Implement `src/aegis_swr/backends/debug/cdb_worker.py` — `CdbBackend(DebugBackend)`.
2. Port all regex extractors from prototype's `cdb.py` exactly as documented in `WIN_DEPENDENCIES.md §8` and `PROMPT_HEURISTICS.md §4`. Extractors must produce structured fields: `exception_code_raw`, `exception_address`, `faulting_module`, `faulting_function`, debug timestamp.
3. Implement `_parse_stack_frames(text: str) -> list[StackFrame]`: parse numbered frame lines in CDB bt output. Handle both resolved (`module!function+offset`) and unresolved (`module+offset`) formats.
4. Compute `symbol_resolution_score = len([f for f in frames if f.function is not None]) / max(len(frames), 1)`.
5. Apply noise filter to `raw_text_excerpt` using `DataAdapter._apply_noise_filter()` logic (duplicated or imported — prefer importing from `core/data_adapter.py` as a standalone function).
6. Implement `_symbol_path_string(symbol_path: Path) -> str`: builds `srv*{cache}*https://msdl.microsoft.com/download/symbols;{local_path}` format.
7. RAII: use `subprocess.run()` inside a `try/finally` block; never leave subprocess open on exception.
8. Implement `src/aegis_swr/backends/debug/_symbol_path.py` — `resolve_symbol_path()` with platform defaults.

**Verification:** mypy passes.

---

#### Agent: WinDbgJSEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §6.2.2` — full WinDbg JS backend specification (architecture, bridge design, JS asset, JSON→result mapping, prototype-defect table)
- `prototype/wincrash_analyzer/backends/debug/js_provider.py` — prototype implementation to supersede
- `prototype/wincrash_analyzer/core/windbg_server.py` — prototype HTTP bridge to supersede
- `docs/prototype-analysis-specs/WIN_DEPENDENCIES.md §4, §5, §7` — COM dependency, DDM query API, bridge TCP notes
- All previously implemented debug backend code (`_base.py`, `cdb_worker.py`, `_symbol_path.py`) for import style and conventions

**Instructions:**

**Part 1 — `backends/debug/assets/windbg_diagnostic.js`:**

1. Create directory `src/aegis_swr/backends/debug/assets/`.
2. Write the JS file exactly as specified in PRODUCTION_DESIGN_SPEC.md §6.2.2 ("Production JS Diagnostic Script"). Do not embed it in Python code.
3. Use exactly three substitution tokens: `__CALLBACK_URL__`, `__MAX_FAULTING_FRAMES__`, `__MAX_OTHER_FRAMES__`. No others.
4. Script structure must be: `initializeScript()` export (DDM API version declaration), then an IIFE that queries the DDM and POSTs JSON via `ActiveXObject("MSXML2.XMLHTTP")`.
5. All DDM accesses must be wrapped in `try/catch` — the DDM is not guaranteed to expose every field for every dump type; a missing attribute must not abort the script and must not prevent the callback POST from firing.

**Part 2 — `backends/debug/windbg_js_worker.py`:**

1. Implement `_make_handler(data_queue: queue.Queue[str]) -> type[BaseHTTPRequestHandler]`:
   - Returns a class whose `do_POST` reads `Content-Length` bytes, enqueues the raw body string, responds 200. Suppresses HTTP access logs via a no-op `log_message`.
   - Uses a **closure** over `data_queue` — NOT a class-level attribute. This eliminates the prototype's race condition.

2. Implement `class _CallbackBridge` as a RAII context manager:
   - `__init__(self, callback_timeout: int)` — stores timeout, initialises `self.port = 0`.
   - `__enter__`: creates `self._queue: queue.Queue[str] = queue.Queue()`, calls `_make_handler(self._queue)`, binds `HTTPServer(("127.0.0.1", 0), handler)`, reads `httpd.server_address[1]` → `self.port`, starts daemon thread.
   - `__exit__`: `httpd.shutdown(); httpd.server_close()`.
   - `wait_for_payload(self) -> str`: `self._queue.get(timeout=self._timeout)`; on `queue.Empty` raise `DebugExtractionError("Timed out waiting for WinDbg JS callback")`.

3. Implement `class WinDbgJSBackend(_BaseDebugBackend)`:
   - `SUPPORTED_FORMATS = [DumpFormat.WINDOWS_MINIDUMP]`
   - `SUPPORTED_PLATFORMS = ["Windows"]`
   - `_asset_path(self) -> Path`: `Path(__file__).parent / "assets" / "windbg_diagnostic.js"`.
   - `_prepare_js(self, port: int) -> str`: reads the asset file, substitutes all three tokens. Raises `DebugExtractionError` if the asset file is absent.
   - `_build_command_sequence(self, source, symbol_path) -> list[str]`: `["cdb.exe", "-z", str(source.dump_path), "-y", self._symbol_path_string(symbol_path), "-c", f'.scriptload "{tmp_js_path}"; g; q']`. The `tmp_js_path` is passed as a parameter (written by `_parse` before calling `_run`).
   - Override `extract()` from the base: orchestrates the bridge + temp file lifecycle using `contextlib.ExitStack` for RAII. Sequence: (a) start bridge, (b) write temp JS, (c) run subprocess, (d) validate JsProvider loaded, (e) wait for payload, (f) parse, (g) cleanup all resources in reverse order.
   - `_parse(self, raw_json: str, source) -> DebugExtractionResult`: parse JSON from the bridge payload. Map fields per spec §6.2.2 table. Use `map_windows_ntstatus` for `ExceptionCode`. Build `StackFrame` list from `FaultingThread.Frames`. `raw_text_excerpt = apply_noise_filter(raw_json[:8000])`.

4. **`_build_command_sequence` must not write any temp file itself** — file lifecycle belongs in `extract()` with RAII. `_build_command_sequence` receives `tmp_js_path` as a parameter (override the signature: `_build_command_sequence(self, source, symbol_path, tmp_js_path="")` with a default to satisfy the ABC).

5. **No `shell=True` anywhere.** All subprocess invocations use list-form argv.

**Part 3 — Factory update (`backends/debug/__init__.py`):**

1. Add `WinDbgJSBackend` to imports and `__all__`.
2. Add `_windbg_js_available() -> bool` — probes for `JsProvider.dll` by running `cdb.exe -version` and checking if `JsProvider` appears in stdout. Catches `FileNotFoundError` → `False`. Caches result via `functools.lru_cache(maxsize=1)` so the probe only runs once per process.
3. Update `create_debug_backend` for Windows per spec §6.2.2 ("Factory Update") — `engine="auto"` → try `WinDbgJSBackend` if available, else `CdbBackend`; `engine="windbg_js"` → always `WinDbgJSBackend`; `engine="cdb"` → always `CdbBackend`.

**Part 4 — Config + Settings:**

1. Add to `config.yaml` under `backends.debug`: `engine: "auto"`, `callback_timeout_seconds: 60`, `max_faulting_frames: 20`, `max_other_thread_frames: 3`.
2. Add these four fields to `DebugSettings` in `config/settings.py` with matching defaults.

**Invariants (must hold):**
- `_CallbackBridge` never uses a module-level or class-level queue — each `with _CallbackBridge(...)` block gets its own `queue.Queue` instance.
- The temp JS file is always deleted, even if `subprocess.run` raises. Use `try/finally` or `contextlib.ExitStack`.
- `_windbg_js_available()` never raises — it returns `False` on any failure.
- The JS asset is read from disk at extraction time, not at import time, so it can be patched in tests without reloading the module.

**Verification:**
- `mypy src/` passes with no new errors.
- All existing tests continue to pass (`pytest tests/ -q`).

---

#### Agent: LinuxDebugEngineer

**Inputs provided:**
- `WIN_DEPENDENCIES.md` cross-platform replacement strategy sections
- `PRODUCTION_DESIGN_SPEC.md §6.2`

**Instructions:**
1. Implement `src/aegis_swr/backends/debug/gdb_worker.py` — `GdbBackend(DebugBackend)`:
   - `SUPPORTED_PLATFORMS = ["Linux"]`
   - Command: `["gdb", "--batch", "--quiet", "-ex", f"core-file {dump_path}", "-ex", "bt 20", "-ex", "info registers rip rsp rbp", "-ex", "quit"]`
   - Parse GDB `bt` output: frame lines match `#N  0x... in function (args) at file:line`.
   - Map POSIX signals to `FaultClass` using `fault_codes.map_linux_signal()`.
2. Implement `src/aegis_swr/backends/debug/lldb_worker.py` — `LldbBackend(DebugBackend)`:
   - `SUPPORTED_PLATFORMS = ["Darwin"]`
   - Command: `["lldb", "--batch", "-c", str(dump_path), "-o", "bt all", "-o", "register read pc sp", "-o", "quit"]`
   - Parse LLDB bt output: frame lines match `frame #N: 0x... module\`function at file:line`.
   - Map macOS exception types to `FaultClass`.
3. Implement `src/aegis_swr/backends/debug/__init__.py` factory.

**Verification:** mypy passes.

---

#### Agent: DebugTestEngineer

**Instructions:**

**Existing tests (already implemented, verify still pass):**
CDB/GDB/LLDB per-backend extraction, fault-class mapping, frame parsing, symbol score, noise filter, factory platform selection (win32/linux/darwin/unsupported).

**New tests for `WinDbgJSBackend` — add to `tests/unit/test_debug_backends.py`:**

1. Create `tests/unit/fixtures/sample_windbg_js_payload.json` — a realistic DDM JSON payload with:
   - `ExceptionCode: "0xc0000005"`, `ExceptionAddress: "0x00007ff8016a1c3f"`, `FaultingModule: "db_writer"`
   - `FaultingThread.Frames`: 5 frames, 4 with non-empty `Function`, 1 with empty `Function`
   - `AllThreadsSummary`: 2 additional threads, each with 2-3 summarised frames

2. Write the following tests, all using `mock.patch("aegis_swr.backends.debug._base.subprocess.run")`:

   - `test_windbg_js_parses_ddm_json`: fixture payload + mock subprocess output that includes `"JsProvider.dll"` string → `WinDbgJSBackend.extract()` returns `DebugExtractionResult` with `fault_class = MEMORY_ACCESS_VIOLATION`, `exception_address = "0x00007ff8016a1c3f"`, `faulting_module = "db_writer"`, `len(stack_frames) == 5`, `symbol_resolution_score == 0.8`.
   
     Implementation hint: the backend calls `bridge.wait_for_payload()`; patch `_CallbackBridge.wait_for_payload` (or mock the full bridge) to return the fixture JSON without actually starting a thread.
   
   - `test_windbg_js_command_uses_scriptload`: `_build_command_sequence` result contains `".scriptload"` string.
   
   - `test_windbg_js_raises_on_missing_jsprovider`: mock subprocess stdout does NOT contain `"JsProvider.dll"` (but payload is ready in bridge) → `DebugExtractionError` raised.
   
   - `test_windbg_js_raises_on_callback_timeout`: bridge's `wait_for_payload` raises `queue.Empty` → `DebugExtractionError` raised.
   
   - `test_windbg_js_missing_asset_raises`: delete (or mock) the JS asset path → `DebugExtractionError` raised before subprocess is invoked.

3. Write the following bridge-unit tests (no subprocess involved):

   - `test_callback_bridge_assigns_ephemeral_port`: `with _CallbackBridge(timeout=5) as b:` asserts `b.port > 0`. (Does start a real local socket — short-lived.)
   
   - `test_callback_bridge_per_instance_queue_isolation`: open two bridges simultaneously; POST to each port independently; `wait_for_payload()` on each returns only the payload sent to that specific port.

4. New factory tests:

   - `test_factory_returns_windbg_js_when_engine_forced`: `DebugSettings(engine="windbg_js")`, `platform="win32"` → `WinDbgJSBackend`.
   - `test_factory_returns_cdb_when_engine_forced`: `DebugSettings(engine="cdb")`, `platform="win32"` → `CdbBackend`.
   - `test_factory_auto_returns_cdb_when_js_unavailable`: `engine="auto"`, `platform="win32"`, patch `_windbg_js_available` → `False` → `CdbBackend`.
   - `test_factory_auto_returns_windbg_js_when_available`: `engine="auto"`, `platform="win32"`, patch `_windbg_js_available` → `True` → `WinDbgJSBackend`.

**Verification:** `pytest tests/unit/test_debug_backends.py -v` passes. `mypy src/` clean.

---

## Step 5: Multi-Agent System Engine

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `ConsensusEngineer` | `core/consensus.py` — weighted CS formula + convergence logic |
| `AgentPersonaEngineer` | All four agent implementations (`os_kernel.py`, `code_analyst.py`, `log_historian.py`, `skeptic.py`) |
| `OrchestratorEngineer` | `core/orchestrator.py` — LangGraph state graph wiring |
| `MASTestEngineer` | Unit tests with mock AI backends |

### Agentic Execution Brief

#### Agent: ConsensusEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §7.2` — CS formula, weight matrix, termination conditions

**Instructions:**
1. Implement `src/aegis_swr/core/consensus.py` — `ConsensusEvaluator(settings: AgentWeightsSettings)`.
2. Implement `calculate(agent_scores: dict[str, float], fault_class: FaultClass) -> float`: apply weight matrix lookup; compute weighted sum; normalize; return CS in [0.0, 1.0].
3. Implement `is_converged(current_score: float, previous_score: float | None, threshold: float, same_hypothesis: bool) -> bool`: True only if `current_score >= threshold` AND `same_hypothesis` is True (the primary hypothesis identity hasn't changed since last round).
4. Implement `is_deadlocked(score: float, round_num: int, max_rounds: int, hitl_threshold: float) -> bool`.
5. Write `tests/unit/test_consensus.py` with:
   - `test_formula_weights_memory`: all agents score 1.0 on MEMORY_ACCESS_VIOLATION → CS = 1.0.
   - `test_formula_not_converged_below_threshold`: CS = 0.70 < 0.85 → `is_converged` = False.
   - `test_convergence_requires_same_hypothesis`: same score but hypothesis changed → `is_converged` = False.
   - `test_deadlock_at_max_rounds`: CS = 0.40, round = 4, max = 4 → `is_deadlocked` = True.

---

#### Agent: AgentPersonaEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §7.3` — all four agent persona definitions, system prompts, output schemas
- `PROMPT_HEURISTICS.md` — all extracted heuristics to incorporate into system prompts
- `GAP_ANALYSIS.md §Gap 1, §Gap 6` — Skeptic agent assertion requirements

**Instructions:**
1. Implement `src/aegis_swr/agents/os_kernel.py` — `OSKernelAgent(BaseAgent)`:
   - System prompt verbatim from spec §7.3 OS Kernel section.
   - Incorporate heuristic from `PROMPT_HEURISTICS.md §1`: exception code to fault type mapping as few-shot examples in the system prompt.
   - `run()`: build message context from `incident_brief`; prepend low-symbol-coverage warning if `symbol_resolution_score < 0.50`; call `ai_backend.generate(output_schema=OSKernelOutput)`; return `AgentTurn`.
2. Implement `src/aegis_swr/agents/code_analyst.py` — `CodeAnalystAgent(BaseAgent)`:
   - Include `user_assumption` as a labeled block in the user message (not in system prompt).
   - Include `OSKernelOutput` from the previous turn.
   - System prompt incorporates structured output format from `PROMPT_HEURISTICS.md §2`.
3. Implement `src/aegis_swr/agents/log_historian.py` — `LogHistorianAgent(BaseAgent)`:
   - `run()` accepts `vector_store: VectorStore | None` as an additional parameter.
   - Applies conditional injection rule from spec §5.3.
   - If no history available (first incident): returns a no-op `AgentTurn` with `confidence_score = 0.0` adjustment.
4. Implement `src/aegis_swr/agents/skeptic.py` — `SkepticAgent(BaseAgent)`:
   - Runs three programmatic pre-checks BEFORE calling the LLM (spec §7.3 Skeptic section). If any check fails deterministically: set `confirmed=False` immediately without an LLM call.
   - Only calls LLM if pre-checks pass.
   - Output schema: `SkepticVerdict`.

**Verification:** mypy passes on all four agent files.

---

#### Agent: OrchestratorEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §7.1` — full LangGraph state graph definition with node names and conditional edges
- LangGraph v0.2 API: `StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`, `compile`

**Instructions:**
1. Implement `src/aegis_swr/core/orchestrator.py` — `Orchestrator(settings: Settings, ...)`.
2. Constructor accepts all backends: `ai_backend, debug_backend, relational_store, object_store, vector_store, log_backend, code_backend`.
3. Build `StateGraph(InvestigationState)`:
   - Node `data_adapter_node`: calls `DataAdapter.process()` and updates `state["incident_brief"]`.
   - Node `os_kernel_node`: calls `OSKernelAgent.run(state)`.
   - Node `code_analyst_node`: calls `CodeAnalystAgent.run(state)`.
   - Node `log_historian_node`: calls `LogHistorianAgent.run(state)` with `vector_store`.
   - Node `skeptic_node`: calls `SkepticAgent.run(state)`; calls `ConsensusEvaluator.calculate()`; updates `state["consensus_score"]` and `state["is_converged"]`.
   - Node `output_synthesizer_node`: constructs `RCAReport` from state; calls `SandboxExecutor.validate()` on `probabilistic_fix` if present; saves to `relational_store`; upserts to `vector_store`.
   - Node `hitl_node`: constructs `HITLRequest`; sets `state["hitl_pending"] = True`; saves state to DB.
4. Conditional edges from `skeptic_node`:
   - `is_converged` → `output_synthesizer_node`
   - `round_number >= max_rounds` and `is_deadlocked` → `hitl_node`
   - Otherwise → `os_kernel_node` (next round; increment `round_number`)
5. Compile: `self._graph = builder.compile()`.
6. Implement `async def run(source: IncidentSource) -> RCAReport`:
   - Check `relational_store.find_by_hash(source.dump_hash)` first — return cached report if exists.
   - Initialize `InvestigationState` with `incident_id`, empty history, `round_number=1`.
   - `await self._graph.ainvoke(initial_state)` → extract final `RCAReport`.
7. Implement `async def run_streaming(source: IncidentSource) -> AsyncGenerator[dict, None]`:
   - Use LangGraph `.astream()` on the compiled graph.
   - Yield event dicts matching SSE event types from spec §9.1.
8. Implement `async def continue_investigation(incident_id: UUID, user_data: dict) -> RCAReport` for HITL continuation.

**Verification:** mypy passes.

---

#### Agent: MASTestEngineer

**Inputs provided:**
- All MAS components implemented above

**Instructions:**
1. Create `tests/unit/fixtures/mock_ai_backend.py` — `MockAIBackend(AIAPIBackend)` that accepts a list of pre-scripted responses per call index. Rotates through them. Tracks call count.
2. Write `tests/unit/test_orchestrator.py`:
   - `test_full_pipeline_converges`: mock agents return `confidence=0.90` → completes in ≤2 rounds with `is_converged=True`.
   - `test_skeptic_rejection_triggers_next_round`: Skeptic returns `confirmed=False` in round 1 → round 2 starts; `discussion_history` has OS Kernel entry in round 2.
   - `test_deadlock_produces_hitl_request`: all rounds have CS < 0.50 → `RCAReport.hitl_request` is not None.
   - `test_cache_hit_skips_analysis`: relational store mock returns existing report for hash → `Orchestrator.run()` returns it immediately without calling any agent.
   - `test_token_tracker_accumulates`: three rounds × 2 agent calls each → `token_tracker["input_tokens"]` is sum of all mock usage values.
3. Write `tests/unit/test_agents.py`:
   - Per-agent: verify that the correct output schema class is requested from `ai_backend.generate()`.
   - `test_skeptic_fails_prechecks_without_llm_call`: provide a state where the stated module is absent from stack frames → `confirmed=False` returned without calling `ai_backend.generate()`.
   - `test_os_kernel_prepends_low_symbol_warning`: `symbol_resolution_score=0.30` → system prompt includes `[LOW SYMBOL COVERAGE: 30%]`.

**Verification:** `pytest tests/unit/test_orchestrator.py tests/unit/test_agents.py -v` all pass.

---

## Step 6: Storage Backends

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `FilesystemEngineer` | `filesystem_store.py` — JSON files + binary objects on disk |
| `SQLiteEngineer` | `sqlite_store.py` — SQLite database |
| `S3Engineer` | `s3_store.py` — S3/MinIO reports and raw objects |
| `StubEngineer` | `postgres_store.py` — NotImplementedError stub |
| `StorageTestEngineer` | Unit tests for all four backends + factory |

### Agentic Execution Brief

#### Agent: FilesystemEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §8.1` — filesystem layout and hash-index design
- `prototype/wincrash_analyzer/backends/store/filesystem.py` — reference implementation
- `backends/base.py` — `RelationalStore` and `ObjectStore` ABC signatures

**Instructions:**
1. Implement `src/aegis_swr/backends/storage/filesystem_store.py` — `FilesystemStore(RelationalStore, ObjectStore)`.
2. Constructor: `__init__(self, settings: StorageSettings)` — resolve `reports_dir` and `objects_dir` from settings using `pathlib.Path(x).expanduser().resolve()`.
3. Path-traversal guard helper `_safe_path(base: Path, *parts: str) -> Path`: resolves the joined path, asserts it starts with `base`, raises `ValueError` otherwise.
4. **`RelationalStore` methods** (all wrapped in `asyncio.to_thread`):
   - `save_report(report)`: mkdir reports_dir; write `{reports_dir}/{incident_id}.json`; if `dump_hash`: write `{reports_dir}/_hash_index/{dump_hash}` with content = incident_id string.
   - `get_report(incident_id)`: read `{incident_id}.json`; `FileNotFoundError` → `None`.
   - `find_by_hash(dump_hash)`: read `_hash_index/{dump_hash}` → incident_id; load and return report; any `FileNotFoundError` → `None`.
   - `update_hitl_response(incident_id, response)`: load report; update `hitl_request` from `response`; write back.
5. **`ObjectStore` methods** (wrapped in `asyncio.to_thread`):
   - `upload_raw(incident_id, filename, data)`: write to `{objects_dir}/{incident_id}/{filename}`; return key `f"{incident_id}/{filename}"`.
   - `get_raw(object_key)`: read from `{objects_dir}/{object_key}`; `FileNotFoundError` → raise `IncidentNotFoundError`.

**Invariants:** `_safe_path` is called on every user-supplied path component. No `shell=True`. No `os.system`.

**Verification:** mypy passes.

---

#### Agent: SQLiteEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §8.2` — SQLite schema
- `prototype/wincrash_analyzer/backends/store/sqlite.py` — reference implementation

**Instructions:**
1. Implement `src/aegis_swr/backends/storage/sqlite_store.py` — `SQLiteStore(RelationalStore)`.
2. Constructor: resolve `db_path` with `pathlib.Path(settings.db_path).expanduser()`. Call `_init_db()` synchronously in `__init__`.
3. `_init_db()`: `sqlite3.connect(db_path)` → execute `CREATE TABLE IF NOT EXISTS reports (...)` and `CREATE UNIQUE INDEX IF NOT EXISTS ...` per spec §8.2.
4. Helper `_connect(self) -> sqlite3.Connection`: returns `sqlite3.connect(str(self._db_path), timeout=30)`. Used in each operation (new connection per call for thread-safety).
5. **`RelationalStore` methods** (all wrapped in `asyncio.to_thread`):
   - `save_report(report)`: `INSERT OR REPLACE INTO reports ...` (all four columns).
   - `get_report(incident_id)`: `SELECT report_json WHERE incident_id = ?`; `None` if no row.
   - `find_by_hash(dump_hash)`: `SELECT report_json WHERE dump_hash = ?`; `None` if no row.
   - `update_hitl_response(incident_id, response)`: `SELECT report_json WHERE incident_id = ?`; mutate the parsed dict; `UPDATE reports SET report_json = ?`.

**Verification:** mypy passes.

---

#### Agent: S3Engineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §8.3` — S3 key layout, MinIO support, find_by_hash algorithm

**Instructions:**
1. Implement `src/aegis_swr/backends/storage/s3_store.py` — `S3Store(RelationalStore, ObjectStore)`.
2. Constructor: parse bucket from `settings.object_store_url` (strip `s3://` prefix). Create `self._client = boto3.client("s3", region_name=..., endpoint_url=settings.s3_endpoint_url or None)`. Store as `Any`.
3. Helper `_run(fn)`: `await asyncio.to_thread(fn)` — wraps any sync boto3 lambda.
4. Helper `_put_text(key, text)` and `_get_text(key) -> str | None`: `_get_text` returns `None` on `ClientError` with code `"NoSuchKey"`.
5. **`RelationalStore` methods**:
   - `save_report(report)`: `_put_text(f"reports/{incident_id}.json", report.model_dump_json())`; if dump_hash: `_put_text(f"hash-index/{dump_hash}", str(incident_id))`.
   - `get_report(incident_id)`: `_get_text(f"reports/{incident_id}.json")` → parse; `None` if missing.
   - `find_by_hash(dump_hash)`: `_get_text(f"hash-index/{dump_hash}")` → incident_id → `get_report(incident_id)`.
   - `update_hitl_response(incident_id, response)`: load report; update; re-save.
6. **`ObjectStore` methods**:
   - `upload_raw(incident_id, filename, data)`: `PutObject(Key=f"objects/{incident_id}/{filename}", Body=data)`; return `f"{incident_id}/{filename}"`.
   - `get_raw(object_key)`: `GetObject(Key=f"objects/{object_key}")`['Body'].read(); `NoSuchKey` → raise `IncidentNotFoundError`.

**Verification:** mypy passes.

---

#### Agent: StubEngineer

**Instructions:**
1. Implement `src/aegis_swr/backends/storage/postgres_store.py` — `PostgresStore(RelationalStore)`.
2. Constructor: `__init__(self, settings: StorageSettings)` — store settings, log a warning that this is a stub.
3. All four methods raise `NotImplementedError("PostgresStore is a stub. Implement with SQLAlchemy async in a future phase.")`.
4. Update `backends/storage/__init__.py` with the `create_storage_backends` factory from spec §8.6. Add `StorageSettings.provider` validator.
5. Extend `StorageSettings` in `config/settings.py` with: `provider: str = "filesystem"`, `reports_dir: str = "~/.aegis-swr/reports"`, `objects_dir: str = "~/.aegis-swr/objects"`, `db_path: str = "~/.aegis-swr/reports.db"`, `s3_endpoint_url: str | None = None`.
6. Update `config.yaml` with the new storage keys.

---

#### Agent: StorageTestEngineer

**Instructions:**
1. Write `tests/unit/test_storage_backends.py`. All tests run without any external service.
2. **FilesystemStore** (in `tmp_path`): `test_filesystem_save_get_roundtrip`, `test_filesystem_find_by_hash`, `test_filesystem_find_by_hash_unknown`, `test_filesystem_update_hitl_response`, `test_filesystem_upload_raw_get_raw`, `test_filesystem_path_traversal_blocked`.
3. **SQLiteStore** (`:memory:` db): same six operations as filesystem. Use `SQLiteStore` with `db_path=":memory:"`. Note: `:memory:` creates a new DB per connection — create the store and call all operations within the same `asyncio.to_thread` call, OR use a real temp-file DB (recommended: `tmp_path / "test.db"`).
4. **S3Store** (mocked `boto3.client`): patch `boto3.client` to return a `MagicMock`; configure mock return values for `put_object`, `get_object`, `delete_object`; test all six operations.
5. **PostgresStore**: each of the four methods raises `NotImplementedError`.
6. **Factory**: `provider="filesystem"` → `(FilesystemStore, FilesystemStore)`; `provider="sqlite"` → `(SQLiteStore, None)`; `provider="s3"` → `(S3Store, S3Store)`; `provider="postgres"` → `(PostgresStore, None)`; unknown provider raises `ValueError`.

**Verification:** `pytest tests/unit/test_storage_backends.py -v` passes with zero external calls.

---

## Step 7: CLI & Local Mode

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `ConfigFileEngineer` | `cli/_config.py`, `cli/_logging.py` — JSON config load/save/merge, sensitive filter |
| `FormatterEngineer` | `cli/_formatters.py` — rich panel + json output |
| `CLIEngineer` | `cli/commands.py` — all subcommands, `load_recent` addition to storage ABCs |
| `CLITestEngineer` | `tests/unit/test_cli.py`, `tests/integration/test_e2e_cli.py` |

### Agentic Execution Brief

#### Agent: ConfigFileEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §12.3` — JSON config file schema and merge logic
- `prototype/wincrash_analyzer/config/app_config.py` — prototype `read_config`/`save_config`/`_apply_config` reference
- `prototype/wincrash_analyzer/core/crash_app.py` — `_handle_config`, `_apply_config`, `SensitiveFilter`

**Instructions:**
1. Implement `src/aegis_swr/cli/_config.py`:
   - `DEFAULT_CONFIG_PATH: Path = Path("~/.aegis-swr/analyze.json").expanduser()`
   - `ANALYZE_CONFIG_KEYS: tuple[str, ...]` — tuple of all option names that belong in the JSON file (`dump`, `logs`, `shots`, `sym`, `assume`, `engine`, `ai`, `store`, `store_config`, `output`, `severity`).
   - `load_analyze_config(path: Path | None = None) -> dict[str, Any]` — reads JSON from path (default = `DEFAULT_CONFIG_PATH`); returns `{}` if file absent or malformed (log a warning on parse error).
   - `save_analyze_config(opts: dict[str, Any], path: Path | None = None) -> None` — writes only keys from `ANALYZE_CONFIG_KEYS` to the JSON file; creates parent dirs.
   - `merge_options(config: dict[str, Any], ctx: typer.Context, **cli_values: Any) -> dict[str, Any]` — for each key: if `ctx.get_parameter_source(key) == ParameterSource.COMMAND_LINE`, use CLI value; else use `config.get(key, cli_values[key])`. Return the merged dict.

2. Implement `src/aegis_swr/cli/_logging.py`:
   - `configure_logging(severity: str = "INFO") -> None` — removes default loguru handler; adds a new sink with `sys.stderr`, the given level, and the sensitive filter.
   - `_REDACT_RE: re.Pattern` — compiles a pattern matching `sk-ant-*`, `sk-*`, and `ANTHROPIC_API_KEY=...`/`OPENAI_API_KEY=...` key=value patterns.
   - The loguru sink filter replaces matched patterns with `[REDACTED]`.

**Verification:** mypy passes; `load_analyze_config` on a non-existent file returns `{}`.

---

#### Agent: FormatterEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §12.5` — formatter descriptions
- `prototype/wincrash_analyzer/actions/analyze.py` — rich `Panel` output reference

**Instructions:**
1. Implement `src/aegis_swr/cli/_formatters.py`:
   - `json_formatter(report: RCAReport) -> str`: returns `report.model_dump_json(indent=2)`.
   - `rich_formatter(report: RCAReport) -> None`: prints to `rich.console.Console()`:
     a. A header `Panel` with root cause, confidence level, and faulting module (if present).
     b. A `Table` titled "Agent Dialogue" with columns: Round, Agent, Message, Confidence. One row per `AgentTurn`.
     c. A `Panel` titled "Mitigation" listing `report.mitigation_instructions` (if any).
     d. If `report.probabilistic_fix`: a `Syntax`-highlighted diff block.
     e. If `report.hitl_request`: a warning `Panel` with the HITL question and `requested_data` list.

**Verification:** `rich_formatter` runs without error when called with a minimal `RCAReport`.

---

#### Agent: CLIEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §12` — full CLI spec (flags, JSON config, export, server stub, config commands)
- `prototype/wincrash_analyzer/cli.py` — prototype option definitions and export subcommand
- `_config.py` and `_formatters.py` from ConfigFileEngineer and FormatterEngineer

**Instructions:**

**Part 1 — Add `load_recent` to the storage layer:**
1. Add `@abstractmethod async def load_recent(self, limit: int = 100) -> list[RCAReport]:` to `backends/base.py` `RelationalStore`.
2. Implement in `FilesystemStore`: scan `_reports_dir/*.json` (excluding `_hash_index/`), load each, sort by `created_at` descending, return up to `limit` (0 = all).
3. Implement in `SQLiteStore`: `SELECT report_json FROM reports ORDER BY created_at DESC LIMIT ?`; `LIMIT -1` when `limit == 0`.
4. Implement in `S3Store`: list `reports/` prefix (paginated), `GetObject` each; sort by key name (lexicographic); return up to `limit` (0 = all).
5. `PostgresStore` stub: raise `NotImplementedError`.

**Part 2 — `cli/commands.py`:**
1. Create the Typer app: `app = typer.Typer(name="aegis", help="Aegis SWR — forensics platform")`.
2. Create a `config_app = typer.Typer()` sub-app and register it with `app.add_typer(config_app, name="config")`.
3. Implement `aegis analyze`:
   - All flags from spec §12.2. `--log` and `--shot` are `list[Path]` with `default=[]`.
   - First action: `configure_logging(severity)`.
   - Load JSON config: `config = load_analyze_config(config_path if config_path else None)`.
   - If `--save-config`: build options dict from current values; call `save_analyze_config(opts, config_path)`; print confirmation; `raise typer.Exit()`.
   - Merge: `opts = merge_options(config, ctx, dump=dump, logs=logs, ...)`.
   - Build `IncidentSource` from merged opts.
   - Determine `StorageSettings` from `store` / `store_config` merged opts; call `create_storage_backends`.
   - Override `settings.backends.ai.provider` from `opts["ai"]`; override `settings.backends.debug.engine` from `opts["engine"]`.
   - Instantiate `Orchestrator(settings, ai_backend, debug_backend, relational, object_store)`.
   - Run with spinner: `with Progress(SpinnerColumn(), ...) as p: p.add_task("Analysing..."); report = asyncio.run(orch.run(source))`.
   - If `report.hitl_request`: print HITL panel to stderr; `raise typer.Exit(code=1)`.
   - Output: `json_formatter` / `rich_formatter` / quiet based on `opts["output"]`.
4. Implement `aegis export`:
   - `--store TYPE`, `--store-config VALUE` (source); `--to-store TYPE`, `--to-config VALUE` (destination).
   - Build `StorageSettings` for each; call `create_storage_backends`; get `RelationalStore` from each.
   - `reports = asyncio.run(src_relational.load_recent(limit=0))`; for each: `asyncio.run(dst_relational.save_report(r))`.
   - Print count of exported records.
5. Implement `aegis server`: print the stub message. Accept `--host` and `--port` (ignored for now).
6. Implement `aegis config show`: print `Settings().redacted_dump()` as JSON.
7. Implement `aegis config set KEY VALUE`: read `config.yaml`, set the dotted-path key, write back.

**Key invariants:**
- Never call `asyncio.run()` inside an async context — the CLI is the top-level sync entry point.
- `asyncio.run()` is called exactly once per command invocation.
- `--log` and `--shot` default to `[]` (empty list), not `None`.
- `--save-config` exits before any analysis begins.

**Verification:** mypy passes; `aegis analyze --help` exits 0.

---

#### Agent: CLITestEngineer

**Instructions:**
1. Write `tests/unit/test_cli.py` using `typer.testing.CliRunner` — all tests mock `Orchestrator.run`:

   - `test_analyze_help`: `runner.invoke(app, ["analyze", "--help"])` exits 0; output contains `--dump`, `--config`, `--save-config`.
   - `test_save_config_writes_json`: invoke with `--dump dummy.dmp --ai openai --save-config`; assert the JSON file was written with `"ai": "openai"`.
   - `test_config_file_sets_defaults`: write a JSON file with `{"ai": "openai"}`; invoke with `--config that_file` (no `--ai` flag); assert mock `Orchestrator` was called (config value was picked up).
   - `test_cli_flag_overrides_config_file`: write `{"ai": "openai"}`; invoke with `--config file --ai anthropic`; assert the `ai` in the built settings is `anthropic`.
   - `test_analyze_json_output`: invoke with `--output json`; assert `json.loads(result.stdout)` produces a dict with `"incident_id"` key.
   - `test_analyze_hitl_exits_nonzero`: mock `Orchestrator.run` returns a report with `hitl_request` set; assert exit code is 1.
   - `test_config_show_redacts_secrets`: `aegis config show` output does not contain `sk-ant-` or actual API key value.
   - `test_export_help`: `aegis export --help` exits 0; output contains `--store`, `--to-store`.

2. Write `tests/integration/test_e2e_cli.py`:
   - Patches `Orchestrator.run` at `aegis_swr.core.orchestrator.Orchestrator.run` to return a pre-built `RCAReport`.
   - Creates a real temp `.dmp` file (4 bytes MDMP magic).
   - Invokes `aegis analyze --dump {tmp_dump} --output json --store filesystem --store-config {tmp_dir}`.
   - Asserts exit code 0.
   - Asserts `json.loads(result.stdout)["root_cause"]` matches the mocked report.
   - Second invocation: `--output rich` — asserts stdout contains the root cause text.

**Verification:** `pytest tests/unit/test_cli.py tests/integration/test_e2e_cli.py -v` passes.

---

## Step 8: REST API Layer

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `APIEngineer` | FastAPI app, all routes, SSE streaming |
| `SecurityEngineer` | Auth middleware, rate limiting |
| `APITestEngineer` | Integration tests with httpx |

### Agentic Execution Brief

#### Agent: APIEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §9` — all endpoint specifications
- `cli/commands.py` from Step 7 — `aegis server` stub to complete

**Instructions:**
1. Implement `src/aegis_swr/api/app.py` — `create_app(settings: Settings) -> FastAPI`.
2. Implement `api/routes/incidents.py`:
   - `POST /v1/incidents/analyze`: validate multipart form; upload to `ObjectStore`; create DB record; start `Orchestrator.run()` as `BackgroundTasks`; return 202.
   - `POST /v1/incidents/{id}/continue`: HITL continuation endpoint.
   - `GET /v1/incidents/`: paginated list with filters.
3. Implement `api/routes/stream.py`:
   - Use an `asyncio.Queue` registry: `incident_event_queues: dict[str, asyncio.Queue]`.
   - `Orchestrator.run_streaming()` pushes events to the queue.
   - SSE endpoint pulls from queue and formats as `data: {json}\n\nevent: {type}\n\n`.
   - Heartbeat every 15 s using `asyncio.sleep(15)` in a concurrent task.
4. Implement `api/routes/reports.py`: `GET /v1/incidents/{id}/report`.
5. Add `GET /health` endpoint (no auth) returning `{ "status": "ok" }`.
6. Complete the `aegis server` stub from Step 7: replace the placeholder message with `uvicorn.run(create_app(settings), host=..., port=..., reload=...)`.

---

#### Agent: SecurityEngineer

**Instructions:**
1. Implement `api/middleware/auth.py` — `AuthMiddleware(BaseHTTPMiddleware)`. Add `api_keys` table to Alembic migration (columns: `key_hash TEXT`, `org_slug TEXT`, `created_at TIMESTAMPTZ`). Hash with `bcrypt.hashpw`.
2. Implement `api/middleware/rate_limit.py` using `slowapi`.
3. Implement `SensitiveFilter` in `src/aegis_swr/core/logging.py` (ported from prototype's pattern): attach to `loguru` logger; redacts `sk-ant-*`, `sk-*`, and all API key patterns.

---

#### Agent: APITestEngineer

**Instructions:**
1. Write `tests/integration/test_api.py` using `httpx.AsyncClient(app=app)`:
   - `test_analyze_returns_202`: valid multipart form → 202 with `incident_id`.
   - `test_report_returns_202_while_analyzing`: status not complete → 202.
   - `test_report_returns_200_when_complete`: mock orchestrator completes → 200 + full report.
   - `test_sse_stream_delivers_events`: connect to stream; mock orchestrator pushes 2 turns + complete → assert all received in order.
   - `test_auth_blocks_missing_key`: no `X-Aegis-API-Key` header → 401.
   - `test_health_no_auth_required`: `GET /health` with no header → 200.

---

## Step 9: Secure Code Sandbox

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `SandboxEngineer` | `sandbox/executor.py`, `sandbox/validators.py`, Dockerfiles |
| `SandboxTestEngineer` | Unit tests with mocked subprocess |

### Agentic Execution Brief

#### Agent: SandboxEngineer

**Inputs provided:**
- `PRODUCTION_DESIGN_SPEC.md §10` — full sandbox architecture, Docker flags, validation flow

**Instructions:**
1. Implement `src/aegis_swr/sandbox/executor.py` — `SandboxExecutor(settings: SandboxSettings)`.
2. `async def validate(patch: str, language: str) -> ValidationResult`:
   - Write patch to a secure temp file (use `tempfile.NamedTemporaryFile` inside the configured temp dir; validate the resolved path stays within the temp dir to prevent path traversal).
   - Build Docker command with all security flags from spec: `--rm`, `--network=none`, `--read-only`, `--tmpfs /tmp:rw,exec,size=50m`, `--memory={memory_mb}m`, `--cpus={cpu_limit}`, `--cap-drop ALL`.
   - Run with `asyncio.create_subprocess_exec` with `timeout`.
   - Parse exit code and stdout/stderr into `ValidationResult`.
3. Implement graceful degradation: if Docker binary not found → `ValidationResult(passed=None, compiler_output="Sandbox unavailable")`.
4. Write `sandbox/Dockerfile.cpp`, `sandbox/Dockerfile.python` (minimal Alpine + build tools only).
5. Add `Makefile` target `build-sandbox-images`.

---

#### Agent: SandboxTestEngineer

**Instructions:**
1. Write `tests/unit/test_sandbox.py`:
   - `test_valid_cpp_patch`: mock `asyncio.create_subprocess_exec` returning exit 0 → `passed=True`.
   - `test_invalid_patch_exit_nonzero`: exit 1 + compiler error output → `passed=False`, `compiler_output` non-empty.
   - `test_docker_unavailable`: mock `FileNotFoundError` on subprocess → `passed=None`.
   - `test_path_traversal_blocked`: patch content containing `../../../etc/passwd` in a filename used for output → path stays within temp dir.

---

## Step 10: Testing & Hardening

### Agent Matrix

| Agent Role | Responsibility |
|---|---|
| `GroundTruthEngineer` | Creates 10 ground truth incidents + `eval_runner.py` |
| `HardeningEngineer` | Docker Compose, Makefile targets, security checklist |
| `DocumentationEngineer` | Updates `docs/README.md` registry |

### Agentic Execution Brief

#### Agent: GroundTruthEngineer

**Inputs provided:**
- Prototype test assets in `prototype/tests/` (real dump files and log fixtures)
- GAP_ANALYSIS.md — known failure modes to include as ground truth cases

**Instructions:**
1. Create `tests/ground_truth/incidents/` with at least 10 subdirectories.
2. For each incident, create:
   - `inputs/` directory with appropriate files (dump, log, screenshot where applicable).
   - `expected_output.json` with `fault_class`, `faulting_module`, `root_cause_keywords` list.
   - `README.md` with human description of true root cause and how it was determined.
3. Coverage must include: access violation, stack overflow, deadlock, resource exhaustion, log-only incident (no dump).
4. Write `tests/ground_truth/eval_runner.py`:
   - Iterates all incident directories.
   - Runs `Orchestrator.run()` for each with real AI backend.
   - Scores PASS/PARTIAL/FAIL.
   - Asserts PASS rate ≥ 80% with a clear failure message listing each failing incident.
   - Prints token usage table per incident.

---

#### Agent: HardeningEngineer

**Inputs provided:**
- All completed source files

**Instructions:**
1. Create `docker-compose.yml` for local production stack: `aegis-api`, `postgres:16-alpine`, `minio`, `qdrant/qdrant`. Include health checks and depends_on conditions.
2. Create `docker-compose.test.yml` for CI integration tests: `postgres`, `minio` only (no `aegis-api`).
3. Create `tests/benchmarks/token_budget.py`: runs Data Adapter on 5 canonical input pairs; tokenizes output with `tiktoken`; asserts average ≤ 12,000 tokens.
4. Complete all Makefile targets: `install`, `lint`, `typecheck`, `test`, `test-integration`, `test-ground-truth`, `benchmark-tokens`, `build-sandbox-images`, `up`, `down`, `migrate`.
5. Review all `subprocess.run()` calls — verify list-form args (no `shell=True` anywhere). Report any violations.
6. Verify all file path operations use `Path.resolve()` and stay within configured root directories.

---

#### Agent: DocumentationEngineer

**Instructions:**
1. Update `docs/README.md` to add a new `specs/` section to the documentation registry table with entries for all three new spec files.
2. Update the root `README.md` Quick Start section to reflect the `aegis-swr` package name and the `src/aegis_swr/` structure.
3. Verify all internal links in all `docs/` files are still valid after the new `specs/` directory is added.

---

## Cross-Cutting Agent Guidelines

These rules apply to every agent in every step:

1. **Schemas are the source of truth.** Always import from `aegis_swr.core.schemas`. Never redefine a model that already exists.
2. **No shell=True.** All `subprocess.run()` and `subprocess.Popen()` calls use list-form arguments. This is a security invariant, not a style preference.
3. **Prompt caching is mandatory.** Every `AIAPIBackend.generate()` call MUST include `cache_control: {"type": "ephemeral"}` on the system prompt block. Never submit a system prompt without it.
4. **Fail open on optional features.** Presidio (PII scrubbing), pytesseract (OCR), and sandbox (code validation) are all optional. When their libraries are absent or their services are unavailable: log a warning, continue the pipeline with graceful degradation. Never fail the analysis because an enhancement is missing.
5. **Hash before analyze.** The dump SHA-256 hash MUST be computed before calling any backend. The deduplication check (find_by_hash) MUST happen before starting any analysis. This is the fix for prototype Gap 4.
6. **Type annotations on all public APIs.** All public functions and methods must have complete type annotations. `mypy src/` must pass after every step.
7. **Tests before next step.** Each step ends with a `pytest` verification gate. The next step does not begin until the current step's tests pass.
