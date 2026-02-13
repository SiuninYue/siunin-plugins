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
