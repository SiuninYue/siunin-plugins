"""Integration tests: complete_feature clears active state when all features done."""
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log
import progress_manager as pm

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _write_progress, _write_audit_event


def _write_full_completed_project(state_dir, feature_count=2):
    """Write progress.json with all features completed."""
    features = [
        {"id": i + 1, "name": f"F{i+1}", "completed": True,
         "development_stage": "completed", "lifecycle_state": "archived",
         "completed_at": f"2026-01-0{i+2}T00:00:00Z",
         "commit_hash": f"abc{i+1}"}
        for i in range(feature_count)
    ]
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": features,
        "current_feature_id": None,
        "bugs": [{"id": "BUG-001", "description": "test bug", "status": "fixed"}],
        "updates": [{"id": "UPD-001", "summary": "test update"}],
        "retrospectives": [{"id": "RET-001", "summary": "test retro"}],
        "current_bug_id": "BUG-001",
    }
    path = state_dir / "progress.json"
    path.write_text(json.dumps(data))
    return data


class TestCompleteFeatureClearsState:
    def test_clears_active_state_on_last_feature(self, project_scope):
        """complete_feature on the last feature clears features/bugs/updates/retrospectives."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=2)

        pm.complete_feature(feature_id=2, skip_archive=True)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []
        assert data["bugs"] == []
        assert data["updates"] == []
        assert data["retrospectives"] == []
        assert data["current_feature_id"] is None
        assert data["current_bug_id"] is None

    def test_clears_with_skip_archive(self, project_scope):
        """_reset_active_progress runs even with skip_archive=True."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1)

        pm.complete_feature(feature_id=1, skip_archive=True)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []

    def test_clears_when_archive_throws(self, project_scope):
        """_reset_active_progress runs even if archive_current_progress raises."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1)

        with patch.object(pm, "archive_current_progress", side_effect=OSError("disk full")):
            pm.complete_feature(feature_id=1, skip_archive=False)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []

    def test_records_project_completed_event(self, project_scope):
        """complete_feature on last feature writes project_completed to audit.log."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1)

        pm.complete_feature(feature_id=1, skip_archive=True)

        records = audit_log.read_audit_log(
            ascending=True, project_root=str(project_scope["root"]))
        assert any(r["event_type"] == "project_completed" for r in records)

    def test_does_not_clear_if_not_fully_completed(self, project_scope):
        """If not all features are complete, _reset_active_progress is NOT called."""
        features = [
            {"id": 1, "name": "F1", "completed": True,
             "development_stage": "completed", "commit_hash": "abc1"},
            {"id": 2, "name": "F2", "completed": False},
        ]
        _write_progress(project_scope["state_dir"], features, current_id=None)
        # Write full data dict manually for extra fields
        path = project_scope["state_dir"] / "progress.json"
        data = json.loads(path.read_text())
        data["bugs"] = [{"id": "BUG-001", "description": "test bug", "status": "fixed"}]
        path.write_text(json.dumps(data))

        pm.complete_feature(feature_id=1, skip_archive=True)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        # bugs should still be there — reset not triggered
        assert len(data["bugs"]) == 1