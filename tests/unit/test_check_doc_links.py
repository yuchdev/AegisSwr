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
def test_slugify_matches_github(heading: str, slug: str) -> None:
    assert cdl.slugify(heading) == slug


def test_duplicate_headings_get_suffixed_anchors(tmp_path: Path) -> None:
    doc = tmp_path / "dup.md"
    doc.write_text("# Tasks\n\n## Tasks\n\n## Tasks\n", encoding="utf-8")
    assert cdl.heading_anchors(doc) == {"tasks", "tasks-1", "tasks-2"}


def test_valid_links_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cdl, "REPO_ROOT", tmp_path)
    (tmp_path / "target.md").write_text("# Real Heading\n", encoding="utf-8")
    src = tmp_path / "src.md"
    src.write_text(
        "# Top\n\n"
        "[rel](target.md)\n"
        "[abs](/target.md)\n"
        "[anchor](target.md#real-heading)\n"
        "[inpage](#top)\n",
        encoding="utf-8",
    )
    assert cdl.check_file(src) == []


def test_dangling_file_and_missing_anchor_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cdl, "REPO_ROOT", tmp_path)
    (tmp_path / "target.md").write_text("# Only Heading\n", encoding="utf-8")
    src = tmp_path / "src.md"
    src.write_text(
        "# Top\n\n"
        "[gone](nope.md)\n"
        "[bad-anchor](target.md#does-not-exist)\n"
        "[bad-inpage](#missing)\n",
        encoding="utf-8",
    )
    problems = cdl.check_file(src)
    assert len(problems) == 3
    assert any("nope.md" in p for p in problems)
    assert any("does-not-exist" in p for p in problems)
    assert any("missing" in p for p in problems)


def test_skips_urls_templates_and_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
