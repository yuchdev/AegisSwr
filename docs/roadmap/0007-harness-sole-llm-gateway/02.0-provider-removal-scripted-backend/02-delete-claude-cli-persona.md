# 02 — Delete `claude_cli_provider.py`; no-tools `claude_code` persona

**Parent task:** 02.0 Direct-Provider Removal & `ScriptedAIBackend`
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** Task 03.0
**Contracts:** C1, C13

## Objective

Delete `backends/ai/claude_cli_provider.py` (`ClaudeCliBackend`) and
`ClaudeCliSettings`, removing the duplicate wiring of the `claude` binary and the
illegal reach into `aegis_swr.claude_code.process` internals. Re-express its one
legitimate use — "Claude Code as just an LLM, agentic loop stripped" — as a
**no-tools persona** of the existing Milestone-0005 `claude_code` backend.

## Scope

- Delete `backends/ai/claude_cli_provider.py`; remove `ClaudeCliBackend` from
  `backends/ai/__init__.py` (`__all__` and the `settings.provider == "claude_cli"`
  branch).
- Delete `ClaudeCliSettings` from `config/settings.py`; remove the `claude_cli`
  sub-settings field from `AISettings` (coordinate with subtask 03). Any test or
  composition reading `settings.ai.claude_cli` migrates.
- Confirm nothing outside the deleted file imports
  `aegis_swr.claude_code.process._extract_assistant_text` / `_extract_usage` — the
  illegal reach is gone; `claude_code` internals are no longer touched from
  `backends/ai/`.
- **No-tools persona.** Document (in `claude_code/config.py` and, as metadata, in
  the Task 01.0 `agents.yaml` reframe) that `harness_persona="no_tools"` maps to a
  `claude_code` session with an **empty tool allowlist** (`allowed_tools=""`, the
  posture the deleted provider forced via `--restricted`/`--allowedTools ""`). The
  actual persona→allowlist resolution is implemented by the
  `HarnessSessionFactory` in Task 03.0; this subtask only removes the duplicate
  and fixes where the capability now lives.
- `ClaudeCodeSettings` is the **one** Claude-Code config surface (ADR §A.2).

## Constraints

- The no-tools persona must reach a model through the `claude_code` backend's own
  auth (0005 C7) — never through a resurrected direct Claude API call. There is no
  second Claude-Code settings/auth story after this subtask (C1).
- `--dangerously-skip-permissions` and any bypass posture remain rejected at
  `ClaudeCodeSettings` validation (0005 C6); an empty allowlist is *more*
  restrictive, not a bypass.

## Acceptance criteria

- [ ] `claude_cli_provider.py` and `ClaudeCliSettings` are deleted; `ClaudeCliBackend`
      is gone from `backends/ai/__init__.py`.
- [ ] No module imports `claude_cli_provider` or reaches into
      `claude_code.process._extract_*` from `backends/ai/` (C13).
- [ ] The "no agentic loop" case is documented as the `no_tools` persona
      (`allowed_tools=""`) of `claude_code`; `ClaudeCodeSettings` is the sole
      Claude-Code config surface (C1).
- [ ] `ruff` clean; the unit suite is green after the deletion + double.
