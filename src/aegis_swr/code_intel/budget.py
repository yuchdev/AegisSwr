"""Boundary-level token/cost accounting for a single delegated call (C5).

Aegis SWR cannot see OpenClaude's internal per-step token usage, so accounting
is a two-step boundary estimate: a *pre-check* before the call and a *charge*
after the stream completes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CallBudget:
    """A single-call token budget.

    :ivar max_tokens: Hard ceiling for the call's boundary token estimate.
    :ivar spent: Tokens charged so far (``0`` until :meth:`charge`).
    """

    max_tokens: int
    spent: int = 0

    @property
    def remaining(self) -> int:
        """Tokens still available before the ceiling is reached."""
        return max(0, self.max_tokens - self.spent)

    def can_afford(self, estimate: int) -> bool:
        """Pre-check step (C5.1): whether *estimate* fits under the ceiling.

        Called with ``max_response_tokens // 4`` before opening a connection.

        :param estimate: Conservative pre-call token estimate.
        :return: ``True`` if the estimate fits within :attr:`remaining`.
        """
        return estimate <= self.remaining

    def charge(self, tokens: int) -> None:
        """Post-charge step (C5.2): record *tokens* actually estimated.

        Called after stream completion with ``max(1, len(content) // 4)``.
        Charging is idempotent per call and never raises on overshoot (the cap
        is enforced by the pre-check and by response truncation, not here).

        :param tokens: Boundary token estimate to add to :attr:`spent`.
        """
        self.spent += tokens
