---
version: "1.2.0"
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
references:
  - ../skills/plan-design-review/SKILL.md
description: 执行设计质量评审并输出结构化结论（含自动建议 lane 推荐）
argument-hint: 例如：为前端交互方案做 0-10 设计评审
---
# /plan-design-review

用于设计维度 preflight 评审（可选 lane）。从设计质量视角审视产品方案，输出评分、问题、建议（自动建议，不硬阻断）。

## 执行流程

1. 接收输入 + 按 `skills/plan-design-review/SKILL.md` 的四维评分体系追问
2. 调用 `skills/plan-design-review/SKILL.md` 产出评审 artifact，落盘到 `docs/product-reviews/`；根据变更类型给出 design/devex lane 自动建议
3. 通过 `planning_workflow.py` 同步 `planning:design_review` + `doc:*` refs 到 PROG
4. 【子 agent 审查】按 skill 中的子 Agent 审查指令执行，最多 2 次迭代
5. 审查通过 → 结束；advisory → 记录到 update details，结束；blocking 2 次耗尽 → 追加 risk update，报告用户
