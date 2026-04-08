---
version: "1.0.0"
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
references: []
description: 生成 planner-only 产品合同（不含技术实现路径）
argument-hint: 例如：为 Harness 联动定义目标、范围和验收标准
---
# /office-hours

用于前置产品澄清（planner 角色）。

执行要求：
1. 仅输出目标、范围、验收标准、风险，不写技术实现方案。
2. 产物落盘到 `docs/product-contracts/`。
3. 通过 `planning_workflow.py` 调用 bridge，同步 `planning:office_hours` 与 `doc:*` refs 到 PROG。
