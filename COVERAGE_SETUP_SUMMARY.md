# 85% Test Coverage Setup - Summary

## Overview

Test coverage requirements of **85%** have been successfully configured for both the main project and the prototype.

## Files Modified

### 1. Main Project - `pyproject.toml`
- ✅ Added `pytest.ini_options.addopts` with `--cov-fail-under=85`
- ✅ Added `tool.coverage.run` with source path `src/aegis_swr`
- ✅ Added `tool.coverage.report` with threshold of 85%
- ✅ Configured coverage to exclude common non-testable patterns
- ✅ Added HTML coverage report generation

### 2. Main Project - `.coveragerc` (New)
- ✅ Created backup coverage configuration file
- ✅ Mirrors `pyproject.toml` coverage settings

### 3. Prototype - `requirements.txt`
- ✅ Added `pytest-cov==6.0.0` for coverage measurement

### 4. Prototype - `pyproject.toml`
- ✅ Updated `project.optional-dependencies.dev` to include `pytest-cov`
- ✅ Added `tool.pytest.ini_options` with `--cov-fail-under=85`
- ✅ Added `tool.coverage.run` with source path `wincrash_analyzer`
- ✅ Added `tool.coverage.report` with threshold of 85%
- ✅ Configured coverage to exclude common non-testable patterns
- ✅ Added HTML coverage report generation

### 5. Prototype - `.coveragerc` (New)
- ✅ Created backup coverage configuration file
- ✅ Mirrors `pyproject.toml` coverage settings

## Documentation Created

### 1. `docs/configuration/coverage.md`
- Comprehensive coverage configuration guide
- Explains 85% threshold rationale
- Includes troubleshooting section
- Documents CI/CD integration
- Provides examples and common commands

### 2. `COVERAGE_QUICKSTART.md` (New)
- Quick reference for developers
- Simple setup instructions
- Common workflows
- Tips and best practices

### 3. `validate_coverage.py` (New)
- Validation script to check coverage setup
- Verifies all configuration files exist
- Confirms 85% threshold is set
- Provides clear feedback on any issues

## Configuration Details

### Coverage Measurement

**Main Project**:
- Source: `src/aegis_swr/`
- Branch coverage: Enabled
- Parallel testing: Supported
- Threshold: 85%

**Prototype**:
- Source: `wincrash_analyzer/`
- Branch coverage: Enabled
- Parallel testing: Supported
- Threshold: 85%

### Automatic Exclusions

The following code patterns are excluded from coverage by default:

```
- pragma: no cover      (manual exclusions)
- def __repr__          (string representations)
- raise AssertionError  (assertions)
- raise NotImplementedError  (stubs)
- if __name__ == .__main__.: (entry points)
- if TYPE_CHECKING:     (type imports)
- @abstractmethod       (abstract methods)
- pass                  (empty statements)
- except ImportError    (import errors)
```

### Output Reports

All test runs generate:
1. **HTML Report**: Interactive visualization in `htmlcov/index.html`
2. **Terminal Report**: Summary with missing lines shown
3. **Exit Code**: Non-zero if coverage < 85%

## How It Works

### For Developers

```powershell
# Install dependencies
pip install -e .[dev]  # Main project
# OR
pip install -r requirements.txt  # Prototype

# Run tests - coverage check is automatic
pytest

# Coverage automatically:
# ✅ Measures code coverage
# ✅ Reports percentage and missing lines
# ✅ Fails test if < 85%
# ✅ Generates HTML report in htmlcov/
```

### For CI/CD

1. Test suite runs with coverage automatically enabled
2. Pytest fails if coverage < 85%
3. Build fails on low coverage
4. Coverage reports available as artifacts

## Validation

All configurations have been validated:

```
✅ Main project coverage configuration
✅ Prototype coverage configuration
✅ pytest-cov installed in dependencies
✅ All .coveragerc files present
✅ All pyproject.toml values correct
✅ Documentation complete
```

Run validation at any time:
```powershell
python validate_coverage.py
```

## Next Steps

1. **Install dependencies**:
   ```powershell
   pip install -e .[dev]        # Main
   cd prototype; pip install -r requirements.txt  # Prototype
   ```

2. **Run tests to confirm setup**:
   ```powershell
   pytest                        # Main
   cd prototype; pytest          # Prototype
   ```

3. **Review coverage reports**:
   - Open `htmlcov/index.html` in browser
   - Identify uncovered code paths
   - Add tests or pragma comments as needed

4. **Share with team**:
   - Point to `COVERAGE_QUICKSTART.md`
   - Reference `docs/configuration/coverage.md` for details

## Adjusting Coverage Threshold

To change the 85% requirement:

1. Edit `fail_under` in `pyproject.toml` (both projects)
2. Edit `fail_under` in `.coveragerc` (both projects)
3. Consider implications before lowering threshold

**Recommended**: Keep at 85% or increase it as code quality improves.

## Troubleshooting

### Coverage shows 0%
- Verify source paths are correct
- Check that tests actually import the code being measured

### Some modules not covered
- Normal: Tests aren't part of coverage
- Check HTML report to see which modules have missing lines

### Coverage numbers seem wrong
- Delete `.coverage` file and run tests again (cache issue)
- Run `pytest --cov-erase --cov ...`

### Want to exclude specific code
```python
def helper_function():  # pragma: no cover
    # This won't be counted toward coverage
    pass
```

## References

- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [Pytest-cov Plugin](https://pytest-cov.readthedocs.io/)
- [Project Docs](docs/)

