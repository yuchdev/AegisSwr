# Threat Model - Claude Code subscription/login authentication (Milestone 0005 Task 04.0) - 2026-08-24

**Mode:** pre-implementation. No code exists for subtasks 01-03 yet; findings are
framed as **required controls** the `python-expert` must satisfy, not defects
observed. Reviewed against C7 (plan.md:460-550), C6, C13, `.claude/CLAUDE.md`
§3, and the shipped `claude_code/{config,process,tool,exceptions,events}.py`.

## Assets & trust boundaries

- **Assets:** (1) the operator's *billing intent* - a subscription login must not
  be silently displaced by a stray API key; (2) two live credential surfaces -
  `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, and the
  stored `claude login` session at `%USERPROFILE%\.claude\.credentials.json`
  (Windows target); (3) the config/runtime error split (`ClaudeCodeConfigError`
  vs `ClaudeCodeUnavailableError`) that tells an operator *fix config* vs
  *re-authenticate*; (4) the licensing posture (opt-in `subscription`).
- **Boundaries crossed:** operator/CI env (`os.environ`, attacker-adjacent -
  unset CI secrets expand to `""`) -> Pydantic settings validator -> credential
  resolver -> `asyncio.create_subprocess_exec` child env/argv -> `claude` process
  -> stderr/NDJSON -> loguru sinks (`_sensitive_filter`) and `EventBus`
  (`ClaudeCodeAuthFailed`). Task text is out of scope (C6: via stdin, confirmed
  `process.py:563-575`).
- **Confirmed in shipped code:** `create_subprocess_exec` passes **no** explicit
  `env=` (`process.py:536-542`), so the child inherits the **entire live
  `os.environ` at spawn time** - this is the crux of Findings 1 and 2.
  `_drain_stderr` (`process.py:608-633`) logs child stderr at DEBUG relying on
  `_sensitive_filter`; that filter's coverage is incomplete (Finding 3).

## Findings

### [HIGH] Silent-override / TOCTOU: child inherits live `os.environ` at spawn, not the env validated at construction
- Vector / evidence: subtask 01 rejects `subscription` + `ANTHROPIC_API_KEY` at
  **settings-construction** time by reading `os.environ` once
  (`04.0/01:120-137`). But the child is spawned later with no explicit `env=`
  (`process.py:536-542`), re-reading whatever `os.environ` holds **at spawn**.
  Any `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` set *after* construction (late
  CI secret injection, a component that populates env post-settings-load, a
  parent-shell export) is inherited and, per C7 ranks 2-3, **silently outranks**
  the subscription credential (rank 5-7). This is precisely the failure C7 exists
  to eliminate, reintroduced through the construction<->spawn window. CWE-367
  (TOCTOU), CWE-696.
- Impact: an operator who opted into `subscription` is silently billed to / run
  under a stray API key with **no error** - the construction-time check gives a
  false sense of safety. Settings-construction rejection alone is **not
  sufficient**.
- Mitigation (required control): construction-time rejection is necessary but
  must be paired with a **spawn-time control** in the credential resolver /
  Task 03.0 env builder. In `subscription` mode, build the child env
  **explicitly** from a copy of `os.environ` with the outranking credentials
  (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and rank-1 cloud-provider creds
  `AWS_BEARER_TOKEN_BEDROCK`/Bedrock/Vertex vars) **removed**, then pass it via
  `env=` to `create_subprocess_exec`. Additionally, **re-check presence at spawn**
  and if an outranking var reappeared, raise
  `ClaudeCodeUnavailableError(reason="ambiguous_credential")` + emit
  `ClaudeCodeAuthFailed` rather than proceeding. This collapses the TOCTOU window
  and makes the C7 precedence guarantee deterministic instead of best-effort.

### [HIGH] `_sensitive_filter` does not redact `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_AUTH_TOKEN` assignment forms
- Vector / evidence: `cli/aegis_logging.py:28-35`. The keyword alternation is
  `(ANTHROPIC_API_KEY|OPENAI_API_KEY|AWS_BEARER_TOKEN_BEDROCK|api[_-]?key|bearer|authorization)`
  - it **omits `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_AUTH_TOKEN`**. The
  value-shape clauses (`sk-ant-...`, `sk-[A-Za-z0-9_-]{10,}`) catch an
  `sk-ant-`-shaped OAuth/API token value *if it has that prefix*, but
  `ANTHROPIC_AUTH_TOKEN` is a **generic gateway/proxy bearer** whose value is
  **not guaranteed** `sk-`-shaped, so a line like
  `ANTHROPIC_AUTH_TOKEN=<non-sk-value>` passes through **unredacted**. This
  matters because `process.py:_drain_stderr` (`:608-633`) logs raw `claude`
  stderr at DEBUG **relying on this filter**, and the probe (subtask 03) reuses
  that same spawn path. CWE-532 (info in log), OWASP A09:2021.
- Impact: a `claude` startup diagnostic or auth error that echoes an env
  assignment can write a live credential to `aegis-swr.log` / stderr at
  DEBUG/TRACE. C7/C13 mandate `SensitiveFilter` cover *every* sink for these
  exact variables; it does not.
- Mitigation (required control, pre-condition for merge): extend `_REDACT_RE`'s
  keyword alternation to include `CLAUDE_CODE_OAUTH_TOKEN` and
  `ANTHROPIC_AUTH_TOKEN`, and add explicit `sk-ant-oat01-`/`sk-ant-ort01-`
  (OAuth access/refresh) coverage as belt-and-braces. Regression test: assert a
  crafted log line containing each variable=value and each token prefix redacts
  to `[REDACTED]`. Do **not** rely on the value-shape clause alone. Hand the
  regex change to `python-expert`, the redaction tests to `testing-expert`.

### [HIGH] Probe error surface must classify from exit status only - never raw `claude` stderr
- Vector / evidence: subtask 03 (`04.0/03:136-159`) is exactly where an
  implementer is tempted to surface `claude`'s stderr into the exception, log, or
  event to explain *why* auth failed. `claude`'s stderr can echo a rejected token
  or the credential-file path. The reason vocabulary is a **closed set**
  (`no_stored_login|token_rejected|ambiguous_credential`,
  `events.py:183-188`, `exceptions.py:76-84`) and is safe **only if the mapping
  never derives free-form text from stderr**.
- Impact: a failing auth probe that logs `stderr` or puts it in
  `ClaudeCodeUnavailableError(message=...)` or the `ClaudeCodeAuthFailed` payload
  leaks credential fragments at the highest-risk moment. CWE-209/CWE-532.
- Mitigation (required control): `probe_auth` maps **process exit status +
  structured NDJSON `result` frame** onto the closed reason set; it **never**
  reads/logs/embeds raw stderr. When a specific reason cannot be determined, use
  the most conservative label and log at WARNING with the **label only**. The
  emitted `ClaudeCodeUnavailableError.message` must be a fixed string
  (`exceptions.py:96` already stores only `message`/`reason` - keep it literal).
  Because subtask 03 reuses `ClaudeCodeProcess`, and `_drain_stderr` logs stderr
  at DEBUG, either suppress stderr logging on the probe path or ensure Finding 3
  is fixed first (belt-and-braces: both).

### [MEDIUM] Never read/parse the `%USERPROFILE%\.claude\.credentials.json` file in-process; never surface its path
- Vector / evidence: subtask 03 verifies the `relies_on_stored_login=True` case.
  The tempting shortcut is for Aegis to open/parse the credentials file to "check
  it exists/looks valid." Doing so copies the OAuth access+refresh tokens into
  Aegis memory (and risks logging them), and any error mentioning the resolved
  path leaks `%USERPROFILE%` -> the OS **username** (CWE-200), the same class of
  disclosure already flagged MEDIUM for `scratch_cwd` in the sibling threat model
  (2026-08-24-harness-code-intel-config.md).
- Impact: credential material lifetime in Aegis memory + username disclosure via
  error/log.
- Mitigation (required control): the probe verifies the stored session **only by
  spawning `claude`** and observing exit status - Aegis never opens, reads,
  copies, or stats the credentials file, and never places any resolved
  `~/.claude` path in an exception, log, or event (the coarse `no_stored_login`
  label is the entire operator-facing signal). File-permission hardening of
  `.credentials.json` (NTFS ACLs to the user) is the operator's concern; note it
  in the Task 13.0 setup guide, do not enforce it in code.

### [MEDIUM] `--bare` exclusion must be enforced at BOTH construction and argv-build (defence in depth)
- Vector / evidence: C7/subtask 01 reject `subscription` + `--bare` at
  construction; subtask 02 (`04.0/02:109-113`) additionally omits `--bare`
  unconditionally in the `subscription` branch. `build_argv` currently never adds
  `--bare` (`process.py:83-84`), so a future bare toggle is the only way it could
  appear.
- Impact: bare mode reads **no** OAuth/login credentials (status.md:110-112). If
  `--bare` ever reached a `subscription` invocation, the child would ignore the
  intended login and either hard-fail or, worse, fall through to a stray API key
  still in env (compounding Finding 1) - a silent wrong-credential run.
- Mitigation (required control): keep the invariant in **both** places - the
  construction-time reject (single documented home, subtask 01) **and** the
  resolver unconditionally omitting `--bare` for `subscription` (subtask 02). Do
  not introduce a duplicate bare toggle if Task 03.0 already owns one. Test the
  matrix: `subscription`+bare-requested -> `ClaudeCodeConfigError`; and assert
  `--bare` absent from `extra_argv` in every `subscription` resolution.

### [MEDIUM] Credential must never reach argv; forward OAuth token by name only
- Vector / evidence: `ResolvedCredential` carries `env_passthrough` (names) and
  `extra_argv` (flags), **never a value** (`04.0/02:44-71,99-103`). The risk is
  an implementer "helpfully" adding `--api-key <value>` or similar to argv, which
  `ps`/process-listing would expose (C6 already routes task text via stdin for
  this reason).
- Impact: credential exposure via argv/process table (CWE-214).
- Mitigation (required control): the OAuth token flows **only** through the child
  env (`env=` dict), copied from `os.environ` at spawn - never into
  `build_argv`, `extra_argv`, or `ResolvedCredential` fields. Assert no argv
  element ever contains a credential value in the test matrix.

### [MEDIUM] Inherited-then-filtered env is safer than an explicit allowlist on the Windows target
- Vector / evidence: Finding 1's mitigation requires an explicit child `env=` for
  `subscription` mode. An allowlist that forwards only a hand-picked set risks
  omitting Windows essentials (`SystemRoot`, `USERPROFILE`, `APPDATA`, `PATH`,
  `TEMP`) that `claude` needs to locate the credential store and run - a
  correctness landmine that could also mask auth as a spurious failure.
- Impact: over-restrictive allowlist breaks the binary; under-restrictive one
  reintroduces Finding 1.
- Mitigation (recommendation): use **inherited-then-filtered** - `dict(os.environ)`
  minus the deny-listed outranking credentials (Finding 1) - not a from-scratch
  allowlist. This preserves platform env while removing exactly the vars that
  defeat the operator's `subscription` intent. Keep `CLAUDE_CODE_OAUTH_TOKEN`
  when present (it is the intended winner once ranks 2-3 are stripped).

### [MEDIUM] Probe needs its own short, independent timeout and must be a genuine dry-run no-op
- Vector / evidence: subtask 03 (`04.0/03:136-155`). The probe spawns `claude`,
  which makes a network round-trip to validate the credential - real latency and
  cost, and a hang risk if the endpoint stalls. Reusing `request_timeout_s` would
  couple a fast health-check to a long investigation budget.
- Impact: DoS/availability - a stalled probe blocks startup / `code-intel check`;
  an un-short-circuited dry-run probe would require a live credential where none
  should be needed.
- Mitigation (required control): give the probe its **own short timeout**
  independent of `request_timeout_s`, `asyncio`-based (`asyncio.sleep` for any
  backoff, never `time.sleep`), with a defined failure path and no bare `except`.
  Under `--dry-run` the probe **short-circuits to success without spawning**.
  Keep it idempotent/run-once-safe (called by both composition and Task 10.0's
  `aegis code-intel check`). RAII via the existing `ClaudeCodeProcess` context
  manager - do not construct a bare subprocess.

### [MEDIUM] Two-error distinction is a security control, not just ergonomics - do not conflate
- Vector / evidence: C7 and subtask 03 require `ClaudeCodeConfigError`
  (construction, settings-shape) and `ClaudeCodeUnavailableError` (runtime
  capability) to stay distinct, neither subclassing the other
  (`exceptions.py:57-96`, `04.0/03:107-118`). A probe that raised `ConfigError`
  on a token-rejected failure would tell the operator to *edit config* when they
  should *re-authenticate* - and vice-versa could mask an ambiguous-credential
  config fault as a transient runtime blip that retry logic keeps hammering.
- Impact: mis-signalled remediation; wrong ret/retry behaviour on an auth fault.
- Mitigation (required control): probe raises **only** `ClaudeCodeUnavailableError`
  with a closed-set `reason`; construction raises **only** `ClaudeCodeConfigError`.
  Test that neither is a subclass of the other and that each failure maps to the
  correct type.

### [MEDIUM] Licensing caveat is an unresolved compliance risk - opt-in default is the mitigation, documentation is mandatory
- Vector / evidence: C7 "Licensing caveat" (plan.md:538-546) and README
  Assumptions (`04.0/README:46-64`): no Anthropic ToS language was found
  permitting personal (Pro/Max) vs organizational (Team/Enterprise) seats for
  **non-interactive production automation at scale**. This is a compliance/legal
  risk, not a technical vulnerability.
- Impact: running `subscription` mode in production at scale on a personal seat
  could breach Anthropic ToS.
- Mitigation (adequate, confirm): shipping `subscription` **opt-in only** with
  `auth_mode` defaulting to `auto` is an **adequate** technical mitigation - it
  does not force the licensing question and leaves existing Task 03.0 behaviour
  untouched. **Required documentation:** (a) the code-level constraint travels in
  the `auth_mode` ivar docstring (default `auto` is licensing-driven, not
  incidental); (b) Task 13.0's setup guide must state the caveat in prose and
  recommend confirming with Anthropic sales/legal before production use. Do not
  change the default without that confirmation.

### [LOW] `auto` mode must remain a behavioural no-op (regression-surface, not a leak)
- Vector / evidence: C7/README (`04.0/README:101`) freeze `auto`: no validation,
  no credential branching, no forced probe behaviour beyond Task 03.0.
  `resolve_credential(auto)` must return empty `extra_argv`/`env_passthrough`
  (`04.0/02:104-108`) and inherit env unexamined. `tool.py:48` currently
  hardcodes `_AUTH_MODE = "auto"` - replacing it must not alter the `auto` path.
- Impact: a regression that adds env-stripping or a mandatory probe to `auto`
  would break every Task 03.0 acceptance criterion and could change which
  credential resolves for existing operators.
- Mitigation: assert Task 03.0's `auto`-mode acceptance tests stay green
  untouched; env-stripping (Finding 1) applies to `subscription` **only**.

## Required pre-conditions the implementer must satisfy

1. Fix `_REDACT_RE` (Finding 3) to cover `CLAUDE_CODE_OAUTH_TOKEN` +
   `ANTHROPIC_AUTH_TOKEN` **before** the probe path (which logs `claude` stderr)
   is exercised. This is merge-blocking.
2. `subscription` mode spawns with an **explicit filtered `env=`** (Finding 1/7)
   and a **spawn-time re-check** of outranking vars - construction-time rejection
   alone is insufficient. This is merge-blocking.
3. Probe classifies from **exit status + NDJSON only**, never raw stderr
   (Finding 3); its message/event carry only closed-set labels (Findings 3, 8).
4. Never open/read/stat the credentials file; never surface a `~/.claude` path
   (Finding 4).
5. No credential value in argv, `ResolvedCredential`, logs, exceptions, or events
   (Findings 5, 3); `--bare` excluded at both layers (Finding 6).
6. Probe has an independent short timeout and a dry-run short-circuit (Finding 9).

## Verdict: PASS_WITH_FOLLOWUP

No implementation exists, so nothing is being merged today. The design in C7 and
subtasks 01-03 is sound and does not itself introduce a CRITICAL flaw. However,
two controls are **merge-blocking pre-conditions** (pre-conditions 1 and 2): the
`SensitiveFilter` gap (Finding 3) and the construction<->spawn credential
override / TOCTOU (Finding 1) would each be **CRITICAL/HIGH if the code ships
without them**. When the implementation lands, `security-auditor` must re-review
against the six pre-conditions above; a build that inherits full `os.environ` at
spawn in `subscription` mode, or that logs raw `claude` stderr through the
current incomplete filter, must be **BLOCKED** from `master`.

---

# Re-review (post-implementation) - 2026-08-25

**Mode:** post-implementation verification. The implementation for subtasks
01-03 has landed in the working tree (uncommitted): `claude_code/config.py`
(`auth_mode`, `bare`, `_validate_subscription_mode`), `claude_code/process.py`
(`ResolvedCredential`, `resolve_credential`, `_build_child_env`, spawn wiring),
`claude_code/tool.py` (`probe_auth`, `_probe_once`), and the `_REDACT_RE` change
in `cli/aegis_logging.py`, with `tests/unit/claude_code/test_auth_modes.py`.
Each of the six merge-blocking / required controls was verified against the code,
not the tests. **One new CRITICAL was found: the fix for pre-condition 1 (the
`_REDACT_RE` extension) introduced a ReDoS.**

## Per-control verification

| Control (original finding)                                  | Verdict          | Evidence |
|-------------------------------------------------------------|------------------|----------|
| F1 spawn-time filtered `env=` + TOCTOU re-check             | VERIFIED (partial gap) | `process.py:661-702`; re-check at `:693-699` runs before spawn at `:633`; applies on both `delegate` and probe paths. Gap: strip list omits Bedrock/Vertex routing toggles (new MEDIUM below). |
| F3 `_REDACT_RE` covers `*AUTH_TOKEN`/`*OAUTH_TOKEN`         | VERIFIED for coverage; **FAILED for safety** | `aegis_logging.py:38-46`. Coverage correct, but the new clause is quadratic-backtracking (new CRITICAL below). |
| F3b probe classifies from exit status/NDJSON only, not stderr | VERIFIED       | `tool.py:237-266` (`_probe_once` reads exit code + `result.usage`/`is_error` + resolved-credential state only); `probe_auth:216-235` maps to closed set; no `stderr` read anywhere in classification. |
| F4 never open/stat/`~/.claude` path; no path on any surface | VERIFIED         | No file access in `resolve_credential`/`_build_child_env`/probe (grep clean); presence tested via `os.environ.get` only; test `test_probe_failure_leaks_no_secret_*` asserts `.credentials.json` absent from every surface. |
| F5 credential never in argv; forwarded by name              | VERIFIED         | `resolve_credential` carries names/flags only; `_build_child_env` copies value into child `env=` dict only (`process.py:701-702`); argv = `build_argv` + `extra_argv` (fixed literal set). |
| F6 `--bare` excluded at both layers                         | VERIFIED         | Construction reject `config.py:518-526`; resolver never emits `--bare` in subscription `process.py:140-147`; `build_argv` structurally cannot emit it. |
| F9 probe own short timeout + dry-run short-circuit          | VERIFIED         | `_PROBE_TIMEOUT_S=20.0` (`tool.py:56`), independent `asyncio.wait_for` (`:217`); `dry_run` returns before spawn (`:212-213`). |
| F8 two-error distinction (Config vs Unavailable)            | VERIFIED         | `exceptions.py`: neither subclasses the other; probe raises only `ClaudeCodeUnavailableError`, construction only `ClaudeCodeConfigError`. |
| `auto` behavioural freeze (LOW)                             | VERIFIED         | `resolve_credential(auto)` no-op; `_build_child_env` returns `None` for auto/api_key (`process.py:690-691`) -> `env=None` inherit. |
| `bare` field default preserves prior behaviour              | VERIFIED         | Default `False`; `_coerce_bare` maps `""`->`False`; malformed value -> pydantic error (fails closed, never truthy); `subscription`+`bare` rejected. |
| Empty-env coercion cannot select `subscription`/`bare`      | VERIFIED (security) / **BUG (robustness)** | `""` cannot select subscription; but `CLAUDE_CODE_AUTH_MODE=""` crashes construction (new MEDIUM below). |

## New findings introduced by the implementation

### [CRITICAL] ReDoS in the new `_REDACT_RE` `*AUTH_TOKEN` clause (regression of the F3 fix)
- Vector / evidence: `cli/aegis_logging.py:42`, clause
  `[A-Z0-9_]*O?AUTH_TOKEN\s*[=:]\s*\S+` (IGNORECASE). The leading unanchored
  greedy `[A-Z0-9_]*` matches at every offset of a long alphanumeric/underscore
  run; combined with `re.sub` scanning every start position this is **O(n^2)**.
  Measured: 8 KB line = 10.7 s, 40 KB line = 64.7 s, growth quadratic (2000->0.57s,
  4000->2.32s, 8000->10.7s). The three pre-existing clauses are fixed-prefix and
  stay < 2 ms on the same input. `_sensitive_filter` runs **synchronously on
  every loguru record app-wide**, including `_drain_stderr`'s DEBUG log of
  attacker-influenced `claude` stderr (`process.py:769`) and any INFO+ record
  carrying incident-payload text (base64/hex/symbol runs are exactly this shape).
  Because the sinks are added without `enqueue=True`, the blow-up runs on the
  asyncio event loop and stalls the whole process; runtime scales with input size
  (multi-MB dump -> effectively unbounded). CWE-1333 (ReDoS), CWE-400.
- Impact: attacker-influenced input reaching any redacted sink causes
  uncontrolled CPU / event-loop stall - a denial of service of the incident
  platform, precisely on the untrusted path Finding 3 exists to protect. The
  merge-blocking F3 remediation reintroduced a worse problem than it fixed.
- Mitigation: anchor the identifier and make the prefix non-backtracking, e.g.
  `\b[A-Z0-9_]*+O?AUTH_TOKEN\s*[=:]\s*\S+`. Verified: this preserves redaction of
  `ANTHROPIC_AUTH_TOKEN=...` / `CLAUDE_CODE_OAUTH_TOKEN: ...`, still leaves
  `OAUTH_TOKEN_COUNT=5` untouched, and collapses runtime to linear
  (20 000-char line: 1.1 ms). Hand the one-line regex change to `python-expert`
  and a timing/ReDoS regression assertion (e.g. redact a 50 KB blob under a hard
  wall-clock bound) to `testing-expert`.

### [MEDIUM] `_STRIPPED_IN_SUBSCRIPTION` omits the Bedrock/Vertex routing toggles - partial F1 mitigation
- Vector / evidence: `process.py:78-82` strips `ANTHROPIC_API_KEY`,
  `ANTHROPIC_AUTH_TOKEN`, `AWS_BEARER_TOKEN_BEDROCK` only. C7 rank 1 (highest
  precedence) is *cloud-provider* routing, driven by `CLAUDE_CODE_USE_BEDROCK` /
  `CLAUDE_CODE_USE_VERTEX` (plus the underlying `AWS_*` / `GOOGLE_APPLICATION_
  CREDENTIALS` chain), none of which is stripped or rejected at construction. An
  operator in `subscription` mode with `CLAUDE_CODE_USE_BEDROCK=1` still in the
  environment would have the child silently route to Bedrock and ignore the OAuth
  login - the exact silent-override class F1 targets, at the *highest* precedence
  rank. The original F1 mitigation text explicitly named "Bedrock/Vertex vars".
- Impact: subscription intent silently defeated / billed to a cloud provider; no
  error. Requires the operator to have the toggle set, so narrower than the
  Anthropic-key case, hence MEDIUM not HIGH.
- Mitigation: add `CLAUDE_CODE_USE_BEDROCK` and `CLAUDE_CODE_USE_VERTEX` to
  `_STRIPPED_IN_SUBSCRIPTION` (and ideally mirror them in the construction-time
  `_OUTRANKING_ENV_VARS` presence check). `apiKeyHelper` (C7 rank 4) is a
  `settings.json` script, not an env var, so it cannot be stripped by env
  filtering; document it as an accepted residual in the Task 13.0 setup guide
  (recommend not configuring `apiKeyHelper` alongside `subscription`).

### [MEDIUM] `CLAUDE_CODE_AUTH_MODE=""` crashes settings construction (empty-secret coercion gap)
- Vector / evidence: `config.py:209` `auth_mode: AuthMode = "auto"` has **no**
  `mode="before"` coercer, unlike `binary_path` / `enabled` / `bare` /
  `scratch_cwd`. An unset CI secret expands to `""`
  (`CLAUDE_CODE_AUTH_MODE: ${{ secrets.MISSING }}`); confirmed empirically this
  raises a raw `pydantic.ValidationError` (`literal_error`), which `__init__`
  does **not** unwrap (it only unwraps `ClaudeCodeConfigError`), so it surfaces as
  an unhandled `ValidationError` at collection. This is the exact empty-env
  coercion failure recorded in the reviewer's own memory note.
- Impact: availability/robustness - a zero-config or partially-configured CI run
  crashes at settings construction. Security-wise it fails **closed** (`""` never
  selects `subscription` and never disables a guard), so it is not an escalation
  vector; hence MEDIUM.
- Mitigation: add a `@field_validator("auth_mode", mode="before")` coercer that
  maps an empty/whitespace-only string to `"auto"`, mirroring `_coerce_enabled` /
  `_coerce_bare`. Hand to `python-expert`; add an empty-value regression test to
  `testing-expert`.

### [LOW] `ResolvedCredential.env_passthrough` is computed but not consumed
- Vector / evidence: `resolve_credential` populates `env_passthrough`
  (`process.py:145`) but `_build_child_env` ignores it and instead retains
  `CLAUDE_CODE_OAUTH_TOKEN` implicitly (it is simply not in the strip list). Not a
  vulnerability - the token is still forwarded by inheritance and never
  materialised into a log/event - but the dead field invites a future refactor to
  "use" it in a way that could reintroduce name/value confusion. Recommend either
  consuming it as the single source of truth for what is forwarded, or documenting
  it as diagnostic-only.

## Re-review verdict: BLOCKED

One **CRITICAL** (ReDoS in `_REDACT_RE`) is present; per `.claude/CLAUDE.md` §5 a
CRITICAL finding blocks merge. This build must be kept out of `master` by the
merge-blocking hook / human reviewer until the regex is anchored (one-line fix,
mitigation given and verified) and a ReDoS timing regression test is added. The
two MEDIUM findings (Bedrock/Vertex strip-list gap; `auth_mode` empty-env crash)
should be fixed in the same change but are not independently blocking. All eight
originally required controls are otherwise correctly implemented and verified.

---

# Second re-review (post-remediation) - 2026-08-24

**Mode:** post-remediation verification. The prior re-review (2026-08-25 section)
returned **BLOCKED** on one CRITICAL (ReDoS in `_REDACT_RE`). This pass verifies
each control **against the code**, independently and adversarially - not against
the remediation summary or the tests' names - with a specific mandate to
re-check the regex linearity/correctness judgement, and to hunt for regressions
introduced by the remediation round (empty-`allowed_tools` rejection,
single-resolution credential threading, the new `bare` validator vs. the
`auth_mode` coercer). Evidence below is reproduced from direct execution of the
shipped regex and settings/process code, not from the suite.

## Per-control verification

| Control (finding)                                             | Verdict | Evidence |
|--------------------------------------------------------------|---------|----------|
| **CRITICAL ReDoS in `_REDACT_RE`** (prior blocker)           | **RESOLVED (VERIFIED)** | `aegis_logging.py:57` clause `\b(?:[A-Z0-9]+_)*O?AUTH_TOKEN\s*[=:]\s*\S+`. Measured **linear** on every adversarial shape: `"A"*n` 5k→80k = 1.8→21.7 ms; `("A_")*n` to 80 kB = 40 ms; `("AUTH_")*n` to 100 kB = 48 ms; `(A0_)*n+AUTH_TOKEN` and `X_+A*n` all scale ~linearly (double n ⇒ double time). No super-linear regime found. The `_`-excluded class forces every repetition boundary (unique decomposition ⇒ no backtrack blow-up); `\b` bounds start positions. This is a **structural** linearity, confirmed empirically. |
| Regex redaction **correctness**                              | VERIFIED | Redacts `ANTHROPIC_AUTH_TOKEN=<non-sk>`, both `=`/`: ` forms of `CLAUDE_CODE_OAUTH_TOKEN`, generic `X_OAUTH_TOKEN`, `*_AUTH_TOKEN`, mid-line env-dump occurrences, `ANTHROPIC_API_KEY`, `Authorization: Bearer …`. No false positives: `OAUTH_TOKEN_COUNT=5`, `AUTH_TOKENIZER=1`, prose, `AUTH_TOKENS_REMAINING` pass through untouched. Post-redaction leak scan across three secret shapes: **no secret substring survives**. |
| Possessive `*+` rejection judgement (my prior patch)         | CONFIRMED WRONG (implementer correct) | Independently reproduced: `\b[A-Z0-9_]*+O?AUTH_TOKEN…` returns **no match** on `CLAUDE_CODE_OAUTH_TOKEN=x` - it would have silently disabled redaction. The implemented alternative is the correct fix; my prior suggested patch is retracted. |
| F1 spawn-time filtered `env=` + TOCTOU re-check              | VERIFIED (now complete) | `process.py:664-676,697-738`. Both spawn paths route through `__aenter__`→`_build_child_env` unconditionally (`:667`→`env=child_env` `:675`). Subscription: OAUTH token retained, strip-vars removed, and a spawn-time reappearance of **any** outranking var raises `ambiguous_credential`. |
| Bedrock/Vertex strip-list gap (prior MEDIUM)                 | **RESOLVED (VERIFIED)** | `_STRIPPED_IN_SUBSCRIPTION` (`:88-94`) now includes `CLAUDE_CODE_USE_BEDROCK`/`CLAUDE_CODE_USE_VERTEX`; verified each triggers `ambiguous_credential` at spawn with a fixed, value-free message. |
| `CLAUDE_CODE_AUTH_MODE=""` crash (prior MEDIUM)              | **RESOLVED (VERIFIED)** | `_coerce_auth_mode` (`config.py:382-400`): `""`→`"auto"`; zero/partial-config construction no longer crashes. |
| `env_passthrough` dead field (prior LOW)                    | RESOLVED (documented) | `ResolvedCredential` docstring `:110-119` records it diagnostic-only; forwarding is inheritance-minus-strip, verified independent of the field. |
| F3b probe classifies from exit status/state, never stderr    | VERIFIED | `tool.py:247-279` reads exit code + `result.usage`/`is_error` + `credential.relies_on_stored_login` only; no stderr read in classification. Fixed `_PROBE_FAILURE_MESSAGE`; `ClaudeCodeAuthFailed` carries only closed-set reason + auth_mode. |
| F4 never open/stat/`~/.claude`; no path surfaced             | VERIFIED | No filesystem access in resolver/`_build_child_env`/probe; presence via `os.environ.get` only. Exceptions carry `binary` (operator config) only - no credential-file path. |
| F5 credential never in argv; forwarded by name/inheritance   | VERIFIED | `extra_argv` only ever `("--bare",)` (api_key); token value only enters the child `env=` dict (`:738`), never argv, never an Aegis surface. |
| F6 `--bare` excluded at both layers                          | VERIFIED | Construction reject (`_validate_subscription_mode`/`_validate_bare_requires_api_key`); resolver emits `--bare` only in api_key mode; `build_argv` structurally cannot emit it. |
| F8 two-error distinction (Config vs Unavailable)             | VERIFIED | `exceptions.py`: independent hierarchies, neither subclasses the other. |
| F9 probe own short timeout + dry-run short-circuit           | VERIFIED | `_PROBE_TIMEOUT_S=20.0` (`tool.py:57`), independent `wait_for` (`:222`); `dry_run` returns before spawn (`:213-214`). |
| `auto` behavioural freeze (LOW)                              | VERIFIED | `resolve_credential(auto)` no-op; `_build_child_env` returns `None` for auto/api_key ⇒ `env=None` inherit, Task 03.0 preserved bit-for-bit. |
| Single-resolution credential threading (correctness review)  | VERIFIED (no new seam) | Credential resolved once in `probe_auth` (`:220`), threaded → `_probe_once` → `ClaudeCodeProcess(credential=…)`. `_build_child_env` re-derives filtering from live `os.environ` at spawn and trusts only `credential.mode` (immutable from `settings.auth_mode`); **no credential value is ever cached**, so no stale-credential reuse is possible. `delegate` passes no credential ⇒ resolves fresh at spawn (zero TOCTOU window). Filtered `env=` is applied on **both** paths - never skipped. |
| `bare` validator × `auth_mode` coercer ordering              | VERIFIED (fail-closed) | `mode="before"` coercer resolves `auth_mode=""`→`"auto"` before the `mode="after"` model validators run; `auth_mode=""`+`bare=true` ⇒ loud `ClaudeCodeConfigError` (bare requires api_key), never a raw `literal_error`, never silently accepted. `subscription`+`bare` rejected by the subscription validator (runs first); `api_key`+`bare` accepted. |
| Empty-`allowed_tools` reject vs. zero-config invariant       | VERIFIED (no regression) | Rejection bites **only** an explicit `[]`. Zero-config `ClaudeCodeSettings()`/`OpenHandsSettings()` construct via non-empty `default_factory`; blank env (`CLAUDE_CODE_ALLOWED_TOOLS=""`) coerces to the read-only default. Confirmed both backends default-construct and every prior empty-env var now coerces safely. |
| OpenHands empty-env fixes (`runtime_mode`/timeouts/tools)    | VERIFIED | `OPENHANDS_RUNTIME=""`→`docker` (C8 sandbox direction preserved); `OPENHANDS_CONNECT_TIMEOUT`/`REQUEST_TIMEOUT`/`ALLOWED_TOOLS` blank all coerce to safe defaults; explicit `[]` rejected fail-closed. |
| ReDoS wall-clock regression guard                            | PRESENT | `tests/unit/test_logging.py:467::test_redact_re_redos_wall_clock_bound`. |

## New findings this round

No CRITICAL, HIGH, or MEDIUM finding was introduced by the remediation. Two
non-blocking informational items:

### [LOW] Construction-time `_OUTRANKING_ENV_VARS` still omits the Bedrock/Vertex toggles
- Vector / evidence: `config.py:53` `_OUTRANKING_ENV_VARS = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")` - the construction-time reject does **not** include `CLAUDE_CODE_USE_BEDROCK`/`CLAUDE_CODE_USE_VERTEX`, whereas the spawn-time strip/re-check (`process.py:88-94,729`) does.
- Impact: none to security. A `subscription` config with a stray `CLAUDE_CODE_USE_BEDROCK` **constructs** but then fails **closed** at spawn with `ambiguous_credential` - it never silently routes to Bedrock. The only cost is a later, less-friendly rejection point (a UX asymmetry, not a bypass).
- Mitigation (optional follow-up): mirror the two toggles into `_OUTRANKING_ENV_VARS` so the rejection is reported at construction as well. Not merge-gating.

### [LOW] Spawn-time reappearance check treats `=0`/`=false` toggles as "present"
- Vector / evidence: `process.py:729` uses non-empty-string truthiness (`os.environ.get(name, "").strip()`), so `CLAUDE_CODE_USE_BEDROCK=0` (an operator *disabling* Bedrock) is read as present and raises `ambiguous_credential`.
- Impact: none to security (fails **closed**); a minor availability edge for an operator who explicitly sets a routing toggle to a falsy string under subscription mode. Real-world exposure is small - these toggles are truthy-if-set in Claude Code itself, so `=0` is already an unusual configuration.
- Mitigation (optional follow-up): treat only truthy toggle values as "present" for the routing toggles if the friendlier behaviour is desired; leave the bearer/API-key vars on presence semantics. Not merge-gating.

## Second re-review verdict: PASS

The prior blocking **CRITICAL (ReDoS in `_REDACT_RE`) is resolved** and
independently re-verified: the implemented clause is linear on every adversarial
input I could construct (including the crafted `(AUTH_)*n` / `(A0_)*n+AUTH_TOKEN`
prefix-stress cases), redaction correctness holds across every mandated
variable/value form with no false positives and no secret leakage, and my prior
possessive-quantifier suggestion is confirmed defective (retracted). Both prior
MEDIUMs (Bedrock/Vertex strip-list; `auth_mode=""` crash) and the prior LOW are
closed. The remediation round introduced **no** regression: empty-`allowed_tools`
rejection does not break zero-config construction for either backend; the
single-resolution credential threading applies the filtered `env=` on both the
`delegate` and probe spawn paths and caches no credential value (no stale-reuse
path); and the `bare` validator composes correctly with the `auth_mode` coercer
(fail-closed, correct domain error). No credential value, credential-file path,
or raw `claude` stderr can reach a log sink, exception message, or event payload.

No CRITICAL and no HIGH finding remains. Per `.claude/CLAUDE.md` §5 the merge gate
is **cleared** - the earlier BLOCK is lifted. Two LOW informational items are
optional follow-ups and do not gate merge.
