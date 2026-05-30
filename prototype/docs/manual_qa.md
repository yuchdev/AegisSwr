## 1. QA Infrastructure & Environment Setup

Before executing the scenarios, ensure the "Gold Standard" environment is prepared.

* **System:** Windows 10/11 x64 with Windows SDK installed.
* **Application Under Test (AUT):** `TestCrashApp.exe` (The tool used to generate the `.dmp` files).
* **Tool Under Test:** `WinCrashAnalyzer` (The application we designed).
* **Validation Tools:** WinDbg (for manual verification) and a SQLite Browser.
* **Pre-Flight:** Verify `GEMINI_API_KEY` or `OPENAI_API_KEY` is set in the environment.

---

## 2. Scenario 1: Access Violation (Null Pointer Dereference)

**Goal:** Verify the Analyzer identifies `0xc0000005` and points to the specific uninitialized pointer in `TestCrashApp`.

### Execution Steps:

1. **Generate Dump:** Use `TestCrashApp.exe` to trigger a Null Pointer exception.
2. **Run Analyzer:** `python cli.py analyze --dump access_violation.dmp --sym ./symbols --ai gemini --store sqlite`
3. **Inspect Logs:** Verify the Orchestrator moves through `EXTRACTING` and `ANALYZING` without `DebuggerEngineError`.
4. **Verify Result (Database):** Open `crash_reports.db` and query the latest entry.

```sql
SELECT exception_code, faulting_module, ai_analysis FROM reports ORDER BY id DESC LIMIT 1;

```

### Expected Conclusions:

* **Exception Code:** Must be exactly `0xc0000005`.
* **AI RCA:** Should explicitly mention that the crash occurred because a pointer (e.g., `pData`) was accessed before being assigned a memory address.
* **Accuracy:** The faulting line number in the AI report must match the source code of `TestCrashApp`.

---

## 3. Scenario 2: Resource Deadlock (Sync Hang)

**Goal:** Verify the Analyzer's JS Engine detects the "Circular Wait" between threads that a standard `!analyze -v` might miss.

### Execution Steps:

1. **Generate Dump:** Trigger a deadlock in `TestCrashApp.exe` (where Thread A waits for B, and B waits for A).
2. **Run Analyzer (JS Engine):**

```
python cli.py analyze --dump deadlock.dmp --sym ./symbols --engine js --ai gemini --store filesystem
```

3. **Observe Server:** Ensure `windbg_server.py` starts, receives the POST from the JS script, and shuts down.
4. **Verify Result (JSON):** Open the generated `{dump}_report.json`.

### Expected Conclusions:

* **Debugger Output:** The `raw_stack` should contain information from both offending threads.
* **AI RCA:** The report must identify a "Deadlock Condition" and list the two specific synchronization objects (Critical Sections or Mutexes) involved.
* **Logic:** The AI should suggest changing the lock acquisition order in `TestCrashApp`.

---

## 4. Scenario 3: Stack Corruption (Buffer Overrun)

**Goal:** Verify the Analyzer detects `0xc0000409` and identifies that the stack cookie (`/GS`) was compromised.

### Execution Steps:

1. **Generate Dump:** Trigger a buffer overflow in `TestCrashApp.exe` by copying a large string into a small local buffer.
2. **Run Analyzer:**

```
python cli.py analyze --dump stack_corrupt.dmp --sym ./symbols --ai openai --store sqlite
```

3. **Verify Result:** Check the AI Analysis field in the report.

### Expected Conclusions:

* **Exception Code:** Must be `0xc0000409` (Security Check Failure).
* **AI RCA:** The AI must explain that a "Stack Buffer Overrun" occurred and specifically mention that the function's return address or security cookie was overwritten.
* **Fault Detection:** It should identify the function responsible for the copy operation (e.g., `strcpy` or `memcpy` call).

---

## 5. Global Requirement Matrix (Final Validation)

To pass the QA Plan, the following "Polished" requirements must be met:

| Checkpoint | Requirement | Pass/Fail |
| --- | --- | --- |
| **Telemetry** | Does the report contain the `report_id` and `timestamp`? |  |
| **State Integrity** | Did the CLI show `INFO` logs for every state transition? |  |
| **Sanitization** | Was the `raw_stack` stripped of `DBGHELP` search errors? |  |
| **Resource Safety** | Did `cdb.exe` exit cleanly after the analysis? |  |
| **Persistence** | Does the SQLite `metadata_json` contain the model name? |  |

---
