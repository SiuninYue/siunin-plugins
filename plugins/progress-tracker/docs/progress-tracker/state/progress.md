# Project Progress: PROG 全量规范化

**Created**: 2026-03-16T14:28:41.135552Z

**Status**: 6/14 completed

## Completed
- [x] 1. 基线与失败测试先行
- [x] 2. 事务层与并发锁
- [x] 3. schema 2.1 回填与迁移校验
- [x] 4. 脑裂修复与降级开关
- [x] P0 Batch 1: Reconcile engine + check/next/done gates
- [x] Plan: 低学习成本优先的命令分层（保留能力，隐藏复杂度）

## In Progress
- [ ] 5. 合约自动导入与 Markdown FSM 解析器
  **Test steps**:
  - cd plugins/progress-tracker && pytest tests/test_feature_contract_readiness.py -q -k "requirement_ids or change_spec or acceptance_scenarios"
  - cd plugins/progress-tracker && pytest tests/test_progress_manager.py -q -k "markdown or contract or parser or fsm"
  - cd plugins/progress-tracker && python3 -m py_compile hooks/scripts/progress_manager.py
  - DoD: JSON 与 Markdown 合约导入可用，Markdown 采用无复杂回溯的 FSM 解析，恶劣输入不会卡死 CLI。

## Pending
- [ ] 6. readiness 校验器与 /prog-start 串联
- [ ] 7. 生命周期 API 与回退规则
- [ ] 8. /prog-done 收尾门禁
- [ ] 9. refs 智能裁剪
- [ ] 10. summary 投影与状态展示
- [ ] 11. 命令文档与帮助更新（含 Drift Prevention/Codex 兼容）
- [ ] 12. 全量回归与验收报告

## Workflow Context
- Phase: execution_complete
- Next action: Run /prog done to verify and close feature 5
- Execution context: codex/prog-beta-setup @ claude-plugins-beta [worktree]
- Current session context: codex/prog-beta-setup @ claude-plugins-beta [worktree]

## Recent Updates
- [UPD-006] status: Feature 3: schema 2.1 contract backfill + lifecycle mapping (feature:3)
  Next: Complete feature 3 after validation.
- [UPD-007] status: scope gate smoke explicit
- [UPD-008] risk: Feature 4 in-progress: scope gates verified, known red baseline still open (feature:4)
  Next: Decide whether to keep baseline red (documented) or implement scope preset/relative-root ergonomics before completing feature 4.
- [UPD-009] status: Feature 4: scope baseline closed and --project-root dot semantics fixed (feature:4)
  Next: Run /prog done to complete Feature 4
- [UPD-010] status: Feature 4 completed via /prog done (feature:4)
  Next: Start feature 5 with /prog next
