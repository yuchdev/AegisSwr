# 02 - docs/config/openclaude-config-reference.md

**Parent task:** 09.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 01.0 (`OpenClaudeSettings` + `openclaude_agent` role), 05.0 (event taxonomy); documents contracts C1 and C8.
**Blocks:** none

## Objective

Author `docs/config/openclaude-config-reference.md` — the complete, self-service
reference for configuring the OpenClaude backend without reading Python source.
It transcribes the authoritative `OpenClaudeSettings` field table from contract
C1, gives a worked `openclaude_agent` role YAML example, documents the default
tool/`Bash` allowlists with a one-line rationale per default, and reproduces the
full OpenClaude event reference from contract C8.

## File: `docs/config/openclaude-config-reference.md`

Outline (section headings + what each covers):

### 1. `OpenClaudeSettings` field table (from C1)
Transcribe all eight fields exactly — env var, field name, type, default:

| Field | Env var | Type | Default |
|-------|---------|------|---------|
| `grpc_url` | `OPENCLAUDE_GRPC_URL` | `Optional[str]` | `None` (backend not registered) |
| `allowed_tools` | `OPENCLAUDE_ALLOWED_TOOLS` | `list[str]` (comma-separated) | `Read,Grep,Glob,Bash` |
| `bash_allowlist` | `OPENCLAUDE_BASH_ALLOWLIST` | `list[str]` (comma-separated) | `gtags,global,semgrep,rg,find,cat` |
| `max_response_tokens` | `OPENCLAUDE_MAX_TOKENS` | `int` | `4096` |
| `connect_timeout_s` | `OPENCLAUDE_CONNECT_TIMEOUT` | `int` | `10` |
| `request_timeout_s` | `OPENCLAUDE_REQUEST_TIMEOUT` | `int` | `120` |
| `auto_start` | `OPENCLAUDE_AUTO_START` | `bool` | `False` |
| `process_binary` | `OPENCLAUDE_BINARY` | `str` | `openclaude` |

Include the C1 notes column verbatim in prose (e.g. `grpc_url=None` means the
backend is not registered; `max_response_tokens` is the hard streamed-response
cap; `auto_start` selects managed vs external mode).

### 2. Allowlist defaults and rationale
- `allowed_tools` default `Read,Grep,Glob,Bash` — one-line rationale per entry:
  `Read`/`Grep`/`Glob` are read-only navigation; `Bash` is the shell-out surface;
  **write tools are excluded** for forensic read-only safety.
- `bash_allowlist` default `gtags,global,semgrep,rg,find,cat` — one-line rationale
  per binary (symbol DB build, symbol lookup, semantic/pattern search, ripgrep,
  file discovery, file read) and the invariant: OpenClaude cannot execute
  arbitrary shell commands.
- State that any relaxation of either allowlist requires an explicit settings
  override **and an ADR** (C1, C7).

### 3. Worked `openclaude_agent` role YAML example
- A complete `agents.yaml` fragment showing the `openclaude_agent` role with
  `enabled_when: OPENCLAUDE_GRPC_URL` (the non-breaking `RouterConfig` extension
  from Task 01.0), annotated so a reader sees which keys are required.
- Note that `enabled_when` is ignored by the LiteLLM router itself and exists only
  to suppress validation errors when the env var is absent (status.md decision).

### 4. Event reference (from C8)
Reproduce all seven event types — class, `event_type` string, when emitted:

| Class | `event_type` | When emitted |
|-------|--------------|--------------|
| `OpenClaudeConnected` | `openclaude.connected` | After successful health check / process start |
| `OpenClaudeDisconnected` | `openclaude.disconnected` | On process stop or connection loss |
| `OpenClaudeToolCall` | `openclaude.tool_call` | On each `TOOL_CALL` frame from the stream |
| `OpenClaudeToolResult` | `openclaude.tool_result` | On each `TOOL_RESULT` frame from the stream |
| `OpenClaudePermissionDenied` | `openclaude.permission_denied` | On `PERMISSION_REQ` for a disallowed command |
| `OpenClaudeStreamCompleted` | `openclaude.stream_completed` | On `DONE`; carries `token_estimate` |
| `OpenClaudeStreamError` | `openclaude.stream_error` | On `ERROR` frame or gRPC status error |

- Note that `OpenClaudeStreamCompleted` is the sole carrier of the boundary token
  estimate and is never duplicated across events (C5, C8).

### 5. Cross-links
- Link back to `docs/config/openclaude-setup.md` for install (code span here — the target
  is authored in subtask 01 and does not exist until implementation) and to
  [docs/roadmap/0004-code-intelligence/plan.md](/docs/roadmap/0004-code-intelligence/plan.md)
  for the authoritative contracts.

## Implementation notes
- C1 and C8 in plan.md are authoritative; this doc transcribes, it does not
  redefine. If a value here ever disagrees with C1/C8, C1/C8 win — keep them in sync.
- Plain Markdown tables and code fences; no RST `:param:` notation.
- Env var names must match `.env.example` and the C1 table exactly.
- Add the new file to the `docs/README.md` index (coordinate with `docs-updater`).

## Constraints
- Renders with zero broken internal links (`python scripts/check_doc_links.py docs/`).
- Absolute-from-repo-root links with a leading `/`; no relative chains.
- All eight settings fields and all seven event types must be present and match
  the plan.md tables.

## Success criteria
- [ ] `docs/config/openclaude-config-reference.md` created with sections 1–5 above.
- [ ] All eight `OpenClaudeSettings` fields (env var, field, type, default) match C1.
- [ ] Both allowlist defaults documented with a one-line rationale per entry.
- [ ] Worked `openclaude_agent` role YAML example included.
- [ ] All seven C8 events (class, `event_type`, when-emitted) present.
- [ ] `docs/README.md` index links to the new file.
- [ ] `python scripts/check_doc_links.py docs/` passes.
