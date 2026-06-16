import os
import subprocess
import sys
from pathlib import Path
import pytest

# Insert scripts dir to sys.path
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import rollback_helper


def _append_change_id_commit(repo: Path, pt_dir: Path, change_id: str, summary: str) -> str:
    index_file = pt_dir / "docs" / "changes" / "index.jsonl"
    index_file.write_text(
        index_file.read_text(encoding="utf-8") +
        (
            f'{{"change_id": "{change_id}", "date": "2026-06-16", '
            f'"component": "hooks/scripts/rollback_helper.py", "summary": "{summary}", '
            '"root_cause": "none", "fixes": [], "touched_files": [], '
            '"test_command": "pytest", "test_result": "pass", '
            f'"rollback_strategy": "revert", "record_path": "docs/changes/{change_id}.md"}}\n'
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", f"Commit for {change_id}"], cwd=repo, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

@pytest.fixture
def test_git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    
    # Init git
    subprocess.run(["git", "init", "--initial-branch", "trunk"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Rollback User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "rollback@example.com"], cwd=repo, check=True)
    
    # Create changes index layout
    pt_dir = repo / "plugins" / "progress-tracker"
    docs_dir = pt_dir / "docs" / "changes"
    docs_dir.mkdir(parents=True)
    prog_calls_log = pt_dir / "prog_calls.log"

    prog_script = pt_dir / "prog"
    prog_script.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "SCRIPT_DIR=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n"
        "printf '%s\\n' \"$*\" >> \"$SCRIPT_DIR/prog_calls.log\"\n"
        "if [[ \"$*\" == *\"reconcile-state --check\"* ]] && [[ \"${PT_FAKE_RECONCILE_EXIT_CODE:-0}\" != \"0\" ]]; then\n"
        "  exit \"$PT_FAKE_RECONCILE_EXIT_CODE\"\n"
        "fi\n",
        encoding="utf-8",
    )
    prog_script.chmod(0o755)
    
    # Initial index.jsonl with a row
    index_file = docs_dir / "index.jsonl"
    index_file.write_text(
        '{"change_id": "20260616-test-rollback-a2f8", "date": "2026-06-16", "component": "hooks/scripts/rollback_helper.py", "summary": "Initial summary", "root_cause": "none", "fixes": [], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260616-test-rollback-a2f8.md"}\n',
        encoding="utf-8"
    )
    
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit A (Addition)"], cwd=repo, check=True)
    
    # Get the addition SHA
    add_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    
    # Commit B: Modify the summary in index.jsonl (to verify --diff-filter=A only matches Commit A)
    index_file.write_text(
        '{"change_id": "20260616-test-rollback-a2f8", "date": "2026-06-16", "component": "hooks/scripts/rollback_helper.py", "summary": "Modified summary", "root_cause": "none", "fixes": [], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260616-test-rollback-a2f8.md"}\n',
        encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit B (Modification)"], cwd=repo, check=True)
    
    return {
        "repo": repo,
        "pt_dir": pt_dir,
        "add_sha": add_sha,
        "initial_branch": "trunk",
        "prog_calls_log": prog_calls_log,
    }

def test_find_commit_sha_diff_filter_a(test_git_repo):
    """Should only locate the commit that introduced (Added) the change_id row, not subsequent modifications."""
    repo = test_git_repo["repo"]
    pt_dir = test_git_repo["pt_dir"]
    expected_sha = test_git_repo["add_sha"]
    
    sha, all_shas = rollback_helper.find_commit_sha("20260616-test-rollback-a2f8", pt_dir)
    assert sha == expected_sha
    assert len(all_shas) == 1

def test_find_commit_sha_multiple_hits_warning(test_git_repo, capsys):
    """When a change_id is introduced in multiple commits (e.g. cherry-picked), warn the user and list all commits, selecting the latest."""
    repo = test_git_repo["repo"]
    pt_dir = test_git_repo["pt_dir"]
    index_file = pt_dir / "docs" / "changes" / "index.jsonl"
    
    # Append another entry with the SAME change_id in a new commit
    index_file.write_text(
        index_file.read_text(encoding="utf-8") +
        '{"change_id": "20260616-test-rollback-a2f8", "date": "2026-06-16", "component": "hooks/scripts/rollback_helper.py", "summary": "Duplicate entry", "root_cause": "none", "fixes": [], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260616-test-rollback-a2f8.md"}\n',
        encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit C (Duplicate Addition)"], cwd=repo, check=True)
    
    dup_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    
    sha, all_shas = rollback_helper.find_commit_sha("20260616-test-rollback-a2f8", pt_dir)
    assert sha == dup_sha
    assert len(all_shas) == 2

    captured = capsys.readouterr()
    assert "Warning: Multiple commits found" in captured.err
    assert dup_sha in captured.err


def test_rollback_route_a_success(test_git_repo, capsys):
    """Route A: Archive is available, reconcile succeeds -> Success."""
    pt_dir = test_git_repo["pt_dir"]

    archive_dir = pt_dir / "docs" / "progress-tracker" / "state" / "progress_archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "20260616T234324-test.progress.json").write_text("{}", encoding="utf-8")

    res = rollback_helper.run_rollback("20260616-test-rollback-a2f8", pt_dir)
    assert res is True
    captured = capsys.readouterr()
    assert "[Route A] Archive is available" in captured.out
    prog_calls = test_git_repo["prog_calls_log"].read_text(encoding="utf-8")
    assert "restore-archive 20260616T234324-test --force" in prog_calls
    assert "reconcile-state --check" in prog_calls

def test_rollback_route_b_success(test_git_repo, capsys):
    """Route B: Archive NOT available, git revert runs, then reconcile succeeds."""
    pt_dir = test_git_repo["pt_dir"]
    repo = test_git_repo["repo"]
    route_b_change_id = "20260616-test-route-b-c7a8"
    _append_change_id_commit(repo, pt_dir, route_b_change_id, "Route B target")

    res = rollback_helper.run_rollback(route_b_change_id, pt_dir)
    assert res is True
    captured = capsys.readouterr()
    assert "[Route B] Archive NOT available" in captured.out
    assert "MANUAL CONFIRMATION REQUIRED" in captured.out
    assert "git revert" not in subprocess.run(
        ["git", "show", "--stat", "--format=%s", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    head_subject = subprocess.run(
        ["git", "show", "--format=%s", "--no-patch", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head_subject.startswith("Revert ")
    prog_calls = test_git_repo["prog_calls_log"].read_text(encoding="utf-8")
    assert "reconcile-state --check" in prog_calls

def test_rollback_route_c_failure(test_git_repo, capsys):
    """Route C: Reconcile fails after real rollback path -> Abort and print diagnostics."""
    pt_dir = test_git_repo["pt_dir"]
    repo = test_git_repo["repo"]
    route_c_change_id = "20260616-test-route-c-a9d4"
    _append_change_id_commit(repo, pt_dir, route_c_change_id, "Route C target")
    os.environ["PT_FAKE_RECONCILE_EXIT_CODE"] = "1"
    with pytest.raises(SystemExit) as exc:
        rollback_helper.run_rollback(route_c_change_id, pt_dir)
    os.environ.pop("PT_FAKE_RECONCILE_EXIT_CODE", None)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "[Route C] EMERGENCY: Reconcile check failed" in captured.err
    assert "progress_manager.py reconcile --json" in captured.err
    assert "git status && git worktree list" in captured.err
    assert "check_pm_boundary.sh" in captured.err


def test_check_archive_available_real_detection(tmp_path):
    """Verify check_archive_available correctly scans progress_archive directory without mock."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    # 1. Directory doesn't exist
    assert rollback_helper.check_archive_available(project_root) is False
    
    # 2. Directory exists but empty
    archive_dir = project_root / "docs" / "progress-tracker" / "state" / "progress_archive"
    archive_dir.mkdir(parents=True)
    assert rollback_helper.check_archive_available(project_root) is False
    
    # 3. Directory has other files, but no .progress.json
    (archive_dir / "something.txt").write_text("hello")
    assert rollback_helper.check_archive_available(project_root) is False
    
    # 4. Directory has a valid *.progress.json file
    (archive_dir / "20260616T234324-test.progress.json").write_text("{}")
    assert rollback_helper.check_archive_available(project_root) is True


def test_rollback_route_b_no_mock_fallback(test_git_repo, capsys):
    """Route B: When no mock is provided and no archive exists in workspace, automatically fall back to Route B (git revert)."""
    pt_dir = test_git_repo["pt_dir"]
    repo = test_git_repo["repo"]
    route_b_change_id = "20260616-test-route-b-no-mock-b7e1"
    _append_change_id_commit(repo, pt_dir, route_b_change_id, "Route B no mock target")
    
    # Run rollback without passing mock_archive_available
    res = rollback_helper.run_rollback(
        route_b_change_id, 
        pt_dir, 
        mock_reconcile_pass=True
    )
    assert res is True
    captured = capsys.readouterr()
    assert "[Route B] Archive NOT available" in captured.out
    assert "git revert" in captured.out
    assert "MANUAL CONFIRMATION REQUIRED" in captured.out


def test_find_commit_sha_cross_history_lookup(test_git_repo, capsys):
    """Verify find_commit_sha searches across all branches (--all) and detects ambiguity across branches."""
    repo = test_git_repo["repo"]
    pt_dir = test_git_repo["pt_dir"]
    
    # Create branch-a and switch to it
    subprocess.run(["git", "checkout", "-b", "branch-a"], cwd=repo, check=True)
    
    # Add a new commit on branch-a that appends a duplicate change_id record
    index_file = pt_dir / "docs" / "changes" / "index.jsonl"
    index_file.write_text(
        index_file.read_text(encoding="utf-8") +
        '{"change_id": "20260616-test-rollback-a2f8", "date": "2026-06-16", "component": "hooks/scripts/rollback_helper.py", "summary": "Duplicate on branch-a", "root_cause": "none", "fixes": [], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260616-test-rollback-a2f8.md"}\n',
        encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit on branch-a"], cwd=repo, check=True)
    sha_a = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    
    # Switch back to the initial branch and create branch-b
    subprocess.run(["git", "checkout", test_git_repo["initial_branch"]], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-b", "branch-b"], cwd=repo, check=True)
    
    # Add another commit on branch-b that also appends a duplicate change_id record (at a later time)
    index_file.write_text(
        index_file.read_text(encoding="utf-8") +
        '{"change_id": "20260616-test-rollback-a2f8", "date": "2026-06-16", "component": "hooks/scripts/rollback_helper.py", "summary": "Duplicate on branch-b", "root_cause": "none", "fixes": [], "touched_files": [], "test_command": "pytest", "test_result": "pass", "rollback_strategy": "revert", "record_path": "docs/changes/20260616-test-rollback-a2f8.md"}\n',
        encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit on branch-b"], cwd=repo, check=True)
    sha_b = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    
    # Now we are on branch-b. Calling find_commit_sha should search all histories (main, branch-a, branch-b)
    # it must find commits introducing '20260616-test-rollback-a2f8' (sha_a, sha_b, and the original commit from main)
    sha, all_shas = rollback_helper.find_commit_sha("20260616-test-rollback-a2f8", pt_dir)
    
    # We should have 3 distinct commits introducing this change_id across all histories
    assert len(all_shas) == 3
    assert sha_b in all_shas
    assert sha_a in all_shas
    
    # And it should choose one of the newly introduced commits on the branches
    assert sha in (sha_a, sha_b)
    
    captured = capsys.readouterr()
    assert "Warning: Multiple commits found" in captured.err
    assert sha_a in captured.err
    assert sha_b in captured.err
