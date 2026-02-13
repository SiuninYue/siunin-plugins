# Session Examples (Feature Complete)

## Example A: Successful Completion

```markdown
## Completing Feature 3: Registration API

Workflow phase: execution_complete
Plan validation: PASS
Acceptance tests: PASS (4/4)

Progress updates:
- complete <feature_id> --commit <hash>: PASS
- complete-feature-ai-metrics: PASS
- clear-workflow-state: PASS

Next: run `/prog next`
```

## Example B: Blocked Completion (Workflow Not Ready)

```markdown
## Cannot Complete Feature Yet

Workflow phase: execution
Required phase: execution_complete

Next:
1. Finish remaining implementation tasks.
2. Re-run `/prog done`.
```

## Example C: Acceptance Failure

```markdown
## Verification Failed

Failed step:
- POST /api/register returns 500

Action:
1. Run `/prog-fix "Registration endpoint returns 500"`.
2. Fix and rerun acceptance.
3. Re-run `/prog done`.
```
