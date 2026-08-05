"""Package-structure tests for the ``aegis_swr.agents`` restructure (Task 01.0).

These lock in the import contract established when the four base debate agents
moved into the ``agents/base/`` subpackage: the new base path resolves, the
top-level re-export still resolves, and the (initially empty) ``forensic`` and
``synthesis`` category packages are importable.
"""

from __future__ import annotations

import importlib


def test_base_import_path() -> None:
    """[Unit] agents package: The moved agents resolve from the new ``aegis_swr.agents.base`` package.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the moved agents resolve from the new ``aegis_swr.agents.base`` package.
    """
    from aegis_swr.agents.base import (
        BaseAgent,
        CodeAnalystAgent,
        LogHistorianAgent,
        OSKernelAgent,
        SkepticAgent,
    )

    assert BaseAgent is not None
    assert {
        OSKernelAgent.agent_key,
        CodeAnalystAgent.agent_key,
        LogHistorianAgent.agent_key,
        SkepticAgent.agent_key,
    } == {"os_kernel", "code_analyst", "log_historian", "skeptic"}


def test_base_shared_primitives_reexported() -> None:
    """[Unit] agents package: ``AgentSpec`` and ``AgentCategory`` re-export from the base package.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``AgentSpec`` and ``AgentCategory`` re-export from the base package.
    """
    from aegis_swr.agents.base import AgentCategory, AgentSpec

    assert AgentSpec is not None
    assert AgentCategory is not None


def test_top_level_reexport() -> None:
    """[Unit] agents package: The four agents remain importable from the top-level ``aegis_swr.agents``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the four agents remain importable from the top-level ``aegis_swr.agents``.
    """
    from aegis_swr.agents import (
        CodeAnalystAgent,
        LogHistorianAgent,
        OSKernelAgent,
        SkepticAgent,
    )

    assert OSKernelAgent is not None
    assert CodeAnalystAgent is not None
    assert LogHistorianAgent is not None
    assert SkepticAgent is not None


def test_forensic_package_importable() -> None:
    """[Unit] agents package: The ``forensic`` category package imports and exports its specialist agents.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the ``forensic`` category package imports and exports its specialist agents.
    """
    module = importlib.import_module("aegis_swr.agents.forensic")
    assert "MemoryForensicsAgent" in module.__all__


def test_synthesis_package_importable() -> None:
    """[Unit] agents package: The ``synthesis`` category package imports and exports the planner agent.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the ``synthesis`` category package imports and exports the planner agent.
    """
    module = importlib.import_module("aegis_swr.agents.synthesis")
    assert "RemediationPlannerAgent" in module.__all__
