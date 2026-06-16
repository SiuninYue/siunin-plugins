# AI 可追溯与可回退机制 v1 (F19)

**change_id:** 20260616-traceability-rollback-f19a  
**date:** 2026-06-16  
**component:** hooks/scripts/validate_change_record.py  
**feature:** PT-F19

## Issue

缺少故障防御、自动守卫和统一的回退机制，导致 AI Agent 的高风险变更有可能引发代码损坏、reverse-import 边界破坏、文档不同步，且在出故障时无法快速安全回退。

## Root Cause

未建立完整的“变更新增 -> pre-commit 强校验 -> CHANGELOG.md 自动同步”环路。此外，缺少明确的回退 SOP 说明与自动恢复工具。

## Fixes

- 引入 `validate_change_record.py` 守卫，限制高风险文件变动时必须新增 canonical change record。
- 引入 `render_changelog_from_index.py`，实现 `CHANGELOG.md` 中 `Unreleased` 段落内 managed block 的自动渲染和暂存。
- 在 `pre-commit` hook 中集成上述二者，形成 fail-closed 的本地自动守卫。
- 制定以下三种回退 SOP 路线，确保能够快速回滚和恢复环境。

## Impact

- 提高了对高风险变更的规范约束力，保障了变更历史的完全可追溯性。
- 自动维护 `CHANGELOG.md`，减免人工维护成本。

## Verification Commands

```bash
# 执行校验器与渲染器的测试用例
uv run pytest plugins/progress-tracker/tests/test_validate_change_record.py -v
uv run pytest plugins/progress-tracker/tests/test_render_changelog_from_index.py -v
uv run pytest plugins/progress-tracker/tests/test_pre_commit_change_record_guard.py -v

# 验证边界和文档
bash scripts/check_pm_boundary.sh
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
```

## Rollback SOP (回退步骤)

当本变更或其它高风险变更引发故障、破坏边界或测试不通过时，需根据具体情况采用以下三条回退路线：

### 查找引入变更的 Commit SHA
执行以下命令，通过 `change_id` 定位最初引入该变更的 commit，从而精确获取回滚目标：
```bash
git log --all --diff-filter=A -S '"change_id": "20260616-traceability-rollback-f19a"'
```

### 路线 A：本地未提交/临时工作区回退
1. 运行 `git restore` 或 `git stash` 丢弃或暂存未提交的代码改动。
2. 运行 `prog restore-archive <archive_id>` 恢复至正常的状态快照。
3. 运行 `prog reconcile` 执行一致性检查与自动修复。

### 路线 B：已提交代码的回退
1. 运行 `git revert <commit_sha>` 撤销引入故障的 commit。
2. 运行 `prog reconcile` 确认状态一致性。
3. 如果涉及到 feature/bug 状态，在 `/prog` 状态检查后，根据提示由操作人员手动执行状态修复命令。

### 路线 C：Reconcile 仍然失败的终极应急策略
如果 `reconcile` 依旧诊断失败，且自动引擎无法修复，立即停止所有自动操作，运行以下诊断命令收集现场：
```bash
# 收集详细日志与一致性分析
python3 plugins/progress-tracker/hooks/scripts/progress_manager.py reconcile --json
# 检查当前 Git 工作区和 Worktree 拓扑
git status
git worktree list
# 检查模块依赖是否发生越界
bash scripts/check_pm_boundary.sh
```

### Shared Hooks 的备份与清理恢复说明
在执行 live 钩子安装之前，建议备份当前的 shared hooks：
- 备份：
  ```bash
  cp "$(git rev-parse --git-path hooks)/pre-commit" "/tmp/f19-pre-commit.backup"
  cp "$(git rev-parse --git-path hooks)/post-merge" "/tmp/f19-post-merge.backup"
  ```
- 恢复：若测试中断或放弃 F19 变更，可直接恢复备份：
  ```bash
  cp "/tmp/f19-pre-commit.backup" "$(git rev-parse --git-path hooks)/pre-commit"
  ```
  或者在 `main` 工作区重新运行 `prog install-git-hooks` 以重新写入 main 分支的钩子载荷。

## Residual Risk

- `pre-commit` 自动暂存 CHANGELOG.md 可能会隐藏工作区中对 CHANGELOG 的其它非预期手写改动，开发人员提交前需留意 `git diff` 详情。
