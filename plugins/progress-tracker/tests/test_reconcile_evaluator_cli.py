"""Tests for prog reconcile-evaluator command (F28)."""

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager


def _make_progress_json(tmp_path, features, current_feature_id=None, workflow_state=None):
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "project_name": "Test",
        "created_at": "2026-01-01T00:00:00Z",
        "features": features,
        "current_feature_id": current_feature_id,
    }
    if workflow_state is not None:
        data["workflow_state"] = workflow_state
    (state_dir / "progress.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    return state_dir


class TestReconcileEvaluatorFullScan:
    def test_backfills_feature_with_null_evaluator(self, tmp_path, monkeypatch):
        """全量扫描：evaluator 为 null 的已完成 Feature 应被回填为 pass。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 1,
                    "name": "Old Feature",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator()

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        evaluator = data["features"][0]["quality_gates"]["evaluator"]
        assert evaluator["status"] == "pass"
        assert evaluator["score"] >= 0  # 不硬编码具体分值，仅验证已被设置

    def test_backfills_feature_with_pending_evaluator(self, tmp_path, monkeypatch):
        """全量扫描：evaluator.status == 'pending' 的已完成 Feature 应被回填。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 2,
                    "name": "Pending Feature",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {
                        "evaluator": {
                            "status": "pending",
                            "score": None,
                            "defects": [],
                            "last_run_at": None,
                            "evaluator_model": None,
                        }
                    },
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator()

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        evaluator = data["features"][0]["quality_gates"]["evaluator"]
        assert evaluator["status"] == "pass"

    def test_backfills_feature_with_execution_complete_state(self, tmp_path, monkeypatch):
        """workflow_state.phase == 'execution_complete' 的当前 Feature 也应被扫描回填。

        execution_complete 是 workflow 阶段（非 schema lifecycle_state），表示已完成实现
        但尚未运行 /prog done — 仍属于有效回填目标。
        通过 workflow_state.phase + current_feature_id 识别，而非 lifecycle_state 字段。
        """
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 3,
                    "name": "Execution Complete Feature",
                    "completed": False,  # 尚未归档，completed 仍为 False
                    "quality_gates": {"evaluator": None},
                }
            ],
            current_feature_id=3,
            workflow_state={"phase": "execution_complete"},
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator()

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        evaluator = data["features"][0]["quality_gates"]["evaluator"]
        assert evaluator["status"] == "pass"

    def test_skips_incomplete_features(self, tmp_path, monkeypatch):
        """lifecycle_state == 'developing' 的未完成 Feature 不应被扫描。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 4,
                    "name": "In Progress",
                    "completed": False,
                    "lifecycle_state": "developing",
                    "quality_gates": {"evaluator": None},
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator()

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        assert data["features"][0]["quality_gates"]["evaluator"] is None

    def test_skips_already_evaluated_features(self, tmp_path, monkeypatch):
        """evaluator.status != 'pending' 的 Feature 不应被重复回填。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 5,
                    "name": "Already Evaluated",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {
                        "evaluator": {
                            "status": "pass",
                            "score": 95,
                            "defects": [],
                            "last_run_at": "2026-01-01T00:00:00Z",
                            "evaluator_model": "sonnet",
                        }
                    },
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator()

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        assert data["features"][0]["quality_gates"]["evaluator"]["score"] == 95

    def test_returns_zero_when_nothing_to_backfill(self, tmp_path, monkeypatch, capsys):
        """没有需要回填的 Feature 时返回 0，JSON 输出 backfilled == 0。"""
        state_dir = _make_progress_json(tmp_path, [])
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator(output_json=True)
        captured = capsys.readouterr()
        report = json.loads(captured.out)

        assert result == 0
        assert report["backfilled"] == 0


class TestReconcileEvaluatorSingleFeature:
    def test_feature_id_targets_specific_feature(self, tmp_path, monkeypatch):
        """`feature_id` 只回填指定 Feature，不影响其他。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 6,
                    "name": "Target",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                },
                {
                    "id": 7,
                    "name": "Other",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                },
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator(feature_id=6)

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        feat6 = next(f for f in data["features"] if f["id"] == 6)
        feat7 = next(f for f in data["features"] if f["id"] == 7)
        assert feat6["quality_gates"]["evaluator"]["status"] == "pass"
        # feat7 未被回填：evaluator 仍为 pending（_apply_schema_defaults 设默认值），非 pass
        assert feat7["quality_gates"]["evaluator"]["status"] != "pass"

    def test_feature_id_not_found_returns_2(self, tmp_path, monkeypatch):
        """指定不存在的 feature_id 应返回 2。"""
        state_dir = _make_progress_json(tmp_path, [])
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator(feature_id=999)

        assert result == 2


class TestReconcileEvaluatorAuditEvent:
    def test_writes_both_evaluator_assessment_and_backfill_events(
        self, tmp_path, monkeypatch
    ):
        """每次成功回填应同时写入 evaluator_assessment 和 evaluator_backfill 两条审计事件。

        evaluator_assessment 由 _store_evaluator_result 内部写入（记录评分）；
        evaluator_backfill 由 reconcile_evaluator 写入（记录来源与原因）。
        """
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 8,
                    "name": "Audit Test",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        import audit_log as al

        result = progress_manager.reconcile_evaluator()

        assert result == 0
        records = al.read_audit_log(project_root=str(tmp_path))
        event_types = [r["event_type"] for r in records if r.get("feature_id") == 8]
        assert "evaluator_assessment" in event_types, (
            "evaluator_assessment event must be written by _store_evaluator_result"
        )
        assert "evaluator_backfill" in event_types, (
            "evaluator_backfill event must be written by reconcile_evaluator"
        )

    def test_backfill_event_has_correct_fields(self, tmp_path, monkeypatch):
        """evaluator_backfill 事件应包含 backfill_reason、source、status 字段。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 9,
                    "name": "Backfill Fields",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        import audit_log as al

        progress_manager.reconcile_evaluator()

        records = al.read_audit_log(project_root=str(tmp_path))
        ev = next(
            r for r in records
            if r.get("event_type") == "evaluator_backfill" and r.get("feature_id") == 9
        )
        assert ev["details"]["backfill_reason"] == "missing_evaluator"
        assert ev["details"]["source"] == "reconcile-evaluator CLI"
        assert ev["details"]["status"] == "pass"

    def test_pending_evaluator_backfill_reason_is_retry(self, tmp_path, monkeypatch):
        """pending 状态的回填应记录 backfill_reason=retry。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 10,
                    "name": "Retry Audit",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {
                        "evaluator": {
                            "status": "pending",
                            "score": None,
                            "defects": [],
                            "last_run_at": None,
                            "evaluator_model": None,
                        }
                    },
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        import audit_log as al

        progress_manager.reconcile_evaluator()

        records = al.read_audit_log(project_root=str(tmp_path))
        ev = next(
            r for r in records
            if r.get("event_type") == "evaluator_backfill" and r.get("feature_id") == 10
        )
        assert ev["details"]["backfill_reason"] == "retry"


class TestReconcileEvaluatorExitCodes:
    def test_output_json_contains_summary_fields(self, tmp_path, monkeypatch, capsys):
        """output_json=True 应输出包含所有必需字段的 JSON。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 11,
                    "name": "JSON Test",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        result = progress_manager.reconcile_evaluator(output_json=True)
        captured = capsys.readouterr()
        report = json.loads(captured.out)

        assert result == 0
        assert report["total_scanned"] == 1
        assert report["backfilled"] == 1
        assert report["failed"] == {}
        assert "1/1" in report["summary"]

    def test_partial_failure_returns_1(self, tmp_path, monkeypatch):
        """部分成功部分失败时应返回 1。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 12,
                    "name": "Good Feature",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                },
                {
                    "id": 13,
                    "name": "Bad Feature",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                },
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        original_store = progress_manager._store_evaluator_result

        def mock_store(feature_id, result):
            if feature_id == 13:
                raise RuntimeError("simulated store failure")
            original_store(feature_id, result)

        monkeypatch.setattr(progress_manager, "_store_evaluator_result", mock_store)

        result = progress_manager.reconcile_evaluator()

        assert result == 1

    def test_all_failed_returns_2(self, tmp_path, monkeypatch):
        """所有 Feature 均失败时应返回 2。"""
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 14,
                    "name": "Always Fails",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path

        monkeypatch.setattr(
            progress_manager,
            "_store_evaluator_result",
            lambda fid, r: (_ for _ in ()).throw(RuntimeError("forced failure")),
        )

        result = progress_manager.reconcile_evaluator()

        assert result == 2


class TestReconcileEvaluatorErrorGuards:
    def test_returns_2_when_evaluator_gate_module_unavailable(
        self, tmp_path, monkeypatch, capsys
    ):
        """evaluator_gate_mod == None 时应返回 2 并输出 error。"""
        state_dir = _make_progress_json(tmp_path, [])
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        monkeypatch.setattr(progress_manager, "evaluator_gate_mod", None)

        result = progress_manager.reconcile_evaluator(output_json=True)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)

        assert result == 2
        assert "error" in payload

    def test_returns_2_when_progress_json_missing(self, tmp_path, monkeypatch, capsys):
        """load_progress_json() 返回 None 时应返回 2 并输出 error。"""
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        # 不创建 progress.json，load_progress_json 将返回 None

        result = progress_manager.reconcile_evaluator(output_json=True)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)

        assert result == 2
        assert "error" in payload


class TestReconcileEvaluatorCLI:
    def test_cli_full_scan_returns_0_and_json(self, tmp_path):
        """prog reconcile-evaluator --json 可正常调用并返回 0。"""
        import subprocess

        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 15,
                    "name": "CLI Test",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                }
            ],
        )
        prog_py = Path(__file__).parent.parent / "hooks" / "scripts" / "progress_manager.py"
        env = {**os.environ, "PROGRESS_TRACKER_STATE_DIR": str(state_dir)}

        proc = subprocess.run(
            [
                sys.executable, str(prog_py),
                "--project-root", str(tmp_path),
                "reconcile-evaluator", "--json",
            ],
            capture_output=True, text=True, env=env, cwd=str(tmp_path),
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        report = json.loads(proc.stdout)
        assert report["backfilled"] == 1
        assert report["failed"] == {}

    def test_cli_feature_id_only_processes_target(self, tmp_path):
        """prog reconcile-evaluator --feature-id <id> 只处理指定 Feature。"""
        import subprocess

        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 16,
                    "name": "CLI Single",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                },
                {
                    "id": 17,
                    "name": "CLI Other",
                    "completed": True,
                    "lifecycle_state": "archived",
                    "quality_gates": {"evaluator": None},
                },
            ],
        )
        prog_py = Path(__file__).parent.parent / "hooks" / "scripts" / "progress_manager.py"
        env = {**os.environ, "PROGRESS_TRACKER_STATE_DIR": str(state_dir)}

        proc = subprocess.run(
            [
                sys.executable, str(prog_py),
                "--project-root", str(tmp_path),
                "reconcile-evaluator", "--feature-id", "16", "--json",
            ],
            capture_output=True, text=True, env=env, cwd=str(tmp_path),
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        report = json.loads(proc.stdout)
        assert report["total_scanned"] == 1
        assert report["backfilled"] == 1

        data = json.loads((state_dir / "progress.json").read_text())
        feat17 = next(f for f in data["features"] if f["id"] == 17)
        # feat17 未被回填：schema 归一化为 pending 但未评估
        assert feat17["quality_gates"]["evaluator"]["status"] != "pass"
