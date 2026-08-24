# 05 – `PdbCodeAdapter` full implementation

**Parent milestone:** 6.1 Code Backend – PDB Adapter
**State:** ⬜ Not started
**Depends on:** 01, 02, 03, 04
**Blocks:** 06, 07

## Objective

Implement `PdbCodeAdapter`, the `CodeBackend` subclass that ties together the
`PdbstrWrapper` (subtask 02), `SrcSrvParser` (subtask 03), and
`resolve_pdb_path` (subtask 04) to deliver all three `CodeBackend` methods.

The adapter is Windows-only. On all other platforms, the constructor raises
`CodeBackendError` immediately (the factory in subtask 06 never routes to it
on non-Windows, but the constructor guard is a defence-in-depth measure).

## Files

- **Create** `src/aegis_swr/backends/code/pdb_adapter.py`

## Class: `PdbCodeAdapter(CodeBackend)`

```python
class PdbCodeAdapter(CodeBackend):
    """Windows PDB Source Server code backend.

    Reads build provenance from the SrcSrv stream embedded in a ``.pdb``
    (Program Database) file.  This yields the **exact** VCS revision compiled
    into the crashing binary - no time-window guessing.

    Supported VCS types (via ``VERCTRL`` in the SrcSrv stream):

    - ``git`` - full diff and blame via ``git show`` / ``git blame``
    - ``tfvc`` - ``get_commits_before`` only; diff and blame return empty
    - unknown - ``get_commits_before`` only; diff and blame return empty

    **Windows-only.** Constructor raises
    :class:`~aegis_swr.core.exceptions.CodeBackendError` on non-Windows.

    :param settings: :class:`~aegis_swr.config.settings.CodeBackendSettings`.
    """

    SUPPORTED_PLATFORMS: ClassVar[list[str]] = ["Windows"]

    def __init__(self, settings: CodeBackendSettings):
        if not _is_windows():
            raise CodeBackendError(
                "PdbCodeAdapter is Windows-only. "
                "Use provider 'git' or 'filesystem' on this platform."
            )
        self._settings = settings
        self._wrapper = PdbstrWrapper(settings)
```

### `get_commits_before`

```python
def get_commits_before(
    self,
    repo_path: str,
    before: datetime,
    window_hours: int = 2,
    limit: int = 10,
) -> list[CommitRecord]:
    """Return one CommitRecord per unique VCS revision in the SrcSrv stream.

    *before* and *window_hours* are **ignored** - the SrcSrv stream records
    the exact revision built into the binary, making time-window heuristics
    unnecessary.  *limit* is also ignored (the number of unique revisions in
    a PDB is typically 1–3).

    :param repo_path: Used only for PDB path resolution (step 2 in subtask 04).
    :return: One :class:`CommitRecord` per unique revision SHA; empty list if
        the SrcSrv stream is absent, empty, or ``pdbstr.exe`` reports an error.
    :raises CodeBackendError: PDB file not found or ``pdbstr.exe`` reports a
        genuine error (not a missing-stream condition).
    """
    pdb_path = resolve_pdb_path(self._settings, repo_path)
    stream_text = self._wrapper.read_srcsrv(pdb_path)
    if not stream_text.strip():
        logger.info(
            f"PdbCodeAdapter: no SrcSrv stream in {pdb_path.name}; "
            "returning empty code history."
        )
        return []
    stream = SrcSrvParser.parse(stream_text)
    if stream.is_empty:
        return []
    pdb_mtime = _pdb_mtime(pdb_path)
    records: list[CommitRecord] = []
    for rev in stream.unique_revisions():
        records.append(
            CommitRecord(
                sha=rev,
                message="SrcSrv build revision",
                author="PdbSourceServer",
                timestamp=pdb_mtime,
                files_changed=stream.files_for_revision(rev),
            )
        )
    return records
```

### `get_file_diff`

```python
def get_file_diff(
    self,
    repo_path: str,
    file_path: str,
    commit_sha: str,
) -> str:
    """Return ``git show {commit_sha}:{file_path}`` for VERCTRL=git.

    For TFVC and unknown VCS types returns ``""`` (not an error).

    :param repo_path: Git working tree root used for ``git show``.
    :param file_path: Repo-relative POSIX path (Windows paths from the SrcSrv
        stream are normalised before being passed here).
    :param commit_sha: Exact revision SHA from the SrcSrv stream.
    """
    pdb_path = resolve_pdb_path(self._settings, repo_path)
    stream_text = self._wrapper.read_srcsrv(pdb_path)
    if not stream_text:
        return ""
    stream = SrcSrvParser.parse(stream_text)
    return self._dispatch_diff(repo_path, file_path, commit_sha, stream.verctrl)
```

### `blame`

```python
def blame(
    self,
    repo_path: str,
    file_path: str,
    line_range: tuple[int, int],
) -> list[BlameRecord]:
    """Return per-line blame for *file_path* at the SrcSrv revision.

    Looks up the revision for *file_path* in the SrcSrv stream (after
    normalising the Windows path from the stream to POSIX for comparison).
    Falls back to the first unique revision if *file_path* is not found
    in the stream entries.  Returns ``[]`` for TFVC and unknown VCS types.

    :param repo_path: Git working tree root.
    :param file_path: Repo-relative POSIX path.
    :param line_range: ``(start_line, end_line)`` inclusive, 1-based.
    """
    pdb_path = resolve_pdb_path(self._settings, repo_path)
    stream_text = self._wrapper.read_srcsrv(pdb_path)
    if not stream_text:
        return []
    stream = SrcSrvParser.parse(stream_text)
    rev = self._find_revision_for_file(stream, file_path)
    if rev is None:
        return []
    return self._dispatch_blame(repo_path, file_path, line_range, rev, stream.verctrl)
```

### Private helpers

#### `_dispatch_diff` - VERCTRL routing for diffs

```python
def _dispatch_diff(
    self,
    repo_path: str,
    file_path: str,
    commit_sha: str,
    verctrl: str,
) -> str:
    if verctrl.lower() == "git":
        return self._git_show(repo_path, file_path, commit_sha)
    logger.info(
        f"PdbCodeAdapter.get_file_diff: unsupported VERCTRL={verctrl!r}; "
        "returning empty diff."
    )
    return ""
```

#### `_dispatch_blame` - VERCTRL routing for blame

```python
def _dispatch_blame(
    self,
    repo_path: str,
    file_path: str,
    line_range: tuple[int, int],
    commit_sha: str,
    verctrl: str,
) -> list[BlameRecord]:
    if verctrl.lower() == "git":
        return self._git_blame(repo_path, file_path, line_range, commit_sha)
    logger.info(
        f"PdbCodeAdapter.blame: unsupported VERCTRL={verctrl!r}; returning []."
    )
    return []
```

#### `_git_show` - `git show {sha}:{file_path}`

```python
def _git_show(self, repo_path: str, file_path: str, sha: str) -> str:
    """Run ``git show {sha}:{file_path}`` and return the file content.

    Returns ``""`` on any git error (unknown SHA, file not in tree, etc.).
    """
    try:
        proc = subprocess.run(  # noqa: S603
            ["git", "show", f"{sha}:{file_path}"],
            cwd=str(Path(repo_path).expanduser()),
            capture_output=True,
            text=True,
            timeout=self._settings.git_timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout if proc.returncode == 0 else ""
```

#### `_git_blame` - `git blame -L ... {sha} -- {file_path}`

```python
def _git_blame(
    self,
    repo_path: str,
    file_path: str,
    line_range: tuple[int, int],
    sha: str,
) -> list[BlameRecord]:
    """Run ``git blame --line-porcelain`` at an exact revision and parse output.

    Returns ``[]`` on any git failure (fail open).
    """
    start, end = line_range
    try:
        proc = subprocess.run(  # noqa: S603
            ["git", "blame", "-L", f"{start},{end}", "--line-porcelain", sha,
             "--", file_path],
            cwd=str(Path(repo_path).expanduser()),
            capture_output=True,
            text=True,
            timeout=self._settings.git_timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    from aegis_swr.backends.code.git_adapter import _parse_blame_porcelain
    return _parse_blame_porcelain(proc.stdout, start)
```

#### `_find_revision_for_file`

```python
def _find_revision_for_file(
    self, stream: SrcSrvStream, file_path: str
) -> Optional[str]:
    """Find the revision for *file_path* in the SrcSrv stream.

    Compares the POSIX-normalised form of the stream's Windows paths against
    *file_path* (which is already POSIX).  Falls back to the first unique
    revision if no entry matches.
    """
    posix_path = file_path.replace("\\", "/").lower()
    for entry in stream.entries:
        entry_posix = entry.source_file.replace("\\", "/").lower()
        if entry_posix.endswith(posix_path) or posix_path.endswith(
            entry_posix.split("/")[-1]
        ):
            return entry.revision
    revisions = stream.unique_revisions()
    return revisions[0] if revisions else None
```

#### `_pdb_mtime` - PDB file modification time

```python
def _pdb_mtime(pdb_path: Path) -> datetime:
    """Return the PDB file's mtime as a UTC-aware datetime."""
    from datetime import timezone
    try:
        return datetime.fromtimestamp(pdb_path.stat().st_mtime, tz=UTC)
    except OSError:
        return datetime.fromtimestamp(0, tz=UTC)
```

Module-level function (not a method) so it can be mocked in tests.

### Windows platform check re-use

Import `_is_windows` from `pdbstr_wrapper.py` rather than duplicating it:

```python
from aegis_swr.backends.code.pdbstr_wrapper import _is_windows
```

## Constraints

- `_git_show` and `_git_blame` use list-form argv (no `shell=True`).
- Both fail open (`return ""` / `return []`) on `FileNotFoundError` and
  `TimeoutExpired` - these are not `CodeBackendError` because git availability
  is not guaranteed in a symbols-only environment.
- `_parse_blame_porcelain` is imported from `git_adapter` to avoid duplication
  (it is a module-level function, already unit-tested).
- Windows paths from SrcSrv entries contain backslashes; `_find_revision_for_file`
  normalises both sides to lowercase POSIX before comparing.
- `SUPPORTED_PLATFORMS` uses `ClassVar[list[str]]` to keep the class-level contract explicit.

## Tests

See subtask 07 for the comprehensive test suite. Per-method smoke tests are
included in that document.

## Success criteria

- [ ] `PdbCodeAdapter` exists in `pdb_adapter.py` with full docstrings.
- [ ] `get_commits_before` returns one `CommitRecord` per unique SrcSrv revision.
- [ ] `get_file_diff` returns `git show` output for `VERCTRL=git`; `""` for others.
- [ ] `blame` returns per-line blame for `VERCTRL=git`; `[]` for others.
- [ ] Constructor raises `CodeBackendError` on non-Windows.
- [ ] Both git helpers fail open (no exception propagation).
- [ ] `ruff check src/ tests/` - clean.
