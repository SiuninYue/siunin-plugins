---
version: "1.2.0"
scope: command
inputs:
  - 产品合同主题
  - 机会点与风险点
  - 结论（通过/风险）
outputs:
  - docs/product-reviews/*-plan-ceo-review.md
  - 同步到 PROG 的 planning 更新（source=spm_planning）
evidence: optional
references:
  - ../skills/plan-ceo-review/SKILL.md
description: 对产品合同执行 CEO 视角评审并沉淀可追溯结论
argument-hint: 例如：评审 Harness 联动方案的机会与主要风险
---
# /plan-ceo-review

用于产品层机会评审（preflight review）。从 CEO 视角审视产品合同的商业合理性，输出机会、风险、Verdict 结论。

## 执行流程

1. 接收输入 + 按 `skills/plan-ceo-review/SKILL.md` 的五维评审原则犀利追问
2. 调用 `skills/plan-ceo-review/SKILL.md` 产出评审 artifact，落盘到 `docs/product-reviews/`
3. 通过 `planning_workflow.py` 同步 `planning:ceo_review` + `doc:*` refs 到 PROG
4. 【子 agent 审查】按 skill 中的子 Agent 审查指令执行，最多 2 次迭代
5. 审查通过 → 结束；advisory → 记录到 update details，结束；blocking 2 次耗尽 → 追加 risk update，报告用户
