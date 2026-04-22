"""
T3 [RED]: wf_auto_driver.py 薄层 driver 测试

覆盖：
- 正常路径：execution_complete phase → pending_action 写回
- fail-open：各种异常 → 静默退出 0
- 幂等：重复调用
- 集成断言：end-to-end pending_action 写回
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import wf_auto_driver
import progress_manager


def _build_progress_json(tmp_path: Path, phase: str, completed: list = None, total: int = 0) -> Path:
    """搭建测试用 progress.json"""
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True)
    progress_file = state_dir / "progress.json"
    data = {
        "project": "Test",
        "current_feature_id": 1,
        "features": [
            {
                "id": 1,
                "name": "Test Feature",
                "completed": False,
                "lifecycle_state": "implementing",
                "development_stage": "developing",
            }
        ],
        "workflow_state": {
            "phase": phase,
            "completed_tasks": completed or [],
            "total_tasks": total,
            "current_task": len(completed or []) + 1,
        },
        "updated_at": "2026-04-22T00:00:00Z",
    }
    progress_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return tmp_path


class TestWfAutoDriverNormalPath:
    """正常路径：pending_action 写回"""

    def test_execution_complete_writes_run_prog_done(self, tmp_path):
        project_root = _build_progress_json(tmp_path, "execution_complete")
        wf_auto_driver.run(project_root=str(project_root))
        data = json.loads((project_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        assert data["workflow_state"]["pending_action"] == "run_prog_done"

    def test_execution_incomplete_writes_continue(self, tmp_path):
        project_root = _build_progress_json(tmp_path, "execution", completed=[1, 2], total=5)
        wf_auto_driver.run(project_root=str(project_root))
        data = json.loads((project_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        assert data["workflow_state"]["pending_action"] == "continue_execution"

    def test_planning_draft_writes_resume_draft(self, tmp_path):
        project_root = _build_progress_json(tmp_path, "planning:draft")
        wf_auto_driver.run(project_root=str(project_root))
        data = json.loads((project_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        assert data["workflow_state"]["pending_action"] == "resume_planning_draft"


class TestWfAutoDriverFailOpen:
    """fail-open：任何异常不传播"""

    def test_missing_progress_json_does_not_raise(self, tmp_path):
        """progress.json 不存在 → 静默退出"""
        wf_auto_driver.run(project_root=str(tmp_path))  # no exception

    def test_no_current_feature_does_not_raise(self, tmp_path):
        """无 current_feature_id → 静默退出"""
        state_dir = tmp_path / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "progress.json").write_text(json.dumps({"current_feature_id": None, "features": []}))
        wf_auto_driver.run(project_root=str(tmp_path))  # no exception

    def test_no_workflow_state_does_not_raise(self, tmp_path):
        """无 workflow_state → 静默退出（空操作）"""
        state_dir = tmp_path / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "progress.json").write_text(json.dumps({
            "current_feature_id": 1,
            "features": [{"id": 1, "name": "F"}],
        }))
        wf_auto_driver.run(project_root=str(tmp_path))  # no exception

    def test_exception_in_inner_drive_does_not_propagate(self, tmp_path):
        """内部 _drive 抛出异常 → fail-open"""
        with patch.object(wf_auto_driver, "_drive", side_effect=RuntimeError("boom")):
            wf_auto_driver.run(project_root=str(tmp_path))  # no exception


class TestWfAutoDriverIdempotent:
    """幂等性：重复调用不改变最终状态"""

    def test_repeated_calls_same_result(self, tmp_path):
        project_root = _build_progress_json(tmp_path, "execution_complete")
        wf_auto_driver.run(project_root=str(project_root))
        wf_auto_driver.run(project_root=str(project_root))
        data = json.loads((project_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        assert data["workflow_state"]["pending_action"] == "run_prog_done"

    def test_unknown_phase_does_not_write_pending_action(self, tmp_path):
        """unknown phase → pending_action 不写入（或保持 None）"""
        project_root = _build_progress_json(tmp_path, "some_unknown_phase")
        wf_auto_driver.run(project_root=str(project_root))
        data = json.loads((project_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        assert data["workflow_state"].get("pending_action") is None


class TestHooksJsonRegistration:
    """T6: hooks.json 集成断言 — Stop + UPS 注册"""

    def test_hooks_json_has_stop_with_wf_auto_driver(self):
        hooks_path = Path(__file__).parent.parent / "hooks" / "hooks.json"
        hooks = json.loads(hooks_path.read_text())
        stop_entries = hooks["hooks"].get("Stop", [])
        commands = [h["command"] for entry in stop_entries for h in entry["hooks"]]
        assert any("wf-auto-driver" in c for c in commands), \
            "Stop hook 中未找到 wf-auto-driver"

    def test_hooks_json_has_ups_with_wf_auto_driver(self):
        hooks_path = Path(__file__).parent.parent / "hooks" / "hooks.json"
        hooks = json.loads(hooks_path.read_text())
        ups_entries = hooks["hooks"].get("UserPromptSubmit", [])
        commands = [h["command"] for entry in ups_entries for h in entry["hooks"]]
        assert any("wf-auto-driver" in c for c in commands), \
            "UserPromptSubmit hook 中未找到 wf-auto-driver"

    def test_hooks_json_stop_timeout_reasonable(self):
        hooks_path = Path(__file__).parent.parent / "hooks" / "hooks.json"
        hooks = json.loads(hooks_path.read_text())
        stop_entries = hooks["hooks"].get("Stop", [])
        for entry in stop_entries:
            for h in entry["hooks"]:
                if "wf-auto-driver" in h.get("command", ""):
                    assert h["timeout"] <= 10000, "Stop hook timeout 应 ≤ 10s"

    def test_hooks_json_ups_has_auto_checkpoint_before_wf_driver(self):
        """auto-checkpoint 应排在 wf-auto-driver 之前"""
        hooks_path = Path(__file__).parent.parent / "hooks" / "hooks.json"
        hooks = json.loads(hooks_path.read_text())
        ups_entries = hooks["hooks"].get("UserPromptSubmit", [])
        commands = [h["command"] for entry in ups_entries for h in entry["hooks"]]
        auto_ck_idx = next((i for i, c in enumerate(commands) if "auto-checkpoint" in c), -1)
        wf_driver_idx = next((i for i, c in enumerate(commands) if "wf-auto-driver" in c), -1)
        assert auto_ck_idx != -1, "auto-checkpoint 未在 UPS 中"
        assert wf_driver_idx != -1, "wf-auto-driver 未在 UPS 中"
        assert auto_ck_idx < wf_driver_idx, "auto-checkpoint 应在 wf-auto-driver 之前"


class TestWfAutoDriverIntegration:
    """集成断言：end-to-end pending_action 写回路径"""

    def test_end_to_end_execution_complete(self, tmp_path):
        """
        搭建真实 progress.json（execution_complete）→
        调用 wf_auto_driver.run() →
        断言 pending_action == "run_prog_done"
        """
        project_root = _build_progress_json(tmp_path, "execution_complete", completed=[1, 2, 3], total=3)

        # 确认初始状态没有 pending_action
        initial = json.loads((project_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        assert "pending_action" not in initial["workflow_state"]

        # 调用 driver
        wf_auto_driver.run(project_root=str(project_root))

        # 断言写回
        result = json.loads((project_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        assert result["workflow_state"]["pending_action"] == "run_prog_done"

    def test_end_to_end_execution_partial(self, tmp_path):
        """
        execution 阶段，2/5 完成 →
        pending_action == "continue_execution"
        """
        project_root = _build_progress_json(tmp_path, "execution", completed=[1, 2], total=5)
        wf_auto_driver.run(project_root=str(project_root))
        result = json.loads((project_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        assert result["workflow_state"]["pending_action"] == "continue_execution"
