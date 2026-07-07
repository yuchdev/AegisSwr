"""Verify that ABCs cannot be instantiated directly and that concrete
subclasses satisfying all abstract methods can be instantiated"""

from __future__ import annotations

import pytest

from aegis_swr.agents.base import BaseAgent
from aegis_swr.backends.base import (
    AIAPIBackend,
    CodeBackend,
    DebugBackend,
    LogBackend,
    ObjectStore,
    RelationalStore,
    VectorStore,
)

# ---------------------------------------------------------------------------
# ABCs raise TypeError when instantiated directly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        AIAPIBackend,
        DebugBackend,
        RelationalStore,
        ObjectStore,
        VectorStore,
        LogBackend,
        CodeBackend,
    ],
)
def test_backend_abc_cannot_be_instantiated(cls: type):
    """
    [Unit] interfaces: verifies backend abc cannot be instantiated.

    Scenario:
        Given test inputs and fixtures for backend abc cannot be instantiated
        When test_backend_abc_cannot_be_instantiated executes the target flow
        Then the expected outcome for backend abc cannot be instantiated is confirmed.

    Boundaries:
        - Focus: backend abc cannot be instantiated
        - Fixtures/params: none (parametrized, 7 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to backend abc cannot be instantiated
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by interfaces
    """
    with pytest.raises(TypeError):
        cls()


def test_base_agent_cannot_be_instantiated():
    """
    [Unit] interfaces: verifies base agent cannot be instantiated.

    Scenario:
        Given test inputs and fixtures for base agent cannot be instantiated
        When test_base_agent_cannot_be_instantiated executes the target flow
        Then the expected outcome for base agent cannot be instantiated is confirmed.

    Boundaries:
        - Focus: base agent cannot be instantiated
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to base agent cannot be instantiated
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by interfaces
    """
    with pytest.raises(TypeError):
        BaseAgent(ai_backend=None, settings=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Minimal concrete subclasses can be instantiated
# ---------------------------------------------------------------------------


def test_minimal_ai_backend_subclass():
    """
    [Unit] interfaces: verifies minimal ai backend subclass.

    Scenario:
        Given test inputs and fixtures for minimal ai backend subclass
        When test_minimal_ai_backend_subclass executes the target flow
        Then the expected outcome for minimal ai backend subclass is confirmed.

    Boundaries:
        - Focus: minimal ai backend subclass
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to minimal ai backend subclass
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by interfaces
    """
    from collections.abc import AsyncGenerator
    from typing import Any, Optional

    from pydantic import BaseModel

    class _DummyAI(AIAPIBackend):
        model_name = "dummy"

        async def generate(
            self,
            system_prompt: str,
            messages: list[dict[str, Any]],
            output_schema: Optional[type[BaseModel]] = None,
        ) -> BaseModel | str:
            return "ok"

        async def stream(
            self,
            system_prompt: str,
            messages: list[dict[str, Any]],
        ) -> AsyncGenerator[str, None]:
            async def _gen() -> AsyncGenerator[str, None]:
                yield "token"

            return _gen()

    backend = _DummyAI()
    assert backend.model_name == "dummy"


def test_minimal_base_agent_subclass():
    """
    [Unit] interfaces: verifies minimal base agent subclass.

    Scenario:
        Given test inputs and fixtures for minimal base agent subclass
        When test_minimal_base_agent_subclass executes the target flow
        Then the expected outcome for minimal base agent subclass is confirmed.

    Boundaries:
        - Focus: minimal base agent subclass
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to minimal base agent subclass
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by interfaces
    """
    from typing import ClassVar

    from aegis_swr.agents.base import AgentCategory
    from aegis_swr.core.schemas import AgentRole, AgentTurn, InvestigationState

    class _DummyAgent(BaseAgent):
        agent_key: ClassVar[str] = "dummy"
        display_name: ClassVar[str] = "Dummy"
        category: ClassVar[AgentCategory] = "base"
        role: ClassVar[AgentRole] = AgentRole.INVESTIGATOR

        @property
        def system_prompt(self) -> str:
            return "dummy"

        async def run(self, state: InvestigationState) -> AgentTurn:
            return self.make_turn(turn_number=1, message="ok", confidence_score=0.5)

    agent = _DummyAgent(ai_backend=None, settings=None)  # type: ignore[arg-type]
    assert agent.system_prompt == "dummy"
