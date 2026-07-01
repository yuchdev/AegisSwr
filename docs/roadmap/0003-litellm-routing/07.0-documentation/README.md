# Task 07.0 - Documentation & CI

**Parent milestone:** [Milestone 0003 - LiteLLM Model Router](/docs/roadmap/0003-litellm-routing/plan.md)
**Status:** ⬜ Not started

## Scope

Author the two new documentation files (`docs/config-reference.md`,
`docs/router-architecture.md`), update `README.md` and `CHANGELOG.md`, wire
the router test suite and litellm isolation check into CI, and close out the
milestone (flip `status.md` to complete, verify the decomposition tree).

## Subtasks

| #  | Document                                                      | Status        | Blocks |
|----|---------------------------------------------------------------|---------------|--------|
| 01 | [docs/config-reference.md](01-config-reference.md)            | ⬜ Not started | -      |
| 02 | [docs/router-architecture.md](02-router-architecture.md)      | ⬜ Not started | -      |
| 03 | [README.md update + CHANGELOG.md](03-readme-and-changelog.md) | ⬜ Not started | -      |
| 04 | [CI pipeline additions](04-ci-configuration.md)               | ⬜ Not started | -      |
| 05 | [milestone closeout](05-milestone-closeout.md)                | ⬜ Not started | -      |

## Key constraints

- `docs/config-reference.md` must cover: `providers` block (all keys, env-var
  resolution, optional fields), `agents` block (model string format, fallback,
  timeout_s, retry), step-by-step guides for adding a new provider and a new
  agent role without code changes.
- `docs/router-architecture.md` must include: ASCII architecture diagram,
  complete `RouterEvent` taxonomy, boundary contract (what `aegis/core/` may
  and may not import), fallback/retry semantics, how to add an event subscriber.
- The CI lint step `pytest tests/router/test_client.py::test_litellm_is_only_imported_in_client`
  must be its own named CI job so litellm drift breaks the build visibly.
- Milestone closeout requires: all 7 task rows in `status.md` flipped to ✅,
  final directory tree matches the file map in `plan.md`, and `docs/README.md`
  index updated.
