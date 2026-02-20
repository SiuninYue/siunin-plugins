# Session Playbook (Feature Implement)

Use this reference when `current_feature_id` is already set or when workflow state indicates interrupted execution.

## Resume Matrix

| State | Condition | Action |
|---|---|---|
| Ready for completion | `phase=execution_complete` | Direct user to `/prog done` |
| Mid execution | `phase=execution` and valid plan | Resume from next unfinished task |
| Plan missing | `phase in {planning_complete, execution}` and invalid plan | Recreate plan, then continue |
| Inconsistent lock | `current_feature_id` missing in features | Run recovery workflow before next delegation |

## Standard Resume Prompt

```markdown
## Resume Detected

- Feature: <id> - <name>
- Phase: <phase>
- Plan: <valid|invalid>

Recommended next action:
1. <primary action>
2. <fallback action>
```

## Plan Recreation Trigger

Recreate plan when any is true:

- `validate-plan` returns non-zero
- `workflow_state.plan_path` missing
- required `Tasks` section missing
- strict sections (`Acceptance Mapping`, `Risks`) missing **and** plan does not match Superpowers header (`**Goal:**` + `**Architecture:**`)

## Safe Fallback

If specialized route fails (simple/complex delegate failure):

1. Keep active feature lock.
2. Switch to standard coordinator path.
3. Re-run planning + subagent execution.
4. Record fallback in workflow `next_action`.
