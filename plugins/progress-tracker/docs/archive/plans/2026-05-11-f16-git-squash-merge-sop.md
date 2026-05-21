# F16 Plan: Git Squash Merge SOP — 集成到 prog-done 自动化流程

## Summary

强制 squash merge，使每个 work item 在合入 main 时只产生 1 个语义完整的 commit。

## Superpowers Header

- Feature: F16 "Git Squash Merge SOP — 集成到 prog-done 自动化流程"
- Bucket: standard
- Model: sonnet
- Confidence: high

## Acceptance Mapping

| Test Step | Implementation |
|-----------|----------------|
| feature 分支多 commit → prog done → main 只增加 1 个 squash commit | git-auto SKILL.md 强制 `--squash` + 明确 CommitHash 来源 |
| main git log 无 WIP 碎片 commit | git-auto SKILL.md 执行规则明确 squash |
| project_memory.json commit_hash 指向 squash commit | feature-complete SKILL.md Step 5 明确要求 squash commit hash |
| feature 分支自动清理 | git-auto SKILL.md 新增 branch cleanup 步骤（非阻塞）|
| 历史 remap 脚本可选执行 | 新增 scripts/squash-remap-history.sh |

## Risks

- CommitHash MUST 来自 default branch 最新提交（`git rev-parse origin/main` 或 `git log main -1 --format=%H`），不能取 feature branch HEAD
- `_git_squash_close_task` 本地删除保持 `git branch -D`（squash 语义下 -d 会失败，-D 是正确选择）；`git push origin --delete` 仅用于 PR/feature closeout 路径，不复杂化 standalone task 路径
- Branch cleanup 失败不应阻塞 feature 完成

## Tasks

- [ ] T1: 更新 skills/git-auto/SKILL.md — 强制 squash merge + CommitHash 定义 + branch cleanup
- [ ] T2: 更新 skills/feature-complete/SKILL.md — Step 5 添加 squash merge 检查项
- [ ] T3: 验证 progress_manager.py _git_squash_close_task commit message 格式
- [ ] T4: 在 tests/test_task_execution_semantics.py 补充"冲突失败"和"cleanup 失败非阻塞"用例（不新开文件）
- [ ] T5: 新增 skills/git-auto/scripts/squash-remap-history.sh（可选历史 remap）
- [ ] T6: 运行全量测试确认无回归
