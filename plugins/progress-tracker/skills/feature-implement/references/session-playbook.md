# Session Playbook (Feature Implement)

Use this reference when `current_feature_id` is already set or when workflow state indicates interrupted execution.

## Resume Matrix

| State | Condition | Action |
|---|---|---|
| Ready for completion | `phase=execution_complete` | Direct user to `/prog done` |
| Mid execution | `phase=execution` and valid plan | Resume from next unfinished task |
| Plan missing | `phase in {planning_complete, execution}` and invalid plan | Recreate plan, then continue |
| Inconsistent lock | `current_feature_id` missing in features | Run recovery workflow before next delegation |
| planning:clarifying | Questions field present | Re-ask questions, proceed to draft after answers |
| planning:draft | Plan + PlanSummary present | Display PlanSummary, wait for approval; do NOT re-run brainstorming |
| planning:approved | Phase=planning:approved | Read persisted bucket, route directly to execution |

## Standard Resume Prompt

```markdown
## Resume Detected

- Feature: <id> - <name>
- Phase: <phase>
- Plan: <valid|invalid>
- Tasks: <completed>/<total>
- Branch: <branch> | Worktree: <worktree or "none">

Recommended next action:
1. <primary action>
2. <fallback action>
```

Always append a Context Handoff Block at the end so the user can continue in a new session without losing state. See `communication-templates.md` → "Context Handoff Block" for the exact format.

## Plan Recreation Trigger

Recreate plan **only** when ALL of the following are true:

- `workflow_state.plan_path` is set (i.e., a plan was previously created)
- The file at `plan_path` does not exist or `validate-plan` returns non-zero
- The current phase is `planning_complete` or `execution` (we expect a plan to exist)

**Do NOT recreate if:**
- `plan_path` is absent because we are starting fresh (normal — create plan for the first time)
- User explicitly specified a plan file path — trust it, do not validate structure
- `workflow_state.execution_context` matches current branch/worktree (we are resuming correctly)

## Planning Sub-Phase Recovery

### `planning:draft` — Plan File Missing

If plan file at `plan_path` does not exist:
- Use `PlanSummary` from inline context (or persisted state) to reconstruct plan without re-running brainstorming.
- Do not re-run `brainstorming` skill — use existing summary as context.

### `planning:approved` — New Session

- Read persisted `feature.ai_metrics.complexity_bucket` from progress state.
- Route directly to implementation path based on bucket (no planning questions).
- If bucket unavailable, default to `standard` path with warning.

### Guard: No Regression from Draft

Once `planning:draft` is reached, do NOT revert to `planning:clarifying`. Recovery always moves forward.

## Safe Fallback

If specialized route fails (simple/complex delegate failure):

1. Keep active feature lock.
2. Switch to standard coordinator path.
3. Re-run planning + subagent execution.
4. Record fallback in workflow `next_action`.
