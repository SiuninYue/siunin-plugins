# Project Progress: prog-parent-coordination-archive

**Created**: 2026-04-09T01:12:55.289861Z

**Status**: 7/24 completed

## Completed
- [x] 定义父级协调追踪器 Schema（linked_projects + snapshot 元数据）
- [x] 实现子项目 progress.json 发现与只读聚合采集器
- [x] 实现 monorepo 根目录歧义 fail-closed 与显式 scope 选择
- [x] 新增父级同步命令 sync-linked（刷新子项目最新快照）
- [x] 全部功能完成时自动归档当前 run 并写入归档索引
- [x] prog init --force 归档与旧状态重命名策略标准化
- [x] 状态展示与文档更新（父级总览+子项目明细+归档历史）

## In Progress
- [ ] [RouteV1] 父级路由 Schema 扩展（tracker_role/project_code/routing_queue/active_routes）
  **Test steps**:
  - 在 progress.json 新增并回填 tracker_role/project_code/routing_queue/active_routes
  - 运行: pytest -q plugins/progress-tracker/tests/test_linked_projects_schema.py
  - 校验旧仓库未启用父级时行为不变

## Pending
- [ ] [RouteV1] 新增 link-project 命令注册子项目与 project_code
- [ ] [RouteV1] 新增 route-status/route-select 命令
- [ ] [RouteV1] feature_ref 命名空间化（<project_code>-F<number>）
- [ ] [RouteV1] mutating 命令统一 route_preflight fail-closed
- [ ] [RouteV1] worktree/branch 一致性校验（next/done fail-closed）
- [ ] [RouteV1] 并行 active_routes 冲突策略（允许执行+强告警）
- [ ] [RouteV1] 父级顺序调度：/prog-next 按 routing_queue 选首个可执行子项目
- [ ] [RouteV1] sync-linked 升级为父级统一同步入口
- [ ] [RouteV1] 在 prog-init/prog-plan 与子项目完成时回写父级备案
- [ ] 清理 /prog-start 残留并锁定 /prog-next 为唯一 start path
- [ ] 实现 set-finish-state 显式解锁器并固化 finish_pending 阻断链路
- [ ] 落地 evaluator_gate 与 quality_gates.evaluator 独立评估门
- [ ] 落地 review_router 智能分流并持久化 review lanes
- [ ] 落地 ship_check 统一门禁与 docs-sync 证据校验
- [ ] 落地 sprint_ledger 与 schema 2.1 的 sprint_contract/handoff 持久化
- [ ] 落地 wf_state_machine + wf_auto_driver + hook 自动推进

## Workflow Context
- Phase: execution_complete
- Next action: /prog-done
- Execution context: main @ Claude-Plugins [in_place]
- Current session context: main @ Claude-Plugins [in_place]
