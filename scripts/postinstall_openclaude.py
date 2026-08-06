"""Best-effort provisioning of the OpenClaude npm CLI.

OpenClaude is consumed as a black-box service (C2); Aegis SWR never builds or
vendors it, only calls its published gRPC API. The CLI is installed globally
via ``npm install -g @gitlawb/openclaude@latest`` so that managed mode
(``OPENCLAUDE_AUTO_START=true``) works out of the box.

This project builds with hatchling + uv (no Poetry build hook), so the module
exposes a ``__main__`` guard instead: run it manually with
``uv run python scripts/postinstall_openclaude.py``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

_NPM_PACKAGE = "@gitlawb/openclaude@latest"


def install_openclaude_cli():
    """Install the OpenClaude CLI globally via npm, best-effort.

    Never raises: a missing Node.js/npm toolchain only blocks managed-mode
    (``OPENCLAUDE_AUTO_START=true``) launches, not the Python install itself -
    external-mode operators pointing at an already-running sidecar never need
    the local binary. Failure is logged to stderr and swallowed.
    """
    npm = shutil.which("npm")
    if npm is None:
        print(
            "warning: npm not found on PATH; skipping OpenClaude CLI install. "
            "Managed-mode (OPENCLAUDE_AUTO_START=true) launches will fail "
            f"until you run: npm install -g {_NPM_PACKAGE}",
            file=sys.stderr,
        )
        return
    try:
        subprocess.run([npm, "install", "-g", _NPM_PACKAGE], check=True, timeout=300)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        # OSError also covers FileNotFoundError/PermissionError from a TOCTOU
        # race where npm is removed or made non-executable after the which()
        # check - the "never raises" contract must still hold.
        print(f"warning: OpenClaude CLI install failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    install_openclaude_cli()
