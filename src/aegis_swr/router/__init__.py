"""Public API for the Aegis SWR model router foundation.

This package currently exposes the configuration types and exception hierarchy
that parse and validate ``agents.yaml``. The ``ModelRouter`` client and its
event types are introduced by later roadmap milestones; only the foundation
types are re-exported here.

.. note::

   Strict isolation invariant: nothing in this package imports ``litellm``,
   ``anthropic``, ``openai`` or ``deepseek``. Configuration can be validated
   without any model-client dependency.
"""

from __future__ import annotations

# Public API - import order follows dependency order.
from aegis_swr.router.config import (
    AgentConfig,
    ProviderConfig,
    RetryPolicy,
    RouterConfig,
)
from aegis_swr.router.exceptions import (
    AllProvidersExhausted,
    ConfigValidationError,
    RouterException,
)

__all__ = [
    "RouterConfig",
    "AgentConfig",
    "ProviderConfig",
    "RetryPolicy",
    "RouterException",
    "ConfigValidationError",
    "AllProvidersExhausted",
]
