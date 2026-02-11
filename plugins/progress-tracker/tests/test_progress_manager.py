"""
Core functionality tests for progress_manager.py
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Import progress_manager module
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


class TestProjectRootDetection:
    """Test project root directory detection."""

    def test_find_project_root_git_repo(self, mock_git_repo):
        """Should find git root when in a git repository."""
        root = progress_manager.find_project_root()
        assert root == mock_git_repo

    def test_find_project_root_with_claude_dir(self, temp_dir):
        """Should find parent directory containing .claude."""
        claude_dir = temp_dir / "subdir" / ".claude"
        claude_dir.mkdir(parents=True)

        os.chdir(temp_dir / "subdir")
        root = progress_manager.find_project_root()
        assert root == temp_dir / "subdir"

    def test_find_project_root_fallback_to_cwd(self, temp_dir):
        """Should fallback to current working directory."""
        root = progress_manager.find_project_root()
        assert root == temp_dir


class TestProgressInit:
    """Test progress tracking initialization."""

    def test_init_tracking_new_project(self, temp_dir):
        """Should initialize new project tracking."""
        result = progress_manager.init_tracking("Test Project", force=True)
        assert result is True

        progress_file = temp_dir / ".claude" / "progress.json"
        assert progress_file.exists()

        data = json.loads(progress_file.read_text())
        assert data["project_name"] == "Test Project"
        assert data["features"] == []
        assert data["current_feature_id"] is None

    def test_init_tracking_with_features(self, temp_dir):
        """Should initialize with provided features."""
        features = [
            {"id": 1, "name": "Feature 1", "test_steps": ["Step 1"], "completed": False}
        ]
        result = progress_manager.init_tracking("Test Project", features=features, force=True)
        assert result is True

        data = progress_manager.load_progress_json()
        assert len(data["features"]) == 1
        assert data["features"][0]["name"] == "Feature 1"

    def test_init_tracking_existing_project_aborts(self, progress_file):
        """Should abort when tracking already exists (without force)."""
        result = progress_manager.init_tracking("Another Project")
        assert result is False

    def test_init_tracking_existing_with_force(self, progress_file):
        """Should re-initialize when force is True."""
        result = progress_manager.init_tracking("New Project", force=True)
        assert result is True

        data = progress_manager.load_progress_json()
        assert data["project_name"] == "New Project"

    def test_init_creates_progress_md(self, temp_dir):
        """Should create progress.md file."""
        progress_manager.init_tracking("Test Project", force=True)

        md_file = temp_dir / ".claude" / "progress.md"
        assert md_file.exists()
        content = md_file.read_text()
        assert "Test Project" in content


class TestProgressLoadSave:
    """Test loading and saving progress data."""

    def test_load_progress_json(self, progress_file):
        """Should load progress.json correctly."""
        data = progress_manager.load_progress_json()
        assert data is not None
        assert data["project_name"] == "Test Project"
        assert len(data["features"]) == 3

    def test_load_progress_json_missing(self, temp_dir):
        """Should return None when progress.json doesn't exist."""
        data = progress_manager.load_progress_json()
        assert data is None

    def test_save_progress_json(self, temp_dir):
        """Should save data to progress.json."""
        test_data = {"project_name": "Save Test", "features": [], "current_feature_id": None}
        progress_manager.save_progress_json(test_data)

        progress_file = temp_dir / ".claude" / "progress.json"
        assert progress_file.exists()

        loaded = json.loads(progress_file.read_text())
        assert loaded["project_name"] == "Save Test"


class TestFeatureManagement:
    """Test feature add and complete operations."""

    def test_add_feature_generates_incrementing_id(self, progress_file):
        """Should generate incrementing feature IDs."""
        progress_manager.add_feature("New Feature", ["Test step"])

        data = progress_manager.load_progress_json()
        new_feature = [f for f in data["features"] if f["name"] == "New Feature"][0]
        assert new_feature["id"] == 4  # Last ID was 3

    def test_add_feature_with_no_existing(self, temp_dir):
        """Should start with ID 1 when no features exist."""
        progress_manager.init_tracking("Test", force=True)
        progress_manager.add_feature("First Feature", ["Step 1"])

        data = progress_manager.load_progress_json()
        assert data["features"][0]["id"] == 1

    def test_update_feature_name(self, progress_file):
        """Should update an existing feature name."""
        result = progress_manager.update_feature(2, "Updated Feature")
        assert result is True

        data = progress_manager.load_progress_json()
        feature = [f for f in data["features"] if f["id"] == 2][0]
        assert feature["name"] == "Updated Feature"
        assert feature["test_steps"] == ["Step A", "Step B"]

    def test_update_feature_name_and_steps(self, progress_file):
        """Should update feature name and test steps together."""
        result = progress_manager.update_feature(2, "Feature 2 Updated", ["New Step 1"])
        assert result is True

        data = progress_manager.load_progress_json()
        feature = [f for f in data["features"] if f["id"] == 2][0]
        assert feature["name"] == "Feature 2 Updated"
        assert feature["test_steps"] == ["New Step 1"]

    def test_complete_feature_updates_status(self, progress_file):
        """Should mark feature as completed."""
        result = progress_manager.complete_feature(2, commit_hash="test123")
        assert result is True

        data = progress_manager.load_progress_json()
        feature = [f for f in data["features"] if f["id"] == 2][0]
        assert feature["completed"] is True
        assert feature["commit_hash"] == "test123"
        assert "completed_at" in feature

    def test_complete_feature_clears_current(self, in_progress_file):
        """Should clear current_feature_id when completing."""
        data = progress_manager.load_progress_json()
        assert data["current_feature_id"] == 2

        progress_manager.complete_feature(2)

        data = progress_manager.load_progress_json()
        assert data["current_feature_id"] is None


class TestStatusDisplay:
    """Test status command output."""

    def test_status_shows_statistics(self, progress_file, capsys):
        """Should display completion statistics."""
        progress_manager.status()
        captured = capsys.readouterr()

        assert "Test Project" in captured.out
        assert "1/3" in captured.out  # 1 completed out of 3

    def test_status_in_progress_feature(self, in_progress_file, capsys):
        """Should show current feature when in progress."""
        progress_manager.status()
        captured = capsys.readouterr()

        assert "In Progress Feature" in captured.out
        assert "in progress" in captured.out.lower()


class TestCurrentFeature:
    """Test current feature management."""

    def test_set_current_feature(self, progress_file):
        """Should set current feature ID."""
        result = progress_manager.set_current(2)
        assert result is True

        data = progress_manager.load_progress_json()
        assert data["current_feature_id"] == 2

    def test_set_nonexistent_feature(self, progress_file):
        """Should fail when feature ID doesn't exist."""
        result = progress_manager.set_current(999)
        assert result is False

    def test_get_next_pending_feature(self, progress_file):
        """Should return first incomplete feature."""
        next_feature = progress_manager.get_next_feature()
        assert next_feature is not None
        assert next_feature["id"] == 2  # First incomplete

    def test_get_next_feature_when_all_complete(self, progress_file):
        """Should return None when all features complete."""
        # Mark all as complete
        data = progress_manager.load_progress_json()
        for f in data["features"]:
            f["completed"] = True
        progress_manager.save_progress_json(data)

        next_feature = progress_manager.get_next_feature()
        assert next_feature is None


class TestProgressMdGeneration:
    """Test progress.md markdown generation."""

    def test_generate_progress_md_content(self, progress_file):
        """Should generate correct markdown content."""
        data = progress_manager.load_progress_json()
        md_content = progress_manager.generate_progress_md(data)

        assert "# Project Progress: Test Project" in md_content
        assert "## Completed" in md_content
        assert "- [x] Feature 1" in md_content
        assert "## Pending" in md_content
        assert "- [ ] Feature 2" in md_content

    def test_save_progress_md(self, temp_dir):
        """Should save markdown to file."""
        progress_manager.init_tracking("MD Test", force=True)
        progress_manager.save_progress_md("# Test Content")

        md_file = temp_dir / ".claude" / "progress.md"
        assert md_file.read_text() == "# Test Content"


class TestReset:
    """Test reset functionality."""

    def test_reset_removes_tracking(self, progress_file):
        """Should remove .claude directory."""
        result = progress_manager.reset_tracking(force=True)
        assert result is True

        claude_dir = progress_file.parent
        assert not claude_dir.exists()

    def test_reset_without_tracking(self, temp_dir):
        """Should handle gracefully when no tracking exists."""
        result = progress_manager.reset_tracking(force=True)
        assert result is True


class TestUndo:
    """Test undo functionality."""

    def test_undo_last_feature(self, temp_dir):
        """Should undo last completed feature."""
        # Set up a simple project without commit hash
        progress_manager.init_tracking("Test Project", force=True)
        progress_manager.add_feature("Feature 1", ["Step 1"])
        progress_manager.complete_feature(1)  # No commit hash

        result = progress_manager.undo_last_feature()
        assert result is True

        data = progress_manager.load_progress_json()
        feature = [f for f in data["features"] if f["id"] == 1][0]
        assert feature["completed"] is False
        assert "completed_at" not in feature

    def test_undo_with_no_completed_features(self, temp_dir):
        """Should fail when no completed features exist."""
        progress_manager.init_tracking("Test", force=True)
        result = progress_manager.undo_last_feature()
        assert result is False

    def test_undo_selects_most_recent(self, temp_dir):
        """Should select most recently completed feature."""
        progress_manager.init_tracking("Test Project", force=True)
        progress_manager.add_feature("Feature 1", ["Step 1"])
        progress_manager.add_feature("Feature 2", ["Step 2"])

        # Complete feature 1 first
        progress_manager.complete_feature(1)

        # Small delay to ensure different timestamps
        import time
        time.sleep(0.01)

        # Complete feature 2 later
        progress_manager.complete_feature(2)

        # Feature 2 should have a later completed_at timestamp
        data = progress_manager.load_progress_json()
        date1 = data["features"][0]["completed_at"]
        date2 = data["features"][1]["completed_at"]
        assert date2 > date1, "Feature 2 should have later completion time"

        # Undo should remove feature 2 (most recent)
        progress_manager.undo_last_feature()
        data = progress_manager.load_progress_json()

        # Feature 2 (id=2) should be undone (most recent)
        # Features are 0-indexed in the list, id 1 is first, id 2 is second
        feature_2 = [f for f in data["features"] if f["id"] == 2][0]
        assert feature_2["completed"] is False

        # Feature 1 should still be completed
        feature_1 = [f for f in data["features"] if f["id"] == 1][0]
        assert feature_1["completed"] is True

    def test_undo_preserves_other_completed_features(self, temp_dir):
        """Should only undo the most recent feature, not all completed."""
        progress_manager.init_tracking("Test Project", force=True)
        progress_manager.add_feature("Feature 1", ["Step 1"])
        progress_manager.add_feature("Feature 2", ["Step 2"])
        progress_manager.add_feature("Feature 3", ["Step 3"])

        progress_manager.complete_feature(1)
        import time
        time.sleep(0.01)
        progress_manager.complete_feature(2)
        time.sleep(0.01)
        progress_manager.complete_feature(3)

        # Undo last (feature 3)
        progress_manager.undo_last_feature()

        data = progress_manager.load_progress_json()
        # Features 1 and 2 should still be completed
        assert [f for f in data["features"] if f["id"] == 1][0]["completed"] is True
        assert [f for f in data["features"] if f["id"] == 2][0]["completed"] is True
        # Feature 3 should be incomplete
        assert [f for f in data["features"] if f["id"] == 3][0]["completed"] is False


class TestPluginRoot:
    """Test plugin root detection."""

    def test_get_plugin_root_from_env(self, monkeypatch):
        """Should use CLAUDE_PLUGIN_ROOT environment variable if set."""
        # Create a temp dir and make it look like a plugin root
        import tempfile
        temp = Path(tempfile.mkdtemp())
        (temp / "hooks" / "scripts").mkdir(parents=True)
        (temp / "hooks" / "scripts" / "progress_manager.py").write_text("# dummy")

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(temp))
        root = progress_manager.get_plugin_root()
        assert root == temp

        # Cleanup
        import shutil
        shutil.rmtree(temp)

    def test_get_plugin_root_fallback(self, monkeypatch):
        """Should fallback to script-relative path when env not set."""
        # Remove env var if set
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        # This should not raise an error since we're in the plugin directory
        root = progress_manager.get_plugin_root()
        assert root is not None

    def test_validate_plugin_root(self, temp_dir):
        """Should validate plugin root directory."""
        # Create a valid plugin structure
        (temp_dir / "hooks" / "scripts").mkdir(parents=True)
        (temp_dir / "hooks" / "scripts" / "progress_manager.py").write_text("# dummy")

        assert progress_manager.validate_plugin_root(temp_dir) is True

    def test_validate_plugin_root_invalid(self, temp_dir):
        """Should reject invalid plugin root."""
        assert progress_manager.validate_plugin_root(temp_dir) is False


class TestProgressMdFile:
    """Test progress.md file operations."""

    def test_load_progress_md(self, temp_dir):
        """Should load progress.md content."""
        progress_manager.init_tracking("Test", force=True)
        content = progress_manager.load_progress_md()
        assert content is not None
        assert "Test" in content

    def test_load_progress_md_missing(self, temp_dir):
        """Should return None when progress.md doesn't exist."""
        content = progress_manager.load_progress_md()
        assert content is None


class TestCheckCommand:
    """Test check command for recovery."""

    def test_check_no_tracking(self, temp_dir):
        """Should return 0 when no tracking exists."""
        result = progress_manager.check()
        assert result == 0

    def test_check_all_complete(self, temp_dir):
        """Should return 0 when all features complete."""
        progress_manager.init_tracking("Test", force=True)
        progress_manager.add_feature("F1", ["Step 1"])
        progress_manager.complete_feature(1)

        result = progress_manager.check()
        assert result == 0


class TestGitSyncPreflight:
    """Test Git sync risk analysis and preflight command."""

    def test_analyze_git_sync_skips_outside_git(self, temp_dir):
        """Should skip Git checks outside repositories."""
        report = progress_manager.analyze_git_sync_risks()
        assert report["status"] == "skipped"
        assert report["issues"] == []

    def test_analyze_git_sync_warns_when_no_upstream(self, mock_git_repo):
        """Should warn when current branch has no upstream tracking."""
        report = progress_manager.analyze_git_sync_risks()
        issue_ids = {issue["id"] for issue in report["issues"]}

        assert "no_upstream" in issue_ids
        assert report["status"] in ["warning", "critical"]

    def test_analyze_git_sync_detects_in_progress_operation(self, mock_git_repo):
        """Should detect active rebase/merge marker files as critical."""
        rebase_dir = mock_git_repo / ".git" / "rebase-merge"
        rebase_dir.mkdir(parents=True, exist_ok=True)

        report = progress_manager.analyze_git_sync_risks()
        issue_ids = {issue["id"] for issue in report["issues"]}

        assert "operation_in_progress" in issue_ids
        assert report["status"] == "critical"


class TestSetCurrent:
    """Test set current feature."""

    def test_set_current_no_tracking(self, temp_dir):
        """Should fail when no tracking exists."""
        result = progress_manager.set_current(1)
        assert result is False


class TestCompleteFeature:
    """Test complete feature edge cases."""

    def test_complete_feature_no_tracking(self, temp_dir):
        """Should fail when no tracking exists."""
        result = progress_manager.complete_feature(1)
        assert result is False

    def test_complete_feature_not_found(self, progress_file):
        """Should fail when feature ID doesn't exist."""
        result = progress_manager.complete_feature(999)
        assert result is False


class TestAddFeature:
    """Test add feature edge cases."""

    def test_add_feature_no_tracking(self, temp_dir):
        """Should fail when no tracking exists."""
        result = progress_manager.add_feature("New", ["Step 1"])
        assert result is False


class TestGetProgressDir:
    """Test get_progress_dir function."""

    def test_get_progress_dir_returns_path(self, temp_dir):
        """Should return path to .claude directory."""
        progress_dir = progress_manager.get_progress_dir()
        assert progress_dir is not None
        assert ".claude" in str(progress_dir)


class TestWorkflowStateEdgeCases:
    """Test workflow state edge cases."""

    def test_set_workflow_state_preserves_existing_fields(self, in_progress_file):
        """Should preserve existing workflow state fields when updating some."""
        data = progress_manager.load_progress_json()
        original_plan = data["workflow_state"]["plan_path"]

        # Update only phase
        progress_manager.set_workflow_state(phase="test_phase")

        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["plan_path"] == original_plan
        assert data["workflow_state"]["phase"] == "test_phase"


class TestJsonErrorHandling:
    """Test JSON parsing error handling."""

    def test_load_corrupted_progress_json(self, temp_dir, capsys):
        """Should handle corrupted progress.json gracefully."""
        claude_dir = temp_dir / ".claude"
        claude_dir.mkdir(parents=True)
        progress_file = claude_dir / "progress.json"
        progress_file.write_text("{invalid json content")

        result = progress_manager.load_progress_json()
        assert result is None

        captured = capsys.readouterr()
        assert "Error:" in captured.out or "corrupted" in captured.out.lower()


class TestMainFunction:
    """Test main function entry point."""

    def test_main_without_args(self, capsys):
        """Should show help when no args provided."""
        with patch("sys.argv", ["progress_manager.py"]):
            result = progress_manager.main()
            # main() returns 1 when no command
            assert result is not None

    def test_main_status_command(self, progress_file):
        """Should handle status command."""
        with patch("sys.argv", ["progress_manager.py", "status"]):
            result = progress_manager.main()
            # status() returns True on success
            assert result is True

    def test_main_check_command(self, progress_file):
        """Should handle check command."""
        with patch("sys.argv", ["progress_manager.py", "check"]):
            result = progress_manager.main()
            # check() returns 1 when incomplete
            assert result == 1

    def test_main_git_sync_check_command(self, mock_git_repo):
        """Should handle git-sync-check command."""
        with patch("sys.argv", ["progress_manager.py", "git-sync-check"]):
            result = progress_manager.main()
            assert result is True

    def test_main_init_command(self, temp_dir):
        """Should handle init command."""
        with patch("sys.argv", ["progress_manager.py", "init", "TestProject"]):
            result = progress_manager.main()
            # init_tracking() returns True on success
            assert result is True

    def test_main_add_feature_command(self, progress_file):
        """Should handle add-feature command."""
        with patch("sys.argv", ["progress_manager.py", "add-feature", "NewFeature", "step1", "step2"]):
            result = progress_manager.main()
            # add_feature() returns True on success
            assert result is True

    def test_main_update_feature_command(self, progress_file):
        """Should handle update-feature command."""
        with patch("sys.argv", ["progress_manager.py", "update-feature", "2", "RenamedFeature", "new-step"]):
            result = progress_manager.main()
            assert result is True

    def test_main_set_current_command(self, progress_file):
        """Should handle set-current command."""
        with patch("sys.argv", ["progress_manager.py", "set-current", "1"]):
            result = progress_manager.main()
            # set_current() returns True on success
            assert result is True

    def test_main_complete_command(self, progress_file):
        """Should handle complete command."""
        with patch("sys.argv", ["progress_manager.py", "complete", "1"]):
            result = progress_manager.main()
            # complete_feature() returns True on success
            assert result is True

    def test_main_undo_command(self, temp_dir):
        """Should handle undo command."""
        progress_manager.init_tracking("Test", force=True)
        progress_manager.add_feature("F1", ["S1"])
        progress_manager.complete_feature(1)

        with patch("sys.argv", ["progress_manager.py", "undo"]):
            result = progress_manager.main()
            # undo_last_feature() returns True on success
            assert result is True

    def test_main_reset_command_with_force(self, progress_file):
        """Should handle reset command."""
        with patch("sys.argv", ["progress_manager.py", "reset", "--force"]):
            result = progress_manager.main()
            # reset_tracking() returns True on success
            assert result is True


class TestAiMetricsAndCheckpoints:
    """Test AI metrics persistence and lightweight checkpoint behavior."""

    def test_set_feature_ai_metrics_records_fields(self, progress_file):
        """Should write complexity/model/workflow metrics to feature."""
        result = progress_manager.set_feature_ai_metrics(
            2, 18, "sonnet", "plan_execute"
        )
        assert result is True

        data = progress_manager.load_progress_json()
        feature = next(f for f in data["features"] if f["id"] == 2)
        metrics = feature["ai_metrics"]
        assert metrics["complexity_score"] == 18
        assert metrics["complexity_bucket"] == "standard"
        assert metrics["selected_model"] == "sonnet"
        assert metrics["workflow_path"] == "plan_execute"
        assert "started_at" in metrics

    def test_complete_feature_ai_metrics_sets_duration(self, progress_file):
        """Should finalize finished_at and duration_seconds."""
        progress_manager.set_feature_ai_metrics(2, 12, "haiku", "direct_tdd")
        result = progress_manager.complete_feature_ai_metrics(2)
        assert result is True

        data = progress_manager.load_progress_json()
        feature = next(f for f in data["features"] if f["id"] == 2)
        metrics = feature["ai_metrics"]
        assert "finished_at" in metrics
        assert "duration_seconds" in metrics
        assert metrics["duration_seconds"] >= 0

    def test_auto_checkpoint_creates_snapshot(self, in_progress_file):
        """Should create checkpoints.json with current workflow snapshot."""
        result = progress_manager.auto_checkpoint()
        assert result is True

        checkpoints_path = Path(".claude/checkpoints.json")
        assert checkpoints_path.exists()
        payload = json.loads(checkpoints_path.read_text())
        assert payload["max_entries"] == 50
        assert len(payload["entries"]) == 1
        assert payload["entries"][0]["feature_id"] == 2
        assert payload["entries"][0]["reason"] == "auto_interval"

    def test_auto_checkpoint_respects_interval(self, in_progress_file):
        """Should avoid duplicate snapshots within the checkpoint interval."""
        assert progress_manager.auto_checkpoint() is True
        assert progress_manager.auto_checkpoint() is True

        checkpoints_path = Path(".claude/checkpoints.json")
        payload = json.loads(checkpoints_path.read_text())
        assert len(payload["entries"]) == 1

    def test_add_bug_with_technical_debt_category(self, progress_file):
        """Should support technical_debt category on bug creation."""
        result = progress_manager.add_bug(
            description="Hard-coded endpoint",
            priority="medium",
            category="technical_debt",
        )
        assert result is True

        data = progress_manager.load_progress_json()
        bugs = data.get("bugs", [])
        assert len(bugs) == 1
        assert bugs[0]["category"] == "technical_debt"

    def test_main_set_feature_ai_metrics_command(self, progress_file):
        """Should handle set-feature-ai-metrics command."""
        with patch(
            "sys.argv",
            [
                "progress_manager.py",
                "set-feature-ai-metrics",
                "2",
                "--complexity-score",
                "10",
                "--selected-model",
                "haiku",
                "--workflow-path",
                "direct_tdd",
            ],
        ):
            result = progress_manager.main()
            assert result is True

    def test_main_auto_checkpoint_command(self, in_progress_file):
        """Should handle auto-checkpoint command."""
        with patch("sys.argv", ["progress_manager.py", "auto-checkpoint"]):
            result = progress_manager.main()
            assert result is True
