---
description: Start active feature development from planning stage
version: "1.0.0"
scope: command
inputs:
  - User request to start current feature implementation
outputs:
  - Active feature moved to developing stage
  - started_at timestamp persisted
  - Next-step reminder to use /prog done
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:prog-start"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
