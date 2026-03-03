---
name: prog-start
description: This skill should be used when the user runs "/prog-start", asks to "start current feature", "start implementation now", "开始当前功能开发", or requests transitioning an active feature from planning to developing.
model: haiku
version: "1.0.0"
scope: skill
inputs:
  - Current progress tracking state
outputs:
  - Active feature moved to developing stage
  - started_at timestamp recorded (if missing)
  - Clear next-step guidance
evidence: optional
references: []
---

# Prog Start Skill

Transition the active feature to implementation mode.

## Optional: Workspace Check

Before starting implementation, you may optionally check workspace state:

```bash
plugins/progress-tracker/prog check-workspace
```

This is informational only - use your judgment based on:
- **Small changes**: Can proceed directly
- **Feature work**: Consider worktree for better isolation

## Main Flow

1. Set active feature stage to `developing`:

```bash
plugins/progress-tracker/prog set-development-stage developing
```

2. Handle common error cases:
- If no tracking exists: guide user to `/prog init <goal>`.
- If no active feature exists: guide user to `/prog next`.
- If feature lookup fails: return concise failure reason from command output.

3. On success, respond with:
- started feature id/name (from command output)
- reminder to run `/prog done` after acceptance checks pass.

## Notes

- `/prog next` should place the selected feature in `planning`.
- `/prog start` is the explicit transition from `planning -> developing`.
- Runtime session context is persisted automatically by progress-manager commands; recovery and `/prog done` may warn if later sessions run in a different worktree/branch.
- **Workspace safety is critical**: Always verify worktree isolation before starting implementation.
