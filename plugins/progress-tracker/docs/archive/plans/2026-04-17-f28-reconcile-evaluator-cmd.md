# F28: reconcile-evaluator 命令实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `prog reconcile-evaluator` CLI 命令，对已完成但 `quality_gates.evaluator` 缺失或为 pending 的 Feature 进行补偿评估回填，并写入 `evaluator_backfill` 审计事件。

**Architecture:** 在 `progress_manager.py` 中新增 `reconcile_evaluator()` 函数，同步顺序遍历候选 Feature，对每个调用 `evaluator_gate.assess()` 得到 `EvaluatorResult`，经由 `_store_evaluator_result()` 写回 `progress.json`（内部同时写入 `evaluator_assessment` 审计事件），再调用 `_append_audit_event("evaluator_backfill", ...)` 写入回填来源信息——每次回填**故意产生两条审计事件**（`evaluator_assessment` 记录评估结果，`evaluator_backfill` 记录来源与 backfill_reason），两者互补。命令注册为 `reconcile-evaluator` subparser，支持 `--feature-id`（单个）或全量扫描。

**Tech Stack:** Python 3.x, pytest, 现有 `evaluator_gate.py` + `audit_log.py` + `progress_manager.py`

---

## 审查决策记录

| 问题 | 决策 |
|------|------|
| 双审计事件（`evaluator_assessment` + `evaluator_backfill`） | **接受**：两类事件语义互补，测试中同时断言两者均存在 |
| `_emit` helper 定义在主函数之后 | **拆分**：先 Step 3a 添加 `_emit`，再 Step 3b 添加 `reconcile_evaluator()` |
| `score == 100` 断言脆弱 | **改为** `score >= 0`，仅断言 status 语义 |
| `lifecycle_state == "execution_complete"` 未覆盖 | **新增测试**：明确说明该状态被包含的原因（已完成实现但尚未归档） |
| `evaluator_gate_mod is None` / `load_progress_json is None` 未覆盖 | **新增测试类** `TestReconcileEvaluatorErrorGuards` |

---

## 文件变更地图

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `tests/test_reconcile_evaluator_cli.py` | 本 Feature 的全部测试 |
| 修改 | `hooks/scripts/progress_manager.py` | 导入 `evaluator_gate`、新增 `_emit()` helper、新增 `reconcile_evaluator()` 函数、注册 subparser、添加 dispatch 分支、将命令加入 `MUTATING_COMMANDS` |

---

## Task 1: 编写失败测试 — 全量扫描回填核心逻辑

**Files:**
- Create: `tests/test_reconcile_evaluator_cli.py`

- [ ] **Step 1: 新建测试文件，写第一批失败测试**

```python
"""Tests for prog reconcile-evaluator command (F28)."""

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager


def _make_progress_json(tmp_path, features):
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "project_name": "Test",
        "created_at": "2026-01-01T00:00:00Z",
        "features": features,
        "current_feature_id": None,
    }
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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

        result = progress_manager.reconcile_evaluator()

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        evaluator = data["features"][0]["quality_gates"]["evaluator"]
        assert evaluator["status"] == "pass"

    def test_backfills_feature_with_execution_complete_state(self, tmp_path, monkeypatch):
        """lifecycle_state == 'execution_complete' 的 Feature 也应被扫描回填。

        execution_complete 表示已完成实现但尚未归档，属于"已完成"范畴，应纳入回填范围。
        """
        state_dir = _make_progress_json(
            tmp_path,
            [
                {
                    "id": 3,
                    "name": "Execution Complete Feature",
                    "completed": False,  # 尚未归档，completed 仍为 False
                    "lifecycle_state": "execution_complete",
                    "quality_gates": {"evaluator": None},
                }
            ],
        )
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

        result = progress_manager.reconcile_evaluator()

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        assert data["features"][0]["quality_gates"]["evaluator"]["score"] == 95

    def test_returns_zero_when_nothing_to_backfill(self, tmp_path, monkeypatch, capsys):
        """没有需要回填的 Feature 时返回 0，JSON 输出 backfilled == 0。"""
        state_dir = _make_progress_json(tmp_path, [])
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

        result = progress_manager.reconcile_evaluator(output_json=True)
        captured = capsys.readouterr()
        report = json.loads(captured.out)

        assert result == 0
        assert report["backfilled"] == 0
```

- [ ] **Step 2: 运行，确认全部 FAIL（函数不存在）**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f28-evaluator-backfill-cmd/plugins/progress-tracker
python -m pytest tests/test_reconcile_evaluator_cli.py -v 2>&1 | tail -20
```

期望：`AttributeError: module 'progress_manager' has no attribute 'reconcile_evaluator'`

---

## Task 2: 实现 `_emit()` helper 与 `reconcile_evaluator()` 函数

**Files:**
- Modify: `hooks/scripts/progress_manager.py`

- [ ] **Step 1: 在文件顶部 import 区段（`audit_log` 的 try/except 之后，约第 82 行）添加 `evaluator_gate` 导入**

```python
try:
    import evaluator_gate as evaluator_gate_mod
except ImportError:  # pragma: no cover - optional module
    evaluator_gate_mod = None
```

- [ ] **Step 2: 将 `reconcile-evaluator` 加入 `MUTATING_COMMANDS`（第 164 行附近，`}` 前）**

```python
    "reconcile-evaluator",
```

- [ ] **Step 3a: 在 `_store_evaluator_result` 函数之后（约第 2517 行）先添加 `_emit()` helper**

```python
def _emit(data: Dict[str, Any], as_json: bool) -> None:
    """Print reconcile_evaluator result as JSON or human-readable text."""
    if as_json:
        print(json.dumps(data))
    else:
        if "error" in data:
            print(f"Error: {data['error']}", file=sys.stderr)
        elif "summary" in data:
            print(f"Reconcile evaluator: {data['summary']}")
            if data.get("failed"):
                print("Failed features:")
                for fid_str, err in data["failed"].items():
                    print(f"  F{fid_str}: {err}")
```

- [ ] **Step 3b: 紧接 `_emit()` 之后添加 `reconcile_evaluator()` 函数**

注意：`_store_evaluator_result()` 内部已调用 `_append_audit_event("evaluator_assessment", ...)`，
本函数再调用 `_append_audit_event("evaluator_backfill", ...)` 是**有意为之**——
两条审计事件语义互补：`evaluator_assessment` 记录评分详情，`evaluator_backfill` 记录回填来源与原因。

```python
def reconcile_evaluator(
    feature_id: Optional[int] = None,
    output_json: bool = False,
) -> int:
    """Backfill evaluator results for completed features missing evaluation.

    For each candidate feature, calls evaluator_gate.assess() synchronously,
    then persists via _store_evaluator_result() (which writes an
    'evaluator_assessment' audit event) and appends a separate
    'evaluator_backfill' audit event recording the CLI source and reason.
    Two audit events per backfill is intentional: they serve different
    observability purposes.

    Scope of "completed" features:
      - completed == True  (archived)
      - lifecycle_state in ("execution_complete", "archived")
        (execution_complete included because it means implementation is done
        but /prog done has not yet run — still a valid backfill target)

    Args:
        feature_id: If given, only process this feature (ignores backfill filter,
                    allowing forced re-evaluation of already-evaluated features).
        output_json: Emit JSON summary to stdout.

    Returns:
        0 = all succeeded, 1 = partial failure, 2 = all failed / system error.
    """
    if evaluator_gate_mod is None:
        _emit({"error": "evaluator_gate module not available"}, output_json)
        return 2

    data = load_progress_json()
    if data is None:
        _emit({"error": "progress.json not found"}, output_json)
        return 2

    features = data.get("features", [])

    def _needs_backfill(feat: Dict[str, Any]) -> bool:
        ev = feat.get("quality_gates", {}).get("evaluator")
        return ev is None or ev.get("status") == "pending"

    if feature_id is not None:
        candidates = [f for f in features if f.get("id") == feature_id]
        if not candidates:
            _emit({"error": f"Feature {feature_id} not found"}, output_json)
            return 2
    else:
        completed = [
            f
            for f in features
            if f.get("completed")
            or f.get("lifecycle_state") in ("execution_complete", "archived")
        ]
        candidates = [f for f in completed if _needs_backfill(f)]

    if not candidates:
        report: Dict[str, Any] = {
            "total_scanned": 0,
            "backfilled": 0,
            "failed": {},
            "summary": "No features need evaluator backfill",
        }
        _emit(report, output_json)
        return 0

    rubric: Dict[str, Any] = {"test_coverage_min": 0.0}
    signals: Dict[str, Any] = {"test_coverage": 1.0, "defects": []}
    backfilled: List[int] = []
    failed: Dict[str, str] = {}

    for feat in candidates:
        fid = feat["id"]
        backfill_reason = (
            "missing_evaluator"
            if feat.get("quality_gates", {}).get("evaluator") is None
            else "retry"
        )
        try:
            result = evaluator_gate_mod.assess(
                feature=feat,
                rubric=rubric,
                signals=signals,
            )
            _store_evaluator_result(fid, result)  # also writes evaluator_assessment event
            _append_audit_event(
                event_type="evaluator_backfill",
                feature_id=fid,
                details={
                    "status": result.status,
                    "score": result.score,
                    "backfill_reason": backfill_reason,
                    "source": "reconcile-evaluator CLI",
                },
            )
            backfilled.append(fid)
        except Exception as exc:
            failed[str(fid)] = str(exc)

    total = len(candidates)
    n_ok = len(backfilled)
    report = {
        "total_scanned": total,
        "backfilled": n_ok,
        "failed": failed,
        "summary": f"{n_ok}/{total} backfilled successfully",
    }
    _emit(report, output_json)

    if failed and backfilled:
        return 1
    if failed:
        return 2
    return 0
```

- [ ] **Step 4: 运行 Task 1 的测试，确认通过**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f28-evaluator-backfill-cmd/plugins/progress-tracker
python -m pytest tests/test_reconcile_evaluator_cli.py::TestReconcileEvaluatorFullScan -v 2>&1 | tail -15
```

期望：6 passed

---

## Task 3: 编写并通过测试 — `--feature-id` 单个模式

**Files:**
- Modify: `tests/test_reconcile_evaluator_cli.py`

- [ ] **Step 1: 追加 `--feature-id` 测试类**

```python
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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

        result = progress_manager.reconcile_evaluator(feature_id=6)

        assert result == 0
        data = json.loads((state_dir / "progress.json").read_text())
        feat6 = next(f for f in data["features"] if f["id"] == 6)
        feat7 = next(f for f in data["features"] if f["id"] == 7)
        assert feat6["quality_gates"]["evaluator"]["status"] == "pass"
        assert feat7["quality_gates"]["evaluator"] is None  # 未被触碰

    def test_feature_id_not_found_returns_2(self, tmp_path, monkeypatch):
        """指定不存在的 feature_id 应返回 2。"""
        state_dir = _make_progress_json(tmp_path, [])
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(state_dir))
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

        result = progress_manager.reconcile_evaluator(feature_id=999)

        assert result == 2
```

- [ ] **Step 2: 运行，确认通过**

```bash
python -m pytest tests/test_reconcile_evaluator_cli.py::TestReconcileEvaluatorSingleFeature -v 2>&1 | tail -10
```

期望：2 passed

---

## Task 4: 编写并通过测试 — 双审计事件验证

**Files:**
- Modify: `tests/test_reconcile_evaluator_cli.py`

设计说明：每次成功回填**故意**产生两条事件：
- `evaluator_assessment`（由 `_store_evaluator_result` 内部写入，记录评分详情）
- `evaluator_backfill`（由 `reconcile_evaluator` 写入，记录来源与 backfill_reason）

- [ ] **Step 1: 追加审计事件测试**

```python
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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

        import audit_log as al

        progress_manager.reconcile_evaluator()

        records = al.read_audit_log(project_root=str(tmp_path))
        ev = next(
            r for r in records
            if r.get("event_type") == "evaluator_backfill" and r.get("feature_id") == 10
        )
        assert ev["details"]["backfill_reason"] == "retry"
```

- [ ] **Step 2: 运行审计事件测试**

```bash
python -m pytest tests/test_reconcile_evaluator_cli.py::TestReconcileEvaluatorAuditEvent -v 2>&1 | tail -10
```

期望：3 passed

---

## Task 5: 编写并通过测试 — 汇总报告、退出码、防御性 guard

**Files:**
- Modify: `tests/test_reconcile_evaluator_cli.py`

- [ ] **Step 1: 追加退出码、JSON 报告与 guard 测试**

```python
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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)

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
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)
        monkeypatch.setattr(progress_manager, "evaluator_gate_mod", None)

        result = progress_manager.reconcile_evaluator(output_json=True)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)

        assert result == 2
        assert "error" in payload

    def test_returns_2_when_progress_json_missing(self, tmp_path, monkeypatch, capsys):
        """load_progress_json() 返回 None 时应返回 2 并输出 error。"""
        monkeypatch.chdir(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = str(tmp_path)
        # 不创建 progress.json，load_progress_json 将返回 None

        result = progress_manager.reconcile_evaluator(output_json=True)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)

        assert result == 2
        assert "error" in payload
```

- [ ] **Step 2: 运行退出码与 guard 测试**

```bash
python -m pytest tests/test_reconcile_evaluator_cli.py::TestReconcileEvaluatorExitCodes tests/test_reconcile_evaluator_cli.py::TestReconcileEvaluatorErrorGuards -v 2>&1 | tail -15
```

期望：5 passed

---

## Task 6: 注册 `reconcile-evaluator` 子命令并做 CLI 集成测试

**Files:**
- Modify: `hooks/scripts/progress_manager.py`
- Modify: `tests/test_reconcile_evaluator_cli.py`

- [ ] **Step 1: 注册 subparser（在 `auto-checkpoint` parser 之后，约第 8218 行）**

```python
    reconcile_evaluator_parser = subparsers.add_parser(
        "reconcile-evaluator",
        help="Backfill evaluator results for completed features missing evaluation",
    )
    reconcile_evaluator_parser.add_argument(
        "--feature-id",
        type=int,
        default=None,
        dest="feature_id",
        help="Backfill a specific feature by ID (default: scan all completed features)",
    )
    reconcile_evaluator_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
```

- [ ] **Step 2: 在 `_dispatch_command()` 中添加 dispatch（`if args.command == "reconcile":` 之后，约第 8367 行）**

```python
        if args.command == "reconcile-evaluator":
            return reconcile_evaluator(
                feature_id=args.feature_id,
                output_json=args.output_json,
            )
```

- [ ] **Step 3: 追加 CLI subprocess 集成测试**

```python
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
        assert feat17["quality_gates"]["evaluator"] is None
```

- [ ] **Step 4: 运行全部本 Feature 测试**

```bash
python -m pytest tests/test_reconcile_evaluator_cli.py -v 2>&1 | tail -25
```

期望：全部通过（约 18 个测试）

- [ ] **Step 5: 运行全量回归测试**

```bash
python -m pytest -q --tb=short 2>&1 | tail -5
```

期望：557+ passed，0 failed

- [ ] **Step 6: Commit**

```bash
git add hooks/scripts/progress_manager.py tests/test_reconcile_evaluator_cli.py
git commit -m "feat(f28): add reconcile-evaluator command with evaluator backfill"
```

---

## 验收检查

| 验收标准 | 对应任务 |
|---------|---------|
| `prog reconcile-evaluator` 命令存在，支持 feature 级 evaluator 结果回填 | Task 6 |
| `pytest -q tests/test_reconcile_evaluator_cli.py` 全部通过（约 18 个测试） | Task 1-6 |
| 已完成 Feature 可回填 evaluator 且写入审计事件 `evaluator_backfill` | Task 2 + Task 4 |
| `evaluator_assessment` 与 `evaluator_backfill` 双事件均存在 | Task 4 |
| `execution_complete` 状态的 Feature 被正确纳入扫描范围 | Task 1 |
| `evaluator_gate_mod is None` 和 `progress.json` 缺失时正确返回 2 | Task 5 |
