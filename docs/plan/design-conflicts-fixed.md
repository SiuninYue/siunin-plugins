# 设计文档冲突修复总结

## 修复完成时间
2026-03-11

## 修复的冲突列表

### [P1] 新增命令口径冲突
**问题**：part4把新增命令限制为2个，但part3-v2定义了完整新命令集，且`/prog-done`依赖`prog-set-finish-state`二段式落盘。

**修复**：
1. **part4 line 9**：澄清"对外公开的新增命令仅保留2个排障入口，内部实现会有更多辅助命令"
2. **part4 line 111**：更新为"确保只公开2个新增排障命令...内部实现命令仅用于特定流程"
3. **新增章节**：在part4添加"命令清单与公开策略"章节，明确区分：
   - 对外公开命令（2个）：`validate-feature-readiness`, `set-lifecycle-state`
   - 内部排障命令（10个）：包括`prog-set-finish-state`、`prog-cleanup-worktree`等

### [P1] /prog-next门禁规则矛盾
**问题**：part2规定`cleanup_status=pending`一律阻断；part3-v2定义`pr_open + pending`为软告警不阻断。

**修复**：
1. **更新part2的`check_finish_gate_blocking`函数**（line 429-447）：
   - 重写函数逻辑与part3-v2保持一致
   - 明确注释：`pr_open + cleanup=pending`是软告警不阻断
   - 硬阻断条件：`verified+finish_pending`、无效`kept_with_reason`、状态不一致、`merged_and_cleaned+pending`

### [P1] 状态机矩阵与执行校验漏洞
**问题**：矩阵限制`pr_open`仅适用于`verified`，但`set-finish-state`校验可能漏掉`archived -> pr_open`。

**修复**：
1. **增强part3-v2的`enforce_hard_rules`规则3**（line 537-560）：
   - 分三层校验：非`finish_pending`状态要求`lifecycle`在`verified/archived`中
   - 目标状态组合校验：`pr_open`仅允许`verified`、`kept_with_reason`和`merged_and_cleaned`仅允许`verified/archived`
   - 非法状态组合修复例外
2. **增强part3-v2的`apply_finish_choice`函数**（line 224-254）：
   - 在函数开头添加完整的状态组合校验
   - 与`enforce_hard_rules`保持一致的校验逻辑

### [P2] 状态命名不一致（cleanup_pending vs pending）
**问题**：part4使用`cleanup_pending`表述，但part2/part3-v2枚举值是`cleanup_status: pending|done|skipped`。

**修复**：
1. **part4 line 85**：`finish_pending/cleanup_pending` → `finish_pending`/`cleanup_status=pending`
2. **part4 line 173**：`cleanup_pending` → `cleanup_status=pending`
3. **part3-v2术语统一**：
   - line 626: `"cleanup_pending"` → `"cleanup_status_pending"`（超时配置键名）
   - line 927: `"cleanup_pending": 1` → `"cleanup_status_pending_count": 1`（监控字段）
   - line 940: `"type": "cleanup_pending"` → `"type": "cleanup_status_pending"`（超时警报）

### [P3] 4阶段(D+)与12阶段实施蓝图缺少显式映射表
**问题**：part1是4大阶段，part4是12执行阶段，缺少映射影响里程碑验收对齐。

**修复**：
1. **在part4添加映射表章节**（line 123后）：
   - 创建4阶段→12阶段映射表
   - 添加映射说明和实施指导
   - 确保里程碑对齐和验收一致性

## 修复后的一致性验证

### 单一权威原则落实
✅ **门禁规则以part3-v2为准**：所有`/prog-next`阻断逻辑与part3-v2保持一致
✅ **命令面以part3-v2为准**：完整命令清单得到认可，公开策略明确
✅ **状态矩阵以part2为准**：所有状态组合校验引用part2矩阵规则

### 术语统一完成
✅ **状态字段**：全文件统一使用`cleanup_status: pending|done|skipped`
✅ **超时类型**：统一使用`cleanup_status_pending`作为超时配置键名
✅ **监控字段**：统一使用`cleanup_status_pending_count`表示计数

### 实施蓝图清晰
✅ **阶段映射**：4阶段(D+)与12阶段实施蓝图显式映射
✅ **里程碑对齐**：每个4阶段里程碑对应多个12阶段实施步骤
✅ **验收一致性**：12阶段DoD保证4阶段里程碑验收标准

## 剩余注意事项

### part3.md（旧版本）
- 包含`cleanup_pending`引用，但part3-v2是新权威版本
- 建议：在实施时忽略part3.md，以part3-v2为准

### 实现细节
1. **超时配置键名变更**：`cleanup_pending` → `cleanup_status_pending`（代码实现需相应调整）
2. **监控字段名变更**：`cleanup_pending` → `cleanup_status_pending_count`（仪表板需调整）
3. **校验函数增强**：`set-finish-state`和`apply_finish_choice`需要实现完整的状态组合校验

## 结论

**所有P1、P2、P3冲突已修复**，设计文档达到"无歧义可执行"状态。

### 可进入编码实施阶段的条件
1. ✅ 设计冲突全部解决
2. ✅ 术语统一完成
3. ✅ 实施蓝图清晰
4. ✅ 测试计划完整

**建议**：立即按part4的12阶段蓝图开始编码实施。