# 05 - Milestone closeout

**Parent task:** 07.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 01, 02, 03, 04 (all documentation complete)
**Blocks:** -

## Objective

Verify the milestone is fully delivered, flip all status rows to ✅, run the
final regression suite, and update `docs/README.md`.

## Checklist

### Code gates

- [ ] `poetry run pytest tests/unit/ tests/router/ -q` - green, same or higher
      count than pre-milestone baseline.
- [ ] `poetry run pytest tests/integration/ -m integration -q` - skipped (not
      failed) when API keys are absent.
- [ ] `mypy src/` (strict) - zero errors.
- [ ] `ruff check src/ tests/` - clean.
- [ ] `python scripts/replace_optional.py --check` - clean.
- [ ] CI litellm isolation grep: exactly one hit in `aegis/router/client.py`.
- [ ] `python -m aegis.app --dry-run` - completes without error or API keys.

### Structural gates

- [ ] `aegis/router/` directory exists with `__init__.py`, `config.py`,
      `client.py`, `router.py`, `events.py`, `exceptions.py`, `null_client.py`.
- [ ] `tests/router/` directory exists with `test_config.py`, `test_client.py`,
      `test_router.py`, and `mocks/`.
- [ ] `tests/integration/test_router_integration.py` exists.
- [ ] `docs/config-reference.md` and `docs/router-architecture.md` exist.
- [ ] `aegis/core/agents/` has no `import anthropic / openai / deepseek`.

### Documentation gates

- [ ] `docs/README.md` index links to `docs/config-reference.md` and
      `docs/router-architecture.md`.
- [ ] `README.md` has a **Model Configuration** section.
- [ ] `CHANGELOG.md` `[Unreleased]` entry covers this milestone.

### Status file update

Flip all 7 task rows in
`docs/roadmap/0003-litellm-routing/status.md` to ✅ and add a per-task
"Delivered" summary (mirror the format used in Milestone 0002's `status.md`).

## Success criteria

- [ ] All checklist items above pass.
- [ ] `status.md` shows all tasks as ✅.
- [ ] `docs/roadmap/README.md` (or the roadmap index) updated to show
      Milestone 0003 as complete.
