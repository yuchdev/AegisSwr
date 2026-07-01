# 03 - Scaffold `forensic/` & `synthesis/` packages

**Parent task:** 01.0 Agent Package Restructure
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 04

## Objective

Create the two empty category subpackages that Tasks 03.0–07.0 will populate, and
record the category convention so future agents land in the right place.

## Files

- **Create** `src/aegis_swr/agents/forensic/__init__.py`
- **Create** `src/aegis_swr/agents/synthesis/__init__.py`

## Changes

1. `agents/forensic/__init__.py` - empty package marker with an `__all__ = []`
   and a one-line module docstring:

   ```python
   """Forensic specialist agents (deep, fault-domain-specific debate voters)."""

   __all__: list[str] = []
   ```

2. `agents/synthesis/__init__.py` - same shape:

   ```python
   """Synthesis-tier agents that run once after the debate converges."""

   __all__: list[str] = []
   ```

   As each agent lands, its task adds the class to the relevant `__all__` and
   import line (forensic agents in Task 03.0–06.0, the planner in Task 07.0).

## Category convention (record in the package docstrings)

| Category    | Package              | Tier        | Joins debate panel? | Weighted voter? |
|-------------|----------------------|-------------|---------------------|-----------------|
| `base`      | `agents/base/`       | debate      | yes (default panel) | yes             |
| `forensic`  | `agents/forensic/`   | debate      | yes (per fault)     | yes             |
| `synthesis` | `agents/synthesis/`  | post-debate | no                  | no              |

This matches the `category` `ClassVar` introduced on `BaseAgent` in Task 02.0.

## Constraints

- Packages stay importable but empty; no agent classes in this subtask.
- `Optional[T]` / mypy / ruff conventions clean.

## Tests

- Extend `tests/unit/test_agents_package.py`:
  - `test_forensic_package_importable` - `import aegis_swr.agents.forensic`.
  - `test_synthesis_package_importable` - `import aegis_swr.agents.synthesis`.

## Success criteria

- [ ] `agents/forensic/` and `agents/synthesis/` exist as importable packages.
- [ ] Both expose an empty `__all__` and a category docstring.
- [ ] `mypy src/` clean.
