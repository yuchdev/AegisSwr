# Claude Code Setup Guide

Operator-facing install and setup for wiring the `claude` CLI into Aegis SWR as its
Code Intelligence backend.

## 1. Overview

Claude Code is **one selectable Code Intelligence backend** in Aegis SWR — reached via
the installed `claude` CLI, spawned as a **one-shot subprocess per `delegate()`** call
with no persistent sidecar. This contrasts with the OpenClaude backend, which runs as a
long-lived gRPC sidecar: every Claude Code delegation spawns a fresh `claude` process,
collects its NDJSON result stream, and reaps the process on completion.

Enabling it requires a **single presence signal** (`CLAUDE_CODE_ENABLED=true`) plus a
resolvable credential, and **zero Python changes** (contract C4). When that variable is
unset, this backend is not registered and the rest of the pipeline is unaffected.

How the harness picks among multiple configured backends is described in
[Code Intelligence Backend Selection](/docs/config/harness-selection.md) (C2).

- Milestone plan and contracts: [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md).
- Full settings and event reference: [Claude Code configuration reference](/docs/config/claude-code-config-reference.md).

## 2. Prerequisites

- **The installed `claude` CLI** on the host `PATH`, or an explicit full path in
  `CLAUDE_CODE_BINARY`. Aegis SWR does not vendor, install, or update it.
- **One resolvable credential** (see [§5 Authentication modes](#5-authentication-modes-c7)):
  an `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`, a Claude.ai subscription login, or a
  `CLAUDE_CODE_OAUTH_TOKEN` for CI.
- **No Docker required** (unlike the OpenHands backend).
- **No Node.js/npm or gRPC stubs** (unlike the OpenClaude backend).

The absence of the binary or the unset presence signal simply means this backend is
unavailable — not an error. Integration tests skip rather than fail when
`CLAUDE_CODE_ENABLED` is unset.

## 3. Enabling the backend

### 3.1 Presence signal

Set the explicit opt-in presence signal:

```bash
export CLAUDE_CODE_ENABLED=true
```

Being on `PATH` is deliberately **not** a signal. A host-permission backend must
never activate silently.

If `CLAUDE_CODE_BINARY` is unset, the harness calls the bare `claude` command resolved
via `PATH`. Set an absolute path when the binary lives elsewhere:

```bash
export CLAUDE_CODE_BINARY=C:\Users\operator\AppData\Local\Programs\Claude\claude.exe
```

### 3.2 Backend selection

When `AEGIS_CODE_INTEL_BACKEND` is unset and `CLAUDE_CODE_ENABLED=true` is the only
presence signal set, Claude Code is auto-selected. Set the selector explicitly to force
selection even when other signals are present:

```bash
export AEGIS_CODE_INTEL_BACKEND=claude_code
```

More than one presence signal with no selector is a `HarnessConfigError` at
settings-construction time — see [Backend Selection](/docs/config/harness-selection.md#3-the-selection-truth-table).

### 3.3 Scratch working directory (mandatory when enabled)

Claude Code runs each one-shot `claude` process in a disposable working directory that
**must not** be the repository root or an ancestor of it. Set it before enabling:

```bash
export CLAUDE_CODE_SCRATCH_CWD=C:\Temp\aegis-claude-scratch
```

`ClaudeCodeConfigError` is raised at settings construction if `CLAUDE_CODE_ENABLED=true`
and `CLAUDE_CODE_SCRATCH_CWD` is unset.

### 3.4 Verification

Use `aegis code-intel check` (backend-agnostic, C4) to confirm the wiring without
running a real delegation. The default `--dry-run` mode builds and registers the backend
object graph but does not spawn a `claude` process or execute the startup auth-probe:

```bash
aegis code-intel check
```

Expected output when Claude Code is the active backend (dry-run, `auth_mode` defaults
to `auto`):

```text
Code intelligence backend active: claude_code (auth mode: auto) (dry-run: sidecar not started).
```

With `CLAUDE_CODE_ENABLED` unset:

```text
Code intelligence unavailable (no backend active; no presence signal set).
```

Pass `--no-dry-run` to also run the C7 startup auth-probe against the real `claude`
binary:

```bash
aegis code-intel check --no-dry-run
```

Exit codes: `0` = active or unavailable (no error), `1` = selected-but-unreachable,
`2` = ambiguous configuration (see [harness-selection.md](/docs/config/harness-selection.md#5-verifying-the-active-backend)).

## 4. Read-only / permission posture

Claude Code runs with **host OS permissions** — there is no container sandbox. Aegis SWR
applies three settings-time guards in place of a sandbox:

| Guard | Mechanism | Default |
|---|---|---|
| `allowed_tools` | Passed as `--allowedTools`; restricts the `claude` tool palette. | `Read,Grep,Glob` (read-only) |
| `permission_mode` | Restricts interactive tool approval; bypass values are rejected. | `default` |
| `scratch_cwd` | Disposable working directory; must not overlap the live source tree. | (mandatory) |

**`--dangerously-skip-permissions`** and any setting that would produce it
(`bypassPermissions`, `bypass`, `dangerously-skip-permissions`) are **rejected
unconditionally at settings-validation time** — the rejection does not depend on
`enabled`. No operator can stage a bypass value for later use.

Write-capable tools (`Write`, `Edit`) are excluded from the default allowlist. Granting
them logs a loud warning and is treated as a departure from the forensic read-only
guarantee; an ADR is required to widen the allowlist (C1/C7).

**Argv-safety:** task text is passed via a temp file (never command-line argv), so it
is not visible via `ps` on a shared host.

For a direct comparison with the OpenHands backend's Docker sandbox, see
[Sandbox / runtime posture](/docs/config/openhands-setup.md#5-sandbox--runtime-posture) in the
OpenHands setup guide.

## 5. Authentication modes (C7)

Unlike OpenClaude, which treats the model provider entirely as the operator's concern,
Claude Code has its own dual credential surface. Aegis SWR exposes an explicit
`auth_mode` so the choice is not left to the ambient environment.

Set it via:

```bash
export CLAUDE_CODE_AUTH_MODE=auto   # or api_key or subscription
```

| Mode | Credential used | `--bare` eligible | Construction-time validation |
|---|---|---|---|
| `auto` *(default)* | Whichever credential the `claude` binary resolves per its own precedence chain. | No | None — defers entirely to the binary. |
| `api_key` | `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`. | Yes (opt-in via `CLAUDE_CODE_BARE=true`) | None beyond the env-var name. |
| `subscription` | Claude.ai login session (OAuth). | **Never** | Rejects construction if `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is set (they silently outrank the login) or if `CLAUDE_CODE_BARE=true` is requested. |

### Credential precedence chain (Claude Code's own resolution, ranks 1–7)

The `claude` CLI resolves its credential in this order (highest rank first). Aegis SWR
reads **only the presence** of ranks 2–3 to enforce `subscription`-mode invariants —
never their values (C7/C13):

1. `ANTHROPIC_AUTH_TOKEN` (if set, highest)
2. `ANTHROPIC_API_KEY`
3. OAuth login session in `%USERPROFILE%\.claude\.credentials.json` (Windows)
4. `CLAUDE_CODE_OAUTH_TOKEN` environment variable
5. (lower ranks — Claude Code internals)
6. …
7. No credential (binary may prompt interactively — not suitable for automation)

When `auth_mode="subscription"` is selected, ranks 2–3 above must be absent. A stray
`ANTHROPIC_API_KEY=""` (empty CI secret) is treated as absent; a non-empty value raises
`ClaudeCodeConfigError` at construction, naming only the env-var name — never its value.

### Establishing a subscription login

The subscription mode is based on an interactive OAuth session that persists across
runs. On Windows (Aegis SWR's only supported platform):

```powershell
# Interactive login — run once as the operator; stores a session at
# %USERPROFILE%\.claude\.credentials.json
claude login
```

For CI pipelines, generate a long-lived OAuth token via `claude setup-token` and supply
it as:

```bash
export CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_CODE_OAUTH_TOKEN}
```

**Never print or log the token value.** Aegis SWR's `SensitiveFilter` and the
`ClaudeCodeAuthFailed` event both carry only failure-reason strings — never a
credential.

### Corporate / Enterprise SSO

The OAuth mechanism is identical for personal (Pro/Max), Team, and Enterprise seats.
`forceLoginMethod` and `forceLoginOrgUUID` are Claude Code managed-settings concerns;
Aegis SWR does not configure them.

## 5a. Licensing caveat (subscription mode)

> **Confirm with Anthropic before using `auth_mode="subscription"` in production.**
>
> No explicit Anthropic Terms of Service language was found during Milestone 0005
> development that clearly distinguishes personal (Pro/Max) from organizational
> (Team/Enterprise) subscription seats for **non-interactive, production automation at
> scale**. Using a personal Pro/Max subscription to drive automated production tooling
> may exceed its intended scope.
>
> `auth_mode` defaults to `auto`; the `subscription` value is **opt-in only** and ships
> without a recommendation to use it as the default automation path. Confirm the
> applicable seat type with Anthropic sales or legal before deploying
> `CLAUDE_CODE_AUTH_MODE=subscription` at scale.

## 6. Troubleshooting

### Auth failure — `ClaudeCodeUnavailableError` / `claude_code.auth_failed`

The startup auth-probe (`--no-dry-run`) or a `delegate()` call failed authentication.
The `ClaudeCodeAuthFailed` event carries a fixed-vocabulary `reason` and the attempted
`auth_mode` — **never** a credential or token value.

| `reason` value | Likely cause | Fix |
|---|---|---|
| `ambiguous_credential` | `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is set while `auth_mode="subscription"`. | Unset the API-key variable, or switch to `auth_mode="api_key"`. |
| `no_stored_login` | `auth_mode="subscription"` but no OAuth session in `%USERPROFILE%\.claude\.credentials.json` and no `CLAUDE_CODE_OAUTH_TOKEN`. | Run `claude login` interactively, or set `CLAUDE_CODE_OAUTH_TOKEN`. |
| `token_rejected` | The resolved credential was rejected by the auth-probe. | Check the credential is current; API keys may have expired or been revoked. |

The `ClaudeCodeUnavailableError` path is distinct from `ClaudeCodeConfigError`
(settings-shape error, e.g., `ANTHROPIC_API_KEY` set with `auth_mode="subscription"`).
`ClaudeCodeConfigError` fires at settings construction; `ClaudeCodeUnavailableError`
fires at the auth-probe or delegation.

### Permission denied — `claude_code.permission_denied`

A tool outside `--allowedTools` was exercised. This is **by design** — forensic
analysis is read-only. Widening `CLAUDE_CODE_ALLOWED_TOOLS` beyond `Read,Grep,Glob`
requires an ADR.

### Binary not found

Confirm `claude --version` works on the operator's `PATH` (or that `CLAUDE_CODE_BINARY`
points to a readable, executable file).

### Timeout

Raise `CLAUDE_CODE_REQUEST_TIMEOUT` (default 120 s) if long multi-file navigation tasks
are hitting the deadline.

See the [configuration reference](/docs/config/claude-code-config-reference.md) for the
complete settings and event tables.
