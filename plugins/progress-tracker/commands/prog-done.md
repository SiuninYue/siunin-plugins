---
description: Complete current feature via deterministic acceptance gatekeeping
version: "2.2.0"
scope: command
inputs:
  - User request to complete current feature
outputs:
  - Test execution results
  - Feature marked as completed or finish-pending
  - Git closeout result (merge-first with policy gates; fallback to blocker summary)
  - Next step recommendation
evidence: optional
references: []
model: sonnet
---

`/prog-done` uses a split architecture:
- Skill layer (`progress-tracker:feature-complete`) handles orchestration and user-facing flow.
- CLI layer (`progress_manager.py done`) enforces deterministic gates, acceptance execution, report writing, and completion state updates.

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:feature-complete"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
