# 01 — MCP server scaffolding + tool registration

**Parent task:** 05.0 Aegis MCP Tool Surface
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03, 04, 05 (this task)
**Contracts:** C8, C13, C12

## Objective

Stand up `aegis_swr/mcp/` with the MCP server scaffolding and a tool-registration
seam, isolated so `core/`/`views/`/`code_intel/` never import it, with
`SensitiveFilter` on every sink from the first line.

## Scope

- Create the `aegis_swr/mcp/` package: `__init__.py`, `server.py` (the server /
  tool-registry), `tools.py` (tool function stubs filled by subtasks 02–04),
  `redaction.py` (subtask 05).
- `server.py` exposes an `AegisMcpServer` that registers the four tools (name,
  input schema, handler) and runs over a transport chosen for the single-process
  deployment (stdio or an in-process transport — the harness session connects as an
  MCP client). The transport detail is the operator's/harness's concern (mirrors
  0004's black-box harness-model contract); Aegis only registers tools and enforces
  redaction + authz.
- Every tool handler is wrapped so its result passes through `redaction.py`
  (subtask 05) before leaving the process — the registration seam enforces this
  centrally so no individual tool can bypass it.
- Isolation (C13): a grep/pytest check (Task 08.0/10.0) asserts `core/`, `views/`,
  and `code_intel/` import no `aegis_swr.mcp` server module; the MCP client wiring
  lives only at the composition root / `harness/session.py`.
- Loguru `SensitiveFilter` on every sink in the package; the server logs only tool
  names + run ids + status, never arguments or results (C12).

## Constraints

- No incident content is logged; tool arguments (which may carry payload-referencing
  ids) are logged only as redacted/opaque handles (C12).
- Every tool call has a timeout and a defined failure path (C12).

## Acceptance criteria

- [ ] `aegis_swr/mcp/` exists with `server.py`, `tools.py`, `redaction.py`,
      `__init__.py`.
- [ ] `AegisMcpServer` registers the four tools through a seam that forces every
      result through `redaction.py` (C8).
- [ ] `core/`, `views/`, `code_intel/` import no `aegis_swr.mcp` server module
      (C13).
- [ ] `SensitiveFilter` on every sink; server logs only names/ids/status (C12).
- [ ] Every tool call has a timeout + defined failure path.
- [ ] `ruff` clean; RST docstrings.
