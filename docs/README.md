# Documentation Registry

All design, planning, and analysis documents for the Aegis SWR project.

---

## Agentic Fleet (`agent/`)

How to use the Claude Code agent fleet, skills, and hooks for day-to-day
development on Aegis SWR.

| Document | Description |
|---|---|
| [tutorial.md](agent/tutorial.md) | **Start here.** Practical onboarding guide: scenarios for every common task, common mistakes, quick-reference card. Aimed at developers new to Claude Code. |
| [agents.md](agent/agents.md) | Reference for all 9 dev agents (`architect`, `coder`, `qa`, `feature-reviewer`, `background-reviewer`, `docs`, `incident-analyst`, `security-auditor`, `orchestrator`): model, tools, responsibilities, when to use. |
| [skills.md](agent/skills.md) | Reference for all 11 slash-command skills (`/adr-write`, `/pr-review`, `/test-gap`, `/runbook-write`, `/post-mortem`, `/dep-audit`, `/secret-scan`, `/playbook-validate`, `/link-check`, `/doc-xref`, `incident-triage`): invocation, step-by-step behaviour, when to use. |
| [hooks.md](agent/hooks.md) | Reference for all hooks that run automatically (`guard_bash`, `secret_scan`, `post_edit_format`, `dep_audit`, `doc_link_check`, `github_audit`, `session_start`, `run_tests`): what each blocks/logs, override env vars, audit log locations. |
| [agentic_fleet_design.md](agent/agentic_fleet_design.md) | Design and operational details for the agentic fleet: agent definitions, prompts, hooks, and orchestration guidance. |

---

## Configuration Reference (`configuration/`)

> `<config-dir>` = `~/.aegis-swr/`

User-facing reference for every CLI option and configuration field, generated
from the source of truth in `src/aegis_swr/`.

| Document                              | Description                                                                                                                                                       |
|---------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [cli.md](configuration/cli.md)        | Every `aegis` command (`analyze`, `export`, `server`, `config show/set`) with all options, defaults, allowed values, output modes, and exit codes.                |
| [config.md](configuration/config.md)  | The unified `<config-dir>/config.json`: analyze keys (flat options plus the `ingest` / `logging` / `evidence` / `process` logging sections) and the nested `core` / `backends` / `sandbox` / `api` runtime sections, sources, precedence, and env overrides. |
| [agents.md](configuration/agents.md)  | The `<config-dir>/agents.json` weight matrix: the four agents, all ten fault-class keys with default weights, and how the consensus score uses them.                    |
| [coverage.md](configuration/coverage.md) | Test coverage configuration (85% threshold) for both the main project and prototype; commands, CI integration, and troubleshooting. |

---

## Architecture Decision Records (`adr/`)

| Document                                                         | Description                                                                                                                                                                                                                                                                                           |
|------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [aegis-swr-roadmap.md](adr/aegis-swr-roadmap.md)                 | Full 5-phase development roadmap: Phase 1 Prototype Deconstruction → Phase 2 Data Adapter → Phase 3 Multi-Agent System → Phase 4 Output Synthesis → Phase 5 Production Hardening. Covers consensus threshold logic, token budget guardrails, and deployment vectors.                                  |
| [proposed-design-aegis-swr.md](adr/proposed-design-aegis-swr.md) | Target system architecture: hybrid enterprise API deployment topology, Data Adapter pipeline (temporal windowing, log clustering, OCR), Synthetic War Room agent layout (OS Kernel, Code Analyst, Skeptic), REST/gRPC endpoint specifications, secure code validation sandbox (gVisor / Firecracker). |
| [new-ui-rich-based-design.md](adr/new-ui-rich-based-design.md)   | Full design specification for the three-pane `WarRoomView`: Evidence Stream (left half), Forensic Agents (right top), Investigation Process (right bottom). Covers animation elements, event→widget mapping, post-conclusion transition, implementation plan, and Rich API inventory.                 |
---

## Production Design Specifications (`specs/`)

Authoritative production specifications for the `aegis-swr` package under `src/aegis_swr/`.

| Document                                                               | Description                                                                                                                                                                                                                                                                                                      |
|------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [PRODUCTION_DESIGN_SPEC.md](specs/PRODUCTION_DESIGN_SPEC.md)           | Full production design: directory structure, `pyproject.toml`, all Pydantic schemas, FaultClass enum, Data Adapter pipeline (9 stages), all 5 backend ABCs, MAS LangGraph state graph, consensus algorithm, 3-tier storage schema, REST/SSE API endpoints, secure sandbox, config system, CLI, testing strategy. |
| [agentic_implementation_plan.md](specs/agentic_implementation_plan.md) | Detailed execution brief for every implementation step: per-phase agent matrix, verbatim per-agent instructions, inputs provided, verification gates, and cross-cutting implementation rules.                                                                                                                    |
| [generic_implementation_plan.md](specs/generic_implementation_plan.md) | 10-phase implementation plan (Foundation → Data Adapter → AI/Debug Backends → MAS → Storage → CLI → API → Sandbox → Testing) with per-phase deliverables and a dependency graph; inlines the Data Adapter & Backend specifications; and includes the completed log-subsystem re-engineering chapter (three logging channels). |
| [implementation_status.md](specs/implementation_status.md)             | Live progress tracker against the 10-phase plan: which phases are complete, current lint/type/test gate status, and per-phase delivered artifacts.                                                                                                                                                               |
---

## Prototype Analysis Specs (`prototype-analysis-specs/`)

Outputs produced by the Phase 1.1 analysis run against the WinCrashAnalyzer prototype. Used as input to Phase 1.2 design decisions.

| Document                                                         | Description                                                                                                                                                                                                                                                                                                               |
|------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [win-dependencies.md](prototype/win_dependencies.md)             | Complete register of 9 Windows-specific components (cdb.exe, symbol paths, `.dmp` format, ActiveXObject COM, WinDbg DDM, NTSTATUS codes, HTTP bridge, CDB command sequences) with exact `file:line` locations and cross-platform replacement strategies.                                                                  |
| [prompt-heuristics.md](prototype/prompt_heuristics.md)           | All LLM system prompts, user prompt templates, regex rules, and sanitization heuristics extracted from the prototype. Sorted by troubleshooting domain and mapped to their target Aegis SWR agent.                                                                                                                        |
| [token-waste-report.md](prototype/token_waste_report.md)         | Token efficiency audit: per-category waste estimates (worst-case ~17,440 tokens/request), comparison of prototype vs. target behavior, and 6 algorithmic guidelines for the Data Adapter layer.                                                                                                                           |
| [gap-analysis.md](prototype/gap_analysis.md)                     | 7 conceptual gaps in the prototype (tunnel vision, no reasoning trail, no non-crash support, filename-based deduplication, no output validation, no multi-turn context, no symbol quality signal) each mapped to the Aegis SWR component that resolves it.                                                                |
| [aegis-swr-vs-prototype.md](prototype/aegis_swr_vs_prototype.md) | End-to-end reproduction of the WinCrashAnalyzer prototype's resolution of `CrashUi.exe.1324.dmp` (deliberate NULL-pointer write) through the full Aegis SWR pipeline - CDB + OpenAI (gpt-5.4) + filesystem store. Side-by-side result comparison, the five backend-engine fixes the run surfaced, and reproduction steps. |

---

## QA (`qa/`)

Project QA guidance, checklists, and coverage requirements used by `qa` agents and CI.

| Document                                          | Description                                                                                                |
|---------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [code_test_coverage.md](qa/code_test_coverage.md) | Coverage requirements checklist, PR checklist, and runnable commands to validate coverage (85% threshold). |

---

## UI (`ui/`)

Design notes and text mockups used by the UI team and for documentation/examples.

| Document                                                        | Description                                                                                                      |
|-----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| [ui-investigation-process.txt](ui/ui-investigation-process.txt) | ASCII mockup / example of the Investigation UI's Evidence Stream and Forensic Agents view (debug output sample). |
| [ui-root-cause-analysis.txt](ui/ui-root-cause-analysis.txt)     | Plain-text Root Cause Analysis report example produced by the agents (RCA template / sample output).             |
