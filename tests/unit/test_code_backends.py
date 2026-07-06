"""Unit tests for the code backends - no network, no system git required"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from aegis_swr.backends.code import (
    FilesystemCodeAdapter,
    GitCodeAdapter,
    create_code_backend,
)
from aegis_swr.backends.code.git_adapter import (
    _parse_blame_porcelain,
    _parse_git_log,
)
from aegis_swr.config.settings import CodeBackendSettings
from aegis_swr.core.exceptions import CodeBackendError

_RS = "\x1e"
_FS = "\x1f"

_GIT_CMD = "aegis_swr.backends.code.git_adapter.subprocess.run"


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> mock.Mock:
    proc = mock.Mock()
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


def _git_log_fixture() -> str:
    return (
        f"{_RS}abc123{_FS}Alice <a@x.com>{_FS}2026-05-30T13:00:00+00:00{_FS}Fix timeout\n"
        "db_writer.py\n"
        "config.yaml\n"
        f"{_RS}def456{_FS}Bob <b@x.com>{_FS}2026-05-30T12:30:00+00:00{_FS}Refactor pool\n"
        "pool.py\n"
    )


def _blame_porcelain_fixture() -> str:
    sha = "a" * 40
    return (
        f"{sha} 1 1 1\n"
        "author Alice\n"
        "author-mail <a@x.com>\n"
        "author-time 1748609100\n"
        "author-tz +0000\n"
        "summary Fix timeout\n"
        "filename db_writer.py\n"
        "\tdef serialize(self):\n"
    )


# ---------------------------------------------------------------------------
# Pure parsers
# ---------------------------------------------------------------------------


def test_parse_git_log_records():
    """
    [Unit] code backends: verifies parse git log records.

    Scenario:
        Given test inputs and fixtures for parse git log records
        When test_parse_git_log_records executes the target flow
        Then the expected outcome for parse git log records is confirmed.

    Boundaries:
        - Focus: parse git log records
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to parse git log records
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    commits = _parse_git_log(_git_log_fixture())
    assert len(commits) == 2
    first = commits[0]
    assert first.sha == "abc123"
    assert first.author == "Alice <a@x.com>"
    assert first.message == "Fix timeout"
    assert first.files_changed == ["db_writer.py", "config.yaml"]
    assert commits[1].files_changed == ["pool.py"]


def test_parse_blame_porcelain():
    """
    [Unit] code backends: verifies parse blame porcelain.

    Scenario:
        Given test inputs and fixtures for parse blame porcelain
        When test_parse_blame_porcelain executes the target flow
        Then the expected outcome for parse blame porcelain is confirmed.

    Boundaries:
        - Focus: parse blame porcelain
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to parse blame porcelain
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    records = _parse_blame_porcelain(_blame_porcelain_fixture(), first_line=1)
    assert len(records) == 1
    rec = records[0]
    assert rec.line_number == 1
    assert rec.sha == "a" * 40
    assert rec.author == "Alice"
    assert rec.content == "def serialize(self):"


# ---------------------------------------------------------------------------
# GitCodeAdapter (mocked subprocess)
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def git_adapter() -> GitCodeAdapter:
    return GitCodeAdapter(CodeBackendSettings(enabled=True, provider="git"))


def test_git_get_commits_before_parses_records(git_adapter: GitCodeAdapter, git_repo: Path):
    """
    [Mock] code backends: verifies git get commits before parses records.

    Scenario:
        Given test inputs and fixtures for git get commits before parses records
        When test_git_get_commits_before_parses_records executes the target flow
        Then the expected outcome for git get commits before parses records is confirmed.

    Boundaries:
        - Focus: git get commits before parses records
        - Fixtures/params: git_adapter, git_repo
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to git get commits before parses records
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    before = datetime(2026, 5, 30, 14, 0, 0, tzinfo=UTC)
    with mock.patch(_GIT_CMD, return_value=_completed(_git_log_fixture())):
        commits = git_adapter.get_commits_before(str(git_repo), before, limit=5)
    assert [c.sha for c in commits] == ["abc123", "def456"]


def test_git_blame_parses_porcelain(git_adapter: GitCodeAdapter, git_repo: Path):
    """
    [Mock] code backends: verifies git blame parses porcelain.

    Scenario:
        Given test inputs and fixtures for git blame parses porcelain
        When test_git_blame_parses_porcelain executes the target flow
        Then the expected outcome for git blame parses porcelain is confirmed.

    Boundaries:
        - Focus: git blame parses porcelain
        - Fixtures/params: git_adapter, git_repo
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to git blame parses porcelain
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    with mock.patch(_GIT_CMD, return_value=_completed(_blame_porcelain_fixture())):
        records = git_adapter.blame(str(git_repo), "db_writer.py", (1, 1))
    assert records[0].author == "Alice"


def test_git_missing_repo_raises(git_adapter: GitCodeAdapter, tmp_path: Path):
    """
    [Unit] code backends: verifies git missing repo raises.

    Scenario:
        Given test inputs and fixtures for git missing repo raises
        When test_git_missing_repo_raises executes the target flow
        Then the expected outcome for git missing repo raises is confirmed.

    Boundaries:
        - Focus: git missing repo raises
        - Fixtures/params: git_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to git missing repo raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    before = datetime(2026, 5, 30, 14, 0, 0, tzinfo=UTC)
    with pytest.raises(CodeBackendError, match="Not a git repository"):
        git_adapter.get_commits_before(str(tmp_path), before)


def test_git_missing_binary_raises(git_adapter: GitCodeAdapter, git_repo: Path):
    """
    [Mock] code backends: verifies git missing binary raises.

    Scenario:
        Given test inputs and fixtures for git missing binary raises
        When test_git_missing_binary_raises executes the target flow
        Then the expected outcome for git missing binary raises is confirmed.

    Boundaries:
        - Focus: git missing binary raises
        - Fixtures/params: git_adapter, git_repo
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to git missing binary raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    before = datetime(2026, 5, 30, 14, 0, 0, tzinfo=UTC)
    with (
        mock.patch(_GIT_CMD, side_effect=FileNotFoundError("git")),
        pytest.raises(CodeBackendError, match="git binary not found"),
    ):
        git_adapter.get_commits_before(str(git_repo), before)


def test_git_nonzero_exit_raises(git_adapter: GitCodeAdapter, git_repo: Path):
    """
    [Mock] code backends: verifies git nonzero exit raises.

    Scenario:
        Given test inputs and fixtures for git nonzero exit raises
        When test_git_nonzero_exit_raises executes the target flow
        Then the expected outcome for git nonzero exit raises is confirmed.

    Boundaries:
        - Focus: git nonzero exit raises
        - Fixtures/params: git_adapter, git_repo
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to git nonzero exit raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    before = datetime(2026, 5, 30, 14, 0, 0, tzinfo=UTC)
    with (
        mock.patch(_GIT_CMD, return_value=_completed(returncode=128, stderr="fatal: bad")),
        pytest.raises(CodeBackendError, match="failed"),
    ):
        git_adapter.get_commits_before(str(git_repo), before)


def test_git_path_traversal_blocked(git_adapter: GitCodeAdapter, git_repo: Path):
    """
    [Unit] code backends: verifies git path traversal blocked.

    Scenario:
        Given test inputs and fixtures for git path traversal blocked
        When test_git_path_traversal_blocked executes the target flow
        Then the expected outcome for git path traversal blocked is confirmed.

    Boundaries:
        - Focus: git path traversal blocked
        - Fixtures/params: git_adapter, git_repo
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to git path traversal blocked
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    with pytest.raises(ValueError, match="traversal"):
        git_adapter.get_file_diff(str(git_repo), "../../etc/passwd", "abc123")


# ---------------------------------------------------------------------------
# FilesystemCodeAdapter
# ---------------------------------------------------------------------------


@pytest.fixture
def fs_adapter() -> FilesystemCodeAdapter:
    return FilesystemCodeAdapter(CodeBackendSettings(enabled=True, provider="filesystem"))


def _touch(path: Path, when: datetime, content: str = "x\n"):
    path.write_text(content, encoding="utf-8")
    ts = when.timestamp()
    os.utime(path, (ts, ts))


def test_fs_commits_within_window(fs_adapter: FilesystemCodeAdapter, tmp_path: Path):
    """
    [Unit] code backends: verifies fs commits within window.

    Scenario:
        Given test inputs and fixtures for fs commits within window
        When test_fs_commits_within_window executes the target flow
        Then the expected outcome for fs commits within window is confirmed.

    Boundaries:
        - Focus: fs commits within window
        - Fixtures/params: fs_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fs commits within window
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    before = datetime(2026, 5, 30, 14, 0, 0, tzinfo=UTC)
    # In-window (1h before), out-of-window (5h before).
    _touch(tmp_path / "recent.py", before - timedelta(hours=1))
    _touch(tmp_path / "old.py", before - timedelta(hours=5))
    (tmp_path / ".git").mkdir()  # must be pruned, not reported
    _touch(tmp_path / ".git" / "HEAD", before - timedelta(minutes=10))

    commits = fs_adapter.get_commits_before(str(tmp_path), before, window_hours=2, limit=10)
    names = {c.files_changed[0] for c in commits}
    assert "recent.py" in names
    assert "old.py" not in names
    assert all(not f.startswith(".git") for c in commits for f in c.files_changed)
    assert all(c.sha.startswith("fs:") for c in commits)
    assert all(c.author == "unknown" for c in commits)


def test_fs_commits_respects_limit(fs_adapter: FilesystemCodeAdapter, tmp_path: Path):
    """
    [Unit] code backends: verifies fs commits respects limit.

    Scenario:
        Given test inputs and fixtures for fs commits respects limit
        When test_fs_commits_respects_limit executes the target flow
        Then the expected outcome for fs commits respects limit is confirmed.

    Boundaries:
        - Focus: fs commits respects limit
        - Fixtures/params: fs_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fs commits respects limit
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    before = datetime(2026, 5, 30, 14, 0, 0, tzinfo=UTC)
    for i in range(5):
        _touch(tmp_path / f"f{i}.py", before - timedelta(minutes=10 * (i + 1)))
    commits = fs_adapter.get_commits_before(str(tmp_path), before, window_hours=2, limit=3)
    assert len(commits) == 3


def test_fs_file_diff_returns_contents(fs_adapter: FilesystemCodeAdapter, tmp_path: Path):
    """
    [Unit] code backends: verifies fs file diff returns contents.

    Scenario:
        Given test inputs and fixtures for fs file diff returns contents
        When test_fs_file_diff_returns_contents executes the target flow
        Then the expected outcome for fs file diff returns contents is confirmed.

    Boundaries:
        - Focus: fs file diff returns contents
        - Fixtures/params: fs_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fs file diff returns contents
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    (tmp_path / "a.py").write_text("line1\nline2\n", encoding="utf-8")
    diff = fs_adapter.get_file_diff(str(tmp_path), "a.py", "fs:whatever")
    assert "no VCS history" in diff
    assert "line1" in diff


def test_fs_file_diff_missing_returns_empty(fs_adapter: FilesystemCodeAdapter, tmp_path: Path):
    """
    [Unit] code backends: verifies fs file diff missing returns empty.

    Scenario:
        Given test inputs and fixtures for fs file diff missing returns empty
        When test_fs_file_diff_missing_returns_empty executes the target flow
        Then the expected outcome for fs file diff missing returns empty is confirmed.

    Boundaries:
        - Focus: fs file diff missing returns empty
        - Fixtures/params: fs_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fs file diff missing returns empty
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    assert fs_adapter.get_file_diff(str(tmp_path), "missing.py", "x") == ""


def test_fs_blame_line_range(fs_adapter: FilesystemCodeAdapter, tmp_path: Path):
    """
    [Unit] code backends: verifies fs blame line range.

    Scenario:
        Given test inputs and fixtures for fs blame line range
        When test_fs_blame_line_range executes the target flow
        Then the expected outcome for fs blame line range is confirmed.

    Boundaries:
        - Focus: fs blame line range
        - Fixtures/params: fs_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fs blame line range
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    (tmp_path / "a.py").write_text("l1\nl2\nl3\nl4\n", encoding="utf-8")
    records = fs_adapter.blame(str(tmp_path), "a.py", (2, 3))
    assert [r.line_number for r in records] == [2, 3]
    assert [r.content for r in records] == ["l2", "l3"]
    assert all(r.author == "unknown" for r in records)


def test_fs_path_traversal_blocked(fs_adapter: FilesystemCodeAdapter, tmp_path: Path):
    """
    [Unit] code backends: verifies fs path traversal blocked.

    Scenario:
        Given test inputs and fixtures for fs path traversal blocked
        When test_fs_path_traversal_blocked executes the target flow
        Then the expected outcome for fs path traversal blocked is confirmed.

    Boundaries:
        - Focus: fs path traversal blocked
        - Fixtures/params: fs_adapter, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fs path traversal blocked
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    with pytest.raises(ValueError, match="traversal"):
        fs_adapter.blame(str(tmp_path), "../../etc/passwd", (1, 1))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_disabled_returns_none():
    """
    [Unit] code backends: verifies factory disabled returns none.

    Scenario:
        Given test inputs and fixtures for factory disabled returns none
        When test_factory_disabled_returns_none executes the target flow
        Then the expected outcome for factory disabled returns none is confirmed.

    Boundaries:
        - Focus: factory disabled returns none
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory disabled returns none
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    assert create_code_backend(CodeBackendSettings(enabled=False)) is None


def test_factory_git():
    """
    [Unit] code backends: verifies factory git.

    Scenario:
        Given test inputs and fixtures for factory git
        When test_factory_git executes the target flow
        Then the expected outcome for factory git is confirmed.

    Boundaries:
        - Focus: factory git
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory git
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    backend = create_code_backend(CodeBackendSettings(enabled=True, provider="git"))
    assert isinstance(backend, GitCodeAdapter)


def test_factory_filesystem():
    """
    [Unit] code backends: verifies factory filesystem.

    Scenario:
        Given test inputs and fixtures for factory filesystem
        When test_factory_filesystem executes the target flow
        Then the expected outcome for factory filesystem is confirmed.

    Boundaries:
        - Focus: factory filesystem
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory filesystem
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    backend = create_code_backend(CodeBackendSettings(enabled=True, provider="filesystem"))
    assert isinstance(backend, FilesystemCodeAdapter)


def test_factory_unknown_provider_raises():
    """
    [Unit] code backends: verifies factory unknown provider raises.

    Scenario:
        Given test inputs and fixtures for factory unknown provider raises
        When test_factory_unknown_provider_raises executes the target flow
        Then the expected outcome for factory unknown provider raises is confirmed.

    Boundaries:
        - Focus: factory unknown provider raises
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory unknown provider raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by code backends
    """
    settings = CodeBackendSettings(enabled=True)
    object.__setattr__(settings, "provider", "svn")
    with pytest.raises(ValueError, match="Unknown code provider"):
        create_code_backend(settings)
