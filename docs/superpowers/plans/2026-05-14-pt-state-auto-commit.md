# PT State Auto-Commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `prog done/next/fix` 成功后自动创建一个 state sync commit，将所有有变更的白名单状态文件打包，防止 PR merge 时状态丢失。

**Architecture:** 在 `progress_manager.py` 中新增三个 git helper 函数（常量 → dirty 检测 → 原子提交 → 编排）以及一个 `settings` 写入，然后在三个现有函数的状态写入完成后调用顶层编排函数。所有 git 操作通过直接 `subprocess.run(shell=False)` 执行，绕过 `safe_git_command` 对括号的限制。失败全部降级为 warning，不影响调用方返回值。

**Tech Stack:** Python 3.12+, subprocess, pytest, `mock_git_repo` fixture（已有真实临时 git 仓库）

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `plugins/progress-tracker/hooks/scripts/progress_manager.py` | 新增常量、3 个函数；修改 `init_tracking`；3 处调用点 |
| Create | `plugins/progress-tracker/tests/test_auto_state_commit.py` | 本次功能全部测试 |

---

## 背景知识（快速参考）

**`mock_git_repo` fixture**（`tests/conftest.py:110`）：创建真实临时 git 仓库，已做初始 commit，`temp_dir` 即 repo root。

**`configure_project_scope`**（`progress_manager.py:400`）：必须在每个使用 `progress_manager` 的测试中调用，将模块状态指向临时目录。签名为 `configure_project_scope(project_root_arg: Optional[str])`，调用时传字符串路径：`configure_project_scope(str(mock_git_repo))`。**不能**用关键字参数 `project_root=...`（会 TypeError）。

**`_resolve_repo_root(project_root: Path) -> Path`**（`progress_manager.py:2223`）：始终可用，不依赖 `git_validator`。

**`_run_git(args, cwd, timeout)`**（`progress_manager.py:5707`）：安全的 git 命令包装，但其 `safe_git_command` 后端拒绝括号；新函数使用直接 `subprocess.run`。

**调用点行号（当前 main）：**
- `init_tracking` 初始化 dict：`progress_manager.py:5127`
- `set_current` save 完成后：`progress_manager.py:6614`
- `cmd_done` archive+reset 之后：`progress_manager.py:8428`（在 `_notify_parent_sync()` 之前）
- `update_bug` save 完成后：`progress_manager.py:10075`（仅 `status == "fixed"` 时）

**运行测试：**
```bash
cd plugins/progress-tracker
python -m pytest tests/test_auto_state_commit.py -v
```

---

## Task 1: 新增模块常量

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:166`（在 `CHECKPOINT_MAX_ENTRIES` 之后）
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py`（新建，写第一批测试）

- [ ] **Step 1: 创建测试文件，写常量存在性测试**

新建 `plugins/progress-tracker/tests/test_auto_state_commit.py`，内容：

```python
"""Tests for _auto_state_commit and supporting functions."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import sys

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


class TestStateFileConstants:
    def test_state_file_names_contains_required_files(self):
        assert "progress.json" in progress_manager.STATE_FILE_NAMES
        assert "progress.md" in progress_manager.STATE_FILE_NAMES
        assert "checkpoints.json" in progress_manager.STATE_FILE_NAMES
        assert "audit.log" in progress_manager.STATE_FILE_NAMES
        assert "project_memory.json" in progress_manager.STATE_FILE_NAMES
        assert "sprint_ledger.jsonl" in progress_manager.STATE_FILE_NAMES

    def test_state_file_names_excludes_lock(self):
        assert "progress.lock" not in progress_manager.STATE_FILE_NAMES

    def test_state_dir_names_contains_required_dirs(self):
        assert "test_reports" in progress_manager.STATE_DIR_NAMES
        assert "progress_archive" in progress_manager.STATE_DIR_NAMES
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd plugins/progress-tracker
python -m pytest tests/test_auto_state_commit.py::TestStateFileConstants -v
```

期望：`AttributeError: module 'progress_manager' has no attribute 'STATE_FILE_NAMES'`

- [ ] **Step 3: 在 `progress_manager.py` 第 166 行后插入常量**

在 `CHECKPOINT_INTERVAL_SECONDS = 1800`（line 161）之后、`PLAN_PATH_PREFIX`（line 163）之前插入：

```python
# State files managed by progress-tracker (whitelist for auto-commit)
STATE_FILE_NAMES = [
    PROGRESS_JSON,
    PROGRESS_MD,
    CHECKPOINTS_JSON,
    PROGRESS_HISTORY_JSON,
    "sprint_ledger.jsonl",
    "status_summary.v1.json",
    "audit.log",
    "project_memory.json",
    "migration_log.json",
]
STATE_DIR_NAMES = [
    "test_reports",
    "progress_archive",
]
```

注：`PROGRESS_JSON`、`PROGRESS_MD`、`CHECKPOINTS_JSON`、`PROGRESS_HISTORY_JSON` 均已在 `prog_paths.py` 中定义并在文件顶部通过 `from prog_paths import ...` 导入。

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_auto_state_commit.py::TestStateFileConstants -v
```

期望：3 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "test+feat(PT): add STATE_FILE_NAMES / STATE_DIR_NAMES constants"
```

---

## Task 2: 实现 `_get_dirty_state_files`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`（在 `_run_git` ~line 5736 之后插入）
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py`

- [ ] **Step 1: 写失败测试**

在 `test_auto_state_commit.py` 追加：

```python
class TestGetDirtyStateFiles:
    def test_detects_modified_tracked_file(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        data = json.loads(progress_json.read_text())
        data["_dirty_marker"] = True
        progress_json.write_text(json.dumps(data))

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("progress.json" in str(f) for f in dirty)

    def test_detects_untracked_new_state_file(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "audit.log").write_text("new audit entry\n")

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("audit.log" in str(f) for f in dirty)

    def test_excludes_progress_lock(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "progress.lock").write_text("pid=12345")

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert all("progress.lock" not in str(f) for f in dirty)

    def test_returns_empty_when_state_is_clean(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert dirty == []

    def test_detects_new_file_in_test_reports_dir(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        test_reports = state_dir / "test_reports"
        test_reports.mkdir(exist_ok=True)
        (test_reports / "report-f1.json").write_text('{"result": "pass"}')

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("report-f1.json" in str(f) for f in dirty)

    def test_detects_deleted_tracked_state_file(self, mock_git_repo):
        """Deleted tracked state files must appear in dirty list (valid state change)."""
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        (state_dir / "audit.log").write_text("entry\n")
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        # Delete a tracked state file
        (state_dir / "audit.log").unlink()

        dirty = progress_manager._get_dirty_state_files(mock_git_repo)
        assert any("audit.log" in str(f) for f in dirty)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_auto_state_commit.py::TestGetDirtyStateFiles -v
```

期望：`AttributeError: module 'progress_manager' has no attribute '_get_dirty_state_files'`

- [ ] **Step 3: 实现 `_get_dirty_state_files`**

在 `progress_manager.py` 的 `_run_git` 函数（~line 5707）之后插入：

```python
def _get_dirty_state_files(project_root: Path) -> list:
    """Return list of state files (whitelist only) that have uncommitted changes.

    Uses git status --porcelain with cwd=repo_root so paths in output are
    consistently repo-root-relative, avoiding double-prefix bugs when
    project_root is a subdirectory (e.g. plugins/progress-tracker).
    """
    progress_dir = get_progress_dir()
    dirty: list = []

    try:
        git_root = _resolve_repo_root(project_root)
    except Exception:
        return dirty

    for name in STATE_FILE_NAMES:
        f = progress_dir / name
        # No exists() guard: deleted tracked files must be included (they show
        # as "D " in porcelain output and must be committed to record the deletion).
        # Files that never existed and were never tracked → empty porcelain output → skipped.
        try:
            rel = str(f.relative_to(git_root))
        except ValueError:
            continue
        code, out, _ = _run_git(["status", "--porcelain", "--", rel], cwd=str(git_root))
        if code == 0 and out.strip():
            dirty.append(f)

    for dir_name in STATE_DIR_NAMES:
        d = progress_dir / dir_name
        # No is_dir() guard: deleted directories with tracked files show up in porcelain.
        try:
            rel_dir = str(d.relative_to(git_root))
        except ValueError:
            continue
        code, out, _ = _run_git(["status", "--porcelain", "--", rel_dir], cwd=str(git_root))
        if code == 0:
            for line in out.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    dirty.append(git_root / parts[1].strip())

    return dirty
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_auto_state_commit.py::TestGetDirtyStateFiles -v
```

期望：6 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "test+feat(PT): implement _get_dirty_state_files with whitelist detection"
```

---

## Task 3: 实现 `_git_commit_state`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`（紧接 `_get_dirty_state_files` 之后）
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py`

- [ ] **Step 1: 写失败测试**

在 `test_auto_state_commit.py` 追加：

```python
class TestGitCommitState:
    def test_creates_commit_for_modified_state_file(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        data = json.loads(progress_json.read_text())
        data["_test"] = True
        progress_json.write_text(json.dumps(data))

        result = progress_manager._git_commit_state(
            [progress_json],
            "chore(PT): state sync [F1: done] [skip ci]",
            mock_git_repo,
        )

        assert result is not None
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert "state sync [F1: done]" in log

    def test_commits_untracked_new_file(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        audit_log = state_dir / "audit.log"
        audit_log.write_text("event1\n")

        result = progress_manager._git_commit_state(
            [audit_log],
            "chore(PT): state sync [F1: done] [skip ci]",
            mock_git_repo,
        )

        assert result is not None
        show = subprocess.run(
            ["git", "show", "--name-only", "--format=", "HEAD"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert "audit.log" in show

    def test_does_not_include_user_staged_files(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        # User stages a non-state file
        user_file = mock_git_repo / "my_code.py"
        user_file.write_text("# user code")
        subprocess.run(["git", "add", "my_code.py"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        data = json.loads(progress_json.read_text())
        data["_test"] = True
        progress_json.write_text(json.dumps(data))

        progress_manager._git_commit_state(
            [progress_json],
            "chore(PT): state sync [F1: done] [skip ci]",
            mock_git_repo,
        )

        # my_code.py should still be staged (not committed)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert "my_code.py" in status

    def test_returns_none_when_nothing_to_commit(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        # File is clean — no changes

        result = progress_manager._git_commit_state(
            [progress_json],
            "chore(PT): state sync [F1: done] [skip ci]",
            mock_git_repo,
        )
        assert result is None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_auto_state_commit.py::TestGitCommitState -v
```

期望：`AttributeError: module 'progress_manager' has no attribute '_git_commit_state'`

- [ ] **Step 3: 实现 `_git_commit_state`**

在 `_get_dirty_state_files` 之后插入：

```python
def _git_commit_state(
    state_files: list, msg: str, project_root: Path
) -> "Optional[str]":
    """Commit state_files using git add + git commit --only.

    Uses subprocess.run directly (not safe_git_command) because the commit
    message contains parentheses, which safe_git_command rejects as dangerous
    shell metacharacters. shell=False ensures no injection risk.

    git add stages untracked files; --only isolates the commit so any files
    the user has staged are left untouched.
    """
    try:
        git_root = _resolve_repo_root(project_root)
    except Exception:
        print("[state-sync] Auto-commit skipped: cannot resolve repo root.")
        return None

    try:
        rel_paths = [str(f.relative_to(git_root)) for f in state_files]
    except ValueError as exc:
        print(f"[state-sync] Auto-commit skipped: path resolution error: {exc}")
        return None

    try:
        add_result = subprocess.run(
            ["git", "add", "--"] + rel_paths,
            capture_output=True, check=False,
            cwd=str(git_root), timeout=15, text=True,
        )
        if add_result.returncode != 0:
            print(
                f"[state-sync] Auto-commit skipped: git add failed: "
                f"{add_result.stderr.strip()}"
            )
            return None

        commit_result = subprocess.run(
            ["git", "commit", "--only", "-m", msg, "--"] + rel_paths,
            capture_output=True, check=False,
            cwd=str(git_root), timeout=30, text=True,
        )
        if commit_result.returncode != 0:
            print(
                f"[state-sync] Auto-commit failed (non-blocking): "
                f"{commit_result.stderr.strip()}"
            )
            return None

        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, check=False,
            cwd=str(git_root), text=True,
        )
        return hash_result.stdout.strip() or None
    except Exception as exc:
        print(f"[state-sync] Auto-commit error (non-blocking): {exc}")
        return None
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_auto_state_commit.py::TestGitCommitState -v
```

期望：4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "test+feat(PT): implement _git_commit_state with git add + --only"
```

---

## Task 4: 实现 `_auto_state_commit`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`（紧接 `_git_commit_state` 之后）
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py`

- [ ] **Step 1: 写失败测试**

在 `test_auto_state_commit.py` 追加：

```python
class TestAutoStateCommit:
    def test_returns_none_when_config_disabled(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        data = progress_manager.load_progress_json()
        data["settings"] = {"auto_state_commit": False}
        progress_manager.save_progress_json(data)

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is None

    def test_returns_none_during_merge(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        (mock_git_repo / ".git" / "MERGE_HEAD").write_text("deadbeef")

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is None
        (mock_git_repo / ".git" / "MERGE_HEAD").unlink()

    def test_returns_none_during_rebase(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        rebase_dir = mock_git_repo / ".git" / "rebase-merge"
        rebase_dir.mkdir()

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is None
        rebase_dir.rmdir()

    def test_returns_none_when_no_dirty_files(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is None

    def test_creates_commit_with_correct_message(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        # Dirty state
        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        data = json.loads(progress_json.read_text())
        data["_test"] = True
        progress_json.write_text(json.dumps(data))

        result = progress_manager._auto_state_commit("F3", "done")

        assert result is not None
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert "chore(PT): state sync [F3: done] [skip ci]" in log

    def test_defaults_to_enabled_when_settings_key_absent(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init state"], cwd=mock_git_repo, capture_output=True)

        # Remove settings key entirely (old project without settings)
        data = progress_manager.load_progress_json()
        data.pop("settings", None)
        progress_manager.save_progress_json(data)

        # Dirty state
        state_dir = mock_git_repo / "docs" / "progress-tracker" / "state"
        progress_json = state_dir / "progress.json"
        pdata = json.loads(progress_json.read_text())
        pdata["_test"] = True
        progress_json.write_text(json.dumps(pdata))

        result = progress_manager._auto_state_commit("F1", "done")
        assert result is not None  # enabled by default
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_auto_state_commit.py::TestAutoStateCommit -v
```

期望：`AttributeError: module 'progress_manager' has no attribute '_auto_state_commit'`

- [ ] **Step 3: 实现 `_auto_state_commit`**

在 `_git_commit_state` 之后插入：

```python
def _auto_state_commit(ref: str, event: str) -> "Optional[str]":
    """Auto-commit dirty state files after a prog lifecycle command succeeds.

    Non-blocking: all failures print a warning and return None without
    raising or affecting the caller's return value.

    Args:
        ref:   Human-readable reference, e.g. "F3" (feature) or "BUG-001".
        event: Lifecycle event name, e.g. "done", "start", "fix".
    """
    data = load_progress_json()
    if not data:
        return None
    if not data.get("settings", {}).get("auto_state_commit", True):
        return None

    # Resolve project root first — needed as cwd for all git calls.
    project_root = find_project_root()

    # Detect in-progress git operations (worktree-safe: --absolute-git-dir).
    # Pass cwd=project_root to avoid detecting the wrong repo in multi-project setups.
    code, git_dir_str, _ = _run_git(["rev-parse", "--absolute-git-dir"],
                                     cwd=str(project_root))
    if code == 0:
        git_dir = Path(git_dir_str.strip())
        for marker in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD"):
            if (git_dir / marker).exists():
                print(
                    f"[state-sync] Skip: {marker} in progress. "
                    "Resolve git operation, then commit state files manually."
                )
                return None
        for dir_marker in ("rebase-merge", "rebase-apply"):
            if (git_dir / dir_marker).is_dir():
                print(f"[state-sync] Skip: {dir_marker} in progress.")
                return None

    dirty = _get_dirty_state_files(project_root)
    if not dirty:
        return None

    msg = f"chore(PT): state sync [{ref}: {event}] [skip ci]"
    return _git_commit_state(dirty, msg, project_root)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_auto_state_commit.py::TestAutoStateCommit -v
```

期望：6 tests PASSED

- [ ] **Step 5: 运行全部新测试**

```bash
python -m pytest tests/test_auto_state_commit.py -v
```

期望：全部通过（当前 16 tests：Task 1×3 + Task 2×6 + Task 3×4 + Task 4×6 - 含删除场景）

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "test+feat(PT): implement _auto_state_commit orchestrator"
```

---

## Task 5: `init_tracking` 写入 `settings.auto_state_commit`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:5127`
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py`

- [ ] **Step 1: 写失败测试**

在 `test_auto_state_commit.py` 追加：

```python
class TestInitTrackingSettings:
    def test_init_tracking_writes_auto_state_commit_true(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test Project", force=True)

        data = progress_manager.load_progress_json()
        assert data.get("settings", {}).get("auto_state_commit") is True
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_auto_state_commit.py::TestInitTrackingSettings -v
```

期望：FAILED（`auto_state_commit` 不存在于 settings 中）

- [ ] **Step 3: 修改 `init_tracking` 初始化 dict**

找到 `progress_manager.py:5127` 的 dict 字面量，在其中添加 `"settings"` 键：

```python
    data = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "project_name": project_name,
        "created_at": now,
        "updated_at": now,
        "features": features or [],
        "current_feature_id": None,
        "settings": {"auto_state_commit": True},   # ← 新增
    }
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_auto_state_commit.py::TestInitTrackingSettings -v
```

期望：1 test PASSED

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "test+feat(PT): init_tracking writes settings.auto_state_commit=true"
```

---

## Task 6: 在 `cmd_done` 中调用 `_auto_state_commit`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:8428`
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py`

- [ ] **Step 1: 写失败测试**

在 `test_auto_state_commit.py` 追加：

```python
class TestCallSiteCmdDone:
    """Use seeded-JSON strategy: quality gates must be in progress.json because
    cmd_done() reads them directly (lines 8327-8366), not via patchable functions."""

    _FEATURE_ID = 1

    def _seed_gated_env(self, tmp_path: Path) -> None:
        """Write fully-gated progress.json + plan document into tmp_path."""
        plan_path = f"docs/plans/2026-01-01-feature-{self._FEATURE_ID}.md"
        plan_abs = tmp_path / plan_path
        plan_abs.parent.mkdir(parents=True, exist_ok=True)
        plan_abs.write_text(
            "# Feature Plan\n\n## Tasks\n\n- [ ] step\n\n"
            "## Acceptance Mapping\n\n- passes\n\n## Risks\n\n- none\n",
            encoding="utf-8",
        )
        feature = {
            "id": self._FEATURE_ID,
            "name": "Test Feature",
            "completed": False,
            "deferred": False,
            "lifecycle_state": "implementing",
            "development_stage": "developing",
            "change_spec": {"why": "test", "in_scope": [], "out_of_scope": [], "risks": []},
            "requirement_ids": ["REQ-001"],
            "acceptance_scenarios": [],
            "acceptance_criteria": [],
            "integration_status": None,
            "quality_gates": {
                "evaluator": {
                    "status": "pass", "score": 100, "defects": [],
                    "last_run_at": "2026-01-01T00:00:00Z", "evaluator_model": None,
                },
                "ship_check": {
                    "status": "pass", "failures": [],
                    "last_run_at": "2026-01-01T00:00:00Z",
                },
                "reviews": {"required": ["eng"], "passed": ["eng"], "pending": []},
            },
            "sprint_contract": {
                "scope": "test", "done_criteria": ["passes"],
                "test_plan": ["pytest"], "accepted_by": "test",
                "accepted_at": "2026-01-01T00:00:00Z",
            },
            "handoff": {
                "from_phase": None, "to_phase": None,
                "artifact_path": None, "created_at": None,
            },
        }
        data = {
            "schema_version": "2.1",
            "project_name": "test",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "features": [feature],
            "current_feature_id": self._FEATURE_ID,
            "updates": [], "retrospectives": [], "runtime_context": {},
            "linked_projects": [], "linked_snapshot": {},
            "tracker_role": "standalone", "project_code": None,
            "routing_queue": [], "active_routes": [],
            "bugs": [], "current_bug_id": None,
            "workflow_state": {
                "phase": "execution_complete", "plan_path": plan_path
            },
            "settings": {"auto_state_commit": True},
        }
        state_dir = tmp_path / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "progress.json").write_text(json.dumps(data))

    def test_cmd_done_calls_auto_state_commit(self, tmp_path):
        """_auto_state_commit is called with F<id> after cmd_done clears all gates."""
        self._seed_gated_env(tmp_path)
        worktree_ctx = {
            "branch": "feature/test", "workspace_mode": "direct", "worktree_path": None
        }

        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", tmp_path),
            patch("progress_manager.require_sprint_contract", return_value=None),
            patch("progress_manager._run_acceptance_tests", return_value=(True, [])),
            patch("progress_manager._save_done_test_report", return_value=None),
            patch("progress_manager.record_sprint_artifact", return_value=None),
            patch("progress_manager._notify_parent_sync", return_value=None),
            patch("progress_manager._run_post_done_cleanup"),
            patch("progress_manager.collect_git_context", return_value=worktree_ctx),
            patch.object(progress_manager, "_auto_state_commit") as mock_asc,
        ):
            progress_manager.cmd_done()

        mock_asc.assert_called_once_with(f"F{self._FEATURE_ID}", "done")
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest "tests/test_auto_state_commit.py::TestCallSiteCmdDone" -v
```

期望：`AssertionError: Expected call not found`（`_auto_state_commit` 还未被接入 cmd_done）

- [ ] **Step 3: 在 `cmd_done` 中插入调用**

找到 `progress_manager.py` 中 `cmd_done` 函数内、`if data_final_check and _is_project_fully_completed(...)` 块结束之后、`print(f"[DONE] Feature {feature_id} completed")` 之前（~line 8428），插入：

```python
    _auto_state_commit(f"F{feature_id}", "done")
```

完整上下文（插入后应如下所示）：

```python
        data_post_reset = load_progress_json()
        if data_post_reset:
            _reset_active_progress(data_post_reset)

    _auto_state_commit(f"F{feature_id}", "done")   # ← 新增

    print(f"[DONE] Feature {feature_id} completed")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest "tests/test_auto_state_commit.py::TestCallSiteCmdDone" -v
```

期望：1 test PASSED

- [ ] **Step 5: 运行现有 cmd_done 相关测试确认无回归**

```bash
python -m pytest tests/test_cleanup_after_done.py tests/test_cmd_done_cleanup_integration.py tests/test_feature_completion_state_transition.py -v
```

期望：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "test+feat(PT): wire _auto_state_commit into cmd_done"
```

---

## Task 7: 在 `set_current` 中调用 `_auto_state_commit`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:6614`
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py`

- [ ] **Step 1: 写失败测试**

在 `test_auto_state_commit.py` 追加：

```python
class TestCallSiteSetCurrent:
    def test_set_current_calls_auto_state_commit(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        progress_manager.add_feature("Feature 1", ["step 1"])

        with patch.object(progress_manager, "_auto_state_commit") as mock_asc:
            progress_manager.set_current(1)

        mock_asc.assert_called_once_with("F1", "start")
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest "tests/test_auto_state_commit.py::TestCallSiteSetCurrent" -v
```

期望：`AssertionError: Expected call not found`

- [ ] **Step 3: 在 `set_current` 中插入调用**

找到 `progress_manager.py` 的 `set_current` 函数（line 6556），在 `save_progress_md(md_content)` 之后、`print(f"Set current feature: ...")` 之前插入：

```python
    _auto_state_commit(f"F{feature_id}", "start")   # ← 新增

    print(f"Set current feature: {feature.get('name', 'Unknown')}")
    return True
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest "tests/test_auto_state_commit.py::TestCallSiteSetCurrent" -v
```

期望：1 test PASSED

- [ ] **Step 5: 运行现有 set_current 相关测试确认无回归**

```bash
python -m pytest tests/test_progress_manager.py -k "set_current or next_feature" -v
```

期望：全部 PASSED

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "test+feat(PT): wire _auto_state_commit into set_current"
```

---

## Task 8: 在 `update_bug` 中调用 `_auto_state_commit`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:10075`
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py`

- [ ] **Step 1: 写失败测试**

在 `test_auto_state_commit.py` 追加：

```python
class TestCallSiteUpdateBug:
    def _add_bug_and_get_id(self) -> str:
        """Helper: add a bug and return its auto-generated ID (e.g. 'BUG-001')."""
        progress_manager.add_bug(description="Something broken", priority="medium")
        data = progress_manager.load_progress_json()
        return data["bugs"][-1]["id"]

    def test_update_bug_calls_auto_state_commit_when_fixed(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        bug_id = self._add_bug_and_get_id()

        with patch.object(progress_manager, "_auto_state_commit") as mock_asc:
            progress_manager.update_bug(bug_id, status="fixed",
                                        fix_summary="Fixed the thing")

        mock_asc.assert_called_once_with(bug_id, "fix")

    def test_update_bug_does_not_call_auto_state_commit_for_other_statuses(
        self, mock_git_repo
    ):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager.init_tracking("Test", force=True)
        bug_id = self._add_bug_and_get_id()

        with patch.object(progress_manager, "_auto_state_commit") as mock_asc:
            progress_manager.update_bug(bug_id, status="investigating")

        mock_asc.assert_not_called()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest "tests/test_auto_state_commit.py::TestCallSiteUpdateBug" -v
```

期望：`AssertionError: Expected call not found`

- [ ] **Step 3: 在 `update_bug` 中插入条件调用**

找到 `progress_manager.py:10072`，在 `save_progress_md(md_content)` 之后、`print(f"Bug {bug_id} updated.")` 之前插入：

```python
    if updated:
        save_progress_json(data)
        md_content = generate_progress_md(data)
        save_progress_md(md_content)
        if status == "fixed":                              # ← 新增
            _auto_state_commit(bug_id, "fix")             # ← 新增
        print(f"Bug {bug_id} updated.")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest "tests/test_auto_state_commit.py::TestCallSiteUpdateBug" -v
```

期望：2 tests PASSED

- [ ] **Step 5: 运行现有 bug 相关测试确认无回归**

```bash
python -m pytest tests/test_auto_state_commit.py tests/test_sprint_ledger.py -v
```

期望：全部 PASSED

- [ ] **Step 6: 运行完整测试套件**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

期望：全部通过，无新失败

- [ ] **Step 7: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "test+feat(PT): wire _auto_state_commit into update_bug (fixed only)"
```

---

## Self-Review

**Spec coverage 检查：**

| Spec 要求 | 覆盖任务 |
|----------|---------|
| `_auto_state_commit` 函数 | Task 4 |
| `_get_dirty_state_files` 白名单检测 | Task 2 |
| `_git_commit_state` git add + --only | Task 3 |
| `STATE_FILE_NAMES` 常量 | Task 1 |
| `STATE_DIR_NAMES` 常量 | Task 1 |
| `settings.auto_state_commit` 配置开关 | Task 4（读），Task 5（写） |
| merge/rebase/cherry-pick 中跳过 | Task 4 |
| cmd_done 调用点 | Task 6 |
| set_current 调用点 | Task 7 |
| update_bug 调用点（仅 fixed） | Task 8 |
| git add 失败时 warn+return None | Task 3（`_git_commit_state`） |
| repo root 用 `_resolve_repo_root()` | Task 2、Task 3 |
| 使用 `--absolute-git-dir` 而非 `--git-dir` | Task 4 |
| 不含 progress.lock | Task 2 (test_excludes_progress_lock) |
| 父 tracker 状态不提交 | 不在本次范围，有文档记录 |

**无占位符**：所有步骤均含完整代码。

**类型一致性**：
- `_auto_state_commit(ref: str, event: str)` — `ref` 在 Task 6 以 `f"F{feature_id}"` 传入，Task 7 相同，Task 8 以 `bug_id` 传入，与函数签名一致。
- `_git_commit_state(state_files: list, msg: str, project_root: Path)` — 在 `_auto_state_commit` 中以 `dirty: list` 传入，一致。
- `_get_dirty_state_files(project_root: Path) -> list` — 在 `_auto_state_commit` 中调用，一致。

**`configure_project_scope` 签名**：`configure_project_scope(project_root_arg: Optional[str])`，必须传字符串，不能用关键字 `project_root=`。

**`add_bug` 签名**：第一个参数是 `description: str`，无 `name`/`bug_id` 参数，ID 自动生成（格式 `BUG-NNN`）。测试中通过加载 `data["bugs"][-1]["id"]` 获取实际 ID。

**Task 6 strategy**：用 seeded JSON + `_PROJECT_ROOT_OVERRIDE` 绕过直接读 JSON 的 evaluator/review/ship_check gate（lines 8327-8366），不用 `mock_git_repo`（call-site 测试不需要真实 git repo）。

**`_auto_state_commit` git-dir cwd**：`project_root` 前移至 git-dir 检测之前，`_run_git(["rev-parse", "--absolute-git-dir"], cwd=str(project_root))` 绑定正确 scope。

**`_get_dirty_state_files` 删除文件**：去掉 `exists()`/`is_dir()` guard，`git status --porcelain` 天然报告删除（`D `）。Task 2 加了 `test_detects_deleted_tracked_state_file` 覆盖此路径。
