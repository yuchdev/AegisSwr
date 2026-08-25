"""Module-isolation invariants for the OpenHands integration (contract C3).

These are the pytest mirror of the CI ``grep`` boundary job (Task 11.0): they
fail fast locally and under the Stop hook if the isolation boundary drifts. Two
independent rules:

* ``socketio`` (the OpenHands HTTP/WS client library) may be *imported* only by
  ``aegis_swr/openhands/client.py``, exactly as ``grpc`` lives only in
  ``aegis_swr/openclaude/grpc/client.py``.
* No raw library object crosses the client's boundary: the only types the client
  projects are :class:`AgentEvent` and :class:`EventKind`, whose fields are all
  primitive / domain types — never a vendor object.

Scanning is import-statement-aware (it matches ``import``/``from`` lines only),
so a bare mention of ``socketio`` in a docstring does not trip the guard.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from pathlib import Path

import aegis_swr
from aegis_swr.openhands import client as client_mod
from aegis_swr.openhands.client import AgentEvent, EventKind

_PKG_ROOT = Path(aegis_swr.__file__).resolve().parent

#: The single hand-written module allowed to import the OpenHands client library.
_SOCKETIO_ALLOWED = _PKG_ROOT / "openhands" / "client.py"

_SOCKETIO_IMPORT = re.compile(r"^\s*(?:import\s+socketio|from\s+socketio\b)")


def _import_lines(path: Path) -> list[str]:
    """Return the import-looking lines of *path* (``import``/``from`` only)."""
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("import ", "from ")):
            lines.append(line)
    return lines


def test_socketio_imported_only_in_client():
    """[Unit] isolation: no source file outside ``openhands/client.py`` imports ``socketio``.

    Scenario: every source module under the package is scanned for a ``socketio``
    import statement.

    Boundaries: an AST-lite, import-statement-aware source scan (C3).

    On failure, first check: no module other than ``openhands/client.py`` may
    import the OpenHands HTTP/WS client library.
    """
    offenders: list[str] = []
    for source in _PKG_ROOT.rglob("*.py"):
        if source == _SOCKETIO_ALLOWED:
            continue
        for line in _import_lines(source):
            if _SOCKETIO_IMPORT.match(line):
                offenders.append(f"{source.relative_to(_PKG_ROOT)}: {line.strip()}")
    assert offenders == [], f"socketio imported outside openhands/client.py (C3): {offenders}"


def test_client_projection_leaks_no_vendor_type():
    """[Unit] isolation: the ``AgentEvent`` projection carries only domain/primitive types.

    Scenario: the field types of the frozen :class:`AgentEvent` projection are
    inspected.

    Boundaries: proves no raw library object crosses the client boundary (C3).

    On failure, first check: every ``AgentEvent`` field must be a primitive or the
    domain :class:`EventKind` enum — never a ``socketio``/``httpx`` object.
    """
    assert dataclasses.is_dataclass(AgentEvent)
    assert issubclass(EventKind, enum.Enum)

    allowed_types = {"EventKind", "str", "int", "Optional", "NoneType"}
    for field in dataclasses.fields(AgentEvent):
        annotation = str(field.type)
        assert "socketio" not in annotation
        assert "httpx" not in annotation
        # The annotation is one of the allowed domain/primitive shapes.
        assert any(token in annotation for token in allowed_types), annotation


def test_client_run_return_annotation_is_the_domain_projection():
    """[Unit] isolation: the client's ``run`` yields the domain projection, not a vendor type.

    Scenario: the ``run`` coroutine's return annotation is inspected.

    Boundaries: guards the public method surface against leaking a vendor object.

    On failure, first check: ``run`` must be annotated to yield ``AgentEvent`` and
    reference no ``socketio``/``httpx`` type.
    """
    annotation = str(client_mod.OpenHandsClient.run.__annotations__.get("return", ""))
    assert "AgentEvent" in annotation
    assert "socketio" not in annotation
    assert "httpx" not in annotation
