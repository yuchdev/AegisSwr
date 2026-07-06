# 04 - Settings composition in top-level config

**Parent task:** 01.0 OpenClaude Settings & Config
**State:** ⬜ Not started
**Depends on:** 01 (`OpenClaudeSettings` Pydantic class)
**Blocks:** 06.0 (App Wiring reads `settings.openclaude`)

## Objective

Wire `openclaude: OpenClaudeSettings` into the top-level settings object
composed in `app.py`, so that `settings.openclaude.grpc_url` is accessible to
Task 06.0's backend-registration logic without that task needing to know how
`OpenClaudeSettings` is constructed.

## Changes

The precise class name of the top-level settings object is determined by the
existing codebase; this subtask must follow its established pattern (whether
that is a Pydantic `BaseSettings` subclass, a dataclass, or a composed
`__init__`). Concretely:

1. Add an `openclaude: OpenClaudeSettings` field to the top-level settings
   object, instantiated via `OpenClaudeSettings()` (which reads
   `OPENCLAUDE_*` env vars per subtask 01) at the same point the object
   composes its other sub-settings (e.g. `router: RouterConfig`).
2. `OpenClaudeSettings` is instantiated exactly once, at application startup,
   by the top-level settings object. It is never re-instantiated during a run.
3. `app.py` must be able to read `settings.openclaude.grpc_url` to decide
   whether to register `OpenClaudeTool` (Task 04.0 provides the registration
   logic and Task 06.0 wires it in; this subtask only ensures the field is
   accessible on the composed settings object).
4. `--dry-run` does not suppress `OpenClaudeSettings` construction; it affects
   whether the tool is exercised, not whether the settings are read. A
   dry-run with `OPENCLAUDE_GRPC_URL` set must still produce a valid
   `OpenClaudeSettings` object.

## Constraints

- No import of `OpenClaudeSettings` may appear in `aegis/core/` or
  `aegis/ui/` (C3) - only the top-level settings-composition module and
  `app.py` reference it.
- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` (C9).
- This subtask does not add any branching on `grpc_url` - that branch belongs
  exclusively to `app.py` in Task 06.0 (C4). This subtask only makes the field
  reachable.

## Success criteria

- [ ] `python -m aegis.app --dry-run` with no env vars set completes without
      raising, with `settings.openclaude.grpc_url is None`.
- [ ] `python -m aegis.app --dry-run` with `OPENCLAUDE_GRPC_URL=localhost:50051`
      set completes without raising, with
      `settings.openclaude.grpc_url == "localhost:50051"`.
- [ ] No import of `OpenClaudeSettings` appears in `aegis/core/` or
      `aegis/ui/`.
- [ ] The top-level settings object's existing fields (e.g. `router`) are
      unaffected - unit tests covering settings composition from earlier
      milestones stay green.
