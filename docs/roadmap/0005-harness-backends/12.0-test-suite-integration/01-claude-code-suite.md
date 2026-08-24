# 01 - `tests/integration/claude_code/` live suite

**Parent task:** 12.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** none upstream (this subtask is self-contained infrastructure and tests); exercises 02.0 (`ClaudeCodeSettings`), 03.0 (`ClaudeCodeTool`/`process.py`), 04.0 (`auth_mode` + subscription auth), 05.0 (`claude_code.*` events) **live**
**Blocks:** none

## Objective

Stand up the live Claude Code integration suite and its skip guards, and prove a
real one-shot `claude -p … --output-format stream-json` invocation flows all the
way through `ClaudeCodeTool.delegate()` to a well-formed `CodeResult`. Two guard
levels apply, and they must be kept **distinct**:

1. A **base** guard (`require_claude_code()`) that skips the module unless the
   `CLAUDE_CODE_ENABLED` presence signal is set **and** the `claude` binary
   resolves on `PATH`. The base live-delegate module additionally skips unless an
   API credential (`ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`) is present, since
   that is what `auth_mode="auto"`/`"api_key"` needs to actually call out.
2. A **subscription-mode** guard (`require_claude_code_subscription()`) that is
   its own conftest fixture/function, layered **on top of** the base guard. It
   additionally skips unless a live `claude login` session or
   `CLAUDE_CODE_OAUTH_TOKEN` is available, **and** skips when a stray
   `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` is present in the inherited
   environment — because `auth_mode="subscription"` rejects construction in that
   ambiguous case (C7), so the variant can only run cleanly when the API-key
   surface is absent.

The load-bearing capability assertion is Claude Code's genuine gain over
OpenClaude's boundary estimate: `CodeResult.token_estimate` must equal the summed
**real** `usage.input_tokens + usage.output_tokens` reported by the terminal
`result` NDJSON message (C6, C9), not a `len(content)//4` estimate — and at least
one `claude_code.tool_call` event must be emitted, proving genuine navigation
over the disposable stub project rather than an answer from training-data priors.

## File: `tests/integration/claude_code/conftest.py`

```python
from __future__ import annotations

import os
import shutil
import textwrap
from pathlib import Path
from typing import Optional

import pytest

from aegis_swr.claude_code.config import ClaudeCodeSettings


# --------------------------------------------------------------------------- #
# Skip-guard predicates
# --------------------------------------------------------------------------- #
def _claude_code_enabled() -> bool:
    """True when the ``CLAUDE_CODE_ENABLED`` presence signal is truthy (C6)."""
    return bool(os.environ.get("CLAUDE_CODE_ENABLED"))


def _binary_present(settings: ClaudeCodeSettings) -> bool:
    """True when ``settings.binary_path`` resolves on PATH or as an absolute path."""
    return shutil.which(settings.binary_path) is not None


def _api_credential_present() -> bool:
    """True when an API-key/console credential is available for auto/api_key mode."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _subscription_credential_present() -> bool:
    """True when a non-interactive subscription credential is available (C7).

    Either an explicit ``CLAUDE_CODE_OAUTH_TOKEN`` (the CI-friendly path minted by
    ``claude setup-token``) or a persisted ``claude login`` session on disk. The
    stored-session probe is deliberately best-effort — a missing file yields a
    skip, never a failure. The token value itself is never read or logged (C13);
    only its presence is tested.
    """
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return True
    # Windows (Aegis SWR's target platform) and POSIX credential-store locations.
    candidates = [
        Path(os.path.expandvars(r"%USERPROFILE%\.claude\.credentials.json")),
        Path.home() / ".claude" / ".credentials.json",
    ]
    return any(p.exists() for p in candidates)


# --------------------------------------------------------------------------- #
# Module-level guards (one clean skip line per module; never per-test)
# --------------------------------------------------------------------------- #
def require_claude_code() -> None:
    """Base guard: skip unless the presence signal and the ``claude`` binary exist.

    Call once at the top of a test module, after imports. Emits a single
    module-level skip when ``CLAUDE_CODE_ENABLED`` is unset or the binary is
    missing — so an absent backend produces one clean ``skipped`` line, never a
    failure.
    """
    if not _claude_code_enabled():
        pytest.skip("CLAUDE_CODE_ENABLED not set", allow_module_level=True)
    if not _binary_present(ClaudeCodeSettings()):
        pytest.skip("claude binary not on PATH", allow_module_level=True)


def require_claude_code_api_mode() -> None:
    """Base guard + an available API credential for ``auto``/``api_key`` mode."""
    require_claude_code()
    if not _api_credential_present():
        pytest.skip("no ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN for api_key/auto mode",
                    allow_module_level=True)


def require_claude_code_subscription() -> None:
    """Third-level guard for the subscription-mode variant (distinct from the base).

    Layers on top of :func:`require_claude_code`:

    * skips when **no** live ``claude login`` session or ``CLAUDE_CODE_OAUTH_TOKEN``
      is available (there is nothing to authenticate with); and
    * skips when a stray ``ANTHROPIC_API_KEY``/``ANTHROPIC_AUTH_TOKEN`` is present,
      because ``auth_mode="subscription"`` rejects construction in that ambiguous
      case (C7) — the variant must only run when it can run cleanly.
    """
    require_claude_code()
    if _api_credential_present():
        pytest.skip("ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN present — ambiguous under "
                    "auth_mode=subscription (C7)", allow_module_level=True)
    if not _subscription_credential_present():
        pytest.skip("no live claude login session or CLAUDE_CODE_OAUTH_TOKEN",
                    allow_module_level=True)


# --------------------------------------------------------------------------- #
# Disposable stub project (never the Aegis SWR source tree)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def stub_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tiny, disposable Python project for ``claude`` to navigate read-only.

    Contains a uniquely named symbol (``compute_checksum``) the model must
    *discover* via ``Read``/``Grep``/``Glob`` rather than guess from priors.
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
    (root / "helpers.py").write_text("# calls compute_checksum somewhere\n", encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def scratch_cwd(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fixed disposable scratch cwd for the one-shot subprocess (C6)."""
    return tmp_path_factory.mktemp("claude_code_scratch")
```

## File: `tests/integration/claude_code/test_delegate_live.py`

```python
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import pytest

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.events import ClaudeCodeCompleted, ClaudeCodeToolCall
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.code_intel.backend import CodeTaskContext
from aegis_swr.core.events import EventBus

from tests.integration.claude_code.conftest import require_claude_code_api_mode

require_claude_code_api_mode()  # module-level: one skip line when signal/binary/cred absent

pytestmark = pytest.mark.asyncio


def _build_tool(bus: EventBus, stub_project: Path, scratch_cwd: Path) -> ClaudeCodeTool:
    """A ClaudeCodeTool in auto mode over the read-only allowlist and scratch cwd."""
    return ClaudeCodeTool(
        settings=ClaudeCodeSettings(
            enabled=True,
            auth_mode="auto",  # whatever the installed binary resolves (C7)
            allowed_tools=["Read", "Grep", "Glob"],  # read-only forensic set
            scratch_cwd=scratch_cwd,
        ),
        event_bus=bus,
    )


async def test_delegate_returns_code_result_shape(
    stub_project: Path,
    scratch_cwd: Path,
):
    """A live delegate() returns an available, non-empty CodeResult."""
    bus = EventBus()
    tool = _build_tool(bus, stub_project, scratch_cwd)
    result = await tool.delegate(
        task=(
            f"Find the function named compute_checksum under {stub_project} and "
            "report which file defines it."
        ),
        ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
    )
    assert result.available is True
    assert result.content.strip()
    assert result.token_estimate > 0
    ...


async def test_token_estimate_is_real_usage_not_length_estimate(
    stub_project: Path,
    scratch_cwd: Path,
):
    """token_estimate equals the summed reported usage, not len(content)//4 (C9)."""
    bus = EventBus()
    seen: list[object] = []
    bus.subscribe(seen.append)  # recorder; exact API per core.events

    tool = _build_tool(bus, stub_project, scratch_cwd)
    result = await tool.delegate(
        task=f"Locate compute_checksum in {stub_project} and describe its module.",
        ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
    )

    completed = [e for e in seen if isinstance(e, ClaudeCodeCompleted)]
    assert len(completed) == 1, "exactly one claude_code.completed carries the token figure"
    reported = completed[0]  # carries real usage.input_tokens + usage.output_tokens

    # The real usage sum is what CodeResult.token_estimate carries...
    assert result.token_estimate == reported.token_estimate
    # ...and it is NOT the OpenClaude-style boundary estimate.
    boundary = max(1, len(result.content) // 4)
    assert result.token_estimate != boundary, (
        "token_estimate must be real reported usage, not a length estimate"
    )
    ...


async def test_at_least_one_tool_call_emitted(
    stub_project: Path,
    scratch_cwd: Path,
):
    """>=1 claude_code.tool_call proves real navigation, not an answer from priors."""
    bus = EventBus()
    seen: list[object] = []
    bus.subscribe(seen.append)

    tool = _build_tool(bus, stub_project, scratch_cwd)
    await tool.delegate(
        task=f"Grep for compute_checksum under {stub_project} and report its file.",
        ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
    )
    assert any(isinstance(e, ClaudeCodeToolCall) for e in seen)
    ...


async def test_task_text_never_appears_in_process_listing(
    stub_project: Path,
    scratch_cwd: Path,
):
    """Argv-safety (C6) holds live: the task string is not visible in argv.

    The one-shot process is spawned with the task on stdin/temp file, never as a
    bare CLI argument. A live check inspects the child's own argv (e.g. via
    ``psutil.Process(pid).cmdline()`` captured during the call) and asserts the
    unique task marker never appears in it.
    """
    ...  # capture child argv during delegate(); assert the task substring is absent
```

## File: `tests/integration/claude_code/test_subscription_live.py`

```python
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import pytest

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.code_intel.backend import CodeTaskContext
from aegis_swr.core.events import EventBus

from tests.integration.claude_code.conftest import require_claude_code_subscription

require_claude_code_subscription()  # third-level guard: distinct from the base guard

pytestmark = pytest.mark.asyncio


def _build_subscription_tool(bus: EventBus, scratch_cwd: Path) -> ClaudeCodeTool:
    """A ClaudeCodeTool explicitly in subscription mode (no API key present)."""
    return ClaudeCodeTool(
        settings=ClaudeCodeSettings(
            enabled=True,
            auth_mode="subscription",  # never passes --bare (C7)
            allowed_tools=["Read", "Grep", "Glob"],
            scratch_cwd=scratch_cwd,
        ),
        event_bus=bus,
    )


async def test_subscription_auth_probe_passes(scratch_cwd: Path):
    """The startup auth-probe resolves the login/OAuth credential as usable (C7).

    Runs the lightweight probe surfaced through ``aegis code-intel check`` before
    the first delegate(); a working subscription credential must NOT raise
    ClaudeCodeUnavailableError here.
    """
    bus = EventBus()
    tool = _build_subscription_tool(bus, scratch_cwd)
    assert await tool.health_check() is True  # exact probe API per Task 04.0
    ...


async def test_subscription_delegate_returns_code_result(
    stub_project: Path,
    scratch_cwd: Path,
):
    """A live delegate() over the subscription credential returns a real CodeResult."""
    bus = EventBus()
    tool = _build_subscription_tool(bus, scratch_cwd)
    result = await tool.delegate(
        task=f"Find compute_checksum under {stub_project} and name its file.",
        ctx=CodeTaskContext(run_id=uuid.uuid4(), dry_run=False),
    )
    assert result.available is True
    assert result.content.strip()
    # Real token accounting holds regardless of C7 auth mode (C9).
    assert result.token_estimate > 0
    ...
```

## Test cases

- `test_delegate_returns_code_result_shape` — a live one-shot `claude` call
  returns a `CodeResult` with `available is True`, non-empty `content`, and a
  positive `token_estimate`.
- `test_token_estimate_is_real_usage_not_length_estimate` — exactly one
  `claude_code.completed` event carries the token figure; `token_estimate` equals
  that real reported `usage` sum and is **not** the `max(1, len(content)//4)`
  boundary estimate (the C9 capability gain, asserted live).
- `test_at_least_one_tool_call_emitted` — at least one `claude_code.tool_call`
  event is emitted, proving the model drove its own read-only tool loop over the
  stub project rather than answering from priors.
- `test_task_text_never_appears_in_process_listing` — argv-safety (C6) verified
  against the real child process: the task marker never appears in its argv.
- `test_subscription_auth_probe_passes` — the subscription-mode startup
  auth-probe resolves a live `claude login`/`CLAUDE_CODE_OAUTH_TOKEN` credential
  as usable without raising `ClaudeCodeUnavailableError` (C7).
- `test_subscription_delegate_returns_code_result` — a live delegate under the
  subscription credential returns a real, non-empty `CodeResult` with positive
  real-usage `token_estimate`; `--bare` is never passed in this mode.

## Implementation notes

- The base and subscription guards are **separate** functions in the same
  `conftest.py`; the subscription module imports and calls
  `require_claude_code_subscription()` at import time, the base module calls
  `require_claude_code_api_mode()`. Never apply either guard per-test — a
  module-level skip yields one clean line, per-test yields N.
- The subscription guard's stored-session probe is best-effort file-existence
  only; it never opens or reads the credentials file (C13). Only presence is
  tested, so the guard cannot leak a credential.
- Each test constructs its own `ClaudeCodeTool` (there is no persistent sidecar
  to share — Claude Code spawns and reaps one process per `delegate()`), so
  there is no session-scoped process fixture to tear down as OpenClaude had.
- The `EventBus` recorder API (`bus.subscribe(...)`) mirrors the shape used in
  the 0004 OpenClaude live suite; settle the exact recorder against the shipped
  `aegis_swr.core.events` API.
- `token_estimate` reflecting real usage is the single most important live
  assertion for this backend — it is the milestone's headline gain (C9) and
  cannot be proven by unit mocks, which fabricate the `usage` numbers.

## Constraints

- **Skip, never fail.** With `CLAUDE_CODE_ENABLED` unset, the `claude` binary absent, or (for the base module) no API credential, the module reports one clean module-level skip. The subscription module additionally skips without a subscription credential and skips when an ambiguous API key is present.
- Tests that run pass with **zero mocks** — a real `claude` subprocess and a real model call.
- The one-shot process is reaped on completion; **no `claude` process survives** the module (Claude Code has no persistent sidecar to leak).
- The task text is passed via the stdin or the temp file and **never** appears in argv (C6), asserted live against the child process listing.
- Uses the temp-dir `stub_project` (a uniquely named symbol to *discover*), never the Aegis SWR source tree; runs strictly read-only under an `Read,Grep,Glob`-only allowlist and a disposable `scratch_cwd`.
- No OAuth token, credentials-file content, or `ANTHROPIC_API_KEY` value ever reaches a log sink, an exception message, or an event payload (C7, C13); loguru sinks keep `SensitiveFilter`.

## Success criteria

- [ ] With `CLAUDE_CODE_ENABLED` unset or the `claude` binary absent, the whole suite reports **skipped** (one line per module), never failed, or errored.
- [ ] The base live module additionally skips (never fails) when no `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` is available.
- [ ] The subscription module carries a **distinct** third-level guard: it skips when no `claude login` session / `CLAUDE_CODE_OAUTH_TOKEN` is available, and skips when an ambiguous API key is present (C7).
- [ ] A live `delegate()` returns a `CodeResult` with `available is True`, non-empty `content`, and `token_estimate > 0`.
- [ ] `token_estimate` equals the real reported `usage` sum from the terminal `result` message and is **not** the `len(content)//4` boundary estimate (C9).
- [ ] At least one `claude_code.tool_call` event is emitted (real navigation).
- [ ] The task text never appears in the live child process's argv (C6).
- [ ] The subscription auth-probe passes for a live login/OAuth credential without raising `ClaudeCodeUnavailableError`, and `--bare` is never passed.
- [ ] No `claude` process survives the run; no credential value is logged.
- [ ] `ruff check src/ tests/` - clean.
