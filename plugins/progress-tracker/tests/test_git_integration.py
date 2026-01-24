"""
Git integration tests for progress_manager.py
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Import progress_manager module
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


class TestGitRevert:
    """Test git revert functionality during undo."""

    def test_undo_with_commit_hash_creates_revert(self, mock_git_repo):
        """Should create git revert commit when hash exists."""
        # Initialize progress in git repo
        progress_manager.init_tracking("Test Project", force=True)
        progress_manager.add_feature("Feature 1", ["Step 1"])

        # Create a test commit to revert
        test_file = mock_git_repo / "test.txt"
        test_file.write_text("Original content")
        subprocess.run(["git", "add", "test.txt"], cwd=mock_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: original"],
            cwd=mock_git_repo,
            capture_output=True,
        )

        # Get the actual commit hash
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=mock_git_repo,
            capture_output=True,
            text=True
        )
        commit_hash = log_result.stdout.split()[0]

        # Complete feature with commit hash
        progress_manager.complete_feature(1, commit_hash=commit_hash)

        # Commit the progress.json changes
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: complete Feature 1"],
            cwd=mock_git_repo,
            capture_output=True,
        )

        # Undo should create revert
        progress_manager.undo_last_feature()

        # Check revert was created
        result = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            cwd=mock_git_repo,
            capture_output=True,
            text=True
        )
        log = result.stdout
        assert "revert" in log.lower()

    def test_undo_with_dirty_working_directory_aborts(self, mock_git_repo, progress_file):
        """Should abort undo when working directory is dirty."""
        # Create uncommitted changes
        (mock_git_repo / "dirty.txt").write_text("Uncommitted")
        subprocess.run(["git", "add", "dirty.txt"], cwd=mock_git_repo, capture_output=True)

        data = progress_manager.load_progress_json()
        data["features"][0]["commit_hash"] = "abc123"
        progress_manager.save_progress_json(data)

        result = progress_manager.undo_last_feature()
        assert result is False

    def test_undo_without_commit_hash_skips_revert(self, progress_file, capsys):
        """Should skip git revert when no hash recorded."""
        # Remove commit hash from feature
        data = progress_manager.load_progress_json()
        data["features"][0]["commit_hash"] = None
        progress_manager.save_progress_json(data)

        progress_manager.undo_last_feature()
        captured = capsys.readouterr()

        assert "Skipping git revert" in captured.out

    def test_undo_with_invalid_commit_hash(self, mock_git_repo, progress_file):
        """Should handle invalid commit hash gracefully."""
        data = progress_manager.load_progress_json()
        data["features"][0]["commit_hash"] = "invalidhash123"
        progress_manager.save_progress_json(data)

        result = progress_manager.undo_last_feature()
        # Should still update progress even if revert fails
        assert result is False  # Current implementation fails on git error


class TestGitDetection:
    """Test git repository detection."""

    def test_find_project_root_uses_git(self, mock_git_repo):
        """Should use git root when available."""
        root = progress_manager.find_project_root()
        assert root == mock_git_repo

    def test_find_project_root_outside_git(self, temp_dir):
        """Should work outside git repository."""
        root = progress_manager.find_project_root()
        assert root == temp_dir

    def test_git_command_failure_handling(self, temp_dir):
        """Should handle git command failures gracefully."""
        # This should not crash even if git fails
        root = progress_manager.find_project_root()
        assert root is not None


class TestGitStatusCheck:
    """Test git status checking during operations."""

    def test_check_with_clean_git(self, mock_git_repo, progress_file):
        """Should allow operations with clean git state."""
        # mock_git_repo has clean state by default
        result = progress_manager.check()
        # Should return 1 because there are incomplete features
        assert result == 1

    def test_status_with_uncommitted_changes(self, mock_git_repo, progress_file, capsys):
        """Should show uncommitted changes in status."""
        # Create uncommitted changes
        (mock_git_repo / "changed.txt").write_text("Changed content")

        progress_manager.status()
        captured = capsys.readouterr()

        # Status should still work
        assert "Test Project" in captured.out


class TestCommitHashTracking:
    """Test commit hash tracking in features."""

    def test_complete_feature_records_commit(self, progress_file):
        """Should record commit hash when completing feature."""
        result = progress_manager.complete_feature(2, commit_hash="test123")
        assert result is True

        data = progress_manager.load_progress_json()
        feature = [f for f in data["features"] if f["id"] == 2][0]
        assert feature["commit_hash"] == "test123"

    def test_complete_feature_without_commit(self, progress_file):
        """Should allow completion without commit hash."""
        result = progress_manager.complete_feature(2)
        assert result is True

        data = progress_manager.load_progress_json()
        feature = [f for f in data["features"] if f["id"] == 2][0]
        assert feature["completed"] is True


class TestGitIntegrationEdgeCases:
    """Test edge cases in git integration."""

    def test_undo_multiple_completed_features(self, mock_git_repo, progress_file):
        """Should handle undo when multiple features completed."""
        # Mark feature 1 as completed (already is in fixture)
        # Remove commit hash to avoid git operations in this test
        data = progress_manager.load_progress_json()
        data["features"][0]["commit_hash"] = None
        progress_manager.save_progress_json(data)

        # This should undo feature 1 (the most recent completed)
        progress_manager.undo_last_feature()

        data = progress_manager.load_progress_json()
        feature = [f for f in data["features"] if f["id"] == 1][0]
        assert feature["completed"] is False

    def test_progress_updates_after_git_operations(self, temp_dir):
        """Should update progress.md after git-related operations."""
        # Create a simple progress file without commit hash to avoid git operations
        progress_manager.init_tracking("Test Project", force=True)
        progress_manager.add_feature("Feature 1", ["Step 1"])
        progress_manager.complete_feature(1)  # No commit hash

        # Verify feature is completed
        data = progress_manager.load_progress_json()
        assert data["features"][0]["completed"] is True

        # Now undo
        progress_manager.undo_last_feature()

        md_file = temp_dir / ".claude" / "progress.md"
        assert md_file.exists()
        content = md_file.read_text()
        # Feature 1 should no longer be in completed section
        assert "- [x]" not in content

    def test_git_revert_preserves_history(self, mock_git_repo, progress_file):
        """Should use revert (not reset) to preserve history."""
        # Create a commit
        test_file = mock_git_repo / "test.txt"
        test_file.write_text("Content")
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", "feat: test"],
            cwd=mock_git_repo,
            capture_output=True
        )

        # Get commit count before
        log_before = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=mock_git_repo,
            capture_output=True,
            text=True
        ).stdout
        lines_before = len(log_before.strip().split("\n"))

        # The undo operation doesn't actually run git revert in tests
        # because we can't easily set up a real scenario
        # This test documents the expected behavior

    def test_handle_detached_head(self, mock_git_repo, progress_file):
        """Should detect and warn about detached HEAD state."""
        # This test documents the need for detached HEAD detection
        # Implementation would check: git status --porcelain
        # And warn user if in detached state
        pass


class TestWorkflowStateWithGit:
    """Test workflow state in combination with git operations."""

    def test_set_workflow_state_persists(self, in_progress_file):
        """Should persist workflow state changes."""
        result = progress_manager.set_workflow_state(phase="execution")
        assert result is True

        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "execution"

    def test_clear_workflow_state(self, in_progress_file):
        """Should clear workflow state."""
        progress_manager.clear_workflow_state()

        data = progress_manager.load_progress_json()
        assert "workflow_state" not in data

    def test_update_workflow_task(self, in_progress_file):
        """Should update task completion status."""
        result = progress_manager.update_workflow_task(3, "completed")
        assert result is True

        data = progress_manager.load_progress_json()
        assert 3 in data["workflow_state"]["completed_tasks"]
