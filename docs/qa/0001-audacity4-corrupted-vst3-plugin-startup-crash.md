# QA-0001: Audacity 4 — Corrupted VST3 Plugin Startup Crash

> **This scenario is illustrative.** All filenames, stack addresses, log lines,
> commit hashes, and numeric values are fabricated for documentation purposes.
> No real captured incident, customer data, or proprietary payload is included.
> See [qa/README.md](README.md) for the required-sections template.

---

## Scenario Summary

A Windows 10 user installs a third-party synthesiser distributed as a VST3
plugin. The plugin binary (`SynthWave.vst3`) is silently truncated during
download: the file is 47 KB on disk, but a valid VST3 factory section requires at
least 128 KB. On the next Audacity 4 launch, the plugin scanner iterates over the
factory class table embedded in the binary's export directory. Because the class
count field in the (corrupted) factory header still reads 24 entries, the scanner
walks 24 class-info structs into memory that lies beyond the actual file mapping,
triggering an `EXCEPTION_ACCESS_VIOLATION` (0xC0000005) before Audacity draws its
main window.

The operator runs `aegis analyze` with a Windows minidump, the Audacity log,
a screenshot of the crash dialog, and a local Audacity 4 checkout. Aegis SWR
reaches a `HIGH`-confidence root cause in three debate rounds and produces a
`RemediationPlan` with three advisory steps.

---

## Artifacts Provided

| # | Type        | Filename                                                      | Description                                                                                     |
|---|-------------|---------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| 1 | Crash dump  | `audacity4-20260801-startup.dmp`                              | Windows minidump captured by WER at crash time; MDMP magic bytes present                        |
| 2 | Log file    | `audacity4-20260801.log`                                      | Application log from Audacity 4 startup; contains plugin-scan entries and a terminal FATAL line |
| 3 | Screenshot  | `audacity-crash-dialog.png`                                   | Screenshot of the Windows "Audacity has stopped working" crash dialog captured at T+3 s         |
| 4 | Source code | Local clone of `github.com/audacity/audacity` at tag `v4.0.1` | Provides git history and `PluginManager.cpp` for the code backend                               |

---

## CLI Invocation

```bash
aegis analyze \
  --dump  /evidence/audacity4-20260801-startup.dmp       \
  --log   /evidence/audacity4-20260801.log               \
  --shot  /evidence/audacity-crash-dialog.png            \
  --repo  /repos/audacity                                \
  --ai    anthropic                                      \
  --store filesystem
```

No `--agent` flag is supplied; panel selection is **automatic** based on the
fault class extracted from the dump. See [docs/config/cli.md](../config/cli.md)
for all option definitions.

---

## Pipeline Trace — INITIALIZING

`commands.analyze()` in `src/aegis_swr/cli/commands.py` performs these steps
before any backend work:

1. **Logging bootstrap.** `configure_logging("WARNING", ...)` initialises the
   application log sink at `~/.aegis-swr/logs/aegis-swr.log`. The Evidence
   Stream and Investigation Process panes retain their default `INFO` severity.

2. **`IncidentSource` construction.**

   ```python
   IncidentSource(
       mode=IncidentMode.CRASH_DUMP,
       dump_path="/evidence/audacity4-20260801-startup.dmp",
       log_paths=["/evidence/audacity4-20260801.log"],
       screenshot_paths=["/evidence/audacity-crash-dialog.png"],
       symbol_path=[],            # no explicit --sym; cdb.exe uses _NT_SYMBOL_PATH
       user_assumption=None,      # no --prompt; default prompt is synthesised
       metadata={"repo_path": "/repos/audacity"},
   )
   ```

   `incident_timestamp` is `None`; the Data Adapter falls back to the last 500
   log lines when no timestamp is available (Stage 4 fallback path).

3. **`Settings` overrides.**

   - `backends.ai.provider = "anthropic"`
   - `backends.debug.engine = "auto"` (resolved to `cdb` on Windows)
   - `backends.storage.provider = "filesystem"`
   - `backends.code.enabled = True`, `backends.code.provider = "git"`,
     `backends.code.repo_path = "/repos/audacity"`
   - `backends.log.provider = "file"`

4. **Backend instantiation.** `create_ai_backend`, `create_debug_backend`
   (returns a `CDBWorker`), `create_storage_backends`, `create_code_backend`
   (returns a `GitCodeBackend`), `create_log_backend` (returns a
   `FileLogAdapter`).

5. **`Orchestrator` construction.**

   ```python
   Orchestrator(
       settings=settings,
       ai_backend=<AnthropicBackend>,
       debug_backend=<CDBWorker>,
       relational_store=<FilesystemStore>,
       object_store=None,
       log_backend=<FileLogAdapter>,
       code_backend=<GitCodeBackend>,
       explicit_specs=None,   # auto-select panel
   )
   ```

   A `DataAdapter` and a `ConsensusEvaluator` are also constructed and held
   privately.

---

## Pipeline Trace — EXTRACTING (Data Adapter)

`Orchestrator._extract_brief()` calls `DataAdapter.process()` with the four
optional backends. All nine stages run synchronously before any LangGraph node
is entered.

### Stage 1 — Source Validation and SHA-256 Hash

`DataAdapter._compute_hash()` reads `audacity4-20260801-startup.dmp` in 8 KB
chunks and produces:

```
dump_hash  = "sha256:3e4f5a6b7c8d9e0f1a2b3c4d5e6f789012345678abcdef01234567890abcde12"
dump_format = DumpFormat.WINDOWS_MINIDUMP   (magic bytes 0x4D 0x44 0x4D 0x50 = "MDMP")
```

No prior report with this hash exists in the relational store, so the
deduplication gate does not short-circuit the run.

### Stage 2 — Dump Extraction (CDB)

`CDBWorker.extract()` spawns `cdb.exe -z audacity4-20260801-startup.dmp`,
runs `.reload /f /i` and `!analyze -v`, then parses the output:

```
exception_code_raw   = "0xC0000005"        (EXCEPTION_ACCESS_VIOLATION)
exception_address    = "0x00007FFB12340010"
faulting_module      = "SynthWave.vst3"
faulting_function    = "IPluginFactory3::getClassInfoUnicode"
fault_class          = FaultClass.ACCESS_VIOLATION
symbol_resolution_score = 0.72             (Audacity PDB partial; no PDB for the plugin)
```

Stack frames extracted (up to `settings.core.stack_frames_limit`, default 10):

```
#0  SynthWave.vst3!IPluginFactory3::getClassInfoUnicode+0x10   0x00007FFB12340010
#1  audacity.exe!PluginManager::ScanVST3Plugin+0x1A4           0x00007FF6AABB1234
#2  audacity.exe!PluginManager::DiscoverPluginsInPath+0x88     0x00007FF6AABB0A80
#3  audacity.exe!AudacityApp::OnInit+0x2BC                     0x00007FF6AABE5C10
#4  wxbase32u_vc_x64_custom!wxAppConsole::CallOnInit+0x12      0x00007FFACDEF1200
```

`symbol_resolution_score = 0.72 < 0.50` is `False`, so no
`low_symbol_coverage_warning` is emitted (threshold is 50 %; this run is above
it).

### Stage 3 — Noise Pre-Filter

`apply_noise_filter()` removes `DBGHELP: … file not found` lines and the DLL
load list block, collapses `0xCCCCCCCC`/`0xBAADF00D` fill patterns to
`<fill>`, and applies an 8 000-character head+tail truncation. In this scenario
the `!analyze -v` output is 6 200 characters; no truncation occurs.

### Stage 4 — Log Processing

`incident_timestamp` is `None`, so `_process_logs()` uses the last 500 log
lines from `audacity4-20260801.log` rather than a temporal window.

After Drain3 template clustering, the summary (illustrative) is:

```
2026-08-01 09:14:22 INFO  [PluginManager] Scanning VST3 plugins in C:\...\VST3\
2026-08-01 09:14:22 INFO  [PluginManager] Discovered 7 VST3 plugins
2026-08-01 09:14:23 INFO  [PluginManager] Loading: SynthWave.vst3
2026-08-01 09:14:23 ERROR [PluginManager] Exception in IPluginFactory3::getClassInfoUnicode
2026-08-01 09:14:23 FATAL [AudacityApp] Unhandled exception — terminating
```

The summary is 423 tokens, well within the `_LOG_TOKEN_BUDGET` of 2 000 tokens.
No lines are dropped.

### Stage 5 — Screenshot OCR

`DataAdapter._process_screenshots()` calls Tesseract via `pytesseract` on
`audacity-crash-dialog.png`. Words with OCR confidence > 60 % are retained:

```
UIContext(
    error_message="Audacity has stopped working A problem caused the program to stop working correctly",
    ui_elements=["Audacity", "has", "stopped", "working", "A", "problem", "caused", ...]
)
```

### Stage 6 — PII Scrubbing

`DataAdapter._scrub_text()` applies the five regex rules
(`DB_CONN`, `EMAIL`, `AWS_KEY`, `CREDIT_CARD`, `IP`) followed by Presidio NER.
In this scenario no PII patterns match the raw excerpt or log summary.
`last_pii_substitution_map` remains `{}`.

The OCR text from Stage 5 likewise contains no PII. `UIContext.error_message`
is unchanged.

### Stage 7 — User-Assumption Token Cap

No `--prompt` was supplied. `_default_prompt()` synthesises:

```
"No operator hypothesis was supplied. Investigate this incident using a crash dump,
1 log file(s), 1 screenshot(s) and determine the most likely root cause as
efficiently as possible. ..."
```

This default prompt is 62 tokens; the `user_assumption_token_limit` (default
500 tokens) is not reached.

### Stage 8 — Code-History Query

`DataAdapter._query_code_history()` calls
`GitCodeBackend.get_commits_before()` for the 2-hour window before
`incident_timestamp` (which is `None` here). Because `incident_timestamp` is
`None`, the code history query returns `[]` immediately (the guard at the top of
`_query_code_history` requires a non-`None` timestamp).

```
code_history = []
```

**SME resolution (2026-08-19):** yes, infer it — but only as a fallback, never
as an override. When `source.incident_timestamp` is `None`, a future Stage 8
enhancement should attempt to read the WER capture time embedded in the
minidump header (the `MINIDUMP_MISC_INFO` stream / `.dumpheader` output already
parsed by `CDBWorker`) and use it in place of the guard's unconditional
`return []`. An operator-supplied timestamp (`--prompt`, or any future explicit
`--timestamp`) must always take precedence over the inferred value — WER
timestamps can be wrong (clock skew, a replayed or synthetic dump, a copied
minidump) in a way an operator's own statement is not.

The inferred value must carry its provenance forward: tag it as
`timestamp_source="inferred_wer"` on `IncidentBrief` (and the persisted
`RCAReport`) rather than treating it identically to an operator-confirmed
timestamp. `code_analyst` and `log_historian` both treat code/log recency as
evidence, so a silently-wrong inferred timestamp would corrupt that evidence
rather than fail loudly — the provenance tag lets both agents (and a human
reviewer) discount it appropriately. The 2-hour window and 5-commit limit in
`_query_code_history()` are unchanged; this is a timestamp-*source* change
only, not a change to the query semantics.

In this scenario specifically, no `--prompt` was supplied and the guard's
current behaviour (`code_history=[]`, unconditionally) is the state described
throughout this trace — that would not change until the WER-inference fallback
above is implemented. Scope this as its own Data Adapter task, separate from
Milestone 0005 (harness/multi-backend), since it is orthogonal to that work.

### Stage 9 — IncidentBrief Assembly

`DataAdapter.process()` returns:

```python
IncidentBrief(
    mode=IncidentMode.CRASH_DUMP,
    dump_hash="sha256:3e4f5a6b7c8d...",
    fault_class=FaultClass.ACCESS_VIOLATION,
    exception_code=None,           # not set in this path (raw only)
    exception_code_raw="0xC0000005",
    exception_address="0x00007FFB12340010",
    faulting_module="SynthWave.vst3",
    faulting_function="IPluginFactory3::getClassInfoUnicode",
    symbol_resolution_score=0.72,
    stack_frames=[
        {"frame_number": 0, "module": "SynthWave.vst3",
         "function": "IPluginFactory3::getClassInfoUnicode",
         "instruction_address": "0x00007FFB12340010"},
        {"frame_number": 1, "module": "audacity.exe",
         "function": "PluginManager::ScanVST3Plugin",
         "instruction_address": "0x00007FF6AABB1234"},
        # … frames 2–4 …
    ],
    raw_text_excerpt="[filtered !analyze -v output — 6 200 chars]",
    log_summary="[5 clustered log lines, 423 tokens]",
    ui_context=UIContext(error_message="Audacity has stopped working …"),
    code_history=[],
    user_assumption="No operator hypothesis was supplied …",
    low_symbol_coverage_warning=None,
)
```

---

## Pipeline Trace — ANALYZING (Panel Resolution)

`Orchestrator._resolve_and_build()` calls `PanelResolver.resolve()` on the
`IncidentBrief` dict. The resolver inspects `fault_class = ACCESS_VIOLATION`
and selects the four base agents (the default panel for memory-related crashes):

| `agent_key`     | Role         | Priority | `default_weight` | `contributes_fix` |
|-----------------|--------------|----------|------------------|-------------------|
| `os_kernel`     | INVESTIGATOR | 3        | 0.35             | False             |
| `code_analyst`  | INVESTIGATOR | 3        | 0.35             | True              |
| `log_historian` | INVESTIGATOR | 3        | 0.17             | False             |
| `skeptic`       | ARBITER      | 3        | 0.13             | False             |

`resolve_panel()` validates exactly one ARBITER (`skeptic`) — the invariant
holds.

All four specs carry `weight = None`, so `resolve_consensus_weights()` uses each
agent's own `default_weight`. The consensus weight map is:

```python
{"os_kernel": 0.35, "code_analyst": 0.35, "log_historian": 0.17, "skeptic": 0.13}
```

`_order_panel()` separates investigators from the arbiter, sorts investigators by
descending priority (all priority 3 → stable sort preserves registry order), then
appends the arbiter:

```
os_kernel_node → code_analyst_node → log_historian_node → skeptic_node
```

The compiled LangGraph routes:

```
START → os_kernel_node → code_analyst_node → log_historian_node → skeptic_node
  → [conditional: converged? → output_synthesizer_node → END
                  limit?     → hitl_node → END
                  else       → os_kernel_node (loop)]
```

`recursion_limit = (4 + 2) × 4 + 5 = 29` (4 agents, 4 max rounds, margin 5).

---

## Pipeline Trace — ANALYZING (Agent Debate)

### Round 1

**`os_kernel_node`** receives the `IncidentBrief` and the empty
`latest_arbiter_feedback` list (first round).

- Input context (illustrative excerpt — no raw payload):

  ```json
  {
    "round": 1,
    "incident_brief": {
      "fault_class": "ACCESS_VIOLATION",
      "exception_code_raw": "0xC0000005",
      "exception_address": "0x00007FFB12340010",
      "faulting_module": "SynthWave.vst3",
      "faulting_function": "IPluginFactory3::getClassInfoUnicode"
    }
  }
  ```

- Output (`OSKernelOutput`): The agent maps `0xC0000005` to
  `FaultClass.ACCESS_VIOLATION` (read sub-type: the exception record's second
  argument indicates a read at the faulting address). Hypothesis: the VST3
  plugin binary is corrupt or truncated, causing a read past the end of its
  memory-mapped factory section.

  ```
  confidence_score = 0.72
  primary_hypothesis.root_cause =
    "Corrupted/truncated SynthWave.vst3 binary causes read past mapped region
     in IPluginFactory3::getClassInfoUnicode during Audacity 4 plugin scan"
  ```

**`code_analyst_node`** receives the brief and the OS Kernel turn as
`latest_turn_this_round`.

- The agent reads the stack: frame #1 (`PluginManager::ScanVST3Plugin`) calls
  into the plugin factory in a loop over `factory->countClasses()`. If the
  class-count field in the corrupt binary reads 24 but data only exists for 3
  entries, loop iterations 4–24 dereference invalid memory.
- `contributes_fix = True`; the agent emits a fix annotation in its leading
  hypothesis evidence list:

  ```
  __fix__: src/PluginManager.cpp: add bounds check comparing
  factory->countClasses() against a maximum derived from the file size before
  entering the getClassInfoUnicode loop.
  ```

  ```
  confidence_score = 0.78
  ```

**`log_historian_node`** receives the brief and the code-analyst turn.

- `LogHistorianAgent._invoke_agent()` receives `vector_store=None` and
  `history=[]` (no relational store populated yet for this deployment).
- `recurrence_analysis.matched_incidents = []`, `history_size = 0`.
- The agent concludes: first-observed failure signature; no confidence
  adjustment.

  ```
  confidence_adjustment = 0.0
  updated_confidence    = 0.72
  history_note = "No prior incidents match this failure signature;
                  first-observed."
  confidence_score = 0.72
  ```

**`skeptic_node`** (ARBITER) receives the full discussion history.

- Programmatic pre-check: `_module_in_frames("SynthWave.vst3", frames[:5])`
  → True (frame #0). Module confirmed in stack.
- LLM challenge: exception code 0xC0000005 is consistent with a read
  violation; hypothesis survives initial scrutiny. The Skeptic issues one
  correction for Round 2: verify whether the violation is a read (not write)
  by examining the exception record's first parameter.

  ```
  SkepticVerdict(
      confirmed = True,
      confidence = ConfidenceLevel.MEDIUM,   # score 0.70 >= 0.65 → arbiter_confirmed
      challenges = ["Confirm read (not write) violation via exception record parameter 0."],
      corrections = ["Examine exception record parameter 0 (0=read, 1=write, 8=DEP)."]
  )
  confidence_score = 0.70
  ```

**Round 1 consensus score:**

```
CS = (0.35 × 0.72 + 0.35 × 0.78 + 0.17 × 0.72 + 0.13 × 0.70)
   = (0.252 + 0.273 + 0.1224 + 0.091) / 1.0
   = 0.7384
```

`is_converged`: `arbiter_confirmed = True` AND `CS 0.7384 ≥ threshold 0.85`?
→ **No.** Route loops back to `os_kernel_node` for Round 2.

---

### Round 2

The Skeptic's correction from Round 1 (`latest_arbiter_feedback`) is
injected into `os_kernel`'s context as
`"skeptic_corrections_from_previous_round"`.

**`os_kernel_node`** addresses the correction: the exception record's first
parameter (available in the raw excerpt) is `0x0000000000000000` — a read
violation. The agent also notes the mapped region ends at
`0x00007FFB1234FFFF`, confirming the address `0x00007FFB12340010` is near the
end of a 47 KB mapping. Confidence rises:

```
confidence_score = 0.82
```

**`code_analyst_node`** cross-references file size: the `SynthWave.vst3` file
is 47 832 bytes on disk. A valid VST3 factory descriptor for 24 classes would
require at least 128 000 bytes. The factory's `classCount` field at offset 0x28
reads 0x18 (24), but only 3 class-info structs fit in the actual file. The loop
in `PluginManager.cpp:882` iterates `i < factory->countClasses()` with no upper
bound check. Confidence:

```
confidence_score = 0.88
```

**`log_historian_node`**: no new history; unchanged conclusion.

```
confidence_score = 0.78
```

**`skeptic_node`**: all corrections addressed. The module is still in frame #0;
the read violation (parameter 0) is confirmed; the hypothesis is stable from
Round 1.

```
SkepticVerdict(
    confirmed    = True,
    confidence   = ConfidenceLevel.MEDIUM,
    challenges   = ["Confirm no other VST3 plugins are affected."],
    corrections  = ["Check whether other installed plugins also have size anomalies."]
)
confidence_score = 0.80
```

**Round 2 consensus score:**

```
CS = (0.35 × 0.82 + 0.35 × 0.88 + 0.17 × 0.78 + 0.13 × 0.80)
   = (0.287 + 0.308 + 0.1326 + 0.104) / 1.0
   = 0.8316
```

`same_hypothesis = True` (root cause string unchanged).
`is_converged`: `CS 0.8316 ≥ 0.85`? → **No.** Route loops for Round 3.

---

### Round 3

Skeptic's correction: check other installed plugins for size anomalies.

**`os_kernel_node`**: confirms the seven discovered plugins in the log; only
`SynthWave.vst3` has an anomalous file size (all others are >200 KB). Scope
of the failure is narrowed to the single plugin. Confidence:

```
confidence_score = 0.88
```

**`code_analyst_node`**: confirms that the Audacity 4 plugin scanner does not
validate file size before entering the factory enumeration loop; this is a
missing defensive check specific to the VST3 scan path. All other plugins load
successfully. Confidence:

```
confidence_score = 0.91
```

**`log_historian_node`**: still no recurrence data. Confidence:

```
confidence_score = 0.85
```

**`skeptic_node`**: all corrections addressed; hypothesis is stable and
consistent across three rounds.

```
SkepticVerdict(
    confirmed = True,
    confidence = ConfidenceLevel.HIGH,
    challenges = [],
    corrections = []
)
confidence_score = 0.90
```

**Round 3 consensus score:**

```
CS = (0.35 × 0.88 + 0.35 × 0.91 + 0.17 × 0.85 + 0.13 × 0.90)
   = (0.308 + 0.3185 + 0.1445 + 0.117) / 1.0
   = 0.888
```

`arbiter_confirmed = (0.90 ≥ 0.65)` → True.
`same_hypothesis = True`.
`is_converged = (0.888 ≥ 0.85)` → **Yes.**

Route: `output_synthesizer_node`.

---

## Pipeline Trace — STORING (Output Synthesis)

`_make_synthesizer_node()` builds the final report and attaches the remediation
plan.

**`_build_report()`** extracts from the discussion history:

- `primary_hypothesis`: the Round 1 hypothesis promoted by `os_kernel` (root
  cause string stable across all three rounds).
- `probabilistic_fix`: extracted from the `code_analyst` turn's leading
  hypothesis evidence annotation (`__fix__: …`).
- `skeptic_challenges`: the Skeptic's Round 1 challenge
  (`"Confirm read (not write) violation …"`).
- `consensus_rounds = 3`, `consensus_score = 0.888`.

**Persistence** (best-effort):

- `FilesystemStore.save_report(report)` writes
  `~/.aegis-swr/reports/<incident-id>.json`.
- No vector store is configured; the `VectorStore` path is skipped.

**`_synthesize_remediation()`**: `"remediation_planner"` is in
`settings.panel.enabled_synthesis` (default). `RemediationPlannerAgent` is
instantiated and `run_synthesis(report)` is called. Only PII-scrubbed,
planning-relevant fields are sent to the model:

```json
{
  "root_cause": "Corrupted/truncated SynthWave.vst3 …",
  "faulting_module": "SynthWave.vst3",
  "faulting_function": "IPluginFactory3::getClassInfoUnicode",
  "confidence_score": 0.888,
  "confidence_level": "high",
  "mitigation_instructions": []
}
```

The resulting `RemediationPlan` (see [§ Suggested Remediation](#suggested-remediation))
is attached to the report as `report.remediation_plan`.

The `AgentSpoke(node="remediation_planner_node", turn=…)` event is published on
the `EventBus` (visible in the Investigation Process pane).

---

## Final RCA Report

Key `RCAReport` fields after synthesis (fabricated values):

```json
{
  "incident_id": "a1b2c3d4-e5f6-7890-abcd-ef0123456789",
  "created_at": "2026-08-19T00:00:00Z",
  "mode": "crash_dump",
  "dump_hash": "sha256:3e4f5a6b7c8d9e0f...",
  "symbol_resolution_score": 0.72,
  "root_cause": "Corrupted/truncated SynthWave.vst3 binary (47 KB vs 128 KB expected) causes out-of-bounds read in IPluginFactory3::getClassInfoUnicode during Audacity 4 startup VST3 plugin scan",
  "faulting_module": "SynthWave.vst3",
  "faulting_function": "IPluginFactory3::getClassInfoUnicode",
  "confidence_score": 0.888,
  "confidence_level": "high",
  "consensus_rounds": 3,
  "probabilistic_fix": "src/PluginManager.cpp: add bounds check comparing factory->countClasses() against a maximum derived from the file size before entering the getClassInfoUnicode loop.",
  "fix_confidence": 0.888,
  "hitl_request": null,
  "total_input_tokens": 9420,
  "total_output_tokens": 2810
}
```

The `agent_dialogue` list contains 12 `AgentTurn` records (4 agents × 3 rounds)
plus the `RemediationPlannerAgent` turn (turn_number 0, node
`remediation_planner_node`).

The report is persisted at:

```
~/.aegis-swr/reports/a1b2c3d4-e5f6-7890-abcd-ef0123456789.json
```

---

## Suggested Remediation

`RemediationPlannerAgent.run_synthesis()` produces the following `RemediationPlan`
(illustrative; generated by the LLM from the scrubbed RCA context above):

**Summary:**

> The truncated SynthWave.vst3 plugin file triggers an unchecked read in
> Audacity's VST3 factory enumeration loop. Contain the incident by removing
> the plugin from the scan path, then replace or delete the corrupted binary and
> verify the application starts cleanly.

**Steps:**

| # | Action | Idempotent | Rollback | Requires approval |
|---|--------|-----------|----------|------------------|
| 1 | Move `SynthWave.vst3` out of `C:\Program Files\Common Files\VST3\` to a quarantine folder to prevent repeated crashes on startup | Yes | Move it back to its original path | No |
| 2 | Delete the quarantined `SynthWave.vst3` file and re-download it from the vendor's official distribution page; verify the SHA-256 of the new file matches the vendor's published checksum | No | Restore from quarantine if the vendor file is unavailable | Yes |
| 3 | Start Audacity 4 and confirm it reaches its main window without a crash dialog; re-enable the plugin and verify it loads in the plugin list | Yes (read-only: no state change) | read-only: no state change | No |

`RemediationPlan.requires_human_approval = True` (step 2 modifies the
file system). The plan is **advisory**: no step is auto-dispatched. Operator
must confirm each production-affecting step with `AEGIS_PROD_CONFIRMED=1`.

---

## Security and Redaction Notes

This scenario demonstrates the following Aegis SWR security posture:

- **No PII in the report.** Stage 6 (PII scrubbing) found no emails, IP
  addresses, credentials, or personal identifiers in the raw dump excerpt, log
  summary, or OCR text. `last_pii_substitution_map = {}`. The `[REDACTED_*]`
  token mechanism is ready but was not triggered.

- **Payload not logged.** The raw `!analyze -v` output and log lines are
  never written to the application log (`loguru` + `SensitiveFilter`). They
  appear only in the `IncidentBrief.raw_text_excerpt` and `log_summary` fields,
  which are treated as sensitive in-memory data.

- **Remediation is advisory.** `RemediationPlannerAgent` attaches the plan to
  the `RCAReport`; it does not invoke any execution engine. Any step with
  `requires_human_approval = True` surfaces as advisory-only and requires the
  operator to confirm with `AEGIS_PROD_CONFIRMED=1` at execution time.

- **Dump hash deduplication.** If an operator re-submits the same dump, the
  `FilesystemStore.find_by_hash()` check at the top of `Orchestrator.run()`
  returns the cached `RCAReport` immediately — no LLM calls are made for
  duplicate submissions.

- **No raw payload in the model prompt.** Only PII-scrubbed, structured fields
  from `IncidentBrief` (not the raw excerpt or full log text) are sent to the
  `RemediationPlannerAgent`'s LLM call, per the security rule in
  `.claude/CLAUDE.md §3`.
