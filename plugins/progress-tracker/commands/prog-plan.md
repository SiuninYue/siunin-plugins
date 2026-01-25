---
name: prog-plan
description: Create architectural plan with technology selection and system design
version: "1.0.0"
scope: command
inputs:
  - Project description or goal
  - Optional specific architecture concerns
outputs:
  - Technology stack recommendations
  - System architecture design
  - Architectural decision records (.claude/architecture.md)
  - Integration guidance for feature breakdown
evidence: optional
references: []
model: sonnet
---

请调用 skills/architectural-planning/SKILL.md 来进行技术选型、系统架构设计和决策记录，创建或更新架构文档。
