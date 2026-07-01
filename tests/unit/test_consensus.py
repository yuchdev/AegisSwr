"""Tests for the weighted consensus score calculator"""
from __future__ import annotations

import pytest

from aegis_swr.config.settings import AgentWeightsSettings
from aegis_swr.core.consensus import ConsensusEvaluator
from aegis_swr.core.fault_codes import FaultClass


@pytest.fixture
def evaluator() -> ConsensusEvaluator:
    return ConsensusEvaluator(AgentWeightsSettings())


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
    cs = evaluator.calculate(scores, FaultClass.MEMORY_ACCESS_VIOLATION)
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
    cs = evaluator.calculate(scores, FaultClass.MEMORY_ACCESS_VIOLATION)
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
    cs = evaluator.calculate(scores, FaultClass.MEMORY_ACCESS_VIOLATION)
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
    cs = evaluator.calculate(scores, FaultClass.DEADLOCK)
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
    cs = evaluator.calculate(scores, FaultClass.UNKNOWN)
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
    cs_stack = evaluator.calculate(scores, FaultClass.STACK_OVERFLOW)
    cs_default = evaluator.calculate(scores, FaultClass.UNKNOWN)
    assert cs_stack > cs_default


# ---------------------------------------------------------------------------
# is_converged()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,threshold,same,expected",
    [
        (0.90, 0.85, True, True),
        (0.85, 0.85, True, True),   # exactly at threshold
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
        (0.40, 4, 4, 0.50, True),   # at max rounds, below threshold
        (0.40, 5, 4, 0.50, True),   # past max rounds
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
