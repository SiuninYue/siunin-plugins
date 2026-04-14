# Project Progress: prog-parent-coordination-archive

**Created**: 2026-04-09T01:12:55.289861Z

**Status**: 10/24 completed

## Completed
- [x] 定义父级协调追踪器 Schema（linked_projects + snapshot 元数据）
- [x] 实现子项目 progress.json 发现与只读聚合采集器
- [x] 实现 monorepo 根目录歧义 fail-closed 与显式 scope 选择
- [x] 新增父级同步命令 sync-linked（刷新子项目最新快照）
- [x] 全部功能完成时自动归档当前 run 并写入归档索引
- [x] prog init --force 归档与旧状态重命名策略标准化
- [x] [RouteV1] 父级路由 Schema 扩展（tracker_role/project_code/routing_queue/active_routes）
- [x] [RouteV1] 新增 link-project 命令注册子项目与 project_code
- [x] 状态展示与文档更新（父级总览+子项目明细+归档历史）
- [x] 清理 /prog-start 残留并锁定 /prog-next 为唯一 start path

## In Progress
- [ ] [RouteV1] 新增 route-status/route-select 命令
  **Test steps**:
  - 实现: prog route-status 输出当前路由与冲突摘要
  - 实现: prog route-select --project <code> [--feature-ref <code-Fn>]
  - 运行: pytest -q plugins/progress-tracker/tests/test_status_linked_summary.py

## Pending
- [ ] [RouteV1] feature_ref 命名空间化（<project_code>-F<number>）
- [ ] [RouteV1] mutating 命令统一 route_preflight fail-closed
- [ ] [RouteV1] worktree/branch 一致性校验（next/done fail-closed）
- [ ] [RouteV1] 并行 active_routes 冲突策略（允许执行+强告警）
- [ ] [RouteV1] 父级顺序调度：/prog-next 按 routing_queue 选首个可执行子项目
- [ ] [RouteV1] sync-linked 升级为父级统一同步入口
- [ ] [RouteV1] 在 prog-init/prog-plan 与子项目完成时回写父级备案
- [ ] 实现 set-finish-state 显式解锁器并固化 finish_pending 阻断链路
- [ ] 落地 evaluator_gate 与 quality_gates.evaluator 独立评估门
- [ ] 落地 review_router 智能分流并持久化 review lanes
- [ ] 落地 ship_check 统一门禁与 docs-sync 证据校验
- [ ] 落地 sprint_ledger 与 schema 2.1 的 sprint_contract/handoff 持久化
- [ ] 落地 wf_state_machine + wf_auto_driver + hook 自动推进

## Workflow Context
- Phase: execution_complete
- Execution context: fix/bug-001-worktree-cwd-feature-complete @ Claude-Plugins [in_place]
- Current session context: fix/bug-001-worktree-cwd-feature-complete @ Claude-Plugins [in_place]

### Fixed (✅)
- [x] [BUG-001] [DEBT] /prog done 应该自动切换到内联上下文中指定的工作树进行验收测试验证，避免在错误分支上运行测试导致误判
  Fix: Fix applied: feature-complete + feature-implement SKILL.md CWD persistence bug fixed, all prog CLI calls use --project-root (commits: 8f887ca, 1c6332e). PR: SiuninYue/siunin-plugins#16
