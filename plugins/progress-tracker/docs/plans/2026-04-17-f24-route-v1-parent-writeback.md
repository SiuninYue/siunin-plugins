# F24 [RouteV1] 在 prog-init/prog-plan 与子项目完成时回写父级备案 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 子项目在 `link-project`、`init`、`add-feature`、`done` 时自动触发父级 `sync-linked`，父级 `linked_snapshot` 实时感知子项目变更；`parent_project_root` 由 `link-project` 写入子项目，供反向查找。

**Architecture:** (1) `link_project()` 向子项目写入 `parent_project_root`（repo-relative）。(2) 新增 `_notify_parent_sync()` 辅助函数：读取子项目 `parent_project_root`，加载父级 data，调用 `collect_linked_project_statuses()` + `_save_progress_payload_at_root()` 刷新父级快照；所有异常 warn-only 不阻断。(3) `init_tracking()`、`add_feature()`、`cmd_done()` 末尾各调用 `_notify_parent_sync()`。

**Tech Stack:** Python 3, pytest, `progress_manager.py` monolith

**Working directory for all commands:** `/Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f24-route-v1-parent-writeback`

## Execution Preconditions (Read Before Running)

- Any pytest command targeting `plugins/progress-tracker/tests/test_parent_writeback.py` requires **Task 1 Step 1** to be completed first (file must exist).
- `add-feature` CLI signature is positional: `add-feature <name> <test_steps...>` (do not use `--name/--test-steps`).
- `done` CLI signature only accepts `--commit`, `--run-all`, `--skip-archive` (do not use `--feature-id`).
- For `cmd_done` test fixtures, ensure done gate preconditions are satisfied:
  - `current_feature_id` is present and matches an existing integer `feature.id`
  - `workflow_state.phase == "execution_complete"`
  - Prefer `test_steps: []` in fixture to avoid executing external shell commands
  - Use `--skip-archive` in test command to reduce side effects

---

## File Map

| File | Change |
|------|--------|
| `plugins/progress-tracker/hooks/scripts/progress_manager.py` | `link_project()` 写 `parent_project_root`；新增 `_notify_parent_sync()`；`init_tracking()` / `add_feature()` / `cmd_done()` 末尾 hook |
| `plugins/progress-tracker/tests/test_parent_writeback.py` | 新建，覆盖 parent_project_root 写入与 notify 回调行为 |

---

### Task 1: TDD — link-project 后子项目含 parent_project_root

**Files:**
- Create: `plugins/progress-tracker/tests/test_parent_writeback.py`

- [ ] **Step 1: 创建新测试文件，写第一个失败测试**

```python
"""Tests for F24 parent writeback on link-project / init / add-feature / done."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import progress_manager


def _write_progress(root: Path, payload: dict) -> None:
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _read_progress(root: Path) -> dict:
    return json.loads(
        (root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )


def test_link_project_writes_parent_project_root_to_child(temp_dir, capsys):
    """After link-project, child progress.json should contain parent_project_root."""
    import os as _os
    _os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "linked_projects": [],
            "linked_snapshot": {"projects": []},
            "active_routes": [],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
        },
    )

    os.chdir(repo_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "link-project",
            "--parent-root",
            "plugins/progress-tracker",
            "--code",
            "NO",
        ],
    ):
        assert progress_manager.main() is True

    child_data = _read_progress(child_root)
    assert "parent_project_root" in child_data
    # should be a relative path pointing at the parent
    parent_raw = child_data["parent_project_root"]
    assert "progress-tracker" in parent_raw
```

- [ ] **Step 2: 运行，确认 FAIL**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f24-route-v1-parent-writeback
pytest plugins/progress-tracker/tests/test_parent_writeback.py::test_link_project_writes_parent_project_root_to_child --tb=short -v
```

Expected: FAIL — `AssertionError: assert "parent_project_root" in child_data`

---

### Task 2: 实现 link_project() 写入 parent_project_root

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:1304-1306`

- [ ] **Step 1: 在 child_data 赋值块末尾追加 parent_project_root**

找到约 line 1304–1306：
```python
    child_data["tracker_role"] = "child"
    child_data["project_code"] = normalized_code
    _save_progress_payload_at_root(child_root, child_data)
```

改为：
```python
    child_data["tracker_role"] = "child"
    child_data["project_code"] = normalized_code
    child_data["parent_project_root"] = _serialize_project_root_for_config(parent_root, repo_root)
    _save_progress_payload_at_root(child_root, child_data)
```

- [ ] **Step 2: 运行 Task 1 测试，确认 PASS**

```bash
pytest plugins/progress-tracker/tests/test_parent_writeback.py::test_link_project_writes_parent_project_root_to_child --tb=short -v
```

Expected: PASS

- [ ] **Step 3: 运行已有 link-project 测试，确认无回归**

```bash
pytest plugins/progress-tracker/tests/test_sync_linked_command.py -k "link_project" --tb=short -q
```

Expected: all pass

---

### Task 3: TDD — _notify_parent_sync() 触发父级快照刷新

**Files:**
- Modify: `plugins/progress-tracker/tests/test_parent_writeback.py`

- [ ] **Step 1: 追加三个失败测试**

在文件末尾追加：

```python
def test_notify_parent_sync_updates_linked_snapshot_after_add_feature(temp_dir, capsys):
    """add-feature on child should trigger parent linked_snapshot refresh."""
    import os as _os
    _os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "parent",
            "linked_projects": [
                {"project_root": "plugins/note-organizer", "project_code": "NO", "label": "NO"}
            ],
            "linked_snapshot": {"projects": []},
            "active_routes": [{"project_code": "NO"}],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "child",
            "project_code": "NO",
            "parent_project_root": "plugins/progress-tracker",
        },
    )

    os.chdir(repo_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "add-feature",
            "My Feature",
            "run pytest",
        ],
    ):
        assert progress_manager.main() is True

    # Parent snapshot should now reflect child's 1 feature
    parent_data = _read_progress(parent_root)
    projects = parent_data.get("linked_snapshot", {}).get("projects", [])
    assert len(projects) == 1
    assert projects[0]["total"] == 1
    assert projects[0]["completed"] == 0


def test_notify_parent_sync_updates_snapshot_after_init(temp_dir, capsys):
    """init on child (when parent_project_root is pre-set) triggers parent snapshot refresh."""
    import os as _os
    _os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "linked_projects": [
                {"project_root": "plugins/note-organizer", "project_code": "NO", "label": "NO"}
            ],
            "linked_snapshot": {"projects": []},
            "active_routes": [],
        },
    )
    # Child already exists with parent_project_root (from prior link-project)
    _write_progress(
        child_root,
        {
            "project_name": "Old Name",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "child",
            "project_code": "NO",
            "parent_project_root": "plugins/progress-tracker",
        },
    )

    os.chdir(repo_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "init",
            "Note Organizer v2",
            "--force",
        ],
    ):
        assert progress_manager.main() is True

    parent_data = _read_progress(parent_root)
    projects = parent_data.get("linked_snapshot", {}).get("projects", [])
    # snapshot should have been refreshed (project still listed, 0 features)
    assert len(projects) == 1
    assert projects[0]["total"] == 0


def test_notify_parent_sync_warn_only_when_parent_missing(temp_dir, capsys):
    """If parent_project_root points to a missing tracker, warn-only, do not block."""
    import os as _os
    _os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    child_root = repo_root / "plugins" / "note-organizer"
    child_root.mkdir(parents=True, exist_ok=True)

    # Parent does NOT exist — only child exists.
    # tracker_role is intentionally NOT set to "child" so that route preflight
    # does not block add-feature (preflight only applies to tracker_role=child).
    # The purpose of this test is to verify _notify_parent_sync warn-only behaviour,
    # which is triggered by parent_project_root alone regardless of tracker_role.
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "parent_project_root": "plugins/progress-tracker",  # parent absent
        },
    )

    os.chdir(repo_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "add-feature",
            "My Feature",
            "run pytest",
        ],
    ):
        result = progress_manager.main()

    # add-feature must succeed even though parent writeback fails
    assert result is True
    output = capsys.readouterr().out
    assert "WARNING" in output or "warning" in output.lower() or "parent" in output.lower()
```

- [ ] **Step 2: 运行，确认所有 3 个失败**

```bash
pytest plugins/progress-tracker/tests/test_parent_writeback.py \
  -k "notify" --tb=short -v
```

Expected: 3 FAILED (snapshot not updated, or `WARNING` not found)

---

### Task 4: 实现 _notify_parent_sync() 辅助函数

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

在 `link_project()` 函数定义（line 1185）**之前**，插入新函数（约在 line 1183）：

- [ ] **Step 1: 在 `_save_progress_payload_at_root` 之后、`link_project` 之前插入函数**

找到：
```python
def link_project(
    child_project_root: Optional[str],
```

在它之前插入：

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
        parent_root = _resolve_linked_project_root(str(parent_raw).strip(), child_root, repo_root)

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

        # NOTE: No explicit file lock is acquired on the parent tracker.
        # This is safe under the single-writer assumption: the CLI is invoked
        # sequentially from a single shell session. If concurrent invocations
        # become a requirement, replace this with an explicit-root lock.
        _save_progress_payload_at_root(parent_root, parent_data)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARNING] Parent writeback failed: {exc}")


```

- [ ] **Step 2: 运行 Task 3 测试，确认通过**

```bash
pytest plugins/progress-tracker/tests/test_parent_writeback.py \
  -k "notify" --tb=short -v
```

Expected: 3 PASSED

---

### Task 5: 在 init_tracking() 和 add_feature() 末尾 hook

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

#### 5A: init_tracking()

- [ ] **Step 1: 在 init_tracking() 中保留父级绑定字段（约 line 3708 附近）**

`init_tracking()` 构建全新 `data` dict，会丢失 `parent_project_root / tracker_role / project_code`。
需要在 `save_progress_json(data)` **之前**读取旧数据并回写这三个字段。

找到（约 line 3706–3708）：
```python
        "current_feature_id": None,
    }

    save_progress_json(data)
```

改为：
```python
        "current_feature_id": None,
    }

    # Preserve parent binding fields so _notify_parent_sync() can locate the parent
    # after re-initialization (these fields are written by link-project and must survive init).
    _prior_payload = load_progress_json() or {}
    for _field in ("parent_project_root", "tracker_role", "project_code"):
        if _field in _prior_payload:
            data[_field] = _prior_payload[_field]

    save_progress_json(data)
```

- [ ] **Step 2: 找到 init_tracking() 的 return True（约 line 3727），在其前插入 notify**

找到：
```python
    if features:
        print(f"Added {len(features)} features")
    return True
```

改为：
```python
    if features:
        print(f"Added {len(features)} features")
    _notify_parent_sync()
    return True
```

#### 5B: add_feature()

- [ ] **Step 3: 找到 add_feature() 的 return True（约 line 6501），在其前插入 notify**

找到：
```python
    print(f"Added feature: {name} (ID: {new_id})")
    return True
```

改为：
```python
    print(f"Added feature: {name} (ID: {new_id})")
    _notify_parent_sync()
    return True
```

- [ ] **Step 4: 运行全量 test_parent_writeback.py 测试**

```bash
pytest plugins/progress-tracker/tests/test_parent_writeback.py --tb=short -v
```

Expected: 4 PASSED（含 Task 1 的 link-project 测试）

---

### Task 6: TDD — cmd_done 触发父级快照刷新

**Files:**
- Modify: `plugins/progress-tracker/tests/test_parent_writeback.py`

- [ ] **Step 1: 追加 cmd_done 失败测试**

在写测试前，先逐条核对 done gate 前置条件（否则命令会在 `_validate_done_preconditions()` 被拦截，无法覆盖 parent writeback）：

1. `current_feature_id` 存在，且等于某个 feature 的整数 `id`
2. `workflow_state.phase` 设置为 `"execution_complete"`
3. `features[*].test_steps` 设为空列表 `[]`（避免测试里执行外部命令）
4. 命令行使用 `done --commit <hash> --skip-archive`

在文件末尾追加：

```python
def test_notify_parent_sync_updates_snapshot_after_done(temp_dir, capsys):
    """prog-done on child should trigger parent linked_snapshot refresh with updated completion."""
    import os as _os
    _os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "parent",
            "linked_projects": [
                {"project_root": "plugins/note-organizer", "project_code": "NO", "label": "NO"}
            ],
            "linked_snapshot": {"projects": []},
            "active_routes": [{"project_code": "NO"}],
        },
    )
    feature_id = 1  # integer, matching add_feature's auto-generated ID scheme
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [
                {
                    "id": feature_id,
                    "name": "My Feature",
                    # test_steps is intentionally empty so _run_acceptance_tests
                    # short-circuits to (True, []) without executing any shell command.
                    "test_steps": [],
                    "completed": False,
                    "deferred": False,
                    "defer_reason": None,
                    "deferred_at": None,
                    "defer_group": None,
                }
            ],
            "current_feature_id": feature_id,
            # workflow_state.phase must equal "execution_complete" to pass
            # _validate_done_preconditions; any other value blocks the command.
            "workflow_state": {"phase": "execution_complete"},
            "tracker_role": "child",
            "project_code": "NO",
            "parent_project_root": "plugins/progress-tracker",
            "active_routes": [{"project_code": "NO"}],
        },
    )

    os.chdir(repo_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "done",
            "--commit",
            "abc1234",
            "--skip-archive",
        ],
    ):
        result = progress_manager.main()

    assert result == 0
    parent_data = _read_progress(parent_root)
    projects = parent_data.get("linked_snapshot", {}).get("projects", [])
    assert len(projects) == 1
    assert projects[0]["completed"] == 1
```

- [ ] **Step 2: 运行，确认 FAIL**

```bash
pytest plugins/progress-tracker/tests/test_parent_writeback.py::test_notify_parent_sync_updates_snapshot_after_done --tb=short -v
```

Expected: FAIL — snapshot 未更新

---

### Task 7: 在 cmd_done() 末尾 hook

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:5780-5789`

- [ ] **Step 1: 找到 cmd_done() 成功返回块（约 line 5780-5789），在 return 0 前插入 notify**

找到：
```python
    print(f"[DONE] Feature {feature_id} completed")
    if resolved_commit:
        print(f"[DONE] Commit: {resolved_commit}")
    if report_path:
        try:
            relative_report = report_path.relative_to(find_project_root())
        except ValueError:
            relative_report = report_path
        print(f"[DONE] Report: {relative_report}")
    return 0
```

改为：
```python
    print(f"[DONE] Feature {feature_id} completed")
    if resolved_commit:
        print(f"[DONE] Commit: {resolved_commit}")
    if report_path:
        try:
            relative_report = report_path.relative_to(find_project_root())
        except ValueError:
            relative_report = report_path
        print(f"[DONE] Report: {relative_report}")
    _notify_parent_sync()
    return 0
```

- [ ] **Step 2: 运行 test_parent_writeback.py 全量**

```bash
pytest plugins/progress-tracker/tests/test_parent_writeback.py --tb=short -v
```

Expected: 5 PASSED（含 Task 6 新增 done 测试）

---

### Task 8: 全量回归测试

- [ ] **Step 1: 运行全量测试套件**

```bash
pytest plugins/progress-tracker/tests/ --tb=short -q
```

Expected: 557 passed（原 552 + 新 5），无 regression

- [ ] **Step 2: 运行 test_integration.py 验收**

```bash
pytest plugins/progress-tracker/tests/test_integration.py --tb=short -q
```

Expected: all pass

---

### Task 9: Commit

- [ ] **Step 1: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f24-route-v1-parent-writeback
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_parent_writeback.py
git commit -m "feat(f24): parent writeback on link-project/init/add-feature/done"
```

---

## Self-Review

**Spec coverage:**
- ✅ `link-project` 写 `parent_project_root` → Task 2
- ✅ `prog-init` 后同步父级快照 → Task 5A (`init_tracking` hook)
- ✅ `prog-plan`（= `add-feature`）后同步父级快照 → Task 5B
- ✅ `prog-done` 后同步父级完成率与 `active_feature_ref` → Task 7
- ✅ 父级 `linked_snapshot` 通过 `collect_linked_project_statuses()` 刷新（复用 F23）→ Task 4
- ✅ 容错 warn-only → Task 4 + Task 3 第三个测试
- ✅ `pytest test_integration.py` → Task 8 Step 2

**Placeholder scan:** 无 TBD / TODO / placeholder。

**Type consistency:**
- `_notify_parent_sync()` 无参数，返回 None，调用点均在 return 前 — 一致
- `collect_linked_project_statuses(parent_data, project_root=parent_root, active_routes=...)` — 与 F23 签名一致（`project_root: Optional[Path]`）
- `_save_progress_payload_at_root(parent_root, parent_data)` — 与现有调用一致
- `_load_progress_payload_at_root(parent_root)` returns `Tuple[Optional[dict], Optional[str]]` — 正确处理
