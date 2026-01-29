---
description: Start implementing the next pending feature
version: "1.0.0"
scope: command
inputs:
  - User request to start next feature
outputs:
  - Selected feature details
  - Implementation workflow launched
  - Test steps for the feature
evidence: optional
references: []
model: sonnet
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:feature-implement"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
