# F15: prog-fix skill 嵌入4阶段调试方法论

> Recovery document — original plan was in worktree (feat+PT-F15-prog-fix-skill-debug-methodology)
> PR #49 merged: commit 4f12d69

## Summary

Embedded 4-stage systematic debugging methodology into the `prog-fix` skill.

## Implementation

- Added `superpowers:systematic-debugging` integration to `bug-fix` skill
- Updated `prog-fix` skill to enforce 4-stage debug flow: Observe → Hypothesize → Test → Fix

## Tasks

- [x] T1: 分析现有 prog-fix skill 结构
- [x] T2: 设计4阶段调试方法论集成方案
- [x] T3: 实现 systematic-debugging 调用
- [x] T4: 更新 bug-fix skill 内容
- [x] T5: 验证和测试

## Acceptance Mapping

| Test Step | Implementation |
|-----------|----------------|
| prog-fix skill 使用 systematic-debugging | bug-fix skill 集成 superpowers:systematic-debugging |
| 4阶段调试流程正确触发 | 技能描述和触发条件更新 |

## Risks

- 无重大风险（已验证 PR #49 通过）
