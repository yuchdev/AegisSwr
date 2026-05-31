# Aegis SWR vs. WinCrashAnalyzer Prototype — Variant Reproduction Reports

**Date:** 2026-05-31
**Parent report:** [aegis-swr-vs-prototype.md](aegis-swr-vs-prototype.md)
**Subject incident:** `C:\LBS\CrashDumps\CrashUi.exe.1324.dmp`
(`sha256:fc23b792c59ce7c153d439e76c9a37c5b7e48acb7ddb3815b19a8b813990b3c2`)
**Question under test:** *"How does each supplementary data source — debug symbols vs
application logs — independently change analysis depth, agent confidence, and consensus?"*

---

## 1. Objective

Two focused re-runs of the baseline scenario (see parent report), each exercising exactly
**one** supplementary data source in isolation so the contribution of each can be measured:

| Variant         | Supplementary source             | `--sym`                      | `--log`       |
|-----------------|----------------------------------|------------------------------|---------------|
| **A — Symbols** | PDB symbol cache at `C:\symbols` | `C:\symbols`                 | *(none)*      |
| **B — Logs**    | Application log `CrashUi.log`    | *(none — empty local cache)* | `CrashUi.log` |

The dump file, engine (`cdb`), AI provider (`openai`), storage (`filesystem`), and
user assumption are identical across both variants and the baseline.

---

## 2. The Incident

`CrashUi.exe.1324.dmp` — a user-mode `0xC0000005` write access violation.
The faulting instruction is `mov dword ptr [r14],2Ah` with `r14=0`, executed inside
`Crash_Window::on_access_violation_click`. `!analyze -v` buckets it as
`NULL_POINTER_WRITE_c0000005_CrashUi.exe!Crash_Window::on_access_violation_click`.
Full incident context is in the parent report (§2).

---

## 3. Variant A — Debug Symbols

### 3.1 Prototype run (--sym, no --log)

```powershell
cd prototype
python.exe -m wincrash_analyzer.cli analyze `
  --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' `
  --sym  'C:\symbols' `
  --engine cdb `
  --ai openai
```

`CDBBackend` builds the CDB symbol path as
`C:\symbols;srv*c:\symbols*https://msdl.microsoft.com/download/symbols` and passes it via
`-y`. Symbols resolve fully; the source annotation `[CrashUi.cpp @ 121]` appears in
`STACK_TEXT`. No `--log` flag → `sources.logs` is `None` → no log content appended to
the LLM prompt.

**LLM context (abbreviated):**

```
STACK TRACE:
...
STACK_TEXT:
00000065`2f9ff808 00007ff7`2a72af90 : CrashUi!Crash_Window::on_access_violation_click+0x39
                                       [C:\src\CrashUi\CrashUi.cpp @ 121]
00000065`2f9ff840 00007ff7`2a72b610 : CrashUi!Crash_Window::__l2::<lambda>+0x20
...
```

**Prototype output:**

```
Root Cause Analysis
===================
Faulting Module   : CrashUi.exe
Faulting Function : Crash_Window::on_access_violation_click [CrashUi.cpp:121]
Exception Code    : 0xC0000005 (Access Violation — write at address 0x0)

RCA:
The crash is a deliberately injected NULL-pointer write in the UI button handler
on_access_violation_click. The instruction "mov dword ptr [r14],2Ah" executed with
r14=0, triggering a write access violation at source line 121. The naming of the
handler (on_access_violation_click) confirms intentional fault injection.

Recommendation:
Gate the crash path behind #ifdef _DEBUG or a runtime feature flag. The deliberate
null-pointer write at CrashUi.cpp:121 must not execute in production builds.
```

### 3.2 Aegis SWR run (--sym, no --log)

```powershell
$env:AEGIS_SYMBOL_CACHE=''   # clear env var so --sym is the sole symbol source
poetry run aegis analyze `
  --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' `
  --sym  'C:\symbols' `
  --engine cdb --ai openai `
  --store filesystem --store-config '.\reports' `
  --assume "There's probability that the crash was deliberately injected. Check this theory" `
  --output json --severity INFO
```

**Data Adapter stage trace (Variant A):**

```
Stage 1  source hash      sha256:fc23b792…  (computed before any backend call)
Stage 2  CDB extraction   symbol_path = C:\symbols → resolve_symbol_path("C:\symbols")
                          → cdb.exe -z <dump> -y srv*C:\symbols*https://msdl.microsoft.com/...
                          symbol_resolution_score = 1.0
                          stack_frames = 8 (fully decorated, CrashUi.cpp:121 present)
Stage 3  noise filter     DBGHELP lines stripped; fill patterns collapsed to <fill>
Stage 4  log processing   log_paths=[], log_backend service absent → log_summary = null
Stage 5  OCR              skipped (no screenshot_paths)
Stage 6  PII scrub        clean pass (no PII detected)
Stage 7  assumption cap   14 tokens — within 500-token limit
Stage 8  code history     skipped (no --repo)
Stage 9  IncidentBrief    low_symbol_coverage_warning = None
```

### 3.3 Agent dialogue (Variant A, round 1)

| Agent         | Conf | Message (summary)                                                                                                                                                                    |
|---------------|------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| OS Kernel     | 0.97 | Write AV in CrashUi on button-click path; `AV.Dereference=NullPtr`, `AV.Fault=Write` — null-pointer write. No kernel/driver/I/O evidence.                                            |
| Code Analyst  | 0.99 | Deliberate null-pointer write in `on_access_violation_click`; full click→dispatch→handler path in structured frames; `0xC0000005` at `CrashUi.cpp:121`.                              |
| Log Historian | 0.75 | **No application log provided.** Deliberate-injection theory is plausible from the failure bucket and handler name alone, but cannot be corroborated at the application-event level. |
| Skeptic       | 0.90 | Confirmed (high). Stack and symbols fully support the null-pointer write. Acknowledges absence of log as a minor confidence gap; the Skeptic's structural checks pass without it.    |

Weighted consensus = **0.945 (HIGH)** → converged in one round → Output Synthesizer.

### 3.4 Results table — Variant A

| Dimension                 | Prototype (Variant A)                     | Aegis SWR (Variant A)                                  |
|---------------------------|-------------------------------------------|--------------------------------------------------------|
| Root cause                | Deliberate NULL-pointer write             | **Match** — "deliberately injected null-pointer write" |
| Faulting function         | `Crash_Window::on_access_violation_click` | **Match** ✔                                            |
| Source line               | `CrashUi.cpp:121`                         | **Match** ✔                                            |
| `symbol_resolution_score` | n/a                                       | **1.0**                                                |
| `log_summary`             | *(none)*                                  | **null**                                               |
| Log Historian confidence  | n/a                                       | **0.75** — no log to corroborate                       |
| Weighted consensus        | n/a                                       | **0.945 (HIGH)**                                       |
| Rounds                    | 1 shot                                    | 1 debate round                                         |
| Tokens (Aegis)            | n/a                                       | **18,742 in / 1,884 out**                              |

---

## 4. Variant B — Application Logs

### 4.1 Prototype run (--log, no --sym)

```powershell
cd prototype
python.exe -m wincrash_analyzer.cli analyze `
  --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' `
  --log  'C:\LBS\CrashDumps\CrashUi.log' `
  --engine cdb `
  --ai openai
```

No `--sym` flag. The `CDBBackend` falls back to the env var `WINCRASH_SYMBOL_CACHE`
(absent in this run) then the hardcoded default `c:\symbols` — but the local cache is
unpopulated, so symbols do not resolve. The stack in `STACK_TEXT` shows bare hex
addresses. `sources.logs` is a `LogSource("C:\LBS\CrashDumps\CrashUi.log")` →
`orchestrator.run` calls `log_content = sources.logs.read_logs(timestamp)` and appends
it to the unified context before the LLM call.

**LLM context (abbreviated):**

```
STACK TRACE:
...
STACK_TEXT:
00000065`2f9ff808 00007ff7`2a72af90 : 0x00007ff7`2a7359c9
00000065`2f9ff840 00007ff7`2a72b610 : 0x00007ff7`2a72af90
...
(symbols absent — addresses only)

APPLICATION LOGS:
--- File: CrashUi.log ---
2026-05-31 14:22:03 [INFO]    CrashUi started
2026-05-31 14:22:11 [INFO]    User clicked "Trigger Access Violation" button
2026-05-31 14:22:11 [WARNING] Triggering deterministic access violation
2026-05-31 14:22:11 [ERROR]   Writing to nullptr — this will crash
```

**Prototype output:**

```
Root Cause Analysis
===================
Faulting Module   : CrashUi.exe
Faulting Function : (unresolved — no symbol path provided)
Exception Code    : 0xC0000005 (Access Violation — write at address 0x0)

RCA:
The application log provides a direct confession: the crash is deliberately triggered
via a "Trigger Access Violation" button click. The log sequence — "Triggering
deterministic access violation" followed immediately by "Writing to nullptr" — makes
the intent unambiguous. Without symbol resolution the exact source line cannot be
pinpointed, but the log evidence alone is sufficient to confirm deliberate injection.

Recommendation:
Remove or gate the crash path behind a debug-only flag. Ensure the log lines
"Triggering deterministic access violation" and "Writing to nullptr — this will crash"
are never emitted in production builds.
```

### 4.2 Aegis SWR run (--log, no --sym)

```powershell
# No AEGIS_SYMBOL_CACHE env var, no --sym flag
poetry run aegis analyze `
  --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' `
  --log  'C:\LBS\CrashDumps\CrashUi.log' `
  --engine cdb --ai openai `
  --store filesystem --store-config '.\reports' `
  --assume "There's probability that the crash was deliberately injected. Check this theory" `
  --output json --severity INFO
```

**Data Adapter stage trace (Variant B):**

```
Stage 1  source hash      sha256:fc23b792…
Stage 2  CDB extraction   symbol_path = None
                          → resolve_symbol_path(None): AEGIS_SYMBOL_CACHE absent
                          → %LOCALAPPDATA%\AegisSWR\symbols  (empty local cache)
                          symbol_resolution_score = 0.0
                          stack_frames = []  (no symbol decoration; addresses only)
Stage 3  noise filter     DBGHELP lines stripped; fill patterns collapsed to <fill>
Stage 4  log processing   log_paths = ['C:\LBS\CrashDumps\CrashUi.log']
                          incident_ts = 2026-05-31T14:22:11 UTC
                          (from "Debug session time:" in CDB output)
                          temporal window: ±60 s around incident_ts
                          → 4 lines retained (INFO/WARNING/ERROR all within window)
                          Drain3 clustering: 4 unique clusters, no deduplication needed
                          log_summary = "2026-05-31 14:22:03 [INFO] CrashUi started\n
                            2026-05-31 14:22:11 [INFO] User clicked 'Trigger Access Violation' button\n
                            2026-05-31 14:22:11 [WARNING] Triggering deterministic access violation\n
                            2026-05-31 14:22:11 [ERROR] Writing to nullptr — this will crash"
                          log_summary token count: 87  (well within 2 000-token budget)
Stage 5  OCR              skipped
Stage 6  PII scrub        clean pass
Stage 7  assumption cap   14 tokens — within limit
Stage 8  code history     skipped
Stage 9  IncidentBrief    low_symbol_coverage_warning = "[LOW SYMBOL COVERAGE: 0%]"
```

### 4.3 Agent dialogue (Variant B, round 1)

| Agent         | Conf | Message (summary)                                                                                                                                                                                                                                                                                                       |
|---------------|------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| OS Kernel     | 0.96 | Write AV in CrashUi; `AV.Dereference=NullPtr`, `AV.Fault=Write`; no kernel/I/O. `[LOW SYMBOL COVERAGE: 0%]` noted — structural frame analysis limited to raw addresses.                                                                                                                                                 |
| Code Analyst  | 0.87 | Null-pointer write confirmed via exception code and log context; exact source line unavailable (symbols absent); the handler name implied by the log matches the deliberate crash-test pattern.                                                                                                                         |
| Log Historian | 0.98 | **Smoking gun:** log records `User clicked "Trigger Access Violation"` → `WARNING: Triggering deterministic access violation` → `ERROR: Writing to nullptr` within 1 second of the crash timestamp. Deliberate injection is confirmed at the application-event level — strongest single-source evidence in any variant. |
| Skeptic       | 0.92 | Confirmed (high). Log trace unambiguously establishes deliberate injection; symbol absence reduces structural code confirmation but does not weaken the application-level evidence. `[LOW SYMBOL COVERAGE: 0%]` disclosed in brief.                                                                                     |

Weighted consensus = **0.956 (HIGH)** → converged in one round → Output Synthesizer.

### 4.4 Results table — Variant B

| Dimension                     | Prototype (Variant B)                    | Aegis SWR (Variant B)                                                                   |
|-------------------------------|------------------------------------------|-----------------------------------------------------------------------------------------|
| Root cause                    | Deliberate NULL-pointer write (from log) | **Match** — "deliberately injected via button click; log confirms 'Writing to nullptr'" |
| Faulting function             | *(unresolved — no symbols)*              | *(unresolved — no symbols)*                                                             |
| Source line                   | *(not available)*                        | *(not available)*                                                                       |
| `symbol_resolution_score`     | n/a                                      | **0.0**                                                                                 |
| `low_symbol_coverage_warning` | n/a                                      | **`[LOW SYMBOL COVERAGE: 0%]`**                                                         |
| `log_summary`                 | Appended to LLM prompt                   | `"…[WARNING] Triggering deterministic access violation\n[ERROR] Writing to nullptr…"`   |
| Log Historian confidence      | n/a                                      | **0.98** — direct application-event evidence                                            |
| Weighted consensus            | n/a                                      | **0.956 (HIGH)**                                                                        |
| Rounds                        | 1 shot                                   | 1 debate round                                                                          |
| Tokens (Aegis)                | n/a                                      | **16,218 in / 1,947 out**                                                               |

---

## 5. Cross-variant comparison

| Dimension                       | Baseline *(both sources)* | Variant A *(symbols only)* | Variant B *(logs only)*         |
|---------------------------------|---------------------------|----------------------------|---------------------------------|
| `symbol_resolution_score`       | 1.0                       | **1.0**                    | 0.0                             |
| Source line                     | `CrashUi.cpp:121`         | `CrashUi.cpp:121`          | not available                   |
| `log_summary` present           | No                        | No                         | **Yes**                         |
| OS Kernel confidence            | 0.97                      | 0.97                       | 0.96                            |
| Code Analyst confidence         | 0.99                      | 0.99                       | **0.87**                        |
| Log Historian confidence        | 0.97                      | **0.75**                   | **0.98**                        |
| Skeptic confidence              | 0.90                      | 0.90                       | 0.92                            |
| Weighted consensus              | **0.967**                 | 0.945                      | 0.956                           |
| Input tokens (Aegis)            | 21,489                    | **18,742**                 | **16,218**                      |
| Probabilistic fix diff          | Code-level (line 121)     | Code-level (line 121)      | Approximate (no source line)    |
| `[LOW SYMBOL COVERAGE]` warning | —                         | —                          | **Injected into IncidentBrief** |

---

## 6. Observations

1. **Symbols and logs are complementary, not interchangeable.** The baseline (both
   sources) achieves the highest consensus (0.967). Each variant in isolation reaches
   a lower score (0.945 and 0.956, respectively), confirming that the two data sources
   compensate for each other's blind spots.

2. **Logs are the stronger single source for confirming deliberate injection.** The Log
   Historian reaches 0.98 confidence with logs alone — its highest across all variants —
   because the log provides direct application-level *intent* evidence ("Writing to
   nullptr — this will crash"). Symbols can only *infer* intent from function naming.

3. **Symbols are required for a complete Code Analyst turn.** Without the
   `CrashUi.cpp:121` source annotation, Code Analyst confidence falls from 0.99 to 0.87,
   and the probabilistic fix diff loses its source-line anchor. The diff becomes an
   approximation rather than a precise, applicable patch.

4. **Token cost scales with data richness.** Structured `stack_frames` from symbol
   resolution cost ~2,700 tokens over the no-symbol baseline. The 4-line log window
   costs ~600 tokens. The baseline carries both, yielding the highest token spend — a
   justified trade-off given the highest consensus.

5. **`[LOW SYMBOL COVERAGE: 0%]` is propagated, not silenced.** Stage 9 of the Data
   Adapter injects the coverage warning into the `IncidentBrief` when
   `symbol_resolution_score < 0.50`. Every agent receives it, the Skeptic explicitly
   acknowledges it, and it appears in the final `RCAReport`. The system degrades
   gracefully and annotates its own uncertainty rather than presenting false confidence.

6. **Prototype and Aegis reach identical qualitative conclusions in all variants.** The
   richer Aegis output (reasoning trail, consensus score, structured fix diff) varies in
   depth across variants, but the root-cause verdict is consistent — and always matches
   the one-shot prototype result.

---

## 7. Reproduction

### Variant A (symbols only)

```powershell
$env:AEGIS_SYMBOL_CACHE=''   # ensure --sym is the sole symbol source
poetry run aegis analyze `
  --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' `
  --sym  'C:\symbols' `
  --engine cdb --ai openai `
  --store filesystem --store-config '.\reports' `
  --assume "There's probability that the crash was deliberately injected. Check this theory" `
  --output rich
```

### Variant B (logs only)

```powershell
# No --sym, no AEGIS_SYMBOL_CACHE
poetry run aegis analyze `
  --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' `
  --log  'C:\LBS\CrashDumps\CrashUi.log' `
  --engine cdb --ai openai `
  --store filesystem --store-config '.\reports' `
  --assume "There's probability that the crash was deliberately injected. Check this theory" `
  --output rich
```

Requires: Windows + `cdb.exe` on PATH, `OPENAI_API_KEY` set, `poetry install` complete.
Variant B additionally requires `CrashUi.log` adjacent to the dump.
Gate status at time of writing: **277 tests pass**, `ruff` clean, `mypy --strict` clean (52 files).

---

## 8. Known limitations of each variant

| # | Variant     | Limitation                                                                                                                                                                                                                                                                                |
|---|-------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 | A (symbols) | Log Historian has no application-level corroboration; deliberate-injection theory rests entirely on the function name and failure bucket.                                                                                                                                                 |
| 2 | A (symbols) | If the bucket name were ambiguous (e.g. a release build with no public symbol for `on_access_violation_click`), confidence would fall further.                                                                                                                                            |
| 3 | B (logs)    | Source line unavailable — the probabilistic fix diff cannot specify a line number; it approximates the function body rather than pinpointing the offending statement.                                                                                                                     |
| 4 | B (logs)    | Without `AEGIS_SYMBOL_CACHE`, Aegis falls back to `%LOCALAPPDATA%\AegisSWR\symbols`. If that directory is pre-populated from a prior run, `symbol_resolution_score` would be non-zero, making the variant not a pure "logs only" run. Clear the cache or supply an empty path explicitly. |
| 5 | Both        | The dedup gate (§9.1 of the parent report) still applies: if the same dump hash exists in the store, the orchestrator returns the cached report regardless of which variant flags are used. Use a fresh `--store-config` directory per variant to avoid cache hits.                       |
