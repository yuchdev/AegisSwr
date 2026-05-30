# Prototype Gap Analysis: Conceptual Vulnerabilities & the Bridge to Aegis SWR

---

## Gap 1: Tunnel Vision — Single-Prompt, No Skeptic Pass

**Severity: Critical**

### What the Prototype Does
Every crash analysis is a single API call. The LLM receives a context block and returns one response. That response is written directly to storage as the final `ai_analysis` value.

**Evidence:**
- `backends/ai/gemini.py:70–74`: Single `generate_content()` call, no follow-up
- `backends/ai/openai.py:72–79`: Single `create()` call, no follow-up
- `core/orchestrator.py:82`: `return ai_backend.analyze(...)` — result stored without validation

### The Problem
The LLM's first answer is statistically influenced by the most prominent token patterns in the context window. If the DLL load list is long, the first plausible module name in that list may dominate the response — even if the actual faulting module is deeper in the stack. There is no mechanism to challenge this.

**Specific failure mode observed in prototype test assets:** `raw_cdb_output.txt` contains 50+ DBGHELP module names before the actual `EXCEPTION_ANALYSIS` block. A prompt-unaware model may anchor on early module mentions.

### Aegis SWR Solution
Introduce a **Skeptic Agent** as a mandatory second pass:
- Receives: `(original_crash_context, RCAReport from Code Analyst Agent)`
- Task: Challenge the RCA. Verify that the stated faulting function appears in the stack. Check that the stated exception code matches the extracted `exception_code` field. Propose alternative root causes if evidence is ambiguous.
- Output: `VerificationVerdict {confidence: HIGH|MEDIUM|LOW, challenges: list[str], confirmed: bool}`
- If `confirmed=False` or `confidence=LOW`: trigger re-analysis with corrections injected into the Code Analyst Agent prompt.

---

## Gap 2: No Discarded Rationale — Opaque Reasoning Trail

**Severity: High**

### What the Prototype Does
The `ai_analysis` field in `CrashReportEntity` stores only the final AI text string. No intermediate reasoning, no alternative hypotheses considered, no rejected explanations.

**Evidence:**
- `core/data_schema.py`: `ai_analysis: str` — single string field, no structured reasoning capture
- `backends/ai/gemini.py:74`: `return response.text` — raw string only
- `backends/ai/openai.py:80`: `return response.choices[0].message.content` — raw string only

### The Problem
When a user disagrees with the RCA or suspects the AI missed something, there is no audit trail to inspect. The user cannot see what alternative modules the LLM considered and dismissed, what evidence led to the conclusion, or whether the conclusion was high- or low-confidence.

### Aegis SWR Solution
Replace the `ai_analysis: str` field with a structured `InvestigatorsRationale` object:
```json
{
  "primary_hypothesis": {
    "root_cause": "...",
    "faulting_module": "...",
    "confidence": "HIGH",
    "supporting_evidence": ["stack frame X", "exception code Y"]
  },
  "alternative_hypotheses": [
    { "root_cause": "...", "rejection_reason": "..." }
  ],
  "skeptic_challenges": ["..."],
  "recommendation": "...",
  "agent_dialogue_log": [...]
}
```
This forms the **editable Investigator's Rationale** audit trail described in the product specification.

---

## Gap 3: Silent Service Lockups — No Non-Crash Scenario Support

**Severity: High**

### What the Prototype Does
The entire pipeline is triggered by `.dmp` file input. There is no entry point for a scenario where a service is frozen or degraded without producing a crash dump.

**Evidence:**
- `cli.py:22–26`: Validates `.dmp` extension; rejects anything else
- `core/data_sources.py`: `SourceCollection` requires `dump_path`; `logs` is optional
- `core/orchestrator.py:55`: Pipeline begins by calling `debug_backend.extract(sources.dump_path, ...)`

### The Problem
A frozen background service that logs errors but stays alive produces no `.dmp` file. The prototype cannot analyze it at all. This covers a large class of production incidents: memory leaks that don't trigger a crash, deadlocks, CPU saturation, and RPC timeout cascades.

### Aegis SWR Solution
Extend `SourceCollection` to support **non-crash modes**:

| Mode | Trigger | Primary Input | Handling Agent |
|------|---------|---------------|----------------|
| `CRASH_DUMP` | `.dmp` file provided | Minidump binary | `OS Kernel Agent` (current) |
| `LOG_FORENSICS` | Log files only | Structured/unstructured text | `Log Historian Agent` |
| `LIVE_PROCESS` | PID or service name | ETW / procfs stream | `OS Kernel Agent` (phase 3) |
| `TELEMETRY_ANOMALY` | Metric threshold breach | Time-series data | `OS Kernel Agent` + `Log Historian` (phase 3) |

The `Orchestrator` selects a pipeline variant based on `SourceCollection.mode`, not only on the presence of a dump file.

---

## Gap 4: Deduplication by Filename — Not by Content

**Severity: Medium**

### What the Prototype Does
The cache-hit check compares `(dump_filename, ai_model)`:
```python
existing = self.storage_backend.find_report(dump_filename, self.ai_backend.model_name)
```
*Source: `core/orchestrator.py:59–62`*

The `dump_hash` field exists in the schema but is computed **after** the AI analysis and stored only for later reference — not used for deduplication.

### The Problem
- Renaming a `.dmp` file causes a full re-analysis of an already-processed crash.
- Two identical dumps at different paths are analyzed twice.
- Switching AI backends (Gemini → OpenAI) re-analyzes the same dump — no cross-model deduplication.

### Aegis SWR Solution
- Compute `dump_hash` (SHA-256 of file content) **before** any backend call.
- Use `dump_hash` as the primary deduplication key.
- Store one `CrashReportEntity` per `(dump_hash)`, with a `analyses` array containing one entry per `(ai_model, timestamp)`.
- This also enables the `Log Historian Agent` to detect truly recurring crashes (same binary content) across renames or moves.

---

## Gap 5: No Output Schema Validation — AI Response Drift

**Severity: Medium**

### What the Prototype Does
The OpenAI system prompt requests "Root Cause Analysis, Faulting Module, and Recommendation" sections. There is no code that verifies these sections actually appear in the response.

**Evidence:**
- `backends/ai/openai.py:80`: Returns `response.choices[0].message.content` — raw Markdown string
- `core/orchestrator.py:82–97`: Stores the string directly in `CrashReportEntity.ai_analysis`
- No regex or schema check on the response structure

### The Problem
LLMs occasionally produce responses in different formats under edge conditions (very long context, unusual crash patterns, API-side model updates). When the format drifts, the stored `ai_analysis` may be missing the `Faulting Module` section — silently, with no error raised.

### Aegis SWR Solution
- Define `RCAReport` as a JSON schema and use structured output APIs (OpenAI: `response_format={"type": "json_schema", ...}`; Gemini: `response_schema=...`).
- The AI backends return a validated `RCAReport` object, not a raw string.
- If the model fails to produce a valid schema (rare), raise `AIOutputValidationError` and retry once with an explicit correction prompt.

---

## Gap 6: No Discussion / Multi-Turn Context

**Severity: Medium**

### What the Prototype Does
Each call to `analyze()` is stateless. History is injected as a formatted text block, not as a true conversation. The user cannot ask a follow-up question like "What if the issue is in the thread pool, not the faulting module?"

**Evidence:**
- `backends/ai/gemini.py:70–74`: No multi-turn `chat` session; single `generate_content()` call
- `backends/ai/openai.py:72–79`: No `messages` conversation array; single-element message list

### The Problem
Crash investigation is inherently iterative. The first RCA is a hypothesis. A senior engineer typically asks 2–3 follow-up questions (checking thread states, examining registers, testing alternative hypotheses) before accepting a conclusion. The prototype forces this iteration to happen outside the tool.

### Aegis SWR Solution
- Persist the `agent_dialogue_log` from the `InvestigatorsRationale` as a resumable multi-turn conversation.
- Expose a `continue_analysis(session_id, user_question)` API that appends to the conversation and re-invokes the agent chain.
- The GUI presents this as a chat-style interface alongside the structured RCA — the **Investigator's Rationale** panel.

---

## Gap 7: No Symbol Resolution Quality Signal

**Severity: Low–Medium**

### What the Prototype Does
The debug backend runs `.reload /f /i` to force symbol loading. If symbols are unavailable, the stack trace contains `<unloaded module>` or raw hex addresses. The prototype passes this unresolved trace to the AI without flagging the degraded quality.

**Evidence:**
- `cdb.py:58–63`: CDB command sequence includes `.reload /f /i` but no post-run symbol quality check
- `docs/core_logic.md:99`: Comment notes "output contains 'unresolved'" as a known issue — no automated handling

### The Problem
An AI analysis of an unresolved stack trace will be significantly less accurate. The prototype gives no indication to the user that the analysis confidence is reduced.

### Aegis SWR Solution
- After extraction, scan stack frames for `<unloaded>`, `<unresolved>`, or `??!??` patterns.
- Compute a `symbol_resolution_score` (0–100%): fraction of frames with resolved symbols.
- If score < 50%, prepend `[LOW SYMBOL COVERAGE: {score}%]` to the AI context and include it in `RCAReport.confidence_factors`.
- Surface this score in the GUI with a remediation suggestion (check symbol path, sync symbol server).

---

## Gap Summary: Mapping to Aegis SWR Agent Matrix

| Gap | Severity | Aegis SWR Component That Resolves It |
|-----|----------|--------------------------------------|
| Single-prompt tunnel vision | Critical | `Skeptic Agent` (mandatory second pass) |
| No reasoning audit trail | High | `InvestigatorsRationale` schema + agent dialogue log |
| No non-crash scenario support | High | `Log Historian Agent`, `OS Kernel Agent` live mode (Phase 3) |
| Filename-based deduplication | Medium | Content-hash (`dump_hash`) primary key in storage |
| No AI output schema validation | Medium | Structured output APIs + `AIOutputValidationError` retry |
| No multi-turn investigation | Medium | Resumable `agent_dialogue_log` + GUI chat interface |
| Symbol resolution quality blind | Low–Medium | `symbol_resolution_score` field + `Data Adapter` flag |
