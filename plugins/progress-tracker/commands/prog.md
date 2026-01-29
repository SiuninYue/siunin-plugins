---
description: Display project progress status
version: "1.0.0"
scope: command
inputs:
  - User request to view progress
outputs:
  - Current progress status with statistics
  - Active/inactive features list
  - Next step recommendations
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:progress-status"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
