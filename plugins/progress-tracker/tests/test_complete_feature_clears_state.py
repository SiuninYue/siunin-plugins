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


def _write_full_completed_project(state_dir, feature_count=2, last_pending=False):
    """Write progress.json where all features are completed (or all-but-last)."""
    features = []
    for i in range(feature_count):
        feature_id = i + 1
        is_last_pending = last_pending and feature_id == feature_count
        feature = {
            "id": feature_id,
            "name": f"F{feature_id}",
            "completed": not is_last_pending,
            "development_stage": "developing" if is_last_pending else "completed",
            "lifecycle_state": "implementing" if is_last_pending else "archived",
            "completed_at": None if is_last_pending else f"2026-01-0{feature_id + 1}T00:00:00Z",
            "commit_hash": None if is_last_pending else f"abc{feature_id}",
        }
        features.append(feature)
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
        """Completing the last pending feature clears features/bugs/updates/retrospectives."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=2, last_pending=True)

        pm.complete_feature(feature_id=2, skip_archive=True)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []
        assert data["bugs"] == []
        assert data["updates"] == []
        assert data["retrospectives"] == []
        assert data["current_feature_id"] is None
        assert data["current_bug_id"] is None

    def test_clears_with_skip_archive(self, project_scope):
        """_reset_active_progress runs even with skip_archive=True on real transition."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1, last_pending=True)

        pm.complete_feature(feature_id=1, skip_archive=True)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []

    def test_clears_when_archive_throws(self, project_scope):
        """_reset_active_progress runs even if archive_current_progress raises."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1, last_pending=True)

        with patch.object(pm, "archive_current_progress", side_effect=OSError("disk full")):
            pm.complete_feature(feature_id=1, skip_archive=False)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []

    def test_records_project_completed_event(self, project_scope):
        """Completing last pending feature writes project_completed to audit.log."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1, last_pending=True)

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

    def test_clears_state_when_project_completed_audit_fails(self, project_scope):
        """project_completed 审计写入失败时，reset 需 best-effort 仍清除 active state。

        仅拦截 event_type == "project_completed" 的调用，放行 feature_completed。
        """
        _write_full_completed_project(project_scope["state_dir"], feature_count=1, last_pending=True)

        original = pm.record_feature_state_event

        def selective_fail(*args, **kwargs):
            if kwargs.get("event_type") == "project_completed":
                raise ValueError("audit fail")
            return original(*args, **kwargs)

        with patch.object(pm, "record_feature_state_event", side_effect=selective_fail):
            pm.complete_feature(feature_id=1, skip_archive=False)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert not data["features"], "best-effort: state should be cleared even when project_completed audit fails"
        assert data["current_feature_id"] is None
