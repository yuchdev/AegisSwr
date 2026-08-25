# 02 - OpenHands docs (setup and config reference)

**Parent task:** 13.0 Documentation & CI
**State:** ✅ Complete
**Depends on:** 06.0 (`OpenHandsSettings`, C8), 07.0 (client and sidecar lifecycle), 08.0 (`OpenHandsTool` — Action/Observation → `CodeResult`), 09.0 (`openhands.*` event taxonomy, C10); documents behavior delivered by those tasks.
**Blocks:** none

## Objective

Author the operator-facing OpenHands documentation pair, mirroring the shipped
OpenClaude pair section-for-section:

- `docs/config/openhands-setup.md` — mirrors [`docs/config/openclaude-setup.md`](/docs/config/openclaude-setup.md);
  lets an operator stand up the OpenHands sandboxed sidecar by setting a single
  presence signal (`OPENHANDS_SERVER_URL`), with **zero Python changes** (C4). It
  must call out the **Docker-on-Windows prerequisite** explicitly (C8).
- `docs/config/openhands-config-reference.md` — mirrors
  [`docs/config/openclaude-config-reference.md`](/docs/config/openclaude-config-reference.md);
  transcribes the `OpenHandsSettings` field table (C8), the sandboxed-runtime
  default and override discipline, the allowlist, the worked `openhands_agent`
  role YAML (C11), and the `openhands.*` event reference (C10).

## File: `docs/config/openhands-setup.md` (mirrors `docs/config/openclaude-setup.md`)

Outline (section headings map to the OpenClaude setup guide — external/managed
modes map onto OpenHands' own external/`auto_start` sidecar modes):

### 1. Overview
- OpenHands is **one selectable Code Intelligence backend**: a long-lived sidecar
  over **REST/WS** (Topology A-equivalent, mirroring OpenClaude's streaming
  pattern), consuming an **Action/Observation** event stream. Its distinguishing
  value is that its runtime executes tools inside a **Docker sandbox** — unlike
  the host-permission OpenClaude and Claude Code backends. State that this sandbox
  is the explicit reason OpenHands was chosen (link Background).
- Enable with a single presence signal `OPENHANDS_SERVER_URL` and zero Python
  changes. Link to [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md),
  `docs/config/openhands-config-reference.md` (code span), and
  [`docs/config/harness-selection.md`](/docs/config/harness-selection.md) (C2 selection).

### 2. Prerequisites (incl. Docker-on-Windows — REQUIRED callout)
- **Docker must be available on the host.** Because Aegis SWR is **Windows-only**
  (`../CLAUDE.md`), this makes **Docker Desktop / a Docker engine on Windows a new
  operator prerequisite** — an explicit callout box, and the same line is added to
  the root `README.md` (subtask 03).
- The OpenHands server itself (the sidecar) reachable at `OPENHANDS_SERVER_URL`,
  or launchable in managed mode (`auto_start`). OpenHands is an opaque black-box
  service; nothing in this repo vendors or builds it.
- LiteLLM model configuration is OpenHands' own concern (mirror the OpenClaude
  "user-supplied model contract" framing) — Aegis SWR resolves no model.
- The absence of the presence signal / Docker simply means this backend is
  unavailable (integration tests skip, not fail), not an error.

### 3. External mode (server already running)
- Point `OPENHANDS_SERVER_URL` at the running sidecar. Aegis SWR health checks it
  (mirrors OpenClaude external mode; `OpenHandsProcess` external mode, C8).
- **Verification** with `aegis code-intel check` (backend-agnostic, C4): show the
  `--dry-run` output (backend registered as OpenHands, no network call) and the
  `--no-dry-run` health-check path. Mirror the OpenClaude verification block.

### 4. Managed mode (`auto_start=true`)
- Set `OPENHANDS_SERVER_URL` (or a bind hint) + `auto_start`; Aegis SWR launches
  the sidecar, waits for readiness (`connect_timeout_s`), registers it on the app
  `AsyncExitStack`, and tears it down on exit (RAII, mirrors OpenClaude C6 / C8).
- When to prefer external vs. managed (lifecycle ownership) — mirror OpenClaude §4.

### 5. Sandbox / runtime posture (the OpenHands-specific section)
- The runtime runs tools inside a **Docker container by default**
  (`runtime_mode`/sandbox selector, default the sandboxed Docker runtime, C8).
- A **non-sandboxed** runtime requires an **explicit override plus an ADR** — the same
  discipline as the OpenClaude allowlist. State this plainly.
- Read-only guard: allowlist + container filesystem.

### 6. User-supplied model contract (OpenHands' own LiteLLM env)
- Callout box mirroring OpenClaude §5: OpenHands' LiteLLM configuration is its
  own/the operator's concern; Aegis SWR never reads it and needs only
  `OPENHANDS_SERVER_URL`. Point at OpenHands' upstream docs.

### 7. Troubleshooting
- **Health-check / connection failure** (`OpenHandsUnavailableError`): server
  unreachable, wrong `OPENHANDS_SERVER_URL`, sidecar not started, port not open
  within `connect_timeout_s`; **Docker not running** (Windows-specific: Docker
  Desktop not started). Diagnostic sequence.
- **Permission denied** (`openhands.permission_denied`): a tool outside the
  allowlist / container FS.
- **Container escape / sandbox note**: the new attack surface is the Docker
  sandbox itself; keep the runtime image and Docker engine patched.

## File: `docs/config/openhands-config-reference.md` (mirrors `docs/config/openclaude-config-reference.md`)

Outline (section headings map 1:1 to the OpenClaude config reference):

### 1. `OpenHandsSettings` fields (from C8)
Transcribe the field table exactly (env prefix `OPENHANDS_`):

| Field               | Env var                     | Type                          | Default                                           |
|---------------------|-----------------------------|-------------------------------|---------------------------------------------------|
| `server_url`        | `OPENHANDS_SERVER_URL`      | `Optional[str]`               | `None` (presence signal — backend not registered) |
| `runtime_mode`      | `OPENHANDS_RUNTIME`         | `str`                         | the sandboxed Docker runtime                      |
| `allowed_tools`     | `OPENHANDS_ALLOWED_TOOLS`   | `list[str]` (comma-separated) | (read-only default, per Task 06.0)                |
| `connect_timeout_s` | `OPENHANDS_CONNECT_TIMEOUT` | `int`                         | (per Task 06.0)                                   |
| `request_timeout_s` | `OPENHANDS_REQUEST_TIMEOUT` | `int`                         | (per Task 06.0)                                   |
| `auto_start`        | `OPENHANDS_AUTO_START`      | `bool`                        | `False`                                           |

Include notes in prose: `server_url=None` means backend not registered;
`runtime_mode` defaults sandboxed and a non-sandboxed value requires an ADR;
`request_timeout_s` must exceed `connect_timeout_s`.

### 2. Runtime / sandbox default and rationale
- One-line rationale: sandboxed Docker runtime is the default because every
  incident payload is treated as hostile; a non-sandboxed override needs an ADR
  (mirror OpenClaude's allowlist-relaxation-needs-ADR section).
- Allowlist rationale per entry and the read-only invariant.

### 3. Worked `openhands_agent` role YAML (from C11)
- Complete `agents.yaml` fragment: `provider: openhands`, `model: ~` (no LiteLLM
  model resolved), `timeout_s` matching `request_timeout_s`,
  `enabled_when: OPENHANDS_SERVER_URL`. Note `enabled_when` is inert config parsed
  only by `RouterConfig`, mirroring the OpenClaude role.

### 4. Event reference (from C10)
Reproduce the `openhands.*` events — class, `event_type`, when emitted:

| Concept           | `event_type`                  | When emitted                                |
|-------------------|-------------------------------|---------------------------------------------|
| Connection up     | `openhands.connected`         | After successful health check / start       |
| Connection down   | `openhands.disconnected`      | On stop or connection loss                  |
| Tool invocation   | `openhands.action`            | On each Action in the stream                |
| Tool result       | `openhands.observation`       | On each Observation in the stream           |
| Permission denied | `openhands.permission_denied` | On a disallowed tool                        |
| Stream completed  | `openhands.completed`         | On terminal event; carries `token_estimate` |
| Stream error      | `openhands.error`             | On stream/connection error                  |

- Note `openhands.completed` is the sole token carrier; the estimate is
  server-reported usage when available, else the boundary estimate
  `max(1, len(content) // 4)` (C9). There is **no** `auth_failed` event (n/a for
  this backend — the auth surface is OpenHands' own LiteLLM config).

### 5. Cross-links
- Back to `docs/config/openhands-setup.md` (code span),
  [`docs/config/harness-selection.md`](/docs/config/harness-selection.md), and the
  [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md).

## Implementation notes
- Plain Markdown tables and fenced code blocks; no RST `:param:` notation.
- All env var names must match `.env.example` and the C8 table exactly.
- Do not paste real endpoints/credentials — use placeholders.
- C8/C9/C10/C11 in [plan.md](/docs/roadmap/0005-harness-backends/plan.md) are authoritative; this doc transcribes — the contract
  wins on any disagreement.
- Add both new files to the `docs/README.md` index (coordinate with `docs-updater`).

## Constraints
- Section-for-section parity with the OpenClaude pair; differ only in per-backend facts (REST/WS sidecar, Docker sandbox, Action/Observation stream).
- The Docker-on-Windows prerequisite callout is **mandatory** in the setup guide.
- The sandboxed-runtime default and the ADR-required override must be stated.
- Renders with zero broken internal links (`python scripts/check_doc_links.py docs/`).
- Absolute-from-repo-root links with a leading `/`; no relative chains.
- No design in these docs may cause a credential or incident payload to be logged or persisted unredacted (C13).

## Success criteria
- [ ] `docs/config/openhands-setup.md` created with sections 1–7 above, mirroring `docs/config/openclaude-setup.md`.
- [ ] The Docker-on-Windows prerequisite is an explicit callout in Prerequisites.
- [ ] Sandboxed-runtime default and ADR-required non-sandboxed override stated.
- [ ] `docs/config/openhands-config-reference.md` created with sections 1–5 above, mirroring `docs/config/openclaude-config-reference.md`.
- [ ] All `OpenHandsSettings` fields match C8.
- [ ] Worked `openhands_agent` role YAML with `enabled_when: OPENHANDS_SERVER_URL` included.
- [ ] All `openhands.*` events present; `completed` noted as sole token carrier; no `auth_failed` (n/a).
- [ ] Both files linked from `docs/README.md`.
- [ ] `python scripts/check_doc_links.py docs/` passes.
