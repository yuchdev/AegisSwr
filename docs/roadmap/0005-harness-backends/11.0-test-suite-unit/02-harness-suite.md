# 02 - `tests/unit/harness/` suite

**Parent task:** 11.0 Test Suite — Unit
**State:** ✅ Complete
**Depends on:** 01 (shared fixtures), 01.0 (`HarnessSettings`,
`HarnessConfigError`, `HarnessUnavailableError`), 10.0
(`harness/composition.py` — `create_code_intel_backend`; the deleted
`openclaude/composition.py` whose tests are re-targeted here).
**Blocks:** none

## Objective

Verify the neutral harness layer: `HarnessSettings` resolves the **full C2
selection truth table** at settings-construction time, `create_code_intel_backend`
is the **sole C4 branch** across all three families (with `dry_run` orthogonal to
selection, exactly as 0004), and the C3 isolation posture holds as an
**import-statement-aware** pytest test. The C2 matrix is the load-bearing part of
this task: it must preserve 0004's closing guarantee (an `OPENCLAUDE_GRPC_URL`-only
deployment auto-selects OpenClaude with zero further changes) while adding the two
new failure modes (multiple-signal ambiguity → `HarnessConfigError` at
construction; explicitly-selected-but-absent → `HarnessUnavailableError` at
composition). Everything runs in-process with no network, subprocess, or binary.

## File: `tests/unit/harness/test_config.py`

```python
from __future__ import annotations

import pytest

from aegis_swr.harness.config import HarnessSettings
from aegis_swr.harness.exceptions import HarnessConfigError


# --- C2 row 1: selector unset + zero signals --------------------------------

def test_unset_selector_zero_signals_no_backend(env_no_signals):
    """Selector unset + 0 signals → active_backend is None, no exception (0004 C4)."""


# --- C2 row 2: selector unset + exactly one signal (auto-select) ------------

def test_unset_selector_openclaude_only_auto_selects(env_openclaude_only):
    """OPENCLAUDE_GRPC_URL-only → active_backend == 'openclaude'; preserves the 0004 guarantee."""

def test_openclaude_only_needs_zero_further_changes(env_openclaude_only):
    """An OPENCLAUDE_GRPC_URL-only environment constructs and resolves with no other var set."""

def test_unset_selector_claude_code_only_auto_selects(env_claude_code_only):
    """CLAUDE_CODE_ENABLED=true only → active_backend == 'claude_code'."""

def test_unset_selector_openhands_only_auto_selects(env_openhands_only):
    """OPENHANDS_SERVER_URL only → active_backend == 'openhands'."""


# --- C2 row 3: selector unset + more than one signal (ambiguity) ------------

def test_unset_selector_multiple_signals_raises_config_error(env_multiple_signals):
    """Selector unset + >1 signals → HarnessConfigError at construction time (loud, never silent)."""

def test_config_error_names_signals_seen_no_secret(env_multiple_signals):
    """HarnessConfigError carries the set of signals seen but NO url/token/payload text (C13)."""


# --- C2 row 4: selector set to X, X's signal present ------------------------

def test_selector_openclaude_with_signal_selects_openclaude(env_openclaude_only, monkeypatch):
    """AEGIS_CODE_INTEL_BACKEND=openclaude + its signal present → 'openclaude'."""

def test_selector_claude_code_with_signal_selects_claude_code(env_claude_code_only, monkeypatch):
    """AEGIS_CODE_INTEL_BACKEND=claude_code + its signal present → 'claude_code'."""

def test_selector_openhands_with_signal_selects_openhands(env_openhands_only, monkeypatch):
    """AEGIS_CODE_INTEL_BACKEND=openhands + its signal present → 'openhands'."""

def test_selector_overrides_other_present_signal(monkeypatch):
    """Explicit selector wins even when a DIFFERENT backend's signal is also present (no ambiguity error)."""


# --- C2 row 5: selector set to X, X's signal absent -------------------------
# (resolves at composition/health-check time, NOT settings construction —
#  see test_composition.py::test_selected_backend_signal_absent_raises_unavailable)

def test_selector_set_signal_absent_constructs_without_config_error(env_no_signals, monkeypatch):
    """AEGIS_CODE_INTEL_BACKEND=claude_code with its signal absent → settings construct OK (no HarnessConfigError); the failure is deferred to composition."""

def test_invalid_selector_value_raises_config_error(monkeypatch):
    """AEGIS_CODE_INTEL_BACKEND=bogus → HarnessConfigError (enum-validated field)."""
```

## File: `tests/unit/harness/test_composition.py`

```python
from __future__ import annotations

from contextlib import AsyncExitStack

import pytest

from aegis_swr.harness.composition import create_code_intel_backend
from aegis_swr.harness.exceptions import HarnessUnavailableError


async def test_no_backend_returns_backendless_agent(env_no_signals):
    """active_backend None → a CodeAgent with capability unavailable; no fallback (0004 parity)."""

async def test_openclaude_path_assembles_unchanged_stack(env_openclaude_only):
    """'openclaude' → the moved-verbatim OpenClaude stack (client→process→tool) is assembled and registered on the AsyncExitStack."""

async def test_claude_code_path_assembles_tool_no_sidecar(env_claude_code_only):
    """'claude_code' → ClaudeCodeTool assembled; nothing entered on the AsyncExitStack (no sidecar)."""

async def test_openhands_path_registers_sidecar_on_exit_stack(env_openhands_only):
    """'openhands' → OpenHands stack assembled; sidecar registered on the caller's AsyncExitStack for RAII teardown."""

async def test_selected_backend_signal_absent_raises_unavailable(env_no_signals, monkeypatch):
    """Selector=claude_code with its signal absent → HarnessUnavailableError at composition/health-check time (C2 row 5)."""

async def test_dry_run_constructs_graph_without_entering_sidecar(env_openhands_only):
    """dry_run: graph fully built + backend registered, but no sidecar entered and no outbound call (dry_run orthogonal to selection)."""

async def test_composition_is_sole_branch_on_active_backend(env_no_signals):
    """create_code_intel_backend is the only place branching on which backend is active (C4)."""
```

## File: `tests/unit/harness/test_isolation.py`

```python
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "aegis_swr"
FAMILIES = {"openclaude", "claude_code", "openhands"}


def _imported_modules(py_file: Path) -> set[str]:
    """Return the top-level aegis_swr.* modules a file imports (AST-based).

    Import-statement-aware: only ``import``/``from ... import`` nodes are read,
    so a family name mentioned in a docstring or comment does NOT count. This is
    the pytest form of 0004's ``openclaude-isolation`` grep check.
    """
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _families_imported(py_file: Path) -> set[str]:
    """The set of backend families a file imports from aegis_swr.*."""
    fams: set[str] = set()
    for mod in _imported_modules(py_file):
        for fam in FAMILIES:
            if mod == f"aegis_swr.{fam}" or mod.startswith(f"aegis_swr.{fam}."):
                fams.add(fam)
    return fams


def test_no_backend_package_imports_a_sibling():
    """No file under a backend family imports a sibling family (C3)."""

def test_composition_is_only_multi_family_importer():
    """harness/composition.py is the ONLY module importing more than one family (C3)."""

def test_core_views_code_intel_import_no_backend():
    """aegis_swr/core, /views, /code_intel import none of the three families or grpc (C3)."""
```

## Test cases

| Test                                                              | Contract verified                                                                           |
|-------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| `test_unset_selector_zero_signals_no_backend`                     | C2 row 1: unset + 0 signals → `active_backend is None`, no raise (0004 C4)                  |
| `test_unset_selector_openclaude_only_auto_selects`                | C2 row 2: single `OPENCLAUDE_GRPC_URL` signal auto-selects OpenClaude                       |
| `test_openclaude_only_needs_zero_further_changes`                 | **0004 closing guarantee** preserved verbatim — no other var required                       |
| `test_unset_selector_claude_code_only_auto_selects`               | C2 row 2: single `CLAUDE_CODE_ENABLED` signal auto-selects Claude Code                      |
| `test_unset_selector_openhands_only_auto_selects`                 | C2 row 2: single `OPENHANDS_SERVER_URL` signal auto-selects OpenHands                       |
| `test_unset_selector_multiple_signals_raises_config_error`        | C2 row 3: >1 signal + unset selector → `HarnessConfigError` **at construction**             |
| `test_config_error_names_signals_seen_no_secret`                  | C2/C13: error carries signal names only, never a url/token/payload value                    |
| `test_selector_openclaude_with_signal_selects_openclaude`         | C2 row 4: explicit selector + matching signal → that backend                                |
| `test_selector_claude_code_with_signal_selects_claude_code`       | C2 row 4 (claude_code)                                                                      |
| `test_selector_openhands_with_signal_selects_openhands`           | C2 row 4 (openhands)                                                                        |
| `test_selector_overrides_other_present_signal`                    | C2: explicit selector suppresses the multi-signal ambiguity error                           |
| `test_selector_set_signal_absent_constructs_without_config_error` | C2 row 5: deferred failure — construction does **not** raise `HarnessConfigError`           |
| `test_invalid_selector_value_raises_config_error`                 | C1: `backend` is enum-validated; unknown value → `HarnessConfigError`                       |
| `test_no_backend_returns_backendless_agent`                       | C4 step 2: `None` → backend-less `CodeAgent`, no fallback                                   |
| `test_openclaude_path_assembles_unchanged_stack`                  | C4 step 3: OpenClaude stack moved **verbatim** from the deleted `openclaude/composition.py` |
| `test_claude_code_path_assembles_tool_no_sidecar`                 | C4 step 4: Claude Code tool, nothing on the `AsyncExitStack`                                |
| `test_openhands_path_registers_sidecar_on_exit_stack`             | C4 step 5: OpenHands sidecar registered for RAII teardown                                   |
| `test_selected_backend_signal_absent_raises_unavailable`          | C2 row 5: `HarnessUnavailableError` at composition/health-check time                        |
| `test_dry_run_constructs_graph_without_entering_sidecar`          | C4/C13: dry-run builds the graph, enters no sidecar, makes no outbound call                 |
| `test_composition_is_sole_branch_on_active_backend`               | C4: the one-and-only backend-selection branch lives here                                    |
| `test_no_backend_package_imports_a_sibling`                       | C3: no family imports a sibling family                                                      |
| `test_composition_is_only_multi_family_importer`                  | C3: `harness/composition.py` is the sole multi-family importer                              |
| `test_core_views_code_intel_import_no_backend`                    | C3: scaffolding imports no backend family and no `grpc`                                     |

## Implementation notes

- The C2 tests drive `HarnessSettings` through the shared `env_*` fixtures
  (subtask 01) so the truth table is expressed one env-scenario per test. Rows
  1–3 assert on `HarnessSettings` construction alone; rows 4–5 that require the
  explicit selector set `AEGIS_CODE_INTEL_BACKEND` via the test's own
  `monkeypatch` on top of the signal fixture.
- Row 5 is deliberately split across the two files: `test_config.py` proves
  construction does **not** raise `HarnessConfigError`; `test_composition.py`
  proves `HarnessUnavailableError` is raised at composition/health-check time.
  This is the exact "config-shape vs runtime-capability" distinction of C2.
- `test_composition.py` uses the shared `mock_claude_subprocess` /
  `mock_openhands_client` / `mock_event_bus` seams and a real `AsyncExitStack`;
  it asserts on **which** collaborators the returned agent holds and on
  `AsyncExitStack` registration, never on any live process.
- `test_openclaude_path_assembles_unchanged_stack` re-targets the deleted
  `openclaude/composition.py`'s own former tests — assert the same stack shape the
  0004 factory produced, now built by `create_code_intel_backend`.
- `test_isolation.py` is **AST-based** (`ast.parse` + walk of `Import` /
  `ImportFrom`), not text grep, so a family name in a docstring or comment does
  not trip it. It walks every `*.py` under `src/aegis_swr/` and classifies which
  families each file imports.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new unit test has a test-specific docstring (`[Unit]`|`[Mock]`|`[Integration]`|`E2E` / `Scenario` / `Boundaries` / `On failuse`)
- All tests pass with `AEGIS_CODE_INTEL_BACKEND` unset, all signals unset, and no binary / Docker / server available — no network, subprocess, or container.
- `monkeypatch` is used **only** to set/clear real env vars the settings read — never to patch a module-level global or class attribute.
- Assert on `HarnessConfigError` / `HarnessUnavailableError` (the canonical 01.0 types), not Pydantic's `ValidationError` — 01.0 unwraps to the project errors.
- No exception message or error payload asserted in the C2 tests may contain a url, token, or payload value — only field/backend/signal **names** (C13).
- `test_isolation.py` imports no backend family itself; it reads source files as text and parses them, so it introduces no import coupling.

## Success criteria

- [ ] All five C2 truth-table rows are covered; the `OPENCLAUDE_GRPC_URL`-only auto-select and the "zero further changes" guarantee each have a dedicated passing test.
- [ ] Multiple-signal ambiguity asserts `HarnessConfigError` **at construction**; selected-but-absent asserts `HarnessUnavailableError` **at composition**.
- [ ] `test_config_error_names_signals_seen_no_secret` asserts the error string contains signal **names** and contains no configured url/token value.
- [ ] `test_composition.py` covers all five C4 assembly outcomes plus the dry-run orthogonality path.
- [ ] `test_isolation.py` passes AST-based (not grep) and would **fail** if any backend package imported a sibling or a second family were imported outside `harness/composition.py`.
- [ ] No `grpc` / `_pb2` / OpenHands-client import in any file of this suite.
- [ ] `ruff check src/ tests/` - clean.
