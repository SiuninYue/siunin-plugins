# AI 可追溯与可回退机制 v1 真实判定与跨历史检索增强 (F19)

**change_id:** 20260616-traceability-rollback-sophisticate-c7a8  
**date:** 2026-06-16  
**component:** hooks/scripts/rollback_helper.py  
**feature:** PT-F19

## Issue

- `check_archive_available()` 之前通过判断 `progress.json` 存在即返回 `True` 的逻辑过于宽泛，导致在正式执行时几乎无法落入 Route B / Route C 路径（除非整个 tracker state 损坏）。
- `find_commit_sha()` 在使用 `git log` 时缺少 `--all` 参数，导致跨分支、平行分支或 cherry-pick / squash 等非当前可达历史中的 `change_id` 引入记录会被漏报，无法实现对全 Git 历史的检索。

## Root Cause

归档检查实现不精确，且 Git 检索参数缺少 `--all` 导致视野局限。

## Fixes

- 修改 `check_archive_available()` 实现，使其真实扫描并列出 `state/progress_archive` 目录下的 `*.progress.json` 归档快照，真正有物理存档时才走 Route A。
- 在 `find_commit_sha()` 的 `git log` 调用中补上 `--all` 检索。
- 在 `test_rollback_drills.py` 中补充了针对这两项增强功能的不依赖 Mock 的真实测试套件（`test_check_archive_available_real_detection`, `test_rollback_route_b_no_mock_fallback`, `test_find_commit_sha_cross_history_lookup`）。

## Impact

- 实现了纯物理检测，支持跨平行分支的变更精确检索拓扑排序。
- 1213 个测试全部顺利跑通。

## Verification Commands

```bash
# 执行校验器与回退测试
pytest plugins/progress-tracker/tests/ -k "rollback" -v
```

## Rollback SOP (回退步骤)

### 查找引入变更的 Commit SHA
```bash
git log --all --diff-filter=A -S '"change_id": "20260616-traceability-rollback-sophisticate-c7a8"'
```

### 路线 A：本地未提交/临时工作区回退
1. 运行 `git restore` 或 `git stash` 丢弃或暂存未提交的代码改动。
2. 运行 `prog restore-archive <archive_id>` 恢复状态。
3. 运行 `prog reconcile` 执行一致性检查。

### 路线 B：已提交代码的回退
1. 运行 `git revert <commit_sha>` 撤销此 commit。
2. 运行 `prog reconcile` 确认状态一致性。

### 路线 C：Reconcile 仍然失败的终极应急策略
如果 `reconcile` 故障，运行以下命令：
```bash
python3 plugins/progress-tracker/hooks/scripts/progress_manager.py reconcile --json
git status
git worktree list
bash scripts/check_pm_boundary.sh
```

## Residual Risk

无。
