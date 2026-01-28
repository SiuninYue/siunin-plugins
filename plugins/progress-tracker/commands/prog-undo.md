---
name: prog-undo
description: Undo the last completed feature and revert its code changes
version: "1.0.0"
scope: command
inputs:
  - User request to undo last feature
outputs:
  - Git revert executed (if commit exists)
  - Feature marked as incomplete
  - Progress tracking updated
evidence: optional
references: []
model: sonnet
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:progress-management"
  - args: "undo"

WAIT for the skill to complete.
</CRITICAL>
