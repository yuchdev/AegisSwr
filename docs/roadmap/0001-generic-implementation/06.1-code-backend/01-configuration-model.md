# 01 – Configuration model extension (`CodeBackendSettings`)

**Parent milestone:** 6.1 Code Backend – PDB Adapter
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 05, 06

## Objective

Extend `CodeBackendSettings` with the PDB-specific fields required by
`PdbCodeAdapter` and update the `provider` validator to accept `"pdb"`.
No implementation logic in this subtask — purely the settings model.

## Files

- **Modify** `src/aegis_swr/config/settings.py`
- **Modify** `config/config.example.json` (add `backends.code` expanded block)

## Changes to `CodeBackendSettings`

### New fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `pdb_path` | `Optional[str]` | `None` | Explicit path to the `.pdb` file. When set, all path-resolution lookups are skipped. Treated as a user-supplied file path — checked for existence at use time, not at construction. |
| `pdbstr_timeout_seconds` | `int` | `15` | Timeout passed to `subprocess.run` when calling `pdbstr.exe`. Same pattern as `git_timeout_seconds`. |
| `pdb_search_dirs` | `list[str]` | `[]` | Additional directories to search for a `.pdb` file when neither `pdb_path` nor an adjacent dump-path PDB is found. Each entry is treated as an absolute directory path; searched in order, first match wins. |

### Provider validator update

```python
@field_validator("provider")
@classmethod
def validate_provider(cls, v: str) -> str:
    allowed = {"git", "filesystem", "pdb"}   # add "pdb"
    if v not in allowed:
        raise ValueError(f"code provider must be one of {allowed}")
    return v
```

### Updated full field listing (for docstring refresh)

```
enabled: bool = False
provider: str = "git"          # git | filesystem | pdb
repo_path: Optional[str] = None
pdb_path: Optional[str] = None         # NEW
window_hours: int = 2
commit_limit: int = 10
git_timeout_seconds: int = 30
pdbstr_timeout_seconds: int = 15       # NEW
pdb_search_dirs: list[str] = []        # NEW
```

### `config.example.json` block

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

## Constraints

- All new optional fields use `Optional[T]`; `list[str]` fields use
  `Field(default_factory=list)`.
- `pdb_path` is **not** a secret field (`_SECRET_KEYS` unchanged) — it is a
  file path, not a credential.
- Env overrides: `AEGIS__backends__code__pdb_path`, etc., follow the existing
  `AEGIS__` prefix + `__` delimiter pattern automatically.
- The docstring on `CodeBackendSettings` must be updated to mention the PDB
  provider and its three new fields.

## Tests

**Unit** (`tests/unit/test_settings.py`):

- `test_code_backend_pdb_provider_accepted` — `CodeBackendSettings(provider="pdb")`
  constructs without error.
- `test_code_backend_pdb_defaults` — `pdb_path` is `None`, `pdbstr_timeout_seconds`
  is `15`, `pdb_search_dirs` is `[]`.
- `test_code_backend_provider_validator_still_rejects_unknown` — `provider="svn"`
  still raises `ValidationError`.
- `test_code_backend_env_override_pdb_path` —
  `AEGIS__backends__code__pdb_path=C:\\x.pdb` overrides the default.

## Success criteria

- [ ] `CodeBackendSettings` has `pdb_path`, `pdbstr_timeout_seconds`,
      `pdb_search_dirs` with the documented types and defaults.
- [ ] `provider` validator accepts `"pdb"`.
- [ ] `config.example.json` `backends.code` block includes the three new fields.
- [ ] All four unit tests above pass.
- [ ] `mypy --strict` clean.
