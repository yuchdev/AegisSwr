# Aegis SWR - Production Design Specification

**Version:** 1.0  
**Status:** Approved for Implementation  
**Package:** `aegis-swr` (PyPI/Poetry name); Python module root: `aegis_swr`  
**Source root:** `src/aegis_swr/`

---

## 1. Product Summary

Aegis SWR (Synthetic War Room) is a production forensics platform that converts raw incident telemetry - crash dumps, log files, screenshots, metric spikes - into a structured **Investigator's Rationale (IR)**: a complete audit trail of the multi-agent debate that led to a root-cause conclusion.

The distinguishing product characteristic is the **Synthetic War Room**: instead of a single LLM call that returns one answer, the platform instantiates four specialized AI agents (OS Kernel, Code Analyst, Log Historian, Skeptic) that run a controlled debate. The debate transcript, discarded hypotheses, confidence scores, and final consensus are all persisted and surfaced as structured output.

This specification covers the full design of the production package: module layout, data models, all five backend interfaces, the Data Adapter preprocessing pipeline, the MAS state machine, the REST/SSE API, the secure code sandbox, and the configuration system.

---

## 2. Target Directory Structure

```
src/aegis_swr/
├── __init__.py
├── py.typed
│
├── core/
│   ├── __init__.py
│   ├── schemas.py            # All Pydantic models and TypedDicts
│   ├── fault_codes.py        # Platform-agnostic FaultClass enum
│   ├── orchestrator.py       # LangGraph MAS state-graph engine
│   ├── consensus.py          # Weighted consensus score calculator
│   └── data_adapter.py       # Token-dense incident brief producer
│
├── agents/
│   ├── __init__.py
│   ├── base.py               # Abstract BaseAgent
│   ├── os_kernel.py          # OS / environment specialist
│   ├── code_analyst.py       # Code logic / architecture analyst
│   ├── log_historian.py      # Historical pattern correlator
│   └── skeptic.py            # Consensus challenger / moderator
│
├── backends/
│   ├── __init__.py
│   ├── base.py               # All abstract backend interfaces (ABCs)
│   ├── ai/
│   │   ├── __init__.py       # Factory: create_ai_backend()
│   │   ├── anthropic_provider.py
│   │   └── openai_provider.py
│   ├── debug/
│   │   ├── __init__.py       # Factory: create_debug_backend() - platform-detected
│   │   ├── cdb_worker.py     # Windows: cdb.exe
│   │   ├── gdb_worker.py     # Linux: gdb
│   │   └── lldb_worker.py    # macOS: lldb
│   ├── storage/
│   │   ├── __init__.py       # Factory: create_storage_backends()
│   │   ├── postgres_store.py # Relational - incidents, rationale, dialogue
│   │   ├── s3_store.py       # Object - raw .dmp, .log, .png files
│   │   └── qdrant_store.py   # Vector - semantic incident history
│   ├── log/
│   │   ├── __init__.py       # Factory: create_log_backend()
│   │   ├── file_adapter.py   # Local .log / .txt files
│   │   ├── elk_adapter.py    # Elasticsearch / ELK stack (deferred)
│   │   └── fluent_adapter.py # Fluentd / Fluent Bit (stub)
│   └── code/
│       ├── __init__.py       # Factory: create_code_backend()
│       ├── git_adapter.py    # Git diff / blame / commit history
│       ├── filesystem_adapter.py  # Plain source tree, no VCS (graceful degradation)
│       └── pdb_adapter.py    # Windows PDB SrcSrv → exact build revision (Windows-only)
│
├── sandbox/
│   ├── __init__.py
│   ├── executor.py           # Docker/gVisor sandbox runner
│   └── validators.py         # AST, compile, lint integration
│
├── api/
│   ├── __init__.py
│   ├── app.py                # FastAPI application factory
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── incidents.py      # POST /v1/incidents/analyze
│   │   ├── stream.py         # GET /v1/incidents/{id}/stream (SSE)
│   │   └── reports.py        # GET /v1/incidents/{id}/report
│   └── middleware/
│       ├── __init__.py
│       ├── auth.py           # API key / JWT auth
│       └── rate_limit.py
│
├── cli/
│   ├── __init__.py
│   └── commands.py           # Typer CLI - analyze, server, config
│
└── config/
    ├── __init__.py
    └── settings.py           # Pydantic Settings - reads config.yaml + env vars
```

**Project configuration** (repository root):
```
pyproject.toml        # Poetry project: name="aegis-swr", packages=[{include="aegis_swr",from="src"}]
config.yaml           # Default runtime configuration
.env.example          # Required environment variable template
tests/
├── unit/
├── integration/
└── ground_truth/     # Historical incidents with known root causes
```

---

## 3. Package Configuration (`pyproject.toml`)

```toml
[tool.poetry]
name = "aegis-swr"
version = "1.0.0"
description = "Production forensics platform: multi-agent crash and incident analysis"
authors = ["Yurii Cherkasov <yurii.cherkasov@gloriumtech.com>"]
packages = [{ include = "aegis_swr", from = "src" }]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.115"
uvicorn = { version = "^0.32", extras = ["standard"] }
typer = { version = "^0.13", extras = ["all"] }
pydantic = "^2.9"
pydantic-settings = "^2.5"
langgraph = "^0.2"
anthropic = "^0.40"
openai = "^1.55"
sqlalchemy = { version = "^2.0", extras = ["asyncio"] }
asyncpg = "^0.30"
boto3 = "^1.35"
qdrant-client = "^1.12"
loguru = "^0.7"
drain3 = "^0.9"
pytesseract = { version = "^0.3", optional = true }
easyocr = { version = "^1.7", optional = true }
spacy = { version = "^3.8", optional = true }
presidio-analyzer = { version = "^2.2", optional = true }
presidio-anonymizer = { version = "^2.2", optional = true }
httpx = "^0.27"
pyyaml = "^6.0"

[tool.poetry.extras]
ocr = ["pytesseract", "easyocr"]
pii = ["spacy", "presidio-analyzer", "presidio-anonymizer"]
all = ["pytesseract", "easyocr", "spacy", "presidio-analyzer", "presidio-anonymizer"]

[tool.poetry.scripts]
aegis = "aegis_swr.cli.commands:app"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.24"
pytest-cov = "^6.0"
httpx = "^0.27"
ruff = "^0.8"
mypy = "^1.13"
```

---

## 4. Core Data Schemas (`core/schemas.py`)

All inter-component data structures use **Pydantic v2** models for validation and JSON serialization. The central types are:

### 4.1 Incident Source

```python
class IncidentMode(str, Enum):
    CRASH_DUMP      = "crash_dump"      # Binary .dmp/.core file provided
    LOG_FORENSICS   = "log_forensics"   # Log files only, no binary dump
    LIVE_PROCESS    = "live_process"    # PID or service name
    TELEMETRY_ANOMALY = "telemetry_anomaly"  # Metric threshold breach

class DumpFormat(str, Enum):
    WINDOWS_MINIDUMP = "windows_minidump"   # .dmp - Windows MiniDumpWriteDump()
    LINUX_CORE       = "linux_core"         # .core - ELF core dump
    APPLE_CRASHREPORT = "apple_crashreport" # .ips / .crash - Apple CrashReporter
    BREAKPAD         = "breakpad"           # .dmp - Google Breakpad format

class IncidentSource(BaseModel):
    mode: IncidentMode
    incident_timestamp: datetime | None = None  # UTC - anchor for temporal windowing
    dump_path: Path | None = None
    dump_format: DumpFormat | None = None
    dump_hash: str | None = None                # SHA-256, computed before any backend call
    log_paths: list[Path] = []
    screenshot_paths: list[Path] = []
    network_capture_paths: list[Path] = []      # .pcap captures - metadata shown in DEBUG evidence
    symbol_path: Path | None = None
    user_assumption: str | None = None          # Capped to 500 tokens by Data Adapter
    metadata: dict[str, str] = {}               # repo tags, environment, application type
```

### 4.2 FaultClass Enum (`core/fault_codes.py`)

```python
class FaultClass(str, Enum):
    MEMORY_ACCESS_VIOLATION = "memory_access_violation"
    NULL_POINTER_DEREFERENCE = "null_pointer_dereference"
    USE_AFTER_FREE           = "use_after_free"
    STACK_OVERFLOW           = "stack_overflow"
    INTEGER_DIVIDE_BY_ZERO   = "integer_divide_by_zero"
    DEADLOCK                 = "deadlock"
    ASSERTION_FAILURE        = "assertion_failure"
    UNHANDLED_EXCEPTION      = "unhandled_exception"
    RESOURCE_EXHAUSTION      = "resource_exhaustion"
    UNKNOWN                  = "unknown"
```

Each `DebugBackend` maps its platform-native fault indicator to `FaultClass`. The agent prompts use `FaultClass` names - never raw hex codes or signal numbers.

**Platform mapping table** (implemented in `fault_codes.py`):

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

### 4.3 Debug Extraction Result

```python
class StackFrame(BaseModel):
    frame_number: int
    module: str | None          # Resolved module name
    function: str | None        # Resolved function name (None if no symbols)
    source_file: str | None
    source_line: int | None
    instruction_address: str    # Hex address always preserved

class DebugExtractionResult(BaseModel):
    fault_class: FaultClass
    exception_code_raw: str     # Native hex or signal string
    exception_address: str      # Instruction pointer (RIP/PC/LR)
    faulting_module: str | None
    faulting_function: str | None
    stack_frames: list[StackFrame]   # Top 20 frames default
    debug_timestamp: datetime | None
    symbol_resolution_score: float   # 0.0–1.0: fraction of resolved frames
    raw_text_excerpt: str            # ≤8,000 chars after Data Adapter noise filter
```

### 4.4 Agent Output Types

```python
class ConfidenceLevel(str, Enum):
    HIGH   = "high"    # ≥0.80
    MEDIUM = "medium"  # 0.50–0.79
    LOW    = "low"     # <0.50

class Hypothesis(BaseModel):
    root_cause: str
    faulting_module: str | None
    faulting_function: str | None
    evidence: list[str]
    confidence: float               # 0.0–1.0

class AgentTurn(BaseModel):
    agent: str                      # "OS Kernel Agent" etc.
    turn_number: int
    message: str
    hypotheses: list[Hypothesis]
    confidence_score: float         # Highest confidence across hypotheses
    timestamp: datetime

class SkepticVerdict(BaseModel):
    confirmed: bool
    confidence: ConfidenceLevel
    challenges: list[str]
    corrections: list[str]          # Injected into next round if confirmed=False

class HITLRequest(BaseModel):
    question: str
    context_summary: str
    requested_data: list[str]       # What the user should provide
```

### 4.5 Investigator's Rationale (Final Output)

```python
class RCAReport(BaseModel):
    incident_id: UUID
    created_at: datetime
    mode: IncidentMode
    dump_hash: str | None
    symbol_resolution_score: float | None

    # Primary conclusion
    root_cause: str
    faulting_module: str | None
    faulting_function: str | None
    confidence_score: float
    confidence_level: ConfidenceLevel

    # Full reasoning trail
    primary_hypothesis: Hypothesis
    alternative_hypotheses: list[Hypothesis]    # Considered but rejected
    skeptic_challenges: list[str]
    agent_dialogue: list[AgentTurn]             # Complete turn-by-turn log
    consensus_rounds: int

    # Actionable outputs
    mitigation_instructions: list[str]
    probabilistic_fix: str | None               # Unified diff format
    fix_confidence: float | None
    fix_validation_result: str | None           # Sandbox compile result

    # Human-in-the-loop
    hitl_request: HITLRequest | None            # Set when confidence < 0.50

    # Token accounting
    total_input_tokens: int
    total_output_tokens: int
```

### 4.6 MAS State Object (LangGraph)

```python
class InvestigationState(TypedDict):
    incident_id:          str
    incident_brief:       dict          # Structured output of Data Adapter
    source:               dict          # Serialized IncidentSource
    discussion_history:   list[dict]    # List of AgentTurn dicts
    current_agent:        str
    round_number:         int           # 1-based; max = settings.max_debate_rounds
    consensus_score:      float
    is_converged:         bool
    primary_hypothesis:   dict | None
    hitl_pending:         bool
    token_tracker:        dict          # {input: int, output: int}
    error:                str | None
```

### 4.7 Code & Log Backend Types

Records returned by the `CodeBackend` (§6.5) and consumed by the Data Adapter's
code-history stage (§5.1 Stage 8). They are plain Pydantic models so they
serialize cleanly into the `IncidentBrief.code_history` block.

```python
class CommitRecord(BaseModel):
    sha: str                        # Full or short SHA; "fs:" pseudo-id for FilesystemCodeAdapter
    author: str                     # "name <email>"; "unknown" when VCS metadata is absent
    authored_at: datetime           # UTC; file mtime for FilesystemCodeAdapter
    message: str                    # First line / subject; "" when unavailable
    changed_files: list[str]        # Repo-relative paths

class BlameRecord(BaseModel):
    line_number: int                # 1-based line in the file
    sha: str                        # Commit that last touched the line; "fs:" when no VCS
    author: str                     # "unknown" when no VCS
    authored_at: datetime | None    # None when no VCS metadata
    line_content: str               # Source text of the line
```

`LogBackend` (§6.4) returns plain `list[str]` log lines, so it needs no
dedicated record type; the lines flow straight into the Stage 4 log pipeline.

---

## 5. Data Adapter Layer (`core/data_adapter.py`)

The Data Adapter is a **non-LLM preprocessing pipeline** that converts raw telemetry into a token-dense incident brief. It runs synchronously before any agent is invoked.

### 5.1 Pipeline Stages (in order)

```
IncidentSource
    │
    ▼ Stage 1: Source Validation & Hash Computation
    │   - Verify file existence and extension / magic bytes
    │   - Compute dump_hash = SHA-256(dump_path) before any backend call
    │   - Determine DumpFormat by reading magic bytes (not file extension)
    │
    ▼ Stage 2: Dump Extraction (Debug Backend call)
    │   - Invoke platform-selected DebugBackend.extract()
    │   - Returns DebugExtractionResult with structured fields
    │   - Compute symbol_resolution_score
    │   - If score < 0.50: prepend [LOW SYMBOL COVERAGE: {score:.0%}] to brief
    │
    ▼ Stage 3: Global Noise Pre-Filter (text normalization)
    │   - Strip all DBGHELP noise lines:  re.sub(r"DBGHELP:.*?file not found\n", "", text)
    │   - Replace fill patterns: 0xCCCCCCCC, 0xDDDDDDDD, 0xFEEEFEEE → <fill>
    │   - Drop DLL load list (lines between "*** WARNING:" and "EXCEPTION_ANALYSIS:")
    │   - Apply 8,000-char head+tail truncation (4,000 / 4,000) to remaining text
    │
    ▼ Stage 4: Log Processing
    │   - Source lines from two places, then merge into one stream:
    │       (a) each local log path in IncidentSource.log_paths (file-based), and
    │       (b) if a LogBackend is configured AND a service name + incident_timestamp
    │           are available: LogBackend.query_window(service, t−window, t+window,
    │           severity_levels) - pulls lines from the log source (file/fluent/…)
    │   - For each line: apply temporal window ±30 s around incident_timestamp
    │   - Run Drain3 log clustering on filtered lines
    │   - Deduplicate: heartbeat lines repeated >3 times become "msg (×N)"
    │   - Severity isolation: retain FATAL/CRITICAL/ERROR/WARNING; drop INFO/DEBUG
    │     unless they appear within ±5 s of the incident timestamp
    │   - Enforce 2,000-token budget on log block total
    │
    ▼ Stage 5: Screenshot OCR (optional)
    │   - pytesseract / EasyOCR → extract raw text
    │   - Parse into UIContext { error_message, visible_timestamp, ui_elements }
    │   - Discard OCR output if confidence < 0.60
    │
    ▼ Stage 6: PII Scrubbing (always runs, before any text leaves the adapter)
    │   - Apply Presidio Analyzer with recognizers: EMAIL, PHONE, CREDIT_CARD,
    │     CRYPTO, US_SSN, IP_ADDRESS, URL, AWS_KEY, DB_CONNECTION_STRING
    │   - Replace each entity with a stable hash token: [REDACTED_EMAIL_1]
    │   - Audit log of scrubbed entities is stored separately (never sent to LLM)
    │
    ▼ Stage 7: User Assumption Enforcement
    │   - Tokenize user_assumption; truncate to 500 tokens with warning
    │
    ▼ Stage 8: Code History Query (if CodeBackend configured)
    │   - CodeBackend.get_commits_before(repo_path, incident_timestamp, window_hours=2)
    │     - git history for GitCodeAdapter; recently-modified files for FilesystemCodeAdapter
    │   - Extract changed files, authors, commit messages - top 5 by proximity
    │
    ▼ Stage 9: Assemble Incident Brief (dict → JSON-serializable)
    │
    └──► IncidentBrief (passed to MAS as incident_brief field)
```

### 5.2 IncidentBrief Structure

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
    {"frame": 0, "module": "db_writer.dll", "function": "db_writer::serialize", "line": 142},
    "..."
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

### 5.3 Conditional History Injection (Log Historian Agent trigger)

The Log Historian Agent queries the Qdrant vector store for semantically similar historical incidents. Injection is conditional:
- Inject if `faulting_module` appears in ≥2 of the last 10 stored incidents, **or**
- Inject if `fault_class` matches ≥3 of the last 10 stored incidents.
- Otherwise omit (saves ~300 input tokens on non-recurring crashes).

The rule is implemented as the pure helper `DataAdapter.should_inject_history(brief, recent)`; the Log Historian Agent (Phase 5) supplies the `recent` list from the vector store.

### 5.4 Implementation Notes (as built in Phase 2)

Two refinements were made while implementing the Data Adapter; both are now the authoritative behavior:

1. **`IncidentBrief` is a Pydantic model** (`core/schemas.py`), not a bare dict. `DataAdapter.process()` returns an `IncidentBrief`; the orchestrator serializes it with `model_dump(mode="json")` into `InvestigationState["incident_brief"]`. The JSON shape in §5.2 is unchanged.

2. **PII scrubbing always runs via a deterministic regex baseline**, with Presidio NER as an optional enhancement layered on top when the `pii` extra is installed. This reconciles "PII scrubbing always runs" (a security invariant) with "fail open on optional features" - emails, IPv4 addresses, AWS keys, credit-card numbers, and DB connection strings are always scrubbed even without Presidio. The PII substitution map is **never** placed in the `IncidentBrief` (it would carry the original PII into agent prompts); instead it is exposed via `DataAdapter.last_pii_substitution_map` immediately after `process()` returns, for the orchestrator to persist out-of-band (encrypted) per §13.1.

3. **`process()` signature**: `async def process(source: IncidentSource, debug_backend: DebugBackend | None = None, code_backend: CodeBackend | None = None, log_backend: LogBackend | None = None) -> IncidentBrief`. All three backends are optional so the adapter is usable in log-only mode and before Phase 4/later backends exist. `code_backend` drives Stage 8 (§6.5); `log_backend` is queried in Stage 4 (§6.4) and its lines are merged with the file-based logs before clustering. The reusable noise filter is the module-level function `apply_noise_filter(text)`, which Phase 4 debug backends import directly.

4. **Token counting** uses `tiktoken` (`cl100k_base`) with an offline-safe `chars/4` fallback (`core/tokens.py`), so token budgeting never breaks in air-gapped environments.

---

## 6. Backend Interfaces (`backends/base.py`)

All five backend interface ABCs are defined here using Python's `abc` module.

### 6.1 AIAPIBackend

```python
class AIAPIBackend(ABC):
    model_name: str

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        output_schema: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        """
        Returns a validated Pydantic instance if output_schema provided,
        otherwise returns raw string. Raises AIOutputValidationError on
        schema mismatch after one retry with correction prompt.
        Uses provider prompt-caching on the system_prompt block.
        """

    @abstractmethod
    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Token-by-token SSE stream for live UI display."""
```

**Implementation notes for `anthropic_provider.py`:**
- Use `cache_control: {"type": "ephemeral"}` on the system prompt block (prompt caching).
- Use `response_format` structured output via `tools` with `input_schema` matching the Pydantic model's JSON schema.
- Model default: `claude-sonnet-4-6` (configurable in `config.yaml`).
- Retry once with correction prompt on `AIOutputValidationError`.

**Implementation notes for `openai_provider.py`:**
- Use `response_format={"type": "json_schema", "json_schema": {...}}` for structured output.
- Use `stream=True` + `stream_options={"include_usage": True}` for token tracking.

#### 6.1.1 As-built notes (Phase 3)

These are the authoritative behaviors of the implemented AI backends:

1. **Shared base class.** Both providers extend `_BaseAIBackend` (`backends/ai/_base.py`), which owns the provider-neutral logic: structured-output validation, the one-shot correction retry, and token accounting. Each provider implements only `_invoke()` (one API round-trip) and `stream()`. This guarantees identical retry/validation semantics across providers.

2. **`stream()` is a plain `def` returning `AsyncGenerator`** in the ABC (not `async def`), so concrete async-generator implementations type-check cleanly. Call it without `await`: `async for token in backend.stream(...)`.

3. **Token tracking via `last_usage`.** `generate()` does not receive the `InvestigationState`, so it cannot mutate `token_tracker` directly. Instead each backend exposes `backend.last_usage` (`{"input_tokens", "output_tokens"}`) reflecting the most recent `generate()` call, **accumulated across the retry**. The calling agent (Phase 5) reads `last_usage` immediately after `await` and adds it to `state["token_tracker"]`.

4. **Correction retry.** On a `ValidationError`/`JSONDecodeError`, the base appends an `assistant` turn (the invalid output) plus a `user` turn naming the schema and the validation errors, then re-invokes once. A second failure raises `AIOutputValidationError`.

5. **OpenAI strict schema.** `_to_openai_strict_schema()` adapts the Pydantic JSON schema to OpenAI strict rules - recursively setting `additionalProperties: false`, listing all properties as `required`, and stripping `default`. Anthropic uses the raw `model_json_schema()` as the tool `input_schema`.

6. **SDK clients are typed as `Any`.** Each provider stores `self._client: Any = anthropic.AsyncAnthropic()` / `openai.AsyncOpenAI()` to avoid coupling to the SDKs' internal `TypedDict` parameter types under `mypy --strict`. API keys are read from the environment by the SDKs (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`).

7. **Provider-aware model resolution.** `model` in `AISettings` defaults to an Anthropic name, so switching only the provider (e.g. CLI `--ai openai`) would otherwise send an Anthropic model id to OpenAI. `AISettings.resolved_model` substitutes the provider's default (`gpt-5.4` for OpenAI, `claude-sonnet-4-6` for Anthropic) **only when the configured model does not belong to the selected provider**; an explicit, provider-matching model is always respected. `_BaseAIBackend` uses `resolved_model`, so the CLI, API, and orchestrator all get this for free.

8. **OpenAI reasoning-model API contract.** gpt-5-class / o-series models reject `max_tokens` and any non-default `temperature`; they require `max_completion_tokens`. `OpenAIBackend._completion_kwargs()` detects a reasoning model by name prefix and, for those, sends `max_completion_tokens` (floored at 16 000 so internal reasoning tokens don't starve the structured answer) and omits `temperature`; non-reasoning models keep `max_tokens` + `temperature`.

9. **OpenAI client resilience.** A multi-agent investigation issues many sequential calls (up to `4 agents × max_debate_rounds`), so the OpenAI client is constructed with `timeout=300s` and `max_retries=4` (SDK exponential backoff on timeouts / 429 / 5xx). This prevents one transient `APITimeoutError` - observed at the `skeptic_node` during real-dump runs - from aborting the whole graph.

### 6.2 DebugBackend

```python
class DebugBackend(ABC):
    SUPPORTED_FORMATS: ClassVar[list[DumpFormat]]
    SUPPORTED_PLATFORMS: ClassVar[list[str]]  # "Windows", "Linux", "Darwin"

    @abstractmethod
    def extract(
        self,
        source: IncidentSource,
        symbol_path: Path | None,
    ) -> DebugExtractionResult:
        """
        Opens dump/core file using native debugger binary.
        Maps all native fault codes to FaultClass enum.
        Runs in a subprocess with RAII context manager.
        Timeout: 300 s (configurable).
        """

    @abstractmethod
    def _build_command_sequence(self, source: IncidentSource, symbol_path: Path) -> list[str]:
        """Returns the debugger command arguments list for subprocess.run()."""
```

**Factory** (`backends/debug/__init__.py`):
```python
def create_debug_backend(config: DebugConfig) -> DebugBackend:
    platform = sys.platform
    if platform == "win32":   return CdbBackend(config)
    if platform == "linux":   return GdbBackend(config)
    if platform == "darwin":  return LldbBackend(config)
    raise PlatformNotSupportedError(platform)
```

**Symbol path defaults** (cross-platform via `pathlib`):
- Windows: `%LOCALAPPDATA%\AegisSWR\symbols`
- Linux/macOS: `~/.cache/aegis-swr/symbols`
- Override with `AEGIS_SYMBOL_CACHE` environment variable.

> **PDB dual-use note.** A `.pdb` (Program Database) file contains two distinct
> information classes used at *different pipeline stages*:
>
> | Class | Used by | Stage | Mechanism |
> |---|---|---|---|
> | Address → symbol (function name, source line, type) | **Debug Backend** | Stage 2 | `cdb.exe -y {symbol_path}` resolves frames |
> | Source Server (SrcSrv) stream → exact VCS revision built | **Code Backend §6.5.4** | Stage 8 | `pdbstr.exe -r -s:srcsrv` extracts build provenance |
>
> Both backends reference the same `.pdb` file; this is intentional and architecturally
> correct - the same file is read for different purposes. The `PdbCodeAdapter` (§6.5.4)
> is therefore not a Debug Backend concern and does not replace symbol resolution here.

#### 6.2.1 As-built notes (Phase 4)

Authoritative behaviors of the implemented debug backends:

1. **Shared base class.** All three workers extend `_BaseDebugBackend` (`backends/debug/_base.py`), which owns the `extract()` template method: `_validate(source)` → `_build_command_sequence()` → `_run()` (RAII subprocess with timeout) → `_parse()`. Each worker implements only `_build_command_sequence` and `_parse`.

2. **Errors.** A missing/absent dump raises `DebugExtractionError`; a missing debugger binary (`FileNotFoundError`) raises `PlatformNotSupportedError`; a timeout raises `DebugExtractionError`. (`DebugExtractionError` was added to `core/exceptions.py`.)

3. **`extract` is synchronous** (per the ABC) and the Data Adapter calls it inline. All `subprocess.run` calls use list-form argv - never `shell=True`.

4. **Fault mapping.** CDB maps the fault-code NTSTATUS hex via `map_windows_ntstatus`; GDB maps the `signal SIG*` name via a local name→number table + `map_linux_signal`; LLDB maps the `stop reason = EXC_*` name via a local name→code table + `map_macos_exception`. Unmapped indicators yield `FaultClass.UNKNOWN`.

   **CDB fault-code extraction (multi-key).** `!analyze -v` reports the fault code under different keys depending on the crash. `_extract_exception_code()` tries, in order: `EXCEPTION_CODE: (NTSTATUS|HRESULT) 0x…`, `ERROR_CODE: (NTSTATUS|HRESULT) 0x…`, `EXCEPTION_CODE_STR:  c0000005`, and `ExceptionCode: c0000005`, normalising to lowercase `0x…`. This was a defect ported from the prototype, which matched only `EXCEPTION_CODE:` and silently yielded `0x0 → FaultClass.UNKNOWN` for real `NULL_POINTER_WRITE` dumps (which report `ERROR_CODE` / `EXCEPTION_CODE_STR` instead). Surfaced during a real-dump reproduction run where the OS Kernel agent noted the brief listed `exception_code_raw` as `0x0` while the excerpt clearly showed `0xc0000005`.

5. **Parsers are module-level functions** (`parse_cdb_frames`, `parse_gdb_frames`, `parse_lldb_frames`) so they are unit-testable in isolation. Each produces `StackFrame`s; `symbol_resolution_score = (frames with a resolved function) / (total frames)`. `apply_noise_filter` (imported from `core/data_adapter`) is applied to `raw_text_excerpt`.

6. **Factory.** `create_debug_backend(settings, platform=None)` takes an optional `sys.platform`-style override (used by tests); it defaults to the running platform. `settings` is the `DebugSettings` section (the spec's `DebugConfig`).

#### 6.2.2 WinDbg JavaScript Backend (`backends/debug/windbg_js_worker.py`)

The WinDbg JS backend restores the `JSProviderBackend` from the prototype with significant production hardening. It is the **preferred Windows debug engine** when the WinDbg JavaScript provider (`JsProvider.dll`) is present; `CdbBackend` remains the fallback.

##### Motivation

`CdbBackend` extracts crash data by parsing the free-text output of `!analyze -v` - a process inherently fragile and subject to format variations across WinDbg versions. The WinDbg JavaScript engine accesses the **Debugger Data Model (DDM)** directly: it returns typed, structured JSON with no text parsing, exposes all threads (not just the faulting thread's text dump), provides module load addresses, and yields richer frame metadata (parameter values, local variable types). It is also the path toward live-process analysis (not just static dumps).

##### Architecture: Callback Bridge Pattern

```
WinDbgJSBackend.extract(source, symbol_path)
  │
  ├─ [1] Start _CallbackBridge(port=0, timeout=callback_timeout)
  │        └─ Binds to 127.0.0.1:0 (OS assigns ephemeral port)
  │           Runs HTTPServer in a daemon thread
  │           Each extraction gets its own instance-level queue
  │
  ├─ [2] Write JS asset to a NamedTemporaryFile
  │        └─ Read from backends/debug/assets/windbg_diagnostic.js
  │           Substitute __CALLBACK_URL__ with http://127.0.0.1:{port}/
  │
  ├─ [3] subprocess.run(["cdb.exe", "-z", dump, "-y", sym_chain,
  │                       "-c", ".scriptload \"{tmp_js}\"; g; q"],
  │                      timeout=cdb_timeout)
  │        └─ If FileNotFoundError → PlatformNotSupportedError
  │           If TimeoutExpired → DebugExtractionError
  │           If "JsProvider.dll" not loaded → DebugExtractionError
  │
  ├─ [4] bridge.wait_for_payload(timeout=callback_timeout)
  │        └─ If queue.Empty → DebugExtractionError (JS callback never arrived)
  │
  ├─ [5] Parse JSON payload → DebugExtractionResult
  │        └─ ExceptionCode → map_windows_ntstatus → FaultClass
  │           FaultingThread.StackFrames → list[StackFrame] (top N)
  │           AllThreadsSummary → included in raw_text_excerpt for Log Historian
  │           symbol_resolution_score from faulting-thread frames
  │           apply_noise_filter on raw JSON excerpt
  │
  └─ [6] _CallbackBridge.__exit__: httpd.shutdown() + delete temp JS file
```

##### Callback Bridge Class

```python
class _CallbackBridge:
    """RAII: starts an ephemeral HTTP listener, shuts it down on __exit__."""

    def __init__(self, callback_timeout: int) -> None: ...

    def __enter__(self) -> _CallbackBridge: ...
        # Binds HTTPServer to ("127.0.0.1", 0) - port 0 forces OS assignment.
        # Creates an instance-level queue.Queue[str] unique to this extraction.
        # Starts daemon thread running httpd.serve_forever().
        # self.port is set from httpd.server_address[1] after binding.

    def __exit__(self, *_: object) -> None: ...
        # httpd.shutdown(); httpd.server_close()

    def wait_for_payload(self) -> str: ...
        # self._queue.get(timeout=self._timeout)
        # Raises DebugExtractionError on queue.Empty
```

The handler factory closes over the instance queue to avoid the prototype's bug of a module-level class-attribute `data_queue` shared across concurrent extractions:

```python
def _make_handler(data_queue: queue.Queue[str]) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            ...  # read body, enqueue raw string, respond 200
        def log_message(self, *args: object) -> None:
            pass  # suppress noisy HTTP access log
    return _Handler
```

##### Production JS Diagnostic Script (`backends/debug/assets/windbg_diagnostic.js`)

The script is shipped as a versioned file (not a Python string) and read at runtime. It fixes and extends the prototype template:

```javascript
"use strict";

function initializeScript() {
    return [new host.apiVersionSupport(1, 9)];
}

(function () {
    var callbackUrl  = "__CALLBACK_URL__";
    var maxFaulting  = __MAX_FAULTING_FRAMES__;   // default 20
    var maxOther     = __MAX_OTHER_FRAMES__;       // default 3

    var process = host.currentProcess;
    var result = {
        ProcessID:          process.Id,
        ProcessName:        process.Name,
        ExceptionCode:      "",
        ExceptionAddress:   "",
        FaultingModule:     "",
        FaultingThread:     null,
        AllThreadsSummary:  []
    };

    try {
        var exc = process.LastEvent.Attributes.Exception;
        result.ExceptionCode    = "0x" + exc.Code.toString(16);
        result.ExceptionAddress = "0x" + exc.Address.toString(16);
    } catch (e) {}

    for (var thread of process.Threads) {
        var isFaulting = false;
        try { isFaulting = thread.Attributes.IsFaulting; } catch (e) {}

        var limit  = isFaulting ? maxFaulting : maxOther;
        var frames = [];
        var idx    = 0;
        for (var frame of thread.Stack.Frames) {
            if (idx >= limit) break;
            var module   = "";
            var baseAddr = "0x0";
            try {
                module   = frame.Module.Name;
                baseAddr = "0x" + frame.Module.BaseAddress.toString(16);
            } catch (e) {}
            frames.push({
                FrameNumber:   idx,
                Module:        module,
                ModuleBase:    baseAddr,
                Function:      frame.FunctionName || "",
                Offset:        "0x" + frame.Offset.toString(16)
            });
            idx++;
        }

        var summary = { ThreadID: thread.Id, IsFaulting: isFaulting, Frames: frames };
        if (isFaulting) {
            result.FaultingThread  = summary;
            result.FaultingModule  = frames.length > 0 ? frames[0].Module : "";
        }
        result.AllThreadsSummary.push(summary);
    }

    var payload = JSON.stringify(result);
    // Use MSXML2.XMLHTTP (COM automation) - the only HTTP client available
    // inside cdb.exe's WinDbg JS engine on Windows.
    var xhr = new ActiveXObject("MSXML2.XMLHTTP");
    xhr.open("POST", callbackUrl, false);
    xhr.setRequestHeader("Content-Type",   "application/json");
    xhr.setRequestHeader("Content-Length", payload.length.toString());
    xhr.send(payload);
})();
```

Substitution tokens (`__CALLBACK_URL__`, `__MAX_FAULTING_FRAMES__`, `__MAX_OTHER_FRAMES__`) are replaced by `WinDbgJSBackend._prepare_js(port, settings)` at runtime.

**`ActiveXObject` note:** MSXML2.XMLHTTP is a Windows COM object and the only synchronous HTTP client usable in the cdb/WinDbg JavaScript engine. It is explicitly scoped to Windows - `WinDbgJSBackend.SUPPORTED_PLATFORMS = ["Windows"]` - so the factory never registers it on Linux/macOS.

##### JSON Payload → `DebugExtractionResult` Mapping

| JSON field | `DebugExtractionResult` field | Notes |
|---|---|---|
| `ExceptionCode` | `exception_code_raw`, `fault_class` | Via `map_windows_ntstatus` |
| `ExceptionAddress` | `exception_address` | From `exc.Address`; more reliable than frame[0] offset |
| `FaultingModule` | `faulting_module` | From JS (DDM knows the module directly) |
| `FaultingThread.Frames[0].Function` | `faulting_function` | Top faulting-thread frame |
| `FaultingThread.Frames[:N]` | `stack_frames` | Top `N` faulting frames as `StackFrame` objects |
| `AllThreadsSummary` (JSON string) | `raw_text_excerpt` | Passed through `apply_noise_filter`; included for Log Historian's multi-thread context |
| Faulting frames with non-empty Function | `symbol_resolution_score` | Fraction of faulting-thread frames with resolved function names |

##### Configuration Additions (`DebugSettings`)

```yaml
backends:
  debug:
    engine: "auto"       # "auto" | "cdb" | "windbg_js"
    callback_timeout_seconds: 60
    max_faulting_frames: 20
    max_other_thread_frames: 3
    timeout_seconds: 300
    symbol_cache: null
    symbol_server_url: null
```

`engine: "auto"` (the default) tries `WinDbgJSBackend` first on Windows (checking for `JsProvider.dll` via a probe invocation), then falls back to `CdbBackend`. Setting `engine: "cdb"` forces the text-parsing path regardless of WinDbg availability.

##### Factory Update (`backends/debug/__init__.py`)

```python
def create_debug_backend(settings: DebugSettings, platform: str | None = None) -> DebugBackend:
    key = platform or sys.platform
    if key == "win32":
        if settings.engine == "windbg_js":
            return WinDbgJSBackend(settings)
        if settings.engine == "auto" and _windbg_js_available():
            return WinDbgJSBackend(settings)
        return CdbBackend(settings)
    if key == "linux":
        return GdbBackend(settings)
    if key == "darwin":
        return LldbBackend(settings)
    raise PlatformNotSupportedError(f"No debug backend for platform {key!r}")


def _windbg_js_available() -> bool:
    """Return True when cdb.exe + JsProvider.dll are present.

    Probes by running cdb.exe with a no-op script and checking whether
    JsProvider.dll loads without error. Result is cached after the first call.
    """
```

##### Files Added by This Feature

```
src/aegis_swr/backends/debug/
├── windbg_js_worker.py           # WinDbgJSBackend + _CallbackBridge + _make_handler
└── assets/
    └── windbg_diagnostic.js      # Versioned JS diagnostic script
```

##### Prototype Defects Fixed

| Prototype issue | Production fix |
|---|---|
| Module-level `JSCallbackHandler.data_queue` shared across concurrent extractions | Instance-level `_CallbackBridge._queue` via `_make_handler(queue)` closure |
| Fixed port-fallback chain (9999/9998/9997) - collides in CI | `port=0` - OS assigns an unused ephemeral port |
| JS template embedded as a Python string - not versionable or editable | Shipped as `backends/debug/assets/windbg_diagnostic.js` |
| No `ExceptionAddress` in DDM query | `exc.Address` added to script output; maps to `exception_address` |
| All threads returned at full depth | Faulting thread: `maxFaultingFrames`; other threads: `maxOtherFrames` (default 3) |
| Symbol path not passed to the JS engine | CDB `-y` symbol chain includes the resolved `symbol_path_string` |
| Raw dict return type - not a typed `DebugExtractionResult` | Full parse into `DebugExtractionResult`; no callers need to handle a dict |
| `JsProvider.dll` check by string matching in stdout | Explicit check; raises `DebugExtractionError` with actionable message |

### 6.3 StorageBackend (four concrete backends)

The ABCs defined in `backends/base.py` remain unchanged. The four concrete implementations differ only in where data lives:

| Backend | `RelationalStore` | `ObjectStore` | When to use |
|---|---|---|---|
| `FilesystemStore` | ✅ JSON files | ✅ binary files | Local development, CI, single-host deployments |
| `SQLiteStore` | ✅ SQLite DB | ✗ | Local dev; no binary artifact storage needed |
| `S3Store` | ✅ JSON objects in bucket | ✅ binary objects in bucket | Cloud / MinIO deployments without PostgreSQL |
| `PostgresStore` | ✅ (stub) | ✗ | Full production with PostgreSQL (Phase 6 complete) |

The `VectorStore` (Qdrant) is always a separate optional backend - not included in the four-provider selection.

The factory `create_storage_backends(settings)` returns `(RelationalStore | None, ObjectStore | None)` - the caller (Orchestrator) handles None for either component.

```python
class RelationalStore(ABC):
    @abstractmethod
    async def save_report(self, report: RCAReport) -> None: ...
    @abstractmethod
    async def get_report(self, incident_id: UUID) -> RCAReport | None: ...
    @abstractmethod
    async def find_by_hash(self, dump_hash: str) -> RCAReport | None: ...
    @abstractmethod
    async def update_hitl_response(self, incident_id: UUID, response: dict) -> None: ...

class ObjectStore(ABC):
    @abstractmethod
    async def upload_raw(self, incident_id: UUID, filename: str, data: bytes) -> str: ...
    @abstractmethod
    async def get_raw(self, object_key: str) -> bytes: ...

class VectorStore(ABC):
    @abstractmethod
    async def upsert_incident(self, report: RCAReport) -> None: ...
    @abstractmethod
    async def search_similar(
        self,
        fault_class: FaultClass,
        faulting_module: str | None,
        top_k: int = 5,
    ) -> list[RCAReport]: ...
```

### 6.4 LogBackend

```python
class LogBackend(ABC):
    @abstractmethod
    async def query_window(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity_levels: list[str] | None = None,
    ) -> list[str]:
        """Returns filtered log lines from the configured source."""
```

The `LogBackend` is **always optional**. When configured it is queried in Data
Adapter Stage 4 (§5.1) and its lines are merged with any file-based logs before
clustering. `query_window` is `async` (log sources may be network-backed). Two
adapters ship now; ELK is deferred (see §6.4.3).

| Adapter | File | Source | Status |
|---|---|---|---|
| `FileLogAdapter` | `log/file_adapter.py` | Local `.log` / `.txt` files | Full implementation |
| `FluentAdapter` | `log/fluent_adapter.py` | Fluentd / Fluent Bit | **Stub** (Phase-deferred) |
| `ELKAdapter` | `log/elk_adapter.py` | Elasticsearch / ELK | Deferred - not implemented yet |

#### 6.4.1 FileLogAdapter (`log/file_adapter.py`)

Reads local log files and returns the lines whose parsed timestamp falls in
`[start_time, end_time]`, optionally filtered by `severity_levels`. It is the
default and needs no external service.

- **File resolution:** the `service` argument maps to files under
  `settings.file_root` (when set): it globs `{file_root}/{service}*.log` and
  `{file_root}/{service}*.txt`. When `file_root` is null it falls back to the
  `IncidentSource.log_paths` already supplied to the Data Adapter (so passing
  `--log` files keeps working with no log provider config at all).
- **Timestamp parse:** best-effort ISO-8601 / common syslog prefix parse per line;
  unparseable lines are retained only when `incident_timestamp` is unknown.
- **Severity filter:** when `severity_levels` is given, keep only lines whose
  level token matches (case-insensitive); otherwise return all windowed lines.
- All file reads are wrapped in `asyncio.to_thread`. Resolved paths are guarded
  to stay within `file_root` (traversal → `ValueError`).

#### 6.4.2 FluentAdapter (`log/fluent_adapter.py`) - stub

Plugin backend for Fluentd / Fluent Bit, shipped as a **stub** (mirrors the
PostgreSQL store stub, §8.4) so the factory and config can select it ahead of a
full implementation:

- Constructor stores `settings` and logs a warning that this is a stub.
- `query_window(...)` raises `NotImplementedError("FluentAdapter is a stub. "
  "Implement the Fluent forward/HTTP query in a future phase.")`.
- The intended production design (documented for the future implementer): connect
  to `fluent_host:fluent_port`, issue a tag-scoped (`fluent_tag_prefix.{service}`)
  time-range query, and map records to log lines. No live connection is made by
  the stub.

#### 6.4.3 Factory & Configuration (`log/__init__.py`)

```python
def create_log_backend(settings: LogSettings) -> LogBackend | None:
    if settings.provider == "file":
        return FileLogAdapter(settings)
    if settings.provider == "fluent":
        return FluentAdapter(settings)          # stub
    if settings.provider == "elk":
        raise NotImplementedError("ELKAdapter is deferred; use 'file' or 'fluent'.")
    raise ValueError(f"Unknown log provider: {settings.provider!r}")
```

The factory always returns an adapter for `file`/`fluent`; the Data Adapter only
*queries* it in Stage 4 when a `service` name and `incident_timestamp` are both
present, so configuring `provider: file` with no service simply leaves the
file-path path (`IncidentSource.log_paths`) as the sole log source.

`LogSettings` (the `backends.log` section, §11):

```yaml
backends:
  log:
    provider: "file"               # file | fluent  (elk deferred)
    file_root: null                # base dir for service→file resolution (file provider)
    default_severity_levels: ["FATAL", "CRITICAL", "ERROR", "WARNING"]
    fluent_host: null              # fluent stub
    fluent_port: null              # fluent stub
    fluent_tag_prefix: null        # fluent stub
```

### 6.5 CodeBackend

```python
class CodeBackend(ABC):
    @abstractmethod
    def get_commits_before(
        self,
        repo_path: Path,
        before: datetime,
        window_hours: int = 2,
        limit: int = 10,
    ) -> list[CommitRecord]: ...

    @abstractmethod
    def get_file_diff(
        self,
        repo_path: Path,
        file_path: str,
        commit_sha: str,
    ) -> str: ...

    @abstractmethod
    def blame(
        self,
        repo_path: Path,
        file_path: str,
        line_range: tuple[int, int],
    ) -> list[BlameRecord]: ...
```

The `CodeBackend` is **always optional**. It is consumed only by Data Adapter
Stage 8 (§5.1) to attribute a crash to recent source changes. All three methods
are **synchronous** (the Data Adapter calls them inline, consistent with
`DebugBackend.extract`); record types are defined in §4.7. Two concrete
adapters ship:

| Adapter | File | Source of truth | When to use |
|---|---|---|---|
| `GitCodeAdapter` | `code/git_adapter.py` | A real Git working tree (`git log`/`diff`/`blame`) | The target service is built from a Git repo available to the analyzer host |
| `FilesystemCodeAdapter` | `code/filesystem_adapter.py` | A plain source directory, no VCS | Vendored / exported source trees, archived snapshots, or air-gapped drops with no `.git` |
| `PdbCodeAdapter` | `code/pdb_adapter.py` | Windows PDB Source Server (SrcSrv) stream | Windows crash where a `.pdb` with Source Server indexing is available; gives the **exact** build commit rather than a time-window guess |

#### 6.5.1 GitCodeAdapter (`code/git_adapter.py`)

Full Git history backend. All Git access is via `subprocess.run` with
**list-form argv** (never `shell=True`); each call passes `cwd=repo_path` and a
timeout (`git_timeout_seconds`, default 30).

- `get_commits_before(repo_path, before, window_hours=2, limit=10)`:
  `git log --since="{before − window_hours}" --until="{before}" --max-count={limit}
  --date=iso-strict --name-only --pretty=format:%H%x1f%an <%ae>%x1f%aI%x1f%s%x1e`.
  Parse the `\x1e`-delimited records (`\x1f`-delimited fields) into `CommitRecord`s;
  the trailing newline-separated paths become `changed_files`. Newest first.
- `get_file_diff(repo_path, file_path, commit_sha)`:
  `git show {commit_sha} -- {file_path}` (or `git diff {sha}~1 {sha} -- {file_path}`);
  returns the unified-diff text. Unknown SHA/path → `""`.
- `blame(repo_path, file_path, line_range)`:
  `git blame -L {start},{end} --line-porcelain -- {file_path}`; parse porcelain
  blocks into `BlameRecord`s.
- **Validation:** if `repo_path / ".git"` is absent → raise `CodeBackendError`
  (`core/exceptions.py`, added by Step 6.1) with an actionable message. If the
  `git` binary is missing (`FileNotFoundError`) → `CodeBackendError`. Per the
  "fail open" rule, the Data Adapter catches `CodeBackendError` in Stage 8, logs
  a warning, and continues with an empty `code_history`.
- **Path safety:** `file_path` is treated as repo-relative; the resolved absolute
  path is asserted to stay within `repo_path` (traversal → `ValueError`).

#### 6.5.2 FilesystemCodeAdapter (`code/filesystem_adapter.py`)

No-VCS fallback that treats a directory tree as the "repository". It degrades
gracefully so the same `CodeBackend` contract holds without Git:

- `get_commits_before(repo_path, before, window_hours=2, limit=10)`:
  walk the tree (skipping `.git`, `node_modules`, and dot-directories), stat each
  file, and synthesize one `CommitRecord` per file modified within the window
  `[before − window_hours, before]`. `sha = "fs:" + sha1(relpath)[:12]`,
  `author = "unknown"`, `authored_at = mtime (UTC)`, `message = "filesystem mtime"`,
  `changed_files = [relpath]`. Sorted newest-mtime first, capped to `limit`.
- `get_file_diff(repo_path, file_path, commit_sha)`: no history exists, so return
  the **full current file contents** prefixed with a `--- (no VCS history)` header
  rather than a real diff.
- `blame(repo_path, file_path, line_range)`: emit one `BlameRecord` per line in
  range with `sha="fs:…"`, `author="unknown"`, `authored_at=None`, and the line text.
- **Path safety:** identical traversal guard to `GitCodeAdapter`.

#### 6.5.3 Factory & Configuration (`code/__init__.py`)

```python
def create_code_backend(settings: CodeSettings) -> CodeBackend | None:
    if not settings.enabled:
        return None                      # code history disabled → Stage 8 is skipped
    if settings.provider == "git":
        return GitCodeAdapter(settings)
    if settings.provider == "filesystem":
        return FilesystemCodeAdapter(settings)
    raise ValueError(f"Unknown code provider: {settings.provider!r}")
```

`CodeSettings` (the `backends.code` section, §11):

```yaml
backends:
  code:
    enabled: false                 # false → no CodeBackend; Stage 8 skipped
    provider: "git"                # git | filesystem
    repo_path: null                # path to the working tree / source root
    window_hours: 2                # default look-back for get_commits_before
    commit_limit: 10               # default max commits returned
    git_timeout_seconds: 30        # git subprocess timeout (git provider)
```

`repo_path` may be supplied at the CLI with `--repo` (which also flips
`enabled=true`); see §12.2.

#### 6.5.4 PdbCodeAdapter (`code/pdb_adapter.py`) - Windows, Source Server indexing required

The PDB Code Adapter derives source attribution from a Windows Program Database
(`.pdb`) file rather than from the file system or a live Git working tree. Because
the PDB's **Source Server (SrcSrv) stream** records the *exact* VCS revision that
was compiled into each binary, this adapter eliminates the time-window heuristic
entirely - no guessing from commit timestamps.

##### Prerequisites

1. The `.pdb` file must be readable (local symbol cache, symbol server download, or
   path passed as `pdb_path`). If only an address-only PDB is present (no SrcSrv
   stream), the adapter falls back gracefully to empty results.
2. `pdbstr.exe` from **Debugging Tools for Windows** must be on PATH. The same
   install that provides `cdb.exe` also ships `pdbstr.exe`, so any environment
   that already runs `CdbBackend` qualifies. On non-Windows platforms the adapter
   raises `CodeBackendError` immediately.

##### SrcSrv stream

The SrcSrv stream is a text block embedded in the PDB by source-indexing tools
(e.g., `ssindex.cmd`, `srcsrv.dll` via build pipeline). Its key fields per entry:

```
SRCSRV: ini ------------------------------------------------
INDEXVERSION=2
VERCTRL=git                         # VCS type: git | tfvc | svn | ...
SRCSRV: variables ------------------------------------------
GITREPO=https://github.com/org/svc  # remote origin URL
SRCSRV: source files ----------------------------------------
db_writer.cpp*abc123def456*         # file path * VCS revision *
pool.cpp*abc123def456*
```

##### Behaviour per method

- **`get_commits_before(repo_path, before, window_hours, limit)`** - `before` and
  `window_hours` are ignored; the PDB is the ground truth. Runs
  `pdbstr.exe -r -p:{pdb_path} -s:srcsrv`, parses the stream, and returns a
  single `CommitRecord` per unique revision SHA found (`author="PdbSourceServer"`,
  `timestamp=None` coerced to the PDB file's mtime, `message="SrcSrv build revision"`).
  If the SrcSrv stream is absent or empty → `[]`. `repo_path` is used only to
  resolve `pdb_path` when it is not explicitly set.
- **`get_file_diff(repo_path, file_path, commit_sha)`** - uses the SrcSrv
  `VERCTRL`-specific extraction command (e.g., `git show {sha}:{file_path}`) or
  falls back to `git show` when `VERCTRL=git`. Unknown VCS type → `""`.
- **`blame(repo_path, file_path, line_range)`** - delegates to the underlying VCS
  with the exact SHA from the SrcSrv stream. For `VERCTRL=git`: calls
  `git blame -L {start},{end} --line-porcelain {sha} -- {file_path}`. Any git
  failure → empty list (fail open).

##### pdb_path resolution

`pdb_path` is resolved in this order:
1. Explicit `pdb_path` in `CodeBackendSettings`.
2. Auto-resolve from `IncidentSource.dump_path` and symbol cache: replace the
   dump's extension with `.pdb` and search the symbol cache directories.
3. If neither yields a readable file → `CodeBackendError` (caught by Stage 8,
   degrades to empty `code_history`).

##### Factory & config additions (§6.5.3 update)

```python
if settings.provider == "pdb":
    return PdbCodeAdapter(settings)
```

```yaml
backends:
  code:
    enabled: false
    provider: "git"          # git | filesystem | pdb
    repo_path: null
    pdb_path: null           # explicit PDB path; null = auto-resolve from dump
    window_hours: 2          # used by git/filesystem; ignored by pdb
    commit_limit: 10
    git_timeout_seconds: 30
    pdbstr_timeout_seconds: 15  # pdbstr.exe subprocess timeout (pdb provider)
```

`--code-provider pdb` is the corresponding CLI value; `--repo` is still accepted
with `pdb` (provides `repo_path` for `git blame` fallback).

##### Architecture note: why this belongs in Code Backend, not Debug Backend

The Debug Backend reads PDB to answer: *"what is the function at 0x00007ff8?"*
(symbol resolution, run during Stage 2). The Code Backend reads PDB to answer:
*"what source code was compiled into this binary and at which VCS revision?"*
(build provenance, run during Stage 8). These are orthogonal questions asked at
different pipeline stages. The same `.pdb` file answers both; the dual reference is
intentional and architecturally correct (see the disambiguation note in §6.2).

---

## 7. Multi-Agent System Engine

### 7.1 LangGraph State Graph

The MAS is implemented as a **LangGraph StateGraph** with the following nodes:

```
START
  │
  ▼
[data_adapter_node]     Runs the full preprocessing pipeline; produces incident_brief
  │
  ▼
[os_kernel_node]        OS Kernel Agent - first pass; produces ExceptionSummary + Hypothesis
  │
  ▼
[code_analyst_node]     Code Analyst Agent - receives ExceptionSummary; produces RCA Hypothesis
  │
  ▼
[log_historian_node]    Log Historian Agent - injects conditional history; updates confidence
  │
  ▼
[skeptic_node]          Skeptic Agent - challenges current primary hypothesis
  │
  ├── [if confirmed=True and consensus >= threshold] ──► [output_synthesizer_node] ──► END
  ├── [if confirmed=False and round < max_rounds]    ──► [os_kernel_node] (next round)
  └── [if confidence < 0.50 and round == max_rounds] ──► [hitl_node] ──► END
```

The `consensus_evaluator` is called at the end of the Skeptic node. It is not a separate graph node - it is a pure function that reads the current state.

### 7.2 Consensus Score Formula

```
CS = Σ(Wᵢ × Sᵢ) / Σ(Wᵢ)
```

Where:
- `Wᵢ` = domain authority weight of Agent `i` for the detected `FaultClass`
- `Sᵢ` = confidence score produced by Agent `i` in the current round

**Default weight matrix** (configurable in `config.yaml`):

| Agent | MEMORY_* | STACK_* | DEADLOCK | LOG_* | DEFAULT |
|---|---|---|---|---|---|
| OS Kernel | 0.40 | 0.45 | 0.35 | 0.20 | 0.30 |
| Code Analyst | 0.35 | 0.30 | 0.30 | 0.40 | 0.35 |
| Log Historian | 0.15 | 0.10 | 0.20 | 0.35 | 0.20 |
| Skeptic | 0.10 | 0.15 | 0.15 | 0.05 | 0.15 |

**Termination conditions:**
1. `CS >= consensus_threshold` (default 0.85) for the same `primary_hypothesis` in ≥2 consecutive rounds.
2. `round_number >= max_debate_rounds` (default 4).
3. `hitl_pending = True` if `CS < 0.50` at `max_debate_rounds`.

### 7.3 Agent Persona Definitions

#### OS Kernel Agent (`agents/os_kernel.py`)

**System prompt role:** "Expert OS-level debugger and kernel engineer. Your primary focus is environmental constraints: memory allocation state, I/O latency, driver conflicts, thread blocking primitives, and hardware signal mapping. You map raw exception codes to FaultClass values and construct the first structural hypothesis about what went wrong in the system environment."

**Inputs:** `IncidentBrief` (full)
**Output schema:** `OSKernelOutput { exception_summary: ExceptionSummary, hypotheses: list[Hypothesis], confidence_score: float }`
**Context prepended when `symbol_resolution_score < 0.50`:** "WARNING: Symbol resolution is {score:.0%}. Confidence in function-level analysis is degraded. Focus hypothesis on module-level and exception-code-level evidence only."

#### Code Analyst Agent (`agents/code_analyst.py`)

**System prompt role:** "Senior software engineer specialized in debugging algorithmic flaws, memory management errors, race conditions, uninitialized pointers, and language-specific anti-patterns. You receive an ExceptionSummary from the OS Kernel Agent and the full stack trace. Your task is to identify the specific code-level root cause: faulting function, line of code, and the logical path that led to the fault."

**Inputs:** `IncidentBrief` + `OSKernelOutput` + optional `user_assumption`
**Output schema:** `CodeAnalystOutput { rca: RCAHypothesis, alternative_hypotheses: list[Hypothesis], confidence_score: float }`

#### Log Historian Agent (`agents/log_historian.py`)

**System prompt role:** "Production incident historian. You analyze temporal log patterns, compare current failure signatures to historical baselines, and determine whether this incident is a first occurrence or a recurrence. You adjust confidence scores based on pattern recurrence evidence."

**Inputs:** `IncidentBrief.log_summary` + historical incidents from Qdrant + `CodeAnalystOutput`
**Output schema:** `LogHistorianOutput { pattern_match: PatternMatch | None, confidence_adjustment: float, updated_confidence: float }`

**Conditional injection rule:** Only injects history block if `faulting_module` recurrence ≥2 OR `fault_class` recurrence ≥3 in last 10 incidents. Otherwise confidence adjustment is 0.0.

#### Skeptic Agent (`agents/skeptic.py`)

**System prompt role:** "The adversarial moderator. You receive the current primary hypothesis and the full discussion so far. Your job is to challenge it: verify that the stated faulting module actually appears in the stack trace, check that the exception code is consistent with the hypothesis, and identify any evidence the other agents may have overlooked. If the hypothesis survives scrutiny, confirm it. If not, provide specific corrections and flag it as LOW confidence."

**Mandatory assertion checks:**
1. `stated_faulting_module` is present in `stack_frames[0..4]`.
2. `stated_fault_class` is semantically consistent with `exception_code_raw`.
3. `stated_exception_address` is within the stated `faulting_module`'s address range (if available).

**Inputs:** `IncidentBrief` + all previous `AgentTurn` objects
**Output schema:** `SkepticVerdict { confirmed: bool, confidence: ConfidenceLevel, challenges: list[str], corrections: list[str] }`

If `confirmed=False`: corrections are appended to the OS Kernel Agent's context in the next round as "Skeptic corrections from round N."

### 7.4 Human-in-the-Loop (HITL) Trigger

If after `max_debate_rounds` the `consensus_score < 0.50`, the system generates a structured `HITLRequest`:

```python
HITLRequest(
    question="The panel is split between a deadlock in the connection pool and "
             "a null-pointer dereference in the serializer. The two hypotheses have "
             "confidence scores of 0.41 and 0.38 respectively.",
    context_summary="...",
    requested_data=[
        "Current maximum connection pool size configured in the target service.",
        "Whether a recent change to the serializer was deployed in the 24 hours before the incident.",
    ]
)
```

The HITL request is returned in `RCAReport.hitl_request`. The API client (CLI, webhook, Slack bot) presents it to the engineer. When the engineer provides the answer, they call `POST /v1/incidents/{id}/continue` with the additional data. The Data Adapter re-processes the new data, appends it to the incident brief, and the state graph re-enters at `os_kernel_node` for one additional round.

---

## 8. Storage Architecture

Four concrete backends implement the `RelationalStore` and/or `ObjectStore` ABCs. All backends surface the same deduplication contract: `find_by_hash(dump_hash)` is called by the Orchestrator before any analysis starts; a non-None result returns the cached `RCAReport` immediately.

All sync I/O (filesystem, SQLite) is wrapped in `asyncio.to_thread` so the interface stays uniformly `async` without blocking the event loop.

### 8.1 Filesystem Store (`filesystem_store.py`)

Implements both `RelationalStore` and `ObjectStore`. Evolved from the prototype's `FilesystemBackend`.

**Report storage** (`reports_dir/`, default `~/.local/share/.aegis-swr/reports`):
- One file per report: `{reports_dir}/{incident_id}.json`
- Hash index for O(1) dedup: `{reports_dir}/_hash_index/{dump_hash}` (content = incident_id string)

**Raw artifact storage** (`objects_dir/`, default `~/.local/share/.aegis-swr/objects`):
- `{objects_dir}/{incident_id}/{filename}` - upload/download path

**Path safety:** every resolved path is checked to remain within its root directory. Traversal attempts raise `ValueError`.

**`find_by_hash` algorithm:**
1. Read `{reports_dir}/_hash_index/{dump_hash}` → incident_id string (raises `FileNotFoundError` → return None if missing)
2. Load and deserialise `{reports_dir}/{incident_id}.json`

**`update_hitl_response`:** read report JSON, update `hitl_request` field in-place, write back.

### 8.2 SQLite Store (`sqlite_store.py`)

Implements `RelationalStore` only. Evolved from the prototype's `SQLiteBackend`.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS reports (
    incident_id TEXT PRIMARY KEY,
    dump_hash   TEXT,
    created_at  TEXT NOT NULL,
    mode        TEXT NOT NULL,
    report_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_dump_hash
    ON reports(dump_hash) WHERE dump_hash IS NOT NULL;
```

`find_by_hash` uses a direct indexed `WHERE dump_hash = ?` query - no full-table scan.
`update_hitl_response` does `UPDATE reports SET report_json = ? WHERE incident_id = ?` after modifying the parsed report dict in Python.
Default `db_path`: `~/.local/db/.aegis-swr/reports.db`.

### 8.3 S3 Store (`s3_store.py`)

Implements both `RelationalStore` and `ObjectStore` via sync `boto3` wrapped in `asyncio.to_thread`.

**Report storage** (relational contract over S3):
- Report JSON: `reports/{incident_id}.json`
- Hash index: `hash-index/{dump_hash}` (content = incident_id UTF-8)

**Raw artifact storage:**
- `objects/{incident_id}/{filename}`
- Object key returned from `upload_raw()` is `{incident_id}/{filename}`

**`find_by_hash`:**
1. `GetObject` for `hash-index/{dump_hash}` → read incident_id (`NoSuchKey` → None)
2. `GetObject` for `reports/{incident_id}.json` → deserialise

**Bucket** parsed from `object_store_url` (e.g., `s3://my-bucket` → `bucket="my-bucket"`).
**MinIO support:** `s3_endpoint_url` config key; if set, passed as `endpoint_url` to `boto3.client()`.
**Credentials:** standard AWS env vars (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) or instance profile.

### 8.4 PostgreSQL Store (`postgres_store.py`) - stub

Implements `RelationalStore`. All methods raise `NotImplementedError` with a message directing the developer to Phase 6. The stub exists so the factory can return it and the Orchestrator can be configured for PostgreSQL in advance.

Full PostgreSQL implementation (SQLAlchemy async + alembic migration) is deferred to a dedicated future phase.

### 8.5 Qdrant Vector Store (`qdrant_store.py`)

Separate from the four-provider selection. Always optional. Used by `LogHistorianAgent` for historical incident similarity search.

**Collection:** `incident_history`

**Point structure:**
```json
{
  "id": "{report_id_as_uuid}",
  "vector": [0.12, ..., 0.88],
  "payload": {
    "incident_id": "...",
    "faulting_module": "db_writer.dll",
    "root_cause_summary": "Race condition in serialize()",
    "confidence_score": 0.92,
    "created_at": "2026-05-30T14:02:11Z"
  }
}
```

### 8.6 Factory (`backends/storage/__init__.py`)

```python
def create_storage_backends(
    settings: StorageSettings,
) -> tuple[RelationalStore | None, ObjectStore | None]:
    if settings.provider == "filesystem":
        store = FilesystemStore(settings)
        return store, store   # implements both
    if settings.provider == "sqlite":
        return SQLiteStore(settings), None
    if settings.provider == "s3":
        store = S3Store(settings)
        return store, store   # implements both
    if settings.provider == "postgres":
        return PostgresStore(settings), None
    raise ValueError(f"Unknown storage provider: {settings.provider!r}")
```

### 8.7 Configuration additions

```yaml
backends:
  storage:
    provider: "filesystem"             # filesystem | sqlite | s3 | postgres
    reports_dir: "~/.local/share/.aegis-swr/reports"  # filesystem
    objects_dir: "~/.local/share/.aegis-swr/objects"  # filesystem object store
    db_path: "~/.local/db/.aegis-swr/reports.db"   # sqlite
    object_store_url: "s3://aegis-raw-inputs"  # s3
    object_store_region: "us-east-1"           # s3
    s3_endpoint_url: null                      # s3 / MinIO custom endpoint
    database_url: "postgresql+asyncpg://..."   # postgres stub
    # vector store always separate:
    vector_store_url: "http://localhost:6333"
    vector_collection: "incident_history"
```

---

## 9. REST API Layer (`api/`)

**Framework:** FastAPI with async endpoints throughout. Runs under Uvicorn.

### 9.1 Endpoints

#### `POST /v1/incidents/analyze`

- Content-Type: `multipart/form-data`
- Body fields:
  - `metadata`: JSON string - `IncidentSource` minus file paths
  - `logs`: zero or more log files (`.log`, `.txt`)
  - `crashdump`: optional binary file (`.dmp`, `.core`, `.ips`)
  - `screenshot`: optional image (`.png`, `.jpg`)
- Returns: `{ "incident_id": "uuid", "status": "analyzing" }`
- Behavior: uploads raw files to S3; creates incident record; starts orchestrator as background task.

#### `GET /v1/incidents/{incident_id}/stream`

- Protocol: **Server-Sent Events (SSE)**
- Event types:
  - `agent_turn`: one event per `AgentTurn` as it completes
  - `consensus_update`: CS after each round
  - `complete`: full `RCAReport` on completion
  - `hitl_request`: `HITLRequest` when deadlocked
  - `error`: error details
- Heartbeat: `comment` event every 15 s to keep connection alive.

#### `GET /v1/incidents/{incident_id}/report`

- Returns: completed `RCAReport` JSON
- Returns 202 Accepted with `{ "status": "analyzing" }` if not yet complete.
- Returns 200 with full report if complete.

#### `POST /v1/incidents/{incident_id}/continue`

- Body: `{ "user_data": { "question": "...", "files": [...], "text": "..." } }`
- Resumes HITL-pending investigation with new data.

#### `GET /v1/incidents/` (list)

- Query params: `fault_class`, `faulting_module`, `since`, `limit`, `offset`
- Returns paginated list of `{ incident_id, status, fault_class, confidence_score, created_at }`.

### 9.2 Authentication Middleware

API key authentication via `X-Aegis-API-Key` header. Key hashed with bcrypt before storage in PostgreSQL. Multi-tenant: each key is scoped to an organization slug that prefixes all storage paths.

### 9.3 Rate Limiting

`slowapi` decorator: 10 analyze requests / minute per API key. Configurable in `config.yaml`.

---

## 10. Secure Code Validation Sandbox (`sandbox/`)

When the Code Analyst Agent produces a `probabilistic_fix` (unified diff), the sandbox validates it before including it in the final report.

### 10.1 Architecture

```
Orchestrator Core
      │  patch content + target language
      ▼
  executor.py: SandboxExecutor
      │
      │  docker run --rm --network=none --read-only
      │            --tmpfs /tmp:rw,exec,size=50m
      │            --memory=256m --cpus=0.5
      │            aegis-sandbox-{language}:{version}
      │
      ▼
  Container execution:
      1. Mount: inject patch to /tmp/proposed_fix.{ext}
      2. Compile: g++ -fsyntax-only -std=c++20 proposed_fix.cpp 2>compiler_errors.log
                  (or: python -m py_compile / javac / tsc --noEmit)
      3. AST lint: clang-tidy / pylint / eslint (static analysis)
      4. Output: exit code + compiler_errors.log + linter output
      │
      ▼
  validators.py: ValidationResult
      │  { passed: bool, exit_code: int, compiler_output: str, lint_findings: list[str] }
      ▼
  If passed=False: ValidationResult passed to Code Analyst Agent
                   with correction prompt "Compilation failed: {compiler_output}"
                   Agent may revise and retry once.
```

**Supported languages (sandbox images):** `cpp20`, `python311`, `java21`, `typescript5`

**Network isolation:** `--network=none` is enforced. The container has no egress.

**Image registry:** Images are pre-built and stored internally. They are never pulled at runtime.

---

## 11. Configuration System (`config/settings.py`)

Using Pydantic Settings v2 with YAML config file + environment variable override.

```yaml
# config.yaml (default)
core:
  max_debate_rounds: 4
  consensus_threshold: 0.85
  hitl_confidence_threshold: 0.50
  log_window_seconds: 30
  user_assumption_token_limit: 500
  stack_frames_limit: 20

backends:
  ai:
    provider: "anthropic"           # anthropic | openai
    model: "claude-sonnet-4-6"
    temperature: 0.2
    max_tokens: 4096
    stream: true

  debug:
    timeout_seconds: 300
    symbol_cache: null              # null = platform default (~/.cache/aegis-swr/symbols)
    symbol_server_url: null

  storage:
    database_url: "postgresql+asyncpg://user:pass@localhost:5432/aegis"
    object_store_url: "s3://aegis-raw-inputs"
    vector_store_url: "http://localhost:6333"
    vector_collection: "incident_history"
    object_store_region: "us-east-1"

  log:
    provider: "file"                # file | fluent  (elk deferred)
    file_root: null                 # base dir for service→file resolution (file provider)
    default_severity_levels: ["FATAL", "CRITICAL", "ERROR", "WARNING"]
    fluent_host: null               # fluent stub
    fluent_port: null               # fluent stub
    fluent_tag_prefix: null         # fluent stub

  code:
    enabled: false                  # false → no CodeBackend; Stage 8 skipped
    provider: "git"                 # git | filesystem | pdb
    repo_path: null                 # working tree / source root (git / filesystem / pdb fallback)
    pdb_path: null                  # explicit .pdb path; null = auto-resolve from dump (pdb)
    window_hours: 2                 # look-back for get_commits_before (git / filesystem)
    commit_limit: 10                # default max commits returned
    git_timeout_seconds: 30         # git subprocess timeout (git provider)
    pdbstr_timeout_seconds: 15      # pdbstr.exe timeout (pdb provider)

sandbox:
  enabled: true
  runtime: "docker"                 # docker | gvisor (gvisor requires gVisor installed)
  memory_mb: 256
  cpu_limit: 0.5
  timeout_seconds: 60

api:
  host: "0.0.0.0"
  port: 8000
  workers: 4
  api_key_header: "X-Aegis-API-Key"
  rate_limit_per_minute: 10

agent_weights:
  memory_access_violation:
    os_kernel:     0.40
    code_analyst:  0.35
    log_historian: 0.15
    skeptic:       0.10
  # (other fault classes follow same structure)
```

All config values can be overridden by environment variables using the prefix `AEGIS__` with double underscore as separator (Pydantic Settings v2 convention):
```
AEGIS__BACKENDS__AI__PROVIDER=openai
AEGIS__CORE__MAX_DEBATE_ROUNDS=6
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

---

## 12. CLI Interface (`cli/commands.py`)

Built with **Typer**. Inherits the prototype's `--config` / `--save-config` pattern: every analyze option can be supplied as a CLI flag **or** persisted in a JSON config file that mirrors the flag names.

### 12.1 Subcommand Overview

```
aegis analyze   [OPTIONS]         Run analysis in-process (no server needed)
aegis export    [OPTIONS]         Migrate records between storage backends
aegis server    [OPTIONS]         Start the FastAPI API server (Phase 8)
aegis config show                 Print resolved config.yaml + env overrides (redacts secrets)
aegis config set KEY VALUE        Write a single key to config.yaml
```

### 12.2 `aegis analyze` - full flag reference

```bash
aegis analyze \
  --dump    ./crash.dmp          # crash dump file (magic-byte format detected)
  --log     ./app.log            # log file (repeatable - pass once per file)
  --shot    ./error.png          # screenshot (repeatable)
  --pcap    ./traffic.pcap       # network traffic capture (repeatable; metadata shown at --log-severity DEBUG)
  --sym     ./symbols/           # symbol path
  --assume  "DB pool reduced"    # user context / assumption text
  --engine  auto                 # debug engine: auto | cdb | windbg_js
  --ai      anthropic            # AI provider: anthropic | openai
  --store   filesystem           # storage backend: filesystem | sqlite | s3 | postgres
  --store-config ~/.local/share/.aegis-swr/reports  # storage config value (dir path / db path / S3 URL)
  --code-provider none           # code backend: none | git | filesystem | pdb
  --repo    ./service-src        # repo / source root (sets code-provider on, repo_path)
  --log-provider file            # log backend: file | fluent
  --log-service auth-api         # service name for LogBackend.query_window (optional)
  --output  rich                 # output format: rich | json | quiet
  --log-severity INFO                # log verbosity: TRACE | DEBUG | INFO | WARNING | ERROR (TRACE streams the full !analyze output)
  --config  ~/.local/state/.aegis-swr/config.json   # load options from JSON file
  --save-config                  # save current effective options to JSON file, then exit
```

**Option precedence (highest wins):** explicit CLI flag → JSON config file value → hardcoded default. The config file is applied first and explicit CLI flags are layered on top (`defaults < config.json < CLI`).

`--log`, `--shot`, and `--pcap` are **repeatable**: pass each flag once per file.

`--log-severity DEBUG` also raises the live war-room Evidence Stream to its DEBUG
verbosity, which surfaces detailed per-artifact metadata (textual core-dump
analysis, ±2-minute log windows, screenshot file properties, and network-capture
metadata). See `docs/adr/new-ui-rich-based-design.md` §2.2.1.

Prototype options carried forward:
- `--engine` (maps to `DebugSettings.engine`)
- `--ai` (maps to `AISettings.provider`)
- `--store` / `--store-config` (maps to `StorageSettings.provider` / path)
- `--assume` (maps to `IncidentSource.user_assumption`)
- `--log-severity` (maps to log verbosity; replaces `--report-severity`)
- `--config` / `--save-config` (JSON file round-trip)

New backend options (§6.4 / §6.5):
- `--code-provider` (maps to `CodeSettings.provider`; `none` leaves `CodeSettings.enabled=false`; valid values: `none | git | filesystem | pdb`)
- `--repo` (maps to `CodeSettings.repo_path`; passing it implies `enabled=true` and, if `--code-provider` is omitted, defaults the provider to `git`; for `pdb` provider, `--repo` still accepted as the git fallback root for blame)
- `--log-provider` (maps to `LogSettings.provider`)
- `--log-service` (service name passed to `LogBackend.query_window`; when omitted, the file-path log source is used and no `query_window` call is made)

### 12.3 JSON config file (`~/.local/state/.aegis-swr/config.json`)

There are two ways to configure `aegis analyze` startup options - the CLI and a
JSON config file - and **both deserialize into the same schema**,
`AnalyzeConfig` (`cli/_config.py`). That dataclass is the *single source of
truth* for the option keys, their types, and their defaults: the CLI option
names, the JSON keys, and the persisted file all derive from it, so there is no
second list of names to keep in sync. The keys mirror the `aegis analyze` CLI
options exactly:

```json
{
  "dump":          null,
  "logs":          [],
  "shots":         [],
  "pcaps":         [],
  "sym":           null,
  "assume":        null,
  "engine":        "auto",
  "store":         "filesystem",
  "store_config":  null,
  "code_provider": "none",
  "repo":          null,
  "output":        "rich",
  "logging": {
    "provider":  "file",
    "service":   null,
    "severity":  "WARNING",
    "dir":       "~/.local/state/aegis-swr/logs"
  }
}
```

The four logging options are grouped under a nested `logging` section (the `log_`
prefix is stripped); each still maps 1:1 to a `--log-*` CLI flag. The section is
named `logging` rather than `log` so it is not confused with the unrelated
`backends.log` log-ingestion backend.

The default path is `~/.local/state/.aegis-swr/config.json` (override with
`--config PATH`). When both sources are present the file is loaded first and
explicit CLI flags are applied on top (`defaults < config.json < CLI`). Unknown
keys in the file are ignored with a warning (typo protection). A ready-to-copy
template lives at [`config.example.json`](../../config.example.json).

`--save-config` writes the current effective options (CLI flags merged over any
loaded JSON values) to the config file and exits without running analysis.

### 12.4 `aegis export` - migrate records between stores

```bash
aegis export \
  --store        filesystem           # source backend
  --store-config ~/.local/share/.aegis-swr/reports \
  --to-store     sqlite               # destination backend
  --to-config    ~/backup/reports.db
```

Reads all reports from the source `RelationalStore` via `load_recent(limit=None)` and writes each to the destination via `save_report()`.

### 12.5 Output formatters (`cli/_formatters.py`)

- **`rich`** - live war-room display, then a `rich.panel` verdict summary (root cause, confidence level, mitigation, optional fix), followed by a `Report saved: <path>` pointer.
- **`json`** - stdout carries only a machine-readable **locator** (`incident_id`, `mode`, `status`, `storage`, `report_path`) so scripts can find the saved file; the full report body is **never** dumped to stdout (regardless of `--log-severity`). The report itself is written exclusively as the result file by the storage backend.
- **`quiet`** - exit code 0 (success) / 1 (HITL or low confidence); no stdout output.

### 12.6 Files

```
src/aegis_swr/cli/
├── __init__.py
├── commands.py       # Typer app, all subcommand implementations
├── _config.py        # JSON config load/save/merge; default path constant
├── _formatters.py    # json_formatter, rich_formatter
└── _logging.py       # loguru level setup + SensitiveFilter sink
```

---

## 13. Security & Privacy Design

### 13.1 PII Scrubbing

The `Data Adapter` runs Presidio Analyzer before any text is passed to an external LLM. All scrubbing happens locally. The substitution map (`REDACTED_EMAIL_1 → user@example.com`) is stored in the `incidents` table `source_metadata` JSONB column under the key `pii_substitution_map`, encrypted at the column level. It is never sent outside the platform.

### 13.2 Secret Redaction (inherited from prototype)

`SensitiveFilter` from the prototype is ported and attached to the `loguru` logger sink. It redacts `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and any string matching `sk-ant-*` or `sk-*` patterns from log output.

### 13.3 Sandbox Isolation

The code sandbox runs with `--network=none`, `--read-only` rootfs, `--tmpfs /tmp:rw,exec,size=50m`, and `--cap-drop ALL`. On gVisor-enabled hosts, the container runtime is `runsc` instead of `runc` for syscall-level isolation.

### 13.4 Deployment Topology Options

| Option | Description | When to use |
|---|---|---|
| Single-host Docker Compose | All services (FastAPI, PostgreSQL, MinIO, Qdrant) on one machine | Development / small team |
| VPC-hosted (AWS/Azure) | FastAPI behind private ALB; RDS PostgreSQL; S3 native; Qdrant Cloud | Enterprise / GDPR/HIPAA |
| Air-gapped | All services on-prem; local LLM (Ollama/vLLM with DeepSeek or Llama) | High-compliance |

---

## 14. Testing Strategy

### 14.1 Unit Tests (`tests/unit/`)

- `test_data_adapter.py`: Each pipeline stage tested in isolation with synthetic input fixtures.
- `test_consensus.py`: Weighted CS formula with boundary values.
- `test_fault_codes.py`: All platform code → FaultClass mappings.
- `test_schemas.py`: Pydantic validation and serialization round-trips.

### 14.2 Integration Tests (`tests/integration/`)

- `test_orchestrator.py`: Full pipeline with a mock AI backend and real Data Adapter.
- `test_api.py`: FastAPI test client hitting all endpoints.
- `test_storage.py`: PostgreSQL + MinIO against Docker Compose test stack.

### 14.3 Ground Truth Evaluation Suite (`tests/ground_truth/`)

A library of historical incidents where the correct root cause is known:

```
tests/ground_truth/
├── incidents/
│   ├── GTC-001/
│   │   ├── inputs/  (dump, logs, screenshot)
│   │   ├── expected_output.json   # { fault_class, faulting_module, root_cause_keywords }
│   │   └── README.md
│   └── ...
└── eval_runner.py     # Runs all incidents; checks if platform reaches correct conclusion
```

`eval_runner.py` reports per-incident: `PASS` / `FAIL` / `PARTIAL` (correct fault class, wrong module). Minimum passing threshold: 80% PASS across the suite. This runs in CI on every change to agent prompts or the consensus algorithm.

### 14.4 Token Budget Benchmarks

After each significant change to the Data Adapter, run `tests/benchmarks/token_budget.py` against 5 canonical dump+log pairs. Assert that the average per-request token count is below the configured `TOKEN_BUDGET_TARGET` (default: 12,000 input tokens), ensuring that the Data Adapter is providing at least a 30% reduction vs. the prototype baseline.
