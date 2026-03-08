---
version: "1.0.0"
scope: command
inputs:
  - 议题列表
  - 各角色观点与结论
outputs:
  - docs/meetings/*.md 讨论纪要
  - docs/meetings/action-items.json 行动项
  - 同步到 PROG 的 meeting/decision 更新结果
evidence: optional
references: []
description: 记录圆桌讨论并同步结构化更新到 progress-tracker
argument-hint: 例如：增长、技术、运营三方圆桌讨论 AI 功能上线节奏
---
# /roundtable

用于多角色议题讨论记录。流程与 `/meeting` 一致，但强调“观点分歧 -> 决策收敛”。

执行要求：
1. 落盘圆桌纪要到 `docs/meetings/`。
2. 更新行动项 JSON。
3. 调用桥接脚本同步到 PROG。
4. 出现同步异常时保留本地产物并报告错误摘要。
