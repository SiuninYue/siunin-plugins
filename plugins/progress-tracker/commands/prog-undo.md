---
name: prog-undo
description: Undo the last completed feature and revert its code changes
version: "1.0.0"
scope: command
inputs:
  - User request to undo last feature
outputs:
  - Git revert executed (if commit exists)
  - Feature marked as incomplete
  - Progress tracking updated
evidence: optional
references: []
model: sonnet
---

请调用 skills/progress-management/SKILL.md 来安全地撤销最近完成的功能。在继续之前，请确保工作目录是干净的。
