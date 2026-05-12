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
3. 逐个白名单文件/目录查 dirty status（cwd=repo_root，确保路径一致）
4. 无 dirty 文件 → 直接返回 None（不创建空 commit）
5. git add -- <dirty_files>（将 untracked 新文件 stage 进来，--only 无法提交 untracked）
6. git commit --only -m <msg> -- <dirty_files>（via 直接 subprocess，非 safe_git_command）
7. 返回新 commit hash，失败时返回 None（非阻塞）
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

**关键**：必须以 `git_root`（`git rev-parse --show-toplevel`）为 `cwd` 运行 `git status`，porcelain 输出路径才是 repo-root-relative。若以 `project_root`（如 `plugins/progress-tracker`）为 cwd，porcelain 路径仍是 repo-root-relative，但用 `project_root / parts[1]` 拼接会产生重复前缀（`plugins/progress-tracker/plugins/progress-tracker/...`）。

```python
def _get_dirty_state_files(project_root: Path) -> List[Path]:
    progress_dir = get_progress_dir()
    dirty = []

    # Resolve repo root; porcelain output is always repo-root-relative.
    # Use _resolve_repo_root() — always available, no git_validator dependency.
    try:
        git_root = _resolve_repo_root(project_root)
    except Exception:
        return dirty  # can't resolve repo root, skip silently

    for name in STATE_FILE_NAMES:
        f = progress_dir / name
        if not f.exists():
            continue
        rel = str(f.relative_to(git_root))        # repo-root-relative
        code, out, _ = _run_git(["status", "--porcelain", "--", rel],
                                  cwd=str(git_root))
        if code == 0 and out.strip():
            dirty.append(f)

    for dir_name in STATE_DIR_NAMES:
        d = progress_dir / dir_name
        if not d.is_dir():
            continue
        rel_dir = str(d.relative_to(git_root))    # repo-root-relative
        code, out, _ = _run_git(["status", "--porcelain", "--", rel_dir],
                                  cwd=str(git_root))
        if code == 0:
            for line in out.strip().splitlines():
                # format: "XY path" — path is repo-root-relative
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    dirty.append(git_root / parts[1].strip())  # ← git_root, not project_root

    return dirty
```

---

### 3. `_git_commit_state(files, msg, project_root)` — 绕过 safe_git_command

`safe_git_command` 的 `DANGEROUS_CHARS` 包含 `(` `)` `<` `>`，会拒绝 `chore(PT):` 中的括号。  
由于我们使用 `subprocess.run(shell=False)` + 固定格式字符串，无注入风险，可安全绕过。

`git commit --only -- <files>` 语义：创建临时 index 仅包含指定文件的工作区版本，用户已 staged 的其他改动**不受影响**，commit 后仍留在 staging area。

**注意**：`git commit --only` 从工作树读取文件，但对于 **untracked（从未被 git 跟踪的新文件）**，它无法直接包含——必须先 `git add` 将其加入 index，`--only` 才能把它纳入临时 index 并提交。因此 `_git_commit_state` 在 commit 之前先运行一次精确白名单的 `git add`。

```python
def _git_commit_state(
    state_files: List[Path], msg: str, project_root: Path
) -> Optional[str]:
    """
    Commit state_files using git add + git commit --only, bypassing safe_git_command.
    shell=False guarantees no injection risk despite parentheses in msg.
    git add stages untracked new state files; --only isolates the commit from
    any other changes the user may have staged.
    """
    # Use _resolve_repo_root() — always available, no git_validator dependency.
    try:
        git_root = _resolve_repo_root(project_root)
    except Exception:
        print("[state-sync] Auto-commit skipped: cannot resolve repo root.")
        return None
    rel_paths = [str(f.relative_to(git_root)) for f in state_files]

    try:
        # Stage untracked state files (no-op for already-tracked files).
        # If git add fails, abort: a partial add could produce an incomplete commit.
        add_result = subprocess.run(
            ["git", "add", "--"] + rel_paths,
            capture_output=True, check=False,
            cwd=str(git_root), timeout=15, text=True,
        )
        if add_result.returncode != 0:
            print(f"[state-sync] Auto-commit skipped: git add failed: {add_result.stderr.strip()}")
            return None

        # Commit only state files; leaves user's other staged changes intact
        result = subprocess.run(
            ["git", "commit", "--only", "-m", msg, "--"] + rel_paths,
            capture_output=True, check=False,
            cwd=str(git_root), timeout=30, text=True,
        )
        if result.returncode != 0:
            print(f"[state-sync] Auto-commit failed (non-blocking): {result.stderr.strip()}")
            return None
        r2 = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, check=False,
            cwd=str(git_root), text=True,
        )
        return r2.stdout.strip() or None
    except Exception as e:
        print(f"[state-sync] Auto-commit error (non-blocking): {e}")
        return None
```

---

### 4. 三个调用点

| 调用位置 | 函数 | 精确行号 | event 值 | 说明 |
|---------|------|---------|---------|-----|
| feature 完成 | `cmd_done()` | ~8426 之后、~8446 之前 | `"done"` | 在 `_reset_active_progress` 之后、`_notify_parent_sync()` 之前；此时 archive/memory 操作已全部完成 |
| feature 开始 | `set_current()` | ~6614（`save_progress_md` 之后） | `"start"` | 无变化 |
| bug 标记修复 | `update_bug()` | ~10075（`save_progress_md` 之后，仅 `status == "fixed"` 时） | `"fix"` | 函数名为 `update_bug`（line 10020），非 `update_bug_status` |

> **[P1 修正]** 原 spec 将调用点写为 `complete_feature()`，但该函数只在 `complete --unsafe-legacy` 路径使用（line 11945）。主路径 `/prog done` 经由 `cmd_done()`（line 8217）执行。正确调用点在 `cmd_done()` 内 `_reset_active_progress(data_post_reset)` 之后、`_notify_parent_sync()` 之前，此时当前 tracker 的所有 archive（`progress_archive/`）和 memory 写入均已完成。

**父 tracker 写回（parent writeback）明确为范围外**：

`_notify_parent_sync()`（line 1291）会写入父 tracker 的 `progress.json` 和 `progress.md`（`_save_progress_payload_at_root`，line 1339），这是不同项目根目录下的文件。本次 auto-commit **不**覆盖父 tracker 状态，理由：

1. `_notify_parent_sync()` 已被 `try/except` 包裹，本身是 best-effort，失败只 print WARNING
2. 父 tracker 是独立项目，其状态由父 tracker 自己的 `prog done` 在父项目上下文中提交
3. 将父路径纳入白名单需要跨项目根解析，超出本次功能边界

`_run_post_done_cleanup()`（line 8448）检测 dirty worktree 时，若父 tracker 写回留下 dirty 文件会影响 cleanup 判断——但这是父 tracker writeback 本身的已知限制，不在本次范围内解决。

**`cmd_done()` 调用示例**：

```python
    # ... existing: _reset_active_progress(data_post_reset)   ← line ~8426

    _auto_state_commit(feature_id, "done")   # ← 新增，当前 tracker 所有状态写入完成后

    _notify_parent_sync()                    # ← line ~8446，父 tracker 同步（范围外）
    _run_post_done_cleanup(...)              # ← line ~8448，worktree cleanup
```

**非阻塞约定**：`_auto_state_commit` 返回值（commit hash 或 None）被调用方记录到日志即可，不影响 `cmd_done` / `set_current` / `update_bug` 自身的返回值。

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
| 只 git add 白名单文件 | 先 `git add -- <files>`（精确列表），再 `git commit --only -- <files>` |
| untracked 新文件可提交 | `git add` 将 untracked 状态文件 stage，`--only` 再将其纳入临时 index |
| 不带入用户 staged 改动 | `--only` 使用临时 index，用户其他 staged 改动不受影响 |
| merge/rebase/cherry-pick 中跳过 | 检测 `--absolute-git-dir` 下的 marker 文件 |
| 提交消息格式固定 | `chore(PT): state sync [F{id}: {event}] [skip ci]` |
| 配置开关 | `settings.auto_state_commit`，默认 True |
| git add 失败时中止 | `add_result.returncode != 0` 时 warn + return None，不执行部分 commit |
| 非阻塞失败 | 所有错误降级为 print 警告，不影响 prog 命令返回值 |
| worktree 兼容 | 使用 `--absolute-git-dir` 而非 `--git-dir` |
| repo root 解析 | 使用 `_resolve_repo_root()`，不依赖 `git_validator` 可用性 |

---

## 不在本次范围内

- **父 tracker 状态提交**：`_notify_parent_sync()` 写入父 tracker 文件属于父项目范围，由父项目自己的 `prog done` 负责
- `prog init` 时 state 文件的初始 commit（init 已有自己的流程）
- `progress_archive/` 子目录的深度追踪（只 add 新文件，不 add 已追踪文件的子目录变更到 archive 内的 archive）
- `sprint_ledger.jsonl` 引用外部文件的完整性校验
- `prog config set` 命令（用户可直接编辑 progress.json）
