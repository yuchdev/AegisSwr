"""Package-structure tests for the ``aegis_swr.agents`` restructure (Task 01.0).

These lock in the import contract established when the four base debate agents
moved into the ``agents/base/`` subpackage: the new base path resolves, the
top-level re-export still resolves, and the (initially empty) ``forensic`` and
``synthesis`` category packages are importable.
"""

from __future__ import annotations

import importlib


def test_base_import_path():
    """[Unit] agents package: The moved agents resolve from the new ``aegis_swr.agents.base`` package.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the moved agents resolve from the new ``aegis_swr.agents.base`` package.
    """
    base = importlib.import_module("aegis_swr.agents.base")

    assert base.BaseAgent is not None
    assert {
        base.OSKernelAgent.agent_key,
        base.CodeAnalystAgent.agent_key,
        base.LogHistorianAgent.agent_key,
        base.SkepticAgent.agent_key,
    } == {"os_kernel", "code_analyst", "log_historian", "skeptic"}


def test_base_shared_primitives_reexported():
    """[Unit] agents package: ``AgentSpec`` and ``AgentCategory`` re-export from the base package.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``AgentSpec`` and ``AgentCategory`` re-export from the base package.
    """
    base = importlib.import_module("aegis_swr.agents.base")

    assert base.AgentSpec is not None
    assert base.AgentCategory is not None


def test_top_level_reexport():
    """[Unit] agents package: The four agents remain importable from the top-level ``aegis_swr.agents``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the four agents remain importable from the top-level ``aegis_swr.agents``.
    """
    agents = importlib.import_module("aegis_swr.agents")

    assert agents.OSKernelAgent is not None
    assert agents.CodeAnalystAgent is not None
    assert agents.LogHistorianAgent is not None
    assert agents.SkepticAgent is not None


def test_forensic_package_importable():
    """[Unit] agents package: The ``forensic`` category package imports and exports its specialist agents.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the ``forensic`` category package imports and exports its specialist agents.
    """
    module = importlib.import_module("aegis_swr.agents.forensic")
    assert "MemoryForensicsAgent" in module.__all__


def test_synthesis_package_importable():
    """[Unit] agents package: The ``synthesis`` category package imports and exports the planner agent.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the ``synthesis`` category package imports and exports the planner agent.
    """
    module = importlib.import_module("aegis_swr.agents.synthesis")
    assert "RemediationPlannerAgent" in module.__all__
