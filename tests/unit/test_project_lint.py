"""Project-wide custom X-rule lint gate, run through the shared flakeforge engine.

This is the pytest half of the two lint gates required by ADR 0005. The other
half is the ``flakeforge check .`` CLI step in CI. Both resolve the same
``[tool.flakeforge]`` section and the same rule registry through one
``flakeforge.api`` boundary, so what blocks CI and what pytest reports cannot
drift apart.

Scope, rule selection and ``# noqa`` policy all live in ``pyproject.toml``; this
module deliberately holds no discovery or selection logic of its own.
"""

from __future__ import annotations

from pathlib import Path

from flakeforge.config import load_config
from flakeforge.testing import assert_lint_clean

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_sources_pass_all_active_custom_rules():
    """
    [Unit] flakeforge: project sources are clean under the active custom X-rules.

    Scenario:
        Given the include/exclude scope and select/ignore rule set declared in
        [tool.flakeforge] in pyproject.toml
        When the shared flakeforge engine lints the project tree from the
        repository root
        Then it reports no violations.

    Boundaries:
        - Real: config loading, file discovery, AST parsing, the rule registry
        - Scope: [tool.flakeforge] include (src, tests, scripts) minus exclude
        - Rules: the selected X-codes only; `# noqa` follows noqa_allowed/forbidden
        - Anchored on PROJECT_ROOT, so the result does not depend on the
          directory pytest was invoked from

    On failure, first check:
        - The violation list in the assertion message: each line is
          `path:line:col: CODE message`
        - Whether a recent change introduced the violation, or whether the
          pinned flakeforge engine changed rule behaviour
        - That `flakeforge check .` reports the same set; a disagreement means
          config drift between the two gates, which ADR 0005 forbids
    """
    assert_lint_clean(PROJECT_ROOT, config=load_config(cwd=PROJECT_ROOT))
