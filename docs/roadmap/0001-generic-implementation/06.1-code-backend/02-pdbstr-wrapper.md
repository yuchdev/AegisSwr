# 02 – `pdbstr.exe` subprocess wrapper

**Parent milestone:** 6.1 Code Backend – PDB Adapter
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 05

## Objective

Wrap the `pdbstr.exe` Windows tool in an async-safe, type-annotated Python class
that reads the SrcSrv stream from a `.pdb` file and maps all failure modes to
`CodeBackendError`. This is the I/O boundary between Python and the Windows
Debugging Tools binary - every error path terminates here; nothing raw escapes.

`pdbstr.exe` is part of **Debugging Tools for Windows** (installed alongside
`cdb.exe`). Its relevant invocation is:

```
pdbstr.exe -r -p:{pdb_file_path} -s:srcsrv
```

- Prints the SrcSrv stream text to **stdout** if the stream is present.
- Exits **0** with empty stdout when the PDB exists but has no SrcSrv stream.
- Exits **non-zero** with an error on stderr when the PDB file cannot be opened.
- Raises `FileNotFoundError` when `pdbstr.exe` is not on PATH.

## Files

- **Create** `src/aegis_swr/backends/code/pdbstr_wrapper.py`

## Class: `PdbstrWrapper`

```python
class PdbstrWrapper:
    """Thin wrapper around ``pdbstr.exe`` for reading the SrcSrv stream.

    Executes ``pdbstr.exe -r -p:{pdb_path} -s:srcsrv`` in a subprocess and
    returns the raw stream text.  All failure modes map to
    :class:`~aegis_swr.core.exceptions.CodeBackendError`.

    This class is Windows-only.  The constructor raises ``CodeBackendError``
    on any non-Windows platform so the factory never instantiates it there.

    :param settings: :class:`~aegis_swr.config.settings.CodeBackendSettings`
        providing ``pdbstr_timeout_seconds``.
    """

    def __init__(self, settings: CodeBackendSettings):
        if not _is_windows():
            raise CodeBackendError(
                "PdbCodeAdapter (and PdbstrWrapper) are Windows-only. "
                "Use provider 'git' or 'filesystem' on this platform."
            )
        self._timeout = settings.pdbstr_timeout_seconds

    def read_srcsrv(self, pdb_path: Path) -> str:
        """Read the SrcSrv stream from *pdb_path*.

        Returns the raw stream text on success, or an empty string when the
        PDB has no SrcSrv stream.

        :param pdb_path: Resolved, existing path to the ``.pdb`` file.
        :return: Raw SrcSrv stream text, or ``""`` if the stream is absent.
        :raises CodeBackendError: pdbstr.exe not found on PATH, timed out,
            or reported an error opening the PDB file.
        """
```

### Implementation notes

**Command construction** (list-form, never `shell=True`):

```python
cmd = ["pdbstr.exe", "-r", f"-p:{pdb_path}", "-s:srcsrv"]
```

**Empty-stream detection** - distinguish "no SrcSrv stream" from "real error":

```python
proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout, check=False)
if proc.returncode != 0:
    if not proc.stdout.strip() and proc.stderr.strip():
        # Non-empty stderr with empty stdout → real error (bad PDB path, etc.)
        raise CodeBackendError(
            f"pdbstr.exe failed (exit {proc.returncode}): {proc.stderr.strip()[:200]}"
        )
    # Non-zero exit with empty stderr and stdout → no SrcSrv stream present.
    return ""
return proc.stdout
```

**Error mapping table**:

| Condition | Outcome |
|-----------|---------|
| `FileNotFoundError` (pdbstr not on PATH) | `CodeBackendError("pdbstr.exe not found on PATH…")` |
| `subprocess.TimeoutExpired` | `CodeBackendError("pdbstr.exe timed out after {n}s")` |
| Non-zero exit + non-empty stderr | `CodeBackendError` with first 200 chars of stderr |
| Non-zero exit + empty stderr + empty stdout | `return ""` (no stream) |
| Exit 0 + empty stdout | `return ""` (no stream) |
| Exit 0 + non-empty stdout | `return proc.stdout` |

### `_is_windows()` helper

```python
def _is_windows() -> bool:
    import sys
    return sys.platform == "win32"
```

Defined at module level so it can be patched in tests without touching `sys`.

## Constraints

- List-form argv - the `-p:{pdb_path}` argument is a **single string element**
  in the list (that is how `pdbstr.exe` parses it; do not split on `:`).
- `pdb_path` must be an absolute `Path` object passed in from subtask 04's
  resolver; this class does not do path resolution.
- stderr excerpt in `CodeBackendError` is truncated to 200 characters so
  Windows error messages (which can be lengthy) do not flood log output.
- `pdbstr.exe` stdout may use `\r\n` line endings on Windows; `text=True`
  in `subprocess.run` normalises these to `\n` automatically.
- No `asyncio.to_thread` wrapping here - the wrapper is synchronous. The
  `PdbCodeAdapter` methods calling it are also synchronous (matching the
  `CodeBackend` ABC contract).

## Tests

**Unit** (`tests/unit/test_pdbstr_wrapper.py` - new file, or extend `test_code_backends.py`):

```python
_WRAPPER_RUN = "aegis_swr.backends.code.pdbstr_wrapper.subprocess.run"
_WRAPPER_IS_WIN = "aegis_swr.backends.code.pdbstr_wrapper._is_windows"
```

- `test_read_srcsrv_returns_stdout_on_success` - mock `subprocess.run` returning
  exit 0 with fixture SrcSrv text in stdout; assert the text is returned verbatim.
- `test_read_srcsrv_returns_empty_when_no_stream_exit_zero` - mock exit 0 + empty
  stdout; assert `""` returned.
- `test_read_srcsrv_returns_empty_when_nonzero_empty_stderr` - mock non-zero exit
  + empty stdout + empty stderr; assert `""` returned (no stream, not an error).
- `test_read_srcsrv_raises_on_nonzero_with_stderr` - mock non-zero exit + non-empty
  stderr; assert `CodeBackendError` raised.
- `test_read_srcsrv_raises_on_file_not_found` - mock `subprocess.run` to raise
  `FileNotFoundError`; assert `CodeBackendError` with "not found" in message.
- `test_read_srcsrv_raises_on_timeout` - mock `subprocess.run` to raise
  `subprocess.TimeoutExpired`; assert `CodeBackendError`.
- `test_constructor_raises_on_non_windows` - mock `_is_windows` returning `False`;
  assert `CodeBackendError` raised in constructor.
- `test_constructor_succeeds_on_windows` - mock `_is_windows` returning `True`;
  assert no exception.
- `test_cmd_uses_list_form` - assert the `cmd` list passed to `subprocess.run`
  never contains a shell metacharacter (no `&`, `|`, `;`, `>`, etc.) and
  `shell=False`.

## Success criteria

- [ ] `PdbstrWrapper.read_srcsrv` returns stream text on success.
- [ ] Returns `""` for both "no SrcSrv stream" conditions (empty stdout on exit 0
      and non-zero with empty stderr).
- [ ] Maps every error condition to `CodeBackendError` per the error table.
- [ ] Constructor raises `CodeBackendError` on non-Windows.
- [ ] `subprocess.run` is always called with list-form argv and `shell=False`.
- [ ] stderr truncated to 200 chars in error messages.
- [ ] All unit tests above pass with zero real subprocess calls.
- [ ] `replace_optional.py --check` clean.
