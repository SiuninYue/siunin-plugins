---
description: AI-first natural language intake for bugs, features, tasks, and updates. Haiku classifies intent, then commits via prog smart --commit.
version: "1.0.0"
scope: command
inputs:
  - Natural language description of a work item (bug report, feature idea, task, or update)
outputs:
  - Preview candidate (no --commit) or committed record in bugs[]/features[]/tasks[]/updates[]
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:prog-smart"
  - args: "$ARGUMENTS"

WAIT for the skill to complete.
</CRITICAL>
