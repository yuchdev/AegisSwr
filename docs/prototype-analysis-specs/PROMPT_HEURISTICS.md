# Extracted Prompts, Heuristics & Regex Rules from WinCrashAnalyzer

Sorted by troubleshooting domain, ready for distribution across the Aegis SWR agent matrix.

---

## Domain 1: Crash Signature Identification

**Target Aegis SWR Agent:** `OS Kernel Agent`

### System-Level Instruction (Gemini)
```
"You are an expert Windows Kernel debugger.
Analyze the provided stack trace.
Identify the specific function and offset where the fault occurred.
Explain the Exception Code (e.g., 0xc0000005 as Null Pointer or Use-After-Free)."
```
*Source: `backends/ai/gemini.py:7–12`*

**Extracted Heuristics:**
- `0xC0000005` → Access Violation / Null Pointer Dereference / Use-After-Free
- "Identify the specific function AND offset" — the offset within the faulting module is critical, not just the module name
- Exception code interpretation is a first-pass filter before deeper stack analysis

**Assignment:** `OS Kernel Agent` — maps raw NTSTATUS codes to `FaultClass` enum; provides structured `ExceptionSummary` to downstream agents.

---

## Domain 2: Root Cause Analysis (RCA) Synthesis

**Target Aegis SWR Agent:** `Code Analyst Agent`

### System-Level Instruction (OpenAI)
```
"You are a senior Windows systems engineer.
Provide a structured analysis with the following sections:
Root Cause Analysis (RCA), Faulting Module, and Recommendation."
```
*Source: `backends/ai/openai.py:11–15`*

### User Prompt Template
```
"Analyze this crash context:\n\n{crash_data}"
```
*Source: `backends/ai/openai.py:58`*

**With user assumption:**
```
"Analyze this crash dump and provide a Root Cause Analysis:\n\n{crash_data}
\n\nAdditional User Context/Assumption:\n{assumption}"
```
*Source: `backends/ai/gemini.py:56–68`*

**Extracted Heuristics:**
- Output MUST be structured in three named sections: `Root Cause Analysis`, `Faulting Module`, `Recommendation`
- User assumptions are appended as a separate, labeled block — they guide but do not override the analysis
- "Senior systems engineer" persona sets the authority level and vocabulary expected in response

**Assignment:** `Code Analyst Agent` — receives `ExceptionSummary` + `StackTrace` from OS Kernel Agent; produces structured `RCAReport`.

---

## Domain 3: Historical Pattern Correlation

**Target Aegis SWR Agent:** `Log Historian Agent`

### History Formatting Heuristic
```python
# Sort by timestamp, newest first. Keep top 5 records.
# Format each record as:
# "[{timestamp}] Module: {faulting_module}, Code: {exception_code}\n  Analysis: {first_200_chars}..."
```
*Source: `backends/ai/gemini.py:78–101`, `backends/ai/openai.py:84–107`*

### History-Aware Prompt Variant
```
"Analyze this crash dump and provide a Root Cause Analysis:\n\n{crash_data}
\n\nRecent Crash History (newest first):\n{history_summary}"
```
*Source: `backends/ai/gemini.py:60–67`*

**Extracted Heuristics:**
- Recency bias: newest crashes are most relevant; truncate to top 5
- Per-record context is capped at 200 characters — enough for pattern hints, not full re-analysis
- History is presented as a labeled block clearly separated from the current crash data
- Crash history provides module recurrence signal: if the same `faulting_module` appears 3 of 5 recent crashes, that is high-confidence corroboration

**Assignment:** `Log Historian Agent` — maintains a rolling crash index; formats `HistorySummary` block for injection into Code Analyst Agent prompt.

---

## Domain 4: Data Noise Removal & Signal Extraction

**Target Aegis SWR Agent:** `Data Adapter` (pipeline preprocessor, not an inference agent)

### Regex: Uninformative Fill Pattern Removal
```python
_FILL_PATTERN = re.compile(r"\b0x[cC]{8}\b")
# Replaces 0xCCCCCCCC (VC++ uninitialized heap fill) with a space
```
*Source: `core/orchestrator.py:20–21, 236–244`*

### Regex: Exception Analysis Block Extraction
```python
re.search(
    r"(Exception Analysis.*?)(?=^0:000>|quit:)",
    raw_text,
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)
# Fallback: raw_text[:10000] if no match
```
*Source: `backends/debug/cdb.py:112–124`*

### Regex: DBGHELP Noise Removal
```python
re.sub(r"DBGHELP:.*?file not found\n", "", content)
# Strips "DBGHELP: ntdll.pdb - file not found" lines
```
*Source: `backends/debug/cdb.py:121`*

### Regex: Structured Field Extraction
```python
# Exception code
re.search(r"EXCEPTION_CODE:\s+\((?:NTSTATUS|HRESULT)\)\s+(0x[0-9a-fA-F]+)", text)

# Faulting module name
re.search(r"MODULE_NAME:\s+(\S+)", text)

# Debug session timestamp
re.search(r"Debug session time:\s+(.*?)\s+\(UTC", text)
```
*Source: `backends/debug/cdb.py:133, 145, 157`*

### Smart Truncation Heuristic
```
If len(crash_data) > 10,000:
    Keep first 5,000 chars  → exception context (exception code, exception address)
    Keep last 5,000 chars   → stack frames (the faulting call chain)
    Discard middle          → DLL load list, heartbeat logs, DBGHELP noise
    Insert marker: "[... middle section truncated ...]"
```
*Source: `backends/ai/openai.py:7–9, 109–125`*

### Log Line Selection Heuristic
```
Read last 100 lines from log file(s).
Prepend: "CRASH TIMESTAMP: {crash_timestamp}" for temporal correlation.
```
*Source: `core/data_sources.py:78–99`*

**Extracted Rules for Data Adapter:**
1. Strip `0xCCCCCCCC` fill patterns before sending to any AI backend
2. Strip `DBGHELP: * file not found` lines
3. Extract the "Exception Analysis" section; discard CDB session preamble
4. Apply head+tail truncation at 10,000 chars with 5,000/5,000 split
5. Log context: last N lines with crash timestamp anchor

---

## Domain 5: System Telemetry Correlation

**Target Aegis SWR Agent:** `OS Kernel Agent` / `Log Historian Agent`

*Note: The prototype has no explicit telemetry prompts. This domain is identified as a gap (see GAP_ANALYSIS.md). The following heuristic is implicit in the context assembly code.*

### Implicit Heuristic: Log–Crash Correlation
```python
unified_context = f"STACK TRACE:\n{stack_trace}\n\n"
if sources.logs and sources.logs.exists():
    log_content = sources.logs.read_logs(raw_report.get("timestamp"))
    unified_context += f"APPLICATION LOGS:\n{log_content}\n"
```
*Source: `core/orchestrator.py:68–72`*

**Extracted Heuristics:**
- Stack trace is always the primary block; logs are appended as secondary context
- Log context is labeled `APPLICATION LOGS:` to help the LLM distinguish it from kernel output
- Crash timestamp is passed to `read_logs()` to anchor log selection (though filtering is not yet implemented)

**Assignment:** Future `OS Kernel Agent` should query structured telemetry (ETW events, `journald`, `syslog`) filtered to a `±N seconds` window around the crash timestamp.

---

## Domain 6: Hypothesis Validation (Currently Absent — Gap)

**Target Aegis SWR Agent:** `Skeptic Agent`

*The prototype has NO prompt, heuristic, or code for challenging the AI's first answer.*

**Extracted Requirement from Gap:**
- The prototype accepts the first LLM response as the final answer
- No second-pass verification that the identified faulting function is actually present in the stack trace
- No check that the stated exception code matches what was extracted by regex

**Proposed Skeptic Agent Heuristic (to be built):**
```
Given:
  - extracted_exception_code = {exception_code from regex}
  - extracted_faulting_module = {module_name from regex}
  - ai_rca = {RCAReport from Code Analyst Agent}

Assert:
  - ai_rca mentions extracted_exception_code (or its semantic equivalent)
  - ai_rca mentions extracted_faulting_module
  - ai_rca does not contradict register context (rip/pc address)

If assertions fail: flag as LOW_CONFIDENCE, request re-analysis with explicit corrections.
```

---

## Heuristic Distribution Summary

| Heuristic | Current Location | Target Aegis SWR Agent |
|-----------|-----------------|------------------------|
| Exception code → fault type mapping | `gemini.py` system prompt | `OS Kernel Agent` |
| Structured RCA output format | `openai.py` system prompt | `Code Analyst Agent` |
| Top-5 history, recency-sorted | `gemini.py`, `openai.py` | `Log Historian Agent` |
| Fill pattern removal (`0xCCCCCCCC`) | `orchestrator.py` | `Data Adapter` |
| DBGHELP noise removal | `cdb.py` | `Data Adapter` |
| Exception Analysis block extraction | `cdb.py` | `Data Adapter` |
| Head+tail truncation (10k/5k/5k) | `openai.py` | `Data Adapter` |
| Last-100-lines log selection | `data_sources.py` | `Data Adapter` / `Log Historian` |
| User assumption injection | `gemini.py`, `openai.py` | `Code Analyst Agent` |
| RCA output validation | **Not implemented** | `Skeptic Agent` |
| Telemetry timestamp windowing | **Not implemented** | `OS Kernel Agent` |
