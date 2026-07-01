#!/usr/bin/env python
"""
Validate test coverage configuration for the 85% threshold.

This script checks that:
1. pytest-cov is installed
2. Coverage configuration files exist
3. The coverage threshold is set to 85%
"""

import sys
from pathlib import Path


def check_main_project() -> tuple[bool, list[str]]:
    """Check the main project coverage configuration."""
    issues = []
    root = Path(__file__).parent

    # Check pyproject.toml
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        issues.append("❌ Main project: pyproject.toml not found")
        return False, issues

    content = pyproject.read_text()
    if "fail_under = 85" not in content:
        issues.append("❌ Main project: fail_under = 85 not configured in pyproject.toml")
    if "--cov-fail-under=85" not in content:
        issues.append("❌ Main project: --cov-fail-under=85 not in pytest addopts")
    if 'source = ["src/aegis_swr"]' not in content:
        issues.append("❌ Main project: coverage source not set to src/aegis_swr")

    # Check .coveragerc
    coveragerc = root / ".coveragerc"
    if not coveragerc.exists():
        issues.append("⚠️  Main project: .coveragerc not found (backup config)")
    elif "fail_under = 85" not in coveragerc.read_text():
        issues.append("⚠️  Main project: fail_under = 85 not in .coveragerc (backup config)")

    if not issues:
        print("✅ Main project: All coverage configurations correct")

    return len(issues) == 0, issues


def check_prototype() -> tuple[bool, list[str]]:
    """Check prototype project coverage configuration."""
    issues = []
    proto = Path(__file__).parent / "prototype"

    # Check requirements.txt
    req_file = proto / "requirements.txt"
    if not req_file.exists():
        issues.append("❌ Prototype: requirements.txt not found")
        return False, issues

    content = req_file.read_text()
    if "pytest-cov" not in content:
        issues.append("❌ Prototype: pytest-cov not in requirements.txt")

    # Check pyproject.toml
    pyproject = proto / "pyproject.toml"
    if not pyproject.exists():
        issues.append("❌ Prototype: pyproject.toml not found")
        return False, issues

    content = pyproject.read_text()
    if "fail_under = 85" not in content:
        issues.append("❌ Prototype: fail_under = 85 not configured in pyproject.toml")
    if "--cov-fail-under=85" not in content:
        issues.append("❌ Prototype: --cov-fail-under=85 not in pytest addopts")
    if 'source = ["wincrash_analyzer"]' not in content:
        issues.append("❌ Prototype: coverage source not set to wincrash_analyzer")

    # Check .coveragerc
    coveragerc = proto / ".coveragerc"
    if not coveragerc.exists():
        issues.append("⚠️  Prototype: .coveragerc not found (backup config)")
    elif "fail_under = 85" not in coveragerc.read_text():
        issues.append("⚠️  Prototype: fail_under = 85 not in .coveragerc (backup config)")

    if not issues:
        print("✅ Prototype: All coverage configurations correct")

    return len(issues) == 0, issues


def check_documentation() -> tuple[bool, list[str]]:
    """Check that documentation exists."""
    issues = []
    doc = Path(__file__).parent / "docs" / "configuration" / "coverage.md"

    if not doc.exists():
        issues.append("⚠️  Coverage documentation not found at docs/configuration/coverage.md")
    else:
        print("✅ Coverage documentation: Found at docs/configuration/coverage.md")

    return len(issues) == 0, issues


def main() -> int:
    """Run all validation checks."""
    print("=" * 70)
    print("TEST COVERAGE CONFIGURATION VALIDATOR (85% THRESHOLD)")
    print("=" * 70)
    print()

    all_passed = True
    all_issues = []

    # Check main project
    main_pass, main_issues = check_main_project()
    all_passed = all_passed and main_pass
    all_issues.extend(main_issues)

    # Check prototype
    proto_pass, proto_issues = check_prototype()
    all_passed = all_passed and proto_pass
    all_issues.extend(proto_issues)

    # Check documentation
    doc_pass, doc_issues = check_documentation()
    all_passed = all_passed and doc_pass
    all_issues.extend(doc_issues)

    print()
    if all_issues:
        print("ISSUES FOUND:")
        for issue in all_issues:
            print(f"  {issue}")
        print()

    print("=" * 70)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Coverage at 85% is fully configured")
        print()
        print("Next steps:")
        print("  1. Install dependencies:")
        print("     - Main: pip install -e .[dev]")
        print("     - Prototype: pip install -r requirements.txt")
        print("  2. Run tests with coverage:")
        print("     - Main: pytest")
        print("     - Prototype: cd prototype && pytest")
        print("  3. View coverage reports in .htmlcov/index.html")
        print()
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Please review issues above")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
