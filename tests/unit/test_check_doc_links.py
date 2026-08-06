"""Unit tests for the documentation link checker (``scripts/check_doc_links.py``).

The script lives outside the package, so it is loaded by file path rather than
imported as a module.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_doc_links.py"


def _load() -> Any:
    """Import the ``check_doc_links`` script module from its file path."""
    spec = importlib.util.spec_from_file_location("check_doc_links", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cdl = _load()


@pytest.mark.parametrize(
    "heading,slug",
    [
        ("Milestone 3.2 - AWS Bedrock Backend", "milestone-32---aws-bedrock-backend"),
        ("Log subsystem re-engineering ✅", "log-subsystem-re-engineering-"),
        ("Phase 6.2: Log Backend", "phase-62-log-backend"),
        ("Tasks", "tasks"),
    ],
)
def test_slugify_matches_github(heading: str, slug: str):
    """
    [Unit] check doc links: verifies slugify matches github.

    Scenario:
        Given test inputs and fixtures for slugify matches github
        When test_slugify_matches_github executes the target flow
        Then the expected outcome for slugify matches github is confirmed.

    Boundaries:
        - Focus: slugify matches github
        - Fixtures/params: heading, slug (parametrized, 4 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to slugify matches github
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by check doc links
    """
    assert cdl.slugify(heading) == slug


def test_duplicate_headings_get_suffixed_anchors(tmp_path: Path):
    """
    [Unit] check doc links: verifies duplicate headings get suffixed anchors.

    Scenario:
        Given test inputs and fixtures for duplicate headings get suffixed anchors
        When test_duplicate_headings_get_suffixed_anchors executes the target flow
        Then the expected outcome for duplicate headings get suffixed anchors is confirmed.

    Boundaries:
        - Focus: duplicate headings get suffixed anchors
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to duplicate headings get suffixed anchors
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by check doc links
    """
    doc = tmp_path / "dup.md"
    doc.write_text("# Tasks\n\n## Tasks\n\n## Tasks\n", encoding="utf-8")
    assert cdl.heading_anchors(doc) == {"tasks", "tasks-1", "tasks-2"}


def test_valid_links_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    [Unit] check doc links: verifies valid links pass.

    Scenario:
        Given test inputs and fixtures for valid links pass
        When test_valid_links_pass executes the target flow
        Then the expected outcome for valid links pass is confirmed.

    Boundaries:
        - Focus: valid links pass
        - Fixtures/params: tmp_path, monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to valid links pass
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by check doc links
    """
    monkeypatch.setattr(cdl, "REPO_ROOT", tmp_path)
    (tmp_path / "target.md").write_text("# Real Heading\n", encoding="utf-8")
    src = tmp_path / "src.md"
    src.write_text(
        "# Top\n\n" "[rel](target.md)\n" "[abs](/target.md)\n" "[anchor](target.md#real-heading)\n" "[inpage](#top)\n",
        encoding="utf-8",
    )
    assert cdl.check_file(src) == []


def test_dangling_file_and_missing_anchor_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    [Unit] check doc links: verifies dangling file and missing anchor fail.

    Scenario:
        Given test inputs and fixtures for dangling file and missing anchor fail
        When test_dangling_file_and_missing_anchor_fail executes the target flow
        Then the expected outcome for dangling file and missing anchor fail is confirmed.

    Boundaries:
        - Focus: dangling file and missing anchor fail
        - Fixtures/params: tmp_path, monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to dangling file and missing anchor fail
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by check doc links
    """
    monkeypatch.setattr(cdl, "REPO_ROOT", tmp_path)
    (tmp_path / "target.md").write_text("# Only Heading\n", encoding="utf-8")
    src = tmp_path / "src.md"
    src.write_text(
        "# Top\n\n" "[gone](nope.md)\n" "[bad-anchor](target.md#does-not-exist)\n" "[bad-inpage](#missing)\n",
        encoding="utf-8",
    )
    problems = cdl.check_file(src)
    assert len(problems) == 3
    assert any("nope.md" in p for p in problems)
    assert any("does-not-exist" in p for p in problems)
    assert any("missing" in p for p in problems)


def test_skips_urls_templates_and_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    [Unit] check doc links: verifies skips urls templates and code.

    Scenario:
        Given test inputs and fixtures for skips urls templates and code
        When test_skips_urls_templates_and_code executes the target flow
        Then the expected outcome for skips urls templates and code is confirmed.

    Boundaries:
        - Focus: skips urls templates and code
        - Fixtures/params: tmp_path, monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skips urls templates and code
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by check doc links
    """
    monkeypatch.setattr(cdl, "REPO_ROOT", tmp_path)
    src = tmp_path / "src.md"
    src.write_text(
        "# Top\n\n"
        "[ext](https://example.com/missing)\n"
        "[mail](mailto:a@b.c)\n"
        "[tmpl](docs/roadmap/{NNNN}-{slug}.md)\n"
        "[glob](/docs/adr/*.md)\n"
        "see `[code](should-not-count.md)` inline\n"
        "```\n[fenced](also-not-counted.md)\n```\n",
        encoding="utf-8",
    )
    assert cdl.check_file(src) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
