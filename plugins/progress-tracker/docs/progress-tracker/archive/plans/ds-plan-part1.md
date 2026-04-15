# PROG全量规范化计划 - 第一部分：架构概览与阶段划分

## 设计目标

基于现有progress-tracker插件（1.6.13）进行增量改进，实现schema 2.1规范化、自动合约导入、结构门禁、生命周期审计、复盘分离、摘要加速，**同时修复关键痛点**：`/prog-done`后必须进入"集成与收尾门禁"，避免main长期不完整和worktree残留。

## 核心设计原则

1. **零侵入体验**：现有`/prog-*`命令用法不变，日常用户无新增学习负担
2. **增量迁移**：Schema 2.0→2.1兼容回填，新旧状态双写，可回滚开关
3. **门禁优先**：关键阻塞点在数据安全与收尾完整性，避免功能超前
4. **审计追溯**：所有状态变更、门禁决策、异常修复均写入updates链

## 阶段实施策略（D+方案）

| 阶段 | 目标 | 关键交付 | 验收标准 | 可观测指标 |
|------|------|----------|----------|------------|
| **阶段1：迁移安全底座** | 确保老数据可读可写、冲突可自愈、失败可回滚 | 文件锁+原子写、备份回滚、validate_post_migration、reconcile_legacy_state | 并发写不丢数据，坏JSON可恢复，状态冲突自动修复 | 迁移失败率、自动修复成功率、回滚成功率 |
| **阶段2：收尾痛点MVP** | 解决"done后main不完整、worktree尾巴未管" | 每次`/prog-done`强制收尾三选一，pending阻断`/prog-next` | 不再出现done了但未收尾的情况，脏worktree不自动删 | pending_finish阻断命中率、未收尾进入next的漏拦截率 |
| **阶段3：规范化核心能力** | 结构门禁、合约自动导入、生命周期审计 | readiness校验、JSON/MD合约解析、生命周期流转合规 | `/prog-start`全链路稳定，非法流转被阻断 | 非法流转拦截率、合约导入成功率 |
| **阶段4：增强与性能** | 状态展示快且一致、审计可追溯 | progress_summary.json、refs裁剪、retro分离 | 大项目下`/prog`响应快，追溯信息完整 | `/prog` p95响应时间、摘要一致性校验通过率 |

## 写路径唯一化约束

**所有状态变更必须走 transaction_manager + add_update**，禁止旁路写 JSON，避免审计断链。

## 架构模块划分

```
existing progress_manager.py (core state)
├── schema_migration.py      # Schema 2.1回填与兼容
├── transaction_manager.py   # 文件锁+原子写
├── finish_gate.py           # 收尾门禁（阶段2）
├── contract_importer.py     # 合约自动导入（阶段3）
├── readiness_validator.py   # 结构门禁（阶段3）
├── state_reconciler.py      # 脑裂修复
└── summary_projector.py     # 摘要投影（阶段4）
```

## 收尾三选一状态机

明确"收尾三选一"状态机：
- `merged_and_cleaned`：已合并且worktree清理
- `pr_open`：PR已打开，记录链接
- `kept_with_reason`：有明确保留原因

超时策略：超过N天未处理的状态需要二次确认。

## 现有代码集成点

1. **主入口**：`progress_manager.py`的`set_development_stage`、`complete_feature`、`add_update`等核心方法
2. **数据持久化**：`get_progress_json_path`读取的`progress.json`
3. **命令行接口**：`/prog-start`、`/prog-done`、`/prog-next`等hook触发
4. **测试框架**：`plugins/progress-tracker/tests/`中的契约测试

## 向后兼容保证

- `set-development-stage developing`仍可被旧调用使用（内部映射到`implementing`）
- `development_stage`与`completed`字段不废弃，由`lifecycle_state`单向同步写回
- 现有用户数据（包括bug字段、archive_info等）保持完整
- `PROG_DISABLE_V2=1`环境变量提供紧急降级开关

## readiness_validator前移为"软门禁"

阶段2先告警不阻断，阶段3再切换为阻断，降低迁移期摩擦。

## 最强大脑建议（优先级从高到低）

1. 先把阶段2独立成可发布里程碑（MVP）并灰度
2. 在updates中增加`decision_id`和`correlation_id`，便于跨命令追溯
3. 增加"每日自检任务"：扫描pending_finish、脏worktree、状态脑裂并自动出报告
4. 设一条硬规则：`/prog-next`前必须通过finish_gate，不允许任何bypass
5. 先补"故障演练测试"：坏JSON、并发写冲突、半迁移中断恢复

## 集成测试策略

1. 现有327个测试全量回归
2. 每个阶段新增契约测试（先红灯后转绿）
3. 并发、迁移、收尾门禁专项测试

## 故障演练测试（必须覆盖）

1. **JSON损坏恢复**：模拟文件损坏、编码错误、截断
2. **并发写冲突**：多进程同时写progress.json
3. **半迁移中断**：迁移过程中断（kill -9）
4. **磁盘空间不足**：写过程中空间耗尽
5. **权限问题**：只读文件、无写权限