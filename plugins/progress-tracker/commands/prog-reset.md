---
name: prog-reset
description: Reset progress tracking by deleting all tracking files
version: "1.0.0"
scope: command
inputs:
  - User request to reset progress
  - Optional force flag to skip confirmation
outputs:
  - Progress tracking files removed
  - Confirmation of reset completion
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:progress-management"
  - args: "reset"

WAIT for the skill to complete.
</CRITICAL>
