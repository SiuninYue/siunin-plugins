# Communication Templates (Progress Recovery)

## Template: Resume Available

```markdown
## Resume Available

Project: <project>
Progress: <done>/<total>
Current feature: <id> - <name>
Phase: <phase>
Plan valid: <yes/no>

Recommended next action:
1. <primary>
2. <secondary>
```

## Template: Plan Invalid

```markdown
## Plan Requires Repair

Current plan cannot be used safely.

Reason:
- <validation error>

Next:
1. Recreate plan.
2. Resume execution.
```

## Template: Risky Git State

```markdown
## Uncommitted Changes Detected

Current resume path may conflict with local edits.

Choose one:
1. Commit current changes.
2. Stash current changes.
3. Cancel recovery.
```

## Template: No Recovery Needed

```markdown
No interrupted work detected.
Use `/prog next` to start the next feature.
```
