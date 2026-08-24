# OpenClaude Setup Guide

Operator-facing install and setup for wiring an
[OpenClaude](https://github.com/Gitlawb/openclaude) sidecar into Aegis SWR as its
Code Intelligence backend.

## 1. Overview

OpenClaude is the **sole Code Intelligence backend** in Aegis SWR
([contract C4](/docs/roadmap/0004-code-intelligence/plan.md#c4--backend-registration-contract)).
It runs as a headless gRPC sidecar pointed at any OpenAI-compatible endpoint
(including a self-hosted vLLM instance). Aegis SWR delegates one open-ended,
multi-file code-navigation task and consumes the response stream; OpenClaude's
own internal agentic loop (`Read` / `Grep` / `Glob` / `Bash`) does the work.

Enabling it requires a **single environment variable** and **zero Python
changes**: set `OPENCLAUDE_GRPC_URL` to the running sidecar's endpoint. When the
variable is unset, code intelligence is simply unavailable and the rest of the
pipeline is unaffected.

- Architecture and contracts: [Milestone 0004 plan](/docs/roadmap/0004-code-intelligence/plan.md).
- Full settings/event reference: [OpenClaude configuration reference](/docs/config/openclaude-config-reference.md).

## 2. Prerequisites

- **Node.js + npm** on the host. Install the OpenClaude CLI globally:

```bash
npm install -g @gitlawb/openclaude@latest
```

  OpenClaude is treated as an opaque, versioned black-box service reached over
  gRPC; nothing in this repository vendors or builds it.

- `uv sync` runs a best-effort npm-install helper
  (`scripts/postinstall_openclaude.py`) so a fresh environment is normally
  sufficient on a machine that already has Node.js/npm. The helper **logs a
  warning and never fails** when npm is absent — run the `npm install -g` command
  above by hand in that case before using managed mode.

- **Optional navigation CLIs** on the sidecar's `PATH`: `gtags`, `global`,
  `semgrep`, `rg`, `find`, `cat`. These are what OpenClaude shells out to via the
  `Bash` tool; their absence degrades navigation quality but does **not** break
  startup.

- Aegis SWR itself needs **no** OpenClaude Python dependency beyond the committed
  gRPC stubs. A missing binary or unset URL simply means code intelligence is
  unavailable — not an error.

## 3. External mode (default, `auto_start=false`)

In external mode you start and own the OpenClaude process; Aegis SWR only
health-checks it.

1. Launch OpenClaude as a long-lived headless gRPC server with the **read-only
   forensic allowlist**:

   ```bash
   openclaude --grpc --port 50051 \
     --allowed-tools Read,Grep,Glob,Bash \
     --bash-allowlist gtags,global,semgrep,rg,find,cat
   ```

   These flags must match `OPENCLAUDE_ALLOWED_TOOLS` /
   `OPENCLAUDE_BASH_ALLOWLIST` so the startup allowlist probe
   ([contract C7](/docs/roadmap/0004-code-intelligence/plan.md#c7--permission-and-tool-allowlist-enforcement))
   does not raise `OpenClaudeUnavailableError`.

2. Point Aegis SWR at the running server:

   ```bash
   export OPENCLAUDE_GRPC_URL=localhost:50051
   ```

3. **Verify** the wiring without opening a connection (`--dry-run` is the
   default):

   ```bash
   aegis code-intel check
   ```

   Expected output (the backend is registered, but **no** gRPC connection is
   attempted):

   ```
   Code intelligence backend registered (OpenClaude) (dry-run: process not started).
   ```

   With `OPENCLAUDE_GRPC_URL` unset the same command reports:

   ```
   Code intelligence unavailable (OPENCLAUDE_GRPC_URL unset).
   ```

   To exercise the live path (health-check + real gRPC handshake), pass
   `--no-dry-run`:

   ```bash
   aegis code-intel check --no-dry-run
   ```

## 4. Managed mode (`auto_start=true`)

In managed mode Aegis SWR launches, supervises, and terminates the sidecar.

```bash
export OPENCLAUDE_AUTO_START=true
export OPENCLAUDE_BINARY=openclaude          # binary name on PATH, or a full path
export OPENCLAUDE_GRPC_URL=localhost:0        # localhost:0 = pick a free port
```

Aegis SWR then:

- spawns the sidecar as a subprocess and **passes the allowlist flags itself**
  (C7 — the operator does not supply them);
- waits for the gRPC port to open (up to `connect_timeout_s`);
- terminates it on shutdown with **SIGTERM, then SIGKILL** after a grace period
  ([contract C6](/docs/roadmap/0004-code-intelligence/plan.md#c6--process-lifecycle-contract)).

Subprocess `stderr` is forwarded to the logger at `DEBUG` only; `stdout` is
discarded (gRPC output travels on the channel).

**External vs managed:** prefer *external* when a shared, long-lived sidecar is
managed by your platform (systemd, a container, etc.) and you want restart
semantics decoupled from Aegis SWR runs. Prefer *managed* for single-run or CI
workflows where Aegis SWR should own the sidecar's full lifecycle.

## 5. User-supplied model contract (OpenClaude's own env vars)

> **These are OpenClaude's own environment variables, not Aegis SWR settings.**
> Aegis SWR never reads them and only needs `OPENCLAUDE_GRPC_URL` to locate the
> server.

| Variable | Owned by | Purpose |
|---|---|---|
| `CLAUDE_CODE_USE_OPENAI` | OpenClaude | Switch OpenClaude to its OpenAI-compatible provider shim. |
| `OPENAI_BASE_URL` | OpenClaude | Your endpoint (e.g. a self-hosted vLLM URL). |
| `OPENAI_MODEL` | OpenClaude | The model name your endpoint serves. |
| `OPENAI_API_KEY` | OpenClaude | Credential for your endpoint (may be empty for unauthenticated local servers). |

**Tool-quality caveat:** navigation quality depends heavily on the chosen model.
Small local models struggle with long multi-step tool flows; if navigation
produces answers with no tool calls, the model likely guessed rather than
navigated. See OpenClaude's upstream documentation for provider configuration
details.

## 6. Troubleshooting

### Health-check failure — `OpenClaudeUnavailableError` at startup

The sidecar is unreachable. Work through:

1. Confirm the server is listening on the expected port
   (e.g. `bash -c '</dev/tcp/localhost/50051' && echo open`).
2. Confirm `OPENCLAUDE_GRPC_URL` matches the port the sidecar bound to.
3. Confirm the sidecar actually started (managed mode: check the `DEBUG` log for
   forwarded `stderr`).
4. If the sidecar is slow to warm, raise `OPENCLAUDE_CONNECT_TIMEOUT`.

### Allowlist denial — `PermissionDeniedError` / `OpenClaudePermissionDenied`

A tool or `Bash` binary outside the allowlist was exercised (or the external-mode
startup probe detected a mismatch and raised `OpenClaudeUnavailableError`). This
is **by design** — forensic analysis is read-only and OpenClaude must not mutate
the repository under analysis.

1. Confirm your external-mode launch flags match `OPENCLAUDE_ALLOWED_TOOLS` and
   `OPENCLAUDE_BASH_ALLOWLIST` exactly.
2. A denied command surfaces as a non-retriable failure result (it does not crash
   the run) and emits an `OpenClaudePermissionDenied` event.
3. Widening either allowlist requires an explicit settings override **and an
   ADR** (C1 / C7) — do not relax it casually.

See the [configuration reference](/docs/config/openclaude-config-reference.md) for the
complete settings and event tables.
