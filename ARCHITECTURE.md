# Aegis SWR — Architecture Overview

This document describes the high-level design: why the system is structured as it is,
how the major components fit together, and what constraints shaped each decision.
For the authoritative implementation specification (module layout, schemas, pipelines,
API contract), see [docs/specs/implementation_spec.md](docs/specs/implementation_spec.md).

---

## 1. Deployment Strategy

Aegis SWR is designed as a **Hybrid Enterprise Platform (Core API + Extension Ecosystem)**
to handle the security and operational constraints of incident forensics in real environments.

| Deployment Vector | How It Works | Why It Is Necessary |
|---|---|---|
| **Core Engine via Secure API** | A centralized or VPC-hosted backend that handles MAS orchestration and LLM context management. | Incident logs and dumps contain PII, credentials, and proprietary logic. A secure API allows deployment inside the client's isolated cloud (AWS VPC / Azure Private Link). |
| **SIEM / Observability Plugins** | Integrations with Datadog, Splunk, or New Relic. | Puts Aegis SWR where incidents happen — engineers click *"Analyze with Aegis"* directly from a Datadog alert without switching tools. |
| **ChatOps Skills (Slack / Teams)** | A bot interface that surfaces the Synthetic War Room into engineering triage channels. | The team sees the agents debating in real-time inside their existing Slack war room, not in a separate dashboard. |

---

## 2. The Data Adapter (preprocessing pipeline)

Feeding raw logs and crash dumps directly to an LLM is financially unviable and
produces low-quality output. The **Data Adapter** is an algorithmic preprocessing
layer that maximizes information density before any agent sees the data.

```
[Raw Logs + Dumps + Screenshots] → [ Data Adapter ] → [Token-Dense Incident Brief] → [Synthetic War Room]
```

### Log compression

- **Temporal windowing**: slice a strict time window around the incident timestamp
  (e.g. ±2 minutes), discarding irrelevant history.
- **Structural clustering**: non-LLM algorithms (Drain / Logparser) compress millions
  of repetitive heartbeat lines into structural templates:
  `[14:02:11] Connection pool status OK (repeated 45,000 times)`
- **Anomaly isolation**: retain only lines containing `FATAL`, `CRITICAL`, `Exception`,
  or non-zero exit codes within the window.

### Crash dump extraction

Raw `.dmp` / `.core` files are passed through `cdb`, `gdb`, or `lldb`. Only the
faulting thread stack trace, register states, and loaded module versions are extracted
as a clean Markdown summary — the bulk binary data is discarded.

### Screenshot processing (vision-to-text)

Screenshots are OCR-processed locally to extract error dialog strings, UI element
layouts, and visible timestamps, then serialized as a JSON map for the agents:
`{ "ui_error_message": "Access Violation at 0x0000", "timestamp_visible": "True" }`.

---

## 3. The Synthetic War Room (multi-agent debate)

Once the Data Adapter produces the incident brief, four specialized agents instantiate
and run a controlled debate.

### Agent personas

| Agent | Bias |
|---|---|
| **OS Kernel Specialist** | Environmental limits, I/O bottlenecks, driver conflicts, memory pressure (ETW/WCT data). |
| **Code Analyst** | Software architecture bugs, uninitialized pointers, race conditions, logic errors in the codebase. |
| **Log Historian** | Cross-incident trend analysis — compares the current failure pattern against historical baselines. |
| **Skeptic (moderator)** | Challenges consensus — if Code Analyst blames a code bug, Skeptic asks *"Why did this only manifest during peak network traffic?"* |

### Investigator's Rationale

The platform exposes the full reasoning path as a threaded debate transcript:

```
[00:02] OS Kernel Agent:  Stack trace indicates deadlock on Mutex 0x4A2F.
                          Matches high I/O latency logged right before the crash.
[00:04] Code Analyst:     Mutex 0x4A2F only held during DB serialization.
                          Missing unlock on early return at db_writer.cpp:142.
[00:05] Skeptic:          Why did this pass CI/CD for 3 months?
                          The code path at line 142 is only reached if DB write > 500 ms.
[00:07] Consensus:        Race condition triggered by I/O latency exposes early-return
                          bug in db_writer.cpp:142. Confidence: 0.92.
```

---

## 4. Input / output pipeline

```
┌─────────────────────────────────────────────────┐
│  INPUTS: Raw Logs + Crash Dumps + Screenshots   │
└──────────────────────┬──────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────┐
│  DATA ADAPTER: compression + feature extraction │
└──────────────────────┬──────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────┐
│  SYNTHETIC WAR ROOM: multi-agent debate loop    │
└──────────────────────┬──────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────┐
│  OUTPUTS                                        │
│  1. Root cause conclusion + confidence metrics  │
│  2. Step-by-step mitigation instructions        │
│  3. Probabilistic code fix (git diff)           │
│  4. HITL clarification prompt (if deadlocked)   │
└─────────────────────────────────────────────────┘
```

---

## 5. Key design constraints

### Security and PII scrubbing

Logs routinely contain emails, card numbers, and credentials. Sending them to a
public LLM breaks GDPR/HIPAA compliance. The Data Adapter runs a local, deterministic
regex/NER pipeline *before* tokenization to scrub PII and replace it with typed
placeholders (`[SCRUBBED_EMAIL_1]`).

### Latency and token budget

Agent debates can loop indefinitely. Aegis SWR enforces a **hard round limit**
(default: 4 rounds) and a **consensus threshold** (default: 85% confidence alignment).
Early consensus terminates the debate automatically. See the token efficiency analysis
in [docs/reviews/token-waste-report.md](docs/reviews/token-waste-report.md).

### Evaluation and regression

Testing a non-deterministic multi-agent system requires a regression suite of
historical incidents where the true root cause is already known. New agent versions
run against this suite in CI to verify they still converge on the correct conclusion.

### Human-in-the-loop (HITL)

When all agents remain below 50% confidence after the round limit, the system
emits a structured `HITLRequest` to the human engineer:

> *"Agents are deadlocked between an expired SSL certificate and a routing table
> failure. Can you provide the current configuration of the staging ingress
> controller?"*

The human response is re-ingested through the Data Adapter and debate resumes.

---

## Further reading

| Document | What it covers |
|---|---|
| [docs/specs/implementation_spec.md](docs/specs/implementation_spec.md) | Full implementation spec: module layout, Pydantic schemas, Data Adapter pipeline (9 stages), backend ABCs, LangGraph state machine, REST/SSE API, sandbox, config. |
| [docs/adr/](docs/adr/) | Architecture Decision Records — point-in-time decisions with rationale. |
| [docs/roadmap/roadmap.md](docs/roadmap/roadmap.md) | 5-phase development roadmap. |
