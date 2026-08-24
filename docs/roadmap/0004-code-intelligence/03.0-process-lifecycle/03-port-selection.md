# 03 - Port-0 free-port selection

**Parent task:** 03.0 Process Lifecycle Manager
**State:** ⬜ Not started
**Depends on:** 02
**Blocks:** 04.0

## Objective

Resolve a concrete gRPC port when the operator configures a wildcard port
(C6). In managed mode, if `settings.grpc_url` resolves to `localhost:0` (port
`0`), the OS must assign a free port *before* launching the subprocess, so both
the child's bind flag and the caller-visible `grpc_url` reference the same
concrete port. A free port is chosen by binding a temporary socket to port `0`,
reading the OS-assigned port, and closing the socket. The resolved
`grpc_url` — with the real port substituted — is what `_build_argv` passes to
the child and what the context manager exposes to callers. When the URL already
carries a concrete port (or omits one), no resolution occurs and the value is
used verbatim.

## File: `aegis/openclaude/process.py`

```python
from __future__ import annotations

import socket


class OpenClaudeProcess:
    # ... external- and managed-mode surface from subtasks 01, 02 ...

    def _resolve_grpc_url(self) -> str:
        """Resolve ``settings.grpc_url`` to a concrete dialable endpoint.

        If the configured port is ``0`` (wildcard), a free port is chosen via
        :meth:`_pick_free_port` and substituted into the returned URL. If the
        URL already has a concrete port (or none), it is returned unchanged.
        Called once at ``__aenter__`` before argv construction so the child and
        the caller-visible ``grpc_url`` agree on the port.

        :return: Bare ``host:port`` with a concrete port.
        """
        ...

    @staticmethod
    def _pick_free_port(host: str) -> int:
        """Ask the OS for a currently-free TCP port on ``host``.

        Binds a temporary :func:`socket.socket` to port ``0``, reads the
        OS-assigned port from ``getsockname``, and closes the socket (RAII via
        ``with``) before returning. See the TOCTOU note in the implementation
        section: the port may in principle be claimed by another process
        between release and the child's bind — an accepted, standard limitation
        of this pattern.

        :param host: Host to bind the probe socket on (e.g. ``localhost``).
        :return: An OS-assigned free TCP port number.
        """
        ...
```

## Implementation notes

- **Trigger.** Parse `settings.grpc_url` into host and port. Only when the port
  component is exactly `0` does free-port selection run. A URL with no port and
  a URL with a fixed port are both passed through unchanged (host defaulting is
  the caller's concern; the field validator in Task 01.0 guarantees a bare
  `host[:port]` shape with no scheme).
- **Socket probe (RAII).** In `_pick_free_port`, use
  `with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:`, call
  `s.bind((host, 0))`, then `port = s.getsockname()[1]`. Let the `with` block
  close the socket. Do not `SO_REUSEADDR`-linger the socket open past the
  function; the point is to release it so the child can bind it.
- **Ordering.** `_resolve_grpc_url` must run before `_build_argv` and before the
  child is spawned. Store the resolved URL in the same private field the
  `grpc_url` property reads, so the caller-visible endpoint carries the concrete
  port. The child receives the concrete port via its bind flag.
- **TOCTOU (known, accepted limitation).** There is an inherent race between
  releasing the probe socket and the child process binding the same port —
  another process could claim it in the interval. This is the standard,
  well-understood limitation of the "bind port 0, close, hand the number off"
  pattern. Do not attempt to eliminate it (e.g. by holding the socket and
  passing an fd — OpenClaude is a separate Node.js process and cannot inherit a
  Python-held fd portably). Document it in the module docstring and surface a
  clear `OpenClaudeUnavailableError` if the child then fails to bind / the port
  never opens (the readiness probe from subtask 02 already covers this failure
  path). Prefer a concrete configured port in production.
- **Synchronous is fine.** The probe is a single non-blocking bind/close; it
  need not be async. It runs once at entry before any await-heavy work.
- **External mode.** Port-0 resolution applies to managed mode only. In external
  mode the operator owns the running process; a `:0` there is a misconfiguration
  and should surface via the health check as `OpenClaudeUnavailableError`, not be
  silently rewritten.

## Constraints

- Free port chosen by binding/releasing a temporary socket, then launching with
  the concrete port (C6).
- Socket is managed with a context manager (RAII) — no leaked descriptor (C9).
- Resolved concrete `grpc_url` is what callers see via the property; child and
  caller agree on the port.
- TOCTOU race is documented as an accepted limitation, not silently ignored.
- `Optional[T]` from `typing`; `from __future__ import annotations` (C9).
- `ruff check src/ tests/` - clean.

## Success criteria

- [ ] `settings.grpc_url = "localhost:0"` resolves to a concrete
      `localhost:<n>` with `n != 0` before the subprocess is launched.
- [ ] The child's bind flag and the caller-visible `grpc_url` carry the same
      concrete port.
- [ ] A URL with a concrete port (e.g. `localhost:50051`) is passed through
      unchanged — no probe socket is opened.
- [ ] The probe socket is opened and closed within a `with` block; no descriptor
      leaks (verifiable by asserting the socket is closed).
- [ ] The module docstring records the TOCTOU limitation and recommends a fixed
      port in production.
- [ ] `ruff check src/ tests/` - clean.
