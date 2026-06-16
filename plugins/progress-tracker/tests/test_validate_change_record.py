import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Insert scripts dir to sys.path so we can import validate_change_record
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import validate_change_record

@pytest.fixture
def temp_project(tmp_path):
    """Set up a mock project structure."""
    project_root = tmp_path / "progress-tracker"
    project_root.mkdir()
    
    docs_dir = project_root / "docs" / "changes"
    docs_dir.mkdir(parents=True)
    
    # Write a default high_risk_scripts.txt
    high_risk_file = docs_dir / "high_risk_scripts.txt"
    high_risk_file.write_text(
        "hooks/scripts/progress_manager.py\nhooks/scripts/git_utils.py\n", 
        encoding="utf-8"
    )
    
    # Write a default index.jsonl with a historical entry
    index_file = docs_dir / "index.jsonl"
    index_file.write_text(
        '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n',
        encoding="utf-8"
    )
    
    # Write the detail record
    detail_file = docs_dir / "20260521-pm-modularize-a7d2.md"
    detail_file.write_text("# Detail\n", encoding="utf-8")
    
    return project_root

def test_valid_ledger_passes(temp_project):
    """A fully valid staged ledger and records should pass validation."""
    index_file = temp_project / "docs" / "changes" / "index.jsonl"
    # Append a newly added valid row
    index_file.write_text(
        index_file.read_text(encoding="utf-8") +
        '{"change_id": "20260616-test-feature-a7b3", "date": "2026-06-16", "component": "hooks/scripts/progress_manager.py", "summary": "Fix validation", "root_cause": "Debt", "fixes": ["F19"], "touched_files": ["hooks/scripts/progress_manager.py"], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260616-test-feature-a7b3.md"}\n',
        encoding="utf-8"
    )
    # Write new detail file
    new_detail = temp_project / "docs" / "changes" / "20260616-test-feature-a7b3.md"
    new_detail.write_text("# Test Feature\n", encoding="utf-8")

    # Mock git commands
    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent) # repo root is temp_project's parent
        elif "diff --cached --name-only" in cmd:
            # Stage progress_manager.py (high risk) and index.jsonl and the new detail record
            return "progress-tracker/hooks/scripts/progress_manager.py\nprogress-tracker/docs/changes/index.jsonl\nprogress-tracker/docs/changes/20260616-test-feature-a7b3.md"
        elif "show :progress-tracker/docs/changes/index.jsonl" in cmd:
            return index_file.read_text(encoding="utf-8")
        elif "show HEAD:progress-tracker/docs/changes/index.jsonl" in cmd:
            # Only has historical row in HEAD
            return '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n'
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(0)

def test_invalid_jsonl_syntax(temp_project):
    """Invalid JSON syntax in index.jsonl should fail validation with exit code 1."""
    index_file = temp_project / "docs" / "changes" / "index.jsonl"
    index_file.write_text("invalid json\n", encoding="utf-8")

    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        elif "diff --cached --name-only" in cmd:
            return "progress-tracker/docs/changes/index.jsonl"
        elif "show :progress-tracker/docs/changes/index.jsonl" in cmd:
            return "invalid json\n"
        elif "show HEAD:progress-tracker/docs/changes/index.jsonl" in cmd:
            return ""
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(1)

def test_missing_required_fields(temp_project):
    """Index rows missing required fields should fail validation with exit code 1."""
    index_file = temp_project / "docs" / "changes" / "index.jsonl"
    index_file.write_text('{"change_id": "20260616-test-a7b3", "date": "2026-06-16"}\n', encoding="utf-8")

    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        elif "diff --cached --name-only" in cmd:
            return "progress-tracker/docs/changes/index.jsonl"
        elif "show :progress-tracker/docs/changes/index.jsonl" in cmd:
            return index_file.read_text(encoding="utf-8")
        elif "show HEAD:progress-tracker/docs/changes/index.jsonl" in cmd:
            return ""
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(1)

def test_duplicate_change_id(temp_project):
    """Duplicate change_ids in index.jsonl should fail validation with exit code 1."""
    index_file = temp_project / "docs" / "changes" / "index.jsonl"
    row = '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n'
    index_file.write_text(row + row, encoding="utf-8")

    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        elif "diff --cached --name-only" in cmd:
            return "progress-tracker/docs/changes/index.jsonl"
        elif "show :progress-tracker/docs/changes/index.jsonl" in cmd:
            return index_file.read_text(encoding="utf-8")
        elif "show HEAD:progress-tracker/docs/changes/index.jsonl" in cmd:
            return ""
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(1)

def test_missing_record_path(temp_project):
    """If the detail record file specified by record_path is missing, it should fail validation with exit code 1."""
    index_file = temp_project / "docs" / "changes" / "index.jsonl"
    index_file.write_text(
        '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/nonexistent.md"}\n',
        encoding="utf-8"
    )

    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        elif "diff --cached --name-only" in cmd:
            return "progress-tracker/docs/changes/index.jsonl"
        elif "show :progress-tracker/docs/changes/index.jsonl" in cmd:
            return index_file.read_text(encoding="utf-8")
        elif "show HEAD:progress-tracker/docs/changes/index.jsonl" in cmd:
            return ""
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(1)

def test_historical_rows_remain_valid(temp_project):
    """Historical rows in index.jsonl (already committed in HEAD) do not need to match the new change_id hex suffix naming convention."""
    # Historical change_id in temp_project index is "20260521-pm-modularize-a7d2" which matches, 
    # but let's change it in HEAD to a non-matching ID like "20260521-old-style" and make sure it still passes.
    index_file = temp_project / "docs" / "changes" / "index.jsonl"
    index_file.write_text(
        '{"change_id": "20260521-old-style", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n',
        encoding="utf-8"
    )

    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        elif "diff --cached --name-only" in cmd:
            return "progress-tracker/docs/changes/index.jsonl"
        elif "show :progress-tracker/docs/changes/index.jsonl" in cmd:
            return index_file.read_text(encoding="utf-8")
        elif "show HEAD:progress-tracker/docs/changes/index.jsonl" in cmd:
            # HEAD also has this exact historical row
            return index_file.read_text(encoding="utf-8")
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(0)

def test_newly_added_rows_fail_if_not_format(temp_project):
    """Newly added rows in index.jsonl must match the YYYYMMDD-<slug>-<4hex> format, else fail validation with exit code 1."""
    index_file = temp_project / "docs" / "changes" / "index.jsonl"
    index_file.write_text(
        index_file.read_text(encoding="utf-8") +
        '{"change_id": "20260616-invalid-id", "date": "2026-06-16", "component": "hooks/scripts/progress_manager.py", "summary": "Fix validation", "root_cause": "Debt", "fixes": ["F19"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n',
        encoding="utf-8"
    )

    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        elif "diff --cached --name-only" in cmd:
            return "progress-tracker/docs/changes/index.jsonl"
        elif "show :progress-tracker/docs/changes/index.jsonl" in cmd:
            return index_file.read_text(encoding="utf-8")
        elif "show HEAD:progress-tracker/docs/changes/index.jsonl" in cmd:
            # HEAD only has the historical row
            return '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n'
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(1)

def test_staged_high_risk_requires_change_record(temp_project):
    """If high-risk files are staged, but no newly added change record exists in index.jsonl, it must fail validation with exit code 1."""
    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        elif "diff --cached --name-only" in cmd:
            # Stage progress_manager.py which is high risk
            return "progress-tracker/hooks/scripts/progress_manager.py"
        elif "show :progress-tracker/docs/changes/index.jsonl" in cmd:
            # Staged index matches HEAD index (no newly added rows)
            return '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n'
        elif "show HEAD:progress-tracker/docs/changes/index.jsonl" in cmd:
            return '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n'
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(1)

def test_missing_high_risk_scripts_txt(temp_project):
    """If high_risk_scripts.txt is missing, it should fail validation with exit code 1."""
    # Delete the high_risk_scripts.txt
    (temp_project / "docs" / "changes" / "high_risk_scripts.txt").unlink()

    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(1)

def test_internal_error_returns_crash_code(temp_project):
    """If the validator encounters an unexpected internal error/crash, it should exit with code 2."""
    # Mocking run_git_command to raise a non-subprocess error, mimicking a crash
    with patch("validate_change_record.run_git_command", side_effect=KeyError("unexpected crash")):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(2)

def test_git_diff_failure_returns_crash_code(temp_project):
    """If git command fails during diff check, validator should crash and exit with 2."""
    def mock_git_command(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse --show-toplevel" in cmd:
            return str(temp_project.parent)
        elif "diff --cached" in cmd:
            raise subprocess.SubprocessError("git diff failed")
        return ""

    with patch("validate_change_record.run_git_command", side_effect=mock_git_command):
        with patch("sys.exit") as mock_exit:
            with patch("sys.argv", ["validate_change_record.py", "--project-root", str(temp_project)]):
                validate_change_record.main()
                mock_exit.assert_called_once_with(2)

