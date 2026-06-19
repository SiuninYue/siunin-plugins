---
name: prog-smart
description: Route /prog-smart to prog smart CLI with AI classification. Use when user wants to add a work item via natural language (bug report, feature idea, task, or status update).
model: haiku
---

# prog-smart intake flow

## Purpose
Classify user's natural language input and commit it to progress tracking as the correct work-item type (bug/feature/task/update). If no live progress tracker exists, act as an intake router, previewing setup options and guiding the user.

## Flow

1. **Check Live Tracker**: Check if an active tracker exists in the current project root (i.e., whether `docs/progress-tracker/state/progress.json` is present).
2. **If Live Tracker Exists (Normal Intake Flow)**:
   - **Classify**: Analyze the user's text to identify the correct work-item type (bug/feature/task/update) and construct a candidate JSON.
   - **Preview**: Call `prog smart --candidate-json '<json>'` (no `--commit`). Show the candidate preview to the user.
   - **Clarify (if needed)**: If confidence < 0.6, ask the user ONE clarification question. Re-classify with their response.
   - **Commit**: Call `prog smart --candidate-json '<json>' --commit <type>` to write the record.
3. **If NO Live Tracker Exists (Route-Preview Flow)**:
   - **Analyze Context & History**:
     - Check for recently archived trackers by running `prog list-archives` or reading `progress_history.json`.
     - Analyze if the user's input refers to starting a new project, setting up a maintenance scope, or planning architecture.
   - **Generate Route Preview**: Show a clear preview explaining that no live tracker was found and suggest options:
     ```text
     No live tracker found for progress-tracker.

     Suggested routes:
     1. Restore last archived tracker: <last-archived-project-name> (archive_id: <id>)
     2. Start new maintenance tracker: <suggested-project-name>
     3. Create architecture/automation plan first via /prog-plan
     4. Select a specific project root (if monorepo scope is ambiguous)

     Recommended: <Option Number>
     Reason: <reasoning based on input context>
     ```
   - **Confirm & Route (do NOT silently run setup)**: Present the Route Preview, recommend one option, and request explicit confirmation. Then route by the chosen option — never run `prog init` yourself:
     - **New project / architecture plan**: do NOT run `prog init` directly — it skips interactive feature breakdown. Instruct the user to run `/progress-tracker:prog-init <goal>` (or the `/prog-init` shortcut), or `/prog-plan`, which performs the proper breakdown.
     - **Restore archived tracker**: after confirmation you may run `prog restore-archive <archive_id>` directly (idempotent recovery, no breakdown needed), then proceed to commit the candidate item(s).
     - **Ambiguous monorepo root**: ask the user to disambiguate the project root before any action — do not guess.

## Batch Intake Handling
If the user's input contains multiple distinct updates, bugs, or tasks:
- Segment the input and classify each item into its own candidate JSON.
- Preview all candidates to the user sequentially in a single response.
- Once confirmed, commit each candidate sequentially.

## Candidate JSON Format

```json
{
  "type": "bug",
  "confidence": 0.92,
  "profile": {
    "description": "crash on startup when config is missing",
    "priority": "P0",
    "details": "reproducible on fresh install",
    "refs": [],
    "next_action": "investigate config loader",
    "category": "status"
  }
}
```

## Rules

- **Never write JSON without explicit --commit** (preview is zero-mutation)
- **No silent setup**: with no live tracker, never run `prog init` yourself — route project creation to `/progress-tracker:prog-init` so feature breakdown happens. (Restoring an archive via `prog restore-archive` is allowed after confirmation.)
- **Exactly one clarification question** when ambiguous (confidence < 0.6)
- Priority values: P0 (critical/high), P1 (medium), P2 (low/normal)
- Category (for update type): status | decision | risk | handoff | assignment | meeting

## CLI Reference

```bash
# Preview only (no mutation)
prog smart --candidate-json '<json>'

# Commit
prog smart --candidate-json '<json>' --commit bug
prog smart --candidate-json '<json>' --commit feature
prog smart --candidate-json '<json>' --commit task
prog smart --candidate-json '<json>' --commit update
```

## Common Mistakes

| 错误 ❌ | 正确 ✅ |
|----------|--------|
| `--json` | `--candidate-json` |
| 直接 `--commit` 跳过预览 | 先预览，用户确认后再 `--commit` |
| `--type bug` | `--commit bug` |
