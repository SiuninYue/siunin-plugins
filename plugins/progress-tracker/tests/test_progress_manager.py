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

    def test_find_project_root_in_plugin_subtree(self, temp_dir):
        """Should auto-detect target plugin root when running under plugins/<name>/..."""
        os.system(f"git -C {temp_dir} init >/dev/null 2>&1")
        plugin_src = temp_dir / "plugins" / "note-organizer" / "src"
        plugin_src.mkdir(parents=True)

        os.chdir(plugin_src)
        root = progress_manager.find_project_root()
        assert root == temp_dir / "plugins" / "note-organizer"

    def test_find_project_root_fallback_to_cwd(self, temp_dir):
        """Should fallback to current working directory."""
        root = progress_manager.find_project_root()
        assert root == temp_dir

    def test_configure_project_scope_accepts_explicit_project_root(self, temp_dir):
        """Should accept explicit --project-root in monorepo root."""
        os.system(f"git -C {temp_dir} init >/dev/null 2>&1")
        plugin_root = temp_dir / "plugins" / "note-organizer"
        plugin_root.mkdir(parents=True)
        os.chdir(temp_dir)

        assert progress_manager.configure_project_scope("plugins/note-organizer") is True
        assert progress_manager.find_project_root() == plugin_root

    def test_configure_project_scope_requires_explicit_scope_in_monorepo_root(self, temp_dir):
        """Should fail in monorepo root when --project-root is omitted."""
        os.system(f"git -C {temp_dir} init >/dev/null 2>&1")
        (temp_dir / "plugins" / "note-organizer").mkdir(parents=True)
        os.chdir(temp_dir)

        assert progress_manager.configure_project_scope(None) is False


class TestProgressInit:
    """Test progress tracking initialization."""

    def test_init_tracking_new_project(self, temp_dir):
        """Should initialize new project tracking."""
        result = progress_manager.init_tracking("Test Project", force=True)
        assert result is True

        progress_file = temp_dir / "docs" / "progress-tracker" / "state" / "progress.json"
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

        history = progress_manager._load_progress_history()
        assert len(history) == 1
        assert history[0]["reason"] == "reinitialize"
        assert history[0]["project_name"] == "Test Project"

        archive_json = Path("docs/progress-tracker/state") / history[0]["progress_json"]
        assert archive_json.exists()

    def test_init_creates_progress_md(self, temp_dir):
        """Should create progress.md file."""
        progress_manager.init_tracking("Test Project", force=True)

        md_file = temp_dir / "docs" / "progress-tracker" / "state" / "progress.md"
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

        progress_file = temp_dir / "docs" / "progress-tracker" / "state" / "progress.json"
        assert progress_file.exists()

        loaded = json.loads(progress_file.read_text())
        assert loaded["project_name"] == "Save Test"


class TestContextComparison:
    """Test execution/runtime context comparison semantics."""

    def test_compare_contexts_missing_current_branch_returns_unknown(self):
        """Missing current branch should not be treated as a match when expected branch exists."""
        expected = {"branch": "feature/demo", "worktree_path": "/tmp/worktree-a"}
        current = {"branch": None, "worktree_path": "/tmp/worktree-a"}

        hint = progress_manager.compare_contexts(expected, current)

        assert hint["status"] == "unknown"
        assert hint["severity"] == "warning"
        assert "branch" in hint["message"].lower()


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
        assert feature["development_stage"] == "completed"
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
        feature = [f for f in data["features"] if f["id"] == 2][0]
        assert feature["development_stage"] == "planning"

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


class TestDevelopmentStage:
    """Test development_stage read/write helpers."""

    def test_set_development_stage_for_current_feature(self, in_progress_file):
        """Should set stage for active feature and stamp started_at when developing."""
        result = progress_manager.set_development_stage("developing")
        assert result is True

        data = progress_manager.load_progress_json()
        feature = [f for f in data["features"] if f["id"] == data["current_feature_id"]][0]
        assert feature["development_stage"] == "developing"
        assert "started_at" in feature

    def test_set_development_stage_without_active_feature_fails(self, progress_file):
        """Should fail when no current feature is active."""
        result = progress_manager.set_development_stage("developing")
        assert result is False


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

        md_file = temp_dir / "docs" / "progress-tracker" / "state" / "progress.md"
        assert md_file.read_text() == "# Test Content"


class TestReset:
    """Test reset functionality."""

    def test_reset_removes_tracking(self, progress_file):
        """Should remove active progress files and keep archive metadata."""
        result = progress_manager.reset_tracking(force=True)
        assert result is True

        claude_dir = progress_file.parent
        assert claude_dir.exists()
        assert not (claude_dir / "progress.json").exists()
        assert not (claude_dir / "progress.md").exists()
        assert (claude_dir / "progress_history.json").exists()

    def test_reset_without_tracking(self, temp_dir):
        """Should handle gracefully when no tracking exists."""
        result = progress_manager.reset_tracking(force=True)
        assert result is True

    def test_reset_preserves_non_tracking_docs_files(self, temp_dir):
        """Reset should not remove unrelated docs/progress-tracker files."""
        progress_manager.init_tracking("Reset Preserve Test", force=True)
        architecture_file = (
            temp_dir
            / "docs"
            / "progress-tracker"
            / "architecture"
            / "architecture.md"
        )
        architecture_file.parent.mkdir(parents=True, exist_ok=True)
        architecture_file.write_text("# Architecture", encoding="utf-8")

        result = progress_manager.reset_tracking(force=True)
        assert result is True
        assert architecture_file.exists()


class TestProgressArchiveRestore:
    """Test archive listing and restore workflow."""

    def test_restore_archive_recovers_previous_progress(self, temp_dir):
        """Should restore archived progress snapshot as active progress."""
        progress_manager.init_tracking("Old Project", force=True)
        progress_manager.add_feature("Old Feature", ["step-1"])

        progress_manager.init_tracking("New Project", force=True)
        history = progress_manager._load_progress_history()
        assert history
        archive_id = history[-1]["archive_id"]

        restored = progress_manager.restore_archive(archive_id, force=True)
        assert restored is True

        data = progress_manager.load_progress_json()
        assert data["project_name"] == "Old Project"
        assert len(data["features"]) == 1

    def test_restore_archive_requires_force_when_active_exists(self, temp_dir):
        """Should refuse restore when active progress exists without --force."""
        progress_manager.init_tracking("Old Project", force=True)
        progress_manager.init_tracking("New Project", force=True)
        archive_id = progress_manager._load_progress_history()[-1]["archive_id"]

        restored = progress_manager.restore_archive(archive_id, force=False)
        assert restored is False


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

    def test_git_auto_preflight_requires_worktree_on_default_branch(self):
        """Should require worktree for default branch feature work in-place."""
        fake_context = {
            "project_root": "/tmp/repo",
            "workspace_mode": "in_place",
            "branch": "main",
        }
        fake_sync = {
            "status": "warning",
            "project_root": "/tmp/repo",
            "issues": [
                {
                    "id": "dirty_worktree",
                    "level": "warning",
                    "message": "Working tree has uncommitted changes.",
                }
            ],
        }
        with patch("progress_manager.collect_git_context", return_value=fake_context), patch(
            "progress_manager.analyze_git_sync_risks", return_value=fake_sync
        ), patch("progress_manager._detect_default_branch", return_value="main"):
            report = progress_manager.analyze_git_auto_preflight()

        assert report["decision"] == "REQUIRE_WORKTREE"
        assert "default_branch_feature_work" in report["reason_codes"]
        assert "dirty_on_default_branch" in report["reason_codes"]
        assert report["default_branch"] == "main"

    def test_git_auto_preflight_delegates_on_worktree_conflict(self):
        """Should delegate to git-auto when branch is checked out elsewhere."""
        fake_context = {
            "project_root": "/tmp/repo",
            "workspace_mode": "in_place",
            "branch": "feature/demo",
        }
        fake_sync = {
            "status": "warning",
            "project_root": "/tmp/repo",
            "issues": [
                {
                    "id": "branch_checked_out_elsewhere",
                    "level": "warning",
                    "message": "Branch is checked out in another worktree.",
                }
            ],
        }
        with patch("progress_manager.collect_git_context", return_value=fake_context), patch(
            "progress_manager.analyze_git_sync_risks", return_value=fake_sync
        ), patch("progress_manager._detect_default_branch", return_value="main"):
            report = progress_manager.analyze_git_auto_preflight()

        assert report["decision"] == "DELEGATE_GIT_AUTO"
        assert "branch_checked_out_elsewhere" in report["reason_codes"]

    def test_git_auto_preflight_allows_in_place_on_clean_feature_branch(self):
        """Should allow in-place execution when no blocking risk exists."""
        fake_context = {
            "project_root": "/tmp/repo",
            "workspace_mode": "in_place",
            "branch": "feature/demo",
        }
        fake_sync = {
            "status": "ok",
            "project_root": "/tmp/repo",
            "issues": [],
        }
        with patch("progress_manager.collect_git_context", return_value=fake_context), patch(
            "progress_manager.analyze_git_sync_risks", return_value=fake_sync
        ), patch("progress_manager._detect_default_branch", return_value="main"):
            report = progress_manager.analyze_git_auto_preflight()

        assert report["decision"] == "ALLOW_IN_PLACE"
        assert report["reason_codes"] == ["no_blocking_workspace_risk"]

    def test_git_auto_preflight_json_contract(self, capsys):
        """Should emit stable JSON contract fields for machine consumers."""
        fake_report = {
            "status": "warning",
            "workspace_mode": "in_place",
            "branch": "main",
            "issues": [],
            "decision": "REQUIRE_WORKTREE",
            "reason_codes": ["default_branch_feature_work"],
            "default_branch": "main",
            "project_root": "/tmp/repo",
        }
        with patch("progress_manager.analyze_git_auto_preflight", return_value=fake_report):
            result = progress_manager.git_auto_preflight(output_json=True)
            assert result is True

        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "warning"
        assert payload["workspace_mode"] == "in_place"
        assert payload["branch"] == "main"
        assert payload["decision"] == "REQUIRE_WORKTREE"
        assert payload["reason_codes"] == ["default_branch_feature_work"]
        assert payload["default_branch"] == "main"


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
        """Should return docs/progress-tracker/state path."""
        progress_dir = progress_manager.get_progress_dir()
        assert progress_dir is not None
        assert str(progress_dir).endswith("docs/progress-tracker/state")


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

    def test_validate_plan_path_accepts_docs_plans(self):
        """Should accept docs/progress-tracker/plans markdown paths."""
        result = progress_manager.validate_plan_path("docs/plans/feature-1-test.md")
        assert result["valid"] is True
        assert result["normalized_path"] == "docs/plans/feature-1-test.md"

    def test_validate_plan_path_rejects_non_standard_paths(self):
        """Should reject plan paths outside docs/plans/ or docs/progress-tracker/plans/ (legacy)."""
        result = progress_manager.validate_plan_path("some/other/path/plan.md")
        assert result["valid"] is False
        result2 = progress_manager.validate_plan_path("docs/notes/plan.md")
        assert result2["valid"] is False

    def test_set_workflow_state_execution_requires_existing_plan(self, in_progress_file):
        """Should fail if execution phase references a missing plan file."""
        result = progress_manager.set_workflow_state(
            phase="execution", plan_path="docs/plans/missing.md"
        )
        assert result is False

    def test_validate_plan_uses_workflow_state_plan(self, in_progress_file):
        """Should validate plan using workflow_state plan_path by default."""
        result = progress_manager.validate_plan()
        assert result is True

    def test_validate_plan_document_accepts_superpowers_template(self, temp_dir):
        """Should accept superpowers writing-plans format with advisory warnings."""
        plans_dir = Path("docs/plans")
        plans_dir.mkdir(parents=True, exist_ok=True)
        (plans_dir / "sp-plan.md").write_text(
            "# Feature Implementation Plan\n\n"
            "> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.\n\n"
            "**Goal:** Build the registration endpoint\n\n"
            "**Architecture:** Keep service and route layers separated\n\n"
            "**Tech Stack:** Python + pytest\n\n"
            "---\n\n"
            "## Tasks\n"
            "- Task 1\n",
            encoding="utf-8",
        )

        result = progress_manager.validate_plan_document("docs/plans/sp-plan.md")

        assert result["valid"] is True
        assert result["profile"] == "superpowers"
        assert "acceptance_mapping" in result["missing_sections"]
        assert "risks" in result["missing_sections"]
        assert result["warnings"]

    def test_validate_plan_document_requires_tasks_even_for_superpowers_template(self, temp_dir):
        """Should reject plans missing tasks regardless of template style."""
        plans_dir = Path("docs/plans")
        plans_dir.mkdir(parents=True, exist_ok=True)
        (plans_dir / "invalid-plan.md").write_text(
            "# Feature Implementation Plan\n\n"
            "**Goal:** Build the registration endpoint\n\n"
            "**Architecture:** Keep service and route layers separated\n",
            encoding="utf-8",
        )

        result = progress_manager.validate_plan_document("docs/plans/invalid-plan.md")

        assert result["valid"] is False
        assert result["profile"] == "invalid"
        assert "tasks" in result["missing_sections"]


class TestJsonErrorHandling:
    """Test JSON parsing error handling."""

    def test_load_corrupted_progress_json(self, temp_dir, capsys):
        """Should handle corrupted progress.json gracefully."""
        state_dir = temp_dir / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True)
        progress_file = state_dir / "progress.json"
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

    def test_main_git_auto_preflight_command(self):
        """Should handle git-auto-preflight command with JSON flag."""
        with patch(
            "progress_manager.git_auto_preflight", return_value=True
        ) as mock_preflight, patch(
            "sys.argv",
            [
                "progress_manager.py",
                "--project-root",
                "plugins/progress-tracker",
                "git-auto-preflight",
                "--json",
            ],
        ):
            result = progress_manager.main()
            assert result is True
            mock_preflight.assert_called_once_with(output_json=True)

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

    def test_main_set_development_stage_command(self, in_progress_file):
        """Should handle set-development-stage command."""
        with patch("sys.argv", ["progress_manager.py", "set-development-stage", "developing"]):
            result = progress_manager.main()
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

    def test_main_sync_runtime_context_command(self, in_progress_file):
        """Should handle sync-runtime-context command."""
        fake_ctx = {
            "workspace_mode": "worktree",
            "worktree_path": "/tmp/demo-worktree",
            "project_root": "/tmp/demo-worktree",
            "cwd": "/tmp/demo-worktree",
            "git_dir": "/tmp/repo/.git/worktrees/demo",
            "branch": "feature/demo",
            "upstream": "origin/feature/demo",
        }
        with patch("progress_manager.collect_git_context", return_value=fake_ctx), patch(
            "sys.argv",
            ["progress_manager.py", "sync-runtime-context", "--quiet"],
        ):
            result = progress_manager.main()
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

        checkpoints_path = Path("docs/progress-tracker/state/checkpoints.json")
        assert checkpoints_path.exists()
        payload = json.loads(checkpoints_path.read_text())
        assert payload["max_entries"] == 50
        assert len(payload["entries"]) == 1
        assert payload["entries"][0]["feature_id"] == 2
        assert payload["entries"][0]["reason"] == "auto_interval"
        assert "branch" in payload["entries"][0]
        assert "worktree_path" in payload["entries"][0]
        assert "next_action" in payload["entries"][0]

    def test_auto_checkpoint_respects_interval(self, in_progress_file):
        """Should avoid duplicate snapshots within the checkpoint interval."""
        assert progress_manager.auto_checkpoint() is True
        assert progress_manager.auto_checkpoint() is True

        checkpoints_path = Path("docs/progress-tracker/state/checkpoints.json")
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

    def test_main_validate_plan_command(self, in_progress_file):
        """Should handle validate-plan command."""
        with patch("sys.argv", ["progress_manager.py", "validate-plan"]):
            result = progress_manager.main()
            assert result is True


class TestRuntimeContextSync:
    """Test runtime_context sync behavior and updated_at semantics."""

    def test_sync_runtime_context_no_tracking_is_non_blocking(self, temp_dir):
        """Should return success when progress tracking doesn't exist."""
        assert progress_manager.sync_runtime_context(quiet=True) is True

    def test_sync_runtime_context_writes_runtime_context(self, in_progress_file):
        """Should write runtime_context with git/worktree metadata."""
        fake_ctx = {
            "workspace_mode": "worktree",
            "worktree_path": "/tmp/feature-wt",
            "project_root": "/tmp/feature-wt",
            "cwd": "/tmp/feature-wt",
            "git_dir": "/tmp/repo/.git/worktrees/feature-wt",
            "branch": "feature/context",
            "upstream": "origin/feature/context",
        }
        with patch("progress_manager.collect_git_context", return_value=fake_ctx):
            assert progress_manager.sync_runtime_context(quiet=True) is True

        data = progress_manager.load_progress_json()
        runtime_context = data.get("runtime_context")
        assert runtime_context is not None
        assert runtime_context["branch"] == "feature/context"
        assert runtime_context["worktree_path"] == "/tmp/feature-wt"
        assert runtime_context["workflow_phase"] == "execution"

    def test_sync_runtime_context_does_not_touch_updated_at(self, in_progress_file):
        """Runtime-only sync should preserve top-level updated_at timestamp."""
        data = progress_manager.load_progress_json()
        data["updated_at"] = "2024-01-10T00:00:00Z"
        progress_manager.save_progress_json(data, touch_updated_at=False)
        before = progress_manager.load_progress_json()["updated_at"]

        fake_ctx = {
            "workspace_mode": "in_place",
            "worktree_path": "/tmp/project",
            "project_root": "/tmp/project",
            "cwd": "/tmp/project",
            "git_dir": "/tmp/project/.git",
            "branch": "feature/no-touch",
            "upstream": "origin/feature/no-touch",
        }
        with patch("progress_manager.collect_git_context", return_value=fake_ctx):
            assert progress_manager.sync_runtime_context(quiet=True) is True

        after_data = progress_manager.load_progress_json()
        assert after_data["updated_at"] == before

    def test_sync_runtime_context_noop_when_unchanged(self, in_progress_file):
        """Should skip rewriting runtime_context when fingerprint is unchanged."""
        fake_ctx = {
            "workspace_mode": "in_place",
            "worktree_path": "/tmp/project",
            "project_root": "/tmp/project",
            "cwd": "/tmp/project",
            "git_dir": "/tmp/project/.git",
            "branch": "feature/noop",
            "upstream": "origin/feature/noop",
        }
        with patch("progress_manager.collect_git_context", return_value=fake_ctx):
            assert progress_manager.sync_runtime_context(quiet=True) is True

        first = progress_manager.load_progress_json()["runtime_context"]["recorded_at"]

        with patch("progress_manager.collect_git_context", return_value=fake_ctx):
            assert progress_manager.sync_runtime_context(quiet=True) is True

        second = progress_manager.load_progress_json()["runtime_context"]["recorded_at"]
        assert second == first


class TestWorktreeDetection:
    """Test detection of incomplete work in other worktrees."""

    def test_check_other_worktrees_no_worktrees(self, temp_dir):
        """Should return empty list when no other worktrees exist."""
        with patch("progress_manager._run_git", return_value=(0, "", "")):
            result = progress_manager._check_other_worktrees_for_incomplete_work(str(temp_dir))
            assert result == []

    def test_check_other_worktrees_no_progress_files(self, temp_dir):
        """Should return empty list when worktrees exist but have no progress files."""
        worktree_output = "worktree /tmp/wt1\nHEAD abc123\nworktree /tmp/wt2\nHEAD def456\n"
        with patch("progress_manager._run_git", return_value=(0, worktree_output, "")):
            result = progress_manager._check_other_worktrees_for_incomplete_work(str(temp_dir))
            assert result == []

    def test_check_other_worktrees_with_complete_work(self, temp_dir):
        """Should skip worktrees where all features are completed."""
        # Create another worktree with completed progress
        wt_dir = temp_dir / "other_wt"
        wt_dir.mkdir()
        wt_state = wt_dir / "docs" / "progress-tracker" / "state"
        wt_state.mkdir(parents=True)

        progress_data = {
            "project_name": "Completed Project",
            "features": [
                {"id": 1, "name": "Feature 1", "completed": True},
                {"id": 2, "name": "Feature 2", "completed": True},
            ],
            "current_feature_id": None,
        }

        with open(wt_state / "progress.json", "w") as f:
            json.dump(progress_data, f)

        worktree_output = f"worktree {str(temp_dir)}\nHEAD abc123\nworktree {str(wt_dir)}\nHEAD def456\n"
        with patch("progress_manager._run_git", return_value=(0, worktree_output, "")):
            result = progress_manager._check_other_worktrees_for_incomplete_work(str(temp_dir))
            assert result == []

    def test_check_other_worktrees_with_incomplete_work(self, temp_dir):
        """Should detect worktrees with incomplete features."""
        # Create another worktree with incomplete progress
        wt_dir = temp_dir / "active_wt"
        wt_dir.mkdir()
        wt_state = wt_dir / "docs" / "progress-tracker" / "state"
        wt_state.mkdir(parents=True)

        progress_data = {
            "project_name": "Active Project",
            "features": [
                {"id": 1, "name": "Feature 1", "completed": True},
                {"id": 2, "name": "Feature 2", "completed": False},
            ],
            "current_feature_id": 2,
        }

        with open(wt_state / "progress.json", "w") as f:
            json.dump(progress_data, f)

        worktree_output = f"worktree {str(temp_dir)}\nHEAD abc123\nworktree {str(wt_dir)}\nHEAD def456\n"
        with patch("progress_manager._run_git", return_value=(0, worktree_output, "")):
            result = progress_manager._check_other_worktrees_for_incomplete_work(str(temp_dir))

        assert len(result) == 1
        assert result[0]["worktree_path"] == str(wt_dir)
        assert result[0]["project_name"] == "Active Project"
        assert result[0]["current_feature_id"] == 2
        assert result[0]["incomplete_count"] == 1
        assert result[0]["total_features"] == 2

    def test_check_other_worktrees_multiple_worktrees(self, temp_dir):
        """Should detect multiple worktrees with incomplete work."""
        # Create two worktrees with incomplete progress
        wt1_dir = temp_dir / "wt1"
        wt1_dir.mkdir()
        wt1_state = wt1_dir / "docs" / "progress-tracker" / "state"
        wt1_state.mkdir(parents=True)

        wt2_dir = temp_dir / "wt2"
        wt2_dir.mkdir()
        wt2_state = wt2_dir / "docs" / "progress-tracker" / "state"
        wt2_state.mkdir(parents=True)

        progress_data_1 = {
            "project_name": "Project 1",
            "features": [{"id": 1, "name": "F1", "completed": False}],
            "current_feature_id": 1,
        }

        progress_data_2 = {
            "project_name": "Project 2",
            "features": [{"id": 1, "name": "F1", "completed": True}, {"id": 2, "name": "F2", "completed": False}],
            "current_feature_id": 2,
        }

        with open(wt1_state / "progress.json", "w") as f:
            json.dump(progress_data_1, f)
        with open(wt2_state / "progress.json", "w") as f:
            json.dump(progress_data_2, f)

        worktree_output = f"worktree {str(temp_dir)}\nHEAD abc123\nworktree {str(wt1_dir)}\nHEAD def456\nworktree {str(wt2_dir)}\nHEAD ghi789\n"
        with patch("progress_manager._run_git", return_value=(0, worktree_output, "")):
            result = progress_manager._check_other_worktrees_for_incomplete_work(str(temp_dir))

        assert len(result) == 2

    def test_check_other_worktrees_skips_current(self, temp_dir):
        """Should skip the current worktree even if it has incomplete work."""
        # Current worktree has incomplete work
        progress_data = {
            "project_name": "Current Project",
            "features": [{"id": 1, "name": "F1", "completed": False}],
            "current_feature_id": 1,
        }

        state_dir = temp_dir / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        with open(state_dir / "progress.json", "w") as f:
            json.dump(progress_data, f)

        worktree_output = f"worktree {str(temp_dir)}\nHEAD abc123\n"
        with patch("progress_manager._run_git", return_value=(0, worktree_output, "")):
            result = progress_manager._check_other_worktrees_for_incomplete_work(str(temp_dir))

        # Should skip current worktree
        assert len(result) == 0

    def test_check_outputs_warning_for_other_worktrees(self, temp_dir, capsys):
        """Should output warning when other worktrees have incomplete work."""
        # Create another worktree with incomplete progress
        wt_dir = temp_dir / "active_wt"
        wt_dir.mkdir()
        wt_state = wt_dir / "docs" / "progress-tracker" / "state"
        wt_state.mkdir(parents=True)

        progress_data = {
            "project_name": "Active Project",
            "features": [{"id": 1, "name": "F1", "completed": False}],
            "current_feature_id": 1,
        }

        with open(wt_state / "progress.json", "w") as f:
            json.dump(progress_data, f)

        # Mock _run_git for worktree list and collect_git_context
        worktree_output = f"worktree {str(temp_dir)}\nHEAD abc123\nworktree {str(wt_dir)}\nHEAD def456\n"

        def mock_run_git(args, timeout=None, cwd=None):
            if "worktree" in args:
                return (0, worktree_output, "")
            # For other git commands, return empty/success
            return (0, "", "")

        with patch("progress_manager._run_git", side_effect=mock_run_git):
            with patch("progress_manager.find_project_root", return_value=temp_dir):
                # This should print warning
                result = progress_manager._check_other_worktrees_for_incomplete_work(str(temp_dir))
                assert len(result) == 1
                assert result[0]["project_name"] == "Active Project"
