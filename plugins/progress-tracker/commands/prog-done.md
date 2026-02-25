---
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

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:feature-complete"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
