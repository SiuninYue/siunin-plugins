# plan_path 归一化：CLI 入口层修复

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `set-workflow-state --plan-path` 在用户传入含 project root 前缀的路径时报错的问题，同时在 CLI 入口层做路径归一化，保持 `validate_plan_path` 验证函数纯净。

**Architecture:** 归一化逻辑放在 `set_workflow_state` 函数开头（CLI 入口层），显式接收 `project_root` 参数；优先用 `Path.resolve() + relative_to()` 处理绝对路径（语义级路径操作），fallback 到字符串前缀匹配；`validate_plan_path` 保持纯验证职责不变。

**Tech Stack:** Python 3.x, pathlib

---

## 设计决策（已确认）

- **归一化位置**：CLI 入口层（`set_workflow_state`），不在 `validate_plan_path` 内部。验证函数应只做验证，不应偷偷修正输入。
- **参数设计**：`_normalize_plan_path` 显式接收 `project_root` 参数，不依赖 `find_project_root()` 的隐性耦合。
- **路径处理优先级**：先用 `Path.resolve() + relative_to()` 处理绝对路径（语义级），再 fallback 到字符串前缀匹配。
- **错误信息**：改善 `validate_plan_path` 的错误提示，明确展示期望格式。

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `hooks/scripts/progress_manager.py` | **修改** | 添加 `_normalize_plan_path()`；`set_workflow_state` 调用归一化；改善 `validate_plan_path` 错误信息 |

---

## Task 1: 添加 `_normalize_plan_path()` 辅助函数

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

- [ ] **Step 1: 在 `set_workflow_state()` 定义之前添加辅助函数**

在 `progress_manager.py` 中，`set_workflow_state()` 函数定义之前添加：

```python
def _normalize_plan_path(plan_path: Optional[str], project_root: Optional[Path] = None) -> Optional[str]:
    """Remove redundant project-root prefix from plan_path.

    Handles both absolute paths (resolved to relative) and relative paths
    that accidentally include the project-root directory prefix.

    This is a CLI convenience — validate_plan_path stays pure.
    """
    if not plan_path:
        return plan_path

    root = project_root or find_project_root()
    if not root:
        return plan_path

    normalized = plan_path.strip().replace("\\", "/")

    # Case 1: absolute path under project_root → resolve to relative
    try:
        abs_path = Path(plan_path).resolve()
        rel = abs_path.relative_to(root)
        return rel.as_posix()
    except (ValueError, OSError):
        pass

    # Case 2: relative path with redundant project-root prefix
    # (e.g. plugins/foo/docs/plans/bar.md → docs/plans/bar.md)
    try:
        prefix = root.relative_to(Path.cwd()).as_posix()
        if prefix and prefix != "." and normalized.startswith(prefix + "/"):
            return normalized[len(prefix) + 1:]
    except ValueError:
        pass

    return plan_path
```

- [ ] **Step 2: 确认函数签名与依赖**

确保 `Optional`, `Path` 已在文件顶部导入（检查 `from pathlib import Path` 和 `from typing import Optional` 是否存在）。

---

## Task 2: 在 `set_workflow_state` 中调用归一化

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

- [ ] **Step 1: 在 feature 检查之后、workflow_state 读取之前插入归一化调用**

在 `set_workflow_state()` 函数体中，`if data.get("current_feature_id") is None` 检查之后，`workflow_state = data.get("workflow_state", {})` 之前，添加：

```python
    # Normalize: strip project-root prefix if user included it
    plan_path = _normalize_plan_path(plan_path, project_root=find_project_root())
```

插入位置（上下文）：

```python
def set_workflow_state(phase=None, plan_path=None, next_action=None):
    """Set workflow state for current feature."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    if data.get("current_feature_id") is None:
        print("Error: No feature currently in progress")
        return False

    # Normalize: strip project-root prefix if user included it
    plan_path = _normalize_plan_path(plan_path, project_root=find_project_root())

    workflow_state = data.get("workflow_state", {})
    ...
```

---

## Task 3: 改善 `validate_plan_path` 错误信息

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

- [ ] **Step 1: 更新错误信息**

将 `validate_plan_path()` 中的错误信息从：

```python
            "error": f"plan_path must be under '{PLAN_PATH_PREFIX}'",
```

改为：

```python
            "error": (
                f"plan_path must be a relative path under '{PLAN_PATH_PREFIX}'"
                f" (e.g., '{PLAN_PATH_PREFIX}my-plan.md')"
            ),
```

---

## Task 4: 验证修复

- [ ] **Step 1: 带前缀的相对路径应自动剥离后成功**

```bash
plugins/progress-tracker/prog --project-root plugins/progress-tracker \
  set-workflow-state --phase "planning:draft" \
  --plan-path "plugins/progress-tracker/docs/plans/2026-04-24-plan-path-normalization.md"
```

期望：`Workflow state updated: phase=planning:draft`

- [ ] **Step 2: 标准格式应正常工作**

```bash
plugins/progress-tracker/prog --project-root plugins/progress-tracker \
  set-workflow-state --phase "planning:draft" \
  --plan-path "docs/plans/2026-04-24-plan-path-normalization.md"
```

期望：`Workflow state updated: phase=planning:draft`

- [ ] **Step 3: 绝对路径应 resolve 到相对路径后成功**

```bash
plugins/progress-tracker/prog --project-root plugins/progress-tracker \
  set-workflow-state --phase "planning:draft" \
  --plan-path "/Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/docs/plans/2026-04-24-plan-path-normalization.md"
```

期望：`Workflow state updated: phase=planning:draft`

- [ ] **Step 4: 错误路径应给出明确提示**

```bash
plugins/progress-tracker/prog --project-root plugins/progress-tracker \
  set-workflow-state --phase "planning:draft" \
  --plan-path "invalid/path.md"
```

期望：报错信息包含 `(e.g., 'docs/plans/my-plan.md')`

- [ ] **Step 5: 提交**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git commit -m "fix: normalize plan_path at CLI entry point

Strip project-root prefix from --plan-path when the user includes it
(e.g. plugins/foo/docs/plans/bar.md → docs/plans/bar.md), and resolve
absolute paths to relative. Validation function stays pure; normalization
is at the CLI layer where project_root context is available.
Also improve error message to show expected format."
```