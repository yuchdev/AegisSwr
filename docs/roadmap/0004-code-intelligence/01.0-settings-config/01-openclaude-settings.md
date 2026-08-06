# 01 - `OpenClaudeSettings` Pydantic class

**Parent task:** 01.0 OpenClaude Settings & Config
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 03, 04 (this task), 03.0, 04.0, 05.0, 06.0 (downstream tasks)

## Objective

Create `aegis/openclaude/__init__.py` (empty, versioned) and
`aegis/openclaude/config.py` containing `OpenClaudeSettings` - a Pydantic
`BaseSettings` subclass whose fields are sourced entirely from environment
variables per milestone contract C1. When no env vars are set the object must
be constructible without error and must produce `grpc_url=None` (backend not
registered). Any downstream code that receives a `None` `grpc_url` must treat
it as "backend unavailable" without raising.

This subtask also wires `scripts/postinstall_openclaude.py` into
`pyproject.toml` so `poetry install` provisions the OpenClaude npm CLI
alongside the Python environment (see "Prerequisite" below).

## File: `aegis/openclaude/config.py`

**Fields** (env var → field name → type → default):

| Env var                      | Field                  | Type                  | Default                              |
|-------------------------------|------------------------|-----------------------|---------------------------------------|
| `OPENCLAUDE_GRPC_URL`        | `grpc_url`             | `Optional[str]`       | `None`                               |
| `OPENCLAUDE_ALLOWED_TOOLS`   | `allowed_tools`        | `list[str]`           | `["Read","Grep","Glob","Bash"]`      |
| `OPENCLAUDE_BASH_ALLOWLIST`  | `bash_allowlist`       | `list[str]`           | `["gtags","global","semgrep","rg","find","cat"]` |
| `OPENCLAUDE_MAX_TOKENS`      | `max_response_tokens`  | `int`                 | `4096`                               |
| `OPENCLAUDE_CONNECT_TIMEOUT` | `connect_timeout_s`    | `int`                 | `10`                                  |
| `OPENCLAUDE_REQUEST_TIMEOUT` | `request_timeout_s`    | `int`                 | `120`                                 |
| `OPENCLAUDE_AUTO_START`      | `auto_start`           | `bool`                | `False`                              |
| `OPENCLAUDE_BINARY`          | `process_binary`       | `str`                 | `"openclaude"`                       |

```python
from __future__ import annotations

from typing import Optional

from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenClaudeConfigError(ValueError):
    """Raised when :class:`OpenClaudeSettings` receives an invalid value.

    Formally moved to ``aegis/openclaude/exceptions.py`` in Task 05.0.
    This alias is kept here so Task 01.0 can raise without depending on 05.0.

    :param field: Name of the offending field.
    :param reason: Human-readable explanation of the violation.
    """

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"OpenClaudeSettings.{field}: {reason}")


class OpenClaudeSettings(BaseSettings):
    """Environment-sourced configuration for the OpenClaude integration.

    :ivar grpc_url: Host[:port] of the OpenClaude gRPC sidecar. ``None`` means
        the backend is not registered (C4).
    :ivar allowed_tools: Claude Code tool names OpenClaude is permitted to use.
    :ivar bash_allowlist: Binary names OpenClaude's ``Bash`` tool may invoke.
    :ivar max_response_tokens: Hard cap on streamed response length.
    :ivar connect_timeout_s: gRPC channel connect timeout, in seconds.
    :ivar request_timeout_s: Per-request stream deadline, in seconds.
    :ivar auto_start: Whether ``app.py`` starts the sidecar process itself.
    :ivar process_binary: Binary name or full path to the OpenClaude
        executable. Defaults to the bare command ``"openclaude"``, resolved
        via ``PATH`` - the global npm install (see "Prerequisite" below)
        places it there. Override with a full path for a non-standard
        install location.
    """

    model_config = SettingsConfigDict(env_prefix="OPENCLAUDE_")

    grpc_url: Optional[str] = None
    allowed_tools: list[str] = ["Read", "Grep", "Glob", "Bash"]
    bash_allowlist: list[str] = ["gtags", "global", "semgrep", "rg", "find", "cat"]
    max_response_tokens: int = 4096
    connect_timeout_s: int = 10
    request_timeout_s: int = 120
    auto_start: bool = False
    process_binary: str = "openclaude"

    @field_validator("grpc_url")
    @classmethod
    def _validate_grpc_url(cls, v: Optional[str]) -> Optional[str]:
        """Reject scheme-prefixed URLs; only bare host[:port] is accepted."""
        ...

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, v: list[str]) -> list[str]:
        """Reject unknown Claude Code tool names; warn on Write/Edit."""
        ...

    @field_validator("max_response_tokens")
    @classmethod
    def _validate_max_response_tokens(cls, v: int) -> int:
        """Enforce the [256, 65536] range."""
        ...

    @field_validator("request_timeout_s")
    @classmethod
    def _validate_request_timeout(cls, v: int, info: ValidationInfo) -> int:
        """Enforce request_timeout_s > connect_timeout_s and both positive."""
        ...
```

## Prerequisite: OpenClaude CLI install hook (`poetry install`)

OpenClaude is consumed as a **black-box service** - Aegis SWR never builds or
vendors it, only calls its published gRPC API (C2). The CLI is installed with
`npm install -g @gitlawb/openclaude@latest`. So that a fresh `poetry install`
leaves a developer ready to run managed mode (`OPENCLAUDE_AUTO_START=true`)
without a separate manual step, wire the npm install into Poetry's
build-script hook - the closest thing Poetry has to a native post-install
event, since it has no dedicated `postinstall` hook of its own.

### File: `scripts/postinstall_openclaude.py`

```python
from __future__ import annotations

import shutil
import subprocess
import sys

_NPM_PACKAGE = "@gitlawb/openclaude@latest"


def install_openclaude_cli():
    """Install the OpenClaude CLI globally via npm, best-effort.

    Invoked from the Poetry build hook so ``poetry install`` provisions the
    OpenClaude coding-agent binary alongside the Python environment. Never
    raises: a missing Node.js/npm toolchain only blocks managed-mode
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
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"warning: OpenClaude CLI install failed: {exc}", file=sys.stderr)


def build(setup_kwargs: dict):
    """Poetry build-script entry point; see `pyproject.toml`'s `[tool.poetry.build]`."""
    install_openclaude_cli()
```

### Change: `pyproject.toml`

```toml
[tool.poetry.build]
script = "scripts/postinstall_openclaude.py"
generate-setup-file = false
```

Poetry-core invokes `build(setup_kwargs)` from this script both for
`poetry build` and for `poetry install`'s local-project build step, which is
what makes `poetry install` trigger the npm install with no separate manual
command.

## Implementation notes

- `grpc_url`: when not `None`, must match `r"^[a-zA-Z0-9.\-]+(:[0-9]+)?$"`.
  Values beginning with `http://` or `https://` are invalid (the gRPC channel
  construction in Task 02.0 handles scheme selection from the presence or
  absence of TLS settings; the URL field must not carry a scheme). Raise
  `OpenClaudeConfigError(field="grpc_url", reason=...)` on violation.
- `allowed_tools`: each entry must be in the set
  `{"Read","Write","Edit","Bash","Glob","LS","Grep","WebFetch","WebSearch",
  "Agent","Task","TodoRead","TodoWrite"}` (the canonical Claude Code tool
  names). Raise `OpenClaudeConfigError(field="allowed_tools", reason=...)` for
  any unknown name. Write-capable tools (`Write`, `Edit`) are allowed by the
  validator but must trigger a `logger.warning` noting that forensic read-only
  mode is compromised.
- `max_response_tokens`: must be in `[256, 65536]`. Raise
  `OpenClaudeConfigError` outside that range.
- `connect_timeout_s`, `request_timeout_s`: must be positive integers.
  `request_timeout_s` must be `> connect_timeout_s`.
- Env vars are parsed via Pydantic's `env_prefix="OPENCLAUDE_"`; `list[str]`
  fields accept a comma-separated string from the environment (Pydantic
  Settings' default list-parsing behaviour) so operators set
  `OPENCLAUDE_ALLOWED_TOOLS=Read,Grep,Glob,Bash`.

## Constraints

- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` at the top of the file (C9).
- No `Any` in field types; `replace_optional.py --check` clean.
- `OpenClaudeConfigError` here is a temporary forward declaration; Task 05.0
  moves the canonical definition to `exceptions.py` and replaces this with a
  re-export alias — no downstream import path changes when 05.0 lands.
- The `postinstall_openclaude.py` build hook must never raise or exit
  non-zero on a missing `npm`/Node.js toolchain — doing so would break
  `poetry install` for every contributor, including those who only ever run
  external mode.

## Success criteria

- [ ] `OpenClaudeSettings()` with no env vars set produces `grpc_url=None` and
      all documented defaults without raising.
- [ ] `OpenClaudeSettings(grpc_url="https://bad")` raises
      `OpenClaudeConfigError`.
- [ ] `OpenClaudeSettings(grpc_url="localhost:50051")` does not raise.
- [ ] `OpenClaudeSettings(allowed_tools=["Read","WriteFile"])` raises
      `OpenClaudeConfigError` because `WriteFile` is not a recognised tool
      name.
- [ ] `OpenClaudeSettings(allowed_tools=["Read","Write"])` does not raise but
      logs a warning.
- [ ] `OpenClaudeSettings(max_response_tokens=100)` raises
      `OpenClaudeConfigError`.
- [ ] `OpenClaudeSettings(connect_timeout_s=100, request_timeout_s=10)` raises
      `OpenClaudeConfigError`.
- [ ] `replace_optional.py --check` clean; no `Any` in field types.
- [ ] On a host with `npm` available, running `poetry install` installs
      `@gitlawb/openclaude@latest` globally (verify via `npm list -g
      @gitlawb/openclaude` or `which openclaude`) with no separate manual
      step.
- [ ] On a host without `npm` on `PATH`, `poetry install` still completes
      successfully (exit code 0) and logs a warning; `OpenClaudeSettings()`
      still constructs with `process_binary == "openclaude"`.
