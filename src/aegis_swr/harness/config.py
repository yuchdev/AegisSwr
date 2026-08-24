"""Neutral selection layer for the code-intelligence harness (C1, C2, C5).

This module hosts :class:`HarnessBackend` (the closed enum of backend families)
and :class:`HarnessSettings`, a Pydantic ``BaseSettings`` subclass that composes
the ``AEGIS_CODE_INTEL_BACKEND`` selector with one nested per-family settings
sub-object (``openclaude``, ``claude_code``, ``openhands``). It resolves the
single active backend at settings-construction time and raises
:class:`aegis_swr.harness.exceptions.HarnessConfigError` on the one ambiguous
combination (selector unset with more than one presence signal), per the C2
truth table.

``HarnessSettings`` itself reads only ``AEGIS_CODE_INTEL_BACKEND``; every nested
sub-object sources its own family's environment variables exactly as
:class:`aegis_swr.openclaude.config.OpenClaudeSettings` does (C1/C5). Each
presence signal is read off the already-constructed nested settings object,
never re-derived from ``os.environ``. No exception message ever formats a
variable value, secret, or payload text - only field names and family *signal
names* (C13).

The composition-time :class:`aegis_swr.harness.exceptions.HarnessUnavailableError`
(a deliberately-selected but unreachable backend) is **not** raised here; it
belongs to Task 10.0's composition root.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.harness.exceptions import HarnessConfigError
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openhands.config import OpenHandsSettings


class HarnessBackend(str, Enum):
    """The code-intelligence backend families the harness can select (C1).

    A ``str`` enum so the value round-trips to/from ``AEGIS_CODE_INTEL_BACKEND``
    and serialises as its bare family name (e.g. ``"openclaude"``). The member
    set is the *closed* universe of backends this milestone ships; adding a
    fourth backend is a deliberate, reviewed change to this enum.

    :cvar OPENCLAUDE: The OpenClaude gRPC sidecar (unchanged from 0004).
    :cvar CLAUDE_CODE: The installed ``claude`` CLI, one-shot subprocess (C6).
    :cvar OPENHANDS: The Docker-sandboxed OpenHands sidecar (C8).
    """

    OPENCLAUDE = "openclaude"
    CLAUDE_CODE = "claude_code"
    OPENHANDS = "openhands"


class HarnessSettings(BaseSettings):
    """Neutral selection layer for the code-intelligence harness (C1, C2, C5).

    Composes the ``AEGIS_CODE_INTEL_BACKEND`` selector with one nested settings
    sub-object per backend family. Each nested object sources its own family's
    environment variables (C1); ``HarnessSettings`` itself reads only the
    selector variable and never touches another family's ``os.environ`` keys.
    The single-active-backend selection and ambiguity resolution (C2) run once,
    at construction time, and are exposed via :attr:`active_backend`.

    :ivar backend: The explicitly selected backend family, or ``None`` to
        auto-select from presence signals (C2). Sourced from
        ``AEGIS_CODE_INTEL_BACKEND``; an empty/whitespace value is treated as
        unset (``None``), not as an invalid selector.
    :ivar openclaude: OpenClaude settings (unchanged from 0004); presence signal
        ``grpc_url is not None``.
    :ivar claude_code: Claude Code settings; presence signal ``enabled is True``
        (``CLAUDE_CODE_ENABLED``).
    :ivar openhands: OpenHands settings; presence signal ``server_url is not
        None`` (``OPENHANDS_SERVER_URL``).
    """

    model_config = SettingsConfigDict(populate_by_name=True)

    backend: Optional[HarnessBackend] = Field(default=None, validation_alias="AEGIS_CODE_INTEL_BACKEND")
    openclaude: OpenClaudeSettings = Field(default_factory=OpenClaudeSettings)
    claude_code: ClaudeCodeSettings = Field(default_factory=ClaudeCodeSettings)
    openhands: OpenHandsSettings = Field(default_factory=OpenHandsSettings)

    def __init__(self, **values: Any):
        """Construct the settings, surfacing :class:`HarnessConfigError` directly.

        Pydantic wraps any ``ValueError`` raised inside a field or model
        validator into a ``ValidationError``; this unwraps the first such
        :class:`HarnessConfigError` (the bad-selector case in
        :meth:`_coerce_and_validate_selector` and the ambiguity case in
        :meth:`_reject_ambiguous_selection`) so callers see the domain error the
        validators actually raised, exactly as :class:`OpenClaudeSettings` does.

        :param values: Field values forwarded to the ``BaseSettings``
            constructor.
        """
        try:
            super().__init__(**values)
        except ValidationError as exc:
            for error in exc.errors():
                ctx = error.get("ctx")
                if ctx is not None and isinstance(ctx.get("error"), HarnessConfigError):
                    raise ctx["error"] from None
            raise

    @field_validator("backend", mode="before")
    @classmethod
    def _coerce_and_validate_selector(cls, v: object) -> object:
        """Treat an empty selector as unset; reject an unrecognised value.

        An unset environment variable or CI secret expands to ``""`` (e.g.
        ``AEGIS_CODE_INTEL_BACKEND: ${{ secrets.MISSING }}``); that must mean
        "auto-select" (``None``), not a construction crash. A non-empty value
        that is not a :class:`HarnessBackend` member raises
        :class:`HarnessConfigError` naming only the offending field and the
        rejected selector value - never any secret.

        :param v: The raw ``backend`` value (``None``, a string, or an enum
            member).
        :return: ``None`` for an unset/blank selector, else a
            :class:`HarnessBackend` member.
        :raises HarnessConfigError: When *v* is a non-empty, unrecognised
            selector string.
        """
        if v is None or isinstance(v, HarnessBackend):
            return v
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return None
            try:
                return HarnessBackend(stripped)
            except ValueError:
                raise HarnessConfigError(
                    reason=(
                        f"unrecognised backend selector '{stripped}'; expected one of "
                        f"{[b.value for b in HarnessBackend]}"
                    ),
                    field="backend",
                ) from None
        return v

    @property
    def presence_signals(self) -> frozenset[str]:
        """Return the set of backend-family names whose presence signal is set.

        Each signal is read off the already-constructed nested settings object
        (C1) - never re-derived from ``os.environ``. Names are the bare family
        strings (``"openclaude"``, ``"claude_code"``, ``"openhands"``), the same
        values :class:`HarnessBackend` carries and the only thing ever placed in
        a :class:`HarnessConfigError` (never a URL or token, C13). This is the
        single source of truth for both :attr:`active_backend` and
        :meth:`_reject_ambiguous_selection`.

        :return: The frozenset of families currently signalled as configured.
        """
        signals: set[str] = set()
        if self.openclaude.grpc_url is not None:
            signals.add(HarnessBackend.OPENCLAUDE.value)
        if self.claude_code.enabled is True:
            signals.add(HarnessBackend.CLAUDE_CODE.value)
        if self.openhands.server_url is not None:
            signals.add(HarnessBackend.OPENHANDS.value)
        return frozenset(signals)

    @property
    def active_backend(self) -> Optional[str]:
        """Return the resolved active backend family name, or ``None`` (C2).

        Resolution, per the C2 truth table:

        * selector set -> that family's name verbatim (the selector wins; a
          missing presence signal for it is Task 10.0's
          :class:`HarnessUnavailableError`, not decided here);
        * selector unset, exactly one presence signal -> that family;
        * selector unset, zero presence signals -> ``None`` (capability
          unavailable - identical observable behaviour to 0004's unset path);
        * selector unset, more than one presence signal -> cannot occur on a
          successfully-constructed instance (rejected by
          :meth:`_reject_ambiguous_selection` at construction).

        Returns a plain ``str`` family name, never a :class:`HarnessBackend`
        member, so Task 10.0's composition branch can compare against the bare
        family strings without importing the enum.

        :return: The active family name, or ``None`` when no backend is active.
        """
        if self.backend is not None:
            return self.backend.value
        signals = self.presence_signals
        if len(signals) == 1:
            return next(iter(signals))
        return None

    @model_validator(mode="after")
    def _reject_ambiguous_selection(self) -> HarnessSettings:
        """Raise :class:`HarnessConfigError` when the selection is ambiguous (C2).

        The single ambiguous combination is: selector unset **and** more than
        one presence signal set. Fail loud, at construction time - never
        silently pick one backend. The error names only the offending field and
        the sorted *set of signal names* seen, never a URL, token, or payload
        (C13). Every other row of the C2 table is resolved by
        :attr:`active_backend` without raising here; a set selector is never
        ambiguous (its reachability is Task 10.0's concern).

        :return: ``self`` when the selection is unambiguous.
        :raises HarnessConfigError: selector unset with >1 presence signal.
        """
        if self.backend is not None:
            return self
        signals = self.presence_signals
        if len(signals) > 1:
            raise HarnessConfigError(
                reason=(
                    f"multiple backend presence signals set ({sorted(signals)}); "
                    "set AEGIS_CODE_INTEL_BACKEND to choose one"
                ),
                signals=signals,
                field="backend",
            )
        return self
