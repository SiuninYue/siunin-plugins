# PRD Organization Rules

## 分段式 PRD 组织规则

### 适用场景

当 PRD 文档过大（超过模型 token 限制）或需要多人/多技能协作编辑时，可将 PRD 拆分为多个章节文件。

### 目录结构

```
/项目/docs/prd/
├── _index.md           # 索引文件（必读）：目录 + 各章节摘要
├── 01-background.md    # 背景与目标
├── 02-user-analysis.md # 用户分析 / 用户故事
├── 03-requirements.md  # 功能范围 / 需求描述
├── 04-specification.md # 详细需求 / 功能规格
├── 05-acceptance.md    # 验收标准
├── 06-metrics.md       # 数据指标
├── 07-non-functional.md# 非功能需求
├── 08-dependencies.md  # 依赖与风险
├── 09-launch-plan.md   # 上线计划
└── 10-appendix.md      # 附录
```

### 加载策略

1. **索引优先**：始终先读取 `_index.md` 了解整体结构和各章节摘要
2. **按需加载**：根据任务只加载需要的章节文件
3. **局部编辑**：修改特定章节时，只加载并编辑该章节文件

### 协作约束

- **不扩展结构**：PRD 只按既有模板章节输出，不新增章节
- **仅补充已存在章节**：只有 PRD 已包含某章节，才允许对应技能补充内容
- **保持一致性**：编辑后检查术语、引用是否与其他章节一致
