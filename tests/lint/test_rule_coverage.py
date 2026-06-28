from pathlib import Path
from lint_rules import check_file

def test_all_rules_coverage():
    """
    [Unit] lint: Verify all 10 custom rules are correctly applied to Python code.
    
    Scenario:
        Given a Python file containing intentional violations of rules X001-X011
        When check_file() is called on that file
        Then it should return RuleViolation instances for each expected rule.
    
    Boundaries:
        - Input: tests/lint/assets/violation_samples.py
        - Rules: X001, X002, X003, X004, X005, X006, X007, X008, X009, X010, X011
    
    On failure, first check:
        - If the violation samples in assets/violation_samples.py match the rules' logic
        - If any rule implementation has changed.
    """
    asset_path = Path(__file__).parent / "assets" / "violation_samples.py"
    violations = check_file(asset_path)
    
    violation_codes = {v.code for v in violations}
    
    expected_codes = {
        "X001", "X002", "X003", "X004", "X005", "X006", "X007", "X008", "X009", "X010", "X011"
    }
    
    missing = expected_codes - violation_codes
    assert not missing, f"Rules not detected: {missing}. Detected: {violation_codes}"
    
    print(f"Detected all expected rules: {expected_codes}")

if __name__ == "__main__":
    test_all_rules_coverage()
