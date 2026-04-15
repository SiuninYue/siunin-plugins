# F21: RouteV1 Worktree/Branch 一致性校验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当 `prog next-feature` 或 `prog done` 从错误的 worktree/branch 执行时，硬阻断并打印含 `route-select` 修复指令的错误提示。

**Architecture:** 扩展 `active_routes` 条目以记录 `worktree_path` 和 `branch`（在 `route-select` 中自动捕获）；新增 `check_worktree_branch_consistency()` 函数，在 `main()` 的命令分发前拦截 `next-feature` 和 `done` 命令，复用现有 `compare_contexts()` + `collect_git_context()` 基础设施。

**Tech Stack:** Python 3, pytest, progress_manager.py (单文件 ~8080 行), unittest.mock.patch

---

## File Map

| 操作 | 路径 | 职责 |
|------|------|------|
| Modify | `hooks/scripts/progress_manager.py` | 扩展 route_select()、新增一致性检查函数、挂入 main() |
| Modify | `tests/test_scope_fail_closed.py` | F21 验收测试 |
| Modify | `tests/test_route_commands.py` | 调整 route-select 断言以兼容新增字段 |

---

## Task 1: 扩展 `route_select()` 以记录 worktree_path 和 branch

**Files:**
- Modify: `hooks/scripts/progress_manager.py:1538-1544`
- Modify: `tests/test_route_commands.py`

### 目标
当 `route-select` 被调用时，自动将当前 worktree 路径和 git branch 写入 `active_routes` 条目。

- [ ] **Step 1: 写失败测试**

在 `tests/test_scope_fail_closed.py` 现有文件中追加第一个测试：

```python
"""
F21 验收测试：worktree/branch 一致性校验 (fail-closed)
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "scripts"))
import progress_manager


# ── 共用 fixture ────────────────────────────────────────────────────────────

def _make_progress(tmp_path, extra=None):
    """在 tmp_path 写入最小 progress.json，返回路径。"""
    data = {
        "project_name": "TestProj",
        "schema_version": "2.1",
        "features": [],
        "active_routes": [],
        "workflow_state": {},
        "tracker_role": "standalone",
    }
    if extra:
        data.update(extra)
    p = tmp_path / "docs" / "progress-tracker" / "state"
    p.mkdir(parents=True)
    (p / "progress.json").write_text(json.dumps(data))
    return tmp_path


# ── Task 1 测试 ─────────────────────────────────────────────────────────────

class TestRouteSelectRecordsWorktreeAndBranch:
    def test_route_select_stores_worktree_path_and_branch(self, tmp_path):
        """route_select() 应将当前 worktree_path 和 branch 写入 active_routes 条目。"""
        _make_progress(tmp_path)
        fake_git = {
            "workspace_mode": "worktree",
            "worktree_path": "/repo/.worktrees/feat-1",
            "project_root": "/repo",
            "cwd": "/repo/.worktrees/feat-1",
            "git_dir": None,
            "branch": "feature/1-test",
            "upstream": None,
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.route_select("MYPROJ")

        assert result is True
        data = json.loads((tmp_path / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        routes = data["active_routes"]
        assert len(routes) == 1
        entry = routes[0]
        assert entry["project_code"] == "MYPROJ"
        assert entry["worktree_path"] == "/repo/.worktrees/feat-1"
        assert entry["branch"] == "feature/1-test"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd plugins/progress-tracker
python3 -m pytest tests/test_scope_fail_closed.py::TestRouteSelectRecordsWorktreeAndBranch -v
```

预期: FAILED (KeyError 或 AssertionError，因为 worktree_path/branch 未写入条目)

- [ ] **Step 3: 修改 `route_select()` 添加 git 上下文捕获**

在 `hooks/scripts/progress_manager.py` 找到 `route_select()` 函数的第 1538 行（`upserted_entry` 构建处）：

```python
    upserted_entry: Dict[str, Any] = {"project_code": normalized_code, "feature_ref": final_ref}
    if existing_entry is not None:
        # Preserve extra fields (e.g. worktree_path, custom flags) from first match
        merged = dict(existing_entry)
        merged["project_code"] = normalized_code
        merged["feature_ref"] = final_ref
        upserted_entry = merged
```

替换为：

```python
    upserted_entry: Dict[str, Any] = {"project_code": normalized_code, "feature_ref": final_ref}
    if existing_entry is not None:
        # Preserve extra fields (e.g. worktree_path, custom flags) from first match
        merged = dict(existing_entry)
        merged["project_code"] = normalized_code
        merged["feature_ref"] = final_ref
        upserted_entry = merged

    # Record current worktree_path and branch for scope consistency checks (F21)
    _git_ctx = collect_git_context()
    upserted_entry["worktree_path"] = _git_ctx.get("worktree_path")
    upserted_entry["branch"] = _git_ctx.get("branch")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python3 -m pytest tests/test_scope_fail_closed.py::TestRouteSelectRecordsWorktreeAndBranch -v
```

预期: PASSED

- [ ] **Step 5: 同步更新既有 route-select 断言（兼容新增字段）**

在 `tests/test_route_commands.py` 中，避免对 `active_routes` 做“整对象全等”断言（因为 F21 会新增 `worktree_path`/`branch` 字段）。  
改为断言关键字段，例如：

```python
assert payload["active_routes"][0]["project_code"] == "NO"
assert payload["active_routes"][0]["feature_ref"] == "NO-F1"
```

- [ ] **Step 6: 确认回归无破坏**

```bash
python3 -m pytest tests/ -q --tb=short -x 2>&1 | tail -5
```

预期: 所有已有测试仍通过（509 passed 或更多）

- [ ] **Step 7: Commit**

```bash
git add hooks/scripts/progress_manager.py tests/test_scope_fail_closed.py
git commit -m "feat(F21): route_select records worktree_path and branch in active_routes"
```

---

## Task 2: 新增 `check_worktree_branch_consistency()` 函数

**Files:**
- Modify: `hooks/scripts/progress_manager.py` (在 `enforce_route_preflight` 之后插入新函数，约 7433 行后)

### 目标
新函数：读取 `workflow_state.execution_context`，与当前 git 上下文比对，不一致则打印 fail-closed 错误并返回 False。

- [ ] **Step 1: 写失败测试**

在 `tests/test_scope_fail_closed.py` 追加 Task 2 测试类：

```python
class TestCheckWorktreeBranchConsistency:
    """check_worktree_branch_consistency() 的单元测试。"""

    def _make_with_exec_context(self, tmp_path, branch, worktree_path):
        """构建含 execution_context 的 progress.json。"""
        return _make_progress(tmp_path, extra={
            "workflow_state": {
                "phase": "execution",
                "execution_context": {
                    "branch": branch,
                    "worktree_path": worktree_path,
                    "source": "set_workflow_state",
                },
            }
        })

    def test_returns_true_when_no_execution_context(self, tmp_path):
        """workflow_state 无 execution_context 时不阻断。"""
        _make_progress(tmp_path)
        with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                          str(tmp_path)):
            result = progress_manager.check_worktree_branch_consistency("next-feature")
        assert result is True

    def test_returns_true_when_context_matches(self, tmp_path):
        """worktree_path 和 branch 都匹配时不阻断。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {
            "worktree_path": "/repo/.worktrees/feat-21",
            "branch": "feature/21-test",
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("next-feature")
        assert result is True

    def test_returns_false_when_branch_mismatches(self, tmp_path, capsys):
        """branch 不匹配时阻断并打印错误。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {
            "worktree_path": "/repo/.worktrees/feat-21",
            "branch": "main",   # 错误的 branch
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("next-feature")
        assert result is False
        captured = capsys.readouterr()
        assert "route-select" in captured.out
        assert "BLOCKED" in captured.out or "branch" in captured.out.lower()

    def test_returns_false_when_worktree_path_mismatches(self, tmp_path, capsys):
        """worktree_path 不匹配时阻断并打印错误。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {
            "worktree_path": "/repo",   # 错误路径（非 worktree）
            "branch": "feature/21-test",
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("done")
        assert result is False
        captured = capsys.readouterr()
        assert "route-select" in captured.out

    def test_returns_false_when_both_mismatch(self, tmp_path, capsys):
        """branch 和 worktree_path 都不匹配时阻断。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {
            "worktree_path": "/repo",
            "branch": "main",
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("done")
        assert result is False

    def test_returns_false_when_expected_context_exists_but_current_context_missing(self, tmp_path):
        """expected 有 branch/worktree 约束，但 current 缺失上下文时也应 fail-closed。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {"worktree_path": None, "branch": None}
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("done")
        assert result is False

    def test_returns_true_when_execution_context_empty(self, tmp_path):
        """execution_context 存在但 branch/worktree_path 都为空时不阻断。"""
        _make_progress(tmp_path, extra={
            "workflow_state": {
                "phase": "planning",
                "execution_context": {},
            }
        })
        with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                          str(tmp_path)):
            result = progress_manager.check_worktree_branch_consistency("next-feature")
        assert result is True
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python3 -m pytest tests/test_scope_fail_closed.py::TestCheckWorktreeBranchConsistency -v
```

预期: FAILED (AttributeError: module 'progress_manager' has no attribute 'check_worktree_branch_consistency')

- [ ] **Step 3: 在 `progress_manager.py` 中实现 `check_worktree_branch_consistency()`**

在 `enforce_route_preflight` 函数结束处（约 7432 行的 `return True` 之后）插入新函数：

```python
def check_worktree_branch_consistency(command: str) -> bool:
    """
    Fail-closed check: verify current worktree/branch matches workflow_state.execution_context.

    Returns True if context matches or no constraint is recorded.
    Returns False (and prints recovery guidance) on mismatch.
    """
    data = load_progress_json()
    if not isinstance(data, dict):
        return True

    workflow_state = data.get("workflow_state")
    if not isinstance(workflow_state, dict):
        return True

    execution_context = workflow_state.get("execution_context")
    if not isinstance(execution_context, dict):
        return True

    expected_branch = execution_context.get("branch")
    expected_path = execution_context.get("worktree_path")

    # No constraint recorded yet — pass through
    if not expected_branch and not expected_path:
        return True

    current_ctx = collect_git_context()
    comparison = compare_contexts(
        expected=execution_context,
        current=current_ctx,
    )

    mismatch_statuses = {"mismatch", "path_mismatch", "branch_mismatch"}
    comparison_status = comparison.get("status")
    current_branch = current_ctx.get("branch")
    current_path = current_ctx.get("worktree_path")
    missing_required_current = bool(
        (expected_branch and not current_branch) or (expected_path and not current_path)
    )
    if comparison_status not in mismatch_statuses and not missing_required_current:
        return True

    # Hard block — print actionable recovery guidance
    print(f"[Scope Consistency] BLOCKED: {command} denied — worktree/branch mismatch.")
    print(f"  Expected branch:       {expected_branch or '(any)'}")
    print(f"  Current branch:        {current_ctx.get('branch') or '(unknown)'}")
    print(f"  Expected worktree:     {expected_path or '(any)'}")
    print(f"  Current worktree:      {current_ctx.get('worktree_path') or '(unknown)'}")
    print("Recovery:")
    print("  1. Switch to the correct worktree/branch, OR")
    print("  2. Re-register this session as the active route:")
    print("       plugins/progress-tracker/prog route-select --project <PROJECT_CODE>")
    return False
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python3 -m pytest tests/test_scope_fail_closed.py::TestCheckWorktreeBranchConsistency -v
```

预期: 7 passed

- [ ] **Step 5: 确认回归无破坏**

```bash
python3 -m pytest tests/ -q --tb=short -x 2>&1 | tail -5
```

预期: 全部通过

- [ ] **Step 6: Commit**

```bash
git add hooks/scripts/progress_manager.py tests/test_scope_fail_closed.py
git commit -m "feat(F21): add check_worktree_branch_consistency fail-closed guard"
```

---

## Task 3: 在 `main()` 中挂入一致性检查

**Files:**
- Modify: `hooks/scripts/progress_manager.py:8054-8056` (在 `_dispatch_command` 定义结束后、MUTATING_COMMANDS 检查前)

### 目标
`next-feature` 和 `done` 命令在实际执行前，先经过 `check_worktree_branch_consistency()` 校验。

- [ ] **Step 1: 写集成测试**

在 `tests/test_scope_fail_closed.py` 追加 Task 3 测试类：

```python
class TestMainConsistencyGate:
    """next-feature 和 done 命令的集成级阻断测试（通过 main() 路径）。"""

    def _make_with_exec_context(self, tmp_path, branch, worktree_path):
        data = {
            "project_name": "TestProj",
            "schema_version": "2.1",
            "features": [
                {
                    "id": 1,
                    "name": "Test Feature",
                    "test_steps": ["step1"],
                    "completed": False,
                    "deferred": False,
                    "development_stage": "developing",
                    "lifecycle_state": "implementing",
                }
            ],
            "active_routes": [],
            "workflow_state": {
                "phase": "execution",
                "execution_context": {
                    "branch": branch,
                    "worktree_path": worktree_path,
                    "source": "set_workflow_state",
                },
            },
            "current_feature_id": 1,
            "tracker_role": "standalone",
        }
        p = tmp_path / "docs" / "progress-tracker" / "state"
        p.mkdir(parents=True)
        (p / "progress.json").write_text(json.dumps(data))
        return tmp_path

    def test_next_feature_blocked_on_branch_mismatch(self, tmp_path, capsys):
        """main() 中 next-feature 在 branch 不匹配时返回 1（被阻断）。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", None)
        fake_git = {"worktree_path": None, "branch": "main"}
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
            patch("sys.argv", ["prog", "next-feature"]),
        ):
            result = progress_manager.main()
        assert result == 1
        captured = capsys.readouterr()
        assert "route-select" in captured.out

    def test_done_blocked_on_worktree_mismatch(self, tmp_path, capsys):
        """main() 中 done 在 worktree 不匹配时返回 1（被阻断）。"""
        self._make_with_exec_context(tmp_path, None, "/repo/.worktrees/feat-21")
        fake_git = {"worktree_path": "/repo", "branch": "main"}
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
            patch("sys.argv", ["prog", "done"]),
        ):
            result = progress_manager.main()
        assert result == 1
        captured = capsys.readouterr()
        assert "route-select" in captured.out

    def test_next_feature_passes_when_context_matches(self, tmp_path, capsys):
        """branch 匹配时 next-feature 正常执行（不被阻断）。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", None)
        fake_git = {"worktree_path": None, "branch": "feature/21-test"}
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         str(tmp_path)),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
            patch("sys.argv", ["prog", "next-feature"]),
        ):
            result = progress_manager.main()
        # 结果是 ok 或无 feature 均可，关键是不返回 1
        assert result != 1
        captured = capsys.readouterr()
        assert "BLOCKED" not in captured.out
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python3 -m pytest tests/test_scope_fail_closed.py::TestMainConsistencyGate -v
```

预期: FAILED（next-feature 和 done 尚未被拦截）

- [ ] **Step 3: 在 `main()` 插入一致性检查**

找到 `progress_manager.py` 中 `_dispatch_command` 定义的末尾（约 8054 行 `return 1`），和 `if args.command in MUTATING_COMMANDS:` 之前（约 8056 行）。

在这两行之间插入：

```python
    # F21: fail-closed scope consistency check for next-feature and done
    if args.command in {"next-feature", "done"}:
        if not check_worktree_branch_consistency(args.command):
            return 1
```

修改后该区域应为：

```python
        parser.print_help()
        return 1

    # F21: fail-closed scope consistency check for next-feature and done
    if args.command in {"next-feature", "done"}:
        if not check_worktree_branch_consistency(args.command):
            return 1

    if args.command in MUTATING_COMMANDS:
        if not enforce_route_preflight(args.command, sys.argv):
            return 1
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python3 -m pytest tests/test_scope_fail_closed.py::TestMainConsistencyGate -v
```

预期: 3 passed

- [ ] **Step 5: 运行全部 F21 测试**

```bash
python3 -m pytest tests/test_scope_fail_closed.py -v
```

预期: 11 passed (Task 1: 1 + Task 2: 7 + Task 3: 3)

- [ ] **Step 6: 确认回归无破坏**

```bash
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

预期: 全部通过（509+ passed）

- [ ] **Step 7: 运行 F21 验收测试命令**

```bash
python3 -m pytest -q tests/test_scope_fail_closed.py
```

预期: 11 passed

- [ ] **Step 8: Commit**

```bash
git add hooks/scripts/progress_manager.py tests/test_scope_fail_closed.py
git commit -m "feat(F21): hook check_worktree_branch_consistency into main() for next-feature and done"
```

---

## Self-Review

### Spec Coverage

| 验收场景 | 对应任务 |
|----------|---------|
| `active_routes 记录 worktree_path/branch` | Task 1 (route_select 扩展 + 测试) |
| `在错误 worktree 执行 /prog-next 时阻断并提示 route-select` | Task 2 (函数) + Task 3 (main 挂载) |
| `在错误 worktree 执行 /prog-done 时阻断并提示 route-select` | Task 2 + Task 3 |
| `pytest -q tests/test_scope_fail_closed.py` 通过 | Task 3 Step 7 |

### 类型一致性

- `check_worktree_branch_consistency(command: str) -> bool` — Task 2 Step 3 定义，Task 3 Step 3 调用 ✓
- `collect_git_context()` 返回 `Dict[str, Any]`，含 `worktree_path`/`branch` ✓
- `compare_contexts(expected, current)` 返回含 `status` 字段的 dict ✓

### Placeholder 扫描

无 TBD/TODO/填写细节等占位符。所有代码均为完整实现。
