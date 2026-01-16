---
name: launch
description: 上线发布技能。用于上线检查、沟通节奏与风险控制。
model: sonnet
version: "1.1.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
references: []
---
# launch

## 延迟加载规则

- 默认只使用本文件内容
- 只有在用户明确要求细节或需要模板时，才加载 references 中的附件
- 未加载附件时，先给摘要与下一步

## 核心说明

上线发布技能。用于上线检查、沟通节奏与风险控制。

## 输出结构（概览）

- 关键结论
- 支撑证据与时间戳
- 风险与约束
- 下一步行动
