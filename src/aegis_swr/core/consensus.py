"""Weighted consensus score calculator for the Multi-Agent System.

The consensus score is the weighted average ``CS = Σ(Wᵢ·Sᵢ) / Σ(Wᵢ)`` over an
arbitrary set of agents, where ``Wᵢ`` is the caller-supplied consensus weight
for agent *i* and ``Sᵢ`` is that agent's confidence score in the current round.

Weight resolution - fault-class lookup and the weight-precedence merge - is the
caller's responsibility (it lives in ``agents/panel.py``). This keeps the
evaluator a pure, fully agent-count-agnostic utility with no knowledge of
:class:`~aegis_swr.core.fault_codes.FaultClass`, the settings weight matrix, or
any fixed set of agent keys.
"""

from __future__ import annotations


class ConsensusEvaluator:
    """Evaluator for weighted consensus scores in multi-agent debate rounds.

    Computes a normalized confidence score across an arbitrary panel of agents
    from a caller-supplied weight map. Also provides convergence and deadlock
    detection helpers to determine when debate should terminate.
    """

    def calculate(
        self,
        agent_scores: dict[str, float],
        weight_map: dict[str, float],
    ) -> float:
        """Return the weighted-average consensus score.

        :param agent_scores: Mapping of agent key (e.g. ``"os_kernel"``) to a
            confidence score in ``[0.0, 1.0]``. An agent present in
            *weight_map* but absent here is treated as contributing ``0.0``, so
            a partial round still yields a usable score.
        :param weight_map: Mapping of agent key to consensus weight. The result
            is normalized by the sum of these weights, so the map need not be
            pre-normalized; only agents named here contribute.
        :return: ``Σ(Wᵢ·Sᵢ) / Σ(Wᵢ)``, or ``0.0`` when the total weight is
            zero.
        """
        total_weight = sum(weight_map.values())
        if total_weight == 0.0:
            return 0.0
        weighted_sum = sum(weight * agent_scores.get(key, 0.0) for key, weight in weight_map.items())
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
