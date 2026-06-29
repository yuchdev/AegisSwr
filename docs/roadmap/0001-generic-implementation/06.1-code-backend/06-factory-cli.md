# 06 – Factory routing and CLI wiring

**Parent milestone:** 6.1 Code Backend – PDB Adapter
**State:** ⬜ Not started
**Depends on:** 01, 05
**Blocks:** 07

## Objective

Wire `PdbCodeAdapter` into the existing factory and CLI surface so that
`--code-provider pdb` works end-to-end. Three files need small, targeted changes:

1. **Factory** (`backends/code/__init__.py`) — add `"pdb"` routing and export.
2. **Config** (`cli/_config.py`) — add `pdb_path` flat field.
3. **CLI** (`cli/commands.py`) — add `--pdb-path` option; update `--code-provider`
   help text; wire `pdb_path` into `CodeBackendSettings`.

No new settings keys are introduced in `config.json`; the PDB fields are CLI-only
(operators pass `--pdb-path` rather than setting `backends.code.pdb_path` in JSON,
though the JSON path also works because `CodeBackendSettings` already reads it).

## Files

- **Modify** `src/aegis_swr/backends/code/__init__.py`
- **Modify** `src/aegis_swr/cli/_config.py`
- **Modify** `src/aegis_swr/cli/commands.py`
- **Modify** `config/config.example.json` (add `pdb_path` and `pdbstr_timeout_seconds` to `backends.code`)

## 1. Factory (`backends/code/__init__.py`)

### Import addition

```python
from aegis_swr.backends.code.pdb_adapter import PdbCodeAdapter
```

### `__all__` extension

```python
__all__ = [
    "FilesystemCodeAdapter",
    "GitCodeAdapter",
    "PdbCodeAdapter",          # new
    "create_code_backend",
]
```

### `create_code_backend` routing

```python
def create_code_backend(settings: CodeBackendSettings) -> Optional[CodeBackend]:
    """Return the configured ``CodeBackend`` or ``None`` when disabled"""
    if not settings.enabled:
        return None
    if settings.provider == "git":
        return GitCodeAdapter(settings)
    if settings.provider == "filesystem":
        return FilesystemCodeAdapter(settings)
    if settings.provider == "pdb":
        return PdbCodeAdapter(settings)          # new branch
    raise ValueError(
        f"Unknown code provider: {settings.provider!r}. "
        "Valid choices: git, filesystem, pdb."   # updated message
    )
```

**Platform behaviour** — `PdbCodeAdapter.__init__` raises `CodeBackendError` on
non-Windows. The factory does not add a platform guard itself; the constructor is
the authoritative check. This allows the factory to remain platform-agnostic.

## 2. Config model (`cli/_config.py`)

Add one field to `AnalyzeConfig`:

```python
pdb_path: Optional[str] = None   # --pdb-path; only relevant with --code-provider pdb
```

No `_FIELD_TO_PATH` mapping is needed unless the field should persist in
`config.json`. For now, treat it as a CLI-only option (like `repo`) that does
not round-trip through the JSON config file.

If persistence is desired, add to `_FIELD_TO_PATH`:

```python
"pdb_path": "backends.code.pdb_path",
```

> Decision: **do not persist by default** — the PDB path is typically an
> artifact-specific path that changes per analysis run. This matches the
> behaviour of `--repo` (not persisted).

## 3. CLI command (`cli/commands.py`)

### New `--pdb-path` option

Add immediately after the `--repo` option:

```python
pdb_path: Annotated[
    Optional[Path],
    typer.Option(
        "--pdb-path",
        help=(
            "Explicit path to the .pdb file for the 'pdb' code provider. "
            "When omitted, the adapter searches repo_path and pdb_search_dirs."
        ),
    ),
] = None,
```

### Update `--code-provider` help string

```python
code_provider: Annotated[
    str,
    typer.Option(
        "--code-provider",
        help="Code backend: none | git | filesystem | pdb.",   # add "| pdb"
    ),
] = "none",
```

### Wiring in `analyze` command body

In the section that builds `CodeBackendSettings` (after existing `--repo` wiring):

```python
# Existing: --repo implies enabled; default provider to git.
code_provider_opt = config.code_provider or "none"
if config.repo or code_provider_opt not in {"none", ""}:
    settings.backends.code.repo_path = config.repo
    settings.backends.code.provider = (
        "git" if code_provider_opt == "none" else code_provider_opt
    )
    settings.backends.code.enabled = code_provider_opt != "none"
    if code_provider_opt != "none":
        settings.backends.code.provider = code_provider_opt

# New: --pdb-path wires into pdb_path setting.
if config.pdb_path:
    settings.backends.code.pdb_path = str(config.pdb_path)
    # Imply --code-provider pdb if not already set.
    if not settings.backends.code.enabled:
        settings.backends.code.provider = "pdb"
        settings.backends.code.enabled = True
```

**`--pdb-path` implies `--code-provider pdb`** — providing a `--pdb-path`
without `--code-provider pdb` is a common user mistake; implying the provider
makes the CLI more ergonomic.

### `AnalyzeConfig.pdb_path` plumbing

In `commands.py`, add `pdb_path` to the kwargs dict passed to `AnalyzeConfig`:

```python
config = AnalyzeConfig(
    ...
    pdb_path=str(pdb_path) if pdb_path else None,
    ...
)
```

## `config.example.json` update

Extend the `backends.code` section with the new fields from subtask 01:

```jsonc
"backends": {
  "code": {
    "enabled": false,
    "provider": "pdb",
    "repo_path": "C:\\src\\my-service",
    "pdb_path": "C:\\symbols\\my-service.pdb",
    "window_hours": 2,
    "commit_limit": 10,
    "git_timeout_seconds": 30,
    "pdbstr_timeout_seconds": 15,
    "pdb_search_dirs": []
  }
}
```

## Tests

**Unit** (`tests/unit/test_code_backends.py` — extend existing):

- `test_factory_pdb_routes_to_pdb_adapter` — mock `_is_windows` to return `True`;
  assert `create_code_backend(CodeBackendSettings(enabled=True, provider="pdb"))`
  returns a `PdbCodeAdapter` instance.
- `test_factory_pdb_raises_on_non_windows` — mock `_is_windows` to return `False`;
  assert `CodeBackendError` raised.
- `test_factory_unknown_provider_message_includes_pdb` — `provider="svn"` raises
  `ValueError` whose message mentions `"pdb"` in the valid choices.

**Unit** (`tests/unit/test_cli.py` — extend existing):

- `test_pdb_path_flag_stored_in_config` — parse `--pdb-path /x/y.pdb`; assert
  `config.pdb_path == "/x/y.pdb"`.
- `test_pdb_path_implies_pdb_provider` — `--pdb-path /x/y.pdb` without
  `--code-provider`; assert `settings.backends.code.provider == "pdb"` and
  `settings.backends.code.enabled == True` in the assembled settings.
- `test_code_provider_help_mentions_pdb` — `aegis analyze --help` output contains
  `"pdb"` in the `--code-provider` help text.

**Integration** (`tests/integration/test_e2e_cli.py`):

- `test_analyze_pdb_provider_fails_open_on_non_windows` — run the full CLI with
  `--code-provider pdb` on the test host (which may not be Windows); assert the
  analysis completes (does not crash), the code history is empty, and a
  `WARNING` about `PdbCodeAdapter` being Windows-only is logged.

## Success criteria

- [ ] `create_code_backend` routes `"pdb"` to `PdbCodeAdapter`; `__all__` updated.
- [ ] `--pdb-path` option exists and sets `settings.backends.code.pdb_path`.
- [ ] `--pdb-path` alone implies `--code-provider pdb`.
- [ ] `--code-provider` help text mentions `pdb`.
- [ ] `config.example.json` shows the three new PDB fields.
- [ ] All unit and integration tests above pass.
- [ ] `mypy --strict` clean.
