"""Tests for quick validation tooling."""

from __future__ import annotations

from pathlib import Path

import quick_validate


def test_run_checks_reports_missing_structure(tmp_path: Path) -> None:
    errors = quick_validate.run_checks(tmp_path, run_docs_check=False)
    assert errors
    assert any("Missing bug-fix directory" in item for item in errors)


def _write_skill(path: Path, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{frontmatter}\n\n# Sample Skill\n", encoding="utf-8")


def test_run_checks_reports_prohibited_frontmatter_with_paths(tmp_path: Path) -> None:
    skill_path = tmp_path / "skills" / "sample" / "SKILL.md"
    _write_skill(
        skill_path,
        "---\nname: sample\ndescription: Use when validating tests\nscope: skill\n---",
    )

    errors = quick_validate.run_checks(tmp_path, run_docs_check=False)
    assert any(
        "Prohibited frontmatter key 'scope'" in item and str(skill_path) in item
        for item in errors
    )


def test_run_checks_reports_non_routable_description_with_paths(tmp_path: Path) -> None:
    skill_path = tmp_path / "skills" / "sample" / "SKILL.md"
    _write_skill(
        skill_path,
        "---\nname: sample\ndescription: Handles validation checks\n---",
    )

    errors = quick_validate.run_checks(tmp_path, run_docs_check=False)
    assert any(
        "Non-routable description" in item and str(skill_path) in item
        for item in errors
    )
