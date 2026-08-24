"""Domain exceptions for the code-intelligence harness selection contract.

This module is the canonical home for the two typed errors the C2 truth table
distinguishes: :class:`HarnessConfigError` (a construction-time, config-shape
ambiguity raised by ``HarnessSettings``) and :class:`HarnessUnavailableError` (a
composition-time runtime capability failure raised by Task 10.0's composition
root). They form two independent hierarchies - neither subclasses the other - so
callers catch precisely the failure they mean.

This is a leaf module: it imports nothing from ``aegis_swr.harness`` (or any
backend package, ``grpc``, ``pydantic``, or a client library), so ``config.py``
(subtasks 01/02) and ``composition.py`` (Task 10.0) can both import it without a
cycle. No exception message or attribute ever formats a URL value, credential, or
dump/log/stack text (C13).
"""

from __future__ import annotations

from typing import Optional


class HarnessConfigError(ValueError):
    """Raised on an ambiguous or invalid harness selection (C2, construction-time).

    A **config-shape** error surfaced the moment ``HarnessSettings()`` is built:
    the selector is unset while more than one backend presence signal is set (the
    harness must never silently pick one), or the selector holds an unrecognised
    family name. Subclasses ``ValueError`` so it can be raised inside a Pydantic
    field/model validator and unwrapped by ``HarnessSettings.__init__`` (the same
    pattern :class:`OpenClaudeConfigError` uses).

    Distinct from :class:`HarnessUnavailableError` (a runtime capability
    failure); neither subclasses the other. The message and attributes carry only
    field names and *signal names* - never a variable value, secret, or payload
    (C13).

    :param reason: Human-readable, payload-free explanation of the ambiguity.
    :param signals: The set of presence-signal family names seen at
        construction, or ``None`` when not applicable (e.g. a bad selector
        value). Names only - never the variables' values.
    :param field: The offending settings field name; defaults to ``"backend"``
        (the selector).
    :ivar reason: The violation explanation.
    :ivar signals: The signal names seen, or ``None``.
    :ivar field: The offending field name.
    """

    def __init__(
        self,
        reason: str,
        *,
        signals: Optional[frozenset[str]] = None,
        field: str = "backend",
    ):
        """Record the payload-free *reason*, *signals* seen, and offending *field*."""
        self.reason = reason
        self.signals = signals
        self.field = field
        super().__init__(f"HarnessSettings.{field}: {reason}")


class HarnessUnavailableError(Exception):
    """Raised when an explicitly-selected backend is not reachable (C2, composition-time).

    A **runtime capability** failure, distinct from the config-shape
    :class:`HarnessConfigError`: the operator set ``AEGIS_CODE_INTEL_BACKEND`` to
    a family whose presence signal is absent (e.g. ``backend=claude_code`` with
    ``CLAUDE_CODE_ENABLED`` unset). Because the choice was explicit, this is a
    capability failure surfaced at composition / health-check time by Task 10.0's
    composition root - **not** at settings construction, and never by
    :class:`HarnessSettings`. Per C2 there is no fallback: the caller reports the
    capability as unavailable.

    Neither subclasses the other. Carries only the selected backend's family name
    and the signal names seen - never a URL, token, credential, or payload (C13).

    :param backend: The explicitly-selected family name that is unavailable
        (e.g. ``"claude_code"``).
    :param signals: The presence-signal family names actually seen, for
        diagnostics. Names only - never the variables' values. Defaults to the
        empty frozenset.
    :ivar backend: The unavailable selected family name.
    :ivar signals: The signal names seen.
    """

    def __init__(self, backend: str, *, signals: frozenset[str] = frozenset()):
        """Record the unavailable *backend* and the (payload-free) *signals* seen."""
        self.backend = backend
        self.signals = signals
        super().__init__(
            f"Selected code-intelligence backend '{backend}' is not available: "
            f"its presence signal is not set (signals seen: {sorted(signals)})."
        )
