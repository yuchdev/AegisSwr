# Documentation Registry

All design, planning, and analysis documents for the Aegis SWR project.

---

## Architecture Decision Records (`adr/`)

| Document | Description |
|----------|-------------|
| [aegis-swr-roadmap.md](adr/aegis-swr-roadmap.md) | Full 5-phase development roadmap: Phase 1 Prototype Deconstruction → Phase 2 Data Adapter → Phase 3 Multi-Agent System → Phase 4 Output Synthesis → Phase 5 Production Hardening. Covers consensus threshold logic, token budget guardrails, and deployment vectors. |
| [proposed-design-aegis-swr.md](adr/proposed-design-aegis-swr.md) | Target system architecture: hybrid enterprise API deployment topology, Data Adapter pipeline (temporal windowing, log clustering, OCR), Synthetic War Room agent layout (OS Kernel, Code Analyst, Skeptic), REST/gRPC endpoint specifications, secure code validation sandbox (gVisor / Firecracker). |

---

## Roadmap Task Specifications (`roadmap/`)

Detailed task definitions for each roadmap phase. These describe *what* must be produced.

| Document | Phase | Description |
|----------|-------|-------------|
| [1.1-analysis-of-wincrashanalyzer.md](roadmap/1.1-analysis-of-wincrashanalyzer.md) | 1.1 | Audit & deconstruction of the WinCrashAnalyzer prototype: Windows dependency inventory, prompt heuristics extraction, token waste profiling, gap & debt mapping. |
| [1.2-core-design-and-implementation.md](roadmap/1.2-core-design-and-implementation.md) | 1.2 | Core system design: orchestration state machine with weighted consensus algorithm, pluggable backend interface model, server-side CLI/storage architecture, client-facing API layer, secure sandbox for code validation. |

---

## Agentic Execution Instructions (`instructions/`)

Step-by-step prompts and agent matrix definitions for automated implementation runs. These describe *how* to execute each roadmap phase using a multi-agent workflow.

| Document | Phase | Agent Profiles | Deliverables |
|----------|-------|----------------|--------------|
| [1.1-analysis-of-wincrashanalyzer-instructions.md](instructions/1.1-analysis-of-wincrashanalyzer-instructions.md) | 1.1 | `DependencyScout`, `PromptExtractor`, `TelemetryAuditor` | Four spec files in `docs/prototype-analysis-specs/` |
| [1.2-core-design-and-implementation-instructions.md](instructions/1.2-core-design-and-implementation-instructions.md) | 1.2 | `LeadArchitect`, `BackendEngineer`, `SecurityReviewer` | ADR files in `docs/adrs/`, Python package skeleton in `src/aegis/` |

---

## Production Design Specifications (`specs/`)

Authoritative production specifications for the `aegis-swr` package under `src/aegis_swr/`.

| Document | Description |
|----------|-------------|
| [PRODUCTION_DESIGN_SPEC.md](specs/PRODUCTION_DESIGN_SPEC.md) | Full production design: directory structure, `pyproject.toml`, all Pydantic schemas, FaultClass enum, Data Adapter pipeline (9 stages), all 5 backend ABCs, MAS LangGraph state graph, consensus algorithm, 3-tier storage schema, REST/SSE API endpoints, secure sandbox, config system, CLI, testing strategy. |
| [IMPLEMENTATION_PLAN.md](specs/IMPLEMENTATION_PLAN.md) | 10-phase implementation plan (Weeks 1–16): Foundation → Data Adapter → AI Backends → Debug Backends → MAS Engine → Storage → API → Sandbox → CLI → Testing & Hardening. Per-phase deliverables, success criteria, and dependency graph. |
| [AGENTIC_IMPLEMENTATION_PLAN.md](specs/AGENTIC_IMPLEMENTATION_PLAN.md) | Detailed agentic execution brief for every implementation step: agent matrix per phase, verbatim instructions per agent, inputs provided, verification gates, and cross-cutting implementation rules. |
| [IMPLEMENTATION_STATUS.md](specs/IMPLEMENTATION_STATUS.md) | Live progress tracker against the 10-phase plan: which phases are complete, current lint/type/test gate status, and per-phase delivered artifacts. |

---

## Prototype Analysis Specs (`prototype-analysis-specs/`)

Outputs produced by the Phase 1.1 analysis run against the WinCrashAnalyzer prototype. Used as input to Phase 1.2 design decisions.

| Document | Description |
|----------|-------------|
| [WIN_DEPENDENCIES.md](prototype-analysis-specs/WIN_DEPENDENCIES.md) | Complete register of 9 Windows-specific components (cdb.exe, symbol paths, `.dmp` format, ActiveXObject COM, WinDbg DDM, NTSTATUS codes, HTTP bridge, CDB command sequences) with exact `file:line` locations and cross-platform replacement strategies. |
| [PROMPT_HEURISTICS.md](prototype-analysis-specs/PROMPT_HEURISTICS.md) | All LLM system prompts, user prompt templates, regex rules, and sanitization heuristics extracted from the prototype. Sorted by troubleshooting domain and mapped to their target Aegis SWR agent. |
| [TOKEN_WASTE_REPORT.md](prototype-analysis-specs/TOKEN_WASTE_REPORT.md) | Token efficiency audit: per-category waste estimates (worst-case ~17,440 tokens/request), comparison of prototype vs. target behavior, and 6 algorithmic guidelines for the Data Adapter layer. |
| [GAP_ANALYSIS.md](prototype-analysis-specs/GAP_ANALYSIS.md) | 7 conceptual gaps in the prototype (tunnel vision, no reasoning trail, no non-crash support, filename-based deduplication, no output validation, no multi-turn context, no symbol quality signal) each mapped to the Aegis SWR component that resolves it. |
