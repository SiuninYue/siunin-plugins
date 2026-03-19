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

- `/progress-tracker:prog-plan <project description>` (alias: `/prog-plan`): architecture planning and stack decisions.
- `/progress-tracker:prog-init <goal description>` (alias: `/prog-init`): initialize tracking and feature decomposition.
- `/progress-tracker:prog` (alias: `/prog`): show progress status and recommendations.
- `/progress-tracker:prog-sync` (alias: `/prog-sync`): sync project capability memory from git history with batch confirmation.
- `/progress-tracker:prog-update [category|summary]` (alias: `/prog-update`): record a structured progress update (status/decision/risk/handoff/assignment/meeting).
- `/progress-tracker:prog-next` (alias: `/prog-next`): begin next feature using deterministic routing.
- `/progress-tracker:prog-done` (alias: `/prog-done`): run acceptance checks and complete current feature.
- `/progress-tracker:prog-fix [description|BUG-ID]` (alias: `/prog-fix`): report/list/fix bugs.
- `/progress-tracker:prog-undo` (alias: `/prog-undo`): undo the last completed feature and revert its code changes.
- `/progress-tracker:prog-reset` (alias: `/prog-reset`): reset active tracking files with confirmation (auto-archive previous snapshot).
- `/progress-tracker:help`: show plugin command help (prefer namespaced form to avoid `/help` conflicts).
- `/progress-tracker:prog-ui` (alias: `/prog-ui`): launch web UI server and open browser.

## Format Notes

- Prefer namespaced form in docs/examples for deterministic plugin routing.
- If Claude Code shows a short command (for example `/prog`), it refers to the same plugin command.
- Do not put a space after `:`. Use `/progress-tracker:prog`, not `/progress-tracker: prog`.
- Slash commands are daily workflow; CLI commands are diagnostics/admin/automation.
- In Codex/local shell, use `plugins/progress-tracker/prog --project-root plugins/<name> <command>` for the same backend behavior.

Keep the response concise and practical.
