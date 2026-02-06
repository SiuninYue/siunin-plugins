# Git Commit Skill Integration Examples

## Example 1: Feature-Complete Integration

In `feature-complete/skill.md`, replace direct git commands with:

```markdown
### Step 6: Create Git Commit

After tests pass, invoke the git-commit skill to create the commit:

<CRITICAL>
Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:git-commit"
  - args: "feat: complete <feature name>"

WAIT for the skill to complete and return the commit hash.
</CRITICAL>

If the skill returns a commit hash, proceed to Step 7.
If the skill returns null (no changes or error), inform the user.
```

## Example 2: Bug-Fix Integration

In `bug-fix/skill.md`, after TDD completes:

```markdown
After TDD completes, update bug status:
→ python3 progress_manager.py update-bug --bug-id "BUG-XXX" --status "fixed"

Next, create a commit for the bug fix:

<CRITICAL>
Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:git-commit"
  - args: "fix(BUG-XXX): <bug description>"

WAIT for the skill to complete and return the commit hash.

After receiving the commit hash, update the bug:
→ python3 progress_manager.py update-bug --bug-id "BUG-XXX" --commit-hash <commit_hash>
</CRITICAL>
```

## Example 3: Direct Invocation

From user prompt or another skill:

```
User: "Create a commit for the user registration feature"

Claude: [Invokes progress-tracker:git-commit skill with "feat: complete user registration"]
```

## Return Values

The git-commit skill returns:

**Success:**
```
Commit created: abc123def456...
```

**No changes:**
```
No changes detected. Nothing to commit.
```

**Error:**
```
Commit failed: <error message>
```
