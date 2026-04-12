# Project Progress: prog-parent-coordination-archive

**Created**: 2026-04-09T01:12:55.289861Z

**Status**: 1/14 completed

## Completed
- [x] 定义父级协调追踪器 Schema（linked_projects + snapshot 元数据）

## Pending
- [ ] 实现子项目 progress.json 发现与只读聚合采集器
- [ ] 实现 monorepo 根目录歧义 fail-closed 与显式 scope 选择
- [ ] 新增父级同步命令 sync-linked（刷新子项目最新快照）
- [ ] 全部功能完成时自动归档当前 run 并写入归档索引
- [ ] prog init --force 归档与旧状态重命名策略标准化
- [ ] 状态展示与文档更新（父级总览+子项目明细+归档历史）
- [ ] 清理 /prog-start 残留并锁定 /prog-next 为唯一 start path
- [ ] 实现 set-finish-state 显式解锁器并固化 finish_pending 阻断链路
- [ ] 落地 evaluator_gate 与 quality_gates.evaluator 独立评估门
- [ ] 落地 review_router 智能分流并持久化 review lanes
- [ ] 落地 ship_check 统一门禁与 docs-sync 证据校验
- [ ] 落地 sprint_ledger 与 schema 2.1 的 sprint_contract/handoff 持久化
- [ ] 落地 wf_state_machine + wf_auto_driver + hook 自动推进
