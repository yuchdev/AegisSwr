"""Module-isolation invariants for the OpenClaude integration (contract C3).

These are the pytest mirror of the CI ``grep`` boundary job (Task 09.0): they
fail fast in local runs and under the Stop hook if the isolation boundary drifts,
before CI catches it. Two independent rules:

* ``grpc`` and the generated ``*_pb2`` stubs may be *imported* only by
  ``aegis_swr/openclaude/grpc/client.py`` (the generated proto modules under
  ``grpc/proto/`` legitimately contain ``grpc``/``_pb2`` as generated code and
  are excluded).
* ``aegis_swr.openclaude`` must never be imported by the isolated modules
  ``core/``, ``views/`` (the UI layer), or ``code_intel/`` — the concrete
  backend is injected by the ``openclaude/composition.py`` factory, never
  imported by the scaffolding.

Scanning is import-statement-aware (it matches ``import``/``from`` lines only),
so a bare mention of ``grpc`` in a docstring does not trip the guard — matching
the Milestone 0003 ``litellm`` isolation test convention.
"""

from __future__ import annotations

import re
from pathlib import Path

import aegis_swr

_PKG_ROOT = Path(aegis_swr.__file__).resolve().parent

#: The single hand-written module allowed to import ``grpc`` / ``_pb2``.
_GRPC_ALLOWED = _PKG_ROOT / "openclaude" / "grpc" / "client.py"
#: Generated proto stubs are excluded from the grpc rule (generated code).
_PROTO_DIR = _PKG_ROOT / "openclaude" / "grpc" / "proto"

#: Modules that must never import ``aegis_swr.openclaude`` (C3).
_ISOLATED_DIRS = ("core", "views", "code_intel")

_GRPC_IMPORT = re.compile(r"^\s*(?:import\s+grpc|from\s+grpc\b|.*\b\w*_pb2\b)")
_OPENCLAUDE_IMPORT = re.compile(r"^\s*(?:import|from)\s+aegis_swr\.openclaude\b")


def _import_lines(path: Path) -> list[str]:
    """Return the import-looking lines of *path* (``import``/``from`` only)."""
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("import ", "from ")):
            lines.append(line)
    return lines


def test_grpc_imported_only_in_client() -> None:
    """[Unit] isolation: No source file outside ``grpc/client.py`` imports ``grpc`` / ``_pb2``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no source file outside ``grpc/client.py`` imports ``grpc`` / ``_pb2``.
    """
    offenders: list[str] = []
    for source in _PKG_ROOT.rglob("*.py"):
        if source == _GRPC_ALLOWED or _PROTO_DIR in source.parents:
            continue
        for line in _import_lines(source):
            if _GRPC_IMPORT.match(line):
                offenders.append(f"{source.relative_to(_PKG_ROOT)}: {line.strip()}")
    assert offenders == [], f"grpc/_pb2 imported outside grpc/client.py (C3): {offenders}"


def test_openclaude_not_imported_by_isolated_modules() -> None:
    """[Unit] isolation: ``core/``, ``views/``, and ``code_intel/`` never import ``aegis_swr.openclaude``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``core/``, ``views/``, and ``code_intel/`` never import ``aegis_swr.openclaude``.
    """
    offenders: list[str] = []
    for module_dir in _ISOLATED_DIRS:
        for source in (_PKG_ROOT / module_dir).rglob("*.py"):
            for line in _import_lines(source):
                if _OPENCLAUDE_IMPORT.match(line):
                    offenders.append(f"{source.relative_to(_PKG_ROOT)}: {line.strip()}")
    assert offenders == [], f"aegis_swr.openclaude imported in an isolated module (C3): {offenders}"
