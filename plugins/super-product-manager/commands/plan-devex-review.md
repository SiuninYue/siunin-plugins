---
version: "1.0.0"
scope: command
inputs:
  - 评审主题
  - DevEx 评分（0-10）
  - friction 点与改进建议
  - 可选 change categories（用于 lane 建议）
outputs:
  - docs/product-reviews/*-plan-devex-review.md
  - 同步到 PROG 的 planning 更新（source=spm_planning）
evidence: optional
references: []
description: 执行 DevEx 摩擦评审并输出结构化结论
argument-hint: 例如：评审开发流程中的 friction 和改进优先级
---
# /plan-devex-review

用于开发体验维度 preflight 评审（可选 lane）。

执行要求：
1. 输出评分、friction、改进建议，不写技术实现路径。
2. 根据变更类型给出 design/devex lane 建议（自动建议，不硬阻断）。
3. 产物落盘并同步 `planning:devex_review` + `doc:*` refs 到 PROG。
