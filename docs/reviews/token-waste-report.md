# Token Efficiency Audit: WinCrashAnalyzer Prototype vs. Aegis SWR Targets

---

## Audit Matrix

| Parameter                          | Current Prototype Behavior                                                                                                      | Source                                            | Estimated Token Impact                                                                                                       | Aegis SWR Target                                                                                                                               |
|------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| **Log processing**                 | Last 100 lines read unconditionally; no timestamp filtering despite receiving crash_timestamp                                   | `data_sources.py:94–99`                           | High waste: 100 lines × ~15 tokens ≈ 1,500 tokens of potentially unrelated log noise                                         | `Log Historian Agent` applies temporal window (±30 s around crash timestamp); deduplicates repeating heartbeat lines                           |
| **Dump ingestion**                 | Entire CDB `!analyze -v` output piped through subprocess; head+tail truncation applied only in OpenAI backend, not Gemini       | `cdb.py:69–74`, `openai.py:109–125`               | Very high: raw `!analyze -v` output is 200–800 lines; fallback char limit 10,000 chars ≈ 2,500 tokens of DLL lists and noise | `Data Adapter` pre-extracts structured fields (exception code, module, stack frames) before AI call; structured schema instead of raw text     |
| **DBGHELP noise lines**            | Regex removal applied post-subprocess but before AI, however only in `cdb.py`; JS provider does not strip these                 | `cdb.py:121`, `js_provider.py` (absent)           | Medium: CDB output typically contains 30–80 `DBGHELP: <dll> - file not found` lines ≈ 300–800 tokens                         | `Data Adapter` strips all DBGHELP noise globally before any backend sees the text                                                              |
| **Fill pattern (`0xCCCCCCCC`)**    | Regex replacement in orchestrator's `_sanitize()` method                                                                        | `orchestrator.py:236–244`                         | Low-medium: repeated fill patterns in uninitialized heap dumps inflate token count; each pattern ≈ 3 tokens                  | Applied correctly; promote to `Data Adapter` layer so it runs before all backends                                                              |
| **DLL load list in `!analyze -v`** | No explicit removal; included in the first 5,000 chars of head+tail split                                                       | `cdb.py:58–63`, `openai.py:109–125`               | High: DLL load list typically 50–200 entries × ~20 tokens ≈ 1,000–4,000 tokens                                               | `Data Adapter` extracts only `Exception Analysis` block (already done via regex); DLL list discarded unless specifically requested by an agent |
| **System prompts**                 | Recreated on every `analyze()` call; no prompt caching directive to the LLM provider                                            | `gemini.py:51–54`, `openai.py:72–79`              | Medium: system prompt ~50–80 tokens billed at full rate on each call; no cache_control                                       | Use Anthropic/Gemini prompt caching for stable system instructions; cache TTL covers repeated crash sessions                                   |
| **History injection**              | Top-5 records × (timestamp + module + code + 200-char analysis) injected as raw text into every request                         | `gemini.py:78–101`                                | Medium: history block ≈ 5 × ~60 tokens = 300 tokens added to every prompt, regardless of whether history is relevant         | `Log Historian Agent` decides if history is relevant (same module? same code?); only injects when similarity threshold met                     |
| **User assumption text**           | Appended verbatim with no length cap                                                                                            | `gemini.py:56–68`                                 | Low-medium: unbounded user input; a long assumption can add 500+ tokens unexpectedly                                         | `Data Adapter` enforces max 500 tokens on user assumption block; truncates with warning                                                        |
| **Register dump**                  | Full x64 register context (rax, rbx, rsp, rip, etc.) included inside the "Exception Analysis" block passed to AI                | raw CDB output, `cdb.py:105–124`                  | Low-medium: ~20 registers × 3 tokens ≈ 60 tokens; not useful unless the AI is specifically prompted for memory analysis      | Extract `rip`/`pc` (instruction pointer) only as structured field; omit remaining registers unless `deep_memory_analysis` mode is active       |
| **Middle section truncation**      | Applied only in OpenAI backend at 10,000-char threshold; Gemini receives untruncated text up to model context limit             | `openai.py:109–125`, `gemini.py` (absent)         | Very high for Gemini: a 50,000-char CDB output costs ~12,500 tokens; most are DLL noise                                      | Unified truncation in `Data Adapter` applies to all backends before dispatch                                                                   |
| **Crash timestamp extraction**     | Optional; logged on failure but not surfaced to user; timestamp is passed to `read_logs()` but filtering is not yet implemented | `cdb.py:150–160`, `data_sources.py:94–99` comment | Medium: without timestamp filtering, log context includes pre-crash activity unrelated to the failure                        | Mandatory timestamp extraction; log filtering gated on timestamp; missing timestamp → warning + `log_context = None`                           |

---

## Token Waste Baseline Estimate (Per Analysis Request)

| Waste Category                                            | Estimated Wasted Tokens | Priority |
|-----------------------------------------------------------|-------------------------|----------|
| DLL load list in `!analyze -v` output                     | 1,000–4,000             | Critical |
| Unfiltered log lines (100-line tail, no timestamp window) | 500–1,500               | High     |
| DBGHELP noise lines                                       | 300–800                 | High     |
| Untruncated Gemini input (no head+tail limit)             | 0–10,000 (spike)        | High     |
| History injection when not relevant                       | 0–300                   | Medium   |
| System prompt not cached                                  | 50–80 per call          | Medium   |
| Full register dump in context                             | ~60                     | Low      |
| Uncapped user assumption text                             | 0–500 (spike)           | Low      |
| Fill pattern repetition                                   | 0–200                   | Low      |
| **Worst-case total per request**                          | **~17,440 tokens**      | -        |
| **Best-case total (already handled paths)**               | **~400 tokens**         | -        |

---

## Algorithmic Target Guidelines for the Data Adapter Layer

### Rule 1: Extract-then-Send (not Send-then-Truncate)

The prototype truncates raw text after the AI call buffer fills. The Data Adapter must extract structured fields **before** any AI call. Only extracted fields and a compact, pre-filtered text block travel to the AI.

**Structured fields to extract in Data Adapter:**
```
exception_code:        str   (from regex, validated against FaultClass enum)
exception_address:     str   (instruction pointer / RIP)
faulting_module:       str   (MODULE_NAME field)
faulting_function:     str   (top of call stack)
stack_frames:          list  (top N frames, default N=20)
debug_timestamp:       str   (UTC, from "Debug session time:")
registers_rip_only:    str   (instruction pointer only)
```

AI receives a compact JSON object + a short free-text block, not raw debugger output.

### Rule 2: Temporal Log Windowing

```
log_window = ±30 seconds around crash_timestamp
discard lines outside window
deduplicate consecutive identical lines (heartbeat flattening): keep first + count
```
Estimated reduction: 60–80% of typical application log volume.

### Rule 3: Global Noise Pre-Filter Pipeline

Apply in order before any text leaves Data Adapter:
1. Strip `DBGHELP: .* file not found` lines
2. Replace `0xCCCCCCCC` (and `0xDDDDDDDD`, `0xFEEEFEEE`, `0xABABABAB`, `0xBAADF00D`) with `<fill>`
3. Drop DLL load list (all lines between `\*\*\* WARNING:` and `EXCEPTION_ANALYSIS:`)
4. Apply head+tail truncation at 8,000 chars (4,000/4,000 split - tighter than prototype's 10k/5k/5k)

### Rule 4: Prompt Caching for System Instructions

All stable system prompts (agent role, output schema, diagnostic taxonomy) must use the provider's prompt caching API:
- Anthropic: `cache_control: {"type": "ephemeral"}` on the `system` block
- Gemini: `cached_content` API for system instruction
- Estimated savings: system prompt re-billed at ~10% of the normal rate on cache hits

### Rule 5: Conditional History Injection

Only inject crash history if:
- `faulting_module` matches a module that appears in ≥2 of the last 10 records, **or**
- `exception_code` matches a code that appears in ≥3 of the last 10 records

Otherwise, omit history block entirely (saves ~300 tokens per non-recurring crash).

### Rule 6: Structured Output Instead of Markdown Free-Text

Request AI output as JSON with a defined schema (`RCAReport`) rather than a free-form Markdown string. Eliminates reparsing overhead and reduces output token count by removing Markdown decorators (`##`, `**`, `---`) which add ~5–10% token overhead to typical RCA responses.

---

## Summary

The prototype's primary token inefficiency is **passing raw debugger output to the AI without pre-extraction of structured fields**. The DLL load list and DBGHELP noise alone can contribute 1,000–4,000 wasted tokens per request - more than the actual signal content in many short stack traces. The Aegis SWR Data Adapter layer eliminates this by acting as a structured extraction pipeline, ensuring that only high-information-density, pre-validated fields reach the inference layer.
