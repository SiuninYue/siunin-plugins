# Verification Playbook (Feature Complete)

Use this reference for detailed acceptance verification and issue handling during `/prog done`.

## Verification Checklist Template

```markdown
## Feature <id>: <name> Acceptance Checklist

- [ ] Test Step 1: <step>
  - Evidence:
  - Result: PASS/FAIL
- [ ] Test Step 2: <step>
  - Evidence:
  - Result: PASS/FAIL
```

## Pass Criteria

A feature can be completed only when:

1. All required test steps pass.
2. Workflow phase is `execution_complete`.
3. Plan validation passes.
4. A commit hash is available for completion update.

## Fail Criteria

Keep feature open when any condition below is met:

- One or more test steps fail.
- Plan validation fails.
- Commit not available.

## Failure Response Template

```markdown
## Verification Failed

Failed checks:
- <failed step>
- <failed step>

Recommended next action:
1. Fix issue and rerun test step.
2. Use `/prog-fix "<issue>"` if bug triage is needed.
3. Re-run `/prog done` after fixes.
```

## Technical Debt Capture

When user identifies debt during acceptance:

- Record debt as `category=technical_debt`.
- Keep debt entries short and actionable.
- Include impacted feature/module in description.
