# Threat Model - Harness & code-intel backend config surface (Milestone 0005 Task 01.0 / 02.0 / 06.0) - 2026-08-24

Scope: NEW untracked configuration-only modules
`src/aegis_swr/harness/{__init__,exceptions,config}.py`,
`src/aegis_swr/claude_code/{__init__,config}.py`,
`src/aegis_swr/openhands/{__init__,config}.py` and their unit tests. Runtime
tools/process/client modules are out of scope (later tasks). Reviewed against
plan.md contracts C2, C3, C6, C8, C13 and `.claude/CLAUDE.md` §3.

## Assets & trust boundaries

- **Assets:** the read-only forensic posture of the host-permission Claude Code
  backend (no sandbox); the Docker-sandbox guarantee of the OpenHands backend;
  operator credentials/URLs never leaking to logs or error bodies; the single-
  active-backend selection invariant.
- **Boundaries crossed:** operator/CI environment (attacker-adjacent: unset CI
  secrets expand to `""`) → Pydantic `BaseSettings` validators → domain
  exceptions → loguru sinks (`_sensitive_filter`, API-key regex only). These
  modules do **not** touch incident payloads, subprocess, SQL, or network; they
  are pure settings construction.
- **Confirmed empirically:** importing all six modules pulls **no** heavy client
  library (grpc/docker/openhands/httpx/boto3) and triggers **no** network,
  subprocess, or filesystem write at import time; `claude_code.config` and
  `openhands.config` import **no** sibling backend package. `harness.config`
  imports all three per-family *config* modules by design (nested settings).

## Findings

### [MEDIUM] `scratch_cwd` validator echoes resolved absolute filesystem paths into error messages
- Vector / evidence: `src/aegis_swr/claude_code/config.py:411`, `:416`, `:426` -
  three `ClaudeCodeConfigError` reasons format `{resolved}`
  (`scratch_cwd.expanduser().resolve()`). Confirmed: `str(e)` =
  `"...scratch_cwd: path is not a directory: /private/var/.../tmp.../afile"`. The
  resolved path includes `expanduser()` output (home dir → username) and host FS
  layout. The project `_sensitive_filter` (`cli/aegis_logging.py:28`) only
  redacts API-key/bearer patterns, so a path passes through to every sink and
  into any API error body that surfaces the exception. CWE-209.
- Impact: information disclosure of host directory structure / usernames via
  logs and error responses. Directly contradicts this milestone's stated C13
  rule ("only field names and backend-family names permitted") and is
  inconsistent with the sibling repo-root branch (`:431`) which deliberately
  omits the path. Operator-controlled config, not a credential or hostile
  payload, so not CRITICAL.
- Mitigation: drop `{resolved}` from all three reasons (state only the field and
  the condition, as the repo-root branch already does). Hand to `python-expert`;
  regression test asserting no path substring in `str(exc)` to `testing-expert`.

### [MEDIUM] Empty/blank env for security-relevant `bool` fields raises a raw `ValidationError` instead of the fail-safe default
- Vector / evidence: `openhands/config.py:148` (`auto_start`), `:149`
  (`allow_unsandboxed_runtime`), `claude_code/config.py:196` (`enabled`). Unlike
  the string/path/selector fields, these `bool` fields have **no** `mode="before"`
  empty-coercion validator. Confirmed: `OPENHANDS_ALLOW_UNSANDBOXED=""` and
  `CLAUDE_CODE_ENABLED=""` both raise Pydantic `bool_parsing` `ValidationError`
  (not the unwrapped domain error) at construction. This is the exact
  unset-CI-secret-`""` failure mode recorded in project memory.
- Impact: **fail-safe for security** - an empty value never flips a guard to a
  permissive state (never enables a backend, never disables the sandbox; verified
  across `""`,`" "`,`0`,`false`,`true`,`1`,`yes`,`on`). But it is an availability
  landmine: a deployment with an unset CI secret crashes settings construction
  with an unhandled `ValidationError` rather than degrading to the safe default.
  Inconsistent with the milestone's own empty-env-tolerance contract applied to
  every other field.
- Mitigation: add a shared `mode="before"` bool coercion that maps blank/`""` to
  the field's safe default (`False`) for `enabled`, `auto_start`,
  `allow_unsandboxed_runtime`; keep the strict fail-safe (never coerce `""`→True).
  Route to `python-expert`; add empty-env regression tests via `testing-expert`.

### [LOW] Validator error messages echo operator-supplied tool/mode/selector tokens
- Vector / evidence: `claude_code/config.py:287` and `openhands/config.py:273`
  echo the rejected `unknown` tool names; `claude_code/config.py:357` echoes the
  raw `permission_mode` value `v`; `harness/config.py:138` echoes the rejected
  `backend` selector string. These are short operator-config tokens, not
  credentials/URLs/payloads, and the tool-name echo matches the accepted
  precedent in `openclaude/config.py:223`.
- Impact: minor deviation from the strict "field/family names only" reading of
  C13; negligible disclosure risk (operator's own invalid config token).
- Mitigation: optional - drop the echoed value or bound its length. Follow-up.

### [LOW] `harness/config.py` imports all three backend config families
- Vector / evidence: `harness/config.py:33-36` imports `ClaudeCodeSettings`,
  `OpenClaudeSettings`, `OpenHandsSettings`. C3 (plan §C3) literally names
  `harness/composition.py` as "the only module permitted to import more than one
  backend family." This is by design (`HarnessSettings` composes nested per-family
  settings) and the imported config modules are lightweight (no client libs), but
  the literal C3 wording and its grep-based CI check name only `composition.py`.
- Impact: none at runtime (no side effects, no heavy libs). Risk is only that the
  C3 isolation CI job may false-positive or that the boundary intent is ambiguous.
- Mitigation: confirm the C3 grep allowlist covers `harness/config.py`, or move
  nested-settings composition to `composition.py`, whichever the architect
  prefers. Follow-up for `app-architect`.

### [INFO] `scratch_cwd` guard blocks repo-root/ancestor but not in-repo subdirectories
- Vector / evidence: `claude_code/config.py:428-433` rejects `scratch_cwd` ==
  repo root or an ancestor of it, matching the documented ivar contract. It does
  **not** reject a subdirectory *inside* the repo (e.g. `<repo>/scratch`), which
  the method docstring's broader "operate over the live source tree" rationale
  might imply. With write-capable tools OFF by default (C6) and no write side
  effects in this task, exposure is limited to read access the backend has
  regardless. Noting the gap between docstring rationale and the narrower
  enforced contract.
- Impact: none under default read-only posture; matters only if an operator both
  enables Write/Edit tools and points `scratch_cwd` inside the repo.
- Mitigation: optionally also reject `scratch_cwd` that is the repo root or *any
  descendant of it*; or tighten the docstring to the enforced contract.

## Posture confirmations (no finding)

- **C6 permission bypass rejection is robust.** `permission_mode` is a strict
  allowlist (`_ALLOWED_PERMISSION_MODES = {default, acceptEdits, plan}`,
  `config.py:354`) applied to the raw value *in addition to* the case-insensitive
  bypass reject-list (`:346-353`). Every spelling of bypass
  (`bypassPermissions`, `BYPASSPERMISSIONS`, `--dangerously-skip-permissions`,
  whitespace-padded) is rejected; no coercion runs after the check. Write-capable
  tools (`Write`,`Edit`) are OFF in the `allowed_tools` default (`:197`).
- **C8 sandbox default is safe.** `runtime_mode` defaults to `docker`
  (`config.py:144`); a non-sandboxed runtime requires `runtime_mode` in
  `_UNSANDBOXED_RUNTIMES` **and** `allow_unsandboxed_runtime is True`, and emits a
  loud WARNING (`:355`). Empty/malformed override values cannot reach the truthy
  path (see MEDIUM above - they crash, not enable).
- **C13 secret/URL non-disclosure holds for credentials.** No validator or
  exception formats a `server_url`, token, API key, or incident-payload value;
  `server_url` validation (`openhands/config.py:235`) rejects without echoing.
  The two `logger.warning` calls (`claude_code/config.py:291`,
  `openhands/config.py:279`, `:355`) log only tool/field names.
- **C2 selection invariant.** Ambiguity (selector unset + >1 presence signal)
  fails loud at construction (`harness/config.py:216`) carrying only sorted family
  signal names; blank selector coerces to auto-select (`:131`) - never a crash.
- **C3 isolation & no import-time side effects** - empirically verified above.

## Verdict: PASS

No CRITICAL or HIGH finding. No credential, token, or incident-payload value is
formatted into any log line, `__repr__`, or exception message; permission-bypass
rejection and sandbox-default posture are sound; empty-env handling is fail-safe
for security (never permissive). Merge is **not blocked**. Two MEDIUM follow-ups
(path echo in `scratch_cwd` errors; raw `ValidationError` on empty bool env)
should be fixed before the runtime tasks (03.0/07.0) build on this surface;
neither gates this configuration-only change.
