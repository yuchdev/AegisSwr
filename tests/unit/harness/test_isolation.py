"""Module-isolation invariants for the neutral harness layer (contract C3).

These are the pytest mirror of the CI boundary jobs (Task 11.0/13.0): they fail
fast locally and under the Stop hook if the isolation boundary drifts. Three
independent rules, each import-statement-aware via :mod:`ast` parsing so a bare
mention of a family name in a docstring or comment does not trip the guard:

* No file under a backend family package imports a sibling backend package (C3).
* :file:`harness/composition.py` is the **only** module permitted to import more
  than one backend family's **runtime** classes (tool / process / client / gRPC).
  :file:`harness/config.py` is allowlisted to import all three families'
  **settings classes only** per the 2026-08-24 C3 amendment (C1 requires
  :class:`~aegis_swr.harness.config.HarnessSettings` to nest all three via
  ``default_factory``); the test encodes that distinction by additionally
  asserting ``harness/config.py`` imports no runtime submodule.
* :file:`aegis_swr/core/`, :file:`/views/`, and :file:`/code_intel/` import
  **none** of the three backend families or ``grpc`` / ``_pb2`` (C3).

All three checks scan source text as an AST and walk only
:class:`ast.Import` / :class:`ast.ImportFrom` nodes.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "aegis_swr"

#: The three code-intelligence backend family names.
FAMILIES = frozenset({"openclaude", "claude_code", "openhands"})

#: Runtime submodule names that harness/config.py must NOT import (C3 amendment).
#: Importing any of these from a family package pulls in the client library or
#: a real subprocess dependency, defeating the settings-only allowlist.
_RUNTIME_SUBMODULES = frozenset({"tool", "process", "client", "grpc"})


def _families_imported(py_file: Path) -> frozenset[str]:
    """Return every backend family a file imports via AST node walk.

    Walks only ``import`` / ``from ... import`` AST nodes so family names in
    docstrings, comments, and string literals do not trigger the check.

    :param py_file: A Python source file to inspect.
    :return: The subset of :data:`FAMILIES` that ``py_file`` imports from.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    fams: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for fam in FAMILIES:
                    if alias.name == f"aegis_swr.{fam}" or alias.name.startswith(f"aegis_swr.{fam}."):
                        fams.add(fam)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for fam in FAMILIES:
                prefix = f"aegis_swr.{fam}"
                if node.module == prefix or node.module.startswith(f"{prefix}."):
                    fams.add(fam)
    return frozenset(fams)


def _runtime_family_imports(py_file: Path) -> list[str]:
    """Return every runtime-submodule import from a backend family in *py_file*.

    A "runtime import" is any ``from aegis_swr.<family>.<submod> import ...``
    where *submod* is one of ``tool``, ``process``, ``client``, ``grpc``.

    :param py_file: A Python source file to inspect.
    :return: The offending dotted module names; empty when the file is clean.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for fam in FAMILIES:
                prefix = f"aegis_swr.{fam}."
                if node.module.startswith(prefix):
                    # e.g. "aegis_swr.openclaude.tool" → submod = "tool"
                    submod = node.module[len(prefix) :].split(".")[0]
                    if submod in _RUNTIME_SUBMODULES:
                        offenders.append(node.module)
    return offenders


def _grpc_or_pb2_imported(py_file: Path) -> bool:
    """Return True if *py_file* imports ``grpc`` or any ``_pb2`` module.

    :param py_file: A Python source file to inspect.
    :return: Whether the file imports gRPC or generated protobuf stubs.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "grpc" or "_pb2" in alias.name:
                    return True
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "grpc" or "_pb2" in node.module or node.module.startswith("grpc."))
        ):
            return True
    return False


def test_no_backend_package_imports_a_sibling():
    """[Unit] isolation: No file under a backend family imports a sibling family (C3).

    Scenario: every ``*.py`` under each backend package (``openclaude``,
    ``claude_code``, ``openhands``) is AST-scanned for imports from any OTHER
    backend family package — the cross-family coupling that breaks the
    Factory-Strategy pattern.

    Boundaries: import-statement-aware AST walk; docstring mentions of a sibling
    family do not trip the check. Skips packages absent from the source tree
    (allows partial checkouts without false positives).

    On failure, first check: the offending file and its cross-family import — the
    fix is to move shared code to ``code_intel/`` or route through the harness
    composition root, never sideways across backend sibling packages.
    """
    offenders: list[str] = []
    for family in FAMILIES:
        pkg_dir = SRC / family
        if not pkg_dir.exists():
            continue
        for py_file in sorted(pkg_dir.rglob("*.py")):
            imported = _families_imported(py_file)
            siblings = imported - {family}
            if siblings:
                rel = py_file.relative_to(SRC)
                offenders.append(f"{rel} imports sibling(s): {sorted(siblings)}")
    assert offenders == [], "\n".join(offenders)


def test_composition_is_only_runtime_multi_family_importer():
    """[Unit] isolation: Only harness/composition.py imports multiple families' runtime classes (C3).

    Scenario: every ``*.py`` under ``src/aegis_swr/`` is scanned for imports from
    two or more backend family packages. The allowed multi-family importers are:

    * ``harness/composition.py`` — imports all three families' runtime classes
      (tool / process / client / gRPC) because it is the C4 composition root.
    * ``harness/config.py`` — **settings-only** allowlist per the 2026-08-24 C3
      amendment: it imports all three families' settings classes to compose
      :class:`~aegis_swr.harness.config.HarnessSettings` via ``default_factory``,
      but must import no runtime submodule (tool / process / client / grpc).

    No other module may import from 2+ families. This is an AST scan, so docstring
    mentions do not count.

    Boundaries: the C3 amendment distinction is encoded as a separate runtime-import
    assertion on ``harness/config.py`` rather than a blanket single-module rule.

    On failure, first check:
    - A new multi-family importer appeared outside the harness → move the
      import into ``harness/composition.py`` or ``harness/config.py``.
    - ``harness/config.py`` grew a runtime import → revert to a settings-class-only
      import (the runtime class belongs in ``composition.py``).
    """
    composition_path = SRC / "harness" / "composition.py"
    config_path = SRC / "harness" / "config.py"

    # Allowed files that may import from multiple families
    multi_family_allowlist = {composition_path, config_path}

    unexpected: list[str] = []
    for py_file in sorted(SRC.rglob("*.py")):
        imported = _families_imported(py_file)
        if len(imported) < 2:
            continue
        if py_file not in multi_family_allowlist:
            rel = py_file.relative_to(SRC)
            unexpected.append(f"{rel} imports {len(imported)} families: {sorted(imported)}")

    assert unexpected == [], "Module(s) outside the harness import multiple backend families (C3):\n" + "\n".join(
        unexpected
    )

    # C3 amendment: harness/config.py must import no runtime submodule.
    if config_path.exists():
        runtime_imports = _runtime_family_imports(config_path)
        assert runtime_imports == [], (
            "harness/config.py imports runtime family submodule(s) (C3 amendment — settings only):\n"
            + "\n".join(runtime_imports)
        )


def test_core_views_code_intel_import_no_backend():
    """[Unit] isolation: aegis_swr/core, /views, /code_intel import no backend family or grpc (C3).

    Scenario: every ``*.py`` under the three scaffolding packages is AST-scanned
    for any import from ``aegis_swr.openclaude``, ``aegis_swr.claude_code``,
    ``aegis_swr.openhands``, ``grpc``, or ``_pb2``.

    Boundaries: import-statement-aware AST walk; docstring mentions do not count.
    Packages absent from the source tree are skipped without error.

    On failure, first check: the offending import in the scaffolding file — the
    backend must be injected into :class:`~aegis_swr.code_intel.agent.CodeAgent`
    by the harness composition root, never imported directly by ``core/``,
    ``views/``, or ``code_intel/``.
    """
    family_offenders: list[str] = []
    grpc_offenders: list[str] = []

    for package in ("core", "views", "code_intel"):
        pkg_dir = SRC / package
        if not pkg_dir.exists():
            continue
        for py_file in sorted(pkg_dir.rglob("*.py")):
            imported = _families_imported(py_file)
            if imported:
                rel = py_file.relative_to(SRC)
                family_offenders.append(f"{rel} imports backend family: {sorted(imported)}")
            if _grpc_or_pb2_imported(py_file):
                rel = py_file.relative_to(SRC)
                grpc_offenders.append(f"{rel} imports grpc/_pb2")

    assert family_offenders == [], "Scaffolding package(s) import a backend family (C3):\n" + "\n".join(
        family_offenders
    )
    assert grpc_offenders == [], "Scaffolding package(s) import grpc/_pb2 (C3):\n" + "\n".join(grpc_offenders)
