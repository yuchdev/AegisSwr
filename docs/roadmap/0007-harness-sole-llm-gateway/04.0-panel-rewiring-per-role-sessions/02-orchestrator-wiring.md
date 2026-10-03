# 02 — `Orchestrator` composition-root wiring

**Parent task:** 04.0 Panel Rewiring onto Per-Role Sessions
**State:** ⬜ Not started
**Depends on:** 01 (`resolve_panel` signature)
**Blocks:** 03 (this task), Task 07.0
**Contracts:** C5, C6, C10, C12

## Objective

Construct `Orchestrator` with the `HarnessSessionFactory` at the composition root
and thread it to `resolve_panel`, keeping the LangGraph construction,
`AgentTurn`/event accounting, token tracking, and routing logic structurally
intact.

## Scope

- Replace `Orchestrator.__init__`'s `ai_backend: AIAPIBackend`
  (`core/orchestrator.py:81`) with `session_factory: HarnessSessionFactory`
  (held as `self._session_factory`). The remediation-synthesis path
  (`_synthesize_remediation`, `core/orchestrator.py:589`) that currently builds a
  `RemediationPlannerAgent(self._ai, ...)` is rewired to obtain a session for the
  synthesis role from the factory (a `read_only_context`/payload session, or a
  dedicated `remediation_planner` binding — add one to the Task 01.0 table).
- `_resolve_and_build` (`core/orchestrator.py:313`) passes the factory to
  `resolve_panel`; everything else (`_order_panel`, `_build_graph`,
  `_make_agent_node`, `_arbiter_updates`, `_make_router`) is **unchanged**.
- The composition root (CLI/API wiring) constructs the factory from
  `HarnessSettings` (Task 06.0) + the reframed `RouterConfig` (Task 01.0), opens an
  `AsyncExitStack`, and registers any sidecar-owning sessions for RAII teardown
  (mirrors 0005 C4).
- Token accounting: per-role `last_usage` continues to fold into `token_tracker`
  via the unchanged `_fold_turn` (C10) — the only change is each turn's tokens now
  originate from a per-role session, not a shared backend.
- The `--dry-run` path constructs the full graph and factory but opens no
  session/sidecar outbound call (mirrors 0004/0005 dry-run discipline).

## Constraints

- `_build_graph` and the arbiter/router logic are not edited (C6).
- `continue_investigation` remains the existing `NotImplementedError` stub; this
  task does not change HITL resumption.
- No raw payload/prompt/response in any log sink (C12).

## Acceptance criteria

- [ ] `Orchestrator` is constructed with a `HarnessSessionFactory`; `self._ai` is
      replaced by per-role sessions (C5).
- [ ] `_resolve_and_build` passes the factory to `resolve_panel`; graph-building and
      routing code is unchanged (C6).
- [ ] The synthesis/remediation path obtains its session from the factory (no
      shared backend) (C5).
- [ ] Token totals fold through the unchanged `_fold_turn`/`token_tracker` (C10).
- [ ] `--dry-run` opens no session/sidecar call.
- [ ] `ruff` clean; RST docstrings updated.
