"""Tests for _auto_state_commit and supporting functions."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import sys

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


class TestStateFileConstants:
    def test_state_file_names_contains_required_files(self):
        assert "progress.json" in progress_manager.STATE_FILE_NAMES
        assert "checkpoints.json" in progress_manager.STATE_FILE_NAMES
        assert "audit.log" in progress_manager.STATE_FILE_NAMES
        assert "project_memory.json" in progress_manager.STATE_FILE_NAMES
        assert "sprint_ledger.jsonl" in progress_manager.STATE_FILE_NAMES

    def test_state_file_names_excludes_generated_progress_md(self):
        assert "progress.md" not in progress_manager.STATE_FILE_NAMES

    def test_state_file_names_excludes_lock(self):
        assert "progress.lock" not in progress_manager.STATE_FILE_NAMES

    def test_state_dir_names_contains_required_dirs(self):
        assert "test_reports" in progress_manager.STATE_DIR_NAMES
        assert "progress_archive" in progress_manager.STATE_DIR_NAMES


class TestGetDirtyStateFiles:
    def test_detects_modified_tracked_file(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        data = json.loads(progress_json.read_text())
        data["_dirty_marker"] = True
        progress_json.write_text(json.dumps(data))

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("progress.json" in str(f) for f in dirty)

    def test_detects_untracked_new_state_file(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "audit.log").write_text("new audit entry\n")

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("audit.log" in str(f) for f in dirty)

    def test_excludes_progress_lock(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "progress.lock").write_text("pid=12345")

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert all("progress.lock" not in str(f) for f in dirty)

    def test_excludes_generated_progress_md(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "progress.md").write_text("# local mirror\n", encoding="utf-8")

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert all("progress.md" not in str(f) for f in dirty)

    def test_returns_empty_when_state_is_clean(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert dirty == []

    def test_detects_new_file_in_test_reports_dir(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        test_reports = state_dir / "test_reports"
        test_reports.mkdir(exist_ok=True)
        (test_reports / "report-f1.json").write_text('{"result": "pass"}')

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("report-f1.json" in str(f) for f in dirty)

    def test_detects_deleted_tracked_state_file(self, mock_git_repo):
        """Deleted tracked state files must appear in dirty list (valid state change)."""
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "audit.log").write_text("entry\n")
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        # Delete a tracked state file
        (state_dir / "audit.log").unlink()

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("audit.log" in str(f) for f in dirty)


class TestGitCommitState:
    def test_creates_commit_for_modified_state_file(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        data = json.loads(progress_json.read_text())
        data["_test"] = True
        progress_json.write_text(json.dumps(data))

        result = progress_manager._git_commit_state(
            [progress_json],
            "chore(PT): state sync [F1: done] [skip ci]",
            mock_git_repo,
        )

        assert result is not None
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert "state sync [F1: done]" in log

    def test_commits_untracked_new_file(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        audit_log = state_dir / "audit.log"
        audit_log.write_text("event1\n")

        result = progress_manager._git_commit_state(
            [audit_log],
            "chore(PT): state sync [F1: done] [skip ci]",
            mock_git_repo,
        )

        assert result is not None
        show = subprocess.run(
            ["git", "show", "--name-only", "--format=", "HEAD"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert "audit.log" in show

    def test_does_not_include_user_staged_files(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        # User stages a non-state file
        user_file = mock_git_repo / "my_code.py"
        user_file.write_text("# user code")
        subprocess.run(["git", "add", "my_code.py"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        data = json.loads(progress_json.read_text())
        data["_test"] = True
        progress_json.write_text(json.dumps(data))

        progress_manager._git_commit_state(
            [progress_json],
            "chore(PT): state sync [F1: done] [skip ci]",
            mock_git_repo,
        )

        # my_code.py should still be staged (not committed)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert "my_code.py" in status

    def test_returns_none_when_nothing_to_commit(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        # File is clean — no changes

        result = progress_manager._git_commit_state(
            [progress_json],
            "chore(PT): state sync [F1: done] [skip ci]",
            mock_git_repo,
        )
        assert result is None


class TestAutoStateCommit:
    def test_returns_none_when_config_disabled(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        data = progress_manager.load_progress_json()
        data["settings"] = {"auto_state_commit": False}
        progress_manager.save_progress_json(data)

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is None

    def test_returns_none_during_merge(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        (mock_git_repo / ".git" / "MERGE_HEAD").write_text("deadbeef")

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is None
        (mock_git_repo / ".git" / "MERGE_HEAD").unlink()

    def test_returns_none_during_rebase(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        rebase_dir = mock_git_repo / ".git" / "rebase-merge"
        rebase_dir.mkdir()

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is None
        rebase_dir.rmdir()

    def test_returns_none_when_no_dirty_files(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is None

    def test_creates_commit_with_correct_message(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        # Dirty state
        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        data = json.loads(progress_json.read_text())
        data["_test"] = True
        progress_json.write_text(json.dumps(data))

        result = progress_manager._auto_state_commit("F3", "done")

        assert result is not None
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert "chore(PT): state sync [F3: done] [skip ci]" in log

    def test_defaults_to_enabled_when_settings_key_absent(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        # Remove settings key entirely (old project without settings)
        data = progress_manager.load_progress_json()
        data.pop("settings", None)
        progress_manager.save_progress_json(data)

        # Dirty state
        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        pdata = json.loads(progress_json.read_text())
        pdata["_test"] = True
        progress_json.write_text(json.dumps(pdata))

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is not None  # enabled by default


class TestInitTrackingSettings:
    def test_init_tracking_writes_auto_state_commit_true(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test Project", force=True)

        data = progress_manager.load_progress_json()
        assert data.get("settings", {}).get("auto_state_commit") is True


class TestCallSiteCmdDone:
    """Use seeded-JSON strategy: quality gates must be in progress.json because
    cmd_done() reads them directly (lines 8327-8366), not via patchable functions."""

    _FEATURE_ID = 1

    def _seed_gated_env(self, tmp_path: Path) -> None:
        """Write fully-gated progress.json + plan document into tmp_path."""
        plan_path = f"docs/plans/2026-01-01-feature-{self._FEATURE_ID}.md"
        plan_abs = tmp_path / plan_path
        plan_abs.parent.mkdir(parents=True, exist_ok=True)
        plan_abs.write_text(
            "# Feature Plan\n\n## Tasks\n\n- [ ] step\n\n"
            "## Acceptance Mapping\n\n- passes\n\n## Risks\n\n- none\n",
            encoding="utf-8",
        )
        feature = {
            "id": self._FEATURE_ID,
            "name": "Test Feature",
            "completed": False,
            "deferred": False,
            "lifecycle_state": "implementing",
            "development_stage": "developing",
            "change_spec": {"why": "test", "in_scope": [], "out_of_scope": [], "risks": []},
            "requirement_ids": ["REQ-001"],
            "acceptance_scenarios": [],
            "acceptance_criteria": [],
            "integration_status": None,
            "quality_gates": {
                "evaluator": {
                    "status": "pass", "score": 100, "defects": [],
                    "last_run_at": "2026-01-01T00:00:00Z", "evaluator_model": None,
                },
                "ship_check": {
                    "status": "pass", "failures": [],
                    "last_run_at": "2026-01-01T00:00:00Z",
                },
                "reviews": {"required": ["eng"], "passed": ["eng"], "pending": []},
            },
            "sprint_contract": {
                "scope": "test", "done_criteria": ["passes"],
                "test_plan": ["pytest"], "accepted_by": "test",
                "accepted_at": "2026-01-01T00:00:00Z",
            },
            "handoff": {
                "from_phase": None, "to_phase": None,
                "artifact_path": None, "created_at": None,
            },
        }
        data = {
            "schema_version": "2.1",
            "project_name": "test",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "features": [feature],
            "current_feature_id": self._FEATURE_ID,
            "updates": [], "retrospectives": [], "runtime_context": {},
            "linked_projects": [], "linked_snapshot": {},
            "tracker_role": "standalone", "project_code": None,
            "routing_queue": [], "active_routes": [],
            "bugs": [], "current_bug_id": None,
            "workflow_state": {
                "phase": "execution_complete", "plan_path": plan_path
            },
            "settings": {"auto_state_commit": True},
        }
        state_dir = tmp_path / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "progress.json").write_text(json.dumps(data))

    def test_cmd_done_calls_auto_state_commit(self, tmp_path):
        """_auto_state_commit is called with F<id> after cmd_done clears all gates."""
        self._seed_gated_env(tmp_path)
        worktree_ctx = {
            "branch": "feature/test", "workspace_mode": "direct", "worktree_path": None
        }

        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", tmp_path),
            patch("progress_manager.require_sprint_contract", return_value=None),
            patch("progress_manager._run_acceptance_tests", return_value=(True, [])),
            patch("progress_manager._save_done_test_report", return_value=None),
            patch("progress_manager.record_sprint_artifact", return_value=None),
            patch("progress_manager._notify_parent_sync", return_value=None),
            patch("progress_manager._run_post_done_cleanup"),
            patch("progress_manager.collect_git_context", return_value=worktree_ctx),
            patch.object(progress_manager, "_auto_state_commit") as mock_asc,
        ):
            progress_manager.cmd_done()

        mock_asc.assert_called_once_with(f"F{self._FEATURE_ID}", "done")


class TestCallSiteSetCurrent:
    def test_set_current_calls_auto_state_commit(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        progress_manager.add_feature("Feature 1", ["step 1"])

        with patch.object(progress_manager, "_auto_state_commit") as mock_asc:
            progress_manager.set_current(1)

        mock_asc.assert_called_once_with("F1", "start")


class TestCallSiteUpdateBug:
    def _add_bug_and_get_id(self) -> str:
        """Helper: add a bug and return its auto-generated ID (e.g. 'BUG-001')."""
        progress_manager.add_bug(description="Something broken", priority="medium")
        data = progress_manager.load_progress_json()
        return data["bugs"][-1]["id"]

    def test_update_bug_calls_auto_state_commit_when_fixed(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        bug_id = self._add_bug_and_get_id()

        with patch.object(progress_manager, "_auto_state_commit") as mock_asc:
            progress_manager.update_bug(bug_id, status="fixed",
                                        fix_summary="Fixed the thing")

        mock_asc.assert_called_once_with(bug_id, "fix")

    def test_update_bug_does_not_call_auto_state_commit_for_other_statuses(
        self, mock_git_repo
    ):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        bug_id = self._add_bug_and_get_id()

        with patch.object(progress_manager, "_auto_state_commit") as mock_asc:
            progress_manager.update_bug(bug_id, status="investigating")

        mock_asc.assert_not_called()
