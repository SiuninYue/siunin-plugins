"""验证 done/undo/reset 路径向 audit.log 写入对应事件。"""
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log
import progress_manager as pm

# 从 conftest 导入辅助函数
sys.path.insert(0, str(Path(__file__).parent))
from conftest import _write_progress, _write_audit_event


class TestRecordFeatureStateEvent:
    def test_function_exists(self):
        assert hasattr(pm, "record_feature_state_event")

    def test_writes_feature_completed_event(self, project_scope):
        root = project_scope["root"]
        pm.record_feature_state_event(
            event_type="feature_completed",
            feature_id=9,
            feature_name="Refactor F9",
        )
        # 必须显式传 project_root，不依赖 PROGRESS_TRACKER_STATE_DIR
        records = audit_log.read_audit_log(ascending=True, project_root=str(root))
        assert len(records) == 1
        r = records[0]
        assert r["event_type"] == "feature_completed"
        assert r["feature_id"] == 9
        assert r["details"]["feature_name"] == "Refactor F9"

    def test_writes_feature_undone_event(self, project_scope):
        root = project_scope["root"]
        pm.record_feature_state_event(
            event_type="feature_undone",
            feature_id=9,
            feature_name="Refactor F9",
        )
        records = audit_log.read_audit_log(ascending=True, project_root=str(root))
        assert records[0]["event_type"] == "feature_undone"

    def test_writes_tracker_reset_without_feature_id(self, project_scope):
        root = project_scope["root"]
        pm.record_feature_state_event(
            event_type="tracker_reset",
            feature_id=None,
            feature_name=None,
        )
        records = audit_log.read_audit_log(ascending=True, project_root=str(root))
        r = records[0]
        assert r["event_type"] == "tracker_reset"
        assert r.get("feature_id") is None

    def test_uses_project_root_from_find_project_root(self, project_scope):
        """audit 事件应写到 project_scope 的 audit.log，不是 audit_log.py 的默认路径。

        此测试验证不依赖 PROGRESS_TRACKER_STATE_DIR 时路径路由是否正确。
        """
        pm.record_feature_state_event(
            event_type="feature_completed",
            feature_id=1,
            feature_name="F1",
        )
        # audit.log 应存在于 project_scope 的 state_dir（通过 project_root 路由）
        assert (project_scope["state_dir"] / "audit.log").exists()
        # 再通过显式 project_root 确认可读取
        records = audit_log.read_audit_log(
            ascending=True, project_root=str(project_scope["root"])
        )
        assert len(records) == 1