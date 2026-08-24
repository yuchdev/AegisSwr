# Milestone 0005 — Code Intelligence Harness & Multi-Backend Support

**Package:** `aegis-swr` | **Module roots:** `aegis_swr/harness/` (new),
`aegis_swr/claude_code/` (new), `aegis_swr/openhands/` (new); extends
`aegis_swr/openclaude/` (existing, unchanged except the removal of
`composition.py`).
**Depends on:** Milestone 0004 (OpenClaude Integration; `aegis_swr/code_intel/`
and `aegis_swr/openclaude/` in their **final, post-remediation state** — see
[ADR 0003](/docs/adr/0003-code-intel-composition-root.md)).

This milestone generalises the single-backend Code Intelligence subsystem that
Milestone 0004 stood up (OpenClaude as the *sole* `CodeIntelBackend`) into a
**multi-backend harness** with an explicit single-active-backend selection
contract. It adds two new first-class backends behind the unchanged
`CodeIntelBackend` ABC — the installed **Claude Code** CLI (`claude`) and a
sandboxed **OpenHands** sidecar — and lifts the C4 composition branch out of the
`openclaude/` package into a neutral `harness/` package that is the one and only
place that knows which backends exist.

After this milestone, an operator selects a code-intelligence backend with a
single environment variable (`AEGIS_CODE_INTEL_BACKEND`) — or lets the harness
auto-select when exactly one backend's presence signal is configured — with
**zero Python changes**. The Milestone 0004 closing guarantee is preserved
verbatim: an existing `OPENCLAUDE_GRPC_URL`-only deployment continues to work
untouched.

> **Extends, does not supersede, Milestone 0004.** The `CodeIntelBackend` ABC
> (`code_intel/backend.py`), the `CodeAgent` entry point (`code_intel/agent.py`),
> and `CallBudget` (`code_intel/budget.py`) stay **backend-agnostic and
> untouched**. The OpenClaude implementation is unchanged except that
> `openclaude/composition.py` (its `build_code_agent` factory) is **deleted** and
> its logic is generalised into `harness/composition.py`. See
> [ADR 0004](/docs/adr/0004-harness-composition-generalization.md) for the
> composition-root generalisation decision.

---

## Background

Milestone 0004 wired OpenClaude as the *central and sole* Code Intelligence
mechanism. Its contract C4 was explicit about the single-backend assumption:
"there are no sibling backends to fall back to." The composition branch
(`settings.grpc_url is not None`) lived inside `openclaude/composition.py`
because, with one backend, there was nowhere more neutral for it to live.

Two forces motivate this milestone:

1. **A second (and third) backend now exist.** The subsystem was designed to be
   backend-agnostic at the `CodeIntelBackend` seam but had exactly one
   implementation, so the "agnostic" claim was never exercised. Adding real
   siblings both validates the seam and delivers operator choice.

2. **The composition branch is in the wrong package.** With more than one
   backend, `openclaude/composition.py` would have to import `claude_code` and
   `openhands` — i.e. one backend package would depend on its siblings. That
   inverts the Factory-Strategy convention and breaks the C3 isolation posture.
   The branch must move to a neutral selection layer.

### Research finding — what "second backend" actually meant

The Milestone 0004 record repeatedly frames OpenClaude as chosen "over stock
Claude Code MCP" ([0004 status.md, Notes & decisions](/docs/roadmap/0004-code-intelligence/status.md#notes--decisions)),
but **no second open-source alternative to OpenClaude is documented anywhere in
the existing roadmap or its git history.** This was checked directly:

- `docs/roadmap/` (all milestones, plans and statuses) — no alternative named.
- The deleted pre-supersession `0004-code-intelligence-layer/plan.md` (the
  bespoke tool-per-capability design) — named no agentic-harness alternative.
- A full `git log -p` sweep of `docs/` for `OpenHands` / `Aider` / `SWE-agent` /
  `Goose` / `Cline` and similar — **zero hits**.

The only previously-named alternative to OpenClaude is **"stock Claude Code
MCP"** ([0004 status.md line 127](/docs/roadmap/0004-code-intelligence/status.md)),
which is exactly what this milestone now promotes to a **first-class backend of
its own** (the `claude_code` family — the installed `claude` CLI). The user was
then asked to pick a *researched* third backend and chose **OpenHands**.

### Why OpenHands as the researched third backend

OpenHands ([All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands))
is Apache-2.0 licensed, uses **LiteLLM internally** (an echo of Milestone
0003's own routing layer, so the operator's model configuration model is
familiar), and — decisively for Aegis SWR — **runs sandboxed in Docker by
default.** Aegis SWR's defining property is that every incident payload is
attacker-influenced and must be treated as hostile (`../CLAUDE.md` §1). A backend
that executes its navigation tools inside a Docker sandbox fits that posture
strictly better than a host-permission subprocess (which is what both OpenClaude
and Claude Code are). That sandbox is the explicit reason OpenHands was chosen
over the other candidates.

#### Alternatives considered

| Candidate                      | Licence                 | Process model                                            | Sandbox                 | Non-interactive maturity                                             | Verdict                                                                                                                              |
|--------------------------------|-------------------------|----------------------------------------------------------|-------------------------|----------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| **OpenHands**                  | Apache-2.0              | REST/WS sidecar (Action/Observation event stream)        | **Docker by default**   | Good (headless server mode)                                          | **Chosen** — sandbox matches the hostile-payload posture; LiteLLM-internal echoes 0003                                               |
| **Claude Code (`claude` CLI)** | Proprietary (Anthropic) | One-shot subprocess (`-p … --output-format stream-json`) | None (host permissions) | Good (`-p` non-interactive mode is first-class)                      | **Adopted as its own backend** — this is the "stock Claude Code" 0004 named; real token accounting is a genuine gain, but no sandbox |
| Aider                          | Apache-2.0              | In-process / subprocess                                  | None                    | Weaker read-only tool allowlisting; less mature non-interactive mode | Rejected — no sandbox, weaker read-only guarantees                                                                                   |
| Goose                          | Apache-2.0              | Subprocess                                               | Limited                 | Interactive-first design                                             | Rejected — interactive-first; a poor fit for Aegis SWR's non-interactive pipeline                                                    |
| SWE-agent                      | MIT                     | Subprocess/harness                                       | Container-capable       | Narrower benchmark focus, smaller ecosystem                          | Rejected — narrower scope and smaller ecosystem than OpenHands                                                                       |

### What this milestone deliberately does *not* do

- It does **not** add a fallback chain. The user confirmed
  **single-active-backend, no fallback** (C2). This generalises 0004's C4
  ("no sibling backends to fall back to") to "exactly one active backend at a
  time; the others are simply not registered." A model-driven fallback across
  agentic harnesses would multiply cost and non-determinism with no reliability
  win the operator asked for.
- It does **not** touch the `CodeIntelBackend` ABC, `CodeAgent`, `CallBudget`,
  or `CodeResult` shape. `CodeResult.token_estimate` keeps its field name and
  type so `CodeAgent` stays fully backend-agnostic even though Claude Code can
  now supply a *real* token count where OpenClaude could only estimate (C9).
- It does **not** re-configure any backend's model. As with OpenClaude, each
  backend's model selection is the operator's concern via that backend's own
  environment (Claude Code: its own auth/model env; OpenHands: its LiteLLM env).
- It does **not** silently prefer one Claude Code authentication mode over
  another. `auth_mode` defaults to `auto` (whatever the installed `claude`
  binary's own credential precedence resolves), and the explicit `subscription`
  mode ships **opt-in only**, pending confirmation with Anthropic of which
  subscription seat tier is licensed for non-interactive production automation
  (C7) — see the licensing caveat in that contract.

---

## Architecture

```
AEGIS_CODE_INTEL_BACKEND  (selector: openclaude | claude_code | openhands | unset)
    │  + per-family presence signals:
    │       OPENCLAUDE_GRPC_URL   (unchanged from 0004)
    │       CLAUDE_CODE_ENABLED   (explicit opt-in; PATH presence is NOT a signal)
    │       OPENHANDS_SERVER_URL  (mirrors OpenClaude's URL-presence pattern)
    ▼
aegis_swr/harness/                 ← NEW neutral selection + composition layer
    config.py        ← HarnessSettings: selector + nested openclaude / claude_code / openhands settings;
    │                   resolves the single active backend (C1, C2); raises HarnessConfigError on ambiguity
    composition.py   ← create_code_intel_backend(...): the ONE place branching on which backend is active
    │                   (the generalised C4). The only module permitted to import openclaude AND claude_code
    │                   AND openhands. Assembles the chosen stack and injects it into CodeAgent.
    exceptions.py    ← HarnessConfigError, HarnessUnavailableError
    │
    │  (injects exactly one CodeIntelBackend, or none)
    ▼
aegis_swr/code_intel/              ← UNCHANGED (Milestone 0004): backend.py (CodeIntelBackend ABC),
    │                                agent.py (CodeAgent), budget.py (CallBudget). Imports NO concrete
    │                                backend — C3 holds exactly as in 0004.
    ├───────────────┬───────────────────────────────┐
    ▼               ▼                                 ▼
aegis_swr/openclaude/    aegis_swr/claude_code/    aegis_swr/openhands/
  (UNCHANGED impl;         (NEW: installed `claude`  (NEW: OpenHands sandboxed
   composition.py           CLI, one-shot subprocess   sidecar over REST/WS)
   REMOVED)                 per delegate() call;
                            two auth modes — C7)
  gRPC sidecar            no sidecar — one-shot      Docker-sandboxed sidecar
  (Topology A, 0004)      subprocess (Topology D)    (Topology A-equivalent)
```

**Hard isolation boundary (generalises 0004 C3):** `aegis_swr/core/`,
`aegis_swr/views/`, and `aegis_swr/code_intel/` import **none** of
`aegis_swr.openclaude`, `aegis_swr.claude_code`, `aegis_swr.openhands`, `grpc`,
or any backend client library. `aegis_swr/harness/` is the **only** package that
imports more than one backend family; each backend package imports only its own
dependencies and never a sibling. Enforced by an extended `grep` CI check (C3,
task 11.0/13.0).

**Backend process boundaries (per family):**
`openclaude/process.py` owns the OpenClaude subprocess (unchanged);
`claude_code/process.py` owns the one-shot `claude` subprocess (both auth
modes); `openhands/process.py` owns the OpenHands sidecar lifecycle.

---

## Tasks

| Task | Name                                          | Category       | Output                                                                                                                                                                                                          |
|------|-----------------------------------------------|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 01.0 | Harness Settings & Selection Contract         | configuration  | `harness/config.py`, `harness/exceptions.py` — `HarnessSettings`, selector + presence-signal resolution (C1, C2)                                                                                                |
| 02.0 | Claude Code Settings & Config                 | configuration  | `claude_code/config.py` — `ClaudeCodeSettings` (binary, allowlist, permission mode, scratch cwd, `CLAUDE_CODE_ENABLED`)                                                                                         |
| 03.0 | Claude Code Subprocess Tool                   | infrastructure | `claude_code/tool.py`, `claude_code/process.py` — one-shot `claude -p … --output-format stream-json`; argv-safety; NDJSON parse; real token accounting (C6, C9)                                                 |
| 04.0 | Claude Code Subscription/Login Authentication | configuration  | `claude_code/config.py` `auth_mode` field + validation; `claude_code/exceptions.py` auth errors; auth-probe health-check in `claude_code/tool.py` / `process.py` (C7)                                           |
| 05.0 | Claude Code Events & Exceptions               | infrastructure | `claude_code/events.py`, `claude_code/exceptions.py` — frozen `DomainEvent` taxonomy + typed errors (C10)                                                                                                       |
| 06.0 | OpenHands Settings & Config                   | configuration  | `openhands/config.py` — `OpenHandsSettings` (server URL, runtime/sandbox mode, allowlist, timeouts) (C5, C8)                                                                                                    |
| 07.0 | OpenHands Client & Process Lifecycle          | infrastructure | `openhands/client.py`, `openhands/process.py` — sole importer of the OpenHands client; sidecar lifecycle (C8)                                                                                                   |
| 08.0 | OpenHands Tool Implementor                    | infrastructure | `openhands/tool.py` — the `CodeIntelBackend`; Action/Observation stream → `CodeResult`; budget, dry-run (C8, C9)                                                                                                |
| 09.0 | OpenHands Events & Exceptions                 | infrastructure | `openhands/events.py`, `openhands/exceptions.py` — frozen `DomainEvent` taxonomy + typed errors (C10)                                                                                                           |
| 10.0 | Harness Composition Root & CLI                | integration    | `harness/composition.py`; delete `openclaude/composition.py`; backend-agnostic `aegis code-intel check`; `agents.yaml` `claude_code_agent` / `openhands_agent` roles; `Settings.harness` nesting (C4, C11, C12) |
| 11.0 | Test Suite — Unit                             | testing        | Per-backend mock suites; per-package isolation grep tests; selection-ambiguity tests; auth-mode tests (C2, C7)                                                                                                  |
| 12.0 | Test Suite — Integration                      | testing        | Live per-backend suites, skipped by default, gated on presence signal + binary/Docker availability                                                                                                              |
| 13.0 | Documentation & CI                            | documentation  | Per-backend setup + config-reference docs; CI isolation/coverage gate extensions; milestone closeout                                                                                                            |

**Sequencing.** 01.0 is the foundation — it fixes the settings shape and the
selection/ambiguity contract every other task depends on. Once 01.0 lands, the
Claude Code track (02.0 → 03.0 → 04.0 → 05.0) and the OpenHands track
(06.0 → 07.0 → 08.0, 09.0) proceed **in parallel** with each other. Within the
Claude Code track, 04.0 (subscription/login authentication) is deliberately
sequenced *after* 03.0 (the subprocess tool) because it extends the same
invocation path with a second, mutually-exclusive-by-design auth surface — it
is not safe to design in isolation from how the subprocess is actually spawned.
10.0 depends on all of 01.0–09.0 (it wires every backend into the generalised
composition root and deletes `openclaude/composition.py`). 11.0 and 12.0 are
written **incrementally alongside** their respective backend tasks (same
convention as Milestone 0004). 13.0 closes the milestone.

---

## Backend topology comparison

Milestone 0004 analysed three *communication* topologies for a single backend
(gRPC tool / MCP server / inverted orchestrator). This milestone instead
compares the three *backend families* it now supports, because each has a
materially different process model, sandbox posture, and token-accounting story.
All three sit behind the **same** `CodeIntelBackend.delegate(task, ctx)` seam.

### Backend A — OpenClaude (unchanged; Topology A from 0004)

```
CodeAgent → OpenClaudeTool (CodeIntelBackend)
              └── gRPC bidirectional stream → OpenClaude headless sidecar (Node.js)
                    └── provider shim → operator's OpenAI-compatible endpoint
```

Long-lived gRPC sidecar, per-frame `EventBus` emission, boundary token estimate
(`len(content)//4`, C9). **Host permissions**, guarded by tool + Bash
allowlists. Presence signal: `OPENCLAUDE_GRPC_URL`. Nothing about it changes in
this milestone except where its factory lives.

### Backend B — Claude Code (`claude` CLI; new; "Topology D" — one-shot)

```
CodeAgent → ClaudeCodeTool (CodeIntelBackend)
              └── one-shot subprocess per delegate():
                    claude -p <task-via-stdin> --output-format stream-json
                    (credential resolved per C7: subscription login OR API key)
                    └── NDJSON stream on stdout → CodeResult
```

**No persistent sidecar** — a fresh `claude` process is spawned per
`delegate()` call and reaped when it exits. This is *simpler* than OpenClaude's
C6-equivalent (0004) lifecycle: there is no server to keep alive, health-check,
or tear down. The trade-offs versus OpenClaude:

- **Real token accounting (gain over 0004 C5).** `stream-json`'s terminal
  `result` message carries actual `usage.input_tokens` / `usage.output_tokens`.
  Claude Code uses these instead of a length-derived estimate — a genuine
  capability improvement, while `CodeResult.token_estimate` keeps its field
  shape (C9).
- **Argv-safety (a new concern).** Task text must never appear in argv — it is
  visible via `ps`/process listing on a shared host. It is passed via stdin (or
  a disposable temp file), never as a bare CLI argument (C6).
- **No sandbox.** Runs with host OS permissions, the same residual-risk posture
  as OpenClaude. `--allowedTools` / `permission_mode` plus a fixed disposable
  scratch cwd are the only guards; `--dangerously-skip-permissions` is rejected
  at settings-validation time (C6).
- **Two independent authentication modes (new; C7).** Unlike OpenClaude (which
  treats the model provider as entirely the operator's concern via env vars),
  Claude Code has its *own* dual credential surface — an API key/Console token,
  or a Claude.ai subscription login (Pro/Max/Team/Enterprise) established via
  `claude login` or a CI-friendly `claude setup-token` long-lived token — and
  the two interact through a documented precedence chain the tool must not
  fight silently. See C7.

Presence signal: `CLAUDE_CODE_ENABLED=true` (explicit opt-in). Being on `PATH`
is deliberately **not** a signal — that is a weaker, more accidental trigger
than a configured URL, and silent activation of a host-permission backend is
exactly the kind of surprise the hostile-payload posture forbids.

### Backend C — OpenHands (new; Topology A-equivalent, sandboxed)

```
CodeAgent → OpenHandsTool (CodeIntelBackend)
              └── REST/WS client → OpenHands sidecar
                    └── Docker-sandboxed runtime: Action → Observation event stream
                          └── LiteLLM-internal → operator's model
```

A long-lived sidecar over REST/WS, mirroring OpenClaude's proven "Topology A"
(a sidecar streaming events onto the `EventBus`) rather than a one-shot CLI —
chosen for consistency with the streaming pattern already validated for
OpenClaude. Its distinguishing value is **Docker sandboxing**: unlike the other
two backends (both host-permission), OpenHands executes its navigation tools
inside a container. This is the explicit reason it was chosen (see Background).

Presence signal: `OPENHANDS_SERVER_URL` (mirrors OpenClaude's own
URL-presence pattern). **Operator prerequisite:** Docker must be available on
the host. Because Aegis SWR is Windows-only (`../CLAUDE.md`), **Docker-on-Windows
is a new operator prerequisite** worth a line in the root `README.md`
system-requirements area (task 13.0).

### Comparison summary

| Property             | OpenClaude (A)        | Claude Code (B)          | OpenHands (C)             |
|----------------------|-----------------------|--------------------------|---------------------------|
| Process model        | gRPC sidecar (long-lived) | one-shot subprocess    | REST/WS sidecar (long-lived) |
| Lifecycle complexity | C6 start/health/stop  | spawn-and-reap per call  | C6-style start/health/stop |
| Sandbox              | none (host perms)     | none (host perms)        | **Docker (default)**      |
| Token accounting     | boundary estimate     | **real `usage` counts**  | boundary estimate         |
| Presence signal      | `OPENCLAUDE_GRPC_URL` | `CLAUDE_CODE_ENABLED`    | `OPENHANDS_SERVER_URL`    |
| Auth surface          | operator's model provider (OpenClaude's own env) | **API key *or* subscription login** (C7) | operator's LiteLLM config |
| Read-only guard      | tool + Bash allowlist | `--allowedTools` + scratch cwd | allowlist + container FS |
| New attack surface   | Bash                  | argv exposure; credential-file exposure | container escape (Docker) |

---

## Shared contracts (authoritative)

These contracts are defined once here; per-task READMEs reference them.

### C1 — Harness settings shape

All harness configuration lives in `HarnessSettings`, a Pydantic settings class
that composes the selector plus one nested settings sub-object per backend
family:

| Field         | Env var                    | Default | Notes                                                          |
|---------------|----------------------------|---------|------------------------------------------------------------------|
| `backend`     | `AEGIS_CODE_INTEL_BACKEND` | `None`  | `openclaude` \| `claude_code` \| `openhands`; `None` = auto-select from presence signals (C2) |
| `openclaude`  | (nested)                   | `OpenClaudeSettings()` | Unchanged from 0004; presence signal `OPENCLAUDE_GRPC_URL` |
| `claude_code` | (nested)                   | `ClaudeCodeSettings()` | Presence signal `CLAUDE_CODE_ENABLED` (C6); two auth modes (C7) |
| `openhands`   | (nested)                   | `OpenHandsSettings()`  | Presence signal `OPENHANDS_SERVER_URL` (C8)                |

`backend` is a `str` enum-validated field. `HarnessSettings` performs the C2
selection resolution at **settings-construction time** and exposes the resolved
choice (e.g. an `active_backend` computed property returning the selected family
name or `None`). It never reads `os.environ` inside composition or tool code;
each nested settings object sources its own family's variables exactly as
`OpenClaudeSettings` already does.

### C2 — Backend selection & ambiguity resolution

The single-active-backend rule (user-confirmed, no fallback), generalising
0004's C4. A "presence signal" is a family's configured-and-non-empty enabling
variable: `OPENCLAUDE_GRPC_URL` set, `CLAUDE_CODE_ENABLED=true`, or
`OPENHANDS_SERVER_URL` set.

| `AEGIS_CODE_INTEL_BACKEND` | Presence signals set | Outcome |
|----------------------------|----------------------|---------|
| unset | zero | No backend registered; capability unavailable (unchanged from 0004 C4). |
| unset | exactly one | That backend is auto-selected. **Preserves 0004's guarantee** — an `OPENCLAUDE_GRPC_URL`-only deployment needs zero further changes. |
| unset | more than one | **`HarnessConfigError` at settings-construction time.** New failure mode; fail loud, never silently pick one. (Could not occur in 0004 with one backend.) |
| set to family *X* | *X*'s signal present | *X* is selected. |
| set to family *X* | *X*'s signal absent | `HarnessUnavailableError` raised at composition / health-check time (not at settings construction — the operator explicitly asked for *X*, so the error is a runtime capability failure, not a config-shape error). |

`HarnessConfigError` and `HarnessUnavailableError` live in
`harness/exceptions.py`. `HarnessConfigError` (construction-time, config-shape
ambiguity) is distinct from `HarnessUnavailableError` (composition-time, an
explicitly-selected backend is not reachable/enabled). Neither subclasses the
other; both carry only the offending field/backend names and the set of
signals seen — **never** any secret or payload text (C13).

### C3 — Module isolation boundary (generalises 0004 C3)

- `aegis_swr/core/`, `aegis_swr/views/`, and `aegis_swr/code_intel/` import
  **none** of `aegis_swr.openclaude`, `aegis_swr.claude_code`,
  `aegis_swr.openhands`, `grpc`, the OpenHands client library, or any generated
  stubs. The backend is injected, never imported by the scaffolding.
- **`aegis_swr/harness/composition.py` is the only module permitted to import
  more than one backend family** (all three). No backend package imports a
  sibling backend package.
- Within each backend package the 0004 sub-boundaries hold: `grpc`/`_pb2` only
  in `openclaude/grpc/client.py`; the OpenHands client library only in
  `openhands/client.py`; each backend's subprocess/sidecar owned solely by that
  package's `process.py`.
- Enforced by an extended `grep` CI check (a per-package isolation job mirroring
  0004's `openclaude-isolation`) and replicated as pytest isolation tests per
  new package (task 11.0). The check is import-statement-aware so docstring
  mentions do not trip it.

### C4 — Composition root contract (generalised C4 from 0004)

`aegis_swr/harness/composition.py` exposes a single async factory,
`create_code_intel_backend(...)` (or `build_code_agent(...)` retaining the 0004
name — settle in task 10.0), which is the **one and only** place that branches
on which backend is active. It:

1. Reads the resolved `HarnessSettings.active_backend` (C2).
2. `None` → returns a backend-less `CodeAgent` (capability unavailable; no
   fallback — identical observable behaviour to 0004's unset path).
3. `openclaude` → assembles the unchanged OpenClaude stack
   (`OpenClaudeGrpcClient` → `OpenClaudeProcess` → `OpenClaudeTool`) exactly as
   the deleted `openclaude/composition.py` did — this logic **moves here
   verbatim**, it is not rewritten.
4. `claude_code` → assembles `ClaudeCodeTool`, resolving its auth mode per C7
   (no sidecar; nothing to enter on the `AsyncExitStack`).
5. `openhands` → assembles the OpenHands stack (`OpenHandsClient` →
   `OpenHandsProcess` → `OpenHandsTool`), registering the sidecar process on the
   caller's `AsyncExitStack` for RAII teardown (mirrors 0004 C6).

The `dry_run` axis is orthogonal to backend selection (as in 0004): the graph is
fully constructed and the backend registered, but no sidecar is entered and no
outbound call is made. `openclaude/composition.py` is **deleted**; its tests are
re-targeted to `harness/composition.py` (task 11.0). See
[ADR 0004](/docs/adr/0004-harness-composition-generalization.md).

### C5 — Backend settings-shape convention

Every new backend settings class **mirrors `OpenClaudeSettings`' proven shape**
(Milestone 0004 C1): a Pydantic `BaseSettings` subclass with a per-family
`env_prefix`, CSV env parsing for `list[str]` fields via an `EnvSettingsSource`
subclass + `mode="before"` coercion validator, `field_validator`s that raise the
backend's own typed config error (unwrapped from Pydantic's `ValidationError` in
`__init__`, as `OpenClaudeSettings` does), and **presence-signal-as-`None`/
falsy-default** so an absent variable means "backend not configured" rather than
a construction crash. Sub-settings are composed into `HarnessSettings` via
`default_factory`, and `HarnessSettings` is composed into the top-level
`Settings` via `default_factory` (C12).

### C6 — Claude Code backend contract

`ClaudeCodeTool` is a `CodeIntelBackend` that spawns a **one-shot** `claude`
subprocess per `delegate()` call (`claude -p … --output-format stream-json`) and
reaps it on completion — no persistent sidecar, no health-check lifecycle.

1. **Argv-safety (new; gRPC never had this concern).** The task text must
   **never** appear in argv (visible via `ps`/process listing on a shared host).
   It is passed via **stdin** or a disposable temp file, never a bare CLI
   argument. This extends the "never log secrets" posture to "never argv
   secrets." Enforced by a helper in `claude_code/process.py` and asserted in
   unit tests (no task substring in the constructed argv).
2. **Real token accounting.** The terminal `result` NDJSON message carries
   actual `usage.input_tokens` / `usage.output_tokens`; the tool uses their sum
   as `CodeResult.token_estimate` instead of a length estimate. The field name
   and type are unchanged (C9) so `CodeAgent` stays backend-agnostic.
3. **No sandbox.** Runs with host OS permissions. `settings.allowed_tools`
   (→ `--allowedTools`), `settings.permission_mode`, and a **mandatory
   disposable scratch cwd** are the only guards. `--dangerously-skip-permissions`
   (and any settings value that would produce it) is **rejected at
   settings-validation time**, analogous to how `OpenClaudeSettings` warns/rejects
   on write-capable tools. Write-capable tools default off, as in OpenClaude.
4. **Config settings** (`ClaudeCodeSettings`, C5, C7): `binary_path`
   (`CLAUDE_CODE_BINARY`, default `claude`), `enabled` (`CLAUDE_CODE_ENABLED`,
   default `False` — the presence signal), `allowed_tools`
   (`CLAUDE_CODE_ALLOWED_TOOLS`, default `Read,Grep,Glob` — read-only),
   `permission_mode` (`CLAUDE_CODE_PERMISSION_MODE`, default a non-bypassing
   mode; rejects any bypass-permissions value), `max_turns`
   (`CLAUDE_CODE_MAX_TURNS`), `request_timeout_s` (`CLAUDE_CODE_REQUEST_TIMEOUT`),
   a mandatory disposable `scratch_cwd` (`CLAUDE_CODE_SCRATCH_CWD`), and
   `auth_mode` (`CLAUDE_CODE_AUTH_MODE` — see C7).
5. **Dry-run** short-circuits before any spawn to a `[dry-run]` `CodeResult` with
   zero tokens (mirrors 0004 C5 / C13).
6. **Authentication mode** selection and validation is governed entirely by C7;
   this contract only fixes where the setting lives and that it must be resolved
   before the subprocess argv/env is constructed.

### C7 — Claude Code authentication modes (subscription login vs API key)

Claude Code supports **two independent, non-interactive-capable** credential
surfaces for headless (`-p`) use, and this backend must let the operator choose
between them explicitly rather than depending on whatever happens to be in the
ambient environment:

- **API key / Console token** — `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`,
  the mode Task 03.0 was built against and the existing OpenClaude-style
  operator contract.
- **Subscription login (Claude Pro / Max / Team / Enterprise)** — established
  once via interactive `claude login`, which persists an OAuth session to the OS
  keychain (macOS) or `~/.claude/.credentials.json` / `%USERPROFILE%\.claude\.credentials.json`
  (Linux / **Windows** — the platform Aegis SWR targets), or via
  `claude setup-token`, which mints a **long-lived (~1 year) `CLAUDE_CODE_OAUTH_TOKEN`**
  printed to stdout specifically for non-interactive/CI use — no
  `ANTHROPIC_API_KEY` required. This is the "use the current Claude Code login"
  path the operator asked for.

**Credential precedence Claude Code itself applies** (non-`--bare` mode — the
mode this backend uses; `--bare` mode never reads OAuth/login credentials at
all and is therefore unusable for a login-based deployment):

1. Cloud provider credentials (Bedrock / Vertex env), if configured
2. `ANTHROPIC_AUTH_TOKEN`
3. `ANTHROPIC_API_KEY` — wins if present, **even over a valid subscription login**
4. `apiKeyHelper`
5. `CLAUDE_CODE_OAUTH_TOKEN`
6. Anthropic profile / federation credentials
7. stored `claude login` OAuth session (lowest priority)

Because rank 3 silently outranks rank 5–7, an operator who *intends* to run on
their subscription login gets silently switched to whatever stray
`ANTHROPIC_API_KEY` happens to be set in the process environment (e.g. inherited
from a parent shell or CI secret) unless Aegis SWR checks for that explicitly.

**Design requirement.** `ClaudeCodeSettings` gains an explicit `auth_mode` field
(`CLAUDE_CODE_AUTH_MODE`; one of `auto` | `api_key` | `subscription`; default
`auto`):

1. `auth_mode="subscription"` — the settings validator **rejects construction**
   (raises `ClaudeCodeConfigError`) if `ANTHROPIC_API_KEY` or
   `ANTHROPIC_AUTH_TOKEN` is present in the environment the subprocess will
   inherit, since either would silently outrank the subscription credential
   (ranks 2–3 above) and defeat the operator's explicit choice. `--bare` is
   **never** passed in this mode. If `CLAUDE_CODE_OAUTH_TOKEN` is set, the tool
   uses it (the recommended, CI-friendly path — no interactive browser step per
   machine); otherwise it relies on a previously-established `claude login`
   session already present in the local credential store, and the **startup
   health-check** (below) must verify that session resolves to a working
   credential *before* the first `delegate()` call, rather than discovering the
   failure mid-investigation.
2. `auth_mode="api_key"` — behaves exactly as Task 03.0 built it: the host's
   `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` is used; `--bare` **may** be added
   for reproducibility, since bare mode exists for exactly this case.
3. `auth_mode="auto"` (default) — Aegis SWR adds **no** extra validation beyond
   what the `claude` binary already does; whichever credential is present wins
   per the precedence chain above, unexamined. This preserves the simplest
   possible default for an operator who already has Claude Code working however
   they like, and is the mode used by every acceptance criterion in Task 03.0
   that predates this task.

**Startup auth-probe.** Before the first `delegate()` call — and exposed via
`aegis code-intel check` — the tool performs a lightweight probe verifying the
resolved credential is actually usable, surfacing an auth failure as
`ClaudeCodeUnavailableError` (runtime capability failure), kept **distinct**
from `ClaudeCodeConfigError` (settings-shape/ambiguity failure, e.g. the
rejected-`ANTHROPIC_API_KEY`-under-`subscription`-mode case above).

**Corporate / Enterprise SSO note.** Claude for Team/Enterprise login uses the
**identical** OAuth mechanism as a personal Pro/Max login — there is no
headless-auth code-path difference. Enterprise deployments can enforce
`forceLoginMethod` / `forceLoginOrgUUID` managed-settings to pin logins to the
corporate org; Aegis SWR does not configure or override these — they are the
operator's own Claude Code managed-settings concern, exactly as OpenClaude's
user-supplied-model contract treats OpenClaude's provider env vars as the
operator's concern.

**Licensing caveat — open item, not resolved by this milestone.** No explicit
Anthropic ToS language was found distinguishing personal (Pro/Max) from
organizational (Team/Enterprise) seats for **non-interactive production
automation at scale**. This must be confirmed with Anthropic (sales/legal)
before `auth_mode="subscription"` is used in a production deployment. Pending
that confirmation, `subscription` mode ships **opt-in only** (default remains
`auto`, which does not force the question), and task 13.0's setup guide must
state this caveat explicitly rather than silently recommending subscription
mode as the default automation path.

**Secrecy.** The OAuth token and the credential file's contents are never
logged, never included in exception messages, and never appear in argv (C6) —
same `SensitiveFilter` discipline as any other secret (C13).

### C8 — OpenHands backend contract

`OpenHandsTool` is a `CodeIntelBackend` backed by a **long-lived sidecar over
REST/WS** (Topology A-equivalent), consuming OpenHands' Action/Observation event
stream and translating it into a single `CodeResult`.

1. **Sidecar lifecycle** mirrors 0004's C6: `OpenHandsProcess` is an async
   context manager with external mode (health-check an already-running server)
   and, where applicable, a managed mode; it emits `OpenHands*Connected` /
   `Disconnected` exactly once each and is registered on the app `AsyncExitStack`
   for RAII teardown.
2. **Docker sandbox** is the distinguishing value: the OpenHands runtime executes
   tools inside a container. This is a design *requirement* of this backend, not
   an option — `OpenHandsSettings` selects the sandboxed runtime mode by default,
   and a non-sandboxed runtime requires an explicit override plus an ADR (same
   discipline as the OpenClaude allowlist).
3. **Client isolation:** `openhands/client.py` is the **sole** importer of the
   OpenHands HTTP/WS client library (C3).
4. **Action/Observation → CodeResult:** the client accumulates the assistant's
   text observations up to the terminal event; tool actions are emitted as
   `EventBus` events (C10); the boundary token estimate follows the OpenClaude
   convention (`max(1, len(content) // 4)`) unless the server reports real
   usage, in which case that is used (still surfaced through
   `CodeResult.token_estimate`, C9).
5. **Config settings** (`OpenHandsSettings`, C5): `server_url`
   (`OPENHANDS_SERVER_URL`, default `None` — the presence signal),
   `runtime_mode` / sandbox selector (`OPENHANDS_RUNTIME`, default the sandboxed
   Docker runtime), `allowed_tools`/allowlist (`OPENHANDS_ALLOWED_TOOLS`),
   `connect_timeout_s`, `request_timeout_s`, and `auto_start`.
6. **Dry-run** short-circuits before any network call (mirrors 0004 C5 / C13).

### C9 — Token accounting: real vs boundary estimate

`CodeResult.token_estimate` keeps its exact field name and `int` type across all
backends so `CodeAgent` and `CallBudget` remain fully backend-agnostic — this is
a **hard invariant**. What differs is only how each backend fills it:

| Backend      | Source of `token_estimate`                                              |
|--------------|--------------------------------------------------------------------------|
| OpenClaude   | Boundary estimate `max(1, len(content) // 4)` (0004 C5; opacity-forced) |
| Claude Code  | **Real** `usage.input_tokens + usage.output_tokens` from the `result` NDJSON message (same in either C7 auth mode) |
| OpenHands    | Server-reported usage when available, else boundary estimate `max(1, len(content) // 4)` |

Claude Code's real accounting is framed as a **genuine improvement** over 0004's
C5 (which was forced into an estimate by OpenClaude's opacity), delivered without
any change to the shared contract. `CallBudget` pre-check and post-completion
charge semantics are unchanged; only the charged figure's provenance improves.

### C10 — Per-backend event taxonomy

Each new backend defines its own frozen event dataclasses **subclassing the live
`aegis_swr.core.events.DomainEvent`** (the shape 0004 actually shipped — see
0004 [status.md](/docs/roadmap/0004-code-intelligence/status.md) Task 05.0, not the stale plain-dataclass/`event_type`-string spec
text), carrying `run_id`, a UTC `timestamp`, and a `ClassVar[str] event_type`
sentinel. The taxonomy mirrors OpenClaude's C8 in shape:

| Concept                | Claude Code (`claude_code.*`)      | OpenHands (`openhands.*`)              |
|------------------------|------------------------------------|---------------------------------------|
| Process/connection up  | `claude_code.spawned`              | `openhands.connected`                 |
| Process/connection down| `claude_code.exited`              | `openhands.disconnected`              |
| Tool invocation        | `claude_code.tool_call`           | `openhands.action`                    |
| Tool result            | `claude_code.tool_result`         | `openhands.observation`              |
| Permission denied      | `claude_code.permission_denied`   | `openhands.permission_denied`        |
| Auth failure            | `claude_code.auth_failed` (C7)     | — (n/a)                               |
| Stream completed       | `claude_code.completed` (carries real `token_estimate`) | `openhands.completed` (carries `token_estimate`) |
| Stream error           | `claude_code.error`               | `openhands.error`                    |

Exactly one event per backend carries the token figure; it is never duplicated
across events (as in 0004 C8). `claude_code.auth_failed` carries only the
failure reason (e.g. `"ambiguous_credential"`, `"no_stored_login"`,
`"token_rejected"`) — **never** any credential or token value.

### C11 — agents.yaml roles

`agents.yaml` gains a `claude_code_agent` and an `openhands_agent` role stanza
**alongside** the existing `openclaude_agent`, each replicating that stanza's
pattern (`provider: <family>`, `model: ~` — Aegis SWR resolves no LiteLLM model,
`timeout_s` matching the backend's `request_timeout_s` default, and an
`enabled_when` tied to **that backend's own presence signal**):
`enabled_when: CLAUDE_CODE_ENABLED` and `enabled_when: OPENHANDS_SERVER_URL`
respectively. As in 0004, these roles are inert config parsed only by
`RouterConfig` (they are not routed through LiteLLM); `enabled_when` simply
suppresses validation errors when the signal is absent. The `claude_code_agent`
stanza's comment names both C7 auth modes and points at the setup guide;
`auth_mode` itself is not part of `agents.yaml` (it lives in `ClaudeCodeSettings`,
sourced from its own env var, exactly like OpenClaude's model env vars).

### C12 — `Settings.harness` nesting (deliberate breaking rename)

`Settings.openclaude` (`src/aegis_swr/config/settings.py:695-699`) is
**renamed and re-nested** to `Settings.harness.openclaude`. The top-level
`Settings` gains a single `harness: HarnessSettings = Field(default_factory=…)`
field; the standalone `openclaude` field is removed. Any code reading
`settings.openclaude` must switch to `settings.harness.openclaude`. This is a
**deliberate breaking rename**, accepted under the same tolerance the codebase
already applied to ADR 0003's `CodeBackend` → `CodeIntelBackend` rename — the
field is internal, has no stable external API surface, and the CLI is the only
composition-root consumer. Migration path is named explicitly: task 10.0 updates
`settings.py`, the CLI subcommand, and any tests that read `settings.openclaude`.

### C13 — Cross-cutting conventions (inherited verbatim from 0001–0004)

- `Optional[T]` from `typing`, never `T | None` (including in subscripts and
  `Annotated[...]`).
- `from __future__ import annotations` in every new file.
- `ruff` (E,F,I,UP,B,SIM; line length 100) stays clean; `ruff format` is the
  formatter.
- Every new public class/function has an RST-style docstring
  (`:param:`/`:ivar:`/`:return:`).
- No backend package import in `aegis_swr/core/`, `aegis_swr/views/`, or
  `aegis_swr/code_intel/` (C3).
- `--dry-run` short-circuits each backend to a `[dry-run]` result with zero
  tokens, without opening any connection or spawning any process (per-backend,
  mirroring 0004 C5).
- `asyncio.sleep` for backoff — **never** `time.sleep`.
- Loguru with `SensitiveFilter` on **every** sink; no raw incident payload text
  (dump/log/stack) and no unredacted response/argv/task/credential text ever
  reaches a log sink or exception message.
- No bare `except:`; every external call (subprocess, sidecar, HTTP/WS) has a
  timeout and a defined failure path; RAII via context managers for every
  subprocess/socket/file resource.

---

## Dependency graph

```
Task 01.0 (Harness Settings & Selection Contract)   ← settings shape + C1/C2 for all
   │
   ├── Claude Code track ───────────────────────────────────────────────┐
   │      Task 02.0 (Claude Code Settings)                               │
   │            │                                                        │
   │            ├──► Task 03.0 (Claude Code Subprocess Tool)             │
   │            │          │                                             │
   │            │          └──► Task 04.0 (Claude Code Subscription/     │
   │            │                          Login Authentication)         │
   │            └──► Task 05.0 (Claude Code Events & Exceptions)         │
   │                                                                     │
   ├── OpenHands track ─────────────────────────────────────────────────┤
   │      Task 06.0 (OpenHands Settings)                                 │
   │            │                                                        │
   │            ├──► Task 07.0 (OpenHands Client & Process)              │
   │            │          │                                             │
   │            │          └──► Task 08.0 (OpenHands Tool)               │
   │            └──► Task 09.0 (OpenHands Events & Exceptions)           │
   │                                                                     │
   └──────────────────────── Tasks 01–09 ──────────────────────────────┤
                                                                        └──► Task 10.0 (Harness Composition Root & CLI)
                                                                                   │  (deletes openclaude/composition.py;
                                                                                   │   Settings.harness nesting; agents.yaml roles)
                             Tasks 01–10 ─────────────────────────────────────────┤
                                                               ├──► Task 11.0 (Unit Tests)        ← incremental
                                                               ├──► Task 12.0 (Integration Tests) ← incremental
                                                               └──► Task 13.0 (Docs & CI)
```

The Claude Code track (02.0–05.0) and the OpenHands track (06.0–09.0) are
**independent of each other** once 01.0 lands and can proceed fully in
parallel; within the Claude Code track, 04.0 depends on 03.0 as noted above.

**Minimum viable:** 01.0 → (02.0 → 03.0) → 10.0 → 11.0 — a working
Claude-Code-only harness (in `auth_mode="auto"`, no subscription-login
validation) with the composition root generalised and OpenClaude still
functioning.
**Full milestone:** all thirteen tasks, both new backends, subscription/login
authentication, integration tests, and docs.

---

## File map (target state after milestone)

```
src/aegis_swr/
├── config/
│   ├── settings.py                    ← updated: Settings.openclaude → Settings.harness (nested) (C12)
│   └── agents.yaml                    ← updated: claude_code_agent + openhands_agent roles (C11)
├── cli/
│   └── commands.py                    ← updated: `aegis code-intel check` becomes backend-agnostic (C4)
├── code_intel/                        ← UNCHANGED (Milestone 0004)
│   ├── backend.py                     ← CodeIntelBackend ABC, CodeResult, CodeTaskContext — untouched
│   ├── agent.py                       ← CodeAgent — untouched
│   └── budget.py                      ← CallBudget — untouched
├── openclaude/                        ← UNCHANGED impl; composition.py DELETED
│   ├── config.py                      ← unchanged (now nested under Settings.harness.openclaude)
│   ├── tool.py / process.py / events.py / exceptions.py / grpc/  ← unchanged
│   └── composition.py                 ← DELETED (logic moved to harness/composition.py)
├── claude_code/                       ← NEW MODULE
│   ├── __init__.py
│   ├── config.py                      ← ClaudeCodeSettings incl. `auth_mode` (C5, C6, C7)
│   ├── tool.py                        ← ClaudeCodeTool (the CodeIntelBackend; auth resolution + probe; C6, C7, C9)
│   ├── process.py                     ← one-shot spawn + NDJSON-stream parse; argv-safety + credential-env helper (C6, C7)
│   ├── events.py                      ← claude_code.* event dataclasses incl. `auth_failed` (C10)
│   └── exceptions.py                  ← ClaudeCodeConfigError, ClaudeCodeUnavailableError (incl. auth failures), …
├── openhands/                         ← NEW MODULE
│   ├── __init__.py
│   ├── config.py                      ← OpenHandsSettings (C5, C8)
│   ├── client.py                      ← sole importer of the OpenHands HTTP/WS client (C3)
│   ├── process.py                     ← sidecar lifecycle (C8; mirrors OpenClaudeProcess / 0004 C6)
│   ├── tool.py                        ← OpenHandsTool (the CodeIntelBackend; C8, C9)
│   ├── events.py                      ← openhands.* event dataclasses (C10)
│   └── exceptions.py                  ← OpenHandsConfigError, OpenHandsUnavailableError, …
└── harness/                           ← NEW MODULE (neutral selection + composition)
    ├── __init__.py
    ├── config.py                      ← HarnessSettings: selector + nested settings; C1/C2 resolution
    ├── composition.py                 ← create_code_intel_backend(...): the sole C4 branch; only importer of all three families
    └── exceptions.py                  ← HarnessConfigError, HarnessUnavailableError (C2)

tests/
├── unit/
│   ├── harness/                       ← NEW: test_config.py (selection matrix), test_composition.py, test_isolation.py
│   ├── claude_code/                   ← NEW: test_config.py, test_process.py (argv-safety), test_tool.py, test_auth_modes.py (C7), test_events.py, test_isolation.py
│   └── openhands/                     ← NEW: test_config.py, test_client.py, test_process.py, test_tool.py, test_events.py, test_isolation.py
└── integration/
    ├── claude_code/                   ← NEW: live `claude` binary; skipped without CLAUDE_CODE_ENABLED + binary; a subscription-mode variant additionally skipped without a live login/CLAUDE_CODE_OAUTH_TOKEN
    └── openhands/                     ← NEW: live sidecar + Docker; skipped without OPENHANDS_SERVER_URL + Docker

docs/
└── config/                                ← existing category (cli.md, config.md, agents.md); also now
                                              home to openclaude-setup.md / openclaude-config-reference.md
                                              (moved here from a bare docs/ location as part of this milestone)
    ├── claude-code-setup.md              ← NEW (mirrors docs/config/openclaude-setup.md; documents both C7 auth modes and the licensing caveat)
    ├── claude-code-config-reference.md   ← NEW (mirrors docs/config/openclaude-config-reference.md)
    ├── openhands-setup.md                ← NEW
    ├── openhands-config-reference.md     ← NEW
    └── harness-selection.md              ← NEW: the C2 selection/ambiguity contract for operators

README.md (repo root)                 ← updated: Docker-on-Windows prerequisite; backend selection note
```

---

## Global acceptance criteria

- [ ] `aegis_swr/harness/composition.py` is the only module importing more than
      one backend family; each backend package imports no sibling (C3, grep-enforced).
- [ ] `aegis_swr/core/`, `aegis_swr/views/`, and `aegis_swr/code_intel/` import
      none of `aegis_swr.openclaude`, `aegis_swr.claude_code`,
      `aegis_swr.openhands`, or `grpc` (C3).
- [ ] `code_intel/backend.py`, `agent.py`, `budget.py` are byte-for-byte
      unchanged; `CodeResult.token_estimate` keeps its name and `int` type (C9).
- [ ] `openclaude/composition.py` is deleted; its C4 logic is present verbatim in
      `harness/composition.py` (C4).
- [ ] Selector unset + zero signals → capability unavailable, no exception
      (unchanged from 0004 C4).
- [ ] Selector unset + exactly one signal → that backend auto-selected; an
      `OPENCLAUDE_GRPC_URL`-only deployment needs zero further changes (C2).
- [ ] Selector unset + more than one signal → `HarnessConfigError` at
      settings-construction time (C2).
- [ ] Selector set to a backend whose signal is absent → `HarnessUnavailableError`
      at composition/health-check time (C2).
- [ ] Claude Code task text never appears in the constructed argv (C6, asserted
      in unit tests).
- [ ] `--dangerously-skip-permissions` (and any settings value producing it) is
      rejected at `ClaudeCodeSettings` validation (C6).
- [ ] Claude Code `token_estimate` is the real `usage` sum from the `result`
      message, not a length estimate (C9).
- [ ] `auth_mode="subscription"` rejects settings construction when
      `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is present in the inherited
      environment, and never passes `--bare` (C7).
- [ ] `auth_mode="subscription"` honours `CLAUDE_CODE_OAUTH_TOKEN` when set as
      the CI-friendly credential path, and otherwise relies on and health-checks
      a pre-existing `claude login` session before the first `delegate()` call
      (C7).
- [ ] `auth_mode="auto"` (default) adds no extra validation beyond the `claude`
      binary's own precedence — the Task 03.0 behaviour is unchanged when this
      task is not exercised (C7).
- [ ] No OAuth token, credential-file content, or `ANTHROPIC_API_KEY` value ever
      reaches a log sink, exception message, or `claude_code.auth_failed` event
      payload (C7, C13).
- [ ] OpenHands runs in the Docker-sandboxed runtime by default; a non-sandboxed
      runtime requires an explicit override (C8).
- [ ] `OpenHandsClient` is the only importer of the OpenHands client library (C3).
- [ ] `aegis code-intel check` is backend-agnostic and reports **which** backend
      is active (or "unavailable") for every selection outcome (C4).
- [ ] `agents.yaml` carries `claude_code_agent` and `openhands_agent` roles, each
      `enabled_when` its own presence signal (C11).
- [ ] `Settings.harness.openclaude` resolves; `Settings.openclaude` no longer
      exists; all consumers migrated (C12).
- [ ] All unit tests pass with `AEGIS_CODE_INTEL_BACKEND` unset, all presence
      signals unset, and no `claude`/Docker/OpenHands available.
- [ ] Integration tests are **skipped** (not failed) when a backend's presence
      signal, binary, or Docker is absent (per-backend, mirroring 0004); the
      subscription-auth-mode integration variant is additionally skipped without
      a live login session or `CLAUDE_CODE_OAUTH_TOKEN`.
- [ ] No raw incident payload, argv, or unredacted response/credential text
      reaches any log sink (C13).
- [ ] All new public classes and functions have RST docstrings (C13).
- [ ] `ruff` clean; per-backend unit coverage ≥ 90%; 100% branch on each new
      tool's `delegate` (mirroring 0004's `tool.py` gate).
