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

    def test_squash_merge_conflict_returns_failure(self, mock_git_repo):
        """Unit: merge --squash failure returns (False, error) without raising."""
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo

        def fake_run_git(args, cwd=None, timeout=5):
            if args[0] == "show-ref":
                return 0, "", ""  # branch exists
            if args[0] == "status":
                return 0, "", ""  # clean tree
            if args[0] == "checkout":
                return 0, "", ""
            if args[:2] == ["merge", "--squash"]:
                return 1, "", "CONFLICT (content): Merge conflict in foo.txt"
            return 0, "", ""

        with patch.object(progress_manager, "_run_git", side_effect=fake_run_git):
            ok, msg = progress_manager._git_squash_close_task(
                task_id="TASK-001",
                branch="task/TASK-001",
                project_root=mock_git_repo,
            )

        assert ok is False
        assert "squash" in msg.lower() or "merge" in msg.lower() or "conflict" in msg.lower()

    def test_branch_cleanup_failure_is_non_blocking(self, mock_git_repo):
        """Unit: branch deletion failure does not fail the squash-close operation."""
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo

        def fake_run_git(args, cwd=None, timeout=5):
            if args[0] == "rev-parse":
                return 0, "deadbeef" * 5, ""
            if args[0] == "branch" and "-D" in args:
                return 1, "", "error: branch not found"  # cleanup fails
            return 0, "", ""

        with patch.object(progress_manager, "_run_git", side_effect=fake_run_git):
            ok, commit_hash = progress_manager._git_squash_close_task(
                task_id="TASK-001",
                branch="task/TASK-001",
                project_root=mock_git_repo,
            )

        assert ok is True
        assert commit_hash  # operation succeeded despite branch deletion failure

    def test_commit_message_uses_task_scope_format(self, mock_git_repo):
        """Unit: commit message follows task(<id>): <description> format."""
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo

        commit_messages = []

        def fake_run_git(args, cwd=None, timeout=5):
            if args[0] == "commit":
                commit_messages.append(args[args.index("-m") + 1])
                return 0, "", ""
            if args[0] == "rev-parse":
                return 0, "abc123", ""
            return 0, "", ""

        with patch.object(progress_manager, "_run_git", side_effect=fake_run_git):
            progress_manager._git_squash_close_task(
                task_id="T42",
                branch="task/T42",
                project_root=mock_git_repo,
                task_name="implement login flow",
            )

        assert len(commit_messages) == 1
        assert commit_messages[0] == "task(T42): implement login flow"

    def test_commit_message_fallback_when_no_task_name(self, mock_git_repo):
        """Unit: fallback description used when task_name is None."""
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo

        commit_messages = []

        def fake_run_git(args, cwd=None, timeout=5):
            if args[0] == "commit":
                commit_messages.append(args[args.index("-m") + 1])
                return 0, "", ""
            if args[0] == "rev-parse":
                return 0, "abc123", ""
            return 0, "", ""

        with patch.object(progress_manager, "_run_git", side_effect=fake_run_git):
            progress_manager._git_squash_close_task(
                task_id="T42",
                branch="task/T42",
                project_root=mock_git_repo,
            )

        assert len(commit_messages) == 1
        assert commit_messages[0].startswith("task(T42):")
        assert "close standalone task" in commit_messages[0]


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


# ---------------------------------------------------------------------------
# Task 5: next --done CLI flag + lock exemption
# ---------------------------------------------------------------------------

class TestNextDoneCLI:
    def test_next_done_flag_closes_task_via_cli(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        progress_manager.add_task_item(description="task", parent_feature_id=fid)
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        result = subprocess.run(
            [
                "python3", str(SCRIPT_DIR / "progress_manager.py"),
                "--project-root", str(tmp_path),
                "next", "--done",
            ],
            capture_output=True, text=True,
            env={**__import__("os").environ, "PROGRESS_TRACKER_SKIP_REPO_CHECK": "1"},
        )

        assert result.returncode == 0

    def test_next_done_does_not_hold_mutating_lock(self, tmp_path):
        """next --done must not time out due to MUTATING_COMMANDS outer lock."""
        import time
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        progress_manager.add_task_item(description="task", parent_feature_id=fid)
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        start = time.monotonic()
        result = subprocess.run(
            [
                "python3", str(SCRIPT_DIR / "progress_manager.py"),
                "--project-root", str(tmp_path),
                "next", "--done",
            ],
            capture_output=True, text=True,
            timeout=5,
            env={**__import__("os").environ, "PROGRESS_TRACKER_SKIP_REPO_CHECK": "1"},
        )
        elapsed = time.monotonic() - start

        assert result.returncode == 0
        assert elapsed < 5.0


# ---------------------------------------------------------------------------
# Task 6: Ghost command protection + wf_state_machine fix
# ---------------------------------------------------------------------------

class TestGhostCommandProtection:
    def test_start_task_shows_did_you_mean(self):
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "progress_manager.py"), "start-task", "TASK-001"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        assert "next --done" in result.stderr or "next --done" in result.stdout

    def test_low_similarity_command_no_did_you_mean(self):
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "progress_manager.py"), "xyzfrobnicate"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        # Should NOT show "Did you mean" for a completely unrelated command
        combined = result.stdout + result.stderr
        assert "Did you mean" not in combined

    def test_typo_close_to_done_shows_suggestion(self):
        """Edit-distance fallback: 'dne' is distance 1 from 'done'."""
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "progress_manager.py"), "dne"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        combined = result.stdout + result.stderr
        assert "done" in combined

    def test_wf_state_machine_task_pending_action_is_not_start_task(self):
        """wf_state_machine must not reference the ghost command."""
        import wf_state_machine
        action = wf_state_machine._PHASE_ACTION_MAP.get("task:pending")
        assert action != "start_task", "ghost command 'start_task' still in state machine"
        assert action is not None, "task:pending must have an action mapping"


# ---------------------------------------------------------------------------
# Task 7: _get_stale_bugs() + status() stale bug warnings
# ---------------------------------------------------------------------------

class TestStaleBugs:
    def _make_bug(self, priority: str, days_old: int, status: str = "confirmed") -> dict:
        ts = (datetime.now(tz=timezone.utc) - timedelta(days=days_old)).isoformat()
        return {
            "id": f"BUG-{priority}-{days_old}d",
            "description": f"{priority} bug {days_old}d old",
            "priority": {"high": "high", "medium": "medium", "low": "low"}[priority],
            "status": status,
            "created_at": ts,
        }

    def test_get_stale_bugs_p0_threshold_3_days(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            self._make_bug("high", 4),   # P0, 4d > 3d => stale
            self._make_bug("high", 2),   # P0, 2d <= 3d => not stale
            self._make_bug("high", 3),   # P0, exactly 3d => NOT stale (strict >)
        ]
        progress_manager.save_progress_json(data)
        stale = progress_manager._get_stale_bugs(data, now)
        assert len(stale) == 1
        assert stale[0]["id"] == "BUG-high-4d"

    def test_get_stale_bugs_p1_threshold_7_days(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            self._make_bug("medium", 8),   # P1, 8d > 7d => stale
            self._make_bug("medium", 7),   # P1, exactly 7d => not stale
            self._make_bug("medium", 6),   # P1, 6d <= 7d => not stale
        ]
        progress_manager.save_progress_json(data)
        stale = progress_manager._get_stale_bugs(data, now)
        assert len(stale) == 1
        assert stale[0]["id"] == "BUG-medium-8d"

    def test_get_stale_bugs_excludes_terminal_status(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            self._make_bug("high", 10, status="fixed"),
            self._make_bug("high", 10, status="false_positive"),
            self._make_bug("high", 10, status="confirmed"),
        ]
        progress_manager.save_progress_json(data)
        stale = progress_manager._get_stale_bugs(data, now)
        ids = [b["id"] for b in stale]
        assert "BUG-high-10d" in ids
        assert len(stale) == 1  # only the "confirmed" one

    def test_get_stale_bugs_p0_before_p1_order(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            {"id": "BUG-P1", "description": "p1", "priority": "medium", "status": "confirmed",
             "created_at": (now - timedelta(days=10)).isoformat()},
            {"id": "BUG-P0", "description": "p0", "priority": "high", "status": "confirmed",
             "created_at": (now - timedelta(days=5)).isoformat()},
        ]
        progress_manager.save_progress_json(data)
        stale = progress_manager._get_stale_bugs(data, now)
        assert stale[0]["id"] == "BUG-P0"
        assert stale[1]["id"] == "BUG-P1"

    def test_status_shows_stale_bug_warnings(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            {"id": "BUG-001", "description": "critical stale bug", "priority": "high",
             "status": "confirmed",
             "created_at": (now - timedelta(days=5)).isoformat()},
        ]
        progress_manager.save_progress_json(data)
        progress_manager.status()
        out = capsys.readouterr().out
        assert "BUG-001" in out
        assert "Bug Warnings" in out or "P0" in out


# ---------------------------------------------------------------------------
# Task 8: status() hidden-history + list_updates() unlimited default
# ---------------------------------------------------------------------------

class TestStatusHiddenHistory:
    def _add_updates(self, tmp_path: Path, count: int) -> None:
        for i in range(count):
            progress_manager.add_update(
                category="status",
                summary=f"update {i + 1}",
            )

    def test_status_shows_plus_n_more_when_over_5_updates(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        self._add_updates(tmp_path, 12)
        capsys.readouterr()  # flush add_update output
        progress_manager.status()
        out = capsys.readouterr().out
        assert "+7 more" in out or "+7" in out

    def test_status_no_plus_n_when_5_or_fewer_updates(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        self._add_updates(tmp_path, 5)
        capsys.readouterr()  # flush add_update output
        progress_manager.status()
        out = capsys.readouterr().out
        assert "more" not in out or "+0" not in out

    def test_status_updates_sorted_by_created_at(self, tmp_path, capsys):
        """The 5 shown updates must be the 5 most recent."""
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        self._add_updates(tmp_path, 7)
        capsys.readouterr()  # flush add_update output
        progress_manager.status()
        out = capsys.readouterr().out
        assert "update 7" in out
        assert "update 3" in out
        assert "update 1" not in out
        assert "update 2" not in out


class TestListUpdatesUnlimited:
    def test_list_updates_default_returns_all(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        for i in range(15):
            progress_manager.add_update(category="status", summary=f"upd {i+1}")
        capsys.readouterr()  # flush add_update output
        progress_manager.list_updates()
        out = capsys.readouterr().out
        assert "upd 1" in out
        assert "upd 15" in out

    def test_list_updates_limit_positive_truncates(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        for i in range(10):
            progress_manager.add_update(category="status", summary=f"upd {i+1}")
        capsys.readouterr()  # flush add_update output
        progress_manager.list_updates(limit=3)
        out = capsys.readouterr().out
        assert "upd 10" in out
        assert "upd 1 " not in out and "upd 1\n" not in out and "upd 1[" not in out

    def test_list_updates_negative_limit_raises_or_returns_error(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        result = subprocess.run(
            [
                "python3", str(SCRIPT_DIR / "progress_manager.py"),
                "--project-root", str(tmp_path),
                "list-updates", "--limit", "-1",
            ],
            capture_output=True, text=True,
            env={**__import__("os").environ, "PROGRESS_TRACKER_SKIP_REPO_CHECK": "1"},
        )
        assert result.returncode == 2
