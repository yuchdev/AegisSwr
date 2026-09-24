# Aegis SWR (Synthetic War Room)

Aegis SWR is a pluggable, Python-based production diagnostic platform designed for rapid investigation of mission-critical production incidents. Instead of relying on a single AI model to guess a root cause, Aegis SWR spins up a Multi-Agent System (MAS) where specialized AI experts debate conflicting telemetry data inside a virtual "Synthetic War Room".

The product converts raw telemetry into a highly descriptive **Investigator's Rationale (IR)**, detailing not just the "what," but the logical debate, discarded hypotheses, and consensus maps leading to the resolution.

See **[docs/README.md](docs/README.md)** for the full index of architecture, roadmap, and analysis documents.

---

## ✨ Core Features

* **Multi-Agent Discussion Logs:** Provides the full transcript of specialized agents (OS Kernel, Code Analyst, Skeptic) arguing over system evidence.
* **The Data Adapter Pipeline:** An intelligent preprocessing layer that automatically filters, deduplicates, and condenses gigabytes of raw logs and crashdumps into token-dense incident briefs.
* **Probabilistic Auto-Remediation:** Outputs concrete diagnostic instructions alongside a generated code patch mapped against a specific confidence rating.
* **Human-in-the-Loop Triggers:** Automatically queries the developer for specific environmental clarifications if the synthetic agents hit a low-confidence deadlock.

---

## 🏗️ Architecture

Aegis SWR is built around a **Data Adapter → Multi-Agent Debate → Consensus** pipeline.
See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design rationale - deployment strategy,
Data Adapter preprocessing, agent personas, HITL escalation, and key constraints.
See **[docs/specs/implementation_spec.md](docs/specs/implementation_spec.md)** for the
authoritative implementation specification (schemas, pipelines, API contract).

---

## 🚀 Quick Start

### Prerequisites

* Python 3.12+
* Docker / gVisor (for secure code patch validation steps)
* **Docker Desktop for Windows** — required when using the **OpenHands** Code
  Intelligence backend only. Not required for the OpenClaude or Claude Code backends.
  See [Code Intelligence backends](#code-intelligence-backends) below.

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-organization/AegisSwr.git
cd AegisSwr
```

2. Install dependencies using uv:
```bash
uv sync
```

3. Check if openclaude is installed by the uv hook; otherwise, install it manually:
```bash
openclaude --version || npm install -g @gitlawb/openclaude@latest
```

4. Configure your telemetry and backend providers. Runtime settings live in
   `<config-dir>/config.json`; seed it from the template in the repo root.
   Consensus weight is a property of each agent class, not a config file - see
   [docs/config/agents.md](docs/config/agents.md):

> `<config-dir>` = `~/.aegis-swr/`

```bash
cp config.example.json <config-dir>/config.json
```
```json
{
  "core": {
     "max_debate_rounds": 4, 
     "consensus_threshold": 0.85
  },
  "backends": {
    "ai": {
       "provider": "anthropic", 
       "anthropic": {
          "model": "claude-sonnet-4-6"
       }
    },
    "debug": {
       "engine": "auto", 
       "symbol_server_url": "https://symbols.internal.net"
    },
    "storage": {
      "database_url": "postgresql://user:pass@localhost:5432/aegis",
      "object_store_url": "s3://prod-incidents"
    }
  }
}
```
Individual keys can be edited with `aegis config set <dotted.key> <value>`
(e.g. `aegis config set backends.ai.anthropic.model claude-opus-4-8`), or overridden at
runtime with `AEGIS__*` environment variables. `aegis config show` prints the
resolved settings with secrets redacted.


5. Launch the core orchestration server:
```bash
uv run python -m aegis.core.server
```

6. Launch `openclaude` in gRPC mode. This starts the headless sidecar that
   backs Code Intelligence (see
   [Milestone 0004 — OpenClaude Integration](docs/roadmap/0004-code-intelligence/plan.md)).
   Aegis SWR never launches this process for you in external mode
   (`OPENCLAUDE_AUTO_START=false`, the default) - start it yourself and point
   Aegis SWR at it:
```bash
openclaude --grpc --port 50051 \
  --allowed-tools Read,Grep,Glob,Bash \
  --bash-allowlist gtags,global,semgrep,rg,find,cat
```
   Then export the endpoint so Aegis SWR can find it:
```bash
export OPENCLAUDE_GRPC_URL=localhost:50051
```
   Verify the sidecar is actually up before relying on it. A plain TCP check
   works with no extra tooling:
```bash
bash -c '</dev/tcp/localhost/50051' && echo "openclaude gRPC port is open"
```
   For a real protocol-level check (recommended once, to catch a port that's
   open but not speaking gRPC), use
   [`grpcurl`](https://github.com/fullstorydev/grpcurl) against the committed
   proto contract:
```bash
grpcurl -plaintext \
  -proto aegis/openclaude/grpc/proto/openclaude.proto \
  -d '{"prompt": "ping", "run_id": "smoke-test"}' \
  localhost:50051 aegis.openclaude.v1.AgentService/Query
```
   A healthy sidecar streams back frames terminated by a `DONE` message. If
   the connection is refused, re-check the `--port` you launched with against
   `OPENCLAUDE_GRPC_URL`; if `grpcurl` reports a permission/allowlist error,
   your launch flags don't match `OPENCLAUDE_ALLOWED_TOOLS` /
   `OPENCLAUDE_BASH_ALLOWLIST` (see [C7](docs/roadmap/0004-code-intelligence/plan.md#c7--permission-and-tool-allowlist-enforcement)).

## Code Intelligence backends

Aegis SWR supports three selectable, optional Code Intelligence backends. Exactly one is
active at a time — selection is driven by environment variables with no fallback chain.
All three are off by default; enabling any one requires only environment variables with
no Python changes.

| Backend         | Presence signal            | Sandbox                   | Note                                  |
|-----------------|----------------------------|---------------------------|---------------------------------------|
| **OpenClaude**  | `OPENCLAUDE_GRPC_URL` set  | Host OS (allowlist guard) | gRPC sidecar, long-lived              |
| **Claude Code** | `CLAUDE_CODE_ENABLED=true` | Host OS (allowlist guard) | `claude` CLI, one-shot per delegation |
| **OpenHands**   | `OPENHANDS_SERVER_URL` set | Docker (default)          | REST/WS sidecar, long-lived           |

See **[docs/config/harness-selection.md](/docs/config/harness-selection.md)** for the selection
contract, truth table, and the two failure modes. Per-backend setup guides:
[OpenClaude](/docs/config/openclaude-setup.md) ·
[Claude Code](/docs/config/claude-code-setup.md) ·
[OpenHands](/docs/config/openhands-setup.md).

## Code Intelligence (OpenClaude)

Aegis SWR can delegate open-ended, multi-file code-navigation tasks to
[OpenClaude](https://github.com/Gitlawb/openclaude) running as a headless gRPC
sidecar pointed at any OpenAI-compatible backend (including a self-hosted vLLM
instance). This capability is **optional** and **off by default**.

**Enable it with a single environment variable** — no Python changes:

```bash
export OPENCLAUDE_GRPC_URL=localhost:50051
```

When `OPENCLAUDE_GRPC_URL` is unset, code intelligence is simply unavailable and
the rest of the pipeline is unaffected.

**Recommended external-mode launch** (OpenClaude already running, read-only
forensic allowlist):

1. Start OpenClaude yourself (its model/provider is your concern):
set `CLAUDE_CODE_USE_OPENAI` / `OPENAI_BASE_URL` / `OPENAI_MODEL` / `OPENAI_API_KEY`,
launch it headless with a read-only tool whitelist, then

```bash
export OPENCLAUDE_GRPC_URL=localhost:50051
```

smoke-test the wiring without connecting (dry-run by default)

```bash
aegis code-intel check
```

> Aegis SWR does **not** manage OpenClaude's model or provider — you do, via
> OpenClaude's own environment variables. Aegis SWR only needs
> `OPENCLAUDE_GRPC_URL` to find the running server.

See **[docs/config/openclaude-setup.md](/docs/config/openclaude-setup.md)** for the full setup
guide (managed vs external mode, the tool/Bash allowlists, and the complete
environment-variable reference).

## 💻 Examples

### Variant A: Baseline

```powershell
$env:AEGIS_SYMBOL_CACHE = 'C:\symbols'
.venv\Scripts\aegis.exe analyze --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' --engine cdb --ai openai --store filesystem --prompt "There's probability that the crash was deliberately injected. Check this theory" --output json --log-severity DEBUG --evidence-severity TRACE
```

### Variant B: Debug Symbols

```powershell
.venv\Scripts\aegis.exe analyze --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' --sym 'C:\Users\atatat\Projects\wincrashdebugger\x64\Release' --sym 'C:\symbols' --engine cdb --ai openai --store filesystem --prompt "There's probability that the crash was deliberately injected. Check this theory" --output rich --log-severity DEBUG --evidence-severity TRACE
```

### 3.4 Variant C: Logs Only

```powershell
$env:AEGIS_SYMBOL_CACHE = ''
.venv\Scripts\aegis.exe analyze --dump 'C:\LBS\CrashDumps\CrashUi.exe.1324.dmp' --log 'C:\LBS\CrashDumps\CrashUi.log' --engine cdb --ai openai --store filesystem --store-config '.\reports-log' --prompt "There's probability that the crash was deliberately injected. Check this theory" --output json --log-severity INFO --evidence-severity TRACE
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
  --logs ./production_fail.log \
  --crashdump ./core.20260529.dmp \
  --screenshot ./error_ui.png
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
    "OS Kernel Agent argued for a deadlock due to I/O latency, but Code Analyst Agent pointed out an uninitialized pointer in the header parser. Skeptic Agent verified that the pointer is only uninitialized when the I/O takes >500ms. Consensus: Race condition."
  ],
  "mitigation_instructions": [
    "1. Temporarily increase database write-timeout limits to 1000ms.",
    "2. Deploy the verified patch to db_writer.cpp."
  ],
  "probabilistic_fix": "--- a/src/db_writer.cpp\n+++ b/src/db_writer.cpp\n@@ -142,5 +142,6 @@\n if (latency > 500) {\n+  cleanup_pointer();\n   return ERR_TIMEOUT;\n }"
}
```

> **Product Note:** "We aren't just developing a tool that reads dumps. We are developing a Synthetic Expert Panel. When a crash occurs, our product performs a 10-minute 'Agentic Discussion' that replaces 4 hours of senior developer meetings."
