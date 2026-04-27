# Status Display Examples

### Active Project Example

```markdown
## Project Progress: User Authentication System

**Status**: 2/5 completed (40%)
**Created**: 2024-01-18T10:00:00Z

### In Progress
- [*] Registration API Endpoint
  Test steps:
  - POST /api/register with valid data
  - Verify user record created in database
  - Test validation with invalid email

### Pending (3 remaining)
- [ ] Login API Endpoint
- [ ] JWT Token Generation
- [ ] Password Reset Flow

### Recent Git Activity
```
abc1234 feat: complete user database model
def5678 chore: initialize progress tracking
```

### Next Steps

Current feature is in progress. When ready:
1. Verify the implementation passes test steps
2. Run `/prog done` to test and commit

---
**Paste into a new session to continue:**

/progress-tracker:prog-next

Feature: F3 "Registration API Endpoint" | Phase: execution
Plan: docs/plans/2024-01-18-registration-api.md | Tasks: 2/5 done
Next: task-3 — Add input validation
Branch: feature-registration-api | Worktree: .claude/worktrees/registration-api
ProjectRoot: /Users/siunin/Projects/auth-system
→ Context pre-loaded. Resume from task 3.
---
```

### Empty State Example

```markdown
## No Active Progress Tracking

No project tracking found in the current directory.

Get started:
```
/prog init Build a user authentication system
```

This will:
- Analyze your goal
- Create a feature breakdown
- Initialize progress tracking
```
