"""Unit tests for :mod:`scripts.ci_relevance`."""

from __future__ import annotations

import subprocess

import pytest
import scripts.ci_relevance as ci_relevance


@pytest.fixture(autouse=True)
def _clear_relevant_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure no ambient GitHub Actions env var leaks between tests."""
    for key in (
        "GITHUB_EVENT_NAME",
        "PR_BASE_SHA",
        "PR_HEAD_SHA",
        "GITHUB_EVENT_BEFORE",
        "GITHUB_EVENT_AFTER",
        "GITHUB_SHA",
        "GITHUB_OUTPUT",
    ):
        monkeypatch.delenv(key, raising=False)


class TestIsForcedRun:
    """Tests for :func:`scripts.ci_relevance.is_forced_run`."""

    @pytest.mark.parametrize(
        "path",
        [
            "src/aegis_swr/core/orchestrator.py",
            "pyproject.toml",
            "uv.lock",
            "requirements-dev.txt",
            ".github/workflows/ci.yml",
            ".github/hooks/guard_bash.py",
            "ruff.cfg",
            "Dockerfile",
            "Dockerfile.ci",
        ],
    )
    def test_matches_source_and_project_files(self, path: str):
        """
        [Unit] is forced run: verifies matches source and project files.

        Scenario:
            Given test inputs and fixtures for matches source and project files
            When test_matches_source_and_project_files executes the target flow
            Then the expected outcome for matches source and project files is confirmed.

        Boundaries:
            - Focus: matches source and project files
            - Fixtures/params: path (parametrized, 9 cases)
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to matches source and project files
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by is forced run
        """
        assert ci_relevance.is_forced_run(path) is True

    @pytest.mark.parametrize("path", ["README.md", "docs/adr/0005-foo.md", ".claude/agents/python-expert.md"])
    def test_does_not_match_docs_or_agents(self, path: str):
        """
        [Unit] is forced run: verifies does not match docs or agents.

        Scenario:
            Given test inputs and fixtures for does not match docs or agents
            When test_does_not_match_docs_or_agents executes the target flow
            Then the expected outcome for does not match docs or agents is confirmed.

        Boundaries:
            - Focus: does not match docs or agents
            - Fixtures/params: path (parametrized, 3 cases)
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to does not match docs or agents
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by is forced run
        """
        assert ci_relevance.is_forced_run(path) is False


class TestIsSkippable:
    """Tests for :func:`scripts.ci_relevance.is_skippable`."""

    @pytest.mark.parametrize(
        "path",
        [
            "README.md",
            "CHANGELOG.md",
            "docs/adr/0005-flake8-lint-adoption.md",
            "docs/README.md",
            ".claude/agents/python-expert.md",
            ".claude/skills/adr-write/SKILL.md",
            ".claude/CLAUDE.md",
            ".github/copilot/agents/app-architect.md",
            ".github/copilot-instructions.md",
            "LICENSE",
            ".gitignore",
        ],
    )
    def test_matches_docs_agents_and_skills(self, path: str):
        """
        [Unit] is skippable: verifies matches docs agents and skills.

        Scenario:
            Given test inputs and fixtures for matches docs agents and skills
            When test_matches_docs_agents_and_skills executes the target flow
            Then the expected outcome for matches docs agents and skills is confirmed.

        Boundaries:
            - Focus: matches docs agents and skills
            - Fixtures/params: path (parametrized, 11 cases)
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to matches docs agents and skills
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by is skippable
        """
        assert ci_relevance.is_skippable(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/aegis_swr/core/orchestrator.py",
            "pyproject.toml",
            "uv.lock",
            # Root-only *.md must NOT swallow nested README-style files -
            # a doc change deep in src/ is far more likely to be documenting
            # a real code change than an isolated, CI-irrelevant edit.
            "src/aegis_swr/openclaude/README.md",
        ],
    )
    def test_does_not_match_source_or_nested_readmes(self, path: str):
        """
        [Unit] is skippable: verifies does not match source or nested readmes.

        Scenario:
            Given test inputs and fixtures for does not match source or nested readmes
            When test_does_not_match_source_or_nested_readmes executes the target flow
            Then the expected outcome for does not match source or nested readmes is confirmed.

        Boundaries:
            - Focus: does not match source or nested readmes
            - Fixtures/params: path (parametrized, 4 cases)
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to does not match source or nested readmes
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by is skippable
        """
        assert ci_relevance.is_skippable(path) is False


class TestDecide:
    """Tests for :func:`scripts.ci_relevance.decide`."""

    def test_none_means_run(self):
        """
        [Unit] decide: verifies none means run.

        Scenario:
            Given test inputs and fixtures for none means run
            When test_none_means_run executes the target flow
            Then the expected outcome for none means run is confirmed.

        Boundaries:
            - Focus: none means run
            - Fixtures/params: none
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to none means run
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by decide
        """
        decision = ci_relevance.decide(None)
        assert decision.run_ci is True
        assert "no diff available" in decision.reason

    def test_empty_list_means_run_fail_safe(self):
        """
        [Unit] decide: verifies empty list means run fail safe.

        Scenario:
            Given test inputs and fixtures for empty list means run fail safe
            When test_empty_list_means_run_fail_safe executes the target flow
            Then the expected outcome for empty list means run fail safe is confirmed.

        Boundaries:
            - Focus: empty list means run fail safe
            - Fixtures/params: none
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to empty list means run fail safe
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by decide
        """
        decision = ci_relevance.decide([])
        assert decision.run_ci is True
        assert "fail-safe" in decision.reason

    def test_all_skippable_means_skip(self):
        """
        [Unit] decide: verifies all skippable means skip.

        Scenario:
            Given test inputs and fixtures for all skippable means skip
            When test_all_skippable_means_skip executes the target flow
            Then the expected outcome for all skippable means skip is confirmed.

        Boundaries:
            - Focus: all skippable means skip
            - Fixtures/params: none
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to all skippable means skip
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by decide
        """
        decision = ci_relevance.decide(["README.md", "docs/adr/0005-foo.md", ".claude/agents/python-expert.md"])
        assert decision.run_ci is False

    def test_any_forced_pattern_means_run(self):
        """
        [Unit] decide: verifies any forced pattern means run.

        Scenario:
            Given test inputs and fixtures for any forced pattern means run
            When test_any_forced_pattern_means_run executes the target flow
            Then the expected outcome for any forced pattern means run is confirmed.

        Boundaries:
            - Focus: any forced pattern means run
            - Fixtures/params: none
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to any forced pattern means run
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by decide
        """
        decision = ci_relevance.decide(["README.md", "src/aegis_swr/core/orchestrator.py"])
        assert decision.run_ci is True
        assert "always-run pattern" in decision.reason

    def test_unclassified_file_means_run(self):
        # A file type this script has never been taught about must default to
        # "run", not "skip" - this is the deny-by-default safety net that
        # matters more than either explicit pattern list.
        """
        [Unit] decide: verifies unclassified file means run.

        Scenario:
            Given test inputs and fixtures for unclassified file means run
            When test_unclassified_file_means_run executes the target flow
            Then the expected outcome for unclassified file means run is confirmed.

        Boundaries:
            - Focus: unclassified file means run
            - Fixtures/params: none
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to unclassified file means run
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by decide
        """
        decision = ci_relevance.decide(["README.md", "assets/new_logo.svg"])
        assert decision.run_ci is True
        assert "not on the skip-list" in decision.reason


class TestGetChangedFilesFromGit:
    """Tests for :func:`scripts.ci_relevance.get_changed_files_from_git`."""

    def test_schedule_event_has_no_diff(self, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] get changed files from git: verifies schedule event has no diff.

        Scenario:
            Given test inputs and fixtures for schedule event has no diff
            When test_schedule_event_has_no_diff executes the target flow
            Then the expected outcome for schedule event has no diff is confirmed.

        Boundaries:
            - Focus: schedule event has no diff
            - Fixtures/params: monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to schedule event has no diff
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by get changed files from git
        """
        monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
        assert ci_relevance.get_changed_files_from_git() is None

    def test_workflow_dispatch_has_no_diff(self, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] get changed files from git: verifies workflow dispatch has no diff.

        Scenario:
            Given test inputs and fixtures for workflow dispatch has no diff
            When test_workflow_dispatch_has_no_diff executes the target flow
            Then the expected outcome for workflow dispatch has no diff is confirmed.

        Boundaries:
            - Focus: workflow dispatch has no diff
            - Fixtures/params: monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to workflow dispatch has no diff
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by get changed files from git
        """
        monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
        assert ci_relevance.get_changed_files_from_git() is None

    def test_pull_request_without_base_sha_fails_safe_to_none(self, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] get changed files from git: verifies pull request without base sha fails safe to none.

        Scenario:
            Given test inputs and fixtures for pull request without base sha fails safe to none
            When test_pull_request_without_base_sha_fails_safe_to_none executes the target flow
            Then the expected outcome for pull request without base sha fails safe to none is confirmed.

        Boundaries:
            - Focus: pull request without base sha fails safe to none
            - Fixtures/params: monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to pull request without base sha fails safe to none
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by get changed files from git
        """
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        assert ci_relevance.get_changed_files_from_git() is None

    def test_pull_request_diffs_between_base_and_head(self, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] get changed files from git: verifies pull request diffs between base and head.

        Scenario:
            Given test inputs and fixtures for pull request diffs between base and head
            When test_pull_request_diffs_between_base_and_head executes the target flow
            Then the expected outcome for pull request diffs between base and head is confirmed.

        Boundaries:
            - Focus: pull request diffs between base and head
            - Fixtures/params: monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to pull request diffs between base and head
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by get changed files from git
        """
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        monkeypatch.setenv("PR_BASE_SHA", "base-sha")
        monkeypatch.setenv("PR_HEAD_SHA", "head-sha")

        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs) -> subprocess.CompletedProcess:
            """Record the invoked command and fake a successful fetch/diff."""
            calls.append(cmd)
            if cmd[:2] == ["git", "fetch"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "a.py\nb.md\n", "")

        monkeypatch.setattr(ci_relevance.subprocess, "run", fake_run)

        files = ci_relevance.get_changed_files_from_git()
        assert files == ["a.py", "b.md"]
        assert calls[0] == ["git", "fetch", "--depth=1", "origin", "base-sha"]
        assert calls[1] == ["git", "diff", "--name-only", "base-sha...head-sha"]

    def test_pull_request_fetch_failure_fails_safe_to_none(self, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] get changed files from git: verifies pull request fetch failure fails safe to none.

        Scenario:
            Given test inputs and fixtures for pull request fetch failure fails safe to none
            When test_pull_request_fetch_failure_fails_safe_to_none executes the target flow
            Then the expected outcome for pull request fetch failure fails safe to none is confirmed.

        Boundaries:
            - Focus: pull request fetch failure fails safe to none
            - Fixtures/params: monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to pull request fetch failure fails safe to none
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by get changed files from git
        """
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        monkeypatch.setenv("PR_BASE_SHA", "base-sha")

        def fake_run(cmd, **kwargs):
            """Simulate a failing git invocation."""
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(ci_relevance.subprocess, "run", fake_run)

        assert ci_relevance.get_changed_files_from_git() is None

    def test_push_diffs_between_before_and_after(self, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] get changed files from git: verifies push diffs between before and after.

        Scenario:
            Given test inputs and fixtures for push diffs between before and after
            When test_push_diffs_between_before_and_after executes the target flow
            Then the expected outcome for push diffs between before and after is confirmed.

        Boundaries:
            - Focus: push diffs between before and after
            - Fixtures/params: monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to push diffs between before and after
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by get changed files from git
        """
        monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
        monkeypatch.setenv("GITHUB_EVENT_BEFORE", "before-sha")
        monkeypatch.setenv("GITHUB_EVENT_AFTER", "after-sha")

        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs) -> subprocess.CompletedProcess:
            """Record the invoked command and fake a successful diff."""
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "src/x.py\n", "")

        monkeypatch.setattr(ci_relevance.subprocess, "run", fake_run)

        files = ci_relevance.get_changed_files_from_git()
        assert files == ["src/x.py"]
        assert calls[0] == ["git", "diff", "--name-only", "before-sha", "after-sha"]

    def test_push_new_branch_all_zero_before_diffs_against_empty_tree(self, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] get changed files from git: verifies push new branch all zero before diffs against empty tree.

        Scenario:
            Given test inputs and fixtures for push new branch all zero before diffs against empty tree
            When test_push_new_branch_all_zero_before_diffs_against_empty_tree executes the target flow
            Then the expected outcome for push new branch all zero before diffs against empty tree is confirmed.

        Boundaries:
            - Focus: push new branch all zero before diffs against empty tree
            - Fixtures/params: monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to push new branch all zero before diffs against empty tree
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by get changed files from git
        """
        monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
        monkeypatch.setenv("GITHUB_EVENT_BEFORE", "0" * 40)
        monkeypatch.setenv("GITHUB_EVENT_AFTER", "after-sha")

        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs) -> subprocess.CompletedProcess:
            """Record the invoked command and fake a successful diff."""
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "src/x.py\n", "")

        monkeypatch.setattr(ci_relevance.subprocess, "run", fake_run)

        ci_relevance.get_changed_files_from_git()
        assert calls[0] == ["git", "diff", "--name-only", ci_relevance._EMPTY_TREE_SHA, "after-sha"]

    def test_push_diff_failure_fails_safe_to_none(self, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] get changed files from git: verifies push diff failure fails safe to none.

        Scenario:
            Given test inputs and fixtures for push diff failure fails safe to none
            When test_push_diff_failure_fails_safe_to_none executes the target flow
            Then the expected outcome for push diff failure fails safe to none is confirmed.

        Boundaries:
            - Focus: push diff failure fails safe to none
            - Fixtures/params: monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to push diff failure fails safe to none
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by get changed files from git
        """
        monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
        monkeypatch.setenv("GITHUB_EVENT_BEFORE", "before-sha")
        monkeypatch.setenv("GITHUB_EVENT_AFTER", "after-sha")

        def fake_run(cmd, **kwargs):
            """Simulate a failing git invocation."""
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(ci_relevance.subprocess, "run", fake_run)

        assert ci_relevance.get_changed_files_from_git() is None


class TestMainOutput:
    """Tests for :func:`scripts.ci_relevance.main`'s ``GITHUB_OUTPUT`` writing."""

    def test_writes_run_ci_to_github_output_file(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] main output: verifies writes run ci to github output file.

        Scenario:
            Given test inputs and fixtures for writes run ci to github output file
            When test_writes_run_ci_to_github_output_file executes the target flow
            Then the expected outcome for writes run ci to github output file is confirmed.

        Boundaries:
            - Focus: writes run ci to github output file
            - Fixtures/params: tmp_path, monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to writes run ci to github output file
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by main output
        """
        output_file = tmp_path / "github_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        exit_code = ci_relevance.main(["--files", "README.md"])

        assert exit_code == 0
        assert output_file.read_text(encoding="utf-8") == "run_ci=false\n"

    def test_forced_pattern_via_files_flag(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        """
        [Unit] main output: verifies forced pattern via files flag.

        Scenario:
            Given test inputs and fixtures for forced pattern via files flag
            When test_forced_pattern_via_files_flag executes the target flow
            Then the expected outcome for forced pattern via files flag is confirmed.

        Boundaries:
            - Focus: forced pattern via files flag
            - Fixtures/params: tmp_path, monkeypatch
            - Scope: assertions and setup in this test case only

        On failure, first check:
            - Assertion details tied to forced pattern via files flag
            - Fixture or parameter values used by this test
            - Recent changes in code paths exercised by main output
        """
        output_file = tmp_path / "github_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        ci_relevance.main(["--files", "README.md", "src/aegis_swr/core/orchestrator.py"])

        assert output_file.read_text(encoding="utf-8") == "run_ci=true\n"
