import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

@pytest.fixture
def test_git_repo(tmp_path):
    """Set up a real Git repository in tmp_path to test the hook."""
    repo = tmp_path / "repo"
    repo.mkdir()
    
    # Initialize Git repo
    subprocess.run(["git", "init"], cwd=repo, check=True)
    # Configure dummy user for commits
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    
    # Create project layout
    pt_dir = repo / "plugins" / "progress-tracker"
    pt_dir.mkdir(parents=True)
    
    # Copy scripts and hook
    src_pt = Path(__file__).resolve().parents[1]
    
    # Create target directories
    (pt_dir / "hooks" / "scripts").mkdir(parents=True)
    (pt_dir / "docs" / "changes").mkdir(parents=True)
    
    shutil.copy(src_pt / "hooks" / "pre-commit", pt_dir / "hooks" / "pre-commit")
    shutil.copy(src_pt / "hooks" / "scripts" / "validate_change_record.py", pt_dir / "hooks" / "scripts" / "validate_change_record.py")
    shutil.copy(src_pt / "hooks" / "scripts" / "render_changelog_from_index.py", pt_dir / "hooks" / "scripts" / "render_changelog_from_index.py")
    
    # Make sure they are executable
    os.chmod(pt_dir / "hooks" / "pre-commit", 0o755)
    os.chmod(pt_dir / "hooks" / "scripts" / "validate_change_record.py", 0o755)
    os.chmod(pt_dir / "hooks" / "scripts" / "render_changelog_from_index.py", 0o755)

    # Write a baseline high_risk_scripts.txt
    (pt_dir / "docs" / "changes" / "high_risk_scripts.txt").write_text(
        "hooks/scripts/progress_manager.py\n", encoding="utf-8"
    )
    
    # Write mock check_pm_boundary.sh
    boundary_script = repo / "scripts" / "check_pm_boundary.sh"
    boundary_script.parent.mkdir(parents=True, exist_ok=True)
    boundary_script.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    os.chmod(boundary_script, 0o755)
    
    # Write a baseline index.jsonl with a historical entry
    (pt_dir / "docs" / "changes" / "index.jsonl").write_text(
        '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "progress_manager", "summary": "Split PM", "root_cause": "Big file", "fixes": ["F18"], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n',
        encoding="utf-8"
    )
    
    # Write the detail record
    (pt_dir / "docs" / "changes" / "20260521-pm-modularize-a7d2.md").write_text("# Historical\n", encoding="utf-8")
    
    # Write CHANGELOG.md with markers
    (pt_dir / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n<!-- START_F19_MANAGED_BLOCK -->\n<!-- END_F19_MANAGED_BLOCK -->\n",
        encoding="utf-8"
    )

    # Initial commit to have a HEAD
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True)
    
    return repo

def test_pre_commit_hook_blocks_high_risk_without_record(test_git_repo):
    """When a high-risk file is modified but no change record added, pre-commit hook should block with exit code 1."""
    pt_dir = test_git_repo / "plugins" / "progress-tracker"
    
    # Create the high risk file and stage it
    high_risk_file = pt_dir / "hooks" / "scripts" / "progress_manager.py"
    high_risk_file.write_text("# modifying high risk file\n", encoding="utf-8")
    
    subprocess.run(["git", "add", str(high_risk_file)], cwd=test_git_repo, check=True)
    
    # Run the hook
    res = subprocess.run([str(pt_dir / "hooks" / "pre-commit")], cwd=test_git_repo, capture_output=True, text=True)
    assert res.returncode == 1
    assert "Staged changes contain high-risk files" in res.stderr

def test_pre_commit_hook_passes_with_change_record_and_autostages(test_git_repo):
    """When a high-risk file is modified and a proper change record is staged, hook should pass and auto-stage regenerated CHANGELOG.md."""
    pt_dir = test_git_repo / "plugins" / "progress-tracker"
    
    # Modify high risk file
    high_risk_file = pt_dir / "hooks" / "scripts" / "progress_manager.py"
    high_risk_file.write_text("# modifying high risk file\n", encoding="utf-8")
    subprocess.run(["git", "add", str(high_risk_file)], cwd=test_git_repo, check=True)
    
    # Add newly staged change record in index.jsonl
    index_file = pt_dir / "docs" / "changes" / "index.jsonl"
    index_file.write_text(
        index_file.read_text(encoding="utf-8") +
        '{"change_id": "20260616-test-new-a2b8", "date": "2026-06-16", "component": "progress_manager", "summary": "Fix PM", "root_cause": "clean", "fixes": ["F19"], "touched_files": ["hooks/scripts/progress_manager.py"], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260616-test-new-a2b8.md"}\n',
        encoding="utf-8"
    )
    # Write detail doc
    (pt_dir / "docs" / "changes" / "20260616-test-new-a2b8.md").write_text("# Detail new\n", encoding="utf-8")
    
    # Stage them
    subprocess.run(["git", "add", str(index_file), str(pt_dir / "docs" / "changes" / "20260616-test-new-a2b8.md")], cwd=test_git_repo, check=True)
    
    # Run the hook
    res = subprocess.run([str(pt_dir / "hooks" / "pre-commit")], cwd=test_git_repo, capture_output=True, text=True)
    assert res.returncode == 0
    
    # CHANGELOG.md should have been modified and auto-staged
    # We check git status to see if CHANGELOG.md is staged (changes to be committed)
    status_res = subprocess.run(["git", "status", "--porcelain"], cwd=test_git_repo, capture_output=True, text=True)
    # 'M  plugins/progress-tracker/CHANGELOG.md' means it is modified in index (staged)
    assert "M  plugins/progress-tracker/CHANGELOG.md" in status_res.stdout

def test_pre_commit_hook_fails_when_scripts_missing(test_git_repo):
    """When the validator or renderer script is missing, the pre-commit hook should block with exit code 1."""
    pt_dir = test_git_repo / "plugins" / "progress-tracker"
    
    # Remove the validator script
    (pt_dir / "hooks" / "scripts" / "validate_change_record.py").unlink()
    
    # Run the hook
    res = subprocess.run([str(pt_dir / "hooks" / "pre-commit")], cwd=test_git_repo, capture_output=True, text=True)
    assert res.returncode == 1
    assert "Validator script not found" in res.stderr

