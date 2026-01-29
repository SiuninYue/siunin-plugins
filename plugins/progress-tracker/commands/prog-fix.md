---
description: Report, list, or fix bugs with smart scheduling and systematic debugging
version: "1.0.0"
scope: command
inputs:
  - Bug description (optional) or bug ID
outputs:
  - Bug verification and scheduling
  - Or bug fixing workflow
evidence: optional
references: []
model: sonnet
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:bug-fix"
  - args: "{user_input}"

WAIT for the skill to complete.
</CRITICAL>
