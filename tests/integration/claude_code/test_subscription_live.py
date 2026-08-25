"""Live subscription-mode delegation tests for the Claude Code backend (Task 12.0/01).

Proves that a ``claude login``/``CLAUDE_CODE_OAUTH_TOKEN`` credential resolves
as usable (C7) and that a live ``delegate()`` in ``auth_mode="subscription"``
mode returns a well-formed :class:`~aegis_swr.code_intel.backend.CodeResult`.

Skipped as a whole (third-level guard) when:
* ``CLAUDE_CODE_ENABLED`` is unset or the ``claude`` binary is absent (base
  guard);
* ``ANTHROPIC_API_KEY``/``ANTHROPIC_AUTH_TOKEN`` is present — that would make
  ``auth_mode="subscription"`` reject construction as ambiguous (C7); or
* no live ``claude login`` session and no ``CLAUDE_CODE_OAUTH_TOKEN`` is
  available (no credential to authenticate with).

This module imports :func:`require_claude_code_subscription` exclusively; it is
*distinct* from :func:`require_claude_code_api_mode` by design.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.code_intel.backend import CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus
from tests.integration.claude_code.conftest import require_claude_code_subscription

require_claude_code_subscription()  # third-level guard: distinct from the base guard


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _build_subscription_tool(bus: EventBus, scratch_cwd: Path) -> ClaudeCodeTool:
    """Build a :class:`ClaudeCodeTool` explicitly in subscription mode (no API key).

    :param bus: Event bus for ``claude_code.*`` lifecycle emissions.
    :param scratch_cwd: Disposable working directory for the one-shot subprocess.
    :return: Configured :class:`ClaudeCodeTool` in ``auth_mode="subscription"``.
    """
    return ClaudeCodeTool(
        ClaudeCodeSettings(
            enabled=True,
            auth_mode="subscription",  # never passes --bare (C7)
            allowed_tools=["Read", "Grep", "Glob"],
            scratch_cwd=scratch_cwd,
        ),
        bus,
        CallBudget(max_tokens=1_000_000),
    )


def _ctx() -> CodeTaskContext:
    """Return a fresh live :class:`CodeTaskContext` (``dry_run=False``).

    :return: Context with a new UUID4 run id.
    """
    return CodeTaskContext(run_id=uuid.uuid4(), dry_run=False)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


async def test_subscription_auth_probe_passes(scratch_cwd: Path):
    """[Integration] claude code subscription: The startup auth-probe passes for a live subscription credential (C7).

    Scenario: probe_auth() is called before the first delegate(); a working
    subscription credential must not raise ClaudeCodeUnavailableError.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify a live ``claude login`` session or
    ``CLAUDE_CODE_OAUTH_TOKEN`` is available and that no API key is present in
    the environment (which would make subscription mode ambiguous per C7).
    """
    bus = EventBus()
    tool = _build_subscription_tool(bus, scratch_cwd)
    # probe_auth() returns None on success; raises ClaudeCodeUnavailableError on failure.
    await tool.probe_auth()


async def test_subscription_delegate_returns_code_result(
    stub_project: Path,
    scratch_cwd: Path,
):
    """[Integration] claude code subscription: A live delegate() via subscription credential returns a real CodeResult.

    Scenario: delegate() flows through the subscription auth path and returns a
    result with real token accounting (C9); --bare is never passed.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify the subscription credential is valid and
    that the stub project symbol is discoverable by the model's tool loop.
    """
    bus = EventBus()
    tool = _build_subscription_tool(bus, scratch_cwd)
    result: CodeResult = await tool.delegate(
        task=f"Find compute_checksum under {stub_project} and name its file.",
        ctx=_ctx(),
    )
    assert result.available is True
    assert result.content.strip()
    # Real token accounting holds regardless of auth mode (C9).
    assert result.token_estimate > 0
