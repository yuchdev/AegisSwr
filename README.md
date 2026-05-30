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

| Backend Interface Type | Description | Component Examples |
| --- | --- | --- |
| **`AIAPIBackend`** | Manages foundational LLM communication, token streaming, and semantic context isolation. | OpenAI, Anthropic, Local vLLM / DeepSeek instances. |
| **`DebugBackend`** | Wraps native command-line debuggers to extract call stacks, symbols, and frame states from binaries. | `cdb.exe` (Windows), `gdb`/`lldb` (Linux/macOS core dumps). |
| **`StorageBackend`** | Handles multi-tier persistence for raw incident payloads, active state graphs, and vector patterns. | PostgreSQL (State), AWS S3 / MinIO (Dumps), Qdrant (Vector Logs). |

---

## 🚀 Quick Start

### Prerequisites

* Python 3.10+
* Docker / gVisor (for secure code patch validation steps)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-organization/aegis-swr.git
cd aegis-swr

```


2. Install dependencies using uv:
```bash
uv sync --group dev

```


3. Configure your telemetry and backend providers in `config.yaml`:
```yaml
core:
  max_debate_rounds: 4
  consensus_threshold: 0.85

backends:
  ai_api:
    provider: "anthropic"
    endpoint: "remote-microservice" # Can point to a local instance or external API
  debug:
    provider: "gdb-linux"
    symbol_server: "https://symbols.internal.net"
  storage:
    database_url: "postgresql://user:pass@localhost:5432/aegis"
    object_store_url: "s3://prod-incidents"

```


4. Launch the core orchestration server:
```bash
uv run python -m aegis.core.server

```



---

## 📥 📤 Input & Output Flow

### Triggering an Investigation (CLI Example)

```bash
uv run aegis analyze \
  --logs ./production_fail.log \
  --crashdump ./core.20260529.dmp \
  --screenshot ./error_ui.png

```

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
