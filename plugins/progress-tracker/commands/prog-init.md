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

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:feature-breakdown"
  - args: "{user_input}"

WAIT for the skill to complete.
</CRITICAL>
