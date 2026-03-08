---
name: progress-update
description: This skill should be used when the user asks to "/prog-update", "record a project update", "add status update", "log decision/risk/handoff", or needs to write structured update entries into progress tracking.
model: haiku
version: "1.0.0"
scope: skill
inputs:
  - Raw update text or structured fields
outputs:
  - `updates[]` entry persisted via prog CLI
  - Optional owner assignment when role/owner is provided
evidence: optional
references: []
---

# Progress Update Skill

Write structured updates into Progress Tracker through CLI commands only.

## Input Mapping

Prefer these normalized fields:
- `category`: one of `status|decision|risk|handoff|assignment|meeting`
- `summary`: short required sentence
- `details`: optional long-form details
- `feature_id`: optional numeric feature id
- `bug_id`: optional bug id
- `role`: optional `architecture|coding|testing`
- `owner`: optional owner text
- `source`: optional, default `prog_update`
- `next_action`: optional next step
- `refs`: optional list of refs

If user input is unstructured, infer `summary` from the first sentence and set category to `status` by default.

## Execution Rules

1. Use `plugins/progress-tracker/prog add-update` to append an update.
2. Never edit `progress.json` directly.
3. If both `role` and `owner` are provided with `feature_id`, also call:
   - `plugins/progress-tracker/prog set-feature-owner <feature_id> <role> <owner>`
4. On CLI failure, report the exact command and stderr summary.

## Command Templates

```bash
plugins/progress-tracker/prog add-update \
  --category "<category>" \
  --summary "<summary>" \
  --details "<details>" \
  --source "prog_update"
```

```bash
plugins/progress-tracker/prog set-feature-owner <feature_id> <role> "<owner>"
```

## Output Contract

Return concise confirmation:
1. `category` + `summary`
2. related `feature_id/bug_id` if any
3. owner assignment result if executed
4. actionable next step if write failed
