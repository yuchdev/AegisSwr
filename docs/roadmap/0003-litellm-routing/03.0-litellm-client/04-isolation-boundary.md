# 04 - Isolation boundary enforcement

**Parent task:** 03.0 LiteLLM Client
**State:** ⬜ Not started
**Depends on:** 01, 02, 03
**Blocks:** -

## Objective

Verify and enforce that `import litellm` appears in **exactly one file** in
the `aegis/` package: `aegis/router/client.py`. This is a non-negotiable
architectural invariant (contract C2 in `plan.md`). Enforcement has two layers:
a pytest test that fails the unit suite on drift, and a CI lint step that
runs the check independently.

## pytest test (lives in `tests/router/test_client.py`)

```python
def test_litellm_is_only_imported_in_client() -> None:
    """Assert 'import litellm' appears in client.py and nowhere else under aegis/."""
    import pathlib

    violations: list[str] = []
    for py in pathlib.Path("aegis").rglob("*.py"):
        # Skip the one legitimate file
        if py.parts == ("aegis", "router", "client.py"):
            continue
        if "litellm" in py.read_text(encoding="utf-8"):
            violations.append(str(py))

    assert violations == [], (
        f"litellm reference found outside aegis/router/client.py: {violations}"
    )
```

## CI lint step

Add to `.github/workflows/ci.yml` (or equivalent):

```yaml
- name: "Lint: litellm isolation (must appear only in router/client.py)"
  run: |
    count=$(grep -rl "litellm" aegis/ | grep -v "aegis/router/client.py" | wc -l)
    if [ "$count" -gt 0 ]; then
      echo "ERROR: litellm imported outside aegis/router/client.py:"
      grep -rl "litellm" aegis/ | grep -v "aegis/router/client.py"
      exit 1
    fi
```

## Why two layers?

The pytest test catches drift in development (Stop hook runs the unit suite).
The CI lint step provides a named, visible job in the PR checks so reviewers
see it as an explicit gate - making the architectural rule concrete.

## Constraints

- The check must scan `*.py` files under `aegis/` only (not `tests/`, which
  legitimately imports `litellm` in fixtures).
- Comment references to `litellm` in docstrings are acceptable - the check
  looks for `import litellm` or `from litellm`, not bare mentions.
  Adjust the grep pattern accordingly.

## Success criteria

- [ ] `test_litellm_is_only_imported_in_client` passes on the initial
      implementation (no violations).
- [ ] CI lint step added with the name `"Lint: litellm isolation"`.
- [ ] Test explicitly skips `aegis/router/client.py` in its scan.
- [ ] Verified that adding `import litellm` to any other `aegis/` file causes
      both the test and the CI step to fail.
