# Threat Model - OpenClaude gRPC Proto & Client (Task 02.0) - 2026-07-08

Milestone 0004, Task 02.0. Reviewer: security-auditor.

## Assets & trust boundaries

- **Assets protected**: incident-payload text (crash-forensics context that may
  embed secrets/PII per `.claude/CLAUDE.md` §1/§3), the prompt sent to the
  sidecar, and the streamed response `content`.
- **Boundary C3 (the only gRPC boundary in the codebase)**:
  `OpenClaudeGrpcClient` <-> out-of-process OpenClaude sidecar over gRPC.
  - Outbound: `PromptRequest{prompt, run_id}` (prompt may embed hostile/sensitive
    forensic context).
  - Inbound: server-streamed `AgentMessage{type, content, tool}` frames. The
    sidecar is **semi-trusted** - a compromised/misbehaving sidecar can send
    hostile frames (unspecified types, unterminated streams, oversized content).
- **Files in scope**: `src/aegis_swr/openclaude/grpc/client.py`,
  `src/aegis_swr/openclaude/exceptions.py`,
  `src/aegis_swr/openclaude/grpc/proto/openclaude.proto` (+ generated stubs).
- **Out of scope (pre-approved)**: forward-declared exceptions module (Task 05.0
  owns canonical), `settings.use_tls` reconciliation, package-qualified stub
  generation, dep CVE audit (ran CLEAN separately).

## Findings

### [MEDIUM] Plaintext prompt transmission possible for a non-loopback sidecar (CWE-319)
- Vector / evidence: `client.py:154-159` selects `insecure_channel` whenever
  `settings.use_tls` is false; `config.py:151` defaults `use_tls=False`. The
  `grpc_url` validator (`config.py:198-215`, pattern `^[a-zA-Z0-9.\-]+(:[0-9]+)?`)
  accepts **any** host, not just loopback. Nothing couples "remote host" to
  "TLS required," and no warning fires when a non-loopback `grpc_url` runs
  insecure.
- Impact: an operator who points `grpc_url` at a remote/non-loopback sidecar
  while leaving `use_tls=False` sends prompts - which embed attacker-influenced
  incident payload and possible secrets/PII - in cleartext, exposing them to
  on-path (MITM) disclosure. This is a latent config foot-gun, not the default
  loopback path.
- Mitigation: emit a `logger.warning` (payload-free) or reject at config time
  when `grpc_url` host is not loopback (`localhost`/`127.0.0.1`/`::1`/unix) and
  `use_tls` is false; and document in the operator runbook that remote sidecars
  MUST enable TLS. Insecure-by-default for a co-located loopback sidecar is
  acceptable; insecure-by-default for a remote one is not.

### [LOW] No explicit inbound message-size / response-length cap in the client (CWE-770 / CWE-400)
- Vector / evidence: channel is created with no `options`
  (`client.py:156,159`; generated stub `options=()`), so per-message size relies
  on the gRPC default (~4 MiB). `query()` (`client.py:210-215`) yields frames
  lazily with no total-stream byte/frame cap, and `settings.max_response_tokens`
  (`config.py:146`) is **not referenced anywhere in the gRPC client** (confirmed
  by grep).
- Impact: a compromised sidecar can stream a large volume of frames within the
  `request_timeout_s` window (default 120s). Buffering risk is bounded because
  frames are yielded (backpressure to the caller), and the per-request gRPC
  deadline caps duration - so this fails safe on time - but the client does not
  itself enforce the documented response-length hard cap.
- Mitigation: set explicit `grpc.max_receive_message_length` on the channel and
  enforce `max_response_tokens` at the aggregation layer (or here). Confirm the
  downstream consumer (later task) enforces the cap; if it does, downgrade to
  informational.

### [LOW] Health probe reuses the full agent-loop `Query` RPC; docstring overstates the client-side guarantee
- Vector / evidence: `_probe()` (`client.py:266-268`) sends `_HEALTH_PROBE_PROMPT`
  through the same `AgentService.Query` RPC an ordinary task uses; the proto
  exposes only `Query` (`openclaude.proto:41-45`). The docstring/comment
  (`client.py:83-84`) asserts the probe "never reaches a shell or a tool" - that
  is a **server-side** behavior the client cannot enforce.
- Impact: readiness probing invokes the sidecar's full agent loop server-side;
  a compromised/misconfigured sidecar could act on "ping." No client-side vuln
  and no operator-poisoning path (the probe string is a module constant, not
  config-derived - good), but the comment claims a guarantee it does not own.
- Mitigation: reword the comment to scope the guarantee to the client
  (constant, inert prompt, bounded timeout); consider a dedicated lightweight
  health RPC in a future proto revision. `health_check` correctly never raises
  and is double-bounded by `asyncio.wait_for` + gRPC `timeout=` (`client.py:303`).

### [LOW/INFO] Abandoned async-generator stream relies on `close()` for RPC cancellation
- Vector / evidence: `query()` is an async generator (`client.py:183-222`); a
  caller that breaks out early without draining relies on `close()`
  (`client.py:314-325`) / channel teardown to cancel the underlying `call`.
- Impact: minor resource-leak window if a caller abandons the iterator and never
  calls `close()`/exits the `async with`. The `__aexit__` path mitigates for
  context-manager users.
- Mitigation: document that callers must use the async-context-manager form, or
  wrap the RPC to cancel on generator close. Informational.

## Positive controls verified

- **C9 no-leak (defining risk): PASS.** Every `logger.debug` sink logs only
  static text, the config `grpc_url`, timeouts, or `exc.code()` (the gRPC
  `StatusCode`) - never `msg.content`, the prompt, `run_id`-correlated payload,
  or frame text (`client.py:155,158,179,205,217,221,275,278,281,305,311,322`).
  Crucially the code uses `exc.code()` and **never** `exc.details()` /
  `debug_error_string` / metadata (grep-confirmed), so no server-supplied text
  echoes into a log or exception.
- **Exception hygiene: PASS.** `_translate_status` (`client.py:231-252`) carries
  only `code.name` + a `retriable` flag; `OpenClaudeUnavailableError`
  (`exceptions.py:49-60`) holds `grpc_url` (bare host:port config, scheme-rejected
  by `config.py:205-214` - not secret-bearing) and `status_code` name. No payload
  rides along. The unspecified-frame raise (`client.py:180`) uses a static message,
  not `msg.content`. Not relying on `SensitiveFilter` as a substitute for
  not-logging.
- **Untrusted-frame fail-safe: PASS.** Unknown/`FRAME_TYPE_UNSPECIFIED` frames
  raise a terminal domain error (`client.py:177-181`); an unterminated stream
  raises after the loop via `terminal_seen` (`client.py:220-222`); all paths are
  bounded by the gRPC `timeout=` deadline and (for the probe) `asyncio.wait_for`.
  No infinite iteration or self-buffering; frames are yielded with backpressure.
- **No injection sink: PASS.** Streamed `content` is only projected onto the
  frozen `AgentFrame` dataclass (`client.py:165-181`). Nothing in this diff routes
  content to a shell, SQL, `eval`, or an onward AI prompt.
- **Health-probe poisoning: PASS.** `_HEALTH_PROBE_PROMPT` is a module constant
  (`client.py:85`); not operator-configurable.

## Verdict: PASS_WITH_FOLLOWUP

No CRITICAL findings, so merge is **not** blocked. The defining C9
payload/secret-leakage risk is cleanly handled. One MEDIUM (CWE-319 cleartext
for a remote sidecar) and three LOW items should be tracked as follow-ups; route
the TLS-coupling warning and the explicit message-size/response cap to
`python-expert`, and the health-probe comment reword to docs. Regression tests
(a scripted mock channel asserting no payload text appears in logs/exceptions,
and unspecified/unterminated-frame handling) to `testing-expert`.
