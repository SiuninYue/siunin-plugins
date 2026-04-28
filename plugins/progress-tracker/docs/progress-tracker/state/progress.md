# Project Progress: progress-tracker-sop-compliance-optimization

**Created**: 2026-04-23T00:28:18.285129Z

**Status**: 11/12 completed

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
- [x] plan_path CLI normalization

## In Progress
- [ ] Implement fail-closed release gate with sync compatibility evidence
  **Test steps**:
  - Run unified gate: python3 plugins/progress-tracker/hooks/scripts/ship_check.py
  - Run gate tests: pytest -q plugins/progress-tracker/tests/test_ship_check.py
  - Run compatibility dry-run: codex-plugin-sync --dry-run

## Workflow Context
- Phase: execution
- Execution context: feature/PT-F8-fail-closed-release-gate @ feature-PT-F8-fail-closed-release-gate [worktree]
- Current session context: feature/PT-F8-fail-closed-release-gate @ feature-PT-F8-fail-closed-release-gate [worktree]

## Bug Backlog
### High Priority (🔴)
- [🔴] [BUG-002] P0: complete 重定向后被外层锁卡死。complete 走 MUTATING_COMMANDS 外层 progress_transaction()，但 cmd_done 内部路径（record_sprint_artifact、嵌套 prog 命令）会再次拿锁，导致 10 秒锁超时，RC=9。关键位置: progress_manager.py:11145, 11341

### Medium Priority (🟡)
- [🔴] [BUG-003] P1: planning:review phase 未接入状态机。skill 已引入 planning:review 停点，但 wf_state_machine.py 映射只有 planning:draft/clarifying/approved，导致 compute_next_action() 对 planning:review 返回 None。关键位置: wf_state_machine.py:21-27
- [🔴] [BUG-004] P1: 恢复策略未覆盖 planning:review，降级为 manual_review。determine_recovery_action() 只覆盖 planning:draft/clarifying/approved，writing planning:review 后走 manual_review 分支，与 skill 定义的单次审批恢复路径不一致。关键位置: progress_manager.py:6439-6462

### Low Priority (🟢)
- [🔴] [BUG-005] P2: complete 未走 fail-closed worktree/branch 一致性检查。一致性检查只对 next-feature 和 done 执行，complete 重定向到 cmd_done 后绕过该检查入口。关键位置: progress_manager.py:11336-11339

### Fixed (✅)
- [x] [BUG-001] Python falsy trap: current_feature_id=0 被 not 误判为 None，导致 set-workflow-state/auto_checkpoint/wf_auto_driver/route_status 等函数在 feature ID 为 0 时异常跳过
