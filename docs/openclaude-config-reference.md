# OpenClaude Configuration Reference

Complete, self-service reference for configuring the OpenClaude Code Intelligence
backend without reading the Python source. Contracts
[C1](/docs/roadmap/0004-code-intelligence/plan.md#c1--openclaude-settings) and
[C8](/docs/roadmap/0004-code-intelligence/plan.md#c8--openclaude-event-taxonomy)
in the milestone plan are authoritative; this document transcribes them. If a
value here ever disagrees with C1/C8, **C1/C8 win**.

For installation and setup, see the [OpenClaude setup guide](/docs/openclaude-setup.md).

## 1. `OpenClaudeSettings` fields

All configuration is sourced from environment variables (prefix
`OPENCLAUDE_`). Settings are injected into `OpenClaudeProcess` and
`OpenClaudeTool` at construction — never read from `os.environ` directly inside
tool or process code.

| Field                 | Env var                      | Type                          | Default                            |
|-----------------------|------------------------------|-------------------------------|------------------------------------|
| `grpc_url`            | `OPENCLAUDE_GRPC_URL`        | `Optional[str]`               | `None` (backend not registered)    |
| `allowed_tools`       | `OPENCLAUDE_ALLOWED_TOOLS`   | `list[str]` (comma-separated) | `Read,Grep,Glob,Bash`              |
| `bash_allowlist`      | `OPENCLAUDE_BASH_ALLOWLIST`  | `list[str]` (comma-separated) | `gtags,global,semgrep,rg,find,cat` |
| `max_response_tokens` | `OPENCLAUDE_MAX_TOKENS`      | `int`                         | `4096`                             |
| `connect_timeout_s`   | `OPENCLAUDE_CONNECT_TIMEOUT` | `int`                         | `10`                               |
| `request_timeout_s`   | `OPENCLAUDE_REQUEST_TIMEOUT` | `int`                         | `120`                              |
| `auto_start`          | `OPENCLAUDE_AUTO_START`      | `bool`                        | `False`                            |
| `process_binary`      | `OPENCLAUDE_BINARY`          | `str`                         | `openclaude`                       |

Notes:

- **`grpc_url = None`** means no `CodeIntelBackend` is registered and the
  code-intelligence capability reports as unavailable (C4). Setting it is the
  single switch that enables OpenClaude — with no Python changes.
- **`max_response_tokens`** is the hard cap on streamed response length;
  accumulated content is truncated at this ceiling, and truncation is flagged in
  the result metadata (C5).
- **`connect_timeout_s`** bounds the gRPC channel connect / managed-mode
  port-open wait; **`request_timeout_s`** is the per-request stream deadline (and
  must exceed `connect_timeout_s`).
- **`auto_start`** selects managed mode (`True`, Aegis SWR launches and
  supervises the sidecar) vs. external mode (`False`, default, Aegis SWR only
  health checks a pre-running sidecar).
- **`process_binary`** is the binary name (resolved via `PATH`) or a full path to
  the OpenClaude executable, used in managed mode.
- A related field, `use_tls` (`OPENCLAUDE_USE_TLS`, default `False`), selects a
  secure gRPC channel; leave it `False` for a locally co-located sidecar and
  enable it for a remote endpoint so prompts are not sent in cleartext.

## 2. Allowlist defaults and rationale

### `allowed_tools` — default `Read,Grep,Glob,Bash`

| Tool   | Why                                                                              |
|--------|----------------------------------------------------------------------------------|
| `Read` | Read-only file contents access.                                                  |
| `Grep` | Read-only content search.                                                        |
| `Glob` | Read-only path/name matching.                                                    |
| `Bash` | The shell-out surface for the navigation CLIs (constrained by `bash_allowlist`). |

**Write tools (`Write`, `Edit`, …) are excluded** for the forensic read-only
guarantee: OpenClaude must not mutate the repository under analysis.

### `bash_allowlist` — default `gtags,global,semgrep,rg,find,cat`

| Binary    | Why                                  |
|-----------|--------------------------------------|
| `gtags`   | Build a GNU GLOBAL symbol database.  |
| `global`  | Symbol lookup against that database. |
| `semgrep` | Semantic / pattern search.           |
| `rg`      | ripgrep fast content search.         |
| `find`    | File discovery.                      |
| `cat`     | File read.                           |

The `bash_allowlist` is the invariant that OpenClaude **cannot execute arbitrary
shell commands** — only these binaries. Any relaxation of either allowlist
requires an explicit settings override **and an ADR** (C1 / C7).

## 3. Worked `openclaude_agent` role

The `openclaude_agent` role in `agents.yaml` is gated by `enabled_when`, a
non-breaking `RouterConfig` extension:

```yaml
agents:
  # ... other roles ...

  openclaude_agent:
    provider: openclaude        # required: not routed through LiteLLM
    # Model selection is entirely OpenClaude's / the operator's concern, set via
    # OpenClaude's own env vars (CLAUDE_CODE_USE_OPENAI, OPENAI_BASE_URL,
    # OPENAI_MODEL, OPENAI_API_KEY). Aegis SWR never resolves a model here.
    model: ~                    # required: YAML null - no LiteLLM model resolved
    timeout_s: 120              # matches OpenClaudeSettings.request_timeout_s default
    enabled_when: OPENCLAUDE_GRPC_URL   # role inactive when the var is unset
```

`enabled_when` names an **environment-variable name** (not its value). It is
ignored by the LiteLLM router itself — OpenClaude is not routed through LiteLLM —
and exists only to suppress validation errors when the variable is absent. No
`api_key` or secret ever appears on this role; credentials are the operator's,
set on the OpenClaude process.

## 4. Event reference

All OpenClaude events are `frozen=True` dataclasses published on the shared
`EventBus`, carrying `run_id` and a UTC `timestamp`.

| Class                        | `event_type`                   | When emitted                                  |
|------------------------------|--------------------------------|-----------------------------------------------|
| `OpenClaudeConnected`        | `openclaude.connected`         | After successful health check / process start |
| `OpenClaudeDisconnected`     | `openclaude.disconnected`      | On process stop or connection loss            |
| `OpenClaudeToolCall`         | `openclaude.tool_call`         | On each `TOOL_CALL` frame from the stream     |
| `OpenClaudeToolResult`       | `openclaude.tool_result`       | On each `TOOL_RESULT` frame from the stream   |
| `OpenClaudePermissionDenied` | `openclaude.permission_denied` | On `PERMISSION_REQ` for a disallowed command  |
| `OpenClaudeStreamCompleted`  | `openclaude.stream_completed`  | On `DONE`; carries `token_estimate`           |
| `OpenClaudeStreamError`      | `openclaude.stream_error`      | On `ERROR` frame or gRPC status error         |

`OpenClaudeStreamCompleted` is the **sole** carrier of the boundary token
estimate; it is never duplicated across events (C5 / C8).

## 5. Cross-links

- Install and setup: [OpenClaude setup guide](/docs/openclaude-setup.md).
- Authoritative contracts and architecture:
  [Milestone 0004 plan](/docs/roadmap/0004-code-intelligence/plan.md).
