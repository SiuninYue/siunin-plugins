"""Tests for quick validation tooling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import quick_validate


def test_run_checks_reports_missing_structure(tmp_path: Path) -> None:
    errors = quick_validate.run_checks(tmp_path, run_docs_check=False)
    assert errors
    assert any("Missing bug-fix directory" in item for item in errors)


def test_check_prog_start_contract_accepts_deprecation_notice(tmp_path: Path) -> None:
    command_path = tmp_path / "commands" / "prog-start.md"
    launcher_skill = tmp_path / "skills" / "prog-launcher" / "SKILL.md"
    command_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_skill.parent.mkdir(parents=True, exist_ok=True)
    command_path.write_text("Deprecated — use /prog-next instead.\n", encoding="utf-8")
    launcher_skill.write_text("---\nname: prog-launcher\n---\n", encoding="utf-8")

    errors: list[str] = []
    quick_validate.check_prog_start_contract(tmp_path, errors)
    assert errors == []


def test_check_prog_start_contract_rejects_alias_regression(tmp_path: Path) -> None:
    command_path = tmp_path / "commands" / "prog-start.md"
    launcher_skill = tmp_path / "skills" / "prog-launcher" / "SKILL.md"
    alias_skill = tmp_path / "skills" / "prog-start" / "SKILL.md"
    command_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_skill.parent.mkdir(parents=True, exist_ok=True)
    alias_skill.parent.mkdir(parents=True, exist_ok=True)
    command_path.write_text('skill: "progress-tracker:prog-start"\n', encoding="utf-8")
    launcher_skill.write_text("---\nname: prog-launcher\n---\n", encoding="utf-8")
    alias_skill.write_text("---\nname: prog-start\n---\n", encoding="utf-8")

    errors: list[str] = []
    quick_validate.check_prog_start_contract(tmp_path, errors)
    assert any("deprecated 'progress-tracker:prog-start'" in item for item in errors)
    assert any("Deprecated alias directory exists" in item for item in errors)


def test_quick_validate_script_passes_current_repo() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "hooks" / "scripts" / "quick_validate.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
