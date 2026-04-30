---
version: "1.2.0"
scope: command
inputs:
  - 产品目标
  - 范围边界
  - 验收标准
  - 关键风险
outputs:
  - docs/product-contracts/*.md 产品合同文档
  - 同步到 PROG 的 planning 更新（source=spm_planning）
evidence: optional
references:
  - ../skills/office-hours/SKILL.md
description: 生成 planner-only 产品合同（不含技术实现路径）
argument-hint: 例如：为 Harness 联动定义目标、范围和验收标准
---
# /office-hours

用于前置产品澄清（planner 角色）。输出仅含目标、范围、验收标准、风险，严禁写入技术实现路径。

## 执行流程

1. 接收输入 + 按 `skills/office-hours/SKILL.md` 的需求澄清三板斧犀利追问
2. 调用 `skills/office-hours/SKILL.md` 产出合同 artifact，落盘到 `docs/product-contracts/`
3. 通过 `planning_workflow.py` 同步 `planning:office_hours` + `doc:*` refs 到 PROG
4. 【子 agent 审查】按 skill 中的子 Agent 审查指令执行，最多 2 次迭代
5. 审查通过 → 结束；advisory → 记录到 update details，结束；blocking 2 次耗尽 → 追加 risk update，报告用户
