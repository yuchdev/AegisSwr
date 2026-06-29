# 07 – Comprehensive test suite

**Parent milestone:** 6.1 Code Backend – PDB Adapter
**State:** ⬜ Not started
**Depends on:** 02, 03, 04, 05, 06
**Blocks:** nothing (final gate)

## Objective

Collect and extend all per-subtask test stubs into a runnable suite that gates
the milestone. Each subtask document (02–06) listed individual unit tests for
its own component; this document:

1. Consolidates the full list with canonical file paths.
2. Adds cross-cutting tests that span multiple components.
3. Adds platform-guard tests that verify non-Windows fail-open behaviour.
4. Adds factory-level routing and CLI integration tests.
5. Specifies the coverage target and how to measure it.

No new product code is written here — only tests.

## Files

| Test file | Covers |
|-----------|--------|
| `tests/unit/test_pdbstr_wrapper.py` | `PdbstrWrapper` (subtask 02) |
| `tests/unit/test_srcsrv_parser.py` | `SrcSrvParser` + dataclasses (subtask 03) |
| `tests/unit/test_pdb_path_resolution.py` | `resolve_pdb_path` (subtask 04) |
| `tests/unit/test_pdb_adapter.py` | `PdbCodeAdapter` + helpers (subtask 05) |
| `tests/unit/test_code_backends.py` | Factory routing — extend existing file |
| `tests/unit/test_cli.py` | CLI flags — extend existing file |
| `tests/unit/fixtures/sample_srcsrv_git.txt` | Fixture (subtask 03) |
| `tests/unit/fixtures/sample_srcsrv_tfvc.txt` | Fixture (subtask 03) |
| `tests/unit/fixtures/sample_srcsrv_empty.txt` | Fixture (subtask 03) |
| `tests/integration/test_e2e_cli.py` | End-to-end CLI — extend existing file |

---

## 1. `test_pdbstr_wrapper.py`

Patch targets:

```python
_RUN  = "aegis_swr.backends.code.pdbstr_wrapper.subprocess.run"
_IS_WIN = "aegis_swr.backends.code.pdbstr_wrapper._is_windows"
```

### Happy-path tests

- `test_read_srcsrv_returns_stdout_on_success`
  Mock: `subprocess.run` → `CompletedProcess(returncode=0, stdout="SRCSRV: ini\n...", stderr="")`.
  Assert: `wrapper.read_srcsrv(fake_pdb)` returns the fixture text verbatim.

- `test_read_srcsrv_empty_stdout_exit_zero_returns_empty`
  Mock: exit 0, stdout `""`.
  Assert: returns `""`.

- `test_read_srcsrv_nonzero_empty_stderr_returns_empty`
  Mock: exit 1, stdout `""`, stderr `""`.
  Assert: returns `""` (no-stream condition, not an error).

### Error-mapping tests

- `test_read_srcsrv_raises_on_nonzero_with_stderr`
  Mock: exit 1, stderr `"Error opening PDB"`.
  Assert: `CodeBackendError` with `"pdbstr.exe failed"` in message.

- `test_read_srcsrv_stderr_truncated_to_200_chars`
  Mock: exit 1, stderr `"x" * 400`.
  Assert: error message contains at most 200 chars of stderr excerpt.

- `test_read_srcsrv_raises_on_file_not_found`
  Mock: `subprocess.run` raises `FileNotFoundError`.
  Assert: `CodeBackendError` with `"not found"` (case-insensitive) in message.

- `test_read_srcsrv_raises_on_timeout`
  Mock: `subprocess.run` raises `subprocess.TimeoutExpired(cmd=[], timeout=15)`.
  Assert: `CodeBackendError` with `"timed out"` in message.

### Constructor guard tests

- `test_constructor_raises_on_non_windows`
  Mock `_is_windows` → `False`.
  Assert: `CodeBackendError` raised on `PdbstrWrapper(settings)`.

- `test_constructor_succeeds_on_windows`
  Mock `_is_windows` → `True`.
  Assert: no exception raised.

### Security tests

- `test_cmd_uses_list_form_no_shell`
  Capture the call kwargs passed to `subprocess.run`.
  Assert: `shell` keyword is `False` or absent.
  Assert: no element of `cmd` is a shell metacharacter string (`&`, `|`, `;`, `>`).

- `test_pdb_path_embedded_correctly_in_cmd`
  Pass `pdb_path = Path("/tmp/test.pdb")`.
  Assert: `cmd` contains `"-p:/tmp/test.pdb"` as a single element (not split on `:`).

---

## 2. `test_srcsrv_parser.py`

Fixture helper:

```python
import pathlib

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

def _load(name: str) -> str:
    return (FIXTURES / name).read_text()
```

### Git fixture tests

- `test_parse_git_verctrl` — `stream.verctrl == "git"`.
- `test_parse_git_repo_url` — `stream.repo_url == "https://github.com/acme/svc"`.
- `test_parse_git_entry_count` — `len(stream.entries) == 3`.
- `test_parse_git_unique_revisions_count` — `len(stream.unique_revisions()) == 2`.
- `test_parse_git_files_for_first_revision` — `stream.files_for_revision("abc123def456789012345678901234567890ab")` == two paths.
- `test_parse_git_files_for_second_revision` — `stream.files_for_revision("def789abc012345678901234567890abcdef12")` == one path.
- `test_parse_git_is_not_empty` — `stream.is_empty == False`.

### TFVC fixture tests

- `test_parse_tfvc_verctrl_preserved_case` — `stream.verctrl == "TFVC"` (case preserved from `VERCTRL=TFVC`).
- `test_parse_tfvc_repo_url` — `stream.repo_url == "https://dev.azure.com/acme/svc"`.
- `test_parse_tfvc_revision_is_changeset` — `stream.entries[0].revision == "42"`.
- `test_parse_tfvc_entry_count` — `len(stream.entries) == 2`.

### Empty fixture tests

- `test_parse_empty_is_empty` — `stream.is_empty == True`.
- `test_parse_empty_unique_revisions` — `stream.unique_revisions() == []`.
- `test_parse_empty_files_for_any_revision` — `stream.files_for_revision("any") == []`.

### Edge-case tests

- `test_parse_blank_text` — `SrcSrvParser.parse("")` returns stream with `verctrl=""`, `repo_url=None`, `entries=[]`.
- `test_parse_missing_ini_section_no_raise` — stream without `SRCSRV: ini` parses without raising; `verctrl == ""`.
- `test_parse_malformed_source_line_skipped` — insert a line without `*` in `source files`; surrounding valid lines are parsed; no exception raised.
- `test_split_sections_keys` — `SrcSrvParser._split_sections(git_text)` returns a dict with keys `"ini"`, `"variables"`, `"source files"`, `"end"`.
- `test_extract_repo_url_unknown_verctrl` — `_extract_repo_url("svn", {})` returns `None` (missing variable).
- `test_extract_repo_url_perforce` — `_extract_repo_url("perforce", {"P4PORT": "perforce:1666"})` returns `"perforce:1666"`.

---

## 3. `test_pdb_path_resolution.py`

All tests use `tmp_path` (pytest fixture) for filesystem isolation.

### Step 1 — explicit `pdb_path`

- `test_explicit_pdb_path_returned_when_exists`
  Create `tmp_path / "my.pdb"`. Set `settings.pdb_path = str(tmp_path / "my.pdb")`.
  Assert: `resolve_pdb_path(settings, str(tmp_path))` returns the same path.

- `test_explicit_pdb_path_raises_when_missing`
  Set `settings.pdb_path = str(tmp_path / "nonexistent.pdb")` (not created).
  Assert: `CodeBackendError` raised with `"pdb_path"` mentioned.

- `test_explicit_pdb_path_takes_precedence_over_repo_glob`
  Create `tmp_path / "repo.pdb"` and `other_dir / "explicit.pdb"`.
  Set `settings.pdb_path = str(other_dir / "explicit.pdb")`.
  Assert: `explicit.pdb` returned (not `repo.pdb`).

### Step 2 — repo_path glob

- `test_repo_path_glob_finds_single_pdb`
  Create `tmp_path / "foo.pdb"`. Leave `settings.pdb_path = None`.
  Assert: `resolve_pdb_path(settings, str(tmp_path))` returns `foo.pdb`.

- `test_repo_path_glob_returns_first_alphabetical_when_multiple`
  Create `tmp_path / "b.pdb"` and `tmp_path / "a.pdb"`.
  Assert: `a.pdb` returned.

- `test_repo_path_multiple_pdbs_emits_warning`
  Same as above. Capture loguru output (or monkeypatch `logger.warning`).
  Assert: warning contains `"Multiple"`.

- `test_repo_path_not_a_directory_skips_step2`
  Pass `repo_path = str(tmp_path / "some_file.txt")` (create as regular file).
  Set `settings.pdb_search_dirs = [str(tmp_path)]`; place `bar.pdb` in `tmp_path`.
  Assert: `bar.pdb` returned from step 3 (not a crash on step 2).

### Step 3 — `pdb_search_dirs`

- `test_pdb_search_dirs_fallback`
  `repo_path` has no `.pdb`. `pdb_search_dirs = [str(search_dir)]` where `search_dir / "bar.pdb"` exists.
  Assert: `bar.pdb` returned.

- `test_pdb_search_dirs_skips_nonexistent_dir`
  `pdb_search_dirs = ["nonexistent_path"]`.
  Assert: no exception from step 3; falls through to final `CodeBackendError`.

- `test_pdb_search_dirs_empty_list_falls_through`
  `pdb_search_dirs = []`, no PDB anywhere.
  Assert: `CodeBackendError` raised.

### Fallthrough

- `test_raises_when_nothing_found_error_message`
  All three steps find nothing.
  Assert: `CodeBackendError` message mentions `repo_path` and `pdb_search_dirs`.

---

## 4. `test_pdb_adapter.py`

Patch targets:

```python
_IS_WIN   = "aegis_swr.backends.code.pdb_adapter._is_windows"
_RUN      = "aegis_swr.backends.code.pdb_adapter.subprocess.run"
_PDBMTIME = "aegis_swr.backends.code.pdb_adapter._pdb_mtime"
_RESOLVE  = "aegis_swr.backends.code.pdb_adapter.resolve_pdb_path"
_WRAPPER  = "aegis_swr.backends.code.pdb_adapter.PdbstrWrapper"
```

All tests patch `_is_windows` → `True` unless testing the platform guard.

### Constructor guard

- `test_constructor_raises_on_non_windows`
  Patch `_is_windows` → `False`. Assert `CodeBackendError` raised.

- `test_constructor_succeeds_on_windows`
  Patch `_is_windows` → `True`. Assert no exception.

### `get_commits_before`

- `test_get_commits_before_git_stream_returns_records`
  Patch `_RESOLVE` → `Path("/fake.pdb")`.
  Patch `PdbstrWrapper.read_srcsrv` → git fixture text.
  Patch `_pdb_mtime` → fixed datetime.
  Assert: two `CommitRecord` objects returned (two unique revisions in git fixture).

- `test_get_commits_before_files_in_commit_record`
  Same setup. Assert: `records[0].files_changed` == two paths from `abc123...` revision.

- `test_get_commits_before_empty_stream_returns_empty`
  Patch `read_srcsrv` → `""`.
  Assert: returns `[]`.

- `test_get_commits_before_no_source_file_entries_returns_empty`
  Patch `read_srcsrv` → empty-fixture text (has ini/variables, no source entries).
  Assert: returns `[]`.

- `test_get_commits_before_ignores_time_window_params`
  Pass `before=datetime.now(), window_hours=99, limit=1`.
  Patch → git fixture. Assert: 2 records returned (limit is ignored for PDB).

### `get_file_diff`

- `test_get_file_diff_git_verctrl_returns_git_show`
  Patch `read_srcsrv` → git fixture. Patch `subprocess.run` → stdout `"diff text"`.
  Assert: returns `"diff text"`.

- `test_get_file_diff_tfvc_verctrl_returns_empty`
  Patch `read_srcsrv` → TFVC fixture text.
  Assert: returns `""` (no exception).

- `test_get_file_diff_empty_stream_returns_empty`
  Patch `read_srcsrv` → `""`.
  Assert: returns `""`.

- `test_get_file_diff_git_show_nonzero_returns_empty`
  Patch `subprocess.run` → exit 1.
  Assert: returns `""` (fail open).

- `test_get_file_diff_git_show_timeout_returns_empty`
  Patch `subprocess.run` → raises `TimeoutExpired`.
  Assert: returns `""`.

- `test_get_file_diff_git_show_not_found_returns_empty`
  Patch `subprocess.run` → raises `FileNotFoundError`.
  Assert: returns `""`.

### `blame`

- `test_blame_git_verctrl_returns_blame_records`
  Patch `read_srcsrv` → git fixture. Patch `subprocess.run` → porcelain blame text
  for lines 1-3. Assert: list of `BlameRecord` objects with correct SHA and author.

- `test_blame_tfvc_verctrl_returns_empty`
  Patch `read_srcsrv` → TFVC fixture.
  Assert: returns `[]`.

- `test_blame_file_not_in_stream_uses_first_revision`
  Patch fixture (git), pass `file_path = "totally_unknown.cpp"`.
  Assert: `git blame` is called with the first revision from `unique_revisions()`.

- `test_blame_empty_stream_returns_empty`
  Patch → `""`. Assert: `[]`.

### `_find_revision_for_file`

- `test_find_revision_exact_filename_match`
  Create stream with entry `C:\src\svc\db_writer.cpp`, revision `abc123`.
  Call `_find_revision_for_file(stream, "db_writer.cpp")`.
  Assert: returns `"abc123"`.

- `test_find_revision_posix_path_match`
  Entry path `C:\src\svc\pool.cpp`, query `"src/svc/pool.cpp"`.
  Assert: correct revision returned.

- `test_find_revision_fallback_to_first_when_not_found`
  Call with `file_path = "unknown.cpp"`.
  Assert: first revision in stream returned.

- `test_find_revision_empty_stream_returns_none`
  Stream with no entries. Assert: returns `None`.

---

## 5. Factory routing tests (`tests/unit/test_code_backends.py` — extend existing)

- `test_factory_pdb_routes_to_pdb_adapter`
  Patch `aegis_swr.backends.code.pdbstr_wrapper._is_windows` → `True`.
  Assert: `create_code_backend(CodeBackendSettings(enabled=True, provider="pdb"))`
  returns instance of `PdbCodeAdapter`.

- `test_factory_pdb_raises_on_non_windows`
  Patch `_is_windows` → `False`.
  Assert: `CodeBackendError` when `create_code_backend(…provider="pdb")` called.

- `test_factory_unknown_provider_message_includes_pdb`
  `provider = "svn"`. Assert: `ValueError` whose message contains `"pdb"`.

- `test_factory_pdb_adapter_in_all`
  Assert `"PdbCodeAdapter"` is in `aegis_swr.backends.code.__all__`.

---

## 6. CLI tests (`tests/unit/test_cli.py` — extend existing)

- `test_pdb_path_option_accepted`
  Use Typer test runner. Pass `--pdb-path /x/y.pdb`. Assert no error.

- `test_pdb_path_stored_in_analyze_config`
  Assert `config.pdb_path == "/x/y.pdb"` after parsing.

- `test_pdb_path_implies_pdb_provider`
  Pass `--pdb-path /x/y.pdb` (no `--code-provider`).
  Assert assembled `settings.backends.code.provider == "pdb"` and
  `settings.backends.code.enabled == True`.

- `test_pdb_path_does_not_override_explicit_provider`
  Pass `--pdb-path /x/y.pdb --code-provider filesystem`.
  Assert `settings.backends.code.provider == "filesystem"` (explicit wins).

- `test_code_provider_help_text_mentions_pdb`
  Run `aegis analyze --help` via Typer test runner.
  Assert output contains `"pdb"` in `--code-provider` help.

---

## 7. Cross-cutting integration test (`tests/integration/test_e2e_cli.py` — extend existing)

- `test_analyze_pdb_provider_non_windows_fails_open`
  Run the full CLI entry point with `--code-provider pdb --dump <test.dmp>` on
  the test host (non-Windows expected in CI).
  Assert:
  - Process exits with code 0 (graceful degradation, not crash).
  - Output or log contains a warning about the PDB adapter being Windows-only.
  - RCA report is still produced (code history section is empty).

  This test is marked `@pytest.mark.integration` and skipped unless
  `AEGIS_INTEGRATION_TESTS=1` is set. It exercises the full
  Factory → DataAdapter → Stage 8 path on a platform where the PDB adapter
  cannot run.

---

## Coverage target

Run with:

```bash
poetry run pytest tests/unit/ tests/integration/ \
  -q \
  --cov=aegis_swr.backends.code \
  --cov=aegis_swr.cli.config \
  --cov=aegis_swr.cli.commands \
  --cov-report=term-missing
```

| Module | Target |
|--------|--------|
| `backends/code/pdbstr_wrapper.py` | ≥ 90% |
| `backends/code/srcsrv_parser.py` | ≥ 95% |
| `backends/code/_paths.py` (new function) | ≥ 90% |
| `backends/code/pdb_adapter.py` | ≥ 85% |
| `backends/code/__init__.py` (factory changes) | 100% |
| `cli/_config.py` (new field) | 100% |
| `cli/commands.py` (new option) | ≥ 80% |

The lower target for `pdb_adapter.py` reflects the `VERCTRL=git` subprocess paths
that require a real git binary — these are covered by the integration test, not
the unit tests.

---

## Running the test suite

```bash
# Unit tests only (CI-fast, no real subprocess)
poetry run pytest tests/unit/ -q

# All tests including integration
AEGIS_INTEGRATION_TESTS=1 poetry run pytest tests/ -q

# Just the new PDB-related tests
poetry run pytest tests/unit/test_pdbstr_wrapper.py \
                  tests/unit/test_srcsrv_parser.py \
                  tests/unit/test_pdb_path_resolution.py \
                  tests/unit/test_pdb_adapter.py \
                  -v
```

---

## Success criteria

- [ ] All unit test files listed above exist and pass: zero failures, zero errors.
- [ ] No existing test is weakened, `xfail`'d, or deleted to achieve a green run.
- [ ] `backends/code/pdbstr_wrapper.py` ≥ 90% coverage.
- [ ] `backends/code/srcsrv_parser.py` ≥ 95% coverage.
- [ ] `backends/code/_paths.py` new `resolve_pdb_path` function ≥ 90% coverage.
- [ ] `backends/code/pdb_adapter.py` ≥ 85% coverage.
- [ ] `backends/code/__init__.py` factory changes 100% covered.
- [ ] CLI option tests all pass.
- [ ] Integration test `test_analyze_pdb_provider_non_windows_fails_open` passes
      when `AEGIS_INTEGRATION_TESTS=1`.
- [ ] `mypy --strict` passes on all new test files.
- [ ] `ruff check` passes on all new test files.
