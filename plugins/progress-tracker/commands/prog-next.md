---
name: prog-next
description: Start implementing the next pending feature
version: "1.0.0"
scope: command
inputs:
  - User request to start next feature
outputs:
  - Selected feature details
  - Implementation workflow launched
  - Test steps for the feature
evidence: optional
references: []
model: sonnet
---

请调用 skills/feature-implement/SKILL.md 来识别下一个待处理功能，更新当前功能状态，并启动 feature-dev 工作流进行实现。
