---
version: "1.0.0"
scope: command
inputs:
  - 会议主题与背景
  - 决策摘要与行动项
outputs:
  - docs/meetings/*.md 会议纪要
  - docs/meetings/action-items.json 行动项
  - 同步到 PROG 的 meeting/decision 更新结果
evidence: optional
references: []
description: 记录会议纪要并同步到 progress-tracker
argument-hint: 例如：支付重构评审，结论是先拆网关后迁移账单
---
# /meeting

将输入整理为会议纪要，写入 `docs/meetings/`，并通过 `prog_bridge.py` 同步到 PROG。

执行要求：
1. 产出会议纪要文件（含主题、决策、行动项）。
2. 更新 `docs/meetings/action-items.json`。
3. 调用桥接脚本同步 `meeting|decision` 更新。
4. 同步失败不阻断产物写入，返回 `sync_errors` 与修复建议。
