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
