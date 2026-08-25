# OpenHands Setup Guide

Operator-facing install and setup for wiring an OpenHands sidecar into Aegis SWR as its
Code Intelligence backend.

## 1. Overview

OpenHands is **one selectable Code Intelligence backend** in Aegis SWR — a long-lived
sidecar reached over **REST/WebSocket**, consuming an **Action/Observation** event
stream. Its distinguishing property is that its runtime executes navigation tools inside
a **Docker sandbox** by default, unlike the host-permission Claude Code and OpenClaude
backends. This sandbox is the explicit reason OpenHands was included as a backend: Aegis
SWR treats every incident payload as hostile, and Docker container isolation is the
strongest available runtime guard against that surface.

Enabling it requires a **single presence signal** (`OPENHANDS_SERVER_URL`) and **zero
Python changes** (contract C4). When the variable is unset, this backend is not
registered and the rest of the pipeline is unaffected.

How the harness picks among multiple configured backends is described in
[Code Intelligence Backend Selection](/docs/config/harness-selection.md) (C2).

- Milestone plan and contracts: [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md).
- Full settings and event reference: [OpenHands configuration reference](/docs/config/openhands-config-reference.md).

## 2. Prerequisites

> **Docker on Windows is required for this backend.**
>
> Aegis SWR is Windows-only. The OpenHands runtime is Docker-sandboxed by default (C8),
> which means **Docker Desktop** (or a compatible Docker engine) must be installed and
> running on the Windows host before the OpenHands backend can operate. This is a new
> operator prerequisite introduced by Milestone 0005; it is **not required** for the
> OpenClaude or Claude Code backends.

- **Docker Desktop for Windows** (or an equivalent Docker engine) installed and running.
  The OpenHands sidecar itself manages container lifecycle; Aegis SWR communicates with
  it only via REST/WebSocket.
- **The OpenHands server** reachable at a URL you supply as `OPENHANDS_SERVER_URL`, or
  launchable in managed mode (`OPENHANDS_AUTO_START=true`). OpenHands is an opaque
  black-box service; nothing in this repository vendors or builds it.
- **`python-socketio` is not installed and is not a project dependency.** The
  Socket.IO transport path in `openhands/client.py` is guarded by a try/import and
  is **inert** until the library is present. The backend cannot reach a real sidecar
  over Socket.IO until you install it separately:

  ```bash
  uv add python-socketio   # or: pip install python-socketio
  ```

  The REST health-check path (`httpx`) works without it, but the full
  Action/Observation streaming requires the Socket.IO library.

> **Wire shapes are unvalidated.** The REST endpoint `POST /api/conversations` and the
> Socket.IO messages `oh_event` / `oh_user_action` follow the researched OpenHands
> V1-server names recorded in the Milestone 0005 spec, but have **never been exercised
> against a live OpenHands server**. Treat the first live run as contract discovery and
> expect to adjust if the OpenHands server's actual API diverges from what was
> researched.
>
> This is one of **15 catalogued open questions**. Before attempting a first live
> bring-up, read [§8 Open questions and unverified assumptions](#8-open-questions-and-unverified-assumptions)
> — it lists every researched-but-unconfirmed assumption, which three are
> **blocking**, and how to settle each. Unlike every other Aegis SWR backend, this
> one has never run against its real counterpart.

- LiteLLM model configuration is OpenHands' own concern (see [§6](#6-user-supplied-model-contract-openhands-own-litellm-env))
  — Aegis SWR never reads or configures it.
- The absence of the presence signal or Docker means this backend is unavailable
  (integration tests skip, not fail) — not an error.

## 3. External mode (server already running)

In external mode you start and own the OpenHands process; Aegis SWR only health-checks
it.

1. Start the OpenHands server on the host according to the upstream OpenHands
   documentation, ensuring Docker Desktop is running.
2. Point Aegis SWR at the running server:

   ```bash
   export OPENHANDS_SERVER_URL=http://localhost:3000
   ```

3. **Verify** the wiring without opening a connection (`--dry-run` is the default):

   ```bash
   aegis code-intel check
   ```

   Expected output (backend registered, no connection attempted):

   ```text
   Code intelligence backend active: openhands (dry-run: sidecar not started).
   ```

   With `OPENHANDS_SERVER_URL` unset:

   ```text
   Code intelligence unavailable (no backend active; no presence signal set).
   ```

   To exercise the live health-check path, pass `--no-dry-run`:

   ```bash
   aegis code-intel check --no-dry-run
   ```

Exit codes: `0` = active or unavailable (no error), `1` = selected-but-unreachable,
`2` = ambiguous configuration (see [harness-selection.md](/docs/config/harness-selection.md#5-verifying-the-active-backend)).

## 4. Managed mode (`auto_start=true`)

In managed mode Aegis SWR launches, supervises, and terminates the sidecar. This mode
requires the sidecar binary to be on `PATH` or reachable as specified by your OpenHands
installation.

```bash
export OPENHANDS_SERVER_URL=http://localhost:3000
export OPENHANDS_AUTO_START=true
```

Aegis SWR then:

- spawns the sidecar as a subprocess;
- waits for the REST endpoint to become reachable (up to `connect_timeout_s`);
- registers the sidecar on the application `AsyncExitStack` for RAII teardown;
- tears it down on application exit (C6/C8).

**External vs managed:** prefer *external* when a shared, long-lived sidecar is managed
by your platform (a container orchestrator, a Windows service, etc.) and you want
restart semantics decoupled from Aegis SWR runs. Prefer *managed* for single-run or CI
workflows where Aegis SWR should own the sidecar's full lifecycle.

## 5. Sandbox / runtime posture

The OpenHands runtime executes navigation tools inside a **Docker container by default**
(`runtime_mode`, default `"docker"`). This is the defining security property of this
backend.

| Runtime | Sandboxed | How to enable |
|---|---|---|
| `docker` *(default)* | Yes — Docker container | Set `OPENHANDS_RUNTIME=docker` (or leave unset). |
| `remote` | Yes — OpenHands-managed remote sandbox | Set `OPENHANDS_RUNTIME=remote`. |
| `local` | **No** — runs on host OS | Requires explicit override plus an ADR (see below). |

**A non-sandboxed runtime (`local`) requires an explicit override and an ADR.** Set
`OPENHANDS_ALLOW_UNSANDBOXED=true` to permit it; `OpenHandsConfigError` is raised at
construction otherwise. An ADR recording the decision is required per Milestone 0005
policy (C8). This discipline mirrors the OpenClaude and Claude Code allowlist-relaxation
requirements.

Read-only access is enforced by the `allowed_tools` allowlist (see
[configuration reference §2](/docs/config/openhands-config-reference.md#2-runtime--sandbox-default-and-rationale))
and by the container filesystem. Write-capable tools (`edit`, `write`, `run`) are off by
default; enabling them logs a loud warning and requires an explicit settings override.

For a direct comparison with the Claude Code backend's host-OS permission model, see
[Read-only / permission posture](/docs/config/claude-code-setup.md#4-read-only--permission-posture) in
the Claude Code setup guide.

## 6. User-supplied model contract (OpenHands' own LiteLLM env)

> **These are OpenHands' own environment variables, not Aegis SWR settings.**
> Aegis SWR never reads them and only needs `OPENHANDS_SERVER_URL` to locate the
> server.

OpenHands resolves its LiteLLM provider, model, and API key from its own configuration.
Point `OPENHANDS_SERVER_URL` at a running, fully-configured OpenHands instance; its AI
model is your and OpenHands' concern. See the upstream OpenHands documentation for
provider configuration details.

**Tool-quality caveat:** navigation quality depends heavily on the configured model.
Models that struggle with long multi-step tool flows may produce answers without
meaningful tool calls.

## 7. Troubleshooting

### Health-check failure — `OpenHandsUnavailableError`

The sidecar is unreachable. Work through:

1. Confirm the OpenHands server is listening at the expected URL
   (e.g. `curl -s http://localhost:3000/api/health`).
2. Confirm `OPENHANDS_SERVER_URL` matches the scheme, host, and port the sidecar bound
   to.
3. On Windows: confirm **Docker Desktop is running**. The OpenHands runtime requires a
   Docker engine; if Docker Desktop is stopped, the sidecar may fail to start or to
   launch its container runtime.
4. In managed mode: check the Aegis SWR application log (at `DEBUG`) for forwarded
   sidecar stderr; confirm the sidecar binary is on `PATH`.
5. If the sidecar is slow to warm, raise `OPENHANDS_CONNECT_TIMEOUT` (default 10 s).

### Permission denied — `openhands.permission_denied`

A sandbox action requested a binary outside the `allowed_tools` allowlist or outside the
container filesystem. This is **by design** — forensic analysis is read-only. Widening
the allowlist requires an ADR.

### Container security note

The attack surface of this backend is the Docker sandbox itself. Keep the OpenHands
runtime image and the Docker engine patched; do not use the `local` runtime without an
ADR. Aegis SWR does not validate or inspect the Docker image.

See the [configuration reference](/docs/config/openhands-config-reference.md) for the complete
settings and event tables.

---

## 8. Open questions and unverified assumptions

**Read this before a first live run.** The OpenHands backend was implemented and
unit-tested against an injection seam, but has **never been exercised end-to-end
against a running OpenHands server**. Nothing below is a known defect — each item is
a place where the implementation encodes a *researched assumption* that a live run
will either confirm or correct. Treat the first live bring-up as **contract
discovery**, not regression testing, and budget time accordingly.

Every other Aegis SWR backend was validated against its real counterpart before
shipping. This one was not, and that difference is the single most important thing
to know about it.

### 8.1 Blocking — must be resolved before any live run

| # | Question | Current assumption | How to resolve |
|---|---|---|---|
| O-1 | **Which Socket.IO client library, and which version?** `python-socketio` is not installed and not a dependency; the import in `openhands/client.py` is guarded and the transport is inert. | The stock `python-socketio` async client speaks the OpenHands server's protocol. | Install it, attempt a connection, confirm the Socket.IO protocol/EIO version matches the server. OpenHands may instead expect its own SDK. |
| O-2 | **Is a server-side credential required?** Aegis SWR sends no authentication to the OpenHands server. | The sidecar is unauthenticated on a trusted local interface. | Check whether your deployment requires an API key/session token. **If it does, this backend cannot currently authenticate** and `OpenHandsSettings` needs a new field. |
| O-3 | **How is the server actually launched in managed mode?** `OpenHandsProcess` spawns a configured command and polls the port. | Whatever `auto_start` invokes is a long-lived OpenHands **server** that owns its own Docker runtime. | Confirm the real launch command for your OpenHands version. Note Aegis SWR **never** shells out to Docker itself — if your OpenHands needs `docker run`, that is the operator's wrapper, not this code. |

### 8.2 Protocol shape — likely to need adjustment on first contact

| # | Question | Current assumption | Impact if wrong |
|---|---|---|---|
| O-4 | **REST conversation creation.** | `POST /api/conversations` creates a conversation and returns an id. | `delegate()` fails at start-up; path/verb/response shape need correcting in `client.py`. |
| O-5 | **Socket.IO message names.** | Server→client `oh_event`; client→server `oh_user_action`, with the connection carrying `conversation_id`. | No events arrive, or the task is never delivered. |
| O-6 | **Raw event dict → `AgentEvent` projection.** `_to_event` maps the server's event payload onto `EventKind.{MESSAGE, ACTION, OBSERVATION, PERMISSION, FINISHED, ERROR}`. | OpenHands' Action/Observation taxonomy collapses cleanly onto those six kinds. | Unmappable kinds currently surface as a terminal `ERROR`, so a mismatch is **loud, not silent** — but the stream may terminate early. |
| O-7 | **Terminal-event detection.** | A `FINISHED` (or `ERROR`) event reliably ends every run. | The stream could hang until `OPENHANDS_REQUEST_TIMEOUT`. The timeout is the backstop, so this fails safe but slowly. |
| O-8 | **Conversation lifecycle.** One conversation is created per `delegate()` call and is not explicitly deleted. | The server reaps conversations itself. | Long-running deployments may accumulate server-side conversation state. Worth watching on the first sustained run. |

### 8.3 Semantics — assumptions that affect correctness, not connectivity

| # | Question | Current assumption | Consequence |
|---|---|---|---|
| O-9 | **Does the server report token usage?** | The terminal event *may* carry a usage total. | Handled either way by design (C9): `OpenHandsCompleted.usage_reported` records which path was taken. If usage never arrives, budgets fall back to the boundary estimate `max(1, len(content) // 4)` — correct, just coarser. **Check `usage_reported` on a first live run** to learn which regime you are in. |
| O-10 | **Are the `allowed_tools` names right, and does the server honour them?** Defaults are lowercase `read, grep, glob, browse`. | OpenHands accepts a client-supplied tool allowlist using those names. | If the allowlist is server- or agent-side configuration instead, Aegis SWR's list is **advisory only** and the Docker sandbox becomes the sole read-only guard. That is still the authoritative guard by design — but verify it, because the tool-side gate is deliberately light. |
| O-11 | **Does a confirmation/permission event exist?** The `PERMISSION` kind drives the defence-in-depth gate. | The server emits a distinguishable confirmation-required event. | If it does not, the gate never fires and the container is the only guard (see O-10). |
| O-12 | **What are the valid `runtime_mode` values?** | `docker` is the sandboxed default; `local` is the unsandboxed escape. | Other runtimes exist in the OpenHands ecosystem (remote/hosted variants). Confirm the identifier your server expects; an unknown value is rejected at settings validation, so this fails closed. |

### 8.4 Environment and operations

| # | Question | Notes |
|---|---|---|
| O-13 | **Docker on Windows — WSL2 backend vs Windows containers.** | Aegis SWR is Windows-only. The OpenHands runtime image is Linux; Docker Desktop must be on the **WSL2 backend**. Untested here. |
| O-14 | **No OpenHands server version is pinned.** | The integration was written against researched **V1** server API names. There is no compatibility matrix; record the version you validate against. |
| O-15 | **Do the client timeouts align with the server's own limits?** | `OPENHANDS_CONNECT_TIMEOUT` (10 s) and `OPENHANDS_REQUEST_TIMEOUT` (120 s) are Aegis SWR-side. If the server enforces a shorter deadline it will win; if longer, Aegis SWR aborts first and reaps the connection. |

### 8.5 What is *not* in question

To keep the list honest, these were verified and need no live run:

- Settings validation, including empty-env coercion for every field, and the
  Docker-sandbox default (`OPENHANDS_RUNTIME=""` resolves to `docker`, never to an
  unsandboxed runtime).
- The C3 isolation boundary — `openhands/client.py` is the only module importing the
  client library, enforced by an AST test in CI.
- Event taxonomy, payload-freedom, and the single-token-carrier invariant.
- `OpenHandsTool.delegate()` at 100% branch coverage, including every failure path,
  dry-run short-circuit, truncation, and budget accounting.
- Zero-config safety: an unconfigured OpenHands never breaks
  `HarnessSettings()` construction or any other backend.

### 8.6 Resolving these

`tests/integration/openhands/` exists precisely for this and is skip-guarded on
`OPENHANDS_SERVER_URL`, Docker reachability, **and** `python-socketio` being
importable. Once a server is available:

```bash
uv add python-socketio
export OPENHANDS_SERVER_URL=http://localhost:3000
uv run pytest tests/integration/openhands/ -q
```

Its sandbox-verification test is the load-bearing one — it asserts the host lacks
`/.dockerenv` while the runtime reports it present, proving execution really happened
inside the container. Please update this section as each item is settled, and record
the validated OpenHands server version.
