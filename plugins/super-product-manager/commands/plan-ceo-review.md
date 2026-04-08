---
version: "1.0.0"
scope: command
inputs:
  - 产品合同主题
  - 机会点与风险点
  - 结论（通过/风险）
outputs:
  - docs/product-reviews/*-plan-ceo-review.md
  - 同步到 PROG 的 planning 更新（source=spm_planning）
evidence: optional
references: []
description: 对产品合同执行 CEO 视角评审并沉淀可追溯结论
argument-hint: 例如：评审 Harness 联动方案的机会与主要风险
---
# /plan-ceo-review

用于产品层机会评审（preflight review）。

执行要求：
1. 输出机会、风险、结论，不写技术实现路径。
2. 产物落盘到 `docs/product-reviews/`。
3. 同步 `planning:ceo_review` 与 `doc:*` refs 到 PROG。
