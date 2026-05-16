"""Tests for PT-F14: task execution semantics."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

import pytest
import sys

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _init_project(root: Path, name: str = "Test") -> None:
    # Bypass configure_project_scope's git check (tmp_path is outside the repo).
    progress_manager._PROJECT_ROOT_OVERRIDE = root
    progress_manager._STORAGE_READY_ROOT = None
    progress_manager.init_tracking(name, force=True)


def _add_feature(root: Path, name: str = "Feature A") -> int:
    """Add a feature and return its id."""
    progress_manager._PROJECT_ROOT_OVERRIDE = root
    data = progress_manager.load_progress_json()
    features = data.get("features", [])
    new_id = (max((f["id"] for f in features), default=0) + 1)
    features.append({
        "id": new_id, "name": name, "completed": False, "deferred": False,
        "lifecycle_state": "pending", "test_steps": [],
        "acceptance_criteria": [], "acceptance_scenarios": [],
        "ai_metrics": {}, "state": {"status": "pending"},
    })
    data["features"] = features
    progress_manager.save_progress_json(data)
    return new_id


# ---------------------------------------------------------------------------
# Task 1: add_task_item parent_feature_id + prog add-task CLI
# ---------------------------------------------------------------------------

class TestAddTaskParentFeatureId:
    def test_add_task_standalone_has_null_parent(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        task_id = progress_manager.add_task_item(description="do something")
        data = progress_manager.load_progress_json()
        task = next(t for t in data["tasks"] if t["id"] == task_id)
        assert task.get("parent_feature_id") is None

    def test_add_task_with_valid_feature_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        task_id = progress_manager.add_task_item(description="bounded", parent_feature_id=fid)
        data = progress_manager.load_progress_json()
        task = next(t for t in data["tasks"] if t["id"] == task_id)
        assert task["parent_feature_id"] == fid

    def test_add_task_invalid_feature_id_returns_none(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        result = progress_manager.add_task_item(description="bad", parent_feature_id=999)
        assert result is None

    def test_add_task_cli_add_task_subcommand_exists(self):
        """prog add-task must be a registered subcommand."""
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "progress_manager.py"), "add-task", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--description" in result.stdout

    def test_add_task_cli_feature_id_and_quick_task_profile_mutually_exclusive(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        result = subprocess.run(
            [
                "python3", str(SCRIPT_DIR / "progress_manager.py"),
                "--project-root", str(tmp_path),
                "add-task",
                "--description", "conflict",
                "--feature-id", str(fid),
                "--workflow-profile", "quick_task",
            ],
            capture_output=True, text=True,
            env={**__import__("os").environ, "PROGRESS_TRACKER_SKIP_REPO_CHECK": "1"},
        )
        assert result.returncode == 2

    def test_add_task_cli_nonexistent_feature_returns_rc1(self, tmp_path):
        _init_project(tmp_path)
        result = subprocess.run(
            [
                "python3", str(SCRIPT_DIR / "progress_manager.py"),
                "--project-root", str(tmp_path),
                "add-task",
                "--description", "bad ref",
                "--feature-id", "999",
            ],
            capture_output=True, text=True,
            env={**__import__("os").environ, "PROGRESS_TRACKER_SKIP_REPO_CHECK": "1"},
        )
        assert result.returncode == 1


# ---------------------------------------------------------------------------
# Task 2: next_feature() task activation — current_task_id + branch creation + ghost fix
# ---------------------------------------------------------------------------

class TestNextFeatureTaskActivation:
    def test_next_selects_task_sets_current_task_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="my task")
        progress_manager.next_feature()
        data = progress_manager.load_progress_json()
        assert data.get("current_task_id") == "TASK-001"

    def test_next_standalone_task_output_contains_next_done(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="my task")
        with patch.object(progress_manager, "_run_git", return_value=(0, "", "")):
            progress_manager.next_feature()
        out = capsys.readouterr().out
        assert "prog next --done" in out
        assert "start-task" not in out

    def test_next_standalone_task_creates_branch(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=mock_git_repo, capture_output=True)
        progress_manager.add_task_item(description="standalone")
        progress_manager.next_feature()
        result = subprocess.run(
            ["git", "branch", "--list", "task/TASK-001"],
            cwd=mock_git_repo, capture_output=True, text=True,
        )
        assert "task/TASK-001" in result.stdout

    def test_next_feature_bound_task_does_not_create_branch(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=mock_git_repo, capture_output=True)
        fid = _add_feature(mock_git_repo)
        progress_manager.add_task_item(description="bound", parent_feature_id=fid)
        progress_manager.next_feature()
        result = subprocess.run(
            ["git", "branch", "--list", "task/TASK-001"],
            cwd=mock_git_repo, capture_output=True, text=True,
        )
        assert result.stdout.strip() == ""

    def test_next_standalone_branch_fail_does_not_set_current_task_id(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=mock_git_repo, capture_output=True)
        progress_manager.add_task_item(description="standalone")
        # _run_git returns non-zero to simulate branch creation failure
        with patch.object(progress_manager, "_run_git", return_value=(1, "", "branch error")):
            progress_manager.next_feature()
        data = progress_manager.load_progress_json()
        assert data.get("current_task_id") is None


# ---------------------------------------------------------------------------
# Task 3: _git_squash_close_task() helper
# ---------------------------------------------------------------------------

class TestGitSquashCloseTask:
    def test_squash_close_succeeds_and_returns_commit_hash(self, mock_git_repo):
        """Unit: mock _run_git to verify call sequence."""
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo

        call_log = []
        def fake_run_git(args, cwd=None, timeout=5):
            call_log.append(args)
            if args[0] == "rev-parse":
                return 0, "abc123", ""
            return 0, "", ""

        with patch.object(progress_manager, "_run_git", side_effect=fake_run_git):
            ok, value = progress_manager._git_squash_close_task(
                task_id="TASK-001",
                branch="task/TASK-001",
                project_root=mock_git_repo,
            )

        assert ok is True
        assert value == "abc123"
        # Verify sequence: show-ref (branch check), status, checkout, merge --squash, commit, branch -d
        cmds = [c[0] for c in call_log]
        assert "checkout" in cmds
        assert "merge" in cmds
        assert "commit" in cmds
        assert "branch" in cmds

    def test_squash_close_fails_if_branch_missing(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo

        def fake_run_git(args, cwd=None, timeout=5):
            if args[0] == "show-ref":
                return 1, "", "not found"  # branch does not exist
            return 0, "", ""

        with patch.object(progress_manager, "_run_git", side_effect=fake_run_git):
            ok, msg = progress_manager._git_squash_close_task(
                task_id="TASK-001",
                branch="task/TASK-001",
                project_root=mock_git_repo,
            )

        assert ok is False
        assert "not found" in msg.lower() or "branch" in msg.lower()

    def test_squash_close_integration(self, mock_git_repo):
        """Integration: real git ops — verifies main+1 commit and branch deleted."""
        import subprocess
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=mock_git_repo, capture_output=True)

        # Get commit count on main before
        before = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout.strip()

        # Detect default branch dynamically (mock_git_repo fixture may use main or master)
        default_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout.strip() or "main"

        # Create a task branch with a commit, then return to default branch
        subprocess.run(["git", "checkout", "-b", "task/TASK-001"], cwd=mock_git_repo, capture_output=True)
        (mock_git_repo / "task_work.txt").write_text("some work")
        subprocess.run(["git", "add", "task_work.txt"], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "task work"], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "checkout", default_branch], cwd=mock_git_repo, capture_output=True)

        ok, commit_hash = progress_manager._git_squash_close_task(
            task_id="TASK-001",
            branch="task/TASK-001",
            project_root=mock_git_repo,
        )

        assert ok is True
        assert len(commit_hash) >= 7

        # main has exactly +1 commit
        after = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout.strip()
        assert int(after) == int(before) + 1

        # task branch is deleted
        branches = subprocess.run(
            ["git", "branch", "--list", "task/TASK-001"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert branches.strip() == ""


# ---------------------------------------------------------------------------
# Task 4: _close_current_task() + _close_standalone_task() + _close_feature_bound_task()
# ---------------------------------------------------------------------------

class TestCloseCurrentTask:
    def test_close_fails_rc1_when_no_current_task_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        rc = progress_manager._close_current_task()
        assert rc == 1

    def test_close_fails_rc1_when_current_task_id_points_to_missing_task(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-999"
        progress_manager.save_progress_json(data)
        rc = progress_manager._close_current_task()
        assert rc == 1

    def test_close_fails_rc1_when_task_already_completed(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="done already")
        data = progress_manager.load_progress_json()
        data["tasks"][0]["status"] = "completed"
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)
        rc = progress_manager._close_current_task()
        assert rc == 1

    def test_close_standalone_task_marks_completed_and_clears_current_task_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="standalone")
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        with patch.object(
            progress_manager, "_git_squash_close_task",
            return_value=(True, "deadbeef"),
        ):
            rc = progress_manager._close_current_task()

        assert rc == 0
        data = progress_manager.load_progress_json()
        task = data["tasks"][0]
        assert task["status"] == "completed"
        assert data.get("current_task_id") is None

    def test_close_standalone_git_failure_does_not_modify_state(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="standalone")
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        with patch.object(
            progress_manager, "_git_squash_close_task",
            return_value=(False, "merge conflict"),
        ):
            rc = progress_manager._close_current_task()

        assert rc == 1
        data = progress_manager.load_progress_json()
        assert data["tasks"][0]["status"] == "pending"  # unchanged
        assert data.get("current_task_id") == "TASK-001"  # unchanged

    def test_close_feature_bound_task_marks_completed_no_git(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        progress_manager.add_task_item(description="bounded", parent_feature_id=fid)
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        git_called = []
        with patch.object(
            progress_manager, "_git_squash_close_task",
            side_effect=lambda **kw: git_called.append(True) or (True, ""),
        ):
            rc = progress_manager._close_current_task()

        assert rc == 0
        assert git_called == []  # git must NOT be called for feature-bound
        data = progress_manager.load_progress_json()
        assert data["tasks"][0]["status"] == "completed"
        assert data.get("current_task_id") is None

    def test_close_feature_bound_task_does_not_auto_close_parent_feature(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        progress_manager.add_task_item(description="bounded", parent_feature_id=fid)
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        rc = progress_manager._close_current_task()

        data = progress_manager.load_progress_json()
        feature = next(f for f in data["features"] if f["id"] == fid)
        assert feature.get("completed") is not True
        assert feature.get("lifecycle_state") != "completed"

    def test_close_json_output_contract(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="task")
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        with patch.object(
            progress_manager, "_git_squash_close_task",
            return_value=(True, "abc123"),
        ):
            rc = progress_manager._close_current_task(output_json=True)

        out = capsys.readouterr().out
        payload = json.loads(out.strip().split("\n")[-1])
        assert "status" in payload
        assert "closed_task_id" in payload
        assert "message" in payload
        assert rc == 0
