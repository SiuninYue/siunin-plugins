---
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

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:architectural-planning"
  - args: "{user_input}"

WAIT for the skill to complete.
</CRITICAL>
