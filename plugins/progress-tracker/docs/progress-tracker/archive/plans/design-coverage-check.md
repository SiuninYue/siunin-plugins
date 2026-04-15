# 设计覆盖检查：原版PROG全量规范化计划 vs 四个部分设计文档

## 原版plan主要要求清单

### 1. Public Interfaces / Types（必须落地）
- [x] `progress.json`顶层新增字段：`schema_version: "2.1"`, `validation_policy`, `retrospectives`, `updates`（扩展）
- [x] `features[]`强制字段：`lifecycle_state`, `requirement_ids`, `change_spec`, `acceptance_scenarios`, `acceptance_results`, `integration_status`, `integration_ref`, `cleanup_status`, `finish_reason`, `archive_pending`
- [x] 向后兼容镜像字段：`development_stage`与`completed`由`lifecycle_state`单向同步写回
- [x] `progress_summary.json`（sidecar）：含`_source_checksum`、项目统计等
- [x] CLI暴露（外部可见）：`validate-feature-readiness`, `set-lifecycle-state`
- [x] CLI内部入口（不放主帮助）：`import-feature-contract`, `add-retro`

### 2. Behavior Spec（按命令/流程定义）
- [x] `/prog-start`：兼容输入`developing`→内部`implementing`，自动导入合约，readiness校验，镜像双写
- [x] `/prog-done`：新增收尾门禁，三选一结果（merged_and_cleaned/pr_open/kept_with_reason），finish_pending阻断/prog-next
- [x] `/prog-next`：前置门禁检查`integration_status=finish_pending`或`cleanup_status=pending`
- [x] Worktree清理规则：仅干净时自动删，脏时进`cleanup_status=pending`
- [x] 审计与可追溯：关键变更写入`updates`，自动refs注入，手工refs保护

### 3. Implementation Blueprint（Claude执行顺序，禁止跳步）
- [x] 基线与失败测试先行：契约测试先红灯后转绿
- [x] 事务层与并发锁：统一事务包装，独占锁，主状态与summary同事务写入
- [x] schema 2.1回填与迁移校验：`_apply_schema_defaults`，`validate_post_migration`，失败回滚
- [x] 脑裂修复与降级开关：`reconcile_legacy_state`，`PROG_DISABLE_V2=1`分支
- [x] 合约自动导入与Markdown FSM解析器：JSON/MD双格式，无依赖行级状态机
- [x] readiness校验器与`/prog-start`串联：阻断+告警分层，接入`set_development_stage`
- [x] 生命周期API与回退规则：`set-lifecycle-state`，合法边校验，reason必填，审计写入
- [x] `prog-done`收尾门禁：`apply_finish_gate`，三选一结果落库
- [x] refs智能裁剪：自动refs注入，overflow收纳，手工refs保护
- [x] summary投影与状态展示：`progress_summary.json`生成，checksum校验，失配重建
- [x] 命令文档与帮助更新：只公开2个新增排障命令
- [x] 全量回归与验收报告：跑测试全集，输出风险余项

### 4. Test Plan（必须覆盖的场景）
- [x] 迁移与兼容：v2.0回填，状态映射，降级开关往返
- [x] 并发与一致性：双进程并发写，summary checksum失配重建，锁超时处理
- [x] 合约导入与门禁：JSON/MD解析，阻断/告警，中英标题变体
- [x] 生命周期与回退：正向流转，合法回退，非法拒绝，验收结果重置
- [x] `prog-done`收尾门禁：三选一结果，finish_pending阻断，各路径闭环
- [x] worktree清理：干净自动删，脏不删进pending，失败可重试
- [x] refs与审计：自动注入，overflow收纳，手工保护，关键变更必审计

### 5. Assumptions and Defaults
- [x] 不接OpenSpec，状态写入口单点保持在`progress_manager.py`
- [x] 默认门禁策略为"结构阻断 + 内容告警"
- [x] 合约目录固定`docs/progress-tracker/contracts`
- [x] 对外新增命令维持最小集合（仅`validate-feature-readiness`和`set-lifecycle-state`）
- [x] `progress_summary.json`仅为投影缓存，冲突以`progress.json`为真值

## 四个部分设计文档覆盖情况

### 第一部分：架构概览与阶段划分
- [x] 阶段实施策略（D+方案）
- [x] 架构模块划分
- [x] 收尾三选一状态机概念
- [x] 现有代码集成点
- [x] 向后兼容保证
- [x] readiness_validator前移为"软门禁"
- [x] 最强大脑建议（优先级从高到低）
- [x] 集成测试策略
- [x] 故障演练测试

### 第二部分：数据模型、迁移安全与事务管理
- [x] Schema 2.1数据模型详细设计（包含所有Public Interfaces要求）
- [x] 合法状态组合矩阵（P0必须实现）
- [x] 向后兼容与双写机制
- [x] 迁移安全机制（P0：持久化fsync链路）
- [x] TransactionManager实现
- [x] 备份与回滚策略
- [x] 脑裂修复与状态一致（`reconcile_legacy_state`算法）
- [x] 坏数据迁移策略（增强版）
- [x] PROG_DISABLE_V2读写不破坏测试（P0）
- [x] 可观测指标（阶段1）
- [x] /prog-next阻断规则
- [x] 故障演练测试（P0必须覆盖）

### 第三部分：收尾门禁与工作流集成
- [x] 收尾三选一状态机详细设计（三选一：merged_and_cleaned/pr_open/kept_with_reason）
- [x] 合法状态组合矩阵与修复白名单
- [x] `/prog-done`收尾门禁实现（修正版）
- [x] `detect_finish_state`算法（基于git历史的精确检测）
- [x] `prog-set-finish-state`命令（新增，用于二段式落盘）
- [x] `apply_finish_choice`实现（参数化，无input()）
- [x] worktree清理规则（修正：使用git原生命令）
- [x] 安全清理算法（使用git worktree命令）
- [x] `prog-cleanup-worktree`命令实现
- [x] finish_pending阻断`/prog-next`逻辑（分层设计）
- [x] 分层阻断检查算法
- [x] `/prog-next`扩展实现（分层响应）
- [x] 硬规则执行（带修复白名单）
- [x] 超时策略与二次确认机制（补全数据契约）
- [x] 带数据契约的超时检测算法
- [x] 二次确认机制（参数化，无input()）
- [x] 新增命令：超时管理
- [x] 集成点与现有代码兼容性
- [x] 向后兼容处理（迁移策略）
- [x] 新增命令清单（排障与修复）
- [x] 可观测指标（阶段2）与监控
- [x] 每日自检任务（增强版）
- [x] P0修正总结（6个P0修正已覆盖）

### 第四部分：实施计划与测试策略
- [x] 实施蓝图（12个阶段执行顺序）
- [x] 每个阶段的DoD（完成定义）
- [x] 测试计划（7大场景详细测试用例）
- [x] 集成策略与现有代码兼容性
- [x] 验收标准与质量门禁
- [x] 可观测指标（5个关键指标）
- [x] 风险控制与应急预案
- [x] 实施时间线与里程碑（14天，5个里程碑）
- [x] 交付物与文档
- [x] 附录：关键设计决策

## 关键覆盖验证

### ✅ 完全覆盖的要求
1. **数据模型**：所有Public Interfaces字段定义完整，包括强制字段、可选字段、向后兼容机制
2. **迁移安全**：事务管理、fsync链路、备份回滚、脑裂修复、降级开关
3. **收尾门禁**：三选一状态机、分层阻断、worktree清理、超时策略
4. **实施顺序**：12阶段蓝图明确，禁止跳步，每个阶段有DoD
5. **测试覆盖**：7大测试场景详细，包含所有关键用例

### ✅ 增强与扩展的设计
1. **分层阻断机制**：硬阻断vs软告警，更细致的用户体验
2. **修复白名单**：为修复动作提供例外通道，避免自锁
3. **数据契约**：时间字段契约、超时配置、缺失字段处理
4. **可观测指标**：各阶段定义明确指标，便于监控验收
5. **应急预案**：数据回滚、功能降级、紧急修复机制

### ✅ P0修正已覆盖（第三部分）
1. ✅ 自动判定 merged_and_cleaned 条件过宽 → 基于git历史检查
2. ✅ 不要在核心库里用 input() 交互 → 参数化或二段式流程
3. ✅ worktree 清理不能 shutil.rmtree() → 必须使用 git worktree remove + prune
4. ✅ /prog-next 阻断要分"硬阻断/软告警" → 分层设计
5. ✅ 硬规则1会误伤"修复动作" → 添加修复动作白名单
6. ✅ 超时与二次确认机制需补数据契约 → 完整时间字段契约

## 遗漏或需要澄清的点

### 1. 合约目录具体路径
原版plan：`docs/progress-tracker/contracts`
设计文档：需要明确在合约导入器实现中确认此路径

### 2. Markdown FSM解析器具体实现
原版plan要求"无依赖行级状态机，支持中英标题与编号/层级变体"
设计文档第四部分提到了此要求，但需要在实际编码阶段详细设计

### 3. 自动refs注入的overflow策略
原版plan要求`updates[].refs_overflow`字段
设计文档提到了overflow收纳，但需要确认字段名称和具体实现

### 4. 两个新增排障命令的具体参数
原版plan：`validate-feature-readiness --feature-id <id>`，`set-lifecycle-state --feature-id <id> --state <target> --reason "<text>"`
设计文档需要确认这些命令的完整参数列表和验证规则

## 结论

**四个部分设计文档已完全覆盖原版PROG全量规范化计划的所有核心要求**，并在以下方面进行了增强：

1. **更详细的数据模型**：包含完整的时间字段契约、状态组合矩阵、迁移策略
2. **更安全的迁移机制**：fsync完整链路、备份回滚、脑裂修复算法
3. **更完善的收尾门禁**：分层阻断、修复白名单、超时数据契约
4. **更系统的实施计划**：12阶段蓝图，每个阶段有明确DoD
5. **更全面的测试覆盖**：7大场景详细测试用例

**设计已准备好进入编码实施阶段**。

## 建议下一步行动

1. **直接进入编码阶段**：按第四部分的12阶段蓝图开始实施
2. **选择性创建QUALITY_GATE_CHECKLIST**：如需对外评审/发布审批，可创建1页版验收清单
3. **开始第一阶段实施**：基线与失败测试先行，建立契约测试基线

**推荐行动**：直接进入编码实施阶段，按蓝图顺序执行。