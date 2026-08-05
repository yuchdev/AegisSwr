"""Unit tests for the :mod:`aegis_swr.code_intel.budget` boundary accountant."""

from __future__ import annotations

from aegis_swr.code_intel.budget import CallBudget


def test_remaining_math() -> None:
    """[Unit] budget: ``remaining`` is ``max_tokens - spent``, floored at zero.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``remaining`` is ``max_tokens - spent``, floored at zero.
    """
    budget = CallBudget(max_tokens=100)
    assert budget.remaining == 100
    budget.charge(30)
    assert budget.remaining == 70


def test_remaining_never_negative_on_overshoot() -> None:
    """[Unit] budget: Overshooting ``spent`` past the ceiling floors ``remaining`` at zero.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: overshooting ``spent`` past the ceiling floors ``remaining`` at zero.
    """
    budget = CallBudget(max_tokens=10, spent=25)
    assert budget.remaining == 0


def test_can_afford_boundary_equal_is_affordable() -> None:
    """[Unit] budget: An estimate exactly equal to ``remaining`` is affordable.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an estimate exactly equal to ``remaining`` is affordable.
    """
    budget = CallBudget(max_tokens=50, spent=10)
    assert budget.remaining == 40
    assert budget.can_afford(40) is True


def test_can_afford_over_remaining_is_not_affordable() -> None:
    """[Unit] budget: An estimate one token over ``remaining`` is not affordable.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an estimate one token over ``remaining`` is not affordable.
    """
    budget = CallBudget(max_tokens=50, spent=10)
    assert budget.can_afford(41) is False


def test_can_afford_under_remaining_is_affordable() -> None:
    """[Unit] budget: An estimate well under ``remaining`` is affordable.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an estimate well under ``remaining`` is affordable.
    """
    budget = CallBudget(max_tokens=50)
    assert budget.can_afford(1) is True


def test_charge_accumulates() -> None:
    """[Unit] budget: Successive charges accumulate into ``spent``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: successive charges accumulate into ``spent``.
    """
    budget = CallBudget(max_tokens=100)
    budget.charge(10)
    budget.charge(15)
    assert budget.spent == 25
    assert budget.remaining == 75


def test_charge_tolerates_overshoot_without_raising() -> None:
    """[Unit] budget: Charging past the ceiling records the overshoot but never raises.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: charging past the ceiling records the overshoot but never raises.
    """
    budget = CallBudget(max_tokens=5)
    budget.charge(9)
    assert budget.spent == 9
    assert budget.remaining == 0
