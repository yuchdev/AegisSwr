"""Fixtures and skip guards for the live Claude Code integration suite (Task 12.0/01).

Single source of truth for *when* the Claude Code integration suite runs and
*how* a disposable stub project is created for navigation tasks. Every downstream
test module calls one of the module-level guards at import time, so an absent
``CLAUDE_CODE_ENABLED`` signal, a missing ``claude`` binary, or an absent
credential produces exactly **one** clean ``skipped`` line per module — never a
failure or collection error.

Two distinct guard levels are provided:

* :func:`require_claude_code` — the base guard; checks the
  ``CLAUDE_CODE_ENABLED`` presence signal and the ``claude`` binary on ``PATH``.
* :func:`require_claude_code_api_mode` — the base guard plus an API credential
  check for ``auto``/``api_key`` mode.
* :func:`require_claude_code_subscription` — a third-level guard; layered on top
  of the base, additionally requires a subscription credential and skips when an
  ambiguous API key is present (C7).

Guards are intentionally kept separate so each test module imports exactly the
one that fits its mode; the subscription module never silently activates under
``auto`` conditions.
"""

from __future__ import annotations

import os
import shutil
import textwrap
from pathlib import Path

import pytest

from aegis_swr.claude_code.config import ClaudeCodeSettings

# --------------------------------------------------------------------------- #
# Skip-guard predicates
# --------------------------------------------------------------------------- #


def _claude_code_enabled() -> bool:
    """True when the ``CLAUDE_CODE_ENABLED`` presence signal is truthy (C6).

    :return: Whether the presence signal opt-in is set.
    """
    return bool(os.environ.get("CLAUDE_CODE_ENABLED"))


def _binary_present(settings: ClaudeCodeSettings) -> bool:
    """True when ``settings.binary_path`` resolves on PATH or as an absolute path.

    :param settings: Validated settings carrying the configured binary name.
    :return: Whether the ``claude`` binary can be found.
    """
    return shutil.which(settings.binary_path) is not None


def _api_credential_present() -> bool:
    """True when an API-key credential is available for ``auto``/``api_key`` mode.

    Only tests presence, never reads or logs the value (C13).

    :return: Whether ``ANTHROPIC_API_KEY`` or ``ANTHROPIC_AUTH_TOKEN`` is set.
    """
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _subscription_credential_present() -> bool:
    """True when a non-interactive subscription credential is available (C7).

    Accepts either an explicit ``CLAUDE_CODE_OAUTH_TOKEN`` (the CI-friendly
    path minted by ``claude setup-token``) or a persisted ``claude login``
    session on disk. The stored-session probe is best-effort file-existence
    only — a missing file yields a skip, never a failure. Credential values are
    never read or logged (C13); only file presence is tested.

    :return: Whether a usable subscription credential can be resolved.
    """
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return True
    candidates: list[Path] = [
        Path(os.path.expandvars(r"%USERPROFILE%\.claude\.credentials.json")),
        Path.home() / ".claude" / ".credentials.json",
    ]
    return any(p.exists() for p in candidates)


# --------------------------------------------------------------------------- #
# Module-level guards (one clean skip line per module; never per-test)
# --------------------------------------------------------------------------- #


def require_claude_code():
    """Base guard: skip unless the presence signal and the ``claude`` binary exist.

    Call once at the top of a test module, after imports. Emits a single
    module-level skip when ``CLAUDE_CODE_ENABLED`` is unset or the binary is
    missing — so an absent backend produces one clean ``skipped`` line, never a
    failure or a collection crash.
    """
    if not _claude_code_enabled():
        pytest.skip("CLAUDE_CODE_ENABLED not set", allow_module_level=True)
    # Construct with enabled=False to prevent scratch_cwd validation in the guard;
    # the guard only needs the configured binary name, not a full live config.
    if not _binary_present(ClaudeCodeSettings(enabled=False)):
        pytest.skip("claude binary not on PATH", allow_module_level=True)


def require_claude_code_api_mode():
    """Base guard plus an available API credential for ``auto``/``api_key`` mode.

    Layers on top of :func:`require_claude_code`; additionally skips when no
    ``ANTHROPIC_API_KEY`` or ``ANTHROPIC_AUTH_TOKEN`` is present, since the
    ``auto``/``api_key`` mode needs one to actually call out.
    """
    require_claude_code()
    if not _api_credential_present():
        pytest.skip(
            "no ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN for api_key/auto mode",
            allow_module_level=True,
        )


def require_claude_code_subscription():
    """Third-level guard for the subscription-mode variant (distinct from the base).

    Layers on top of :func:`require_claude_code` and adds two more conditions:

    * skips when **no** live ``claude login`` session or
      ``CLAUDE_CODE_OAUTH_TOKEN`` is available (nothing to authenticate with);
    * skips when a stray ``ANTHROPIC_API_KEY``/``ANTHROPIC_AUTH_TOKEN`` is
      present — ``auth_mode="subscription"`` rejects construction in that
      ambiguous case (C7), so the module must only run when it can run cleanly.

    This function is **deliberately separate** from :func:`require_claude_code`;
    the subscription module imports this one exclusively.
    """
    require_claude_code()
    if _api_credential_present():
        pytest.skip(
            "ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN present — ambiguous under " "auth_mode=subscription (C7)",
            allow_module_level=True,
        )
    if not _subscription_credential_present():
        pytest.skip(
            "no live claude login session or CLAUDE_CODE_OAUTH_TOKEN",
            allow_module_level=True,
        )


# --------------------------------------------------------------------------- #
# Disposable stub project (never the Aegis SWR source tree)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def stub_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tiny, disposable Python project for ``claude`` to navigate read-only.

    Contains a uniquely named symbol (``compute_checksum``) the model must
    *discover* via ``Read``/``Grep``/``Glob`` rather than guess from priors.
    Task prompts reference stub files by absolute path because the scratch cwd
    is a separate disposable directory, not the stub project root.

    :param tmp_path_factory: pytest temporary-path factory (module-scoped).
    :return: Path to the created stub project root.
    """
    root = tmp_path_factory.mktemp("claude_code_stub")
    (root / "app.py").write_text(
        textwrap.dedent(
            '''\
            """Throwaway stub for Claude Code integration navigation."""


            def compute_checksum(payload: bytes) -> int:
                """A uniquely named function the model must FIND, not guess."""
                return sum(payload) % 65521
            '''
        ),
        encoding="utf-8",
    )
    (root / "helpers.py").write_text(
        "# calls compute_checksum somewhere\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture(scope="module")
def scratch_cwd(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fixed disposable scratch working directory for the one-shot subprocess (C6).

    Kept separate from ``stub_project`` to honour the per-``delegate()`` RAII
    constraint: the ``claude`` process runs from ``scratch_cwd``, never from
    the stub project root or the Aegis SWR source tree.

    :param tmp_path_factory: pytest temporary-path factory (module-scoped).
    :return: Path to the created scratch working directory.
    """
    return tmp_path_factory.mktemp("claude_code_scratch")
