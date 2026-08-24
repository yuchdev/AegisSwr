# 01 - Claude Code docs (setup + config reference)

**Parent task:** 13.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 02.0 (`ClaudeCodeSettings`), 03.0 (one-shot subprocess tool + NDJSON parse + real tokens), 04.0 (`auth_mode` + auth-probe, C7), 05.0 (`claude_code.*` event taxonomy, C10); documents behaviour delivered by those tasks.
**Blocks:** none

## Objective

Author the operator-facing Claude Code documentation pair, mirroring the shipped
OpenClaude pair section-for-section:

- `docs/claude-code-setup.md` — mirrors [`docs/openclaude-setup.md`](/docs/openclaude-setup.md);
  lets an operator with the installed `claude` CLI stand up code intelligence by
  setting a single presence signal (`CLAUDE_CODE_ENABLED=true`) plus a resolvable
  credential, with **zero Python changes** (C4). It documents **both C7 auth
  modes** (`api_key` and `subscription`, with `auto` as the default) and states
  the **C7 licensing caveat** explicitly.
- `docs/claude-code-config-reference.md` — mirrors
  [`docs/openclaude-config-reference.md`](/docs/openclaude-config-reference.md);
  transcribes the `ClaudeCodeSettings` field table (C6/C7), the `auth_mode`
  semantics and precedence chain (C7), the read-only allowlist defaults (C6), the
  worked `claude_code_agent` role YAML (C11), and the `claude_code.*` event
  reference (C10).

## File: `docs/claude-code-setup.md` (mirrors `docs/openclaude-setup.md`)

Outline (section headings map 1:1 to the OpenClaude setup guide):

### 1. Overview
- Claude Code is **one selectable Code Intelligence backend** (not the sole one):
  reached via the installed `claude` CLI, spawned as a **one-shot subprocess per
  `delegate()`** (no persistent sidecar) — call out this contrast with
  OpenClaude's long-lived gRPC sidecar.
- Enable with a single presence signal `CLAUDE_CODE_ENABLED=true` (explicit
  opt-in; being on `PATH` is deliberately **not** a signal) plus a resolvable
  credential, and zero Python changes.
- Link to [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md),
  to `docs/claude-code-config-reference.md` (code span — authored in the same
  subtask), and to [`docs/harness-selection.md`](/docs/harness-selection.md) for
  how selection among backends works (C2).

### 2. Prerequisites
- The installed **`claude` CLI** on the host `PATH` (or an explicit
  `CLAUDE_CODE_BINARY` path). Aegis SWR does not vendor or install it.
- One resolvable credential (see §5): an API key/Console token, or a Claude.ai
  subscription login / `CLAUDE_CODE_OAUTH_TOKEN`.
- Note: unlike OpenHands, **no Docker** is required; unlike OpenClaude, **no
  Node.js/npm** and no gRPC stubs. Absence of the binary / unset presence signal
  simply means this backend is unavailable, not an error.

### 3. Enabling the backend (presence signal + selection)
- Set `CLAUDE_CODE_ENABLED=true` (the presence signal, C2/C6).
- Selection: if `AEGIS_CODE_INTEL_BACKEND` is unset and this is the **only**
  presence signal set, Claude Code is auto-selected; set
  `AEGIS_CODE_INTEL_BACKEND=claude_code` to select it explicitly. More than one
  signal without the selector is a `HarnessConfigError` (point at
  `docs/harness-selection.md`).
- **Verification** with `aegis code-intel check` (backend-agnostic, C4): show the
  expected `--dry-run` (default) output reporting the backend registered as
  Claude Code and the resolved auth mode, and the `--no-dry-run` path that runs
  the C7 startup auth-probe. Mirror the OpenClaude guide's verification block.

### 4. Read-only / permission posture
- Runs with **host OS permissions** (no sandbox) — same residual-risk class as
  OpenClaude. Guards: `allowed_tools` (→ `--allowedTools`, default read-only
  `Read,Grep,Glob`), a non-bypassing `permission_mode`, and a **mandatory
  disposable scratch cwd** (C6).
- State plainly that `--dangerously-skip-permissions` (and any setting producing
  it) is **rejected at settings-validation time** — mirror OpenClaude's
  allowlist-relaxation-needs-an-ADR discipline.
- **Argv-safety note:** task text is passed via stdin/temp file, never argv
  (visible via `ps` on a shared host) (C6).

### 5. Authentication modes (C7) — the section with no OpenClaude analogue
- A short callout: unlike OpenClaude (which treats the model provider as entirely
  the operator's concern), Claude Code has its **own dual credential surface**,
  and Aegis SWR exposes an explicit `auth_mode` so the choice is not left to
  ambient environment.
- Table of the three modes:
  - `auto` (default) — no extra validation; whichever credential the `claude`
    binary resolves per its precedence chain wins. Simplest for an operator whose
    `claude` already works.
  - `api_key` — uses `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`; `--bare` may be
    added for reproducibility.
  - `subscription` — Claude Pro/Max/Team/Enterprise login. Established via
    interactive `claude login` (persists to
    `%USERPROFILE%\.claude\.credentials.json` on **Windows**, Aegis SWR's target)
    or the CI-friendly `claude setup-token` → long-lived `CLAUDE_CODE_OAUTH_TOKEN`.
    Rejects construction when `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` is present
    (they would silently outrank the login); never passes `--bare`; health-checks
    a stored login before the first `delegate()`.
- Reproduce (abridged) the credential precedence chain from C7 so an operator
  understands *why* a stray `ANTHROPIC_API_KEY` defeats subscription mode.
- Corporate/Enterprise SSO note: identical OAuth mechanism to personal login;
  `forceLoginMethod`/`forceLoginOrgUUID` are the operator's own Claude Code
  managed-settings concern, not configured by Aegis SWR.

### 5a. Licensing caveat (REQUIRED — explicit callout box)
- A blockquote/warning callout, verbatim in intent from C7: **no explicit
  Anthropic ToS language was found distinguishing personal (Pro/Max) from
  organizational (Team/Enterprise) seats for non-interactive production automation
  at scale.** Confirm with Anthropic (sales/legal) before using
  `auth_mode="subscription"` in a production deployment. Pending confirmation,
  `subscription` ships opt-in only; the default `auto` does not force the question.
  Do **not** present `subscription` as the recommended default automation path.

### 6. Troubleshooting
- **Auth failure** (`ClaudeCodeUnavailableError` from the startup probe /
  `claude_code.auth_failed` event, C7): distinguish from `ClaudeCodeConfigError`
  (settings-shape, e.g. the rejected `ANTHROPIC_API_KEY`-under-`subscription`
  case). Diagnostic sequence for each `auth_failed` reason
  (`ambiguous_credential`, `no_stored_login`, `token_rejected`) — **without ever
  printing the credential value**.
- **Permission denied** (`claude_code.permission_denied`): a tool outside
  `--allowedTools` was exercised; by-design read-only guarantee.
- **Binary not found / wrong `CLAUDE_CODE_BINARY`**; **timeout**
  (`request_timeout_s`).

## File: `docs/claude-code-config-reference.md` (mirrors `docs/openclaude-config-reference.md`)

Outline (section headings map 1:1 to the OpenClaude config reference):

### 1. `ClaudeCodeSettings` fields (from C6/C7)
Transcribe the field table exactly (env prefix `CLAUDE_CODE_`):

| Field | Env var | Type | Default |
|-------|---------|------|---------|
| `enabled` | `CLAUDE_CODE_ENABLED` | `bool` | `False` (presence signal — backend not registered) |
| `binary_path` | `CLAUDE_CODE_BINARY` | `str` | `claude` |
| `allowed_tools` | `CLAUDE_CODE_ALLOWED_TOOLS` | `list[str]` (comma-separated) | `Read,Grep,Glob` (read-only) |
| `permission_mode` | `CLAUDE_CODE_PERMISSION_MODE` | `str` | a non-bypassing mode (rejects any bypass value) |
| `max_turns` | `CLAUDE_CODE_MAX_TURNS` | `int` | (per Task 03.0) |
| `request_timeout_s` | `CLAUDE_CODE_REQUEST_TIMEOUT` | `int` | (per Task 03.0) |
| `scratch_cwd` | `CLAUDE_CODE_SCRATCH_CWD` | `str` (mandatory, disposable) | (per Task 02.0) |
| `auth_mode` | `CLAUDE_CODE_AUTH_MODE` | `str` (`auto`\|`api_key`\|`subscription`) | `auto` |

Include the notes in prose: `enabled=False` means backend not registered;
`allowed_tools` write tools default off; `--dangerously-skip-permissions` rejected
at validation; `scratch_cwd` mandatory-disposable.

### 2. Read-only allowlist defaults and rationale
- One-line rationale per default `allowed_tools` entry (`Read`/`Grep`/`Glob` =
  read-only navigation; **no `Bash`**, unlike OpenClaude — Claude Code's tool set
  differs), the invariant that write tools are excluded, and the ADR requirement
  to relax it. Explain `permission_mode`'s non-bypassing default.

### 3. `auth_mode` semantics and credential precedence (from C7)
- Table of the three modes and what each validates (mirror §5 of the setup guide,
  reference-density). Reproduce the full 7-rank precedence chain and the reason
  rank 3 (`ANTHROPIC_API_KEY`) silently outranks the login. Note `--bare` is never
  passed in `subscription` mode and never reads OAuth credentials.

### 4. Worked `claude_code_agent` role YAML (from C11)
- A complete `agents.yaml` fragment: `provider: claude_code`, `model: ~` (no
  LiteLLM model resolved), `timeout_s` matching `request_timeout_s`,
  `enabled_when: CLAUDE_CODE_ENABLED`. A comment naming **both** C7 auth modes and
  pointing at `docs/claude-code-setup.md`. Note `auth_mode` is **not** in
  `agents.yaml` — it lives in `ClaudeCodeSettings` (its own env var), exactly like
  OpenClaude's model env vars.

### 5. Event reference (from C10)
Reproduce the `claude_code.*` events — class, `event_type`, when emitted:

| Concept | `event_type` | When emitted |
|---------|--------------|--------------|
| Process up | `claude_code.spawned` | On subprocess spawn |
| Process down | `claude_code.exited` | On subprocess reap |
| Tool invocation | `claude_code.tool_call` | On a tool-call NDJSON message |
| Tool result | `claude_code.tool_result` | On a tool-result NDJSON message |
| Permission denied | `claude_code.permission_denied` | On a disallowed tool |
| Auth failure | `claude_code.auth_failed` | On auth-probe/credential failure (C7) |
| Stream completed | `claude_code.completed` | On terminal `result`; carries **real** `token_estimate` |
| Stream error | `claude_code.error` | On stream/subprocess error |

- Note `claude_code.completed` is the **sole** carrier of the token figure, and
  that the figure is the **real** `usage.input_tokens + usage.output_tokens` sum
  (C9), a gain over OpenClaude's boundary estimate. Note `claude_code.auth_failed`
  carries **only** the failure reason, never a credential/token value (C7/C13).

### 6. Cross-links
- Back to `docs/claude-code-setup.md` (code span), to
  [`docs/harness-selection.md`](/docs/harness-selection.md), and to the
  [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md).

## Implementation notes
- Plain Markdown tables and fenced code blocks; no RST `:param:` notation (that is
  for docstrings only).
- All env var names must match `.env.example` and the C1/C6/C7 tables exactly.
- Do not paste real credentials, tokens, or an API key — use placeholders. The
  OAuth token and credential-file contents must never appear in any example output.
- C6/C7/C9/C10/C11 in [plan.md](/docs/roadmap/0005-harness-backends/plan.md) are authoritative; this doc transcribes — if a value
  disagrees, the contract wins.
- Add both new files to the `docs/README.md` index (coordinate with `docs-updater`).

## Constraints
- Section-for-section parity with the OpenClaude pair; differ only in per-backend
  facts.
- The licensing caveat (§5a of the setup guide) is **mandatory** and must not be
  softened or omitted; `subscription` must not be presented as the default.
- Renders with zero broken internal links (`python scripts/check_doc_links.py docs/`).
- Absolute-from-repo-root links with a leading `/`; no relative `../../` chains.
- No design in these docs may cause a credential, token, or incident payload to be
  logged or persisted unredacted (C7, C13).

## Success criteria
- [ ] `docs/claude-code-setup.md` created with sections 1–6 (incl. 5, 5a) above,
      mirroring `docs/openclaude-setup.md`.
- [ ] Both C7 auth modes documented, with `auto` stated as the default.
- [ ] The C7 licensing caveat is present as an explicit callout and recommends
      confirming with Anthropic before production `subscription` use.
- [ ] Argv-safety and the `--dangerously-skip-permissions` rejection are stated.
- [ ] `docs/claude-code-config-reference.md` created with sections 1–6 above,
      mirroring `docs/openclaude-config-reference.md`.
- [ ] All `ClaudeCodeSettings` fields (incl. `auth_mode`) match C6/C7.
- [ ] Worked `claude_code_agent` role YAML with `enabled_when: CLAUDE_CODE_ENABLED`
      included; `auth_mode` noted as living in settings, not `agents.yaml`.
- [ ] All `claude_code.*` events (incl. `auth_failed`) present; `completed` noted
      as the sole real-`usage` token carrier.
- [ ] Both files linked from `docs/README.md`.
- [ ] `python scripts/check_doc_links.py docs/` passes.
