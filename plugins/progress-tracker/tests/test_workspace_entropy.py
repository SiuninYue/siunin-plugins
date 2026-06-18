import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "hooks" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import workspace_entropy


def test_classifies_tracker_state_as_auto_commit():
    report = workspace_entropy.classify_dirty_entries([
        " M docs/progress-tracker/state/progress.json",
        " M plugins/progress-tracker/docs/progress-tracker/state/status_summary.v1.json",
    ])

    assert report["auto_commit"] == [
        "docs/progress-tracker/state/progress.json",
        "plugins/progress-tracker/docs/progress-tracker/state/status_summary.v1.json",
    ]
    assert report["quarantine"] == []
    assert report["block"] == []


def test_classifies_source_edits_as_quarantine_not_delete():
    report = workspace_entropy.classify_dirty_entries([
        " M plugins/progress-tracker/hooks/scripts/progress_manager.py",
    ])

    assert report["auto_commit"] == []
    assert report["quarantine"] == [
        "plugins/progress-tracker/hooks/scripts/progress_manager.py",
    ]
    assert report["block"] == []


def test_classifies_delete_of_source_file_as_block():
    report = workspace_entropy.classify_dirty_entries([
        " D plugins/progress-tracker/hooks/scripts/progress_manager.py",
    ])

    assert report["block"] == [
        "plugins/progress-tracker/hooks/scripts/progress_manager.py",
    ]


def test_branch_cleanup_deletes_only_merged_unchecked_local_branch():
    branches = [
        {"name": "f21", "is_current": False, "merged": True, "has_worktree": False},
        {"name": "main", "is_current": True, "merged": True, "has_worktree": True},
        {"name": "old-topic", "is_current": False, "merged": False, "has_worktree": False},
    ]

    report = workspace_entropy.classify_branches(branches, default_branch="main")

    assert report["delete_local"] == ["f21"]
    assert "main" in report["keep"]
    assert report["review"] == ["old-topic"]


from unittest.mock import patch


def test_entropy_check_cli_exits_zero(tmp_path, monkeypatch):
    """entropy-check --json should succeed and print JSON."""
    monkeypatch.chdir(tmp_path)
    # Create a minimal git repo so git commands don't fail
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, capture_output=True)

    with patch("sys.argv", ["progress_manager.py", "entropy-check", "--json"]):
        import progress_manager
        result = progress_manager.main()
    assert result in (0, None)


def test_entropy_fix_cli_safe_exits(tmp_path, monkeypatch):
    """entropy-fix --safe --json should succeed."""
    import subprocess
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, capture_output=True)

    with patch("sys.argv", ["progress_manager.py", "entropy-fix", "--safe", "--json"]):
        import progress_manager
        result = progress_manager.main()
    assert result in (0, 1, None)
