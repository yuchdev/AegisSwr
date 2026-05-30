"""Tests for the weighted consensus score calculator."""
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


def test_all_agents_full_confidence(evaluator: ConsensusEvaluator) -> None:
    scores = {"os_kernel": 1.0, "code_analyst": 1.0, "log_historian": 1.0, "skeptic": 1.0}
    cs = evaluator.calculate(scores, FaultClass.MEMORY_ACCESS_VIOLATION)
    assert cs == pytest.approx(1.0)


def test_all_agents_zero_confidence(evaluator: ConsensusEvaluator) -> None:
    scores = {"os_kernel": 0.0, "code_analyst": 0.0, "log_historian": 0.0, "skeptic": 0.0}
    cs = evaluator.calculate(scores, FaultClass.MEMORY_ACCESS_VIOLATION)
    assert cs == pytest.approx(0.0)


def test_weighted_formula_memory_violation(evaluator: ConsensusEvaluator) -> None:
    # Weights for MEMORY_ACCESS_VIOLATION: os=0.40, code=0.35, log=0.15, skep=0.10
    scores = {"os_kernel": 0.8, "code_analyst": 0.9, "log_historian": 0.7, "skeptic": 0.6}
    expected = 0.40 * 0.8 + 0.35 * 0.9 + 0.15 * 0.7 + 0.10 * 0.6
    cs = evaluator.calculate(scores, FaultClass.MEMORY_ACCESS_VIOLATION)
    assert cs == pytest.approx(expected)


def test_missing_agent_treated_as_zero(evaluator: ConsensusEvaluator) -> None:
    # Log historian and skeptic absent.
    scores = {"os_kernel": 1.0, "code_analyst": 1.0}
    cs = evaluator.calculate(scores, FaultClass.DEADLOCK)
    # Only os_kernel (0.35) and code_analyst (0.30) contribute.
    assert cs < 1.0
    assert cs > 0.0


def test_score_bounded_zero_to_one(evaluator: ConsensusEvaluator) -> None:
    scores = {"os_kernel": 0.5, "code_analyst": 0.5, "log_historian": 0.5, "skeptic": 0.5}
    cs = evaluator.calculate(scores, FaultClass.UNKNOWN)
    assert 0.0 <= cs <= 1.0


def test_weight_selection_uses_fault_class(evaluator: ConsensusEvaluator) -> None:
    # STACK_OVERFLOW: os_kernel weight is 0.45 (higher than default 0.30)
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
) -> None:
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
) -> None:
    assert evaluator.is_deadlocked(score, round_num, max_rounds, hitl_threshold) is expected
