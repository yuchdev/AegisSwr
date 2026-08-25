# Task 04.0 — Claude Code Subscription/Login Authentication

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ✅ Complete (2026-08-24) — all three subtasks; security gate PASS

## Scope

This task adds Claude Code's **second, non-interactive-capable credential
surface** — a Claude.ai subscription login (Pro / Max / Team / Enterprise) — as
an explicit, operator-selectable authentication mode alongside the API-key mode
that Task 03.0 was built against. It implements milestone contract **C7** in
full and touches three files:

- `claude_code/config.py` — extends the `ClaudeCodeSettings` class from
  [Task 02.0](/docs/roadmap/0005-harness-backends/02.0-claude-code-settings/README.md)
  **additively** with a single new `auth_mode` field
  (`CLAUDE_CODE_AUTH_MODE`; `auto` | `api_key` | `subscription`; default
  `auto`), its subscription-mode rejection validator, and the `--bare`
  exclusion rule (subtask 01).
- `claude_code/process.py` / `claude_code/tool.py` — a **credential-resolution
  helper** that, given the resolved `auth_mode`, decides which credential the
  one-shot `claude` subprocess Task 03.0 spawns will actually use, and whether
  `--bare` is eligible (subtask 02); plus a **startup auth-probe** method that
  verifies the resolved credential is usable before the first `delegate()`
  call (subtask 03).
- `claude_code/exceptions.py` — `ClaudeCodeUnavailableError` (runtime auth
  capability failure), kept strictly distinct from `ClaudeCodeConfigError`
  (settings-shape/ambiguity failure). Forward-declared here, import-compatible
  with the canonical definition Task 05.0 places in the same module (subtask
  03).

Because C7 is a credential concern, the whole task is governed by the C13
secrecy discipline: the OAuth token and the credential file's contents are
**never** logged, never included in exception messages, and never appear in
argv (C6).

> This task is a **configuration + settings-validation extension**, sequenced
> deliberately *after* Task 03.0 (the subprocess tool). It extends the same
> subprocess invocation path with a second, mutually exclusive-by-design auth
> surface — per the milestone Sequencing note, "it is not safe to design in
> isolation from how the subprocess is actually spawned." It does **not**
> re-architect the one-shot spawn, the NDJSON parse, argv-safety, or the real
> token accounting that Task 03.0 owns; it only resolves the credential that
> spawn will inherit and probes that it works.

## Assumptions

The design choices below are forced by an **open licensing question that this
milestone does not resolve** (C7, "Licensing caveat"):

- No explicit Anthropic ToS language was found distinguishing **personal**
  (Pro / Max) from **organizational** (Team / Enterprise) subscription seats
  for **non-interactive production automation at scale**. This must be
  confirmed with Anthropic (sales / legal) before `auth_mode="subscription"`
  is used in a production deployment.
- Pending that confirmation, **`subscription` mode ships opt-in only.** The
  `auth_mode` default stays `auto`, which does not force the licensing
  question — an operator who already has Claude Code working keeps working
  unchanged. This opt-in-only default is a **design constraint driven by the
  licensing caveat**, not an incidental choice.
- Writing the operator-facing setup guide that states this caveat in prose is
  [Task 13.0](/docs/roadmap/0005-harness-backends/plan.md)'s job. This task
  only encodes the caveat into the *default* (`auto`) and records it in the
  Assumptions / Constraints here so the constraint travels with the code.
- **Corporate / Enterprise SSO** login uses the **identical** OAuth mechanism
  as a personal Pro / Max login — there is no headless-auth code-path
  difference, so the subscription mode needs no SSO-specific branch. Enterprise
  operators may pin logins via Claude Code's own `forceLoginMethod` /
  `forceLoginOrgUUID` managed-settings; Aegis SWR **does not** configure or
  override these — they are the operator's own Claude Code managed-settings
  concern, exactly as OpenClaude's provider env vars are the operator's
  concern.
- The **environment the subprocess will inherit** is the current process
  environment (`os.environ`): the one-shot `claude` subprocess Task 03.0
  spawns inherits the parent environment by default. "Present in the inherited
  environment" therefore means "set and non-empty in `os.environ`" — an empty
  `ANTHROPIC_API_KEY=""` (a common unset-CI-secret artifact) is treated as
  **absent**, not as an outranking credential.

## Subtasks

| #  | Document                                                                               | State          | Blocks                                                            |
|----|----------------------------------------------------------------------------------------|----------------|-------------------------------------------------------------------|
| 01 | [`auth_mode` field + subscription-mode rejection validator](01-auth-mode-field.md)     | ✅ Complete    | 02, 03                                                            |
| 02 | [Credential-resolution helper (`process.py` / `tool.py`)](02-credential-resolution.md) | ✅ Complete    | 03                                                                |
| 03 | [Startup auth-probe + `ClaudeCodeUnavailableError` distinction](03-auth-probe.md)      | ✅ Complete    | 05.0 (canonical `exceptions.py`), 10.0 (`aegis code-intel check`) |

Subtask 01 lands first (it fixes the `auth_mode` field shape and the two
construction-time rejections). Subtask 02 consumes the resolved `auth_mode` to
build the subprocess credential surface. Subtask 03 depends on both: it probes
the credential subtask 02 resolves and surfaces failures as the runtime error
kept distinct from subtask 01's config error.

## Key constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- **Two distinct failure surfaces, never conflated (C7):** `ClaudeCodeConfigError` is raised at **settings-construction time** for a config-shape / ambiguity fault (e.g. `subscription` + a present `ANTHROPIC_API_KEY`); `ClaudeCodeUnavailableError` is raised at **health-check / composition time** when the resolved credential is not actually usable. Neither subclasses the other.
- **Secrecy (C7 / C13):** no OAuth token, no `CLAUDE_CODE_OAUTH_TOKEN` value, no credential-file contents, and no `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` value ever reaches a log sink, an exception message, an argv element, or a `claude_code.auth_failed` event payload. `SensitiveFilter` covers every sink.
- **`auto` (default) is behaviourally frozen (C7):** when `auth_mode="auto"`, this task adds **no** validation, **no** credential branching, and **no** probe-forced behaviour beyond what Task 03.0 already shipped — the Task 03.0 acceptance criteria must remain green untouched.
- `--bare` is **never** emitted when `auth_mode="subscription"` (bare mode never reads OAuth / login credentials at all, C7); it **may** be emitted only in `api_key` mode.
- This task imports **no** sibling backend package; it stays entirely within `aegis_swr/claude_code/` (C3).

## Files created or modified by this task

```
src/aegis_swr/
└── claude_code/
    ├── config.py        ← modified (subtask 01): +auth_mode field, subscription rejection validator, --bare exclusion rule
    ├── process.py       ← modified (subtask 02): credential-resolution helper feeding the Task 03.0 subprocess env/argv
    ├── tool.py          ← modified (subtask 02, 03): consumes resolved credential; adds the startup auth-probe method
    └── exceptions.py    ← modified (subtask 03): ClaudeCodeUnavailableError (auth-capability failures), forward-declared, import-compatible with Task 05.0's canonical module

tests/unit/claude_code/
└── test_auth_modes.py   ← NEW (Task 11.0, incremental): C7 matrix — ambiguous- credential rejection, --bare exclusion, CLAUDE_CODE_OAUTH_TOKEN precedence, probe outcomes, no-secret-in-logs assertions
```

> `tests/unit/claude_code/test_auth_modes.py` is authored under **Task 11.0**
> (incrementally, alongside this task, per the milestone's testing convention);
> it is listed here to name the coverage this task's behaviour requires.
