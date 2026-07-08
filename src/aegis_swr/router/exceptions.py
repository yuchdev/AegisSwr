"""Exception hierarchy for the Aegis SWR model router.

This module has **no** third-party client dependency (no ``litellm``,
``anthropic``, ``openai`` or ``deepseek`` imports) so it can be imported from
any layer, including pure configuration parsing.
"""

from __future__ import annotations


class RouterException(Exception):
    """Wraps any provider or network error raised while calling a model.

    :param message: Human-readable description of the failure.
    :param cause: The underlying exception (set as ``__cause__`` by the caller).
    """


class ConfigValidationError(Exception):
    """Raised when ``agents.yaml`` fails validation.

    Used for missing environment variables, undefined provider references and
    malformed fields. The message always lists *all* violations at once, not
    just the first, so operators fix every problem in a single pass.

    .. note::

       This is deliberately **not** a subclass of :class:`RouterException`.
       A configuration problem is a startup fault, distinct from a runtime
       provider-call failure.
    """


class AllProvidersExhausted(RouterException):
    """Raised when every model in the primary + fallback chain has failed.

    :ivar role: The agent role that was being resolved.
    :ivar tried: Ordered list of model strings that were attempted.
    :ivar errors: Parallel list of error messages for each attempted model.
    """

    def __init__(self, role: str, tried: list[str], errors: list[str]) -> None:
        """Store the failure context and build a diagnostic message.

        :param role: The agent role that was being resolved.
        :param tried: Ordered list of model strings that were attempted.
        :param errors: Parallel list of error messages for each attempted model.
        """
        self.role = role
        self.tried = tried
        self.errors = errors
        super().__init__(f"All providers exhausted for role '{role}'. Tried: {tried}. Errors: {errors}")
