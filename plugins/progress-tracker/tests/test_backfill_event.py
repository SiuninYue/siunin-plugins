"""测试 backfill-event 命令。"""
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


class TestFindBackfillCandidates:
    def test_detects_completed_missing_audit_event(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True,
                          "completed_at": "2026-04-23T02:00:00Z"}])
        candidates = pm.find_backfill_candidates()
        assert 9 in [c["feature_id"] for c in candidates]

    def test_no_candidate_when_event_exists(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        candidates = pm.find_backfill_candidates()
        assert candidates == []

    def test_incomplete_feature_not_candidate(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 5, "name": "F5", "completed": False}])
        candidates = pm.find_backfill_candidates()
        assert candidates == []


class TestBackfillEventWrite:
    def test_writes_event_with_backfilled_metadata(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "Refactor F9", "completed": True,
                          "completed_at": "2026-04-23T02:00:00Z"}])
        with patch("builtins.input", return_value="y"):
            result = pm.cmd_backfill_event(feature_id=9)
        assert result["written"] == 1
        records = audit_log.read_audit_log(ascending=True, project_root=str(project_scope["root"]))
        r = records[0]
        assert r["event_type"] == "feature_completed"
        assert r["feature_id"] == 9
        assert r.get("backfilled") is True
        assert "backfill_reason" in r

    def test_idempotent_second_backfill_skipped(self, project_scope):
        """同一 feature 重复 backfill → 第二次检测已有事件，跳过，written=0。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True}])
        with patch("builtins.input", return_value="y"):
            pm.cmd_backfill_event(feature_id=9)
        # 第二次：已有 feature_completed 事件，不再是候选
        with patch("builtins.input", return_value="y"):
            result2 = pm.cmd_backfill_event(feature_id=9)
        assert result2["written"] == 0
        assert result2["candidates"] == 0

    def test_cancelled_on_n(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True}])
        with patch("builtins.input", return_value="n"):
            result = pm.cmd_backfill_event(feature_id=9)
        assert result["written"] == 0
        assert result["cancelled"] is True

    def test_backfill_all_candidates(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 1, "name": "F1", "completed": True},
                         {"id": 9, "name": "F9", "completed": True}])
        with patch("builtins.input", return_value="y"):
            result = pm.cmd_backfill_event(feature_id=None)
        assert result["written"] == 2

    def test_pre_reset_event_does_not_block_post_reset_backfill(self, project_scope):
        """P1 修复：reset 之前的 feature_completed 不阻止 reset 之后的合法 backfill。

        场景：F9 在 reset 前已完成（有事件），reset 后 F9 重新变为 completed=True
        但 audit.log 里 reset 后没有新的 feature_completed → 应该是 backfill 候选。
        """
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True,
                          "completed_at": "2026-04-24T12:00:00Z"}])
        # 写 reset 之前的完成事件
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9, ts="2026-04-24T09:00:00Z")
        # 然后 tracker_reset
        _write_audit_event(project_scope["state_dir"],
                           "tracker_reset", ts="2026-04-24T10:00:00Z")
        # reset 之后没有新的 feature_completed → 仍然是 backfill 候选
        candidates = pm.find_backfill_candidates(feature_id=9)
        assert 9 in [c["feature_id"] for c in candidates], \
            "Pre-reset completion should NOT block post-reset backfill"