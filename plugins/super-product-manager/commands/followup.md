---
version: "1.0.0"
scope: command
inputs:
  - action item id 或主题
  - 跟进状态（进行中/阻塞/完成）
  - 备注
outputs:
  - action-items.json 状态更新
  - 同步到 PROG 的 status/handoff 更新
evidence: optional
references: []
description: 跟进会议行动项并同步状态到 progress-tracker
argument-hint: 例如：A-20260309-01 已完成联调，下步准备灰度
---
# /followup

用于更新行动项进度与交接信息：
1. 更新 `docs/meetings/action-items.json` 对应项状态。
2. 同步 `status|handoff` 更新到 PROG。
3. 同步失败不阻断本地状态更新，记录 `sync_errors`。
