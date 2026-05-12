# Progress Tracker 状态文件自动提交设计

**日期**：2026-05-13  
**状态**：待实现  
**解决的根本问题**：`prog done/next/fix` 修改 state 文件后未提交，导致分支合并后 prog 状态回退到旧版（如重复提示"run done"而非"start next feature"）。

---

## 问题背景

Progress Tracker 在以下场景写入状态文件但不提交：

| 文件 | 写入时机 |
|------|---------|
| `progress.json` | `prog done/next/fix`、`wf-auto-driver` hook、`sync-runtime-context` hook |
| `checkpoints.json` | `auto-checkpoint` hook（每 30 分钟） |
| `progress.md` | 与 progress.json 同步 |
| `sprint_ledger.jsonl` | `done/fix` 相关事件 |
| `audit.log` | `done/undo/reconcile` 操作 |

**核心风险场景**：  
Feature branch 上 `prog done` 写入了"F13 已完成、F14 为当前"的状态，但未 commit。PR 合并到 main 时，这批状态变更没有随代码进来，main 上 prog 仍显示"F13 in progress，请运行 done"。

---

## 设计决策

**方案 A（选定）**：`prog done/next/fix` 成功后，自动创建一个 state sync commit，将所有有变更的白名单状态文件打包进去。

- 每个 feature lifecycle event 产生 1 条 state commit（`chore(PT): state sync [F{id}: done]`），噪音可预期
- 合并时 state commit 随 feature commit 一起进来，状态始终正确
- hooks（auto-checkpoint、wf-auto-driver）**不触发**，由下一次 prog 命令的 state commit 顺带带走

---

## 实现规格

### 1. 新增函数：`_auto_state_commit(feature_id, event)`

位于 `progress_manager.py`，被三个调用点使用。

**完整流程**：

```
1. 读配置开关 → False 时静默跳过
2. 检测 git 进行中操作 → 有则打印警告并跳过
3. 逐个白名单文件/目录查 dirty status
4. 无 dirty 文件 → 直接返回 None（不创建空 commit）
5. git commit --only -m <msg> -- <dirty_files>（via 直接 subprocess，非 safe_git_command）
6. 返回新 commit hash，失败时返回 None（非阻塞）
```

**实现骨架**：

```python
def _auto_state_commit(feature_id: int, event: str) -> Optional[str]:
    """
    Auto-commit state files after a prog command succeeds.
    Non-blocking: failures print a warning but don't affect the caller's return value.
    """
    data = load_progress_json()
    if not data:
        return None
    if not data.get("settings", {}).get("auto_state_commit", True):
        return None

    # Detect in-progress git operations (worktree-safe: use --absolute-git-dir)
    code, git_dir_str, _ = _run_git(["rev-parse", "--absolute-git-dir"])
    if code == 0:
        git_dir = Path(git_dir_str.strip())
        for marker in ["MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD"]:
            if (git_dir / marker).exists():
                print(f"[state-sync] Skip: git {marker} in progress. "
                      "After resolving, manually commit state files.")
                return None
        for dir_marker in ["rebase-merge", "rebase-apply"]:
            if (git_dir / dir_marker).is_dir():
                print(f"[state-sync] Skip: git {dir_marker} in progress.")
                return None

    project_root = find_project_root()
    dirty_files = _get_dirty_state_files(project_root)
    if not dirty_files:
        return None

    msg = f"chore(PT): state sync [F{feature_id}: {event}] [skip ci]"
    return _git_commit_state(dirty_files, msg, project_root)
```

---

### 2. `_get_dirty_state_files(project_root)` — 白名单精确检测

**单文件白名单**（均在 `docs/progress-tracker/state/` 下）：

```python
STATE_FILE_NAMES = [
    PROGRESS_JSON,           # progress.json
    PROGRESS_MD,             # progress.md
    CHECKPOINTS_JSON,        # checkpoints.json
    PROGRESS_HISTORY_JSON,   # progress_history.json
    "sprint_ledger.jsonl",   # audit 事件
    "status_summary.v1.json",
    "audit.log",             # done/undo/reconcile 依赖此文件
    "project_memory.json",
    "migration_log.json",
]
```

**目录白名单**（枚举目录内 dirty 文件，而非目录本身）：

```python
STATE_DIR_NAMES = [
    "test_reports",      # prog done 生成的验收报告（sprint_ledger 引用）
    "progress_archive",  # prog done 完成时归档（sprint_ledger 引用）
]
```

**`progress.lock` 明确排除**（运行时锁文件，永远不提交）。

**Dirty 检测方式**：`git status --porcelain -- <relpath>` 逐文件调用，非空输出即为 dirty。此方式能同时捕获：modified（`M`）、untracked（`??`）、新 staged（`A`）文件，覆盖首次创建的状态文件场景。

```python
def _get_dirty_state_files(project_root: Path) -> List[Path]:
    progress_dir = get_progress_dir()
    dirty = []

    for name in STATE_FILE_NAMES:
        f = progress_dir / name
        if not f.exists():
            continue
        rel = str(f.relative_to(project_root))
        code, out, _ = _run_git(["status", "--porcelain", "--", rel],
                                  cwd=str(project_root))
        if code == 0 and out.strip():
            dirty.append(f)

    for dir_name in STATE_DIR_NAMES:
        d = progress_dir / dir_name
        if not d.is_dir():
            continue
        rel_dir = str(d.relative_to(project_root))
        code, out, _ = _run_git(["status", "--porcelain", "--", rel_dir],
                                  cwd=str(project_root))
        if code == 0:
            for line in out.strip().splitlines():
                # format: "XY path"
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    dirty.append(project_root / parts[1].strip())

    return dirty
```

---

### 3. `_git_commit_state(files, msg, project_root)` — 绕过 safe_git_command

`safe_git_command` 的 `DANGEROUS_CHARS` 包含 `(` `)` `<` `>`，会拒绝 `chore(PT):` 中的括号。  
由于我们使用 `subprocess.run(shell=False)` + 固定格式字符串，无注入风险，可安全绕过。

`git commit --only -- <files>` 语义：创建临时 index 仅包含指定文件的工作区版本，用户已 staged 的其他改动**不受影响**，commit 后仍留在 staging area。

```python
def _git_commit_state(
    state_files: List[Path], msg: str, project_root: Path
) -> Optional[str]:
    """
    Commit state_files using git commit --only, bypassing safe_git_command.
    shell=False guarantees no injection risk despite parentheses in msg.
    """
    rel_paths = [str(f.relative_to(project_root)) for f in state_files]
    cmd = ["git", "commit", "--only", "-m", msg, "--"] + rel_paths
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            cwd=str(project_root),
            timeout=30,
            text=True,
        )
        if result.returncode != 0:
            print(f"[state-sync] Auto-commit failed (non-blocking): {result.stderr.strip()}")
            return None
        r2 = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, check=False,
            cwd=str(project_root), text=True,
        )
        return r2.stdout.strip() or None
    except Exception as e:
        print(f"[state-sync] Auto-commit error (non-blocking): {e}")
        return None
```

---

### 4. 三个调用点

| 调用位置 | 函数 | 行号（约） | event 值 |
|---------|------|-----------|---------|
| feature 完成 | `complete_feature()` | ~8714（`save_progress_md` 之后） | `"done"` |
| feature 开始 | `set_current()` | ~6614（`save_progress_md` 之后） | `"start"` |
| bug 标记修复 | `update_bug_status()` | ~10075（`save_progress_md` 之后，仅 `status == "fixed"` 时） | `"fix"` |

**`complete_feature()` 调用示例**：

```python
save_progress_json(data)
save_progress_md(generate_progress_md(data))
_auto_state_commit(feature_id, "done")   # ← 新增
```

**非阻塞约定**：`_auto_state_commit` 返回值（commit hash 或 None）被调用方记录到日志即可，不影响 `complete_feature` / `set_current` / `update_bug_status` 自身的返回值。

---

### 5. 配置开关

在 `progress.json` 中新增 `settings` 顶层键：

```json
{
  "settings": {
    "auto_state_commit": true
  }
}
```

- `prog init` 时默认写入 `auto_state_commit: true`
- 缺省值为 `True`（向后兼容，老项目无此键时自动启用）
- 关闭：直接编辑 `progress.json`，或未来通过 `prog config set auto_state_commit false`

---

### 6. hooks 不触发

`auto-checkpoint`、`wf-auto-driver`、`sync-runtime-context` 三个 hook **不调用** `_auto_state_commit`。  
理由：
- hook 写的是 operational state（`pending_action`、`runtime_context`、checkpoint 快照），非 lifecycle 事件
- 下一次 `prog done/next/fix` 的 state commit 会顺带把这些积累的改动带走
- 避免每次用户发消息都产生 git commit

---

## 边界约束（来自 review）

| 约束 | 实现方式 |
|------|---------|
| 只在有 diff 时 commit | `_get_dirty_state_files` 返回空列表时直接跳过 |
| 只 git add 白名单文件 | `git commit --only -- <files>`，精确路径列表 |
| 不带入用户 staged 改动 | `--only` 使用临时 index，用户 staged 改动不受影响 |
| merge/rebase/cherry-pick 中跳过 | 检测 `--absolute-git-dir` 下的 marker 文件 |
| 提交消息格式固定 | `chore(PT): state sync [F{id}: {event}] [skip ci]` |
| 配置开关 | `settings.auto_state_commit`，默认 True |
| 非阻塞失败 | 所有错误降级为 print 警告，不影响 prog 命令返回值 |
| worktree 兼容 | 使用 `--absolute-git-dir` 而非 `--git-dir` |

---

## 不在本次范围内

- `prog init` 时 state 文件的初始 commit（init 已有自己的流程）
- `progress_archive/` 子目录的深度追踪（只 add 新文件，不 add 已追踪文件的子目录变更到 archive 内的 archive）
- `sprint_ledger.jsonl` 引用外部文件的完整性校验
- `prog config set` 命令（用户可直接编辑 progress.json）
