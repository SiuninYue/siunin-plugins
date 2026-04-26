"""
Tests for summary refresh best-effort in _notify_parent_sync.

Task 7: load_status_summary_projection refresh failure must not abort child operation.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_progress(root: Path, payload: dict) -> None:
    """Write a progress.json under <root>/docs/progress-tracker/state/."""
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _notify_parent_sync summary refresh tests
# ---------------------------------------------------------------------------


class TestSummaryWriteback:
    """Test that _notify_parent_sync attempts summary refresh best-effort."""

    def test_summary_refresh_attempted(self, tmp_path, monkeypatch):
        """_notify_parent_sync calls load_status_summary_projection on child."""
        child = tmp_path / "child"
        child.mkdir()
        parent = tmp_path / "parent"
        parent.mkdir()

        progress_manager._PROJECT_ROOT_OVERRIDE = child
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(child))

        # Child tracker with parent reference
        child_data = {
            "schema_version": progress_manager.CURRENT_SCHEMA_VERSION,
            "project_name": "Child",
            "tracker_role": "child",
            "parent_project_root": str(parent),
            "features": [],
        }
        _write_progress(child, child_data)

        # Parent tracker
        parent_data = {
            "schema_version": progress_manager.CURRENT_SCHEMA_VERSION,
            "project_name": "Parent",
            "tracker_role": "parent",
            "linked_projects": [
                {"project_code": "CH", "project_root": str(child)},
            ],
            "active_routes": [],
        }
        _write_progress(parent, parent_data)

        refresh_called = False
        original_loader = progress_manager.load_status_summary_projection

        def _spy_loader(project_root=None):
            nonlocal refresh_called
            refresh_called = True
            return original_loader(project_root)

        with patch.object(progress_manager, "load_status_summary_projection", _spy_loader):
            progress_manager._notify_parent_sync()

        assert refresh_called is True

    def test_summary_refresh_failure_does_not_abort(self, tmp_path, monkeypatch, capsys):
        """Summary refresh failure is logged but parent writeback still succeeds."""
        child = tmp_path / "child"
        child.mkdir()
        parent = tmp_path / "parent"
        parent.mkdir()

        progress_manager._PROJECT_ROOT_OVERRIDE = child
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(child))

        child_data = {
            "schema_version": progress_manager.CURRENT_SCHEMA_VERSION,
            "project_name": "Child",
            "tracker_role": "child",
            "parent_project_root": str(parent),
            "features": [],
        }
        _write_progress(child, child_data)

        parent_data = {
            "schema_version": progress_manager.CURRENT_SCHEMA_VERSION,
            "project_name": "Parent",
            "tracker_role": "parent",
            "linked_projects": [
                {"project_code": "CH", "project_root": str(child)},
            ],
            "active_routes": [],
        }
        _write_progress(parent, parent_data)

        def _broken_loader(project_root=None):
            raise RuntimeError("simulated summary failure")

        with patch.object(progress_manager, "load_status_summary_projection", _broken_loader):
            progress_manager._notify_parent_sync()

        # Parent writeback should still have happened
        saved_parent = progress_manager._load_progress_payload_at_root(parent)[0]
        assert saved_parent is not None
        assert "linked_snapshot" in saved_parent
        assert saved_parent["linked_snapshot"]["projects"][0]["project_code"] == "CH"
