---
description: Show progress-tracker command help
version: "1.0.0"
scope: command
inputs:
  - User request for command usage help
outputs:
  - Available progress-tracker commands with quick examples
evidence: optional
references: []
model: haiku
---

Show help for the `progress-tracker` plugin commands.

Respond in Chinese by default unless the user explicitly asks for English.

Use this structure:

## Progress Tracker Commands

- `/prog plan <project description>`: architecture planning and stack decisions.
- `/prog init <goal description>`: initialize tracking and feature decomposition.
- `/prog`: show progress status and recommendations.
- `/prog next`: begin next feature using deterministic routing.
- `/prog done`: run acceptance checks and complete current feature.
- `/prog-fix [description|BUG-ID]`: report/list/fix bugs.
- `/prog undo`: revert most recently completed feature.
- `/prog reset`: reset tracking files with confirmation.
- `/prog-ui`: launch web UI server and open browser.

## Namespaced Usage

When global command resolution conflicts, use namespaced form:

- `/progress-tracker:help`
- `/progress-tracker:prog`
- `/progress-tracker:prog-ui`

Keep the response concise and practical.
