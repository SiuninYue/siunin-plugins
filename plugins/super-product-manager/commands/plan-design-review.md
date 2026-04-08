---
version: "1.0.0"
scope: command
inputs:
  - 评审主题
  - 设计评分（0-10）
  - 优点/问题/建议
  - 可选 change categories（用于 lane 建议）
outputs:
  - docs/product-reviews/*-plan-design-review.md
  - 同步到 PROG 的 planning 更新（source=spm_planning）
evidence: optional
references: []
description: 执行设计质量评审并输出结构化结论
argument-hint: 例如：为前端交互方案做 0-10 设计评审
---
# /plan-design-review

用于设计维度 preflight 评审（可选 lane）。

执行要求：
1. 输出评分、问题、建议，不写技术实现路径。
2. 根据变更类型给出 design/devex lane 建议（自动建议，不硬阻断）。
3. 产物落盘并同步 `planning:design_review` + `doc:*` refs 到 PROG。
