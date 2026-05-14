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
        assert "progress.md" in progress_manager.STATE_FILE_NAMES
        assert "checkpoints.json" in progress_manager.STATE_FILE_NAMES
        assert "audit.log" in progress_manager.STATE_FILE_NAMES
        assert "project_memory.json" in progress_manager.STATE_FILE_NAMES
        assert "sprint_ledger.jsonl" in progress_manager.STATE_FILE_NAMES

    def test_state_file_names_excludes_lock(self):
        assert "progress.lock" not in progress_manager.STATE_FILE_NAMES

    def test_state_dir_names_contains_required_dirs(self):
        assert "test_reports" in progress_manager.STATE_DIR_NAMES
        assert "progress_archive" in progress_manager.STATE_DIR_NAMES


class TestGetDirtyStateFiles:
    def test_detects_modified_tracked_file(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
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
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "audit.log").write_text("new audit entry\n")

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("audit.log" in str(f) for f in dirty)

    def test_excludes_progress_lock(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "progress.lock").write_text("pid=12345")

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert all("progress.lock" not in str(f) for f in dirty)

    def test_returns_empty_when_state_is_clean(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert dirty == []

    def test_detects_new_file_in_test_reports_dir(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
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
        progress_manager.configure_project_scope(str(mock_git_repo))
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
        progress_manager.configure_project_scope(str(mock_git_repo))
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
        progress_manager.configure_project_scope(str(mock_git_repo))
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
        progress_manager.configure_project_scope(str(mock_git_repo))
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
        progress_manager.configure_project_scope(str(mock_git_repo))
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
