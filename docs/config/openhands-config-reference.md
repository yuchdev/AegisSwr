# OpenHands Configuration Reference

Complete, self-service reference for configuring the OpenHands Code Intelligence backend
without reading the Python source. Contract
[C8](/docs/roadmap/0005-harness-backends/plan.md#c8--openhands-backend-contract)
in the Milestone 0005 plan is authoritative; this document transcribes it. If a value
here ever disagrees with C8, **C8 wins**.

For installation and setup, see the [OpenHands setup guide](/docs/config/openhands-setup.md).

## 1. `OpenHandsSettings` fields

All configuration is sourced from environment variables (prefix `OPENHANDS_` unless a
`validation_alias` is listed). Settings are injected into `OpenHandsProcess` and
`OpenHandsTool` at construction — never read from `os.environ` directly inside tool or
process code.

| Field | Env var | Type | Default |
|---|---|---|---|
| `server_url` | `OPENHANDS_SERVER_URL` | `Optional[str]` | `None` (presence signal — backend not registered) |
| `runtime_mode` | `OPENHANDS_RUNTIME` | `str` | `"docker"` (Docker-sandboxed) |
| `allowed_tools` | `OPENHANDS_ALLOWED_TOOLS` | `list[str]` (comma-separated) | `read,grep,glob,browse` |
| `max_response_tokens` | `OPENHANDS_MAX_TOKENS` | `int` | `4096` |
| `connect_timeout_s` | `OPENHANDS_CONNECT_TIMEOUT` | `int` | `10` |
| `request_timeout_s` | `OPENHANDS_REQUEST_TIMEOUT` | `int` | `120` |
| `auto_start` | `OPENHANDS_AUTO_START` | `bool` | `False` |
| `allow_unsandboxed_runtime` | `OPENHANDS_ALLOW_UNSANDBOXED` | `bool` | `False` |

Notes:

- **`server_url=None`** means no `CodeIntelBackend` is registered and the
  code-intelligence capability reports as unavailable (C4). Setting
  `OPENHANDS_SERVER_URL` is the single switch that enables this backend — with no Python
  changes. An empty or whitespace-only value (e.g. an unset CI secret expanding to `""`)
  is treated as unset (`None`), not as a malformed URL.
- **`runtime_mode`** uses the env-var alias `OPENHANDS_RUNTIME` (not
  `OPENHANDS_RUNTIME_MODE`). Accepted values: `"docker"` (sandboxed), `"remote"`
  (sandboxed), `"local"` (non-sandboxed). A blank value coerces to `"docker"` so an
  unset secret never silently selects a non-sandboxed runtime.
- **`max_response_tokens`** is the hard cap on accumulated response length, validated in
  the range `[256, 65536]`. The tool pre-checks the token budget and truncates at this
  cap, flagging truncation in the result metadata (C5).
- **`request_timeout_s`** must be strictly greater than `connect_timeout_s`; construction
  raises `OpenHandsConfigError` when this invariant is violated.
- **`allow_unsandboxed_runtime`** must be `True` before `runtime_mode="local"` is
  accepted; combined with an ADR, this is the only supported path to a non-sandboxed
  runtime (C8).

## 2. Runtime / sandbox default and rationale

### `runtime_mode` — default `"docker"` (Docker-sandboxed)

Aegis SWR treats every incident payload as hostile. The Docker sandbox is therefore the
default runtime: navigation tools execute inside a container with no access to the host
filesystem or network beyond the container boundary.

| Runtime | Sandboxed | When to use |
|---|---|---|
| `docker` | Yes | Default; recommended for all production deployments. |
| `remote` | Yes | OpenHands-managed remote sandbox; suitable for cloud deployments. |
| `local` | **No** | Runs on host OS. Requires `OPENHANDS_ALLOW_UNSANDBOXED=true` and an ADR. |

**Selecting a non-sandboxed runtime without the explicit override raises
`OpenHandsConfigError` at construction.** This is the same fail-closed discipline
applied to the Claude Code `--dangerously-skip-permissions` bypass and the OpenClaude
`bash_allowlist` relaxation.

### `allowed_tools` — default `read,grep,glob,browse`

OpenHands tool names are lowercase (the OpenHands action vocabulary, not Claude Code's
tool set):

| Tool | Why included |
|---|---|
| `read` | Read-only file contents access. |
| `grep` | Read-only content search. |
| `glob` | Read-only path/name matching. |
| `browse` | Read-only web/documentation lookup. |

**Write-capable tools (`edit`, `write`, `run`) are excluded** to preserve the forensic
read-only guarantee. Their inclusion logs a loud warning at settings construction; an ADR
is required to relax the allowlist.

An empty `allowed_tools` value (after coercion) is rejected at construction because it
would widen the runtime's tool access — the inverse of the read-only guard (fails open).
An empty env-var value (`""`) coerces to the default set rather than an empty list.

## 3. Worked `openhands_agent` role YAML (C11)

```yaml
agents:
  # ... other roles ...

  openhands_agent:
    provider: openhands        # required: not routed through LiteLLM
    # LiteLLM model selection is entirely OpenHands'/the operator's concern,
    # set via OpenHands' own configuration. Aegis SWR never resolves a model here.
    model: ~                   # required: YAML null — no LiteLLM model resolved
    timeout_s: 120             # match OpenHandsSettings.request_timeout_s default
    enabled_when: OPENHANDS_SERVER_URL   # role inactive when the var is unset
```

`enabled_when` names an **environment-variable name** (not its value). It is parsed only
by `RouterConfig` — OpenHands is not routed through LiteLLM — and exists to suppress
validation errors when the variable is absent. No `api_key` or secret ever appears on
this role; credentials are OpenHands' own LiteLLM configuration concern.

## 4. Event reference (C10)

All OpenHands events are `frozen=True` dataclasses published on the shared `EventBus`,
carrying `run_id` and a timezone-aware UTC `timestamp`. No field carries raw incident
payload, action arguments, sandbox command lines, or unredacted observation text
(C10/C13).

| Class | `event_type` | When emitted |
|---|---|---|
| `OpenHandsConnected` | `openhands.connected` | After successful health check / sidecar start; carries the server URL (configuration) and lifecycle mode (`"external"` or `"managed"`). |
| `OpenHandsDisconnected` | `openhands.disconnected` | On sidecar teardown or connection loss; carries a short `reason` string only. |
| `OpenHandsAction` | `openhands.action` | On each `Action` event from the stream; carries action kind and argument count (not content). |
| `OpenHandsObservation` | `openhands.observation` | On each `Observation` event from the stream; carries observation kind, success flag, and content byte size (not content). |
| `OpenHandsPermissionDenied` | `openhands.permission_denied` | On a non-allowlisted action/binary; carries action kind and denied binary name only. |
| `OpenHandsCompleted` | `openhands.completed` | On the terminal stream event; the **sole** carrier of the token figure. |
| `OpenHandsError` | `openhands.error` | On a stream error event or transport failure; carries an `error_type` classification and a short status code. |

There is **no** `openhands.auth_failed` event — authentication is OpenHands' own LiteLLM
configuration concern and Aegis SWR has no auth surface for this backend.

### `OpenHandsCompleted` — sole token carrier

`OpenHandsCompleted.token_estimate` is the **sole** carrier of the token figure for the
call (C10). Per C9 the figure is the server-reported real usage when available
(`usage_reported=True`), or the boundary estimate `max(1, len(content) // 4)` when the
server does not report it (`usage_reported=False`). The figure is never duplicated across
other events.

## 5. Cross-links

- Install and setup: [OpenHands setup guide](/docs/config/openhands-setup.md).
- Backend selection contract: [harness-selection.md](/docs/config/harness-selection.md).
- Authoritative contracts and architecture:
  [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md).
