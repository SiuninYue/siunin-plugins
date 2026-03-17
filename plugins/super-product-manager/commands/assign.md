---
version: "1.0.0"
scope: command
inputs:
  - feature_id
  - role(architecture|coding|testing)
  - owner
outputs:
  - PROG feature owners 更新结果
  - assignment 类型更新记录
evidence: optional
references: []
description: 为指定功能分配角色负责人并同步到 progress-tracker
argument-hint: 例如：feature 3 coding 由 Alice 负责
---
# /assign

将负责人分配同步到 PROG：
1. 调用 `prog set-feature-owner` 设置 `features[].owners[role]`。
2. 写入一条 `assignment` 更新用于追溯。
3. 返回执行摘要；失败时提供可复现命令。
