# Milestone 0004 - Code Intelligence Layer

**Package:** `aegis-swr` | **Module root:** `aegis/code_intel/`
**Depends on:** Milestone 0003 (LiteLLM Model Router; `aegis/router/` in its final state)

This milestone replaces the stateless `FilesystemCodeAdapter` with a **multi-tool
code intelligence layer** that gives Code Agent the ability to navigate,
search, and reason about large-scale C/C++/Python codebases (~500k LOC)
without exceeding context budgets. After this milestone, Code Agent does not
receive a blob of source code - it *navigates* the codebase through a ReAct
tool loop, fetching only what each reasoning step requires.

> **Prerequisite:** `aegis/router/` must be fully operational and injected into
> all agents before this milestone begins. Code Agent must accept a
> `ModelRouter` via constructor injection (Milestone 0003 Task 06.0).

---

## Background

`FilesystemCodeAdapter` synthesises fake commits from `mtime` metadata and
returns raw file content on `get_file_diff`. That is sufficient for small
Python packages but breaks at an Audacity-scale for three reasons:

1. **Context budget exhaustion.** A single large C++ translation unit can
   exceed the model's context window. Handing the agent a whole file is not
   viable - it must fetch only the relevant slice.
2. **No cross-file navigation.** A crash stack references symbols defined
   across dozens of files. Without a call-graph or symbol index, the agent
   cannot follow the stack.
3. **No semantic search.** Locating the source of a bug requires finding
   "all callers of `AudioIO::StartStream` that do not hold the device lock"
   - a query that regex or `os.walk` cannot answer.

The solution is a **tool-per-capability** design: each code intelligence
operation (symbol lookup, caller graph, semantic search, AST slice, file
slice) is a discrete `CodeTool` that the agent invokes in a ReAct loop.
The agent reasons about which tool to call next; it never receives unsolicited
source content.

### Why these tools

| Tool                  | Upstream              | Replaces                   |
|-----------------------|-----------------------|----------------------------|
| `SymbolLookupTool`    | `tree-sitter`         | grep-based name search     |
| `CallerGraphTool`     | GNU GLOBAL (`gtags`)  | none - new capability      |
| `SemanticSearchTool`  | `zoekt` (self-hosted) | none - new capability      |
| `ASTSliceTool`        | `tree-sitter`         | full-file reads            |
| `FileSliceTool`       | stdlib                | `get_file_diff` (retained) |
| `SemgrepTool`         | `semgrep`             | none - new capability      |
| `CrashCorrelatorTool` | internal              | none - new capability      |

All tools implement a single `CodeTool` protocol. Code Agent holds
`list[CodeTool]` injected at construction; it never imports a tool directly.

---

## Architecture

```
aegis/code_intel/
    protocol.py         ← CodeTool protocol, ToolResult, ToolError
    index/
        gtags.py        ← GtagsIndex: subprocess wrapper (gtags / global)
        zoekt.py        ← ZoektIndex: HTTP client for zoekt-webserver
        treesitter.py   ← TreeSitterIndex: in-process, per-language grammar
    tools/
        symbol_lookup.py    ← SymbolLookupTool   (tree-sitter)
        caller_graph.py     ← CallerGraphTool    (gtags)
        semantic_search.py  ← SemanticSearchTool (zoekt)
        ast_slice.py        ← ASTSliceTool       (tree-sitter)
        file_slice.py       ← FileSliceTool      (stdlib, replaces FilesystemCodeAdapter.get_file_diff)
        semgrep.py          ← SemgrepTool        (semgrep subprocess)
        crash_correlator.py ← CrashCorrelatorTool (crash stack → symbol set → CallerGraph)
    react/
        loop.py         ← ReActLoop: reason → tool → observe cycle
        context.py      ← ToolContext: per-run state (budget, history, repo root)
        budget.py       ← TokenBudget: tracks context spend, halts loop on exhaustion
    agent.py            ← CodeAgent: updated to own ReActLoop + injected tools
    exceptions.py       ← IndexNotReadyError, ToolExecutionError, BudgetExceededError

aegis/backends/code/
    filesystem_adapter.py   ← KEPT for blame/mtime history (no change to contract)
    git_adapter.py          ← existing (unchanged)

tests/code_intel/
    conftest.py
    fixtures/
        audacity_stub/      ← minimal C++ stub mimicking Audacity structure
        python_stub/        ← minimal Python stub
        crashdumps/         ← sample minidump + symbolicated stack fixtures
        logs/               ← sample structured log fixtures
    unit/
        test_protocol.py
        test_gtags_index.py
        test_zoekt_index.py
        test_treesitter_index.py
        test_symbol_lookup.py
        test_caller_graph.py
        test_semantic_search.py
        test_ast_slice.py
        test_file_slice.py
        test_semgrep.py
        test_crash_correlator.py
        test_react_loop.py
        test_token_budget.py
    integration/
        conftest.py         ← skips when index binaries absent
        test_gtags_live.py
        test_zoekt_live.py
        test_semgrep_live.py
        test_react_loop_live.py
        test_end_to_end_audacity.py ← full pipeline: crash → verdict

docs/
    code-intel-architecture.md
    code-intel-config-reference.md
    code-intel-tool-authoring-guide.md
```

**Hard boundary:** `aegis/core/` and `aegis/ui/` must never import
`tree_sitter`, `semgrep`, subprocess wrappers for `gtags`/`zoekt`, or any
other index client. All code intelligence is mediated through the `CodeTool`
protocol. Enforced by a `grep` check in CI identical in structure to the
LiteLLM boundary check.

---

## Tasks

| Task | Name                        | Category       | Output                                                                                     |
|------|-----------------------------|----------------|--------------------------------------------------------------------------------------------|
| 01.0 | CodeTool Protocol & Types   | infrastructure | `protocol.py`, `exceptions.py` - zero external dependencies                                |
| 02.0 | Index Backends              | infrastructure | `index/gtags.py`, `index/zoekt.py`, `index/treesitter.py` - subprocess / HTTP / in-process |
| 03.0 | File & AST Slice Tools      | infrastructure | `tools/file_slice.py`, `tools/ast_slice.py` - context-safe line-range reads                |
| 04.0 | Symbol & Caller Graph Tools | infrastructure | `tools/symbol_lookup.py`, `tools/caller_graph.py`                                          |
| 05.0 | Semantic Search Tool        | infrastructure | `tools/semantic_search.py` - zoekt HTTP client + query builder                             |
| 06.0 | Semgrep Tool                | infrastructure | `tools/semgrep.py` - AST-pattern queries, JSON output parsing                              |
| 07.0 | Crash Correlator Tool       | infrastructure | `tools/crash_correlator.py` - crash stack → symbol set → caller graph fan-out              |
| 08.0 | Token Budget                | infrastructure | `react/budget.py` - per-run token ceiling, per-tool cost estimation                        |
| 09.0 | ReAct Loop                  | infrastructure | `react/loop.py`, `react/context.py` - reason → tool → observe; budget-gated                |
| 10.0 | Code Agent Wiring           | integration    | `agent.py` updated; `app.py` composition; `CodeBackendSettings` extended                   |
| 11.0 | Test Suite - Unit           | testing        | All `tests/code_intel/unit/` tests; mock index backends; 100 % branch on protocol          |
| 12.0 | Test Suite - Integration    | testing        | All `tests/code_intel/integration/` tests; real binaries; skipped when absent              |
| 13.0 | End-to-End Scenario         | testing        | `test_end_to_end_audacity.py`; crash + log + code → full verdict; token budget logged      |
| 14.0 | Documentation & CI          | documentation  | Architecture doc, config reference, tool-authoring guide, CI additions                     |

Tasks 01.0 → 02.0 are sequential foundations. Tasks 03.0 – 07.0 depend on
02.0 and can proceed in parallel once 02.0 is done. Task 08.0 depends on
01.0. Task 09.0 depends on 03.0–08.0. Tasks 11.0 and 12.0 are written
**incrementally alongside** their corresponding implementation tasks. Task
10.0 depends on 09.0. Task 13.0 depends on 10.0. Task 14.0 closes the
milestone.

---

## Shared contracts (authoritative)

These contracts are defined once here; per-task READMEs reference them.

### C1 - CodeTool protocol

```python
from __future__ import annotations
from typing import Any, ClassVar, Optional
from dataclasses import dataclass, field

class CodeTool:
    """Single capability exposed to the ReAct loop."""

    name: ClassVar[str]
    description: ClassVar[str]          # shown to the model in tool selection prompt
    input_schema: ClassVar[dict]        # JSON Schema for input validation

    async def run(
        self,
        ctx: ToolContext,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the tool. Must not raise - return ToolError on failure."""
        ...

@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    content: str                        # plain-text; fits inside model context
    token_estimate: int                 # caller uses for budget accounting
    metadata: dict = field(default_factory=dict)

@dataclass(frozen=True)
class ToolError:
    tool_name: str
    reason: str
    retriable: bool = False
```

`content` is always plain text. Tools never return raw binary, never return
full files. Maximum `content` length is enforced by `TokenBudget`; a tool
that would exceed the remaining budget must truncate and set
`metadata["truncated"] = True`.

### C2 - Module isolation boundary

- `import tree_sitter` appears only in `aegis/code_intel/index/treesitter.py`
  and `aegis/code_intel/tools/` that wrap it.
- `import semgrep` / subprocess calls to `semgrep` appear only in
  `aegis/code_intel/tools/semgrep.py`.
- Subprocess calls to `gtags` / `global` appear only in
  `aegis/code_intel/index/gtags.py`.
- HTTP calls to zoekt appear only in `aegis/code_intel/index/zoekt.py`.
- `aegis/core/`, `aegis/ui/`, `aegis/router/` contain **zero** imports of
  the above. Enforced by `grep` CI test (same pattern as C2 in Milestone 0003).

### C3 - Index readiness contract

Every index backend implements:

```python
async def ensure_ready(self, repo_root: Path) -> None:
    """Build or verify the index. Idempotent. Raises IndexNotReadyError on failure."""
    ...

def is_ready(self, repo_root: Path) -> bool:
    """Non-blocking check. False if index has never been built."""
    ...
```

`ensure_ready` is called once per `ToolContext` lifetime, not per tool
invocation. CI tests use a pre-built index fixture; they never call
`ensure_ready` against the network.

### C4 - Token budget semantics

1. Each `ToolContext` is constructed with a `token_ceiling: int` (default
   from `CodeBackendSettings.react_token_ceiling`, default `32_000`).
2. `TokenBudget.charge(tool_result: ToolResult)` deducts
   `tool_result.token_estimate`. Estimate is `len(content) // 4` (GPT-style
   approximation - deliberately conservative).
3. If `remaining < tool.min_tokens` (a per-tool constant), the loop
   **halts** before invoking the tool and raises `BudgetExceededError`.
4. The loop emits a `CodeIntelBudgetEvent` on the `EventBus` at halt or
   on normal completion, carrying `ceiling`, `used`, and `remaining`.
5. `--dry-run` mode sets `token_ceiling = 0` and short-circuits every tool
   to return a `ToolResult` with `content="[dry-run]"` and
   `token_estimate=0`.

### C5 - ReAct loop protocol

The loop follows strict Reason → Act → Observe cycles:

1. **Reason:** Call `ModelRouter.complete(role="code_agent", messages=history)`
   to get the next tool invocation (structured JSON) or a `DONE` sentinel.
2. **Act:** Validate the tool name and input against `input_schema`. Call
   `tool.run(ctx, **kwargs)`. Append `ToolError` to history on failure.
3. **Observe:** Append `ToolResult.content` as an `assistant`-role message
   to `history`. Deduct from `TokenBudget`.
4. Loop terminates on `DONE`, `BudgetExceededError`, or after
   `CodeBackendSettings.react_max_iterations` cycles (default `20`).
5. Every cycle emits a `CodeIntelLoopStepEvent` on the `EventBus` carrying
   `iteration`, `tool_name`, `token_estimate`, `budget_remaining`.

History passed to the router **never** contains raw source files - only
`ToolResult.content` strings, which are already token-bounded.

### C6 - Crash correlator contract

`CrashCorrelatorTool` accepts either:

- A **symbolicated stack trace** (plain text, one frame per line), or
- A **minidump path** (`.dmp` / `.mdmp`) - in which case it shells out to
  `minidump_stackwalk` (must be on `PATH`) to symbolicate first.

Output is a `ToolResult` whose `content` is a ranked list of
`(symbol, file, line, caller_count)` tuples - the symbols most likely
causally related to the crash, ordered by call-graph fan-in. The ReAct loop
then issues `CallerGraphTool` calls for the top-N symbols.

`CrashCorrelatorTool` never calls the model; it is purely deterministic.

### C7 - Semgrep query contract

`SemgrepTool` accepts:

```json
{
  "pattern":  "string",          // semgrep pattern syntax
  "lang":     "string",          // e.g. "cpp", "python"
  "paths":    ["string"],        // relative paths within repo_root; [] = whole repo
  "severity": "ERROR|WARNING|INFO"  // optional filter
}
```

Output is truncated to `max_findings` (default `50`) findings. Each finding
includes `path`, `start.line`, `end.line`, and `message`. Raw matched source
lines are included only if they fit within `ToolResult` token budget; otherwise
only the location is returned and the agent must issue a `FileSliceTool` call
to retrieve the content.

### C8 - Zoekt query contract

`SemanticSearchTool` wraps the zoekt HTTP API. It accepts a free-text or
regex query and optional `lang` and `path_prefix` filters. Results are
ranked by zoekt's internal TF-IDF scorer. Each result carries `repo`,
`file`, `line_number`, and a context snippet of ±3 lines. The tool caps
results at `max_results` (default `20`).

Zoekt must be running as a sidecar process; `ZoektIndex.ensure_ready()`
verifies the HTTP endpoint is reachable and returns a `200` on `/` before
any search is issued. Integration tests start zoekt via `subprocess` against
the `audacity_stub` fixture and tear it down in the session fixture.

### C9 - CodeIntelEvent taxonomy

All events are `frozen=True` dataclasses on the existing `EventBus`.

| Class                       | `event_type`                    | When emitted                                |
|-----------------------------|---------------------------------|---------------------------------------------|
| `CodeIntelLoopStarted`      | `code_intel.loop.started`       | Before iteration 1                          |
| `CodeIntelLoopStepEvent`    | `code_intel.loop.step`          | After each Act + Observe                    |
| `CodeIntelLoopCompleted`    | `code_intel.loop.completed`     | On `DONE` sentinel                          |
| `CodeIntelLoopHalted`       | `code_intel.loop.halted`        | On budget exhaustion or max iterations      |
| `CodeIntelBudgetEvent`      | `code_intel.budget`             | At loop end; carries ceiling/used/remaining |
| `CodeIntelIndexReady`       | `code_intel.index.ready`        | After `ensure_ready()` succeeds             |
| `CodeIntelIndexFailed`      | `code_intel.index.failed`       | After `ensure_ready()` raises               |

### C10 - Cross-cutting conventions (inherited from 0001–0003)

- `Optional[T]` from `typing`, never `T | None` (including in subscripts).
- `from __future__ import annotations` in every new file.
- `mypy --strict` + `ruff` must stay clean.
- Every new public class / function has a docstring (RST style).
- No direct provider SDKs, no index libraries, no subprocess calls in
  `aegis/core/` or `aegis/ui/`.
- `--dry-run` short-circuits every `CodeTool.run()` to `ToolResult("[dry-run]", 0)`.
- `asyncio.sleep` for backoff - never `time.sleep`.

---

## Task specifications

### Task 01.0 - CodeTool Protocol & Types

**Subtasks (ordered):**

1. Create `aegis/code_intel/__init__.py` (empty, versioned).
2. Create `aegis/code_intel/protocol.py` containing:
   - `CodeTool` protocol class (C1).
   - `ToolResult` and `ToolError` frozen dataclasses.
   - `ToolContext` dataclass: `repo_root: Path`, `run_id: str`,
     `budget: TokenBudget`, `dry_run: bool`.
3. Create `aegis/code_intel/exceptions.py`:
   - `IndexNotReadyError(repo_root, backend_name)`.
   - `ToolExecutionError(tool_name, reason, cause)`.
   - `BudgetExceededError(ceiling, used, tool_name)`.
   - `CorrelatorError(reason)`.
4. Add `CodeIntelEvent` base and all nine event dataclasses (C9) to
   `aegis/events.py` alongside existing events.
5. Extend `CodeBackendSettings` in `aegis/config/settings.py`:
   - `react_token_ceiling: int = 32_000`
   - `react_max_iterations: int = 20`
   - `gtags_binary: str = "gtags"`
   - `global_binary: str = "global"`
   - `zoekt_url: str = "http://localhost:6070"`
   - `semgrep_binary: str = "semgrep"`
   - `minidump_stackwalk_binary: Optional[str] = None`

**Acceptance criteria:**
- `from aegis.code_intel.protocol import CodeTool, ToolResult, ToolError` imports cleanly.
- All event types round-trip through `EventBus` with zero `Any` fields.
- `mypy --strict` clean with no new ignores.
- No external dependencies introduced.

---

### Task 02.0 - Index Backends

**Subtasks (ordered):**

1. Create `aegis/code_intel/index/__init__.py`.
2. `aegis/code_intel/index/gtags.py` - `GtagsIndex`:
   - `ensure_ready(repo_root)`: runs `gtags -v` under `repo_root` if
     `GTAGS` / `GRTAGS` / `GPATH` files absent or older than 24 h.
   - `is_ready(repo_root) -> bool`.
   - `lookup_symbol(repo_root, symbol) -> list[SymbolLocation]`:
     subprocesses `global -x <symbol>`, parses tabular output.
   - `find_callers(repo_root, symbol) -> list[SymbolLocation]`:
     subprocesses `global -rx <symbol>`.
   - `SymbolLocation` frozen dataclass: `symbol`, `file`, `line`, `text`.
   - All subprocess calls use `asyncio.create_subprocess_exec`; never
     `subprocess.run` in an async path.
3. `aegis/code_intel/index/zoekt.py` - `ZoektIndex`:
   - `ensure_ready(repo_root)`: HTTP GET `/` on `zoekt_url`, raises
     `IndexNotReadyError` if not `200`.
   - `search(query, lang, path_prefix, max_results) -> list[ZoektMatch]`.
   - `ZoektMatch` frozen dataclass: `repo`, `file`, `line_number`, `snippet`.
   - Uses `httpx.AsyncClient`; injectable for testing.
4. `aegis/code_intel/index/treesitter.py` - `TreeSitterIndex`:
   - `get_parser(lang: str) -> tree_sitter.Parser`: caches `Parser` per
     language; raises `ToolExecutionError` if grammar not installed.
   - `find_symbol(source: bytes, symbol: str, lang: str) -> list[ASTNode]`.
   - `slice_function(source: bytes, symbol: str, lang: str) -> Optional[str]`:
     returns source text of the named function/method, `None` if not found.
   - `ASTNode` frozen dataclass: `type`, `start_line`, `end_line`, `text`.
   - Supported languages at milestone close: `c`, `cpp`, `python`.

**Acceptance criteria:**
- All three index classes satisfy `ensure_ready` / `is_ready` contract (C3).
- `GtagsIndex` and `ZoektIndex` are mockable by injecting a fake subprocess
  runner / `httpx.AsyncClient` respectively - no monkey-patching.
- `TreeSitterIndex` works fully offline (grammars bundled as package data).
- `mypy --strict` clean.

---

### Task 03.0 - File & AST Slice Tools

**Subtasks (ordered):**

1. `aegis/code_intel/tools/file_slice.py` - `FileSliceTool`:
   - `name = "file_slice"`
   - `input_schema`: `{"file": "string", "start_line": "integer", "end_line": "integer"}`.
   - Reads `[start_line, end_line]` inclusive from `ctx.repo_root / file`.
   - Prefixes each line with its line number (`"{n:>6} | {line}"`).
   - Enforces a hard cap of 300 lines per call; truncates and sets
     `metadata["truncated"] = True` if range exceeds cap.
   - Returns `ToolError` (non-retriable) for missing files or path traversal
     attempts (reuses `safe_repo_path` from `aegis/backends/code/_paths.py`).
2. `aegis/code_intel/tools/ast_slice.py` - `ASTSliceTool`:
   - `name = "ast_slice"`
   - `input_schema`: `{"file": "string", "symbol": "string", "lang": "string"}`.
   - Reads the file, calls `TreeSitterIndex.slice_function(...)`, returns
     the function body with start/end line metadata.
   - Falls back to `FileSliceTool` behaviour (full file, capped at 300
     lines) if symbol not found and sets `metadata["fallback"] = True`.
   - Injects `TreeSitterIndex` at construction.

**Acceptance criteria:**
- `FileSliceTool` rejects paths containing `..` with `ToolError`.
- `ASTSliceTool` returns correct start/end lines for C++ and Python fixtures.
- Both tools respect `TokenBudget`; a 301-line request returns 300 lines +
  truncation flag.
- `--dry-run` returns `ToolResult("[dry-run]", 0)` without touching disk.

---

### Task 04.0 - Symbol & Caller Graph Tools

**Subtasks (ordered):**

1. `aegis/code_intel/tools/symbol_lookup.py` - `SymbolLookupTool`:
   - `name = "symbol_lookup"`
   - `input_schema`: `{"symbol": "string", "lang": "string"}`.
   - Calls `GtagsIndex.lookup_symbol` for C/C++; `TreeSitterIndex.find_symbol`
     for Python (chosen by `lang`).
   - Returns a `ToolResult` whose `content` is a table of
     `file:line - snippet` rows, at most `max_results` (default `30`).
   - Injects `GtagsIndex` and `TreeSitterIndex` at construction.
2. `aegis/code_intel/tools/caller_graph.py` - `CallerGraphTool`:
   - `name = "caller_graph"`
   - `input_schema`: `{"symbol": "string", "depth": "integer"}`.
   - Performs a BFS of `GtagsIndex.find_callers` up to `depth` levels
     (default `2`, max `4`).
   - Returns a plain-text tree; caps total nodes at `max_nodes` (default `50`).
   - `depth > 2` emits a `CodeIntelLoopStepEvent` warning that cost may
     be high.
   - Injects `GtagsIndex` at construction.

**Acceptance criteria:**
- `CallerGraphTool` with `depth=2` on the `audacity_stub` fixture returns
  correct BFS tree without duplicates.
- `SymbolLookupTool` correctly routes `lang=cpp` to `GtagsIndex` and
  `lang=python` to `TreeSitterIndex`.
- Both tools emit `ToolError` (retriable) when the index is not ready.
- `max_nodes` cap is respected; excess nodes are replaced with `"... N more"`.

---

### Task 05.0 - Semantic Search Tool

**Subtasks (ordered):**

1. `aegis/code_intel/tools/semantic_search.py` - `SemanticSearchTool`:
   - `name = "semantic_search"`
   - `input_schema`: `{"query": "string", "lang": "string", "path_prefix": "string", "max_results": "integer"}`.
   - Calls `ZoektIndex.search(...)`.
   - Formats results as `file:line - snippet` with a header showing query
     and total hit count.
   - `max_results` defaults to `20`, hard cap `50`.
   - Returns `ToolError` (retriable) if `ZoektIndex.ensure_ready()` fails.
   - Injects `ZoektIndex` at construction.

**Acceptance criteria:**
- Tool returns correctly formatted output for mock zoekt responses.
- `max_results` cap is enforced.
- `ToolError.retriable = True` when zoekt is unreachable; `False` for
  malformed queries.
- `--dry-run` bypasses HTTP call.

---

### Task 06.0 - Semgrep Tool

**Subtasks (ordered):**

1. `aegis/code_intel/tools/semgrep.py` - `SemgrepTool`:
   - `name = "semgrep"`
   - `input_schema` per C7.
   - Runs `semgrep --json --pattern <pattern> --lang <lang> <paths>` via
     `asyncio.create_subprocess_exec`.
   - Parses JSON output; filters by `severity` if provided.
   - Truncates to `max_findings` (default `50`); sets `metadata["truncated"]`.
   - Source lines included only if they fit in remaining budget (C7).
   - `ToolError` (non-retriable) on `semgrep` parse failure.
   - `ToolError` (retriable) if `semgrep` binary not found on `PATH`.
2. Register `semgrep_binary` from `CodeBackendSettings` so the binary path
   is injectable in tests without `PATH` manipulation.

**Acceptance criteria:**
- Tool correctly parses semgrep's JSON output format for both `c` and
  `python` fixtures.
- `max_findings` cap respected.
- Binary-not-found produces retriable `ToolError`.
- JSON parse failure produces non-retriable `ToolError`.
- `--dry-run` skips subprocess call.

---

### Task 07.0 - Crash Correlator Tool

**Subtasks (ordered):**

1. `aegis/code_intel/tools/crash_correlator.py` - `CrashCorrelatorTool`:
   - `name = "crash_correlator"`
   - `input_schema`: `{"input_type": "stack|minidump", "content": "string"}`.
     For `minidump`, `content` is the absolute path to the dump file.
   - Stack parser: regex-based, handles GDB, LLDB, Windows DbgHelp, and
     Breakpad/Crashpad symbolicated formats.
   - Minidump path: shells out to `minidump_stackwalk` (path from
     `CodeBackendSettings.minidump_stackwalk_binary`). `ToolError`
     (non-retriable) if binary not configured.
   - After parsing: calls `GtagsIndex.lookup_symbol` for each frame symbol;
     ranks by `caller_count` (fan-in from `GtagsIndex.find_callers` with
     `depth=1`).
   - Returns `ToolResult` with ranked `(symbol, file, line, caller_count)`
     table, top `N=10` entries.
   - Emits `CodeIntelLoopStepEvent` with `tool_name="crash_correlator"` and
     `metadata` containing frame count and matched symbol count.
2. Add `StackFrame` and `CorrelationResult` internal dataclasses (not
   exported from `__init__.py`).

**Acceptance criteria:**
- Stack parser correctly extracts symbols from all four format fixtures in
  `tests/code_intel/fixtures/crashdumps/`.
- Ranking is deterministic (secondary sort by file path for equal
  `caller_count`).
- `minidump_stackwalk_binary = None` produces non-retriable `ToolError`
  immediately without shelling out.
- `GtagsIndex` calls are mocked in unit tests; no subprocess required.

---

### Task 08.0 - Token Budget

**Subtasks (ordered):**

1. `aegis/code_intel/react/budget.py` - `TokenBudget`:
   - `__init__(ceiling: int)`.
   - `charge(result: ToolResult) -> int`: deducts `result.token_estimate`,
     returns `remaining`. Raises `BudgetExceededError` if already at zero.
   - `remaining` property.
   - `would_exceed(estimate: int) -> bool`: non-destructive pre-check.
   - `reset()`: for test reuse.
   - `snapshot() -> BudgetSnapshot`: frozen dataclass (`ceiling`, `used`,
     `remaining`) for event payload.
2. Estimate formula: `max(1, len(content) // 4)`. Document this constant
   in a module-level docstring as an approximation subject to revision.

**Acceptance criteria:**
- `charge` raises `BudgetExceededError` exactly at zero, not below.
- `would_exceed` never mutates state.
- `snapshot()` is consistent with `remaining` at call time.
- 100% branch coverage in `tests/code_intel/unit/test_token_budget.py`.

---

### Task 09.0 - ReAct Loop

**Subtasks (ordered):**

1. `aegis/code_intel/react/context.py` - `ToolContext`:
   - `repo_root: Path`
   - `run_id: str`
   - `budget: TokenBudget`
   - `dry_run: bool`
   - `iteration: int = 0` (mutable; incremented by loop)
2. `aegis/code_intel/react/loop.py` - `ReActLoop`:
   - `__init__(router: ModelRouter, tools: list[CodeTool], settings: CodeBackendSettings, event_bus: EventBus)`.
   - `async def run(ctx: ToolContext, prompt: str) -> str`:
     implements the 5-step protocol from C5.
   - Tool selection: model returns JSON `{"tool": "<name>", "args": {...}}`
     or `{"done": "<final answer>"}`. Schema validated with `jsonschema`;
     malformed responses increment a `parse_error_count`; three consecutive
     parse errors raise `ToolExecutionError`.
   - All EventBus emissions per C9.
   - `react_max_iterations` from settings; `CodeIntelLoopHalted` on breach.
3. Tool registry: `ReActLoop._registry: dict[str, CodeTool]` built from
   `tools` list at init. Unknown tool names produce `ToolError` appended to
   history (non-fatal, loop continues).

**Acceptance criteria:**
- `run()` halts on `BudgetExceededError` and emits `CodeIntelLoopHalted`.
- `run()` halts after `react_max_iterations` and emits `CodeIntelLoopHalted`.
- Three consecutive parse errors raise `ToolExecutionError`.
- `DONE` sentinel terminates loop and emits `CodeIntelLoopCompleted`.
- All five EventBus event types are emitted in correct order in integration
  test.
- `--dry-run` produces a single-iteration loop with `NullClient` and all
  tools returning `"[dry-run]"`.

---

### Task 10.0 - Code Agent Wiring

**Subtasks (ordered):**

1. Update `aegis/code_intel/agent.py` - `CodeAgent`:
   - Constructor: `(router: ModelRouter, tools: list[CodeTool], settings: CodeBackendSettings, event_bus: EventBus)`.
   - `async def analyze(repo_root: str, prompt: str, run_id: str) -> str`:
     constructs `ToolContext`, delegates to `ReActLoop.run(ctx, prompt)`.
   - Removes any legacy `FilesystemCodeAdapter` usage for diff/search;
     `FilesystemCodeAdapter.blame()` is retained as a standalone tool if
     needed for mtime history.
2. Update `aegis/app.py`:
   - Construct index backends from settings.
   - Construct all seven `CodeTool` instances with injected backends.
   - Construct `ReActLoop` with tools + router + event_bus.
   - Construct `CodeAgent` with loop.
   - `--dry-run` flag sets `CodeBackendSettings.react_token_ceiling = 0`
     and injects `NullClient`.
3. Update `aegis/config/sources.yaml` / `agents.yaml`:
   - Add `code_agent` role with a capable model (e.g., the primary
     `self_hosted` vLLM model or `anthropic/claude-3-5-sonnet`) and
     `timeout_s: 120`, `retry.attempts: 2`.

**Acceptance criteria:**
- `python -m aegis.app --dry-run` completes without API keys or index
  binaries.
- `CodeAgent` can be constructed with all-mock tools and a mock router
  in a unit test with zero real I/O.
- `FilesystemCodeAdapter` is still importable and used for blame;
  no regressions in existing backend tests.

---

### Task 11.0 - Test Suite - Unit

**Subtasks (ordered):**

1. Create `tests/code_intel/conftest.py`:
   - `audacity_stub` session fixture: a minimal directory tree with 3–5
     `.cpp`/`.h` files, a Python helper, and a pre-built GTAGS database.
   - `mock_gtags_index`: `AsyncMock`-based `GtagsIndex` substitute.
   - `mock_zoekt_index`: `AsyncMock`-based `ZoektIndex` substitute with
     a fake HTTP response factory.
   - `mock_router`: returns structured JSON tool invocations from a
     configurable script; final message returns `{"done": "verdict"}`.
   - `token_budget_unlimited`: `TokenBudget(ceiling=999_999)`.
2. One test file per implementation file in `aegis/code_intel/`
   (see file map). Each must:
   - Cover all branches (required: 100% branch coverage on `protocol.py`,
     `budget.py`, and all `tools/`).
   - Use only mock index backends; never call real binaries.
   - Verify `ToolResult.token_estimate` is always `>= 1` for non-empty
     content.
   - Verify `--dry-run` path on every tool.
3. `test_react_loop.py`:
   - Test normal completion (`DONE` after N steps).
   - Test budget exhaustion halt.
   - Test max-iterations halt.
   - Test three consecutive parse errors → `ToolExecutionError`.
   - Test unknown tool name → `ToolError` appended, loop continues.
   - Verify event sequence on `EventBus` for each scenario.

**Acceptance criteria:**
- All unit tests pass with `ANTHROPIC_API_KEY=""` and no index binaries
  on `PATH`.
- 100% branch coverage on `protocol.py`, `budget.py`, and all `tools/`.
- No `monkeypatch` of module-level globals; all dependencies injected.

---

### Task 12.0 - Test Suite - Integration

**Subtasks (ordered):**

1. `tests/code_intel/integration/conftest.py`:
   - Session-scoped `pytest.mark.skipif` skip condition: skip entire module
     if `gtags`, `global`, `semgrep` not on `PATH` or zoekt not reachable.
   - `live_audacity_stub`: same stub as unit conftest but with real GTAGS
     index built via `gtags` subprocess in a `tmp_path` fixture.
   - `live_zoekt`: starts `zoekt-index` + `zoekt-webserver` against
     `live_audacity_stub`; tears down in `yield` finaliser.
2. `test_gtags_live.py`:
   - `lookup_symbol` returns correct locations for a symbol defined in the
     stub.
   - `find_callers` returns correct caller list with depth-1 BFS.
3. `test_zoekt_live.py`:
   - `search` returns results for a query string present in the stub.
   - `max_results` cap respected.
4. `test_semgrep_live.py`:
   - Pattern `"$X = malloc(...)"` finds the malloc call in the stub's C++.
   - Severity filter `INFO` returns superset of `ERROR`.
5. `test_react_loop_live.py`:
   - Full loop against a real `ModelRouter` (skipped without API key).
   - Verifies loop terminates in ≤ `react_max_iterations` steps.
   - Verifies budget is charged on each step.
   - Verifies all EventBus events emitted in order.

**Acceptance criteria:**
- All integration tests are **skipped** (not failed) when binaries absent.
- Integration tests that run must pass without mocks.
- No integration test leaves processes running after session end.

---

### Task 13.0 - End-to-End Scenario

**Subtasks (ordered):**

1. Add fixture `tests/code_intel/fixtures/crashdumps/audacity_null_deref.txt`:
   a realistic symbolicated Breakpad stack for a null-dereference in
   `AudioIO::StartStream` (fabricated, references stub symbols).
2. Add fixture `tests/code_intel/fixtures/logs/audacity_session.jsonl`:
   10–15 lines of structured log entries (JSON per line) leading up to
   the crash, referencing stub filenames and line numbers.
3. `tests/code_intel/integration/test_end_to_end_audacity.py`:
   - Skipped without API key + binaries.
   - Constructs the full stack: `GtagsIndex` → `CallerGraphTool` +
     `SymbolLookupTool` + `CrashCorrelatorTool` + `FileSliceTool` +
     `ASTSliceTool` + `SemanticSearchTool` + `SemgrepTool` → `ReActLoop`
     → `CodeAgent`.
   - Input: crash stack fixture + log fixture + repo root of stub.
   - Asserts: verdict string is non-empty, loop completed (not halted),
     at least one `FileSliceTool` and one `CallerGraphTool` step emitted,
     final `CodeIntelBudgetEvent` carries `used > 0`.
4. Log the full event sequence and budget snapshot to
   `tmp_path / "e2e_event_log.jsonl"` for post-hoc inspection.

**Acceptance criteria:**
- Test skips cleanly without environment.
- When run with environment: verdict is non-empty, loop does not exceed
  budget, all expected events emitted, event log written.
- No hardcoded model responses; the model drives the tool selection.

---

### Task 14.0 - Documentation & CI

**Subtasks (ordered):**

1. `docs/code-intel-architecture.md`:
   - System diagram (ASCII): crash/log input → `CrashCorrelatorTool` →
     `ReActLoop` → tools → verdict.
   - Explanation of token budget rationale and the 300-line / 50-finding
     caps.
   - Extension guide: how to add a new `CodeTool` in 5 steps.
2. `docs/code-intel-config-reference.md`:
   - All `CodeBackendSettings` fields with types, defaults, and env var
     overrides.
   - `agents.yaml` `code_agent` role example.
   - Index readiness requirements (binaries, ports).
3. `docs/code-intel-tool-authoring-guide.md`:
   - `CodeTool` protocol walkthrough with a minimal worked example.
   - `input_schema` JSON Schema conventions.
   - Token budget interaction pattern (pre-check with `would_exceed`).
   - Event emission pattern.
4. CI additions (`.github/workflows/ci.yml` or equivalent):
   - `grep` boundary check: `aegis/core/` and `aegis/ui/` contain no
     `tree_sitter`, `semgrep`, `gtags`, `zoekt` imports - job fails if
     found.
   - `pytest tests/code_intel/unit/` runs on every PR with no binaries
     required.
   - `pytest tests/code_intel/integration/ -m "not live"` runs on every PR.
   - `pytest tests/code_intel/integration/ -m live` runs on a nightly
     schedule only (requires self-hosted runner with binaries).
   - Coverage gate: unit tests must report ≥ 90% overall; ≥ 100% on
     `protocol.py` and `budget.py`.

**Acceptance criteria:**
- `grep` CI check catches a deliberately introduced `import tree_sitter`
  in `aegis/core/` and fails the build.
- All three docs render without broken internal links.
- Coverage gate is enforced in CI configuration (not just documented).

---

## Dependency graph

```
Task 01.0 (Protocol & Types)
   │
   ├──► Task 02.0 (Index Backends)
   │         │
   │         ├──► Task 03.0 (File & AST Slice Tools)
   │         ├──► Task 04.0 (Symbol & Caller Graph Tools)
   │         ├──► Task 05.0 (Semantic Search Tool)
   │         ├──► Task 06.0 (Semgrep Tool)
   │         └──► Task 07.0 (Crash Correlator Tool)
   │                    │
   │    Tasks 03–07 ────┤
   │                    ▼
   └──► Task 08.0 (Token Budget)
              │
              └──► Task 09.0 (ReAct Loop)  ◄── Tasks 03–07
                        │
                        └──► Task 10.0 (Agent Wiring)
                                   │
              Tasks 01–10 ─────────┤
                                   ├──► Task 11.0 (Unit Tests)      ← incremental
                                   ├──► Task 12.0 (Integration Tests) ← incremental
                                   └──► Task 13.0 (End-to-End)
                                              │
                              Tasks 01–13 ────┴──► Task 14.0 (Docs & CI)
```

**Minimum viable:** 01.0 → 02.0 → 03.0 → 04.0 → 07.0 → 08.0 → 09.0 →
10.0 → 11.0 (unit only) → 10.0.
**Full milestone:** all fourteen tasks including live integration tests,
end-to-end scenario, and documentation.

---

## Global acceptance criteria

- [ ] `import tree_sitter` appears only in `aegis/code_intel/index/treesitter.py`
      and `aegis/code_intel/tools/` that wrap it
- [ ] `aegis/core/` and `aegis/ui/` contain no imports of `tree_sitter`,
      `semgrep`, or subprocess calls to `gtags` / `zoekt`
- [ ] All unit tests pass with `ANTHROPIC_API_KEY=""` and no index binaries
- [ ] Integration tests are **skipped** (not failed) when binaries absent
- [ ] `python -m aegis.app --dry-run` completes with no API keys or binaries
- [ ] `CrashCorrelatorTool` correctly parses all four crash-stack format
      fixtures
- [ ] `ReActLoop` never passes a raw source file to the model - only
      `ToolResult.content` strings
- [ ] `TokenBudget` halts the loop before a tool call that would exceed ceiling
- [ ] Adding a new `CodeTool` requires only: implement protocol, add to
      `app.py` tool list - zero changes elsewhere
- [ ] Coverage: ≥ 90% overall unit; 100% on `protocol.py` and `budget.py`
- [ ] `mypy --strict`, `ruff`, `replace_optional.py --check` all clean
- [ ] All new public classes and functions have RST docstrings
- [ ] End-to-end test produces a non-empty verdict against the Audacity stub
      with a real model and real index binaries
