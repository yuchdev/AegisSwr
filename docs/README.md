# Documentation Registry

All design, planning, and analysis documents for the Aegis SWR project.

---

## Architecture Decision Records (`adr/`)

Point-in-time decisions in [MADR](https://adr.github.io/madr/) format.
See [adr/README.md](adr/README.md) for the full inventory and naming conventions.
Mermaid diagrams live in `adr/assets/`.

| Document | Status | Description |
|---|---|---|
| [0001-new-ui-rich-based-design.md](adr/0001-new-ui-rich-based-design.md) | Implemented | WarRoomView three-pane terminal UI: Evidence Stream (left), Forensic Agents (right-top), Investigation Process (right-bottom). Animation, event→widget mapping, post-conclusion transition, Rich API inventory. |
| [0002-agent-weight-as-property.md](adr/0002-agent-weight-as-property.md) | Accepted | Consensus weight declared as a `ClassVar` on each agent class, not in an external config file; eliminates double-roster maintenance and enables per-agent defaults with a two-tier override. |
| [0003-code-intel-composition-root.md](adr/0003-code-intel-composition-root.md) | Accepted | Code-intelligence composition root moved to `openclaude/composition.py` and exposed via `aegis code-intel check`; `CodeBackend` renamed to `CodeIntelBackend`; orphan `app.py` deleted. |
| [0004-harness-composition-generalization.md](adr/0004-harness-composition-generalization.md) | Proposed | Composition root generalised out of `openclaude/` into a neutral `harness/` package for multi-backend Code Intelligence (OpenClaude + Claude Code + OpenHands); single-active-backend selection with loud ambiguity error; `Settings.openclaude` → `Settings.harness.openclaude`. Extends ADR 0003. |
| [template.md](adr/template.md) | - | Blank MADR template; use `/adr-write <title>` to scaffold a new record. |

---

## Design Specifications (`specs/`)

Long-form implementation specifications for `src/aegis_swr/`. For the high-level
architecture overview see **[ARCHITECTURE.md](../ARCHITECTURE.md)** (repo root).

| Document | Description |
|---|---|
| [implementation_spec.md](specs/implementation_spec.md) | Full implementation spec: module layout, `pyproject.toml`, all Pydantic schemas, FaultClass enum, Data Adapter pipeline (9 stages), all 5 backend ABCs, MAS LangGraph state machine, consensus algorithm, 3-tier storage schema, REST/SSE API endpoints, secure sandbox, config system, CLI, testing strategy. |
| [agentic_fleet_design.md](specs/agentic_fleet_design.md) | Design and operational details for the Claude Code dev fleet: agent definitions, hooks, MCP connections, model tiering, orchestration, worktree policy, secrets management, and scheduled tasks. |

---

## Roadmap (`roadmap/`)

Development timeline, per-phase task briefs, and live progress tracking.

| Document                                                                                     | Description                                                                                                                                                                                                                          |
|----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [roadmap/README.md](/docs/roadmap/README.md)                                                 | Roadmap index and conventions: the Milestone → Task → Subtask hierarchy, folder/file naming, the absolute-link rule, and the milestone list. Start here.                                                                             |
| [roadmap.md](/docs/roadmap/roadmap.md)                                                       | Full 5-phase development roadmap: Phase 1 Prototype Deconstruction → Phase 2 Data Adapter → Phase 3 Multi-Agent System → Phase 4 Output Synthesis → Phase 5 Hardening. Covers consensus threshold logic and token budget guardrails. |
| [0001-generic-implementation/status.md](/docs/roadmap/0001-generic-implementation/status.md) | Live tracker: which tasks are complete, current lint/type/test gate status, delivered artifacts.                                                                                                                                     |
| [0001-generic-implementation/plan.md](/docs/roadmap/0001-generic-implementation/plan.md)     | 10-task implementation plan with per-task deliverables and a dependency graph; inlines the Data Adapter and Backend specifications.                                                                                                  |
| [0002-forensic-agents/status.md](/docs/roadmap/0002-forensic-agents/status.md) | Live tracker for Milestone 0002 (Forensic Agents): **complete** (2026-07-10). Per-task delivered lists, test counts, and hardening-gate verdicts. |
| [0002-forensic-agents/plan.md](/docs/roadmap/0002-forensic-agents/plan.md)                   | Agentic execution brief per task: agent matrix, verbatim per-agent instructions, inputs, verification gates.                                                                                                                         |
| [0003-litellm-routing/plan.md](/docs/roadmap/0003-litellm-routing/plan.md)                   | LiteLLM routing task brief.                                                                                                                                                                                                          |
| [0004-code-intelligence/plan.md](/docs/roadmap/0004-code-intelligence/plan.md)               | OpenClaude integration: the central Code Intelligence mechanism (supersedes the bespoke Milestone 0004 design).                                                                                                                      |
| [0005-harness-backends/plan.md](/docs/roadmap/0005-harness-backends/plan.md)                 | Code Intelligence harness & multi-backend support: generalises the single-backend subsystem into a neutral `harness/` selection layer and adds Claude Code (`claude` CLI) and OpenHands (Docker-sandboxed) backends. Extends Milestone 0004. |
| [0005-harness-backends/status.md](/docs/roadmap/0005-harness-backends/status.md)             | Live tracker for Milestone 0005 (Harness & multi-backend): **not started**; task-level plan only, records the "no documented second backend" research finding and the single-active-backend selection decision. |

---

## Agentic Fleet (`agent/`)

Operational references for the Claude Code dev agent fleet.

| Document                         | Description                                                                                                                                                                                                                                                             |
|----------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [tutorial.md](agent/tutorial.md) | Practical onboarding: scenarios for every common task, common mistakes, quick-reference card. Aimed at developers new to Claude Code.                                                                                                                                   |
| [agents.md](agent/agents.md)     | Reference for all dev agents (`app-architect`, `background-reviewer`, `docs-updater`, `docs-writer`, `feature-reviewer`, `incident-analyst`, `python-expert`, `security-auditor`, `testing-expert`): model, tools, responsibilities, when to use.                       |
| [skills.md](agent/skills.md)     | Reference for all slash-command skills (`/adr-write`, `/pr-review`, `/test-gap`, `/runbook-write`, `/post-mortem`, `/dep-audit`, `/secret-scan`, `/playbook-validate`, `/link-check`, `/doc-xref`, `incident-triage`): invocation, step-by-step behaviour, when to use. |
| [hooks.md](agent/hooks.md)       | Reference for all automatic hooks (`guard_bash`, `secret_scan`, `post_edit_format`, `dep_audit`, `doc_link_check`, `github_audit`, `session_start`, `run_tests`): what each blocks/logs, override env vars, audit log locations.                                        |

---

## Configuration Reference (`config/`)

User-facing reference for every CLI option and configuration field, derived from
`src/aegis_swr/`. Config dir: `~/.aegis-swr/`.

| Document | Description |
|---|---|
| [cli.md](config/cli.md) | Every `aegis` command (`analyze`, `export`, `server`, `config show/set`) with all options, defaults, allowed values, output modes, and exit codes. |
| [config.md](config/config.md) | The unified `config.json`: analyze keys plus `ingest` / `logging` / `evidence` / `process` sections, nested `core` / `backends` / `sandbox` / `api` runtime config, sources, precedence, and env overrides. |
| [agents.md](config/agents.md) | Agent consensus weight: how each forensic agent declares its own `default_weight` class property, the two-tier weight precedence, and how the consensus score uses it. |
| [openclaude-setup.md](config/openclaude-setup.md) | Operator install/setup guide for the OpenClaude gRPC sidecar: external vs managed mode, allowlist launch flags, the user-supplied model contract, and troubleshooting. |
| [openclaude-config-reference.md](config/openclaude-config-reference.md) | Full `OpenClaudeSettings` field table, allowlist defaults + rationale, the `openclaude_agent` role example, and the OpenClaude event reference. |
| [harness-selection.md](config/harness-selection.md) | How Aegis SWR picks which Code Intelligence backend (OpenClaude, Claude Code, OpenHands) is active: the selector env var, presence signals, the selection truth table, and the two failure modes. Specified by [Milestone 0005](roadmap/0005-harness-backends/plan.md); not yet implemented. |

---

## Developer Guides (`dev/`)

| Document | Description |
|---|---|
| [python_coding_standard.md](dev/python_coding_standard.md) | Index and project-specific overrides (start here). |
| [python_language_rules.md](dev/python_language_rules.md) | §1 Background + §2 Python Language Rules: lint, imports, packages, exceptions, mutable globals, comprehensions, generators, lambdas, type annotations. |
| [python_style_rules.md](dev/python_style_rules.md) | §3 Python Style Rules: line length, indentation, comments, docstrings, naming, main, function length, type annotation style. §4 Parting Words. |

---

## QA & Test Coverage (`test/`)

| Document | Description |
|---|---|
| [code_test_coverage.md](test/code_test_coverage.md) | Coverage requirements checklist, PR checklist, and runnable commands to validate coverage (85% threshold). |
| [coverage.md](test/coverage.md) | Coverage configuration; commands, CI integration, and troubleshooting. |

---

## Manual QA Scenarios (`qa/`)

Detailed, step-by-step walkthroughs of Aegis SWR processing a specific
incident end-to-end - every backend, every pipeline stage, every agent turn.
See [qa/README.md](qa/README.md) for the naming convention and required
sections.

| Document | Description |
|---|---|
| [0001-audacity4-corrupted-vst3-plugin-startup-crash.md](qa/0001-audacity4-corrupted-vst3-plugin-startup-crash.md) | Full walkthrough: a truncated VST3 plugin crashes Audacity 4 on startup; traces the dump/log/screenshot/code intake through the Data Adapter, the four-agent debate to consensus, the final RCA report, and a suggested patch. |

---

## Reviews (`reviews/`)

Outputs from `background-reviewer`: dependency audits, secret scans, performance
findings, and licence checks. See [reviews/README.md](reviews/README.md).

| Document | Description |
|---|---|
| [token-waste-report.md](reviews/token-waste-report.md) | Token efficiency audit: per-category waste estimates (~17 440 tokens/request worst-case). |

---

## Runbooks (`runbooks/`)

Operational runbooks for on-call engineers. See [runbooks/README.md](runbooks/README.md).

> No runbooks yet - use `/runbook-write <incident-type>` to create the first one.

---

## Security (`security/`)

Threat models and security review outputs from `security-auditor`.
See [security/README.md](security/README.md).

> No threat models yet - populated when incident-ingestion and auth code is reviewed.

---

## Post-Mortems (`post-mortems/`)

Blameless post-mortems for resolved incidents. See [post-mortems/README.md](post-mortems/README.md).

> No post-mortems yet - filed after the first P0/P1 incident.

---

## UI Sketches (`ui/`)

Design notes and text mockups.

| Document | Description |
|---|---|
| `ui/ui-investigation-process.txt` | ASCII mockup of the Evidence Stream and Forensic Agents panels (debug output sample). |
| `ui/ui-root-cause-analysis.txt` | Plain-text RCA report example produced by the agents (RCA template / sample output). |
