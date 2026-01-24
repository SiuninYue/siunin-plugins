---
name: prog-reset
description: Reset progress tracking by deleting all tracking files
version: "1.0.0"
scope: command
inputs:
  - User request to reset progress
  - Optional force flag to skip confirmation
outputs:
  - Progress tracking files removed
  - Confirmation of reset completion
evidence: optional
references: []
model: haiku
---

请调用 skills/progress-management/SKILL.md 来重置项目进度。除非用户明确请求强制执行，否则在执行重置前**请求确认**。
