# Test Coverage Configuration (85% Threshold)

## Overview

Test coverage has been configured to enforce **85% minimum coverage** across both the main project and the prototype. This ensures code quality and helps identify untested code paths.

## Project Setup

### Main Project (`/`)

**Configuration file**: `pyproject.toml` (primary) and `.coveragerc` (backup)

**Coverage scope**: `src/aegis_swr/`

**Run tests with coverage**:
```powershell
pytest
# or explicitly request coverage
pytest --cov=src/aegis_swr --cov-fail-under=85
```

### Prototype (`/prototype`)

**Configuration file**: `pyproject.toml` (primary) and `.coveragerc` (backup)

**Coverage scope**: `wincrash_analyzer/`

**Run tests with coverage**:
```powershell
cd prototype
pytest
# or explicitly request coverage
pytest --cov=wincrash_analyzer --cov-fail-under=85
```

## Configuration Details

### Included in Coverage

- **Main**: All code in `src/aegis_swr/`
- **Prototype**: All code in `wincrash_analyzer/`
- Branch coverage is **enabled** (`branch = true`) for more thorough analysis
- Parallel testing support enabled for faster CI/CD

### Excluded from Coverage

The following are automatically excluded from coverage reports:

```
- pragma: no cover              # Manual exclusions with comments
- def __repr__                  # String representations
- raise AssertionError          # Assertion failures
- raise NotImplementedError     # Unimplemented methods
- if __name__ == .__main__.:   # Module entry points
- if TYPE_CHECKING:             # Type checking imports
- @abstractmethod               # Abstract method stubs
- pass                          # Empty passes
- except ImportError            # Import error handling
```

## Output Reports

All test runs with coverage generate:

1. **HTML Report** (interactive)
   - Main: `htmlcov/index.html`
   - Prototype: `prototype/htmlcov/index.html`
   - View in browser for detailed per-file coverage visualization

2. **Terminal Report** (quick summary)
   - Printed to console after test run
   - Shows missing lines and coverage percentage

3. **Exit Code**
   - **Non-zero** if coverage < 85% (test suite fails)
   - Tests must meet 85% threshold to pass CI/CD

## Common Commands

### Run All Tests with Coverage

**Main project**:
```powershell
pytest --cov=src/aegis_swr --cov-report=html --cov-report=term-missing
```

**Prototype**:
```powershell
cd prototype
pytest --cov=wincrash_analyzer --cov-report=html --cov-report=term-missing
```

### Check Coverage Without Failing on Threshold

```powershell
pytest --cov=src/aegis_swr --cov-report=term-missing --no-cov-on-fail
```

### Generate Only HTML Report

```powershell
pytest --cov=src/aegis_swr --cov-report=html
open htmlcov/index.html
```

### View Coverage for Specific Module

```powershell
pytest --cov=src/aegis_swr --cov-report=term-missing --cov-report=term-missing:skip-covered
```

## Why 85%?

- **Not too strict**: Allows pragmatic exclusions for edge cases and error handling
- **Not too loose**: Ensures critical code paths are tested
- **Industry standard**: Aligns with best practices for production code
- **Balances quality and velocity**: Achieves good coverage without diminishing returns

## Handling Coverage Failures

If tests fail due to low coverage:

1. **Identify uncovered code**:
   - Check the HTML report: `htmlcov/index.html`
   - Red lines indicate uncovered code
   - Look for key business logic that needs tests

2. **Add tests or exclusions**:
   - Write tests for important uncovered paths
   - Use `# pragma: no cover` for intentionally excluded code
   - Document why exclusions are necessary

3. **Example pragma**:
   ```python
   def __repr__(self):  # pragma: no cover
       return f"MyClass({self.value})"
   ```

4. **Re-run tests**:
   ```powershell
   pytest --cov=src/aegis_swr
   ```

## CI/CD Integration

The coverage threshold is automatically enforced:
- **Pytest hook**: `--cov-fail-under=85` added to default options
- **Test must pass**: Coverage < 85% will fail the build
- **HTML artifacts**: Coverage reports available in CI job artifacts

## Adjusting the Threshold

To change coverage requirements:

1. **In `pyproject.toml`**:
   ```toml
   [tool.coverage.report]
   fail_under = 90  # Change to desired percentage
   ```

2. **In `.coveragerc`**:
   ```ini
   [report]
   fail_under = 90
   ```

3. **Via CLI** (temporary, single run):
   ```powershell
   pytest --cov --cov-fail-under=90
   ```

## Troubleshooting

### Coverage shows 0%

- Verify source path is correct in configuration
- Ensure tests import modules being measured
- Check that `.coveragerc` or `pyproject.toml` exists in project root

### Some tests excluded from coverage

- Check if test files match the `source` pattern
- Tests themselves are typically not covered (only their targets)

### HTML report not generated

- Ensure `--cov-report=html` option is included
- Check write permissions in project directory
- Report is in `htmlcov/` subdirectory

## Documentation References

- [Coverage.py Docs](https://coverage.readthedocs.io/)
- [Pytest-cov Plugin](https://pytest-cov.readthedocs.io/)
- Project-specific docs: See `docs/` and `prototype/docs/`

