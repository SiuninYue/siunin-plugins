---
name: prog-init
description: Initialize project progress tracking with feature breakdown
version: "1.0.0"
scope: command
inputs:
  - Project goal or description
  - Optional force flag to re-initialize
outputs:
  - Feature breakdown with test steps
  - Initialized progress tracking files
  - Next action recommendation
evidence: optional
references: []
model: sonnet
---

请调用 skills/feature-breakdown/SKILL.md 来分析目标，将其分解为具体功能并包含测试步骤，然后初始化进度跟踪。
