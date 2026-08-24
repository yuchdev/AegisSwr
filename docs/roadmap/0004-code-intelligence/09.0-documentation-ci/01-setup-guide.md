# 01 - docs/config/openclaude-setup.md

**Parent task:** 09.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 03.0 (process lifecycle / external + managed modes), 04.0 (`OpenClaudeTool` + dry-run), 06.0 (`app.py` wiring + `--dry-run`); documents behaviour delivered by those tasks.
**Blocks:** none

## Objective

Author `docs/config/openclaude-setup.md` — the operator-facing install and setup guide
for wiring an OpenClaude sidecar into Aegis SWR. It must let an operator who runs
a local or self-hosted OpenAI-compatible endpoint stand up code intelligence with
a single environment variable and zero Python changes (C4), covering both the
default **external** mode and the **managed** (`auto_start`) mode, the required
tool/`Bash` allowlist launch flags (C7), and troubleshooting for the two failure
classes an operator will actually hit: health-check failure and allowlist denial.

## File: `docs/config/openclaude-setup.md`

Outline (section headings + what each covers):

### 1. Overview
- One paragraph: OpenClaude is the sole Code Intelligence backend (C4); it runs
  as a headless gRPC sidecar; Aegis SWR delegates one open-ended task and consumes
  the response stream. Link to
  [docs/roadmap/0004-code-intelligence/plan.md](/docs/roadmap/0004-code-intelligence/plan.md)
  for the architecture and to `docs/config/openclaude-config-reference.md` for the full
  settings table (this cross-link is authored in subtask 02; the target file does
  not exist until implementation, so it is a code span here, not a live link).

### 2. Prerequisites
- Node.js + npm on the host. Install the OpenClaude CLI globally:
  `npm install -g @gitlawb/openclaude@latest` (per Task 01.0 Assumptions).
  OpenClaude is treated as an opaque, versioned black-box service reached
  over gRPC (C2) — nothing in this repository vendors or builds it.
- `poetry install` runs this npm install automatically via a build-script
  hook (`scripts/postinstall_openclaude.py`, Task 01.0 subtask 01), so a
  fresh Python environment setup is normally sufficient on a machine that
  already has Node.js/npm. The hook logs a warning and does not fail
  `poetry install` when npm is absent — run the `npm install -g` command
  above by hand in that case before using managed mode.
- Optional navigation CLIs on `PATH` inside the sidecar's environment
  (`gtags`, `global`, `semgrep`, `rg`, `find`, `cat`) — these are what OpenClaude
  shells out to via the `Bash` tool; absence degrades navigation quality but does
  not break startup.
- Note: Aegis SWR itself needs no OpenClaude Python dependency beyond the
  committed gRPC stubs; a missing binary/unset URL simply means code-intel is
  unavailable, not an error.

### 3. External mode (default, `auto_start=false`)
- The operator starts OpenClaude themselves as a long-lived headless gRPC server.
- **Required allowlist launch flags** the operator must pass (C7): the tool
  allowlist restricting OpenClaude to `Read,Grep,Glob,Bash` and the `Bash` binary
  allowlist restricting it to `gtags,global,semgrep,rg,find,cat`. State that these
  must match `OPENCLAUDE_ALLOWED_TOOLS` / `OPENCLAUDE_BASH_ALLOWLIST` so the
  startup probe (C7) does not raise `OpenClaudeUnavailableError`.
- Point `OPENCLAUDE_GRPC_URL` at the running server.
- **Verification:** `python -m aegis.app --dry-run` with `OPENCLAUDE_GRPC_URL`
  set — confirm it reports the backend as registered and does *not* open a gRPC
  connection (C5 item 3, acceptance criterion). Show expected output.

### 4. Managed mode (`auto_start=true`)
- Set `OPENCLAUDE_AUTO_START=true` and `OPENCLAUDE_BINARY` to the binary name or
  full path of the built entrypoint.
- Aegis SWR launches the sidecar as a subprocess, passes the allowlist flags
  itself (C7 — operator does not supply them), waits for the port, and terminates
  it on exit (C6). Note SIGTERM-then-SIGKILL shutdown and that stderr is forwarded
  to the logger at DEBUG only.
- When to prefer managed vs external (lifecycle ownership, restart semantics).

### 5. User-supplied model contract (OpenClaude's own env vars)
- Explicit callout box: the following are **OpenClaude's own environment
  variables, not Aegis SWR settings** — Aegis SWR never reads them and only needs
  `OPENCLAUDE_GRPC_URL`:
  - `CLAUDE_CODE_USE_OPENAI`
  - `OPENAI_BASE_URL`
  - `OPENAI_MODEL`
  - `OPENAI_API_KEY`
- Note the tool-quality caveat: small local models struggle with long multi-step
  flows (plan.md "User-supplied model contract"). Link to OpenClaude's upstream
  docs for provider configuration.

### 6. Troubleshooting
- **Health-check failure** (`OpenClaudeUnavailableError` at startup): endpoint
  unreachable, wrong `OPENCLAUDE_GRPC_URL`, sidecar not built, port not open
  within `connect_timeout_s`. Give the diagnostic sequence (verify the server is
  listening, verify URL, raise `connect_timeout_s`).
- **Allowlist-denial error** (`PermissionDeniedError` / `OpenClaudePermissionDenied`,
  or `OpenClaudeUnavailableError` from the startup probe): a tool or `Bash` binary
  was exercised outside the allowlist. Explain that this is by design (read-only
  forensic guarantee), how to confirm the launch flags match the settings, and
  that widening the allowlist requires a settings override **and an ADR** (C1/C7).

## Implementation notes
- Use plain Markdown tables and fenced code blocks; no RST `:param:` notation
  (that is for docstrings only).
- All env var names must match `.env.example` and the C1 table exactly.
- Do not paste real credentials or a real vLLM URL — use placeholders.
- Add the new file to the `docs/README.md` index (coordinate with `docs-updater`).

## Constraints
- Renders with zero broken internal links (`python scripts/check_doc_links.py docs/`).
- Absolute-from-repo-root links with a leading `/`; no relative `../../` chains.
- Must make unmistakably clear that the four `OPENAI_*` / `CLAUDE_CODE_*` vars are
  OpenClaude's, not Aegis SWR's.
- No design in this doc may cause secrets or incident payloads to be logged.

## Success criteria
- [ ] `docs/config/openclaude-setup.md` created with sections 1–6 above.
- [ ] External-mode section states the exact allowlist launch flags and the
      `python -m aegis.app --dry-run` verification step.
- [ ] Managed-mode section documents `OPENCLAUDE_AUTO_START=true` + `OPENCLAUDE_BINARY`.
- [ ] The four operator-supplied model env vars are documented with an explicit
      "these are OpenClaude's, not Aegis SWR's" note.
- [ ] Troubleshooting covers both health-check failure and allowlist denial.
- [ ] `docs/README.md` index links to the new file.
- [ ] `python scripts/check_doc_links.py docs/` passes.
