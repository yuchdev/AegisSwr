# Claude Code Configuration Reference

Complete, self-service reference for configuring the Claude Code backend without reading
the Python source. Contracts
[C6](/docs/roadmap/0005-harness-backends/plan.md#c6--claude-code-backend-contract) and
[C7](/docs/roadmap/0005-harness-backends/plan.md#c7--claude-code-authentication-modes-subscription-login-vs-api-key)
in the Milestone 0005 plan are authoritative; this document transcribes them. If a value
here ever disagrees with C6/C7, **C6/C7 win**.

For installation and setup, see the [Claude Code setup guide](/docs/config/claude-code-setup.md).

## 1. `ClaudeCodeSettings` fields

All configuration is sourced from environment variables (prefix `CLAUDE_CODE_` unless a
`validation_alias` is listed). Settings are injected into `ClaudeCodeProcess` and
`ClaudeCodeTool` at construction — never read from `os.environ` directly inside tool or
process code.

| Field | Env var | Type | Default |
|---|---|---|---|
| `enabled` | `CLAUDE_CODE_ENABLED` | `bool` | `False` (presence signal — backend not registered) |
| `binary_path` | `CLAUDE_CODE_BINARY` | `str` | `"claude"` (resolved via `PATH`) |
| `allowed_tools` | `CLAUDE_CODE_ALLOWED_TOOLS` | `list[str]` (comma-separated) | `Read,Grep,Glob` |
| `max_turns` | `CLAUDE_CODE_MAX_TURNS` | `int` | `8` |
| `request_timeout_s` | `CLAUDE_CODE_REQUEST_TIMEOUT` | `int` | `120` |
| `permission_mode` | `CLAUDE_CODE_PERMISSION_MODE` | `str` | `"default"` |
| `scratch_cwd` | `CLAUDE_CODE_SCRATCH_CWD` | `str` (path) | `None` (mandatory when `enabled`) |
| `auth_mode` | `CLAUDE_CODE_AUTH_MODE` | `"auto"` \| `"api_key"` \| `"subscription"` | `"auto"` |
| `bare` | `CLAUDE_CODE_BARE` | `bool` | `False` (permitted only in `api_key` mode) |

Notes:

- **`enabled=False`** means no `CodeIntelBackend` is registered and the
  code-intelligence capability reports as unavailable (C4). Setting
  `CLAUDE_CODE_ENABLED=true` is the single switch that enables this backend — with no
  Python changes. Being on `PATH` is deliberately **not** a signal.
- **`allowed_tools`** defaults to the read-only set `Read,Grep,Glob`; an empty value
  (e.g. an unset CI secret expanding to `""`) coerces to the default rather than an
  empty allowlist (which would grant unrestricted tool access — fail open).
- **`permission_mode`** accepts `"default"`, `"acceptEdits"`, or `"plan"`. Any
  bypass-permissions value (`bypassPermissions`, `bypass`,
  `--dangerously-skip-permissions`, and equivalents) is **rejected unconditionally at
  construction**, case-insensitively, regardless of `enabled`.
- **`scratch_cwd`** is mandatory when `enabled=True`; must be a path to a creatable,
  writable directory that is neither the repository root nor an ancestor of it. An empty
  env-var value (`""`) coerces to `None` so a zero-config construction never crashes.
- **`bare`** (`CLAUDE_CODE_BARE=true`) may pass `--bare` to the `claude` binary, which
  skips reading OAuth/login credentials. Permitted **only** in `auth_mode="api_key"`;
  rejected at construction in any other mode.

## 2. Read-only allowlist defaults and rationale

### `allowed_tools` — default `Read,Grep,Glob`

| Tool | Why included |
|---|---|
| `Read` | Read-only file contents access. |
| `Grep` | Read-only content search. |
| `Glob` | Read-only path/name matching. |

**Write-capable tools (`Write`, `Edit`) are excluded** to preserve the forensic
read-only guarantee: the Claude Code process must not mutate the repository under
analysis. Unlike the OpenClaude backend, `Bash` is also excluded by default because
Claude Code's tool set is self-contained for navigation without an explicit
`bash_allowlist` guard — the shorter allowlist is the safer default.

Any relaxation of `allowed_tools` beyond the default logs a loud warning (`logger.warning`)
at settings construction. Granting `Write` or `Edit` requires an explicit settings
override **and an ADR** (C1/C7).

The `allowed_tools` comma-separated string in the env var is translated directly to the
`claude` CLI's `--allowedTools` flag. An empty list (after coercion) is rejected at
construction because omitting `--allowedTools` entirely grants the `claude` binary
unrestricted tool access — the inverse of the read-only guard.

### `permission_mode` — default `"default"`

| Accepted value | Behaviour |
|---|---|
| `"default"` | Standard interactive-mode approval flow, non-interactive in practice. |
| `"acceptEdits"` | Auto-accepts file edits without per-edit prompts. |
| `"plan"` | Plan-only: proposes changes without applying them. |

Any bypass-permissions spelling is rejected at construction (see
[§1 table notes](#1-claudecodesettings-fields)).

## 3. `auth_mode` semantics and credential precedence (C7)

### Mode table

| Mode | What it does | `--bare` | Construction-time rejection |
|---|---|---|---|
| `auto` *(default)* | No Aegis-side validation; the `claude` binary resolves whatever credential is present via its own precedence chain. | No | None. |
| `api_key` | Uses `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`. | Yes (opt-in via `CLAUDE_CODE_BARE=true`) | None beyond the env-var name. |
| `subscription` | Uses the Claude.ai OAuth login persisted at `%USERPROFILE%\.claude\.credentials.json` (Windows), or `CLAUDE_CODE_OAUTH_TOKEN`. | Never | Rejects if `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` is set (they outrank the login — see precedence chain). Rejects if `CLAUDE_CODE_BARE=true`. |

`auth_mode` is configured in `ClaudeCodeSettings` (its own env var,
`CLAUDE_CODE_AUTH_MODE`); it does **not** appear in `agents.yaml` — exactly as
OpenClaude's model env vars do not appear in `agents.yaml`.

### Credential precedence chain (Claude Code's own resolution, ranks 1–7)

Aegis SWR reads only **presence** (set and non-empty) for ranks 1–2 when enforcing
`subscription`-mode invariants — never the variable values (C7/C13):

| Rank | Source |
|---|---|
| 1 | `ANTHROPIC_AUTH_TOKEN` (highest — outranks everything) |
| 2 | `ANTHROPIC_API_KEY` |
| 3 | OAuth login session — `%USERPROFILE%\.claude\.credentials.json` (Windows) |
| 4 | `CLAUDE_CODE_OAUTH_TOKEN` environment variable |
| 5–7 | Claude Code internals (browser session, etc.) |

**Why rank 1–2 defeats subscription mode:** the `claude` binary applies this chain
itself; even if `auth_mode="subscription"` is set, a non-empty `ANTHROPIC_API_KEY`
causes the binary to use the API key instead of the OAuth session — silently, without
error. Aegis SWR rejects this combination at construction time to prevent the silent
defeat.

`--bare` is never passed in `subscription` mode because it prevents the binary from
reading OAuth/login credentials at all (C7).

## 4. Worked `claude_code_agent` role YAML (C11)

```yaml
agents:
  # ... other roles ...

  claude_code_agent:
    provider: claude_code      # required: not routed through LiteLLM
    # Claude Code resolves its own model via its credential and the Claude API;
    # Aegis SWR never specifies a model here. auth_mode lives in ClaudeCodeSettings
    # (CLAUDE_CODE_AUTH_MODE), not here — see docs/config/claude-code-setup.md.
    model: ~                   # required: YAML null — no LiteLLM model resolved
    timeout_s: 120             # match ClaudeCodeSettings.request_timeout_s default
    enabled_when: CLAUDE_CODE_ENABLED   # role inactive when the var is unset / false
```

`enabled_when` names an **environment-variable name** (not its value). It is parsed only
by `RouterConfig` and exists to suppress validation errors when the variable is absent.
No `api_key` or secret ever appears on this role.

`auth_mode` is **not** in `agents.yaml`. Configure it via `CLAUDE_CODE_AUTH_MODE` in
the environment, exactly as OpenClaude's model/provider env vars live outside
`agents.yaml`.

## 5. Event reference (C10)

All Claude Code events are `frozen=True` dataclasses published on the shared `EventBus`,
carrying `run_id` and a timezone-aware UTC `timestamp`. No field carries raw incident
payload, tool arguments, response text, argv, or any credential value (C10/C13).

| Class | `event_type` | When emitted |
|---|---|---|
| `ClaudeCodeSpawned` | `claude_code.spawned` | On subprocess spawn; carries `auth_mode` (mode name, never a credential) and configured binary name. |
| `ClaudeCodeExited` | `claude_code.exited` | On subprocess reap; carries a short `reason` string and the exit code. |
| `ClaudeCodeToolCall` | `claude_code.tool_call` | On each tool-use NDJSON message; carries tool name and argument count (not content). |
| `ClaudeCodeToolResult` | `claude_code.tool_result` | On each tool-result NDJSON message; carries tool name, success flag, and result byte size (not content). |
| `ClaudeCodePermissionDenied` | `claude_code.permission_denied` | On a disallowed tool/binary; carries tool name and denied binary name only. |
| `ClaudeCodeAuthFailed` | `claude_code.auth_failed` | On auth-probe or credential failure (C7); carries `reason` (fixed vocabulary) and `auth_mode` — **never** a credential. |
| `ClaudeCodeCompleted` | `claude_code.completed` | On the terminal NDJSON `result` message; the **sole** carrier of the token figure. |
| `ClaudeCodeError` | `claude_code.error` | On spawn/parse/timeout/non-zero-exit failure; carries an `error_type` classification and a short status code. |

### `ClaudeCodeCompleted` — sole real-usage token carrier

`ClaudeCodeCompleted.token_estimate` is the **real** token count
(`usage.input_tokens + usage.output_tokens`) reported by the `claude` binary's terminal
`result` message (C9) — the actual count charged to the budget, not a boundary estimate.
This is a gain over the OpenClaude backend's boundary estimate. The figure is never
duplicated across other events.

### `ClaudeCodeAuthFailed` — reason vocabulary

| `reason` | Meaning |
|---|---|
| `ambiguous_credential` | An outranking API-key credential (`ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`) was present under `subscription` mode — already rejected at construction but defensively emitted if reached at delegation time. |
| `no_stored_login` | `subscription` mode; no usable OAuth session and no `CLAUDE_CODE_OAUTH_TOKEN`. |
| `token_rejected` | The resolved credential was rejected by the auth-probe. |

The event carries only the reason string and the attempted `auth_mode` — **never** the
credential or token value (C7/C13).

## 6. Cross-links

- Install and setup: [Claude Code setup guide](/docs/config/claude-code-setup.md).
- Backend selection contract: [harness-selection.md](/docs/config/harness-selection.md).
- Authoritative contracts and architecture:
  [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md).
