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

## Example C: Successful Completion (Project Complete, Existing PR Found)

```markdown
## Completing Feature 5: Final Integration

Workflow phase: execution_complete
Plan validation: PASS
Acceptance tests: PASS (6/6)

Progress updates:
- complete <feature_id> --commit <hash>: PASS
- complete-feature-ai-metrics: PASS
- clear-workflow-state: PASS

PR detection:
- current branch: feat/final-integration
- existing PR: https://github.com/example/repo/pull/42
- duplicate-finish guard: SKIP `finishing-a-development-branch`

Next: continue with existing PR lifecycle (review/merge), no duplicate finish flow.
```

## Example D: Completion With PR Detection Unavailable

```markdown
## Completing Feature 5: Final Integration

Workflow phase: execution_complete
Plan validation: PASS
Acceptance tests: PASS (6/6)

PR detection:
- status: unavailable (`gh` not authenticated)
- safety action: do not auto-run `finishing-a-development-branch`

Next:
1. Authenticate `gh` and re-check PR status, or
2. Choose manual integration path explicitly.
```

## Example E: Acceptance Failure

```markdown
## Verification Failed

Failed step:
- POST /api/register returns 500

Action:
1. Run `/prog-fix "Registration endpoint returns 500"`.
2. Fix and rerun acceptance.
3. Re-run `/prog done`.
```
