# F25: prog done 后自动清理已合并的 feature 分支和 worktree

**Feature ID:** 25
**Date:** 2026-04-22
**Branch:** feature/feature-25
**Worktree:** /Users/siunin/Projects/Claude-Plugins/.worktrees/feature-25

## 决策综合

| 问题 | 最终决策 |
|------|----------|
| 清理触发 | **自动内联，默认执行；`--no-cleanup` 跳过全部** |
| 远程删除 | **始终尝试（非阻塞）** — 失败仅警告，符合测试步骤 #3 |
| 脏检查 | **强制前置：dirty → 跳过清理 + 警告，不阻断 done** |
| in-place | **in-place 时 feature 分支即当前分支，无法删除 → warn + 提示手动操作** |

---

## Architecture（P1 修正版）

### 核心修正

**修正 1 — 快照时机（P1-2）**

`complete_feature()` 在 L6434 执行 `data.pop("workflow_state", None)` 并清空
`current_feature_id`。因此 **必须在 `complete_feature()` 调用之前**，从 `collect_git_context()`
快照 `feature_branch`、`workspace_mode`、`worktree_path`，作为显式参数传入清理函数。

```python
# 在 complete_feature() 之前 — 此后这些信息不再可用
git_ctx = collect_git_context()
cleanup_ctx = {
    "branch": git_ctx.get("branch"),
    "workspace_mode": git_ctx.get("workspace_mode", "unknown"),
    "worktree_path": git_ctx.get("worktree_path"),
}
```

**修正 2 — remote upstream 缓存时机（P1-3）**

`git branch -d <branch>` 之后本地分支元数据（包括 `@{u}` tracking info）即消失。
因此 **必须在删除本地分支之前** 解析并缓存 remote 名称和远程分支名。

```python
remote, remote_branch = _resolve_upstream(branch)  # 先缓存
_delete_local_branch(branch)                        # 再删本地
_delete_remote_branch(remote, remote_branch)        # 用缓存值
```

**修正 3 — cmd_done 签名与调用链（P1-1）**

`cmd_done` 使用显式参数（非 argparse 命名空间）。修改方式：

```python
# 1. 签名
def cmd_done(commit_hash=None, run_all: bool = False,
             skip_archive: bool = False, no_cleanup: bool = False) -> int:

# 2. argparser（done_parser，L8517）
done_parser.add_argument(
    "--no-cleanup", action="store_true", dest="no_cleanup",
    help="Skip post-done worktree and branch cleanup"
)

# 3. 分发（L8921-8926）
if args.command == "done":
    return cmd_done(
        commit_hash=args.commit,
        run_all=args.run_all,
        skip_archive=args.skip_archive,
        no_cleanup=args.no_cleanup,
    )
```

**修正 4 — 调用顺序统一（P2-1）**

唯一插入点：`_notify_parent_sync()` 之后，`return 0` 之前（L6202）。

```python
    _notify_parent_sync()
    _run_post_done_cleanup(cleanup_ctx, skip=no_cleanup)  # ← 新增
    return 0
```

**修正 5 — in-place 分支判定（P1-2 延伸）**

in-place 模式下，用户当前就在 feature 分支上，因此分支无法删除。
不做恒等比较，直接在 in-place 路径下：
- 先尝试 `git branch -d`，会因"已检出"而失败 → warn + 提示用户切换到 main 后手动删除
- 仍尝试 remote delete（用缓存的 remote info）

**修正 6 — 非 git 环境保护（P2-2）**

```python
if cleanup_ctx["workspace_mode"] == "unknown":
    print("[CLEANUP] WARN: non-git context, skipping cleanup")
    return
```

测试套件（T3）新增：非 git 环境不阻断 done，exit code 仍为 0。

---

### 完整清理流程伪代码

```
cmd_done(no_cleanup=False):

  # === 快照阶段（complete_feature 之前）===
  git_ctx = collect_git_context()
  cleanup_ctx = {branch, workspace_mode, worktree_path}

  # === 现有门控 ===
  ... acceptance → evaluator → review → ship_check ...

  success = complete_feature(feature_id, ...)
  if not success: return 4

  print("[DONE] Feature completed")
  _notify_parent_sync()

  # === 清理阶段（notify 之后）===
  _run_post_done_cleanup(cleanup_ctx, skip=no_cleanup)
  return 0


_run_post_done_cleanup(ctx, skip):
  if skip:
    print("[DONE] --no-cleanup: skipping cleanup")
    return

  branch        = ctx["branch"]
  workspace_mode = ctx["workspace_mode"]
  worktree_path = ctx["worktree_path"]

  if workspace_mode == "unknown":
    print("[CLEANUP] WARN: non-git context, skipping cleanup")
    return

  # 脏检查（全模式）
  if _is_worktree_dirty(worktree_path):
    print("[CLEANUP] WARN: dirty worktree, skipping cleanup")
    return

  # 先缓存 upstream（删本地分支前）
  remote, remote_branch = _resolve_upstream(branch)

  if workspace_mode == "worktree":
    _remove_worktree(worktree_path)        # git worktree remove（从 repo root）
    _delete_local_branch(branch)           # git branch -d（warn on fail）
    _delete_remote_branch(remote, remote_branch)  # 用缓存值，非阻塞

  elif workspace_mode == "in_place":
    # 当前就在 feature 分支，branch -d 会因"已检出"失败
    ok = _delete_local_branch(branch)
    if not ok:
      print("[CLEANUP] WARN: cannot delete current branch; switch to main then: git branch -d <branch>")
    _delete_remote_branch(remote, remote_branch)
```

---

## 子函数规格

```python
def _is_worktree_dirty(worktree_path: str) -> bool:
    """git -C <path> status --porcelain → 有输出为 dirty"""

def _resolve_upstream(branch: str) -> tuple[str, str]:
    """
    在删除本地分支之前调用。
    git rev-parse --abbrev-ref <branch>@{u} → "origin/feature-25"
    返回 ("origin", "feature-25")，失败返回 ("", "")
    """

def _remove_worktree(worktree_path: str) -> bool:
    """
    git worktree remove <path>
    cwd=_get_repo_root()（不能在 worktree 自身执行）
    失败 → [CLEANUP] WARN + return False
    """

def _delete_local_branch(branch: str) -> bool:
    """
    git branch -d <branch>（安全，未合并则失败）
    cwd=_get_repo_root()
    失败 → [CLEANUP] WARN + return False
    """

def _delete_remote_branch(remote: str, remote_branch: str) -> bool:
    """
    if not remote or not remote_branch: return True  # 无 upstream → 静默跳过
    git push <remote> --delete <remote_branch>
    失败 → [CLEANUP] WARN + return False（非阻塞）
    """

def _run_post_done_cleanup(ctx: dict, skip: bool = False) -> None:
    """
    编排清理。所有步骤非阻塞，不向 cmd_done 传播异常。
    在 _notify_parent_sync() 之后调用。
    """
```

---

## Tasks

### T1: [RED] 编写 test_cleanup_after_done.py 失败测试

文件：`tests/test_cleanup_after_done.py`

#### 测试隔离策略（必须明确）

所有 T1 场景均为**纯单元测试**，通过 `unittest.mock.patch` 注入命令执行器，**不起真实 git repo**：

```python
# 注入点：patch 以下三个底层函数（不 patch subprocess 本身）
@patch("progress_manager._remove_worktree")
@patch("progress_manager._delete_local_branch")
@patch("progress_manager._delete_remote_branch")
@patch("progress_manager._resolve_upstream")
@patch("progress_manager._is_worktree_dirty")
def test_xxx(mock_dirty, mock_upstream, mock_remote, mock_local, mock_remove):
    ...
```

这样可精确控制每个子函数的返回值/副作用，避免仓库状态残留或并发抖动。

**场景覆盖（12个）：**

```
正常路径：
- worktree 模式，干净 → remove + branch -d + remote delete（全部成功）
- worktree 模式，干净，remote 失败 → warn 但不阻断
- in-place 模式，干净 → branch -d 失败（已检出） + warn；remote delete 仍尝试
- in-place 模式，干净，无 upstream → branch -d warn；remote 静默跳过

安全防线：
- worktree 模式，dirty → skip 全部 + warn
- in-place 模式，dirty → skip 全部 + warn
- unknown workspace_mode → skip 全部 + warn（P2-2）
- --no-cleanup → 完全跳过，无任何 git 调用

顺序与时机：
- upstream 在 branch -d 之前解析（不依赖删除后的元数据）
- worktree remove 失败 → warn，仍继续 branch -d
- branch -d 失败 → warn，仍继续 remote delete（用缓存的 remote）
- 无 upstream → 静默跳过 remote delete
```

### T2: [GREEN] 实现 _run_post_done_cleanup() 及子函数

文件：`hooks/scripts/progress_manager.py`

新增 6 个私有函数（见"子函数规格"章节）。

验收：`pytest -q tests/test_cleanup_after_done.py` 全绿

### T3: [RED] 编写 cmd_done 集成测试

文件：`tests/test_cmd_done_cleanup_integration.py`

#### 调用模型（必须明确）

所有 T3 测试**直接调用 `cmd_done()` Python 函数**（in-process），不通过 CLI 子进程。
`unittest.mock.patch` 仅对同进程内的符号生效；若改用 `subprocess.run(["prog", "done"])` 调用，所有 patch 会被绕过。

#### Gate 前置状态 seeding（必须明确）

`cmd_done()` 在到达 `complete_feature()`/cleanup 之前有 6 道门控，必须全部解除：

```python
@pytest.fixture
def seeded_done_env(tmp_path, monkeypatch):
    """为每个 T3 场景提供一个"所有门控已通过"的最小可执行环境。"""

    # 1. 重定向 tracker state 到 tmp_path（对齐 progress_manager 实际路径解析）
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True)
    progress_file = state_dir / "progress.json"
    progress_file.write_text(json.dumps({
        "current_feature_id": 25,
        "features": [{
            "id": 25,
            "name": "test-feature",
            "status": "developing",
            "quality_gates": {
                "evaluator": {"status": "pass"},       # 解除 evaluator gate
                "ship_check": {"status": "pass"},      # 解除 ship_check gate
                "reviews": {"required": [], "passed": [], "pending": []}  # 解除 review gate
            },
            "acceptance_criteria": []
        }]
    }))
    # patch 实际入口：get_progress_dir()/find_project_root，而不是不存在的 PROGRESS_FILE/ARCHIVE_DIR
    monkeypatch.setattr("progress_manager.find_project_root", lambda: tmp_path)
    monkeypatch.setattr("progress_manager.get_progress_dir", lambda: state_dir)

    # 2. 绕过前三道函数级门控（不写盘、无副作用）
    monkeypatch.setattr("progress_manager.require_sprint_contract", lambda f: None)
    monkeypatch.setattr("progress_manager._run_acceptance_tests", lambda f, **kw: (True, []))
    monkeypatch.setattr("progress_manager._notify_parent_sync", lambda: None)

    # 3. mock git 环境
    monkeypatch.setattr("progress_manager.collect_git_context", lambda: {
        "branch": "feature/feature-25",
        "workspace_mode": "worktree",
        "worktree_path": str(tmp_path / ".worktrees" / "feature-25"),
    })

    return tmp_path
```

seeded 环境建立后，`cmd_done()` 能直通到 `complete_feature()` 和 `_run_post_done_cleanup()`，
各场景再按需 patch `_run_post_done_cleanup` 或 `complete_feature`。

**场景（5个，含 P2-2 修正 + P1 状态不变量）：**

```python
def test_cmd_done_snapshots_branch_before_complete_feature(seeded_done_env, monkeypatch):
    """cleanup_ctx 在 complete_feature() 之前已捕获正确的 branch/mode/path"""
    # patch complete_feature 记录调用时机，验证 cleanup_ctx 值正确

def test_cmd_done_no_cleanup_flag_skips_cleanup(seeded_done_env, monkeypatch):
    """cmd_done(no_cleanup=True) → _run_post_done_cleanup(skip=True)"""

def test_cmd_done_cleanup_failure_preserves_completion_state(seeded_done_env, monkeypatch):
    """
    [P1 不变量] _run_post_done_cleanup 内部抛出 RuntimeError 时：
    - cmd_done 返回码仍为 0
    - progress.json 中 feature.status == "completed"
    - current_feature_id == null（或已清空）
    - archive 文件已写入 `state/progress_archive/`（即 `get_progress_dir() / PROGRESS_ARCHIVE_DIR`）
    - progress.json 整体可被 json.load() 解析（无部分写入损坏）
    """

def test_cmd_done_non_git_context_does_not_block(seeded_done_env, monkeypatch):
    """workspace_mode=unknown → cleanup skip，cmd_done 仍返回 0"""
    monkeypatch.setattr("progress_manager.collect_git_context",
                        lambda: {"branch": "", "workspace_mode": "unknown", "worktree_path": None})

def test_cmd_done_completion_state_stable_before_cleanup_runs(seeded_done_env, monkeypatch):
    """
    [P1 不变量] 验证调用顺序保证：complete_feature() 落盘发生在
    _run_post_done_cleanup() 之前，即使清理被 mock 延迟也不影响已持久化的状态
    """
    # 在 _run_post_done_cleanup 内读取 progress.json，断言此时已包含 status==completed
```

### T4: [GREEN] 在 cmd_done 中接线 --no-cleanup + 调用清理

文件：`hooks/scripts/progress_manager.py`

**修改点（精确）：**

1. **签名** `def cmd_done(...)` → 添加 `no_cleanup: bool = False`
2. **快照** 在 `_validate_done_preconditions` 之后、`complete_feature()` 之前，
   插入 `git_ctx = collect_git_context()` + `cleanup_ctx = {...}` 构建
3. **调用** 在 `_notify_parent_sync()` 之后、`return 0` 之前插入
   `_run_post_done_cleanup(cleanup_ctx, skip=no_cleanup)`
4. **argparser** `done_parser` 添加 `--no-cleanup` flag（L8517 区域）
5. **分发** L8921 添加 `no_cleanup=args.no_cleanup`

### T5: [DOCS] 更新 --no-cleanup 用户可见文档

文件：`commands/prog-done.md`（已存在，直接更新；同步更新 argparser `--help` 字符串）

**修改点：**

1. **argparser help 文本**（T4 同批次，写在 `done_parser.add_argument` 里）：
   ```python
   done_parser.add_argument(
       "--no-cleanup", action="store_true", dest="no_cleanup",
       help="Skip automatic post-done cleanup of worktree and feature branch"
   )
   ```
2. **commands/prog-done.md** 新增 Options 章节：
   ```
   ## Options
   --no-cleanup    Skip automatic cleanup of the feature worktree and branch after done.
                   Use when you want to inspect the worktree state before removing it,
                   or when cleanup is handled by CI.
   ```
3. **默认行为说明**：文档中注明"默认自动执行清理，失败仅 warn 不阻断"，让用户知道
   `--no-cleanup` 是可选旁路，而非正常操作路径。

## Tasks Summary

| # | Task | 文件 | 类型 |
|---|------|------|------|
| T1 | 编写失败测试（12 场景，纯 mock 单元测试） | `tests/test_cleanup_after_done.py` | RED |
| T2 | 实现 6 个清理子函数 | `progress_manager.py` | GREEN |
| T3 | 编写 cmd_done 集成测试（5 场景，含状态不变量） | `tests/test_cmd_done_cleanup_integration.py` | RED |
| T4 | 接线 `--no-cleanup` + 快照 + 调用清理 | `progress_manager.py` | GREEN |
| T5 | 更新 `--no-cleanup` 用户文档 | `commands/prog-done.md` | DOCS |

## Acceptance Criteria

- [ ] `pytest -q tests/test_cleanup_after_done.py` 全绿（12 个清理单元场景）
- [ ] `pytest -q tests/test_cmd_done_cleanup_integration.py` 全绿（5 个 cmd_done 集成场景）
- [ ] **[P1 不变量]** cleanup 异常后：`feature.status == "completed"`、`current_feature_id == null`、archive 文件存在、progress.json 可正常解析
- [ ] `pytest tests/ -q --tb=short` 全量无失败（不依赖总数，以"零失败"为准）
- [ ] worktree 模式：`prog done` 后 `.worktrees/feature-X` 目录自动消失
- [ ] dirty worktree 时：`[CLEANUP] WARN: dirty worktree, skipping cleanup`，done 返回 0
- [ ] `prog done --no-cleanup` 跳过清理，输出 `[DONE] --no-cleanup: skipping cleanup`
- [ ] 非 git 环境：`[CLEANUP] WARN: non-git context, skipping cleanup`，done 返回 0
- [ ] `commands/prog-done.md` 包含 `--no-cleanup` Options 说明

## Acceptance Mapping

| 测试步骤 | 覆盖任务 |
|----------|----------|
| worktree remove 自动执行 | T1, T2 |
| git branch -d 自动执行 | T1, T2 |
| git push origin --delete（非阻塞） | T1, T2 |
| dirty worktree 报警跳过 | T1, T2 |
| in-place 仅清理分支 | T1, T2 |
| 清理失败不阻断 done（退出码 + 状态不变量） | T3, T4 |
| --no-cleanup 用户可发现性 | T5 |

## Risks

- 回归风险：`cmd_done` 调用链新增 cleanup，可能影响原有完成态落盘顺序。  
  缓解：通过 T3 集成测试固定完成态不变量（`completed=true`、`current_feature_id=null`、archive 存在）。
- 误删风险：in-place 模式下可能尝试删除当前分支。  
  缓解：仅使用 `git branch -d` 安全删除；失败仅警告并提示手动处理，不阻断 done。
- 远程清理风险：`git push <remote> --delete` 可能因权限/保护规则失败。  
  缓解：远程删除保持非阻塞，失败仅 `WARN`，不回滚 feature 完成状态。
- 状态漂移风险：worktree 脏状态下清理步骤与用户预期不一致。  
  缓解：前置 dirty 检查并显式输出跳过原因，确保行为可解释且可重试。

## P1 修正对照

| 审查 P1 | 修正方案 |
|---------|----------|
| cmd_done 参数接线 | 显式添加 `no_cleanup` 参数；argparser + 分发均同步更新 |
| in-place 恒等比较 | 不做比较；直接尝试 `branch -d`（它自然会因"已检出"失败）；用失败信息 warn |
| upstream 缓存时机 | `_resolve_upstream(branch)` 在 `_delete_local_branch()` 之前调用；返回值传入 `_delete_remote_branch()` |
| 调用顺序矛盾 | 统一为：`_notify_parent_sync()` → `_run_post_done_cleanup()` → `return 0` |
| 非 git 环境保护 | `workspace_mode == "unknown"` → skip + warn；T3 新增专项测试 |

## 计划审查修正对照（2026-04-22）

| 问题 | 修正方案 |
|------|----------|
| [P1] 清理失败后完成态不变量缺失 | T3 新增 `test_cmd_done_cleanup_failure_preserves_completion_state` 和 `test_cmd_done_completion_state_stable_before_cleanup_runs`；明确断言 `status==completed`、`current_feature_id==null`、archive 存在、progress.json 可解析 |
| [P2] T1 测试隔离边界不明确 | T1 前新增"测试隔离策略"节：明确为纯 mock 单元测试，patch `_remove_worktree` 等 5 个子函数，不起真实 git repo |
| [P2] T3 测试隔离边界不明确 | T3 前新增"调用模型"节：明确 in-process 直调 `cmd_done()`，不走 CLI 子进程；新增 `seeded_done_env` fixture 解除 6 道门控（mock 3 个函数 + 注入 JSON state），允许 `complete_feature` 真实落盘 |
| [P2] 验收标准 "670+" 硬编码总数 | 替换为具体 test file 目标 + "全量无失败"，不依赖总数阈值 |
| [P2] T3 fixture path hook 与实现不一致 | `seeded_done_env` 改为 patch `find_project_root()` + `get_progress_dir()`；移除无效的 `PROGRESS_FILE/ARCHIVE_DIR` patch |
| [P2] archive 断言路径与实现不一致 | 断言目标改为 `get_progress_dir() / PROGRESS_ARCHIVE_DIR`（`state/progress_archive/`），避免假阴性 |
| [P3] 缺少 --no-cleanup 用户文档 | 新增 T5：更新 `commands/prog-done.md`（已存在路径）Options 节 + argparser help 文本 |
| [P3] T5 文档路径错误 | `docs/commands/prog-done.md` → `commands/prog-done.md`（匹配仓库实际路径） |
