# Special Situations

### Uncommitted Changes

When `git status` shows uncommitted changes:

```markdown
### ⚠️ Uncommitted Changes Detected

You have uncommitted changes. Consider:
- Committing current work with `/prog done` (if feature is complete)
- Stashing changes if switching context
- Reviewing changes before continuing
```

### Stale Tracking (No recent Git activity)

If last commit was more than a day ago:

```markdown
### 💤 Inactive Project

Last Git activity was <time> ago.

Resume by:
- Using `/prog` to review current state
- Running `/prog next` to continue implementation
```

### Feature Without Test Steps

If a feature has empty or missing `test_steps`:

```markdown
### ⚠️ Feature Missing Test Steps

Feature "<name>" lacks clear test steps.

Consider updating test steps before marking complete.
```
