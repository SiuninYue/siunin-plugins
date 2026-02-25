---
description: Sync project capability memory from git history with batch confirmation
version: "1.0.0"
scope: command
inputs:
  - User request to sync project memory
outputs:
  - Candidate capabilities from incremental commits
  - Batch confirmation result
  - Updated project memory summary
evidence: optional
references: []
model: sonnet
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:prog-sync"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
