"""测试 reconcile-state 命令。"""
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


class TestNoDrift:
    def test_no_audit_log_returns_no_drift(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 1, "name": "F1", "completed": False}])
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is False

    def test_consistent_state_returns_no_drift(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True,
                          "development_stage": "completed",
                          "lifecycle_state": "archived"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is False


class TestDriftDetection:
    def test_detects_completed_in_audit_not_in_progress(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is True
        assert 9 in result["drifted_features"]

    def test_detects_undone_in_audit_completed_in_progress(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 5, "name": "F5", "completed": True}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=5, ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "feature_undone", feature_id=5, ts="2026-04-24T11:00:00Z")
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is True
        assert 5 in result["drifted_features"]

    def test_tracker_reset_clears_prior_events_progress_false(self, project_scope):
        """tracker_reset 后无后续事件，progress.json completed=False → 一致（无 drift）。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9, ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "tracker_reset", ts="2026-04-24T11:00:00Z")
        # reset 后无后续事件，progress.json completed=False → 与期望一致
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is False

    def test_tracker_reset_detects_stale_completed_in_progress(self, project_scope):
        """tracker_reset 后无后续事件，但 progress.json completed=True → drift。

        这是 P0 修复的核心场景：reset 后 progress.json 仍残留 completed=True
        属于数据 drift，必须被检测到。
        """
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True,
                          "development_stage": "completed",
                          "lifecycle_state": "archived"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9, ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "tracker_reset", ts="2026-04-24T11:00:00Z")
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is True
        assert 9 in result["drifted_features"]


class TestAutoFix:
    def test_auto_fix_sets_complete_state_fields(self, project_scope):
        """completed=True 时强制写完整状态，不用 setdefault。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False,
                          "development_stage": "developing",
                          "lifecycle_state": "implementing"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        pm.cmd_reconcile_state(check_only=False)
        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        feat = next(f for f in data["features"] if f["id"] == 9)
        assert feat["completed"] is True
        assert feat["development_stage"] == "completed"   # 强制覆盖，不是 setdefault
        assert feat["lifecycle_state"] == "archived"

    def test_auto_fix_undo_clears_completed_fields(self, project_scope):
        """undone 时清理 completed_at 和 commit_hash。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 5, "name": "F5", "completed": True,
                          "completed_at": "2026-04-24T00:00:00Z",
                          "commit_hash": "abc1234",
                          "development_stage": "completed"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_undone", feature_id=5)
        pm.cmd_reconcile_state(check_only=False)
        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        feat = next(f for f in data["features"] if f["id"] == 5)
        assert feat["completed"] is False
        assert feat.get("completed_at") is None
        assert feat.get("commit_hash") is None

    def test_no_auto_commit_by_default(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        with patch("subprocess.run") as mock_run:
            pm.cmd_reconcile_state(check_only=False, auto_commit=False)
            commit_calls = [c for c in mock_run.call_args_list
                            if "commit" in str(c)]
            assert commit_calls == []

    def test_idempotent_second_reconcile_no_drift(self, project_scope):
        """修复后再次运行 reconcile，应报告无 drift。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        pm.cmd_reconcile_state(check_only=False)
        result2 = pm.cmd_reconcile_state(check_only=True)
        assert result2["drift"] is False