"""Tests for the weighted consensus score calculator"""

from __future__ import annotations

import pytest

from aegis_swr.config.settings import AgentWeightsSettings
from aegis_swr.core.consensus import ConsensusEvaluator
from aegis_swr.core.fault_codes import FaultClass

#: Shared curated weight matrix, used to derive per-fault-class weight maps.
_WEIGHTS = AgentWeightsSettings()


def _weight_map(fault_class: FaultClass) -> dict[str, float]:
    """Return the curated agent-key -> weight map for *fault_class*.

    Mirrors the caller-side resolution that ``agents/panel.py`` now performs:
    ``ConsensusEvaluator.calculate`` is handed a plain weight map, no longer a
    fault class.
    """
    return _WEIGHTS.for_fault_class(fault_class.value).weights


@pytest.fixture
def evaluator() -> ConsensusEvaluator:
    return ConsensusEvaluator()


# ---------------------------------------------------------------------------
# calculate()
# ---------------------------------------------------------------------------


def test_all_agents_full_confidence(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: verifies all agents full confidence.

    Scenario:
        Given test inputs and fixtures for all agents full confidence
        When test_all_agents_full_confidence executes the target flow
        Then the expected outcome for all agents full confidence is confirmed.

    Boundaries:
        - Focus: all agents full confidence
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to all agents full confidence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 1.0, "code_analyst": 1.0, "log_historian": 1.0, "skeptic": 1.0}
    cs = evaluator.calculate(scores, _weight_map(FaultClass.MEMORY_ACCESS_VIOLATION))
    assert cs == pytest.approx(1.0)


def test_all_agents_zero_confidence(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: verifies all agents zero confidence.

    Scenario:
        Given test inputs and fixtures for all agents zero confidence
        When test_all_agents_zero_confidence executes the target flow
        Then the expected outcome for all agents zero confidence is confirmed.

    Boundaries:
        - Focus: all agents zero confidence
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to all agents zero confidence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 0.0, "code_analyst": 0.0, "log_historian": 0.0, "skeptic": 0.0}
    cs = evaluator.calculate(scores, _weight_map(FaultClass.MEMORY_ACCESS_VIOLATION))
    assert cs == pytest.approx(0.0)


def test_weighted_formula_memory_violation(evaluator: ConsensusEvaluator):
    # Weights for MEMORY_ACCESS_VIOLATION: os=0.40, code=0.35, log=0.15, skep=0.10
    """
    [Unit] consensus: verifies weighted formula memory violation.

    Scenario:
        Given test inputs and fixtures for weighted formula memory violation
        When test_weighted_formula_memory_violation executes the target flow
        Then the expected outcome for weighted formula memory violation is confirmed.

    Boundaries:
        - Focus: weighted formula memory violation
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to weighted formula memory violation
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 0.8, "code_analyst": 0.9, "log_historian": 0.7, "skeptic": 0.6}
    expected = 0.40 * 0.8 + 0.35 * 0.9 + 0.15 * 0.7 + 0.10 * 0.6
    cs = evaluator.calculate(scores, _weight_map(FaultClass.MEMORY_ACCESS_VIOLATION))
    assert cs == pytest.approx(expected)


def test_missing_agent_treated_as_zero(evaluator: ConsensusEvaluator):
    # Log historian and skeptic absent.
    """
    [Unit] consensus: verifies missing agent treated as zero.

    Scenario:
        Given test inputs and fixtures for missing agent treated as zero
        When test_missing_agent_treated_as_zero executes the target flow
        Then the expected outcome for missing agent treated as zero is confirmed.

    Boundaries:
        - Focus: missing agent treated as zero
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to missing agent treated as zero
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 1.0, "code_analyst": 1.0}
    cs = evaluator.calculate(scores, _weight_map(FaultClass.DEADLOCK))
    # Only os_kernel (0.35) and code_analyst (0.30) contribute.
    assert cs < 1.0
    assert cs > 0.0


def test_score_bounded_zero_to_one(evaluator: ConsensusEvaluator):
    """
    [Unit] consensus: verifies score bounded zero to one.

    Scenario:
        Given test inputs and fixtures for score bounded zero to one
        When test_score_bounded_zero_to_one executes the target flow
        Then the expected outcome for score bounded zero to one is confirmed.

    Boundaries:
        - Focus: score bounded zero to one
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to score bounded zero to one
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 0.5, "code_analyst": 0.5, "log_historian": 0.5, "skeptic": 0.5}
    cs = evaluator.calculate(scores, _weight_map(FaultClass.UNKNOWN))
    assert 0.0 <= cs <= 1.0


def test_weight_selection_uses_fault_class(evaluator: ConsensusEvaluator):
    # STACK_OVERFLOW: os_kernel weight is 0.45 (higher than default 0.30)
    """
    [Unit] consensus: verifies weight selection uses fault class.

    Scenario:
        Given test inputs and fixtures for weight selection uses fault class
        When test_weight_selection_uses_fault_class executes the target flow
        Then the expected outcome for weight selection uses fault class is confirmed.

    Boundaries:
        - Focus: weight selection uses fault class
        - Fixtures/params: evaluator
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to weight selection uses fault class
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by consensus
    """
    scores = {"os_kernel": 1.0, "code_analyst": 0.0, "log_historian": 0.0, "skeptic": 0.0}
    cs_stack = evaluator.calculate(scores, _weight_map(FaultClass.STACK_OVERFLOW))
    cs_default = evaluator.calculate(scores, _weight_map(FaultClass.UNKNOWN))
    assert cs_stack > cs_default


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
