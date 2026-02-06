---
name: git-commit
description: This skill should be used when the user asks to "create a git commit", "commit changes", "make a commit", or needs to create a conventional commit message based on code changes. Follows commit-commands plugin best practices.
version: "1.0.0"
scope: skill
---

# Git Commit

Create conventional Git commits with auto-generated messages based on staged and unstaged changes.

## Purpose

Create Git commits by analyzing changes, generating appropriate commit messages, and staging files. This skill encapsulates the commit workflow from commit-commands plugin for use within other skills.

## When to Use

Invoke this skill when:
- A feature or bug fix is complete and needs to be committed
- Progress tracking requires a commit hash
- Multiple skills need consistent commit behavior

## Commit Workflow

### Gather Context

First, gather git context to inform the commit:

```bash
# Check current git status
git status

# Review staged and unstaged changes
git diff HEAD

# Check recent commit history for style
git log --oneline -10
```

### Create Commit

Based on the gathered context, create an appropriate commit:

1. **Stage relevant files**: Use `git add <files>` for specific changes. Avoid files with secrets (.env, credentials.json).

2. **Generate commit message** following conventional commits format:
   - `feat:` for new features
   - `fix:` for bug fixes
   - `fix(BUG-XXX):` for bug fixes with ID
   - `refactor:`, `docs:`, `test:`, `chore:` for other changes

3. **Include `Co-Authored-By: Claude <noreply@anthropic.com>`** in the commit message.

4. **Create the commit**:
   ```bash
   git commit -m "<commit message>"
   ```

5. **Return the commit hash**:
   ```bash
   git rev-parse HEAD
   ```

## Return Values

Return the result to the caller:

- **Success**: `Commit created: <commit_hash>`
- **No changes**: `No changes detected. Nothing to commit.`
- **Error**: `Commit failed: <error message>`

## Error Handling

### No Changes to Commit

If `git status` shows no changes:
```
No changes detected. Nothing to commit.
Return: null
```

### Commit Failed

If commit creation fails:
```
Commit failed: <error message>
Return: null
```

## Examples

### Feature Completion
```bash
git add src/auth/
git commit -m "feat: complete user authentication

- Implement login/logout endpoints
- Add JWT token validation

Co-Authored-By: Claude <noreply@anthropic.com>"

git rev-parse HEAD
# Returns: abc123def456...
```

### Bug Fix
```bash
git add src/auth/session.js
git commit -m "fix: session timeout issue

Co-Authored-By: Claude <noreply@anthropic.com>"

git rev-parse HEAD
# Returns: def456ghi789...
```

### Bug Fix with ID
```bash
git add src/api/rates.js
git commit -m "fix(BUG-001): rate calculation overflow

Co-Authored-By: Claude <noreply@anthropic.com>"

git rev-parse HEAD
# Returns: 789ghi012jkl...
```

## Additional Resources

### Reference Files

For detailed conventional commits specification:
- **`references/conventional-commits.md`** - Complete conventional commits reference

### Example Files

Integration examples:
- **`examples/integration.md`** - How to integrate this skill into feature-complete and bug-fix
