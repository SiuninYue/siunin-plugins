# Parent-Child Route 同步：子插件 set_current/done 回写父 active_routes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **依赖**: F14 + F16 合并后实现。插入点 `set_current()` 和 `cmd_done()` 的最终形态取决于前两个 feature。实现前必须执行 Pre-implementation Checklist。
>
> **参见**: `docs/superpowers/plans/2026-04-24-f10-monorepo-mixed-host-v2.md` (F10 monorepo 架构) 和 `docs/superpowers/plans/2026-05-15-task-execution-semantics.md` (F14 task 执行语义，位于 worktree `feat+PT-F14-task-execution-semantics`)

**Goal:** 子插件在锁定 feature（`set_current`）和完成 feature（`cmd_done`）时自动同步父跟踪器的 `active_routes`，使 root dashboard 能直接定位活跃工作，消除队列扫描的 token 浪费。

**Architecture:** 扩展 `_notify_parent_sync()` 支持 route event（`activate`/`clear`），在 `set_current()` 后写父 route，在 `cmd_done()` 后清父 route。route 和 `linked_snapshot` 在同一个 `parent_data` 内存对象中更新 → 单次 save → 不出现状态分裂。新增 route preflight bootstrap 例外，允许子项目 `set-current` 在尚无父 route 时执行。

**Tech Stack:** Python 3.10+, 复用现有 `progress_manager.py` 的 `load_progress_json` / `save_progress_json` / `collect_git_context` / `_update_runtime_context`。

---

## Pre-implementation Checklist

> **必须在开始 Task 1 之前逐项完成并确认。** 这些检查项确保 plan 中的假设与 F14/F16 合并后的实际代码一致。

- [ ] `git checkout main && git pull` — 确保在最新 main 上工作
- [ ] 确认 F14 已合并：`git log --oneline main | grep -i "F14\|task.execution"`
- [ ] 确认 F16 已合并：`git log --oneline main | grep -i "F16\|squash.merge"`
- [ ] 读取 `set_current()` 完整函数体，对比 plan Task 3 中的"当前代码"，标注差异：`__________`
- [ ] 读取 `cmd_done()` 完整函数体，对比 plan Task 6 中的"当前代码"，标注差异：`__________`
- [ ] 读取 `enforce_route_preflight()` 完整函数体，对比 plan Task 4 中的"当前代码"，标注差异：`__________`
- [ ] 读取 `_notify_parent_sync()` 完整函数体，对比 plan Task 2 中的"当前代码"，标注差异：`__________`
- [ ] 读取 `next_feature()` 中 active_routes 写入段（约 L7358-7391），对比 plan Task 5，标注差异：`__________`
- [ ] 运行现有测试确认基线：`uv run pytest plugins/progress-tracker/tests/ -q --tb=short 2>&1 | tail -5`
- [ ] 确认 `test_parent_writeback.py` 是否已存在。如存在，记录现有测试列表：`__________`

**差异标注说明**: 如果上述任何读取与 plan 中的"当前代码"不一致，在对应 Task 的 margin 记录实际代码行号和差异，调整实现代码后再动手。

---

## 问题分析：为什么需要这个 Feature

### 当前 Root Dashboard 的队列扫描浪费

当用户在根目录运行 `/prog` 或新会话拿到 handoff block 时，`prog-next` 需要按 `routing_queue` 顺序逐个扫描：

```
routing_queue: ["ROOT", "NO", "PT", "SPM"]
```

即使 NO 和 SPM 都没有 pending feature（0/0），新会话仍然要：

1. 读 ROOT `progress.json` → 空，跳过
2. 读 NO `progress.json` → 空，跳过
3. 读 PT `progress.json`（43K tokens）→ 找到 F14

**前两步纯浪费 token。** 而根的 `active_routes` 其实已经记录了答案：

```json
"active_routes": [{
  "project_code": "PT",
  "feature_ref": "PT-F14",
  "branch": "main"
}]
```

### 根源：子项目不通知父 — 同步缺口表

| 子项目操作 | 是否通知父 | 方式 | 对应代码行 |
|-----------|-----------|------|-----------|
| `prog add-feature` | ✅ | `_notify_parent_sync()` → 刷新 `linked_snapshot` | L9560 |
| `prog done` | ✅ | `_notify_parent_sync()` → 刷新 `linked_snapshot` | L8651 |
| **`prog next` / `prog set-current`** | ❌ | **无通知** | — |
| `prog init` | ✅ | `_notify_parent_sync()` → 刷新 `linked_snapshot` | L5230 |

`prog next` 和 `set-current` 是启动 feature 工作的入口，但完全不通知父跟踪器。父不知道子项目开始了新工作，只能靠扫描发现。

### 关键发现：`/prog next` 的真实链路（Codex 确认）

Codex 分析确认了执行链路（`progress_manager.py:L12157-12166`）：

```
/prog next skill（SKILL.md:L142）
  → plugins/progress-tracker/prog next-feature --json    # 只 preview，不锁定
  → plugins/progress-tracker/prog set-current <feature_id> # 真正锁定 feature
  → set_current(feature_id)                                 # 写入 current_feature_id
```

**`next_feature()` 不直接锁定 feature，`set_current()` 才是锁定点。** 所以父 route 写回应挂在 `set_current()`，而不是 `next-feature` 的 preview 阶段。

### 五个缺口与修复策略

| 缺口 | 当前位置 | 修复策略 | 对应 Task |
|------|---------|---------|-----------|
| 子项目 set-current 不回写父 active_routes | `progress_manager.py:L6779` | 在 set_current 末尾调 `_notify_parent_sync(activate)` | Task 3 |
| 子项目 done 只刷新 snapshot，不清理 route | `progress_manager.py:L8651` | done 后调 `_notify_parent_sync(clear)` | Task 6 |
| 父 prog next 写的 feature_ref 是 F{id}，不够可路由 | `progress_manager.py:L7369` | 统一成 PT-F14 格式 | Task 5 |
| root dashboard handoff 无 active route fast path | `progress_manager.py:L5265` | 三态 handoff 输出 | Task 7 |
| `_notify_parent_sync()` 只写 linked_snapshot | `progress_manager.py:L1307` | 扩展 route_event 参数 | Task 2 |
| 无修复手段重建路由 | 新增 | `sync-linked --repair-routes` | Task 8 |

---

## Architecture Contract

1. `root.features[]` 只保存 root-level features，不复制子 feature。
2. 子项目 `features[]` 是子 feature 的**唯一事实源**。
3. `root.active_routes[]` 是当前活跃执行投影，不保存历史。
4. `root.linked_snapshot` 是展示投影，可从 child 状态重建。
5. done 后**移除** route，不保留 `status=done` 的僵尸 route。
6. 路由发现优先级：`active_routes` → `linked_snapshot` fallback → queue scan 最后手段。

---

## Data Contract — 统一 Route Entry

```json
{
  "project_code": "PT",
  "feature_ref": "PT-F14",
  "feature_id": 14,
  "feature_name": "Feature name",
  "child_project_root": "plugins/progress-tracker",
  "worktree_path": "/Users/siunin/Projects/Claude-Plugins",
  "branch": "main",
  "assigned_at": "2026-05-16T00:00:00Z",
  "updated_at": "2026-05-16T00:00:00Z",
  "status": "active",
  "source": "child_set_current"
}
```

**字段约束**:
- `feature_ref` 一律 `<PROJECT_CODE>-F<id>`，严禁裸 `F14`
- `project_code` 非空字符串，与 child `project_code` 一致
- `feature_id` 为整型
- `assigned_at` / `updated_at` 为 ISO-8601 UTC

**`source` 枚举**:
| 值 | 含义 |
|----|------|
| `"child_set_current"` | 子项目 `set_current()` 写入 |
| `"parent_next_dispatch"` | 父 `prog next` dispatch 写入 |
| `"sync_repair"` | `sync-linked --repair-routes` 重建 |

---

## File Map

| File | Change |
|------|--------|
| `plugins/progress-tracker/hooks/scripts/progress_manager.py` | 新增 5 helper + 修改 set_current/cmd_done/next_feature dispatch/enforce_route_preflight/_display_root_dashboard/_notify_parent_sync/sync_linked |
| `plugins/progress-tracker/skills/progress-status/SKILL.md` | 更新 root dashboard handoff 模板（3 种状态） |
| `plugins/progress-tracker/tests/test_parent_writeback.py` | 新增 24 个测试用例 |

---

## Task 1: 新增 Route Helper 函数（6 个独立函数）

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_parent_writeback.py`

**复杂度**: `simple` — 纯函数，无外部依赖，不修改现有逻辑。

### Context

这 6 个函数是后续所有 Task 的基础工具。插入位置建议在 `_notify_parent_sync()` 之前（约 L1300），与其他 route helper（如 `_normalize_project_code`、`_discover_parent_route_bindings_for_child`）放在同一区域。

关键依赖：
- `collect_git_context()` — 已在 `progress_manager.py` 中定义
- `collect_linked_project_statuses()` — 已在 `progress_manager.py` 中定义
- `LINKED_SNAPSHOT_SCHEMA_VERSION` — 已定义的常量
- `_iso_now()` — 已在 `progress_manager.py` 中定义

### Step 1: Write failing tests

Create `plugins/progress-tracker/tests/test_parent_writeback.py`:

```python
"""Tests for PT-F17: parent-child route writeback."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import sys
import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_child_data():
    return {
        "project_code": "PT",
        "tracker_role": "child",
        "parent_project_root": ".",
        "runtime_context": {
            "worktree_path": "/tmp/test-worktree",
            "branch": "feature/test-17",
        },
        "current_feature_id": 17,
        "features": [
            {
                "id": 17,
                "name": "Test Route Writeback",
                "completed": False,
                "deferred": False,
            }
        ],
    }


@pytest.fixture
def mock_parent_data():
    return {
        "tracker_role": "parent",
        "active_routes": [],
        "linked_projects": [
            {"project_code": "PT", "project_root": "plugins/progress-tracker"}
        ],
        "linked_snapshot": {
            "schema_version": "1.0",
            "updated_at": None,
            "projects": [],
        },
    }


# ---------------------------------------------------------------------------
# Task 1 tests
# ---------------------------------------------------------------------------

class TestFormatRouteFeatureRef:
    def test_simple(self):
        assert progress_manager._format_route_feature_ref("PT", 14) == "PT-F14"

    def test_different_code(self):
        assert progress_manager._format_route_feature_ref("NO", 3) == "NO-F3"

    def test_zero_id(self):
        assert progress_manager._format_route_feature_ref("PT", 0) == "PT-F0"


class TestBuildChildActiveRoute:
    def test_uses_runtime_context_priority(self, mock_child_data):
        feature = mock_child_data["features"][0]
        route = progress_manager._build_child_active_route(
            mock_child_data, feature, "plugins/test-plugin"
        )
        assert route["project_code"] == "PT"
        assert route["feature_ref"] == "PT-F17"
        assert route["feature_id"] == 17
        assert route["feature_name"] == "Test Route Writeback"
        assert route["child_project_root"] == "plugins/test-plugin"
        assert route["worktree_path"] == "/tmp/test-worktree"
        assert route["branch"] == "feature/test-17"
        assert route["status"] == "active"
        assert route["source"] == "child_set_current"
        assert "assigned_at" in route
        assert "updated_at" in route

    def test_falls_back_to_git_context_when_runtime_context_missing(self, mock_child_data):
        mock_child_data.pop("runtime_context")
        feature = mock_child_data["features"][0]
        with patch.object(progress_manager, "collect_git_context") as mock_git:
            mock_git.return_value = {
                "worktree_path": "/tmp/git-worktree",
                "branch": "main",
            }
            route = progress_manager._build_child_active_route(
                mock_child_data, feature, "plugins/test-plugin"
            )
        assert route["worktree_path"] == "/tmp/git-worktree"
        assert route["branch"] == "main"


class TestUpsertActiveRoute:
    def test_adds_to_empty(self, mock_parent_data):
        route = {"project_code": "PT", "feature_ref": "PT-F17"}
        progress_manager._upsert_active_route(mock_parent_data, route)
        assert len(mock_parent_data["active_routes"]) == 1
        assert mock_parent_data["active_routes"][0]["feature_ref"] == "PT-F17"

    def test_replaces_existing_same_code(self, mock_parent_data):
        mock_parent_data["active_routes"] = [
            {"project_code": "PT", "feature_ref": "PT-F14"}
        ]
        route = {"project_code": "PT", "feature_ref": "PT-F17"}
        progress_manager._upsert_active_route(mock_parent_data, route)
        assert len(mock_parent_data["active_routes"]) == 1
        assert mock_parent_data["active_routes"][0]["feature_ref"] == "PT-F17"

    def test_preserves_other_codes(self, mock_parent_data):
        mock_parent_data["active_routes"] = [
            {"project_code": "NO", "feature_ref": "NO-F3"}
        ]
        route = {"project_code": "PT", "feature_ref": "PT-F17"}
        progress_manager._upsert_active_route(mock_parent_data, route)
        assert len(mock_parent_data["active_routes"]) == 2
        codes = {r["project_code"] for r in mock_parent_data["active_routes"]}
        assert codes == {"PT", "NO"}


class TestRemoveActiveRoute:
    def test_removes_matching_code(self, mock_parent_data):
        mock_parent_data["active_routes"] = [
            {"project_code": "PT", "feature_ref": "PT-F14"},
            {"project_code": "NO", "feature_ref": "NO-F3"},
        ]
        progress_manager._remove_active_route(mock_parent_data, "PT")
        assert len(mock_parent_data["active_routes"]) == 1
        assert mock_parent_data["active_routes"][0]["project_code"] == "NO"

    def test_noop_when_code_not_found(self, mock_parent_data):
        mock_parent_data["active_routes"] = [
            {"project_code": "NO", "feature_ref": "NO-F3"}
        ]
        progress_manager._remove_active_route(mock_parent_data, "PT")
        assert len(mock_parent_data["active_routes"]) == 1

    def test_noop_on_empty_routes(self, mock_parent_data):
        progress_manager._remove_active_route(mock_parent_data, "PT")
        assert mock_parent_data["active_routes"] == []
```

### Step 2: Run tests — verify RED

```bash
cd <project_root>
python3 -m pytest plugins/progress-tracker/tests/test_parent_writeback.py -v 2>&1 | tail -30
```

Expected: All tests FAIL — functions not defined yet.

### Step 3: Implement 5 helper functions

Insert before `_notify_parent_sync()` (before L1307):

```python
def _format_route_feature_ref(project_code: str, feature_id: int) -> str:
    """Normalize route reference to <PROJECT_CODE>-F<id> form."""
    return f"{project_code}-F{feature_id}"


def _build_child_active_route(
    child_data: dict, feature: dict, child_project_root: str
) -> dict:
    """Build a unified active_route entry from child tracker state.

    Args:
        child_data: Child tracker progress.json data.
        feature: The feature dict being activated.
        child_project_root: Relative path from repo root to child plugin,
            computed via _serialize_project_root_for_config().

    Reads worktree_path / branch from runtime_context (priority)
    with fallback to collect_git_context().
    """
    rt = child_data.get("runtime_context") if isinstance(child_data, dict) else {}
    if not isinstance(rt, dict):
        rt = {}
    git_ctx = collect_git_context()
    project_code = str(child_data.get("project_code") or "")
    feature_id = feature["id"]

    return {
        "project_code": project_code,
        "feature_ref": _format_route_feature_ref(project_code, feature_id),
        "feature_id": feature_id,
        "feature_name": feature.get("name", ""),
        "child_project_root": child_project_root,
        "worktree_path": str(rt.get("worktree_path") or git_ctx.get("worktree_path", "")),
        "branch": str(rt.get("branch") or git_ctx.get("branch", "")),
        "assigned_at": _iso_now(),
        "updated_at": _iso_now(),
        "status": "active",
        "source": "child_set_current",
    }


def _upsert_active_route(parent_data: dict, route_entry: dict) -> None:
    """Insert or replace an active route keyed by project_code."""
    routes = parent_data.setdefault("active_routes", [])
    if not isinstance(routes, list):
        routes = []
        parent_data["active_routes"] = routes
    code = route_entry.get("project_code")
    # Guard: active_routes may contain non-dict entries from legacy data
    routes[:] = [
        r for r in routes
        if not (isinstance(r, dict) and r.get("project_code") == code)
    ]
    routes.append(route_entry)


def _remove_active_route(parent_data: dict, project_code: str) -> None:
    """Remove any active route matching project_code."""
    routes = parent_data.get("active_routes")
    if not isinstance(routes, list):
        return
    parent_data["active_routes"] = [
        r for r in routes
        if not (isinstance(r, dict) and r.get("project_code") == project_code)
    ]


def _refresh_parent_linked_snapshot(
    parent_data: dict, parent_root: str, repo_root: str
) -> None:
    """Refresh linked_snapshot.projects from current linked_project statuses."""
    active_routes = parent_data.get("active_routes") or []
    projects = collect_linked_project_statuses(
        parent_data,
        project_root=parent_root,
        active_routes=active_routes,
    )
    linked_snapshot = parent_data.get("linked_snapshot")
    if not isinstance(linked_snapshot, dict):
        linked_snapshot = {}
    linked_snapshot["schema_version"] = LINKED_SNAPSHOT_SCHEMA_VERSION
    linked_snapshot["updated_at"] = _iso_now()
    linked_snapshot["projects"] = projects
    parent_data["linked_snapshot"] = linked_snapshot
```

### Step 4: Run tests — verify GREEN

```bash
python3 -m pytest plugins/progress-tracker/tests/test_parent_writeback.py -v 2>&1 | tail -20
```

Expected: All 10 tests PASS.

### Step 5: Commit

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py plugins/progress-tracker/tests/test_parent_writeback.py
git commit -m "feat(PT-F17): add 6 route helper functions for parent-child writeback

_format_route_feature_ref, _build_child_active_route,
_upsert_active_route, _remove_active_route,
_refresh_parent_linked_snapshot.  All pure functions with tests."
```

---

## Task 2: 扩展 `_notify_parent_sync(route_event=None)`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_parent_writeback.py`

**复杂度**: `standard` — 修改现有函数，需保持向后兼容。

### Context — 当前代码 (L1307-L1357)

```python
def _notify_parent_sync() -> None:
    """Trigger parent linked_snapshot refresh after child state changes.

    Reads parent_project_root from the current child tracker.
    On any error (missing parent, invalid data), prints WARNING and returns.
    Never raises — always warn-only.
    """
    try:
        child_data = load_progress_json()
        if not isinstance(child_data, dict):
            return
        parent_raw = child_data.get("parent_project_root")
        if not parent_raw or not str(parent_raw).strip():
            return

        child_root = find_project_root().resolve()
        repo_root = Path(_REPO_ROOT or child_root).resolve()
        parent_root = _resolve_linked_project_root(
            str(parent_raw).strip(), child_root, repo_root
        )

        # Best-effort summary refresh before parent writeback
        try:
            load_status_summary_projection(str(child_root))
        except Exception as exc:
            logger.debug(f"Summary refresh failed during parent sync: {exc}")

        parent_data, err = _load_progress_payload_at_root(parent_root)
        if parent_data is None:
            print(
                f"[WARNING] Parent writeback skipped: cannot load parent tracker "
                f"at {parent_root}: {err}"
            )
            return

        active_routes = parent_data.get("active_routes") or []
        statuses = collect_linked_project_statuses(
            parent_data,
            project_root=parent_root,
            active_routes=active_routes,
        )

        linked_snapshot = parent_data.get("linked_snapshot")
        if not isinstance(linked_snapshot, dict):
            linked_snapshot = {}
        linked_snapshot["schema_version"] = LINKED_SNAPSHOT_SCHEMA_VERSION
        linked_snapshot["updated_at"] = _iso_now()
        linked_snapshot["projects"] = statuses
        parent_data["linked_snapshot"] = linked_snapshot

        _save_progress_payload_at_root(parent_root, parent_data)
    except Exception as exc:
        print(f"[WARNING] Parent writeback failed: {exc}")
```

### Step 1: Write failing tests

Append to `test_parent_writeback.py`:

```python
class TestNotifyParentSyncRouteEvent:
    """Test _notify_parent_sync with route_event parameter."""

    def test_no_route_event_keeps_existing_behavior(self, tmp_path, monkeypatch):
        """When route_event=None, only snapshot is refreshed — no route changes."""
        # Setup child
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "current_feature_id": 1,
            "features": [{"id": 1, "name": "F1", "completed": False}],
        }))

        # Setup parent
        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [
                {"project_code": "PT", "feature_ref": "PT-F99", "status": "active"}
            ],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
            "linked_snapshot": {
                "schema_version": "1.0",
                "updated_at": None,
                "projects": [],
            },
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(child_root)

        # route_event=None should NOT touch active_routes
        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = child_root
            try:
                progress_manager._notify_parent_sync(route_event=None)
            except Exception:
                pass  # We only care about side effects below

        parent_after = json.loads(parent_prog.read_text())
        # active_routes should still have the original entry
        assert len(parent_after.get("active_routes", [])) == 1
        # linked_snapshot should have been refreshed
        snap = parent_after.get("linked_snapshot", {})
        assert snap.get("updated_at") is not None

    def test_activate_upserts_route(self, tmp_path, monkeypatch):
        """route_event activate should upsert active route + refresh snapshot."""
        # Setup similar to above
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "current_feature_id": 1,
            "features": [{"id": 1, "name": "F1", "completed": False}],
        }))

        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
            "linked_snapshot": {
                "schema_version": "1.0",
                "updated_at": None,
                "projects": [],
            },
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(child_root)

        route = {
            "project_code": "PT",
            "feature_ref": "PT-F1",
            "feature_id": 1,
            "feature_name": "F1",
            "child_project_root": "child",
            "worktree_path": str(tmp_path),
            "branch": "main",
            "assigned_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "status": "active",
            "source": "child_set_current",
        }

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = child_root
            progress_manager._notify_parent_sync(
                route_event={"action": "activate", "route": route}
            )

        parent_after = json.loads(parent_prog.read_text())
        routes = parent_after.get("active_routes", [])
        assert len(routes) == 1
        assert routes[0]["feature_ref"] == "PT-F1"

    def test_clear_removes_route(self, tmp_path, monkeypatch):
        """route_event clear should remove matching route + refresh snapshot."""
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "current_feature_id": None,
            "features": [{"id": 1, "name": "F1", "completed": True}],
        }))

        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [
                {"project_code": "PT", "feature_ref": "PT-F1", "status": "active"}
            ],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
            "linked_snapshot": {
                "schema_version": "1.0",
                "updated_at": None,
                "projects": [],
            },
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(child_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = child_root
            progress_manager._notify_parent_sync(
                route_event={"action": "clear"}
            )

        parent_after = json.loads(parent_prog.read_text())
        routes = parent_after.get("active_routes", [])
        assert len(routes) == 0
```

### Step 2: Run tests — verify RED

```bash
python3 -m pytest plugins/progress-tracker/tests/test_parent_writeback.py::TestNotifyParentSyncRouteEvent -v
```

Expected: FAIL — `_notify_parent_sync()` doesn't accept `route_event` yet.

### Step 3: Implement

Modify `_notify_parent_sync()` signature and body:

```python
def _notify_parent_sync(route_event: Optional[dict] = None) -> None:
    """Trigger parent linked_snapshot refresh after child state changes.

    Args:
        route_event: Optional routing event.
            None (default) → refresh snapshot only (existing behavior).
            {"action": "activate", "route": <route_entry>} → upsert active_route + refresh snapshot.
            {"action": "clear"} → remove active_route for this child + refresh snapshot.

    Reads parent_project_root from the current child tracker.
    On any error (missing parent, invalid data), prints WARNING and returns.
    Never raises — always warn-only.
    """
    try:
        child_data = load_progress_json()
        if not isinstance(child_data, dict):
            return
        parent_raw = child_data.get("parent_project_root")
        if not parent_raw or not str(parent_raw).strip():
            return

        child_root = find_project_root().resolve()
        repo_root = Path(_REPO_ROOT or child_root).resolve()
        parent_root = _resolve_linked_project_root(
            str(parent_raw).strip(), child_root, repo_root
        )

        # Best-effort summary refresh before parent writeback
        try:
            load_status_summary_projection(str(child_root))
        except Exception as exc:
            logger.debug(f"Summary refresh failed during parent sync: {exc}")

        parent_data, err = _load_progress_payload_at_root(parent_root)
        if parent_data is None:
            print(
                f"[WARNING] Parent writeback skipped: cannot load parent tracker "
                f"at {parent_root}: {err}"
            )
            return

        # ——— NEW: route_event handling ———
        if route_event is not None and isinstance(route_event, dict):
            action = route_event.get("action")
            if action == "activate":
                route = route_event.get("route")
                if isinstance(route, dict):
                    _upsert_active_route(parent_data, route)
            elif action == "clear":
                child_code = str(child_data.get("project_code") or "")
                if child_code:
                    _remove_active_route(parent_data, child_code)
        # ——— END NEW ———

        active_routes = parent_data.get("active_routes") or []
        statuses = collect_linked_project_statuses(
            parent_data,
            project_root=parent_root,
            active_routes=active_routes,
        )

        linked_snapshot = parent_data.get("linked_snapshot")
        if not isinstance(linked_snapshot, dict):
            linked_snapshot = {}
        linked_snapshot["schema_version"] = LINKED_SNAPSHOT_SCHEMA_VERSION
        linked_snapshot["updated_at"] = _iso_now()
        linked_snapshot["projects"] = statuses
        parent_data["linked_snapshot"] = linked_snapshot

        _save_progress_payload_at_root(parent_root, parent_data)
    except Exception as exc:
        print(f"[WARNING] Parent writeback failed: {exc}")
```

Key: route 写入和 snapshot 刷新在同一个 `parent_data` 对象上完成，最后 `_save_progress_payload_at_root` 只调一次。不会出现状态分裂。

### Step 4: Run tests — verify GREEN

```bash
python3 -m pytest plugins/progress-tracker/tests/test_parent_writeback.py -v 2>&1 | tail -20
```

Expected: All 13 tests PASS (10 Task-1 + 3 Task-2).

### Step 5: Commit

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py plugins/progress-tracker/tests/test_parent_writeback.py
git commit -m "feat(PT-F17): extend _notify_parent_sync with route_event parameter

Support activate (upsert) and clear (remove) actions while
maintaining backward compatibility when route_event=None."
```

---

## Task 3: 修改 `set_current()` — 回写父 active_routes

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_parent_writeback.py`

**复杂度**: `standard` — 在 set_current 末尾加父通知逻辑。
**⚠ 此 Task 依赖 F14 合并后的代码形态。** 实现前必须执行 Pre-implementation Checklist 第 4 项。

### Context — 当前代码 (L6757-L6820)

```python
def set_current(feature_id):
    """Set the current feature being worked on."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)

    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    if _is_feature_deferred(feature):
        defer_reason = feature.get("defer_reason") or "Deferred feature"
        print(
            f"Feature ID {feature_id} is deferred and cannot be set as current: "
            f"{defer_reason}. Run `prog resume` first."
        )
        return False

    if not feature.get("completed", False):
        readiness_report = validate_feature_readiness(feature)
        if not readiness_report["valid"]:
            print_readiness_error(feature, readiness_report)
            return False
        if readiness_report["warnings"]:
            print_readiness_warnings(readiness_report)
            print("")

    previous_current_id = data.get("current_feature_id")
    data["current_feature_id"] = feature_id

    if not feature.get("completed", False):
        feature["development_stage"] = "developing"
        feature["lifecycle_state"] = "implementing"
        if not feature.get("started_at"):
            feature["started_at"] = _iso_now()

    if previous_current_id != feature_id:
        data.pop("workflow_state", None)
        if not feature.get("completed", False):
            data["workflow_state"] = {
                "phase": "planning",
                "updated_at": _iso_now()
            }

    if not feature.get("completed", False) and REVIEW_ROUTER_AVAILABLE:
        _initialize_reviews(feature)

    _update_runtime_context(data, source="set_current")
    save_progress_json(data)

    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    _auto_state_commit(f"F{feature_id}", "start")

    print(f"Set current feature: {feature.get('name', 'Unknown')}")
    return True
```

### Step 1: Write failing tests

Append to `test_parent_writeback.py`:

```python
class TestSetCurrentParentWriteback:
    """Test that set_current writes parent active_routes."""

    def test_set_current_upserts_parent_active_route(self, tmp_path, monkeypatch):
        """After set_current on a child, parent active_routes has the route."""
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "current_feature_id": None,
            "features": [
                {
                    "id": 1, "name": "Test Feature", "completed": False,
                    "deferred": False, "development_stage": "planning",
                    "lifecycle_state": "approved",
                    "requirement_ids": ["REQ-TEST"],
                    "change_spec": {"why": "Test readiness pass."},
                    "test_steps": ["echo ok"],
                    "acceptance_scenarios": ["Scenario: test"],
                }
            ],
        }))

        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.setattr(progress_manager, "REVIEW_ROUTER_AVAILABLE", False)
        monkeypatch.chdir(child_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = child_root
            result = progress_manager.set_current(1)

        assert result is True

        # Parent should now have active route
        parent_after = json.loads(parent_prog.read_text())
        routes = parent_after.get("active_routes", [])
        assert len(routes) >= 1
        pt_routes = [r for r in routes if r.get("project_code") == "PT"]
        assert len(pt_routes) == 1
        assert pt_routes[0]["feature_ref"] == "PT-F1"
        assert pt_routes[0]["status"] == "active"

    def test_set_current_noop_for_non_child_tracker(self, tmp_path, monkeypatch):
        """Standalone tracker (tracker_role != child) does not write parent route."""
        root = tmp_path / "standalone"
        root.mkdir()
        state = root / "docs" / "progress-tracker" / "state"
        state.mkdir(parents=True)
        prog = state / "progress.json"
        prog.write_text(json.dumps({
            "tracker_role": "standalone",
            "features": [
                {
                    "id": 1, "name": "Solo", "completed": False,
                    "deferred": False, "development_stage": "planning",
                    "lifecycle_state": "approved",
                    "requirement_ids": ["REQ-TEST"],
                    "change_spec": {"why": "Test readiness pass."},
                    "test_steps": ["echo ok"],
                    "acceptance_scenarios": ["Scenario: test"],
                }
            ],
        }))

        monkeypatch.setattr(progress_manager, "REVIEW_ROUTER_AVAILABLE", False)
        monkeypatch.chdir(root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = root
            result = progress_manager.set_current(1)

        assert result is True
        # No parent writeback attempted for standalone

    def test_set_current_warns_when_parent_missing(self, tmp_path, monkeypatch, capsys):
        """When parent progress.json is missing, set_current succeeds but warns."""
        child_root = tmp_path / "orphan"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "OR",
            "tracker_role": "child",
            "parent_project_root": "../nonexistent",
            "features": [
                {
                    "id": 1, "name": "Orphan", "completed": False,
                    "deferred": False, "development_stage": "planning",
                    "lifecycle_state": "approved",
                    "requirement_ids": ["REQ-TEST"],
                    "change_spec": {"why": "Test readiness pass."},
                    "test_steps": ["echo ok"],
                    "acceptance_scenarios": ["Scenario: test"],
                }
            ],
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.setattr(progress_manager, "REVIEW_ROUTER_AVAILABLE", False)
        monkeypatch.chdir(child_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = child_root
            result = progress_manager.set_current(1)

        assert result is True  # Must not block child operation
        captured = capsys.readouterr()
        assert "[WARNING]" in captured.out or "[WARNING]" in captured.err
```

### Step 2: Run tests — verify RED

```bash
python3 -m pytest plugins/progress-tracker/tests/test_parent_writeback.py::TestSetCurrentParentWriteback -v
```

Expected: FAIL — parent `active_routes` not updated after `set_current`.

### Step 3: Implement

At the end of `set_current()`, after `_auto_state_commit(...)` and before `print(...)` + `return True`:

```python
    _auto_state_commit(f"F{feature_id}", "start")

    # ——— NEW: Parent route writeback ———
    if (
        not feature.get("completed")
        and str(data.get("tracker_role") or "").strip().lower() == "child"
        and data.get("project_code")
        and data.get("parent_project_root")
    ):
        child_root_path = find_project_root().resolve()
        repo_root_path = Path(_REPO_ROOT or child_root_path).resolve()
        child_project_root = _serialize_project_root_for_config(
            child_root_path, repo_root_path
        )
        route_entry = _build_child_active_route(
            data, feature, str(child_project_root)
        )

        # Instant parallel-route warning
        try:
            parent_raw = data.get("parent_project_root")
            child_root = find_project_root().resolve()
            repo_root = Path(_REPO_ROOT or child_root).resolve()
            parent_root = _resolve_linked_project_root(
                str(parent_raw).strip(), child_root, repo_root
            )
            parent_data, _err = _load_progress_payload_at_root(parent_root)
            if isinstance(parent_data, dict):
                existing = parent_data.get("active_routes") or []
                other = [
                    r for r in existing
                    if r.get("project_code") != data["project_code"]
                ]
                if other:
                    for r in other:
                        print(
                            f"[WARNING] Existing active route "
                            f"{r.get('project_code')} -> {r.get('feature_ref')} "
                            f"is still active."
                        )
                    print(
                        f"[WARNING] Starting "
                        f"{_format_route_feature_ref(data['project_code'], feature_id)} "
                        f"will create parallel active routes. "
                        f"Run `prog route-status` from the parent to inspect."
                    )
        except Exception:
            pass  # warn-only; parent availability checked in _notify_parent_sync

        _notify_parent_sync(
            route_event={"action": "activate", "route": route_entry}
        )
    # ——— END NEW ———

    print(f"Set current feature: {feature.get('name', 'Unknown')}")
    return True
```

### Step 4: Run tests — verify GREEN

```bash
python3 -m pytest plugins/progress-tracker/tests/test_parent_writeback.py -v 2>&1 | tail -25
```

Expected: All 16 tests PASS (10 Task-1 + 3 Task-2 + 3 Task-3).

### Step 5: Commit

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py plugins/progress-tracker/tests/test_parent_writeback.py
git commit -m "feat(PT-F17): set_current writes parent active_routes on child trackers

Child set_current(feature_id) now calls _notify_parent_sync(activate)
when tracker_role=child with valid project_code and parent_project_root.
Instant parallel-route warning emitted before write."
```

---

## Task 4: Route Preflight — set-current Bootstrap 例外

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_parent_writeback.py`

**复杂度**: `standard` — 在 route preflight 的 fail-closed 逻辑中加例外路径。
**⚠ 此 Task 依赖 F14 Task 5（`next --done` lock exemption）的最终代码形态。** 实现前必须执行 Pre-implementation Checklist 第 6 项。

### Context — 当前代码 (L11223-L11292)

`enforce_route_preflight(command, argv)` 的流程：
1. 如果 `command in ROUTE_PREFLIGHT_EXEMPT_COMMANDS` → 放行
2. 如果 `tracker_role != "child"` → 放行
3. 如果 `project_code is None` → 拒绝
4. 如果无 `parent_bindings` → 拒绝
5. 如果多个 `parent_bindings` → 拒绝
6. 检查 parent 的 `active_routes` 是否有此 child 的 route → 无则拒绝

**问题**: `set-current` 在第 6 步会被挡住，因为此时父 route 还没有（要等 `set_current()` 执行后才写入）。这是一个鸡生蛋问题。

### Step 1: Write failing tests

Append to `test_parent_writeback.py`:

```python
class TestRoutePreflightBootstrap:
    """Test that set-current can execute without pre-existing active route."""

    def test_set_current_bootstrap_allowed(self, tmp_path, monkeypatch, capsys):
        """set-current as registered child must pass preflight even with no active route."""
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "features": [
                {"id": 1, "name": "F1", "completed": False, "deferred": False}
            ],
        }))

        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [],  # No route at all
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(child_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = child_root
            result = progress_manager.enforce_route_preflight(
                "set-current", ["set-current", "1"]
            )

        assert result is True, (
            "set-current must be allowed as bootstrap, even without active route"
        )

    def test_other_mutating_commands_still_blocked(self, tmp_path, monkeypatch):
        """Non-bootstrap commands without active route must still be blocked."""
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "features": [
                {"id": 1, "name": "F1", "completed": False}
            ],
        }))

        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(child_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = child_root
            result = progress_manager.enforce_route_preflight(
                "done", ["done"]
            )

        assert result is False, "done without active route must still be blocked"

    def test_bootstrap_warns_when_linked_projects_incomplete(self, tmp_path, monkeypatch, capsys):
        """When parent linked_projects lacks the child, bootstrap still allows but warns."""
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "NEW",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "features": [
                {"id": 1, "name": "F1", "completed": False}
            ],
        }))

        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
                # Note: NEW is NOT in linked_projects
            ],
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(child_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = child_root
            result = progress_manager.enforce_route_preflight(
                "set-current", ["set-current", "1"]
            )

        assert result is True
        captured = capsys.readouterr()
        assert "[WARNING]" in captured.out or "[WARNING]" in captured.err
```

### Step 3: Implement

In `enforce_route_preflight()`, after the `if command in ROUTE_PREFLIGHT_EXEMPT_COMMANDS` check, add:

```python
    # ——— NEW: bootstrap exception for set-current ———
    # set-current is the locking point where child trackers begin work.
    # At this point the parent active_route may not exist yet (chicken-egg).
    # Trust the child's own parent_project_root binding.
    if command == "set-current":
        child_bootstrap_data = load_progress_json()
        if isinstance(child_bootstrap_data, dict):
            role = str(
                child_bootstrap_data.get("tracker_role") or DEFAULT_TRACKER_ROLE
            ).strip().lower()
            code = child_bootstrap_data.get("project_code")
            parent_ref = child_bootstrap_data.get("parent_project_root")
            if role == "child" and code and parent_ref:
                # Warn if parent linked_projects is incomplete
                try:
                    child_proot = find_project_root().resolve()
                    repo = Path(_REPO_ROOT or child_proot).resolve()
                    parent_proot = _resolve_linked_project_root(
                        str(parent_ref).strip(), child_proot, repo
                    )
                    p_data, _err = _load_progress_payload_at_root(parent_proot)
                    if isinstance(p_data, dict):
                        linked = p_data.get("linked_projects")
                        if isinstance(linked, list):
                            if not any(
                                p.get("project_code") == code for p in linked
                            ):
                                print(
                                    f"[WARNING] Parent linked_projects does not "
                                    f"include {code}; active route written but "
                                    f"dashboard snapshot may be incomplete. "
                                    f"Run `prog link-project` or "
                                    f"`prog sync-linked --repair-routes`."
                                )
                except Exception:
                    pass
                return True  # Bootstrap: allow set-current
    # ——— END NEW ———
```

Insertion point: right before `data = load_progress_json()` at L11228.

### Step 4: Run tests — verify GREEN

```bash
python3 -m pytest plugins/progress-tracker/tests/test_parent_writeback.py -v 2>&1 | tail -25
```

Expected: All 19 tests PASS.

### Step 5: Commit

---

## Task 5: 修正父 `prog next` dispatch 写入格式

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_parent_writeback.py`

**复杂度**: `simple` — 扩展现有 ar_list.append 的 dict。

### Context — 当前代码 (L7367-L7373)

```python
ar_list.append({
    "project_code": code,
    "feature_ref": f"F{fid}",
    "feature_name": fname,
    "assigned_at": _iso_now(),
    "status": "active",
})
```

问题：`feature_ref` 写 `F14` 不是 `PT-F14`，缺少 `feature_id` 和 `child_project_root`。

### Step 1: Write failing test

```python
class TestParentDispatchFormat:
    def test_parent_dispatch_uses_project_qualified_feature_ref(self, tmp_path, monkeypatch):
        # ... setup parent/child similar to above, then trigger next_feature dispatch
        # Assert: written route has "feature_ref": "PT-F1", "feature_id": 1 (int)
        pass
```

### Step 3: Modified code

```python
# Resolve child_project_root from the dispatch result (available
# as part of the work_item selector output).
child_root_rel = dispatch_result.get("child_project_root", "")
git_ctx = collect_git_context()
ar_list.append({
    "project_code": code,
    "feature_ref": _format_route_feature_ref(code, fid),
    "feature_id": fid,
    "feature_name": fname,
    "child_project_root": str(child_root_rel),
    "worktree_path": git_ctx.get("worktree_path", ""),
    "branch": git_ctx.get("branch", ""),
    "assigned_at": _iso_now(),
    "updated_at": _iso_now(),
    "status": "active",
    "source": "parent_next_dispatch",
})
```

**注意**: 父 dispatch 时 `worktree_path` / `branch` 来源于 `collect_git_context()`，表示父跟踪器当前的 git 上下文，不是子项目的实际工作区。子项目的精确上下文由后续 `set_current()` 的 route upsert 更新。

---

## Task 6: 修改 `cmd_done()` — 清理父 active_routes

**⚠ 此 Task 高度依赖 F14 + F16 合并后的 cmd_done() 形态。** 实现前必须执行 Pre-implementation Checklist 第 5 项。

### Context — 当前代码 (L8651)

```python
    _notify_parent_sync()
```

改为：

```python
    _notify_parent_sync(route_event={"action": "clear"})
```

**插入点验证**:
- 此调用在 done 逻辑完全成功后（feature marked complete, sprint recorded, report path printed）
- F14 standalone task 的 `next --done` 路径走 `_close_current_task()` 不经过 `cmd_done()`，不会被误清
- 如果 F16 在 done 流程中加了 squash-merge，确保 `clear` 在 squash 成功后调用

### Test

```python
class TestChildDoneRouteCleanup:
    def test_child_done_removes_parent_active_route(self, tmp_path, monkeypatch):
        # Setup child with active feature + parent with matching active route
        # Call cmd_done()
        # Assert: parent active_routes no longer has PT entry
        pass
```

---

## Task 7: Root Dashboard Handoff 三态输出

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py` (`_display_root_dashboard()` near L5265)
- Modify: `plugins/progress-tracker/skills/progress-status/SKILL.md` (handoff 模板)

**核心逻辑**:

```python
def _render_root_dashboard_handoff(parent_data: dict, parent_root: str) -> str:
    active = parent_data.get("active_routes") or []
    # "active" means status is absent or anything except terminal states.
    # Legacy routes may have no "status" field at all — treat them as active.
    active = [
        r for r in active
        if isinstance(r, dict) and r.get("status") not in {"done", "cancelled"}
    ]

    if len(active) == 0:
        # Queue-based
        queue = parent_data.get("routing_queue", [])
        q_str = " -> ".join(queue)
        return f"""/progress-tracker:prog-next

Dashboard: Monorepo Root
Queue: {q_str}
ProjectRoot: {parent_root}
→ Context pre-loaded. Follows routing_queue for next dispatch."""

    if len(active) == 1:
        # Direct child resume
        r = active[0]
        return f"""/progress-tracker:prog-next

Route: {r['project_code']} -> {r['feature_ref']} "{r.get('feature_name', '')}"
Target: {r.get('child_project_root', '')}
Branch: {r.get('branch', '?')} | Workspace: {r.get('worktree_path', 'in-place')}
ProjectRoot: {parent_root}/{r.get('child_project_root', '')}
→ Context pre-loaded. Resume this child feature directly; do not rescan routing_queue."""

    # 2+: list + recommend by queue order
    queue = parent_data.get("routing_queue", [])
    route_map = {r["project_code"]: r for r in active}
    ordered_codes = [c for c in queue if c in route_map]
    recommended = ordered_codes[0] if ordered_codes else active[0]["project_code"]

    lines = ["/progress-tracker:prog-next", "", f"ParentRoot: {parent_root}", "ActiveRoutes:"]
    for r in active:
        lines.append(f"  - {r['project_code']} -> {r['feature_ref']} | {r.get('child_project_root', '')}")
    lines.append(f"RecommendedRoute: {recommended} -> {route_map[recommended]['feature_ref']} (按 routing_queue 顺序)")
    lines.append("→ Context pre-loaded. Multiple active routes exist; resume one explicitly, do not scan routing_queue.")
    return "\n".join(lines)
```

### Tests

| 测试 | 断言 |
|------|------|
| 0 active → queue-based output | output contains "Queue:" |
| 1 active → direct resume output | output contains "Route:" and "do not rescan" |
| 2+ active → list + recommend | output contains all routes + "RecommendedRoute:" |

---

## Task 8: `sync-linked --repair-routes`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_parent_writeback.py`

**复杂度**: `standard` — 扩展现有命令 + argparse。

### Context — 当前代码 (L1169-L1173)

```python
def sync_linked(
    output_json: bool = False,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
) -> bool:
    """Refresh and persist linked project status snapshot under linked_snapshot."""
```

### Step 1: Write failing tests

```python
class TestSyncLinkedRepairRoutes:
    def test_repair_rebuilds_from_child_current_feature(self, tmp_path, monkeypatch):
        """sync-linked --repair-routes adds active route from child's current_feature_id."""
        # Setup child with current_feature_id=1
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "current_feature_id": 1,
            "features": [
                {"id": 1, "name": "Active feature", "completed": False, "deferred": False}
            ],
            "runtime_context": {
                "worktree_path": str(child_root),
                "branch": "feature/test",
            },
        }))

        # Setup parent with empty active_routes but linked_projects including child
        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(parent_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = parent_root
            progress_manager.sync_linked(
                output_json=False, repair_routes=True
            )

        parent_after = json.loads(parent_prog.read_text())
        routes = parent_after.get("active_routes", [])
        pt_routes = [r for r in routes if r.get("project_code") == "PT"]
        assert len(pt_routes) == 1
        assert pt_routes[0]["feature_ref"] == "PT-F1"
        assert pt_routes[0]["source"] == "sync_repair"

    def test_repair_skips_completed_current_feature(self, tmp_path, monkeypatch):
        """If child's current_feature_id points to a completed feature, remove route."""
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "current_feature_id": 1,
            "features": [
                {"id": 1, "name": "Done", "completed": True, "deferred": False}
            ],
        }))

        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [
                {"project_code": "PT", "feature_ref": "PT-F1", "status": "active"}
            ],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(parent_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = parent_root
            progress_manager.sync_linked(
                output_json=False, repair_routes=True
            )

        parent_after = json.loads(parent_prog.read_text())
        pt_routes = [
            r for r in parent_after.get("active_routes", [])
            if r.get("project_code") == "PT"
        ]
        assert len(pt_routes) == 0  # Completed → removed

    def test_repair_without_flag_remains_snapshot_only(self, tmp_path, monkeypatch):
        """Without --repair-routes, active_routes is untouched."""
        child_root = tmp_path / "child"
        child_root.mkdir()
        child_state = child_root / "docs" / "progress-tracker" / "state"
        child_state.mkdir(parents=True)
        child_prog = child_state / "progress.json"
        child_prog.write_text(json.dumps({
            "project_code": "PT",
            "tracker_role": "child",
            "parent_project_root": "../parent",
            "current_feature_id": 1,
            "features": [
                {"id": 1, "name": "F1", "completed": False, "deferred": False},
            ],
        }))

        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        parent_state = parent_root / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)
        parent_prog = parent_state / "progress.json"
        parent_prog.write_text(json.dumps({
            "tracker_role": "parent",
            "active_routes": [
                {"project_code": "OLD", "feature_ref": "OLD-F99"}
            ],
            "linked_projects": [
                {"project_code": "PT", "project_root": "../child"}
            ],
        }))

        monkeypatch.setattr(progress_manager, "_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(parent_root)

        with patch.object(progress_manager, "find_project_root") as mock_root:
            mock_root.return_value = parent_root
            progress_manager.sync_linked(
                output_json=False, repair_routes=False
            )

        parent_after = json.loads(parent_prog.read_text())
        routes = parent_after.get("active_routes", [])
        # OLD route untouched; no NEW route added
        assert len(routes) == 1
        assert routes[0]["project_code"] == "OLD"
```

### Step 3: Implement

**3a. Modify `sync_linked()` signature**:

```python
def sync_linked(
    output_json: bool = False,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
    repair_routes: bool = False,
) -> bool:
    """Refresh and persist linked project status snapshot under linked_snapshot.

    Args:
        output_json: Emit JSON to stdout instead of human-readable text.
        stale_after_hours: Mark projects stale after this many hours.
        repair_routes: If True, rebuild active_routes from child trackers'
            current_feature_id before refreshing snapshot.
    """
```

**3b. Insert repair logic before the final snapshot write**:

```python
    # ——— NEW: repair-routes ———
    if repair_routes:
        linked = parent_data.get("linked_projects") or []
        for proj in linked:
            if not isinstance(proj, dict):
                continue
            child_root_rel = proj.get("project_root", "")
            if not child_root_rel:
                continue
            child_code = proj.get("project_code", "")
            child_abs = _resolve_linked_project_root(
                str(child_root_rel), parent_root, repo_root
            )
            child_data, _err = _load_progress_payload_at_root(child_abs)
            if not isinstance(child_data, dict):
                _remove_active_route(parent_data, child_code)
                continue
            cf_id = child_data.get("current_feature_id")
            if cf_id is None:
                _remove_active_route(parent_data, child_code)
                continue
            features = child_data.get("features") or []
            feature = next((f for f in features if f.get("id") == cf_id), None)
            if feature is None:
                _remove_active_route(parent_data, child_code)
                print(
                    f"[WARNING] {child_code}: current_feature_id={cf_id} "
                    f"not found in features; route removed."
                )
                continue
            if feature.get("completed") or feature.get("deferred"):
                _remove_active_route(parent_data, child_code)
                print(
                    f"[WARNING] {child_code}: feature {cf_id} is "
                    f"{'completed' if feature.get('completed') else 'deferred'}; "
                    f"route removed."
                )
                continue
            route = _build_child_active_route(
                child_data, feature,
                child_project_root=str(child_root_rel),
            )
            route["source"] = "sync_repair"
            _upsert_active_route(parent_data, route)
    # ——— END NEW ———

    active_routes = parent_data.get("active_routes") or []
    statuses = collect_linked_project_statuses(...)
```

**3c. Add argparse subcommand flag**:

In the CLI dispatch (where `sync-linked` is wired), add:

```python
sync_parser.add_argument(
    "--repair-routes",
    action="store_true",
    dest="repair_routes",
    help="Rebuild active_routes from child tracker current_feature_id before refreshing snapshot.",
)
```

### Step 4: JSON output when `output_json=True`

When `repair_routes=True` and `output_json=True`, emit:

```python
if output_json:
    print(json.dumps({
        "status": "ok",
        "repaired_routes": repair_routes,
        "active_routes": parent_data.get("active_routes", []),
    }, ensure_ascii=False))
```

### Step 5: Run tests — verify GREEN

```bash
python3 -m pytest plugins/progress-tracker/tests/test_parent_writeback.py -v 2>&1 | tail -25
```

Expected: All 22 tests PASS (previous 19 + 3 new Task-8).

---

## Task 9: 同步 `progress-status/SKILL.md`

更新 root dashboard handoff 模板：0/1/2+ active routes 三态输出，确保与 Task 7 的 CLI 输出一致。

---

## Task 10: 全量测试 + 回归

### 完整测试列表 (24 个)

| # | 测试 | Task |
|---|------|------|
| 1 | `test_format_route_feature_ref_simple` | T1 |
| 2 | `test_build_uses_runtime_context_priority` | T1 |
| 3 | `test_build_falls_back_to_git_context` | T1 |
| 4 | `test_upsert_adds_to_empty` | T1 |
| 5 | `test_upsert_replaces_existing_same_code` | T1 |
| 6 | `test_upsert_preserves_other_codes` | T1 |
| 7 | `test_remove_removes_matching_code` | T1 |
| 8 | `test_no_route_event_keeps_existing_behavior` | T2 |
| 9 | `test_activate_upserts_route` | T2 |
| 10 | `test_clear_removes_route` | T2 |
| 11 | `test_set_current_upserts_parent_active_route` | T3 |
| 12 | `test_set_current_noop_for_non_child_tracker` | T3 |
| 13 | `test_set_current_warns_when_parent_missing` | T3 |
| 14 | `test_set_current_bootstrap_allowed` | T4 |
| 15 | `test_other_mutating_commands_still_blocked` | T4 |
| 16 | `test_bootstrap_warns_when_linked_projects_incomplete` | T4 |
| 17 | `test_parent_dispatch_uses_project_qualified_feature_ref` | T5 |
| 18 | `test_child_done_removes_parent_active_route` | T6 |
| 19 | `test_dashboard_handoff_queue_when_zero_active` | T7 |
| 20 | `test_dashboard_handoff_direct_when_one_active` | T7 |
| 21 | `test_dashboard_handoff_lists_when_multiple_active` | T7 |
| 22 | `test_sync_linked_repair_rebuilds_from_child_current` | T8 |
| 23 | `test_sync_linked_repair_skips_completed_or_deferred` | T8 |
| 24 | `test_sync_linked_without_repair_remains_snapshot_only` | T8 |

### 回归命令

```bash
uv run pytest plugins/progress-tracker/tests/test_parent_writeback.py -q
uv run pytest plugins/progress-tracker/tests/test_dispatch_child_feature.py -q
uv run pytest plugins/progress-tracker/tests/test_route_commands.py -q
uv run pytest plugins/progress-tracker/tests/test_root_dashboard.py -q
uv run pytest plugins/progress-tracker/tests/test_sync_linked_command.py -q
```

---

## F14/F16 合并后适配注意事项

> **此节是预判性分析，实现 F17 时必须对照 F14/F16 的实际合并代码验证。**

### 1. `set_current()` 语义可能被 F14 改变

**当前假设**: `set_current(feature_id)` 只处理 feature 锁定。

**F14 可能带来的变化**: F14 引入 `current_task_id` 和 task 级别的激活。
- 对 **feature-bound task**：`set_current()` 是否仍被调用？如果是，钩子仍有效。
- 对 **standalone quick_task**：可能不走 `set_current()`（Task 3 守卫条件 `feature.get("completed")` 会正确跳过 task）。
- **需验证**: F14 合并后 `set_current()` 完整代码，确认 Task 3 的插入代码放置位置正确。

### 2. `cmd_done()` 执行路径分叉

F14/F16 后的三条关闭路径：

| 路径 | 函数 | 是否应清父 route |
|------|------|:---:|
| 关闭 standalone task | `_close_standalone_task()` | ❌ |
| 关闭 feature-bound task | `_close_feature_bound_task()` | ❌ |
| 完成 feature | `cmd_done()` | ✅ |

**实现时需确认**: `_notify_parent_sync(clear)` 放在 `cmd_done()` 成功路径末尾。standalone task 不走 `cmd_done()`，不会被误清。

### 3. Route Preflight 双重补丁合并

F14 Task 5（`next --done` lock exemption）和 F17 Task 4（`set-current` bootstrap）同时修改 `enforce_route_preflight()`。建议 F17 实现时基于 F14+F16 合并后的代码直接编写。

---

## Acceptance Criteria

1. 子项目 `prog set-current 14` 后，root `active_routes` 自动有 `PT → PT-F14`。
2. 子项目 `/prog done` 后，root `active_routes` 中 PT 条目被移除。
3. root `features[]` 仍为空或只含 root-level feature，不复制 child feature。
4. `set_current()` 的 `worktree_path` / `branch` 来源为 child `runtime_context` 或 `collect_git_context()` fallback。
5. `set-current` bootstrap 在 child 有 `parent_project_root` 时成功，即使父 `linked_projects` 不完整。
6. 多个 active route 时，dashboard/handoff 列出全部 + RecommendedRoute。
7. `set_current()` 在创建多项目活跃路由时即时 warn。
8. `sync-linked --repair-routes` 能从 child `current_feature_id` 重建 root route 投影，跳过 completed/deferred。
9. `progress-status` SKILL.md handoff 模板与 CLI dashboard 输出一致。
10. 全部 24 个测试 pass + 5 组回归 pass。
