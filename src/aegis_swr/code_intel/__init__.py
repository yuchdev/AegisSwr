"""Minimal, backend-agnostic Code Intelligence scaffolding.

Exports the public contract only. Contains **zero** imports of
``aegis_swr.openclaude`` or ``grpc`` (C3).
"""

from __future__ import annotations

from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.code_intel.backend import CodeIntelBackend, CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget

__all__ = [
    "CallBudget",
    "CodeAgent",
    "CodeIntelBackend",
    "CodeResult",
    "CodeTaskContext",
]
