---
description: Record a structured progress update (status/decision/risk/handoff/assignment/meeting)
version: "1.0.0"
scope: command
inputs:
  - User update intent and optional structured fields
outputs:
  - New update entry in progress.json updates[]
  - Refreshed progress.md with recent updates section
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:progress-update"
  - args: "$ARGUMENTS"

WAIT for the skill to complete.
</CRITICAL>
