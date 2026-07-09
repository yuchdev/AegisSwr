# Threat Model - OpenClaude managed-mode subprocess spawn - 2026-07-09

**Feature:** Milestone 0004, Task 03.0 subtask 02 - managed mode of
`OpenClaudeProcess` (`src/aegis_swr/openclaude/process.py`).
**Scope:** `auto_start=True` path - Aegis launches the OpenClaude Node.js
sidecar via `asyncio.create_subprocess_exec`, passes tool/Bash allowlist flags,
waits for the gRPC port, and terminates it (SIGTERM -> grace -> SIGKILL) on exit.
**Status of code under review:** not yet written; this is a pre-implementation
gate. No CRITICAL defect exists *in situ* - the findings below are binding
requirements whose violation would introduce one.

## Assets & trust boundaries

- **Asset:** the read-only forensic guarantee. The sidecar is confined by the
  `--allowed-tools` allowlist (write tools rejected at config) and the Bash
  binary allowlist. Anything that lets an extra CLI flag reach the sidecar can
  dissolve that confinement -> arbitrary command execution on the analyst host.
- **Asset:** incident payloads / secrets that transit the sidecar. Its stderr
  is an untrusted, potentially secret-bearing stream.
- **Trust boundaries crossed:**
  1. `settings`/env (operator- and deployment-controlled, treated as
     semi-trusted) -> `_build_argv` -> `execvp` argv of a child process.
  2. child process stderr (untrusted output) -> logger sink -> persisted log.
  3. PATH / filesystem -> resolved binary -> code executed as the Aegis user.
  4. sidecar gRPC listener -> local/network socket surface.

## Findings

### [HIGH] Argument (flag) injection via `bash_allowlist` into the sidecar argv
- Vector / evidence: `config.py:235-251` `_validate_bash_allowlist` is
  **warn-only** - it rejects nothing, so `bash_allowlist` entries are arbitrary
  strings (leading `--`, `=`, whitespace, commas, control chars all pass). By
  contrast `allowed_tools` (`config.py:217-233`) is whitelisted against
  `_KNOWN_TOOLS`, so those values are safe tokens. `_build_argv` is the new sink
  that turns these values into CLI flags. A value like `--dangerously-...` or
  one containing the CSV separator smuggles an extra flag / list entry into the
  sidecar and can defeat the allowlist confinement. CWE-88 (Argument Injection),
  OWASP A03:2021.
- Impact: bypass of the read-only forensic guarantee -> arbitrary binary /
  command execution by the sidecar. Elevation.
- Mitigation / **required posture**:
  - Emit the **joined `--flag=value` single-token form**, one argv element that
    binds value to flag unambiguously:
    `f"--allowed-tools={','.join(settings.allowed_tools)}"` and the equivalent
    for the Bash allowlist. Do **not** emit `["--allowed-tools", v0, v1, ...]`
    positional runs and do **not** rely on the space-separated `--flag value`
    two-token form (a value beginning with `-` is then re-parsed as a flag).
  - Add **per-value validation at the argv boundary** (fail closed) for every
    `bash_allowlist` entry: accept only `^[A-Za-z0-9._-]+$` and reject any value
    that starts with `-`, or contains `,`, `=`, whitespace, or control chars.
    Raise `OpenClaudeConfigError`/`ValueError` - never silently drop. Config's
    warn-only stance is deliberate (keeps defaults valid); the hard reject
    belongs at the argv sink, not in config.
  - `allowed_tools` is already whitelisted, but apply the same token check for
    defense-in-depth so both lists go through one validated helper.

### [HIGH] Sidecar must bind loopback only, never a wildcard address
- Vector / evidence: managed mode resolves the gRPC bind address (port-0
  resolution deferred to subtask 03); `_is_loopback_host` (`client.py:97-109`)
  already assumes a loopback endpoint. If the spawned sidecar is told to bind
  `0.0.0.0`/`::`, the tool-executing sidecar is reachable off-box. CWE-668
  (Exposure of Resource to Wrong Sphere), OWASP A05:2021.
- Impact: a network peer can drive the sidecar's Bash/tool surface.
- Mitigation / **required posture**: the bind address passed in argv must be
  `127.0.0.1` (loopback) explicitly; never a wildcard. The readiness probe
  connects to the same loopback host:port.

### [MEDIUM] Binary path resolution / PATH hijack
- Vector / evidence: `settings.process_binary` defaults to the bare name
  `"openclaude"` (`config.py:150`), resolved via PATH (`execvp` semantics of
  `create_subprocess_exec`). A writable PATH entry, or cwd on PATH, lets an
  attacker plant a malicious `openclaude`. CWE-426/CWE-427 (Untrusted / Uncontrolled Search Path).
- Impact: arbitrary code execution as the Aegis user at spawn time.
- Mitigation / **required posture**:
  - The binary path comes from `settings.process_binary` only (C1) - never read
    `os.environ` directly and never hardcode.
  - If `process_binary` contains a path separator, require it be **absolute**
    and validate it resolves to an existing regular file before spawning; reject
    a relative path.
  - Do not add cwd to PATH and do not inherit an attacker-mutated search path;
    pass an explicit safe `cwd` to the child. Bare-name PATH resolution is
    acceptable **only** under the documented operator-controlled-PATH assumption.

### [MEDIUM] Untrusted stderr forwarding must not leak payloads/secrets (C9)
- Vector / evidence: subtask 04 will forward child stderr to the logger at
  DEBUG. Child stderr is untrusted and may carry incident-payload fragments,
  tool output, or secrets. The loguru `_sensitive_filter`
  (`aegis_logging.py:60-64`) redacts only key-*shaped* tokens via `_REDACT_RE`
  (`aegis_logging.py:28-35`); it does **not** redact arbitrary payload text.
  CWE-532 (Sensitive Information in Log File).
- Impact: PII/secret/payload disclosure in persisted logs.
- Mitigation / **invariant the coder must hold now**:
  - Treat stderr as untrusted; log it only through loguru (so `_sensitive_filter`
    covers the sink) at DEBUG, never at a level that persists by default.
  - Never log raw response/prompt/payload text; stderr forwarding is for
    process-diagnostic lines only. Do not concatenate stderr into exception
    messages that propagate to API bodies.
  - Read stderr **bounded** (line-by-line / capped buffer), never a single
    unbounded `read()` (see DoS below).
  - `stdout=DEVNULL` (gRPC traffic is on the channel, not stdout) is correct and
    required; only `stderr` is piped.

### [LOW] Teardown: signal only the owned, still-live handle (PID-reuse race)
- Vector / evidence: SIGTERM->grace->SIGKILL sequence. Signalling a recycled PID
  after the child exited/was reaped would hit an unrelated process. CWE-364/CWE-367
  (signal/TOCTOU race).
- Mitigation / advisory: operate only on the `asyncio` process handle
  (`process.terminate()`/`process.kill()`), never `os.kill(pid, ...)` on a raw
  int; guard every step on `process.returncode is None`; rely on the asyncio
  child watcher to reap. `_terminate_managed` must be idempotent and a no-op when
  never started or already exited.

### [LOW] DoS / resource exhaustion
- Vector / evidence: readiness poll and stderr drain.
- Mitigation / advisory: the poll is bounded by `settings.connect_timeout_s`
  (validator guarantees `> 0`, `config.py:264-273`) using `asyncio.sleep`
  backoff - never `time.sleep`. Enforce the always-terminate invariant via
  `try/except: await self._terminate_managed(); raise` around the readiness wait
  and re-terminate from `__aexit__`, so an entry-raised-after-start never orphans
  a sidecar (no zombie). Bound the stderr buffer. CWE-400.

### [CRITICAL-if-violated] Shell avoidance (hard rule)
- Vector / evidence: any shell string path would let payload/config text reach a
  shell interpreter. CWE-78 (OS Command Injection).
- Mitigation / **required posture (non-negotiable)**: use
  `asyncio.create_subprocess_exec(*argv, ...)` with a **list argv only**. No
  `create_subprocess_shell`, no `subprocess.Popen`/`shell=True`, no f-string
  command line anywhere in the module. Violation is an automatic CRITICAL /
  merge block.

## Verdict: ADVISORY

No CRITICAL defect is present because the code is not yet written. Merge is not
blocked, **but** the two HIGH items (argv flag-injection form + per-value
validation; loopback-only bind) and the shell-avoidance hard rule are binding:
if the implementation ships without them the review flips to BLOCK. Hand the
argv-hardening and binary-path validation to `python-expert`; hand
flag-injection and always-terminate regression tests to `testing-expert`.
