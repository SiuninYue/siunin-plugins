"""Tests for _reset_active_progress: clearing active state on project completion."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log
import progress_manager as pm

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _write_progress, _write_audit_event


def _make_fully_completed_data():
    """Progress data where all features are completed."""
    return {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [
            {"id": 1, "name": "F1", "completed": True,
             "completed_at": "2026-01-02T00:00:00Z"},
            {"id": 2, "name": "F2", "completed": True,
             "completed_at": "2026-01-03T00:00:00Z"},
        ],
        "current_feature_id": None,
        "bugs": [{"id": "BUG-001", "description": "test bug", "status": "fixed"}],
        "updates": [{"id": "UPD-001", "summary": "test update"}],
        "retrospectives": [{"id": "RET-001", "summary": "test retro"}],
        "current_bug_id": "BUG-001",
        "workflow_state": {"phase": "execution_complete"},
        "runtime_context": {
            "current_feature_id": 2,
            "workflow_phase": "execution_complete",
            "current_task": None,
            "total_tasks": 3,
            "next_action": "run /prog done",
        },
    }


class TestResetActiveProgress:
    """Tests for _reset_active_progress normal behavior."""

    def test_clears_features_bugs_updates_retrospectives(self, project_scope):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        # Write data to disk so save_progress_json can operate
        (state_dir / "progress.json").write_text(json.dumps(data))
        old_updated = data["updated_at"]

        pm._reset_active_progress(data)

        assert data["features"] == []
        assert data["bugs"] == []
        assert data["updates"] == []
        assert data["retrospectives"] == []

    def test_clears_current_ids_and_workflow_state(self, project_scope):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))

        pm._reset_active_progress(data)

        assert data["current_feature_id"] is None
        assert data["current_bug_id"] is None
        assert "workflow_state" not in data

    def test_resets_runtime_context_work_fields(self, project_scope):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))

        pm._reset_active_progress(data)

        rc = data["runtime_context"]
        assert rc["current_feature_id"] is None
        assert rc["workflow_phase"] is None
        assert rc["current_task"] is None
        assert rc["total_tasks"] is None
        assert rc["next_action"] is None

    def test_preserves_runtime_context_structure(self, project_scope):
        data = _make_fully_completed_data()
        # Add non-work fields that should survive reset
        data["runtime_context"]["branch"] = "main"
        data["runtime_context"]["project_root"] = "/some/path"
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))

        pm._reset_active_progress(data)

        rc = data["runtime_context"]
        assert rc["branch"] == "main"
        assert rc["project_root"] == "/some/path"

    def test_updates_updated_at(self, project_scope):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))
        old_updated = data["updated_at"]

        pm._reset_active_progress(data)

        assert data["updated_at"] != old_updated

    def test_saves_progress_json(self, project_scope):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))

        pm._reset_active_progress(data)

        saved = json.loads((state_dir / "progress.json").read_text())
        assert saved["features"] == []
        assert saved["current_feature_id"] is None

    def test_records_project_completed_audit_event(self, project_scope):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))

        pm._reset_active_progress(data)

        records = audit_log.read_audit_log(
            ascending=True, project_root=str(project_scope["root"])
        )
        project_completed_events = [
            r for r in records if r["event_type"] == "project_completed"
        ]
        assert len(project_completed_events) >= 1

    def test_does_not_regenerate_progress_md(self, project_scope):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))
        (state_dir / "progress.md").write_text("OLD MARKER 12345", encoding="utf-8")

        pm._reset_active_progress(data)

        md_path = state_dir / "progress.md"
        assert not md_path.exists()


class TestResetActiveProgressBestEffortAuditError:
    """Tests for best-effort behavior when audit event writing fails."""

    def test_saves_cleared_state_when_audit_fails(self, project_scope, capsys):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))

        with patch.object(
            pm, "record_feature_state_event", side_effect=ValueError("audit fail")
        ) as mock_audit:
            pm._reset_active_progress(data)

        # audit event was attempted with project_completed
        mock_audit.assert_called_once_with(
            event_type="project_completed",
            feature_id=None,
            feature_name=None,
        )

        # On-disk progress.json must be cleared
        saved = json.loads((state_dir / "progress.json").read_text())
        assert saved["features"] == []
        assert saved["bugs"] == []
        assert saved["current_feature_id"] is None

        # Warning was printed
        captured = capsys.readouterr()
        assert "[DONE] WARNING: Failed to write project_completed audit event" in captured.out

    def test_removes_stale_md_when_audit_fails(self, project_scope, capsys):
        data = _make_fully_completed_data()
        state_dir = project_scope["state_dir"]
        (state_dir / "progress.json").write_text(json.dumps(data))

        # Write a progress.md with marker text
        marker = "OLD MARKER 12345"
        (state_dir / "progress.md").write_text(marker)

        with patch.object(
            pm, "record_feature_state_event", side_effect=ValueError("audit fail")
        ):
            pm._reset_active_progress(data)

        assert not (state_dir / "progress.md").exists()
