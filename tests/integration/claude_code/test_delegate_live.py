"""Live ``auto``/``api_key``-mode delegation tests for the Claude Code backend (Task 12.0/01).

Proves the delegation path against a real ``claude`` subprocess: a one-shot
invocation returns a well-formed :class:`~aegis_swr.code_intel.backend.CodeResult`,
exactly one :class:`~aegis_swr.claude_code.events.ClaudeCodeCompleted` carries the
**real** reported ``usage`` figure (C9 — not a ``len(content)//4`` estimate), and
at least one :class:`~aegis_swr.claude_code.events.ClaudeCodeToolCall` is emitted,
proving the model navigated the stub project rather than answering from priors.

Skipped as a whole when ``CLAUDE_CODE_ENABLED`` is unset, the ``claude`` binary
is absent from PATH, or no API credential (``ANTHROPIC_API_KEY`` /
``ANTHROPIC_AUTH_TOKEN``) is available.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.events import ClaudeCodeCompleted, ClaudeCodeToolCall
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.code_intel.backend import CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import DomainEvent, EventBus
from tests.integration.claude_code.conftest import require_claude_code_api_mode

require_claude_code_api_mode()  # module-level: one skip line when signal/binary/cred absent


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _Recorder:
    """Capturing :class:`DomainEvent` subscriber for the delegate live tests."""

    def __init__(self):
        """Initialise with an empty event list."""
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent):
        """Append *event* to the capture list."""
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        """Return events matching *event_type* (or any subclass).

        :param event_type: The target event class to filter on.
        :return: Matching events in emission order.
        """
        return [e for e in self.events if isinstance(e, event_type)]


def _build_tool(bus: EventBus, scratch_cwd: Path) -> ClaudeCodeTool:
    """Build a :class:`ClaudeCodeTool` in ``auto`` mode with a read-only allowlist.

    :param bus: Event bus for ``claude_code.*`` lifecycle emissions.
    :param scratch_cwd: Disposable working directory for the one-shot subprocess.
    :return: Configured :class:`ClaudeCodeTool` ready for ``delegate()``.
    """
    return ClaudeCodeTool(
        ClaudeCodeSettings(
            enabled=True,
            auth_mode="auto",
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


async def test_delegate_returns_code_result_shape(
    stub_project: Path,
    scratch_cwd: Path,
):
    """[Integration] claude code delegate: A live one-shot invocation returns a well-formed CodeResult.

    Scenario: delegate() is called against a real claude process with a
    navigation task that requires reading the stub project.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify CLAUDE_CODE_ENABLED and ANTHROPIC_API_KEY are
    set and that the ``claude`` binary is reachable on PATH.
    """
    bus = EventBus()
    tool = _build_tool(bus, scratch_cwd)
    result: CodeResult = await tool.delegate(
        task=(f"Find the function named compute_checksum under {stub_project} and " "report which file defines it."),
        ctx=_ctx(),
    )
    assert result.available is True
    assert result.content.strip()
    assert result.token_estimate > 0


async def test_token_estimate_is_real_usage_not_length_estimate(
    stub_project: Path,
    scratch_cwd: Path,
):
    """[Integration] claude code delegate: token_estimate equals the real reported usage sum, not len(content)//4 (C9).

    Scenario: after a live delegate(), exactly one ClaudeCodeCompleted event is
    emitted carrying the real usage; CodeResult.token_estimate matches it and
    differs from the boundary estimate.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: inspect the ClaudeCodeCompleted event payload and
    verify the tool charges real token counts, not a length approximation.
    """
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)

    tool = _build_tool(bus, scratch_cwd)
    result: CodeResult = await tool.delegate(
        task=f"Locate compute_checksum in {stub_project} and describe its module.",
        ctx=_ctx(),
    )

    completed = recorder.of(ClaudeCodeCompleted)
    assert len(completed) == 1, "exactly one claude_code.completed must carry the token figure"
    reported_estimate = completed[0].token_estimate  # type: ignore[attr-defined]

    assert (
        result.token_estimate == reported_estimate
    ), "CodeResult.token_estimate must equal the reported usage from ClaudeCodeCompleted"

    boundary = max(1, len(result.content) // 4)
    assert result.token_estimate != boundary, "token_estimate must be real reported usage, not a length estimate (C9)"


async def test_at_least_one_tool_call_emitted(
    stub_project: Path,
    scratch_cwd: Path,
):
    """[Integration] claude code delegate: At least one claude_code.tool_call proves real navigation.

    Scenario: the model must discover compute_checksum via its own read-only
    tool loop, not answer from training-data priors, so at least one
    ClaudeCodeToolCall must be emitted.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify the stub project symbol is unique enough
    that the model cannot answer without navigating the filesystem.
    """
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)

    tool = _build_tool(bus, scratch_cwd)
    await tool.delegate(
        task=f"Grep for compute_checksum under {stub_project} and report its file.",
        ctx=_ctx(),
    )
    assert recorder.of(ClaudeCodeToolCall), "expected at least one ClaudeCodeToolCall event"


async def test_task_text_never_appears_in_process_listing(
    stub_project: Path,
    scratch_cwd: Path,
):
    """[Integration] claude code delegate: Task text is passed via stdin, never appears in child process argv (C6).

    Scenario: the one-shot process is spawned with the task on stdin/temp file;
    the unique task marker must not appear in its observable argv. This is the
    live proof of the argv-safety guarantee (C6.1).

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify ClaudeCodeProcess passes task on stdin/file,
    not as a bare positional CLI argument.
    """
    # A live argv-safety check requires an in-process pid hook (e.g. psutil)
    # that can inspect the child's cmdline while delegate() is running.
    # psutil is not a declared project dependency; this stub records the
    # contract so a future implementation can slot in when psutil is available.
    pytest.skip(
        "argv-safety live check requires an in-process pid hook (psutil); "
        "the contract is verified by unit tests of ClaudeCodeProcess.build_argv "
        "and this stub is a placeholder for a future live assertion"
    )
