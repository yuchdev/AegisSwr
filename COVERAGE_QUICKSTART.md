# Coverage Quick Start

This project requires **85% test coverage** on all code. This is enforced automatically when running tests.

## Running Tests with Coverage

### Main Project

```powershell
# Install dev dependencies (one-time)
pip install -e .[dev]

# Run tests (coverage check included by default)
pytest

# View detailed coverage report
# Open: htmlcov/index.html
```

### Prototype

```powershell
# Install dependencies (one-time)
cd prototype
pip install -r requirements.txt

# Run tests (coverage check included by default)
pytest

# View detailed coverage report
# Open: htmlcov/index.html
```

## What This Means

- ✅ All test runs automatically measure and report code coverage
- ✅ Tests **fail** if coverage drops below 85%
- ✅ Failed tests block merging to main branches
- ✅ Coverage reports are always available in `htmlcov/` directory

## If Coverage Check Fails

1. **Identify uncovered code**: Open `htmlcov/index.html` in a browser
   - Red lines = not covered by tests
   - Yellow lines = partially covered
   - Green lines = fully covered

2. **Add tests** for the uncovered code, or

3. **Mark intentional exclusions** with `# pragma: no cover`:
   ```python
   def __repr__(self):  # pragma: no cover
       return f"{self.__class__.__name__}()"
   ```

4. **Re-run tests**:
   ```powershell
   pytest
   ```

## Threshold Details

- **Why 85%?** Balances quality with pragmatism
- **Not 100%**: Some code (error paths, UI, etc.) is hard/expensive to test
- **Not below 85%**: Ensures critical code paths are tested

## Configuration

Coverage settings are in:
- **Main**: `pyproject.toml` and `.coveragerc`
- **Prototype**: `pyproject.toml` and `.coveragerc`

Full documentation: [docs/configuration/coverage.md](../docs/configuration/coverage.md)

## Tips

- Run specific tests: `pytest tests/test_module.py --cov`
- Faster runs locally: `pytest --no-cov` (but CI will still check)
- Update threshold: Edit `fail_under` in `pyproject.toml` (don't lower!)

