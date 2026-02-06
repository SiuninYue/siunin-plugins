# Git Commit Skill - Usage Guide

This guide demonstrates how to use the git-commit skill both directly and through integration with other skills.

## Direct Usage

Users can invoke this skill directly to create conventional git commits.

### Example 1: Commit a Completed Feature

**User Request:**
```
"Create a commit for the user authentication feature"
```

**Skill Invocation:**
```
Skill: progress-tracker:git-commit
Args: "feat: complete user authentication"
```

**What Happens:**
1. Skill runs `git status` to check for changes
2. Analyzes staged and unstaged changes
3. Stages relevant files (avoiding .env, credentials)
4. Generates commit message following conventional commits format
5. Creates commit with `Co-Authored-By: Claude <noreply@anthropic.com>`
6. Returns commit hash

**Return Value:**
```
Commit created: abc123def456...
```

### Example 2: Commit a Bug Fix

**User Request:**
```
"Commit the session timeout fix"
```

**Skill Invocation:**
```
Skill: progress-tracker:git-commit
Args: "fix: session timeout issue"
```

**Return Value:**
```
Commit created: def456ghi789...
```

### Example 3: Commit with Bug ID

**User Request:**
```
"Commit fix for BUG-001"
```

**Skill Invocation:**
```
Skill: progress-tracker:git-commit
Args: "fix(BUG-001): rate calculation overflow"
```

**Return Value:**
```
Commit created: 789ghi012jkl...
```

## Integration Usage

Other skills invoke this skill to ensure consistent commit behavior across the plugin.

### Feature-Complete Integration

When a feature passes all tests, the `feature-complete` skill invokes git-commit:

```
Skill: progress-tracker:git-commit
Args: "feat: complete <feature_name>"
```

**Workflow:**
1. feature-complete runs acceptance tests
2. If tests pass, invokes git-commit
3. git-commit returns commit hash
4. feature-complete updates progress.json with commit hash
5. feature-complete marks feature as completed

**Code Integration:**
```markdown
### Step 6: Create Git Commit

<CRITICAL>
Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:git-commit"
  - args: "feat: complete <feature_name>"

WAIT for the skill to complete and return the commit hash.
</CRITICAL>

If the skill returns a commit hash:
→ Update progress.json with commit hash
→ Mark feature as completed

If the skill returns null:
→ Inform user of the issue
→ Do not mark feature as completed
```

### Bug-Fix Integration

After TDD completes, the `bug-fix` skill invokes git-commit:

```
Skill: progress-tracker:git-commit
Args: "fix(BUG-XXX): <bug_description>"
```

**Workflow:**
1. bug-fix runs TDD workflow (RED-GREEN-REFACTOR)
2. bug-fix runs code review
3. bug-fix updates bug status to "fixed"
4. bug-fix invokes git-commit
5. git-commit returns commit hash
6. bug-fix updates bug with commit hash

**Code Integration:**
```markdown
### Step 7: Create Bug Fix Commit

<CRITICAL>
Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:git-commit"
  - args: "fix(BUG-XXX): <bug_description>"

WAIT for the skill to complete and return the commit hash.
</CRITICAL>

After receiving commit hash:
→ python3 progress_manager.py update-bug --bug-id "BUG-XXX" --commit-hash <commit_hash>
```

## Return Values

The skill always returns a result to indicate success or failure.

### Success

**Format:**
```
Commit created: <commit_hash>
```

**Example:**
```
Commit created: abc123def4567890123456789012345678901234
```

**Action:** Caller can proceed with post-commit steps.

### No Changes

**Format:**
```
No changes detected. Nothing to commit.
```

**Example:**
```
No changes detected. Nothing to commit.
```

**Action:** Caller should inform the user that no changes were found. Return value is `null`.

### Error

**Format:**
```
Commit failed: <error_message>
```

**Examples:**
```
Commit failed: git status shows uncommitted changes
Commit failed: pre-commit hook failed
Commit failed: unable to stage files
```

**Action:** Caller should inform the user of the error. Return value is `null`.

## Error Handling

### No Changes Detected

When `git status` shows no changes:

```python
# Skill behavior
if no_changes_detected:
    return "No changes detected. Nothing to commit."

# Caller behavior
if result == "No changes detected. Nothing to commit.":
    inform_user("No changes to commit. Make some changes first.")
    return null
```

### Pre-commit Hook Failure

When a pre-commit hook fails:

```python
# Skill behavior
if commit_fails:
    return f"Commit failed: {error_message}"

# Caller behavior
if result.startswith("Commit failed:"):
    error_message = result.replace("Commit failed: ", "")
    inform_user(f"Commit failed: {error_message}")
    suggest_fix(error_message)
    return null
```

### File Staging Issues

When unable to stage files:

```python
# Skill behavior
if stage_fails:
    return f"Commit failed: unable to stage files"

# Caller behavior
if result.startswith("Commit failed:"):
    inform_user("Unable to stage files for commit.")
    suggest_manual_staging()
    return null
```

## Best Practices

### For Users

1. **Ensure changes are ready**: Review changes before invoking the skill
2. **Provide clear commit type**: Use `feat:`, `fix:`, `docs:`, etc.
3. **Include bug ID when applicable**: Use `fix(BUG-XXX):` format
4. **Let the skill handle staging**: The skill will stage relevant files

### For Skill Integrators

1. **Always wait for result**: Use `<CRITICAL>` blocks to ensure waiting
2. **Check return value**: Verify commit was created before proceeding
3. **Handle null returns**: Inform user when commit fails
4. **Store commit hash**: Save the returned hash in progress tracking

### Commit Message Format

Follow conventional commits specification:

```
<type>[optional scope]: <description>

[optional body]

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Types:**
- `feat:` - New feature
- `fix:` - Bug fix
- `fix(BUG-XXX):` - Bug fix with ID
- `docs:` - Documentation changes
- `test:` - Test changes
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

## Testing

### Test Success Scenario

```bash
# Make changes
echo "test" > test.txt

# Invoke skill
Skill: progress-tracker:git-commit
Args: "test: add test file"

# Expected result
Commit created: <hash>

# Verify
git log --oneline -1
# Output: test: add test file
```

### Test No Changes Scenario

```bash
# No changes made

# Invoke skill
Skill: progress-tracker:git-commit
Args: "test: should fail"

# Expected result
No changes detected. Nothing to commit.

# Verify
git status
# Output: nothing to commit
```

### Test Error Scenario

```bash
# Create pre-commit hook that fails
echo "exit 1" > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Make changes
echo "test" > test.txt

# Invoke skill
Skill: progress-tracker:git-commit
Args: "test: should fail hook"

# Expected result
Commit failed: pre-commit hook failed

# Cleanup
rm .git/hooks/pre-commit
```

## See Also

- **`SKILL.md`** - Main skill documentation
- **`references/conventional-commits.md`** - Conventional commits specification
- **`examples/integration.md`** - Integration examples for feature-complete and bug-fix
