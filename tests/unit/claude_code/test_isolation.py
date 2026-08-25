"""Module-isolation invariants for the Claude Code backend (contract C3).

These are the pytest mirror of the CI boundary job (Task 11.0/13.0): they fail
fast locally and under the Stop hook if the C3 isolation boundary drifts. Two
independent rules, each import-statement-aware via :mod:`ast` parsing so a bare
mention of a sibling name in a docstring or comment does not trip the guard:

* No file under ``aegis_swr/claude_code/`` imports ``aegis_swr.openclaude`` or
  ``aegis_swr.openhands`` (C3: no backend imports a sibling).
* ``claude_code/`` imports neither ``grpc`` / ``_pb2`` (OpenClaude's transport)
  nor the OpenHands HTTP/WS client library (``socketio``/``httpx`` in the
  openhands client), since neither belongs in a subprocess-based backend (C3).

Both checks scan source text as an AST and walk only
:class:`ast.Import` / :class:`ast.ImportFrom` nodes.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "aegis_swr"
_PKG = SRC / "claude_code"

#: Sibling backend families that claude_code must not import.
SIBLINGS = frozenset({"openclaude", "openhands"})

#: Transport / client libraries that must not appear in claude_code.
_FORBIDDEN_LIBS = frozenset({"grpc", "socketio", "httpx"})


def _collect_import_modules(py_file: Path) -> list[str]:
    """Return every module name referenced in import statements of *py_file*.

    Walks :class:`ast.Import` and :class:`ast.ImportFrom` nodes only, so
    docstring/comment mentions are invisible to the scanner.

    :param py_file: A Python source file to inspect.
    :return: Flat list of dotted module names seen in import statements.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_claude_code_imports_no_sibling_backend():
    """[Unit] isolation: No file under aegis_swr/claude_code imports a sibling backend family (C3).

    Scenario: every ``*.py`` under ``aegis_swr/claude_code/`` is AST-scanned for
    any import from ``aegis_swr.openclaude`` or ``aegis_swr.openhands`` — the
    cross-family coupling that inverts the Factory-Strategy pattern and would
    require a sibling backend's dependencies to be installed.

    Boundaries: import-statement-aware AST walk; a family name mentioned in a
    docstring or comment does not trip the check. The scanner treats
    ``aegis_swr.<sibling>`` and ``aegis_swr.<sibling>.*`` as offending.

    On failure, first check: the offending file and its cross-family import —
    cross-backend wiring belongs exclusively in ``harness/composition.py``,
    which is the one and only module permitted to import from multiple families.
    """
    offenders: list[str] = []
    for py_file in sorted(_PKG.rglob("*.py")):
        for module in _collect_import_modules(py_file):
            for sibling in SIBLINGS:
                prefix = f"aegis_swr.{sibling}"
                if module == prefix or module.startswith(f"{prefix}."):
                    rel = py_file.relative_to(SRC)
                    offenders.append(f"{rel}: imports {module!r}")
    assert offenders == [], "claude_code imports sibling backend(s) (C3):\n" + "\n".join(offenders)


def test_claude_code_imports_no_grpc_or_openhands_client():
    """[Unit] isolation: claude_code imports neither grpc/_pb2 nor the OpenHands client library (C3).

    Scenario: every ``*.py`` under ``aegis_swr/claude_code/`` is AST-scanned for
    imports of ``grpc`` (OpenClaude's transport), any ``_pb2``-suffixed stub
    module (protobuf generated code), or ``socketio`` / ``httpx`` (the OpenHands
    HTTP/WS client library). None of these dependencies belongs in a
    subprocess-based backend.

    Boundaries: import-statement-aware AST walk; forbidden names in docstrings or
    comments do not count. The check is a substring match on the dotted module
    name so ``grpc.*`` sub-packages and generated ``*_pb2*`` stubs are also caught.

    On failure, first check: the offending import in the ``claude_code`` module —
    ``grpc`` and the OpenHands client library belong to ``openclaude/grpc/`` and
    ``openhands/client.py`` respectively, guarded by the C3 boundary.
    """
    offenders: list[str] = []
    for py_file in sorted(_PKG.rglob("*.py")):
        for module in _collect_import_modules(py_file):
            top = module.split(".")[0]
            if top in _FORBIDDEN_LIBS or "_pb2" in module:
                rel = py_file.relative_to(SRC)
                offenders.append(f"{rel}: imports {module!r}")
    assert offenders == [], "claude_code imports forbidden transport/client library (C3):\n" + "\n".join(offenders)
