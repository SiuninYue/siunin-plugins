---
name: prog-done
description: Complete and commit the current feature after testing
version: "1.0.0"
scope: command
inputs:
  - User request to complete current feature
outputs:
  - Test execution results
  - Feature marked as completed
  - Git commit with changes
  - Next step recommendation
evidence: optional
references: []
model: sonnet
---

请调用 skills/feature-complete/SKILL.md 来执行当前功能的测试步骤，验证实现，更新进度跟踪，并将更改提交到 Git。
