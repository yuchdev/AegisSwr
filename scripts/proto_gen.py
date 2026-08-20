"""Regenerate the committed OpenClaude gRPC stubs from ``openclaude.proto``.

The generated ``*_pb2.py`` / ``*_pb2_grpc.py`` files are committed (see C9); run
this script whenever ``openclaude.proto`` changes and commit the result.

The proto is compiled with the package source root (``src``) as ``--proto_path``
and a package-qualified proto path, so the generated grpc stub emits a
package-qualified cross-import::

    from aegis_swr.openclaude.grpc.proto import openclaude_pb2

rather than a flat ``import openclaude_pb2`` (which breaks when the stubs are
loaded as package submodules). This avoids any hand-editing of generated code.

``grpc_tools.protoc`` is invoked in-process (it is a pinned dev dependency,
``grpcio-tools==1.82.1``); this deliberately avoids shelling out to ``make`` or
re-invoking ``python -m grpc_tools.protoc`` as a subprocess.

The ``mypy-protobuf`` plugin additionally emits ``.pyi`` stubs alongside the
``_pb2.py`` / ``_pb2_grpc.py`` modules (``protoc-gen-mypy`` /
``protoc-gen-mypy_grpc``, resolved from PATH via the dev-only ``mypy-protobuf``
dependency), so mypy sees real message/stub attributes instead of the opaque
dynamically-built classes protobuf generates at import time.

Usage::

    uv run python scripts/proto_gen.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from grpc_tools import protoc

REPO_ROOT = Path(__file__).resolve().parent.parent

# Package source root used as both --proto_path and the codegen output root, so
# the emitted cross-import is package-qualified rather than flat.
PROTO_ROOT = REPO_ROOT / "src"
PROTO_PKG = "aegis_swr/openclaude/grpc/proto"
PROTO_FILE = PROTO_ROOT / PROTO_PKG / "openclaude.proto"


def main() -> int:
    """Compile ``openclaude.proto`` into committed gRPC stubs.

    :return: the ``grpc_tools.protoc`` exit code (``0`` on success).
    """
    exit_code = protoc.main(
        [
            "grpc_tools.protoc",
            f"--proto_path={PROTO_ROOT}",
            f"--python_out={PROTO_ROOT}",
            f"--grpc_python_out={PROTO_ROOT}",
            f"--mypy_out={PROTO_ROOT}",
            f"--mypy_grpc_out={PROTO_ROOT}",
            str(PROTO_FILE),
        ]
    )
    if exit_code == 0:
        print(f"Regenerated stubs in {PROTO_ROOT / PROTO_PKG}; commit the result.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
