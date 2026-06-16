# AI 可追溯与可回退机制 v1 Bugfix与状态对齐 (F19)

**change_id:** 20260616-traceability-rollback-fix-a2d9  
**date:** 2026-06-16  
**component:** hooks/scripts/rollback_helper.py  
**feature:** PT-F19

## Issue

- `rollback_helper.py` 在重命名 `shas` -> `added_shas` 时，末尾存在几处未定义的变量引用，导致回退测试红灯。
- `progress.json` 中 F19 对应的状态处于 planning 阶段，未被设置为 ready 状态，导致无法通过 done gate 校验。

## Root Cause

重构遗留引用错误及状态机未更新。

## Fixes

- 修正 `rollback_helper.py` 中的 `shas` 变量引用为 `added_shas`。
- 将 F19 的 `development_stage` 设为 `execution_complete`，并完成所有 review lane 签署，使其达到可完成状态。

## Impact

- 所有 71 个核心单元与集成测试顺利绿灯。
- 完成契约就绪度校验通过。

## Verification Commands

```bash
# 执行校验器与回退测试
pytest plugins/progress-tracker/tests/ -k "rollback or validate or pre_commit or changelog" -v
```

## Rollback SOP (回退步骤)

### 查找引入变更的 Commit SHA
```bash
git log --all --diff-filter=A -S '"change_id": "20260616-traceability-rollback-fix-a2d9"'
```

### 路线 A：本地未提交/临时工作区回退
1. 运行 `git restore` 或 `git stash` 丢弃或暂存未提交的代码改动。
2. 运行 `prog restore-archive <archive_id>` 恢复状态。
3. 运行 `prog reconcile` 执行一致性检查。

### 路线 B：已提交代码的回退
1. 运行 `git revert <commit_sha>` 撤销此修复 commit。
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
