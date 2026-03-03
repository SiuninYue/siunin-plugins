---
description: Check workspace safety and get worktree recommendations
version: "1.0.0"
scope: command
inputs:
  - User request to check workspace status
outputs:
  - Current workspace status (branch, worktree mode)
  - Safety warnings if any
  - Recommendations for worktree creation
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the command. You MUST execute it.

Run the workspace check command:

```bash
plugins/progress-tracker/prog check-workspace
```

Parse the JSON output and present it in a user-friendly format.
</CRITICAL>
