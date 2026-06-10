"""Weighted consensus score calculator for the Multi-Agent System.

The formula is CS = Σ(Wᵢ·Sᵢ) / Σ(Wᵢ) where Wᵢ is the domain authority weight
of Agent i for the detected fault type, and Sᵢ is the confidence score from
that agent in the current round.
"""
from __future__ import annotations

from aegis_swr.config.settings import AgentWeightsSettings
from aegis_swr.core.fault_codes import FaultClass

"""Tuple of canonical agent identifiers used to map scores and weights across the system."""
_AGENT_KEYS = ("os_kernel", "code_analyst", "log_historian", "skeptic")


class ConsensusEvaluator:
    """Evaluator for weighted consensus scores in multi-agent debate rounds.

    Computes a normalized confidence score across agents using domain-specific
    authority weights (e.g., higher weight for code analysis on SEGFAULT vs.
    memory corruption). Also provides convergence and deadlock detection logic
    to determine when debate should terminate.
    """

    def __init__(self, weights: AgentWeightsSettings):
        """Initialize the evaluator with agent weight configuration.

        Args:
            weights: AgentWeightsSettings instance that maps fault classes to
                per-agent domain authority weights.
        """
        self._weights = weights

    def calculate(
        self,
        agent_scores: dict[str, float],
        fault_class: FaultClass,
    ) -> float:
        """Return the weighted consensus score for *agent_scores* and *fault_class*.

        *agent_scores* maps the agent key (e.g. ``"os_kernel"``) to a confidence
        score in [0.0, 1.0]. Missing agents are treated as contributing 0.0,
        so a partial round still yields a usable score.
        """
        entry = self._weights.for_fault_class(fault_class.value)
        weight_map = {
            "os_kernel": entry.os_kernel,
            "code_analyst": entry.code_analyst,
            "log_historian": entry.log_historian,
            "skeptic": entry.skeptic,
        }
        total_weight = sum(weight_map.values())
        if total_weight == 0.0:
            return 0.0
        weighted_sum = sum(
            weight_map.get(k, 0.0) * agent_scores.get(k, 0.0) for k in _AGENT_KEYS
        )
        return weighted_sum / total_weight

    @staticmethod
    def is_converged(
        score: float,
        threshold: float,
        same_hypothesis: bool,
    ) -> bool:
        """Return True when the round score meets the threshold on a stable hypothesis"""
        return score >= threshold and same_hypothesis

    @staticmethod
    def is_deadlocked(
        score: float,
        round_num: int,
        max_rounds: int,
        hitl_threshold: float,
    ) -> bool:
        """Return True when we've exhausted debate rounds with insufficient confidence"""
        return round_num >= max_rounds and score < hitl_threshold
