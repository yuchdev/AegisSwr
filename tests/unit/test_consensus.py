"""Tests for the weighted consensus score calculator"""

from __future__ import annotations

import pytest

from aegis_swr.agents.registry import AGENT_REGISTRY
from aegis_swr.core.consensus import ConsensusEvaluator

#: Default consensus weight map built from each registered agent's own declared
#: ``default_weight`` (weight is now an intrinsic property of the agent, not a
#: per-fault-class matrix). The four built-in agents are authored to sum to 1.0.
_DEFAULT_WEIGHTS: dict[str, float] = {key: cls.default_weight for key, cls in AGENT_REGISTRY.items()}


@pytest.fixture
def evaluator() -> ConsensusEvaluator:
    return ConsensusEvaluator()


# ---------------------------------------------------------------------------
# calculate()
# ---------------------------------------------------------------------------


def test_all_agents_full_confidence(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: all agents at full confidence yields a consensus of 1.0.

    Scenario:
        Given the default agent-declared weight map and every agent reporting a
        confidence of 1.0, when calculate runs, then the normalized weighted
        average is exactly 1.0 regardless of the individual weights.

    Boundaries:
        - Focus: normalization when all scores are 1.0
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether the weight map still sums to a positive total
        - Whether calculate normalizes by the summed weights
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 1.0, "code_analyst": 1.0, "log_historian": 1.0, "skeptic": 1.0}
    cs = evaluator.calculate(scores, _DEFAULT_WEIGHTS)
    assert cs == pytest.approx(1.0)


def test_all_agents_zero_confidence(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: all agents at zero confidence yields a consensus of 0.0.

    Scenario:
        Given the default agent-declared weight map and every agent reporting a
        confidence of 0.0, when calculate runs, then the result is 0.0.

    Boundaries:
        - Focus: zero-score aggregation
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether calculate multiplies scores by weights before summing
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 0.0, "code_analyst": 0.0, "log_historian": 0.0, "skeptic": 0.0}
    cs = evaluator.calculate(scores, _DEFAULT_WEIGHTS)
    assert cs == pytest.approx(0.0)


def test_weighted_formula_uses_agent_declared_weights(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: the weighted average uses each agent's declared weight.

    Scenario:
        Given per-agent confidence scores and the default agent-declared weight
        map (os=0.35, code=0.35, log=0.17, skeptic=0.13), when calculate runs,
        then the result equals the analytically computed weighted average.

    Boundaries:
        - Focus: weighted-average arithmetic against agent-declared weights
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether the default_weight ClassVars changed on the four agents
        - Whether calculate divides by the summed weights
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 0.8, "code_analyst": 0.9, "log_historian": 0.7, "skeptic": 0.6}
    expected = sum(_DEFAULT_WEIGHTS[k] * scores[k] for k in _DEFAULT_WEIGHTS) / sum(_DEFAULT_WEIGHTS.values())
    cs = evaluator.calculate(scores, _DEFAULT_WEIGHTS)
    assert cs == pytest.approx(expected)


def test_missing_agent_treated_as_zero(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: an agent in the weight map but absent from scores counts as zero.

    Scenario:
        Given a weight map naming four agents but only two present in the scores,
        when calculate runs, then the two absent agents contribute 0.0 so the
        result is strictly between 0.0 and 1.0.

    Boundaries:
        - Focus: absent-agent-as-zero behavior
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether calculate uses scores.get(key, 0.0)
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 1.0, "code_analyst": 1.0}
    cs = evaluator.calculate(scores, _DEFAULT_WEIGHTS)
    assert cs < 1.0
    assert cs > 0.0


def test_score_bounded_zero_to_one(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: the consensus score stays within [0.0, 1.0].

    Scenario:
        Given every agent at a mid confidence of 0.5 and the default weight map,
        when calculate runs, then the result is bounded to [0.0, 1.0].

    Boundaries:
        - Focus: output range invariant
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether calculate normalizes by the summed weights
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 0.5, "code_analyst": 0.5, "log_historian": 0.5, "skeptic": 0.5}
    cs = evaluator.calculate(scores, _DEFAULT_WEIGHTS)
    assert 0.0 <= cs <= 1.0


def test_default_weight_map_comes_from_the_agents(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: the default weight map is the agents' declared weights.

    Scenario:
        Given the registered agent roster, when their ``default_weight`` values
        are collected, then they match the authored defaults and sum to 1.0 -
        confirming weight is sourced from the agent, not an external matrix.

    Boundaries:
        - Focus: weight-as-agent-property sourcing
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether any concrete agent changed its default_weight ClassVar
        - Recent changes in code paths exercised by the agent registry
    """
    assert _DEFAULT_WEIGHTS == {
        "os_kernel": pytest.approx(0.35),
        "code_analyst": pytest.approx(0.35),
        "log_historian": pytest.approx(0.17),
        "skeptic": pytest.approx(0.13),
    }
    assert sum(_DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_arbitrary_panel_weight_map(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: verifies an arbitrary (non-default) agent panel.

    Scenario:
        Given a caller-supplied weight map for agent keys outside the historical
        four-agent set, when calculate runs, then the weighted average is
        computed purely from the supplied map (agent-count-agnostic) and
        normalized by its (non-unit) weight sum.

    Boundaries:
        - Focus: agent-count-agnostic weighted average over an unnormalized map
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to the arbitrary panel weighted average
        - Whether calculate still keys off weight_map rather than a fixed set
        - Recent changes in code paths exercised by consensus
    """
    weight_map = {"race_detector": 2.0, "gpu_analyst": 1.0, "skeptic": 1.0}
    scores = {"race_detector": 0.9, "gpu_analyst": 0.6, "skeptic": 0.3}
    expected = (2.0 * 0.9 + 1.0 * 0.6 + 1.0 * 0.3) / (2.0 + 1.0 + 1.0)
    cs = evaluator.calculate(scores, weight_map)
    assert cs == pytest.approx(expected)


def test_zero_total_weight_returns_zero(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: verifies the zero-total-weight guard.

    Scenario:
        Given a weight map whose weights sum to zero (or an empty map), when
        calculate runs, then it returns 0.0 rather than dividing by zero.

    Boundaries:
        - Focus: divide-by-zero guard on total weight
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to the zero-weight guard
        - Whether the total-weight sum branch still returns 0.0
        - Recent changes in code paths exercised by consensus
    """
    assert evaluator.calculate({"os_kernel": 1.0}, {"os_kernel": 0.0}) == 0.0
    assert evaluator.calculate({"os_kernel": 1.0}, {}) == 0.0


# ---------------------------------------------------------------------------
# is_converged()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,threshold,same,expected",
    [
        (0.90, 0.85, True, True),
        (0.85, 0.85, True, True),  # exactly at threshold
        (0.84, 0.85, True, False),  # just below threshold
        (0.90, 0.85, False, False),  # score OK but hypothesis changed
        (0.00, 0.85, True, False),
        (1.00, 0.85, False, False),
    ],
)
def test_is_converged(
    evaluator: ConsensusEvaluator,
    score: float,
    threshold: float,
    same: bool,
    expected: bool,
):
    """
    [Unit] consensus: verifies is converged.

    Scenario:
        Given test inputs and fixtures for is converged
        When test_is_converged executes the target flow
        Then the expected outcome for is converged is confirmed.

    Boundaries:
        - Focus: is converged
        - Fixtures/params: evaluator, score, threshold, same, expected (parametrized, 6 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to is converged
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by consensus
    """
    assert evaluator.is_converged(score, threshold, same) is expected


# ---------------------------------------------------------------------------
# is_deadlocked()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,round_num,max_rounds,hitl_threshold,expected",
    [
        (0.40, 4, 4, 0.50, True),  # at max rounds, below threshold
        (0.40, 5, 4, 0.50, True),  # past max rounds
        (0.60, 4, 4, 0.50, False),  # at max rounds but score is above hitl threshold
        (0.40, 3, 4, 0.50, False),  # below max rounds
        (0.00, 1, 4, 0.50, False),
    ],
)
def test_is_deadlocked(
    evaluator: ConsensusEvaluator,
    score: float,
    round_num: int,
    max_rounds: int,
    hitl_threshold: float,
    expected: bool,
):
    """
    [Unit] consensus: verifies is deadlocked.

    Scenario:
        Given test inputs and fixtures for is deadlocked
        When test_is_deadlocked executes the target flow
        Then the expected outcome for is deadlocked is confirmed.

    Boundaries:
        - Focus: is deadlocked
        - Fixtures/params: evaluator, score, round_num, max_rounds, hitl_threshold, expected (parametrized, 5 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to is deadlocked
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by consensus
    """
    assert evaluator.is_deadlocked(score, round_num, max_rounds, hitl_threshold) is expected
