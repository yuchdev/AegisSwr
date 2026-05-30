# Core Logic: Orchestrator & Exceptions

## Overview

The **Core** manages the lifecycle of a crash-analysis transaction, moving data
from a raw memory dump through debug extraction, AI inference, and final
persistence while maintaining a strict internal state machine.

---

## Sequence Diagram

```
CLI
 │
 │  process(dump_path, sym_path, assumption)
 │                               ▲
 ▼                               │ (Optional context/theory)
CrashOrchestrator
 │
 │  extract(dump_path, sym_path)
 ▼
DebugBackend (cdb.exe / JS Provider)
 │  returns raw stack-trace string
 │
 │  _sanitize(raw_data)   ← strips 0xCCCCCCCC fill patterns
 │
 │  analyze(sanitized_text, assumption)
 ▼
AIBackend (Gemini / OpenAI)
 │  returns Markdown Root-Cause Analysis
 │
 │  save({"dump": …, "raw": …, "analysis": …})
 ▼
StorageBackend (Filesystem / SQLite)
 │  persists record
 │
 ▼
CLI ← diagnosis string returned
```

---

## State Matrix

| State        | Description                                          | Killed-During Impact                                      |
|--------------|------------------------------------------------------|-----------------------------------------------------------|
| `IDLE`       | Orchestrator created, no work started.               | No side effects.                                          |
| `EXTRACTING` | `cdb.exe` / JS provider subprocess running.          | Subprocess may become a zombie; OS reaps it on process exit. |
| `ANALYZING`  | HTTP request to AI API in flight.                    | No persistent state changed; request is simply abandoned. |
| `STORING`    | Writing record to filesystem or SQLite.              | DB/file may have a partial record; re-run will overwrite. |
| `COMPLETED`  | All stages finished successfully.                    | No impact; the full record is already on disk.            |

---

## Exception Hierarchy

```
WinCrashError (base, carries .code)
├── DumpFileNotFoundError
├── DebuggerNotFoundError
├── DebuggerError
│   └── SymbolMismatchError
├── AIBackendError
├── ProviderCallbackError
└── StorageBackendError
```

`WinCrashAnalyzerError` and `StorageError` are retained as backwards-compatible
aliases for `WinCrashError` and `StorageBackendError` respectively.

---

## Graceful Degradation

If the AI stage raises `AIBackendError`, the orchestrator catches it, persists
the raw extraction data with `analysis = "AI Analysis Unavailable"`, then
re-raises so the caller can decide whether to retry.

If the storage stage raises `OSError` (e.g. disk full), it is wrapped in
`StorageBackendError` and propagated to the caller.

---

## Release No-PDB Regime

When symbols (PDB files) are unavailable for the target application, the analyzer still extracts a stack trace. In this "Release No-PDB" regime:
- The `DebugBackend` (CDB) uses the Microsoft Symbol Server for system libraries but leaves the application frames as module offsets (e.g., `CrashUi+0x1234`).
- The `Orchestrator` bundles this information along with any provided `LogSource` and `assumption` text.
- The `AIBackend` receives the `assumption` separately, allowing it to provide a more focused diagnosis even without symbol information.

---

## Edge-Case Mitigations

| Edge Case             | Mitigation                                                               |
|-----------------------|--------------------------------------------------------------------------|
| CDB hangs             | Caller should use `subprocess.run(timeout=300)` inside `DebugBackend`.   |
| Missing symbols       | `!analyze -v` output contains "unresolved"; surface as a `WARNING` log.  |
| Massive dump output   | Stream debugger stdout line-by-line instead of `stdout.read()`.          |
| API rate limit        | `AIBackendError` is raised; caller may wrap backend with exponential backoff. |
| Zombie JS server      | Ensure `WinDbgServer.stop()` is called in a `finally` block or `__exit__`. |
