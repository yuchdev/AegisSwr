# Aegis SWR vs. WinCrashAnalyzer Prototype — Reproduction Report

**Date:** 2026-05-31
**Author:** generated during a real-dump validation run
**Subject incident:** `C:\LBS\CrashDumps\CrashUi.exe.1324.dmp` (84,359,313 bytes,
`sha256:fc23b792c59ce7c153d439e76c9a37c5b7e48acb7ddb3815b19a8b813990b3c2`)
**Question under test:** *"There's probability that the crash was deliberately injected. Check this theory."*

---

## 1. Objective

Take a crash incident that the **WinCrashAnalyzer prototype** already resolved with a
single LLM call, and reproduce the same resolution through the **Aegis SWR** production
pipeline (Data Adapter → multi-agent Synthetic War Room → storage), using the simplest
backends:

| Concern      | Choice                                                                                                                                                               |
|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Debug engine | `CdbBackend` (`cdb.exe`, Debugging Tools for Windows)                                                                                                                |
| AI backend   | OpenAI (`gpt-5.4`)                                                                                                                                                   |
| Storage      | `FilesystemStore` (JSON reports on disk)                                                                                                                             |
| Code backend | **none** — a PDB carries both debug symbols *and* (optionally) build provenance; symbol resolution is the Debug Backend's job, so no separate code backend was wired |
| Log backend  | **skipped** — dump-only                                                                                                                                              |

The success bar: Aegis must reach *at least* the prototype's conclusion — a deliberate
NULL-pointer write in `CrashUi!Crash_Window::on_access_violation_click`.

---

## 2. The incident

`CrashUi.exe` is a deliberate crash-test harness. The captured dump is a user-mode
`0xC0000005` access violation. The faulting instruction writes `0x2A` through a register
holding `0` (`mov dword ptr [r14],2Ah` with `r14=0`), in a button-click handler explicitly
named `on_access_violation_click`. `!analyze -v` buckets it as
`NULL_POINTER_WRITE_c0000005_CrashUi.exe!Crash_Window::on_access_violation_click`.

---

## 3. Method

### 3.1 Prototype (single-call pipeline)

```text
cdb.exe -z <dump> -c '.sympath "srv*c:\symbols*https://msdl.microsoft.com/download/symbols";
                       .reload /f /i; !analyze -v; q'
   → parse "Exception Analysis" section (strip DBGHELP noise)
   → one OpenAI chat.completions call (gpt-5.x), system prompt:
     "senior Windows systems engineer … RCA, Faulting Module, Recommendation"
   → save JSON report to filesystem
```

The prototype additionally fed `CrashUi.log` and prior-report history into the prompt.

### 3.2 Aegis SWR (multi-agent pipeline)

```powershell
$env:AEGIS_SYMBOL_CACHE='c:\symbols'   # reuse the prototype's cached symbols
uv run aegis analyze `
  --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' `
  --engine cdb --ai openai `
  --store filesystem --store-config '.\reports' `
  --assume "There's probability that the crash was deliberately injected. Check this theory" `
  --output json --severity INFO
```

Internally:

```text
IncidentSource
  → Data Adapter  (hash → CDB extract → noise filter → log/PII/assumption stages → IncidentBrief)
  → MAS state graph (LangGraph):
        OS Kernel  → Code Analyst → Log Historian → Skeptic → [consensus] → Output Synthesizer
  → FilesystemStore (RCAReport JSON)
```

CDB is invoked as
`cdb.exe -z <dump> -y srv*c:\symbols*https://msdl.microsoft.com/download/symbols -c ".reload /f /i; !analyze -v; q"`
— the same engine and symbol chain as the prototype, expressed via the `-y` flag.

---

## 4. Result — side by side

| Dimension                   | Prototype (1 GPT call)                            | Aegis SWR (4-agent MAS)                                                        |
|-----------------------------|---------------------------------------------------|--------------------------------------------------------------------------------|
| Root cause                  | Deliberate NULL-pointer **write**                 | **Match** — "deliberately injected … write through a null pointer"             |
| Faulting module             | `CrashUi.exe`                                     | `CrashUi` ✔                                                                    |
| Faulting function           | `Crash_Window::on_access_violation_click`         | **Match** ✔                                                                    |
| Exception                   | `0xC0000005` access violation                     | **Match** ✔                                                                    |
| Source line                 | (not isolated)                                    | `CrashUi.cpp:121` ✔ (from resolved symbols)                                    |
| Deliberate-injection theory | Confirmed (intentional, *not* external injection) | **Match** — Skeptic confirmed, citing the failure-bucket name and handler name |
| Output shape                | Prose: RCA / Faulting Module / Recommendation     | Structured `RCAReport` + turn-by-turn dialogue + probabilistic-fix diff        |
| Confidence                  | implicit ("high")                                 | **0.97 (HIGH)**, explicit weighted consensus                                   |
| Rounds                      | 1 (single shot)                                   | Converged in **1 debate round**                                                |
| Symbol resolution           | full                                              | `symbol_resolution_score = 1.0`                                                |
| Tokens (Aegis run)          | n/a                                               | 21,489 in / 2,029 out                                                          |

**Verdict: parity reached, and exceeded** — Aegis matched the prototype's conclusion and
additionally produced a reasoning trail (four agents), a quantified consensus score, and a
concrete code fix.

---

## 5. Aegis SWR output (verbatim)

### 5.1 Primary conclusion

> The crash was most likely deliberately injected in the UI click handler
> `Crash_Window::on_access_violation_click` by performing write through a null pointer
> (classic fault-injection pattern such as `*(int*)nullptr = ...` or equivalent). The logical
> path is: user clicks a button → UI framework lambda bound in `Crash_Window` constructor fires
> → message dispatch enters `Crash_Window::on_access_violation_click` → handler executes
> intentional null-pointer write → `0xC0000005` write AV at source line 121.

### 5.2 Evidence (primary hypothesis)

- `AV.Dereference = NullPtr` and `AV.Fault = Write` — signature of a null-pointer write.
- Failure bucket `NULL_POINTER_WRITE_c0000005_CrashUi.exe!Crash_Window::on_access_violation_click`.
- Clean button/message-handler stack: `ButtonWndProc*` → window proc → constructor-installed lambda → `on_access_violation_click`.
- The handler name `on_access_violation_click` indicates a crash-test/injection button.
- Symbols resolved fully (`symbol_resolution_score = 1.0`), exact source `CrashUi.cpp:121`.
- No kernel/driver/OOM/I/O/race evidence; crash is synchronous on button click.

### 5.3 Agent dialogue (round 1)

| Agent         | Conf | Message (summary)                                                                                                                                                      |
|---------------|------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| OS Kernel     | 0.97 | Write AV in CrashUi on a button/message-handler path; `AV.Dereference=NullPtr`, `AV.Fault=Write` → null-pointer write, not kernel/driver/I/O.                          |
| Code Analyst  | 0.99 | Deliberate null-pointer write in `on_access_violation_click`; full click→dispatch→handler path; `0xC0000005` at line 121.                                              |
| Log Historian | 0.97 | First-seen signature (no history provided); naming + stack + bucket strongly support deliberate injection; small confidence reduction for lack of recurrence evidence. |
| Skeptic       | 0.90 | **Confirmed (high)**; the stated module/function appear in the trace, the code is consistent with the exception, and no external-injection evidence exists.            |

Weighted consensus = **0.967 (HIGH)** → converged in one round → Output Synthesizer.

### 5.4 Probabilistic fix (sandbox-ready diff, confidence 0.97)

```diff
--- a/src/CrashUi/CrashUi.cpp
+++ b/src/CrashUi/CrashUi.cpp
@@
 void Crash_Window::on_access_violation_click()
 {
-    // intentional crash for testing
-    *static_cast<volatile int*>(nullptr) = 1;
+    // Avoid deliberate null-pointer write in production builds.
+    // If crash testing is needed, gate it explicitly behind a debug-only switch.
+#if defined(_DEBUG)
+    if (allow_fault_injection_)
+    {
+        __debugbreak();
+        return;
+    }
+#endif
+
+    // Production-safe behavior: report instead of crashing.
+    show_status(L"Access violation test is disabled.");
 }
```

The prototype described this remediation in prose ("gate the crash path behind a feature
flag / `#ifdef DEBUG`"); Aegis emitted it as an applicable unified diff.

---

## 6. Engine upgrades required to reach parity

Running the prototype's scenario through Aegis surfaced five concrete backend defects/gaps.
Each was fixed and unit-tested; all are recorded as authoritative as-built notes in
`docs/specs/PRODUCTION_DESIGN_SPEC.md` (§6.1.1, §6.2.1).

| # | Symptom                                                                                                                     | Fix                                                                                                                                                                         | Where                            |
|---|-----------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------|
| 1 | `--ai openai` still sent the Anthropic default model `claude-sonnet-4-6` → OpenAI 404                                       | `AISettings.resolved_model` substitutes the provider default (`gpt-5.4`) only when the configured model doesn't match the provider                                          | `config/settings.py`             |
| 2 | gpt-5-class reasoning models reject `max_tokens` and non-default `temperature`                                              | `OpenAIBackend._completion_kwargs()` sends `max_completion_tokens` (16k floor so reasoning doesn't starve the answer) and omits `temperature` for reasoning models          | `backends/ai/openai_provider.py` |
| 3 | A transient `APITimeoutError` at the `skeptic_node` aborted the whole graph (run 2)                                         | OpenAI client built with `timeout=300s`, `max_retries=4` (SDK exponential backoff)                                                                                          | `backends/ai/openai_provider.py` |
| 4 | Fault code mis-extracted → `FaultClass.UNKNOWN`; OS Kernel agent noted "exception_code_raw as 0x0"                          | `_extract_exception_code` now matches all four `!analyze -v` keys (`EXCEPTION_CODE` / `ERROR_CODE` / `EXCEPTION_CODE_STR` / `ExceptionCode`) → `MEMORY_ACCESS_VIOLATION`    | `backends/debug/cdb_worker.py`   |
| 5 | `symbol_resolution_score = 0.0` despite perfect symbols; structured `stack_frames` empty (LLM recovered only from raw text) | `parse_cdb_frames` rewritten to handle the real `!analyze -v` STACK_TEXT format (`<csp> <ret> : args : CallSite`, backtick 64-bit addresses) in addition to the `kn` format | `backends/debug/cdb_worker.py`   |

Defects #4 and #5 were inherited from the prototype's regexes; they were invisible there
because the prototype hands the *raw* `!analyze` text to the LLM and never relies on
structured extraction. Aegis's MAS consumes a *structured* `IncidentBrief`, so the bugs
became observable (and matter: the Skeptic's assertion checks and the weighted-consensus
fault-class weights both depend on correctly parsed frames).

### Effect of fix #5

|                           | Before fix #5                     | After fix #5                     |
|---------------------------|-----------------------------------|----------------------------------|
| `symbol_resolution_score` | 0.0 (false "LOW SYMBOL COVERAGE") | 1.0                              |
| Structured `stack_frames` | empty                             | fully populated                  |
| Consensus                 | 0.964                             | 0.97                             |
| Input tokens              | 17,263                            | 21,489 (frames now in the brief) |

---

## 7. Where Aegis adds value over the prototype

- **Reasoning trail:** four specialist personas (OS Kernel, Code Analyst, Log Historian,
  Skeptic) with an adversarial confirmation step, instead of one opaque answer.
- **Quantified consensus:** a weighted score per fault class, with explicit convergence /
  HITL termination rules.
- **Structured output:** a typed `RCAReport` (queryable, dedup-able by `dump_hash`) rather
  than free-form prose.
- **Actionable fix:** a unified diff with a fix-confidence score, ready for the secure
  sandbox validator (Phase 9).
- **PII scrubbing & token budgeting** run before any text reaches the LLM.

---

## 8. Reproduction

```powershell
$env:AEGIS_SYMBOL_CACHE='c:\symbols'
uv run aegis analyze `
  --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' `
  --engine cdb --ai openai `
  --store filesystem --store-config '.\reports' `
  --assume "There's probability that the crash was deliberately injected. Check this theory" `
  --output rich
```

Requires: Windows + `cdb.exe` on PATH, `OPENAI_API_KEY` set, `uv sync --group dev` complete.
Gate status at time of writing: **277 tests pass**, `ruff` clean, `mypy --strict` clean (52 files).

---

## 9. Known limitations / follow-ups

1. **Dedup gate bypassed from the CLI.** `Orchestrator.run` checks
   `find_by_hash(source.dump_hash)`, but the CLI builds `IncidentSource` *without*
   pre-computing `dump_hash` (it is computed later inside Data Adapter Stage 1). So every
   CLI invocation re-analyzes instead of returning the cached report. The prototype dedups by
   filename+model. *Fix:* hash the dump in the CLI (or a pre-Stage) before the gate.
2. **`mitigation_instructions` is empty.** The probabilistic fix is produced and surfaced,
   but the Output Synthesizer does not yet distill a separate mitigation list (the prototype's
   "Recommendation" section). *Fix:* have the synthesizer extract mitigation bullets from the
   Code Analyst turn.
3. **Logs intentionally skipped.** The prototype's strongest "deliberate" wording came partly
   from `CrashUi.log` ("Triggering deterministic access violation / Writing to nullptr"). Aegis
   reached the same conclusion from the dump alone; feeding `--log CrashUi.log` (file-based
   Stage 4, no LogBackend needed) would add that corroboration verbatim.
4. **PDB as a code backend** (`PdbCodeAdapter`, spec §6.5.4) remains unimplemented; it would
   give the *exact* build revision from the PDB Source Server stream rather than a time-window
   guess. Not needed for this incident.
```
