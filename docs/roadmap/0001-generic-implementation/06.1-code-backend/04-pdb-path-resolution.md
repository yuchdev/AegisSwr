# 04 – PDB path resolution

**Parent milestone:** 6.1 Code Backend – PDB Adapter
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 05

## Objective

Implement the logic that locates the `.pdb` file before `pdbstr.exe` is called.
The resolution has a defined priority order so that explicit configuration always
wins over heuristic discovery, and every failure mode raises `CodeBackendError`
rather than returning `None` (fail-fast so Stage 8 can degrade cleanly).

## Files

- **Modify** `src/aegis_swr/backends/code/_paths.py`
  (add `resolve_pdb_path`; keep `safe_repo_path` unchanged)

## Function: `resolve_pdb_path`

```python
def resolve_pdb_path(
    settings: CodeBackendSettings,
    repo_path: str,
) -> Path:
    """Locate the ``.pdb`` file for the PDB code adapter.

    Resolution order (first match wins):

    1. ``settings.pdb_path`` — explicit path; checked for existence.
    2. ``{repo_path}/*.pdb`` — non-recursive glob in the directory passed as
       *repo_path*; first match alphabetically wins.  Logs a ``WARNING`` when
       more than one ``.pdb`` is found (ambiguous; first is used).
    3. Each directory in ``settings.pdb_search_dirs`` — non-recursive glob;
       first match alphabetically across all dirs wins.

    :param settings: :class:`~aegis_swr.config.settings.CodeBackendSettings`
        providing ``pdb_path`` and ``pdb_search_dirs``.
    :param repo_path: Repository root passed to ``get_commits_before`` /
        ``get_file_diff`` / ``blame``.  Used as the first search location when
        ``settings.pdb_path`` is not set.
    :return: Absolute :class:`~pathlib.Path` to the resolved ``.pdb`` file.
    :raises CodeBackendError: No ``.pdb`` file found through any resolution
        step, or ``settings.pdb_path`` is set but the file does not exist.
    """
```

### Resolution step detail

**Step 1 — explicit `pdb_path`:**

```python
if settings.pdb_path:
    p = Path(settings.pdb_path).expanduser().resolve()
    if not p.is_file():
        raise CodeBackendError(
            f"PDB file not found at configured pdb_path: {p}"
        )
    return p
```

**Step 2 — `repo_path` directory glob:**

```python
base = Path(repo_path).expanduser().resolve()
if base.is_dir():
    matches = sorted(base.glob("*.pdb"))
    if len(matches) > 1:
        logger.warning(
            f"Multiple .pdb files in {base}; using {matches[0].name}. "
            "Set pdb_path explicitly to suppress this warning."
        )
    if matches:
        return matches[0]
```

**Step 3 — `pdb_search_dirs`:**

```python
for dir_str in settings.pdb_search_dirs:
    search_dir = Path(dir_str).expanduser().resolve()
    if not search_dir.is_dir():
        logger.debug(f"pdb_search_dirs entry is not a directory: {search_dir}")
        continue
    matches = sorted(search_dir.glob("*.pdb"))
    if matches:
        return matches[0]
```

**Fallthrough — nothing found:**

```python
raise CodeBackendError(
    f"No .pdb file found. Set pdb_path in config or place a .pdb in "
    f"repo_path ({repo_path!r}) or one of pdb_search_dirs "
    f"({settings.pdb_search_dirs!r})."
)
```

## Constraints

- The function is synchronous and performs filesystem operations with plain
  `pathlib` — no asyncio, no subprocess.
- Only the **immediate** directory is searched (non-recursive `glob("*.pdb")`),
  not a deep tree walk. Recursive search would be too slow and might surface
  stale symbol caches.
- `pdb_search_dirs` entries that do not exist as directories are skipped with a
  `DEBUG` log — not an error.
- The returned `Path` is always absolute (`.resolve()` applied).
- Imports must not create circular dependencies: `_paths.py` only imports from
  `pathlib`, `loguru`, and `aegis_swr.core.exceptions`.

## Tests

**Unit** (`tests/unit/test_pdb_path_resolution.py` — new file, or extend
`test_code_backends.py`):

- `test_explicit_pdb_path_used_when_set` — create a `.pdb` file in `tmp_path`;
  set `settings.pdb_path` to its path; assert `resolve_pdb_path` returns it.
- `test_explicit_pdb_path_raises_when_missing` — set `settings.pdb_path` to a
  non-existent path; assert `CodeBackendError` raised.
- `test_repo_path_glob_finds_pdb` — write a `foo.pdb` in `tmp_path`; leave
  `settings.pdb_path = None`; pass `repo_path=str(tmp_path)`;
  assert the result equals `tmp_path / "foo.pdb"`.
- `test_repo_path_glob_multiple_pdb_uses_first_alphabetical` — write `b.pdb` and
  `a.pdb`; assert `a.pdb` is returned (sorted first).
- `test_repo_path_glob_multiple_logs_warning` — same setup; assert a warning is
  logged (capture with `caplog` or mock `logger`).
- `test_repo_path_not_a_directory_falls_through_to_search_dirs` — `repo_path`
  points at a file (not dir); assert the function proceeds to step 3.
- `test_pdb_search_dirs_used_as_fallback` — `repo_path` has no `.pdb`;
  `pdb_search_dirs=[str(second_dir)]` where `second_dir` has `bar.pdb`; assert
  `bar.pdb` returned.
- `test_pdb_search_dirs_skips_missing_dir` — `pdb_search_dirs=["nonexistent"]`;
  assert no exception raised (step 3 skips it), falls through to `CodeBackendError`.
- `test_raises_when_nothing_found` — no `.pdb` anywhere; assert `CodeBackendError`
  with informative message.
- `test_explicit_pdb_path_takes_precedence_over_repo_glob` — both `pdb_path` and
  a `repo_path` glob match exist; assert `pdb_path` result returned.

## Success criteria

- [ ] `resolve_pdb_path` implemented in `_paths.py` with the three-step logic
      above.
- [ ] Explicit `pdb_path` check comes first and raises immediately on missing file.
- [ ] Multiple-PDB warning emitted and first alphabetical selected.
- [ ] `pdb_search_dirs` searched only when steps 1 and 2 find nothing.
- [ ] `CodeBackendError` raised with an informative message when nothing found.
- [ ] All 10 unit tests above pass with no real `.pdb` files required.
- [ ] `mypy --strict` clean.
