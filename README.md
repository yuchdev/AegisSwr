# Aegis SWR (Synthetic War Room)

Aegis SWR is a pluggable, Python-based production forensics platform designed for rapid investigation of mission-critical production incidents. Instead of relying on a single AI model to guess a root cause, Aegis SWR spins up a Multi-Agent System (MAS) where specialized AI experts debate conflicting telemetry data inside a virtual "Synthetic War Room".

The product converts raw telemetry into a highly descriptive **Investigator's Rationale (IR)**, detailing not just the "what," but the logical debate, discarded hypotheses, and consensus maps leading to the resolution.

See **[docs/README.md](docs/README.md)** for the full index of architecture, roadmap, and analysis documents.

---

## ✨ Core Features

* **Multi-Agent Discussion Logs:** Provides the full transcript of specialized agents (OS Kernel, Code Analyst, Skeptic) arguing over system evidence.
* **The Data Adapter Pipeline:** An intelligent preprocessing layer that automatically filters, deduplicates, and condenses gigabytes of raw logs and crashdumps into token-dense incident briefs.
* **Probabilistic Auto-Remediation:** Outputs concrete diagnostic instructions alongside a generated code patch mapped against a specific confidence rating.
* **Human-in-the-Loop Triggers:** Automatically queries the developer for specific environmental clarifications if the synthetic agents hit a low-confidence deadlock.

---

## 🏗️ Architecture & Pluggable Backends

Aegis SWR is architected as a core Python orchestration layer that exposes abstract interfaces for specialized backends. These backends can run as local Python modules or remote microservices, dynamically registering themselves to extend the platform's diagnostic intelligence.

### Backend Interface Matrix

| Backend Interface Type | Description                                                                                          | Component Examples                                                |
|------------------------|------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| **`AIAPIBackend`**     | Manages foundational LLM communication, token streaming, and semantic context isolation.             | OpenAI, Anthropic, Local vLLM / DeepSeek instances.               |
| **`DebugBackend`**     | Wraps native command-line debuggers to extract call stacks, symbols, and frame states from binaries. | `cdb.exe` (Windows), `gdb`/`lldb` (Linux/macOS core dumps).       |
| **`StorageBackend`**   | Handles multi-tier persistence for raw incident payloads, active state graphs, and vector patterns.  | PostgreSQL (State), AWS S3 / MinIO (Dumps), Qdrant (Vector Logs). |

---

## 🚀 Quick Start

### Prerequisites

* Python 3.12+
* Docker / gVisor (for secure code patch validation steps)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-organization/aegis-swr.git
cd aegis-swr

```

2. Install dependencies using Poetry:
```bash
poetry install

```


3. Configure your telemetry and backend providers. Runtime settings live in
   `<config-dir>/config.json`; the per-fault-class agent weight matrix
   lives alongside it in `<config-dir>/agents.json`. Seed both from the
   templates in the repo root:

> `<config-dir>` = `~/.aegis-swr/`

```bash
cp config.example.json <config-dir>/config.json
cp agents.example.json <config-dir>/agents.json
```
```json
{
  "core": { "max_debate_rounds": 4, "consensus_threshold": 0.85 },
  "backends": {
    "ai": { "provider": "anthropic", "model": "claude-sonnet-4-6" },
    "debug": { "engine": "auto", "symbol_server_url": "https://symbols.internal.net" },
    "storage": {
      "database_url": "postgresql://user:pass@localhost:5432/aegis",
      "object_store_url": "s3://prod-incidents"
    }
  }
}
```
Individual keys can be edited with `aegis config set <dotted.key> <value>`
(e.g. `aegis config set backends.ai.model claude-opus-4-8`), or overridden at
runtime with `AEGIS__*` environment variables. `aegis config show` prints the
resolved settings with secrets redacted.


4. Launch the core orchestration server:
```bash
uv run python -m aegis_swr.core.server

```

## 💻 Examples

### Variant A: Baseline

```powershell
$env:AEGIS_SYMBOL_CACHE = 'C:\symbols'
.venv\Scripts\aegis.exe analyze --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' --engine cdb --ai openai --store filesystem --assume "There's probability that the crash was deliberately injected. Check this theory" --output json --log-severity DEBUG --evidence-severity TRACE
```

### Variant B: Debug Symbols

```powershell
.venv\Scripts\aegis.exe analyze --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' --sym 'C:\Users\atatat\Projects\wincrashdebugger\x64\Release' --sym 'C:\symbols' --engine cdb --ai openai --store filesystem --assume "There's probability that the crash was deliberately injected. Check this theory" --output rich --log-severity DEBUG --evidence-severity TRACE
```

### 3.4 Variant C: Logs Only

```powershell
$env:AEGIS_SYMBOL_CACHE = ''
.venv\Scripts\aegis.exe analyze --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' --log 'C:\LBS\CrashDumps\CrashUi.log' --engine cdb --ai openai --store filesystem --store-config '.\reports-log' --assume "There's probability that the crash was deliberately injected. Check this theory" --output json --log-severity INFO --evidence-severity TRACE
```

`CrashUi.log` was generated from the plog call-sites in the source:

```
2026-03-30 17:33:14.001 INFO  [main] CrashUi application started
2026-03-30 17:33:14.003 DEBUG [Crash_Window::Crash_Window@CrashUi.cpp:95] Handler bound: on_access_violation_click
2026-03-30 17:33:46.801 DEBUG [Crash_Window::on_access_violation_click@CrashUi.cpp:117] Setting pointer to nullptr
2026-03-30 17:33:46.802 INFO  [Crash_Window::on_access_violation_click@CrashUi.cpp:120] Writing to nullptr
```

> **Data Adapter note (Variant B):** `source.incident_timestamp` is not backfilled from the
> CDB extraction result, so Stage 4 logged *"No incident timestamp; falling back to last 500
> log lines"* and included all 8 log lines unconditionally. Known limitation - see §10.3.

---

## 📥 📤 Input & Output Flow

### Triggering an Investigation (CLI Example)

```bash
uv run aegis analyze \
  --log ./production_fail.log \
  --dump ./core.20260529.dmp \
  --shot ./error_ui.png
```

#### Configuration: CLI plus the config file

Startup options can be supplied two ways, and both share one schema
(`AnalyzeConfig` - the single source of truth for every setting key):

1. **CLI flags** - `aegis analyze --ai openai …`
2. **JSON config file** - `<config-dir>/config.json` (override with `--config PATH`)

When both are present the file is applied first and explicit CLI flags are
layered on top - `defaults < config.json < CLI`. Copy
[`config.example.json`](config.example.json) to the default path to get started,
or run `aegis analyze … --save-config` to write your current flags there.

### The Output Payload

The platform processes the inputs through the **Data Adapter**, runs the agentic debate loop, and returns a structured JSON response:

```json
{
  "incident_id": "8f3b9a2c-1a4d-4e9e-8b6c-2f1a3b4c5d6e",
  "conclusion": "Race condition triggered by high I/O latency exposing an unhandled early-return pointer bug in db_writer.cpp:142.",
  "confidence_score": 0.92,
  "investigators_rationale": [
    "OS Kernel Agent argued for a deadlock due to I/O latency, but Code Analyst Agent pointed out an uninitialized pointer in the header parser. Skeptic Agent verified that the pointer is only uninitialized when the I/O takes >500ms. Consensus: Race condition.",
  ],
  "mitigation_instructions": [
    "1. Temporarily increase database write-timeout limits to 1000ms.",
    "2. Deploy the verified patch to db_writer.cpp."
  ],
  "probabilistic_fix": "--- a/src/db_writer.cpp\n+++ b/src/db_writer.cpp\n@@ -142,5 +142,6 @@\n if (latency > 500) {\n+  cleanup_pointer();\n   return ERR_TIMEOUT;\n }"
}

```

> **Product Note:** "We aren't just developing a tool that reads dumps. We are developing a Synthetic Expert Panel. When a crash occurs, our product performs a 10-minute 'Agentic Discussion' that replaces 4 hours of senior developer meetings."
