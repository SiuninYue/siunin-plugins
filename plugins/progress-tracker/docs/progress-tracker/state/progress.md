# Project Progress: progress-tracker-sop-compliance-optimization

**Created**: 2026-04-23T00:28:18.285129Z

**Status**: 19/22 completed

## Completed
- [x] 根目录混合宿主架构：Monorepo /prog 支持
- [x] Robust Progress State Architecture - Event Sourcing & Reconciliation
- [x] Baseline compliance scan for frontmatter and routable descriptions
- [x] Refactor progress_manager into modular command helpers
- [x] Normalize skill frontmatter to SOP-compliant shape
- [x] Enforce plugin metadata traceability fields
- [x] Add explicit model declaration checks for required skill scopes
- [x] Apply progressive disclosure budget to oversized SKILL files
- [x] Harden command lifecycle boundaries and architecture immutability guard
- [x] Enforce PROG command docs single-source parity
- [x] Implement fail-closed release gate with sync compatibility evidence
- [x] plan_path CLI normalization
- [x] Complexity scoring v2: weighted rubric via haiku subagent
- [x] Unified work-item intake and profile routing (task/feature/bug) via /prog next
- [x] Task execution semantics and visibility (standalone task vs feature task) with profile-aware done gates
- [x] prog-fix skill 嵌入4阶段调试方法论
- [x] Git Squash Merge SOP — 集成到 prog-done 自动化流程
- [x] Parent-Child Route 同步：子插件 set_current/done 回写父 active_routes
- [x] progress_manager.py 深度模块化拆分（Phase 2 技术债偿还）

## In Progress
- [ ] progress_manager facade 收口 Round 0-1：边界护栏 + 状态/摘要只读链路外移
  **Test steps**:
  - scripts/check_pm_boundary.sh 能对局部 import progress_manager / from progress_manager import ... fail-closed
  - python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
  - uv run pytest plugins/progress-tracker/tests/test_root_dashboard.py plugins/progress-tracker/tests/test_status_linked_summary.py plugins/progress-tracker/tests/test_summary_writeback.py plugins/progress-tracker/tests/test_progress_ui_status.py -q
  - DoD: summary_projector.py 与 status_commands.py 建立，progress_manager.py 对应链路仅保留 facade wrapper
  - DoD: 本轮变更按 F19 记录格式写入 docs/changes/index.jsonl 与对应 markdown record

## Pending
- [ ] progress_manager facade 收口 Round 2：readiness validation 外移
- [ ] AI 可追溯与可回退机制 v1：变更记录 + 自动守卫 + 回退 SOP

## Workflow Context
- Phase: execution_complete
- Next action: verify_and_complete
- Execution context: f20 @ f20 [worktree]
- Current session context: f20 @ f20 [worktree]

## Recent Updates
- [UPD-006] status: Regression test update
- [UPD-007] decision: 记录 progress_manager facade 收敛分轮方案；详细执行计划转移到 docs/plans/2026-06-03-progress-manager-facade-rounds.md
  Next: Execute Round 0 boundary-check hardening, then Round 1 summary/status extraction.
- [UPD-008] decision: 登记 Round 0-1 为独立执行 feature，并显式排在 F19 前 (feature:20)
  Next: Start Round 0 by hardening scripts/check_pm_boundary.sh before any code extraction.
- [UPD-009] decision: 安排 facade 收口后续优先级：F21 执行 Round 2 readiness validation 外移，F19 暂后 (feature:21)
  Next: Close/complete F20 after validation, then start F21 Round 2 readiness_validator.py extraction before returning to F19.
- [UPD-010] decision: 设置 F21 closeout 防遗忘门槛：必须登记下一条 facade 收口 feature 或写明 defer 决策 (feature:21)
  Next: When closing F21, create the next facade convergence feature for Round 3-4 or record an explicit defer decision.

## Bug Backlog
### High Priority (🔴)
- [🔴] [BUG-006] Memory leak in websocket handler

### Medium Priority (🟡)
- [🔴] [BUG-008] [DEBT] F14: AC-3 profile gate matrix — mutual exclusivity tested but different validation-depth per profile not explicitly validated
- [🔴] [BUG-009] [DEBT] F14: _git_squash_close_task error-recovery branches (checkout/merge/commit failures) not covered by tests

### Low Priority (🟢)
- [🔴] [BUG-005] P2: complete 未走 fail-closed worktree/branch 一致性检查。一致性检查只对 next-feature 和 done 执行，complete 重定向到 cmd_done 后绕过该检查入口。关键位置: progress_manager.py:11336-11339
- [🔴] [BUG-007] Regression test bug

### Fixed (✅)
- [x] [BUG-001] Python falsy trap: current_feature_id=0 被 not 误判为 None，导致 set-workflow-state/auto_checkpoint/wf_auto_driver/route_status 等函数在 feature ID 为 0 时异常跳过
- [x] [BUG-002] P0: complete 重定向后被外层锁卡死。complete 走 MUTATING_COMMANDS 外层 progress_transaction()，但 cmd_done 内部路径（record_sprint_artifact、嵌套 prog 命令）会再次拿锁，导致 10 秒锁超时，RC=9。关键位置: progress_manager.py:11145, 11341
  Fix: Fix applied (commit: ab3a38d99d090a629d71065e19ddb2d124ba249b) — progress_manager.py:11490 extend lock exemption to {done, complete}; regression test added (925 tests pass).
- [x] [BUG-003] P1: planning:review phase 未接入状态机。skill 已引入 planning:review 停点，但 wf_state_machine.py 映射只有 planning:draft/clarifying/approved，导致 compute_next_action() 对 planning:review 返回 None。关键位置: wf_state_machine.py:21-27
  Fix: 与 BUG-004 同一次改动修复：wf_state_machine.py:21-27 补全 planning:review 状态映射，compute_next_action() 现在对 planning:review 返回 resume_planning_draft
- [x] [BUG-004] P1: 恢复策略未覆盖 planning:review，降级为 manual_review。determine_recovery_action() 只覆盖 planning:draft/clarifying/approved，writing planning:review 后走 manual_review 分支，与 skill 定义的单次审批恢复路径不一致。关键位置: progress_manager.py:6439-6462
  Fix: 与 BUG-003 同一次改动修复：progress_manager.py:6439-6462 的 determine_recovery_action() 补全 planning:review 分支，返回单次审批恢复路径
- [x] [BUG-010] P0: standalone task 分支从当前 HEAD 创建而非默认分支，可能把无关改动一起 squash 到默认分支
- [x] [BUG-011] P0: squash merge/commit 失败后回滚不完整 — reset --mixed 不清理 worktree 冲突内容，未切回原分支
