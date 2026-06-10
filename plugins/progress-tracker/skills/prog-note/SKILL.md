---
name: prog-note
description: This skill should be used when the user asks to "/prog note", "/prog-note", "record a project update", "add status update", "log decision/risk/handoff", or asks AI to add discussion items into progress tracking and needs intent triage (bug vs feature vs update).
model: haiku
---

# Prog Note Skill

Write structured updates into Progress Tracker through CLI commands only.  
AI is the classifier. Backend CLI should only execute explicit write commands.

## Intent Triage (AI-side)

Before any write, classify the user intent:
- **Bug** (symptom/failure/regression): call bug path (`/prog-fix` or `prog add-bug`).
- **Feature/Enhancement** (new capability/change request): call `prog add-feature`.
- **Progress Update** (status/decision/risk/handoff log): call `prog add-update`.

If intent is ambiguous, **MUST ask one clarification question and STOP**.  
Do not write anything until user confirms type.

Default rule:
- Do not auto-route ambiguous input to "idea".
- Use update logging only when user explicitly asks to "record/note/log update".

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

1. AI must classify first, then call only one write path (`add-bug` or `add-feature` or `add-update`).
2. Never edit `progress.json` directly.
3. For update path, use `plugins/progress-tracker/prog add-update`.
4. If both `role` and `owner` are provided with `feature_id`, also call:
   - `plugins/progress-tracker/prog set-feature-owner <feature_id> <role> <owner>`
5. On CLI failure, report the exact command and stderr summary.

## Feature/Bug Templates

```bash
plugins/progress-tracker/prog add-feature "<feature_name>" "<test_step_1>"
```

```bash
plugins/progress-tracker/prog add-bug \
  --description "<bug_description>" \
  --status "pending_investigation" \
  --priority "medium"
```

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
