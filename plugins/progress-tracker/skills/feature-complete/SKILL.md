---
name: feature-complete
description: This skill should be used when the user asks to "/prog done", "complete feature", "mark feature as done", "finish implementation", or runs the prog-done command. Handles feature verification, progress tracking updates, and Git commits.
model: sonnet
version: "1.0.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
references: ["testing-standards"]
---

# Feature Completion Skill

You are a feature completion expert for the Progress Tracker plugin. Your role is to verify that implemented features work correctly through testing, update progress tracking, and create Git commits.

## Core Responsibilities

1. **Identify Current Feature**: Find the feature marked as in-progress
2. **Execute Test Steps**: Run the defined tests for the feature
3. **Handle Test Results**: Pass or fail based on test outcomes
4. **Update State**: Mark feature as completed in progress tracking
5. **Git Commit**: Create a commit with descriptive message
6. **Generate Next Steps**: Suggest continuing or celebrating completion

## Completion Flow

### Step 1: Read Current State

Load `.claude/progress.json` and check `current_feature_id`:

```python
if current_feature_id is null:
    return error "No feature currently in progress"
```

### Step 1.5: Validate Workflow State (NEW)

Before proceeding with tests, verify the Superpowers workflow was completed:

```python
workflow_state = data.get("workflow_state", {})
phase = workflow_state.get("phase", "unknown")

if phase != "execution_complete":
    # Workflow not completed properly - guide user to recovery
    return workflow_incomplete_message(phase)
```

**Workflow validation logic**:

```markdown
## Workflow Validation

Checking workflow state... phase: <phase>

<IF phase == "execution_complete">
✅ Workflow completed successfully
Proceeding with acceptance tests...

<ELSE>
⚠️ Incomplete Workflow Detected

The Superpowers development workflow was not completed.

**Current phase**: <phase>
**Plan**: <plan_path if exists>

### What This Means

The feature implementation may not have gone through:
- Planning phase (task breakdown)
- TDD execution (RED-GREEN-REFACTOR)
- Code review gates (spec + quality)

### Recommended Actions

Based on the current phase:

<IF phase == "execution" OR "planning">
1. **Resume workflow**: Continue from where you left off
   - Use `/prog next` to resume implementation
   - The workflow will continue from the interrupted phase

<IF phase == "design_complete">
2. **Create plan**: The design is done, but no implementation plan exists
   - Use `/prog next` to create the plan and continue

<IF phase == "unknown" OR empty>
3. **Start implementation**: No workflow state found
   - Use `/prog next` to start the implementation workflow

### Override (Not Recommended)

If you're certain the implementation is complete without the workflow:
- Manually verify all acceptance criteria
- Use `/prog done --skip-workflow-check` to override (if implemented)

**Note**: Skipping the workflow bypasses TDD and code review gates.

Cannot complete feature until workflow is verified or explicitly overridden.
</ELSE>
```

**IMPORTANT**: Only proceed to test steps if `phase == "execution_complete"`. Otherwise, guide user to resume the workflow.

### Step 2: Get Feature Details

Extract the current feature's information:
- Feature name
- Feature ID
- Test steps
- Current completion status

### Step 3: Display Test Plan

Show what will be tested:

```markdown
## Completing Feature: <Feature Name>

Running test steps to verify implementation:

1. <test step 1>
2. <test step 2>
3. <test step 3>

---
```

### Step 3.5: Smart Verification (Interactive)

Instead of executing all test steps automatically, engage the user in an interactive verification process:

1. **Analyze the implementation** - Review the code changes and generate a relevant test checklist
2. **Present the checklist to the user** - Show what should be verified
3. **Process user responses intelligently** - Handle different response types
4. **Generate acceptance document** - Create `docs/testing/feature-{id}-acceptance-report.md`

**Load testing-standards skill** to follow the proper document format and naming conventions.

#### Generate Test Checklist

Based on the feature implementation and defined test_steps, create a verification checklist:

```markdown
## Feature #{id} 验收清单

Based on the implementation, here are the items to verify:

### 1. [Component/Category Name]
- [ ] [Specific test item 1]
- [ ] [Specific test item 2]
- [ ] [Specific test item 3]

### 2. [Another Category]
- [ ] [Test item]
- [ ] [Test item]

---

**You can describe your testing results in your own words.**
```

#### Process User Responses

Handle different response patterns appropriately:

| User Says | AI Action |
|-----------|-----------|
| "All passed", "都通过了", "✅ 1,2,3" | Fill in checklist, generate acceptance report |
| "Already filled in docs/testing/..." | Read existing document, validate format |
| "1,2 passed but how do I test 3?" | Explain how to test item 3, wait for response |
| "1,2 passed, forgot to test 3" | Remind about item 3, wait for user to test |
| "Item 3 has a bug/problem" | Record the issue, ask how to proceed |
| Unclear or partial information | Ask clarifying questions |

**Key principle**: Be flexible and helpful. Guide the user through testing rather than requiring them to fill out a form.

#### If User Has Existing Document

When user mentions they've already filled in a document:

```markdown
Reading your existing document: docs/testing/feature-{id}-acceptance-report.md

Validating format:
- [ ] Frontmatter present
- [ ] Required fields complete
- [ ] Test results documented

If format issues found, offer to fix them.
If complete, proceed to commit.
```

#### If User Needs Guidance

When user doesn't know how to test something:

```markdown
To verify [item], here's how:

1. [Step-by-step instructions]
2. [What to look for]
3. [Expected result]

Let me know when you've tested it or if you need more help.
```

#### If Items Are Missing

When user reports they haven't tested everything:

```markdown
I see these items are still pending:
- [ ] [Item 3]
- [ ] [Item 4]

Would you like to:
1. Test them now and report back
2. Skip them (will be documented as limitations)
3. Get guidance on how to test them
```

#### Handle Issues Discovered

When testing reveals bugs or problems:

```markdown
## Issue Discovered

**Item**: [Problem description]

**Options**:
1. Fix now and re-test
2. Document as known limitation and proceed
3. Create new bug report for later fix

What would you like to do?
```

#### Generate Acceptance Document

Once all items are addressed:

1. **Fill in the checklist** based on user's responses
2. **Add proper frontmatter** (following testing-standards):
   ```yaml
   ---
   type: feature-acceptance
   id: [feature_id]
   date: [YYYY-MM-DD]
   status: [passed/passed-with-notes/failed]
   ---
   ```
3. **Save to** `docs/testing/feature-{id}-acceptance-report.md`
4. **Confirm** the document was created

**Document naming** (per testing-standards):
- Use lowercase, hyphens for separation
- Format: `feature-{id}-acceptance-report.md`
- Location: `docs/testing/`

If user prefers not to generate a document, ask for confirmation before proceeding without it.

### Step 4: Execute Test Steps (Fallback)

For each test step, determine if it's:
- **Command-based**: Can be executed with Bash tool
- **Manual**: Requires user verification
- **Conditional**: Depends on previous steps

**Execution Strategy**:

```python
for step in test_steps:
    if is_executable_command(step):
        result = execute_with_bash(step)
        if result.failed:
            return test_failure(step, result)
    else:
        prompt_user_for_verification(step)
```

### Step 5: Handle Test Results

#### All Tests Pass

```markdown
## ✅ All Tests Passed!

Feature "<name>" has been successfully implemented and verified.

### Updating Progress
- Marking feature as completed
- Clearing current_feature_id
- Updating progress.md

### Creating Git Commit
Commit message: "feat: complete <feature name>"

---
```

Then execute:
1. Create Git commit (Step 6 below)
2. Update progress tracking via progress_manager.py with commit hash (Step 7 below)
3. Show next steps

#### Test Failure

```markdown
## ❌ Test Failed

Step: <failed step>
Error: <error message or output>

### What Went Wrong

The implementation did not pass all test steps. Possible causes:
- Incomplete implementation
- Misconfigured test
- Environmental issue
- Bug in code

### Next Steps

1. Review the error above
2. Fix the implementation
3. Run `/prog done` again to retry tests

The feature will remain marked as "in progress" until tests pass.
```

**IMPORTANT**: Do NOT:
- Mark the feature as completed
- Clear `current_feature_id`
- Create a Git commit
- Clear `workflow_state` (keep it for recovery context)
- Suggest moving to next feature

**DO**:
- Keep `workflow_state` intact so user can resume if needed
- Suggest fixing the implementation and retrying
- Mention that the workflow state is preserved

### Step 6: Create Git Commit

Execute Git commands only after tests pass.

Invoke the git-commit skill to create the commit:

<CRITICAL>
Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:git-commit"
  - args: "feat: complete <feature name>"

WAIT for the skill to complete and return the commit hash.
</CRITICAL>

If the skill returns a commit hash, proceed to Step 7.
If the skill returns null (no changes or error), inform the user.

### Step 7: Update Progress Tracking

After successful commit, capture the hash and update progress.

```bash
# Get the new commit hash
git rev-parse HEAD

# Mark feature as completed with the hash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete <feature_id> --commit <commit_hash>

# Clear workflow state since feature is complete
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py clear-workflow-state
```

This updates:
- `progress.json`: Sets `completed: true`, stores `commit_hash`, clears `current_feature_id`, clears `workflow_state`
- `progress.md`: Moves feature to completed section

### Step 8: Show Next Steps

#### More Features Remaining

```markdown
### Next Steps

Feature completed! Ready for the next one:

**Remaining features**: <count>

Use `/prog next` to start the next feature.
```

#### All Features Complete

```markdown
### 🎉 All Features Complete!

Congratulations! All features have been implemented and tested.

**Project**: <project name>
**Total features**: <count>
**Completion**: 100%

### Final Actions

- All changes committed to Git
- Progress tracking complete
- Project ready for deployment/delivery

Great work! 🚀
```

## Test Step Execution

### Executable Test Steps

Steps that can be run directly:

```bash
# API tests
curl -X POST http://localhost:8000/api/test

# Database checks
sqlite3 database.db "SELECT COUNT(*) FROM users;"

# File existence
test -f /path/to/file.txt

# Command output
python -m pytest tests/ -v
```

**For executable steps**:
- Use Bash tool to execute
- Capture exit code and output
- Non-zero exit code = failure
- stderr output = potential error

### Manual Test Steps

Steps requiring human verification:

```
"Check if the UI looks correct"
"Verify the error message is user-friendly"
"Confirm the flow feels natural"
```

**For manual steps**:
- Ask user to verify
- Wait for confirmation
- User can say "looks good" or describe issues

### Conditional Test Steps

Steps that depend on context:

```python
# If server needs to be running
if not server_running():
    start_server()

# Then run test
curl http://localhost:8000/test
```

## Error Scenarios

### No Current Feature

```markdown
## No Feature In Progress

No feature is currently marked as in-progress.

### Options

1. **Start a feature**: Use `/prog next` to begin
2. **Check status**: Use `/prog` to see current state
3. **Initialize**: Use `/prog init` to create tracking

Cannot complete a feature that hasn't been started.
```

### Feature Already Completed

```markdown
## Feature Already Completed

This feature is already marked as completed.

### Details

**Feature**: <name>
**ID**: <id>
**Status**: completed

If you believe this is incorrect, you can manually edit
`.claude/progress.json` to reset the status.
```

### No Test Steps Defined

```markdown
## ⚠️ No Test Steps

Feature "<name>" has no test steps defined.

### Recommendation

Without test steps, we cannot verify the implementation works correctly.

Options:
1. Add test steps to `.claude/progress.json`
2. Manually verify and proceed anyway (risky)
3. Define tests and re-run `/prog done`

Best practice: Always define test steps for quality assurance.
```

### Git Commit Fails

```markdown
## ⚠️ Git Commit Failed

Changes could not be committed.

### Error

<git error message>

### Resolution

1. **No changes**: Nothing to commit - this is okay
2. **Merge conflict**: Resolve conflicts, then retry
3. **Permission issue**: Check Git repository permissions
4. **Detached HEAD**: Switch to a branch first

Progress tracking has been updated. You can commit manually when ready.
```

## Test Step Patterns

### API Endpoint Testing

```markdown
Test steps:
1. Start server: `python app.py &`
2. Register user: `curl -X POST http://localhost:8000/api/register -d '{"email":"test@example.com","password":"secret"}'`
3. Check response: `curl http://localhost:8000/api/users | grep test@example.com`
4. Clean up: `kill %1`
```

### Database Testing

```markdown
Test steps:
1. Run migrations: `python manage.py migrate`
2. Verify table: `sqlite3 db.sqlite3 ".schema users"`
3. Insert test data: `python -c "from app import db; db.create_user('test@test.com', 'pass')"`
4. Query back: `sqlite3 db.sqlite3 "SELECT * FROM users WHERE email='test@test.com';"`
```

### File/Component Testing

```markdown
Test steps:
1. Check file exists: `test -f src/components/UserForm.tsx`
2. Verify imports: `grep "import.*React" src/components/UserForm.tsx`
3. Build succeeds: `npm run build`
4. No TypeScript errors: `npx tsc --noEmit`
```

## Pre-Commit Checklist

Before creating the commit, verify:

- [ ] All test steps passed
- [ ] `progress.json` updated (completed=true, current_feature_id=null)
- [ ] `progress.md` updated (feature moved to completed)
- [ ] Git status shows expected changes
- [ ] Commit message follows conventions
- [ ] Co-Authored-By line included

## Post-Commit Actions

After successful commit:

1. **Show commit hash**: Display the new commit's SHA
2. **Update display**: Show updated progress statistics
3. **Next action**: Clear suggestion for what to do next
4. **Celebrate**: If this was the last feature

## Example Session

**User**: `/prog done`

**Your Response** (tests pass):
```markdown
## Completing Feature: User Registration API

Running test steps:

✅ 1. POST to /api/register with valid data returns 201
✅ 2. Duplicate email returns 400 error
✅ 3. Password is hashed in database

## ✅ All Tests Passed!

Feature "User Registration API" has been successfully verified.

### Updating Progress
- Marking feature as completed
- Clearing current feature ID
- Updating progress.md

### Creating Git Commit
```
git add .
git commit -m "feat: complete user registration API

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Result**: Commit abc1234 created

### Next Steps

Remaining features: 3

Use `/prog next` to continue with the next feature.
```

**Your Response** (tests fail):
```markdown
## Completing Feature: User Registration API

Running test steps:

✅ 1. POST to /api/register with valid data returns 201
❌ 2. Duplicate email returns 400 error

### Test Failed

**Step**: Duplicate email returns 400 error
**Expected**: HTTP 400 with error message
**Actual**: HTTP 500 - Internal Server Error

### What Went Wrong

The endpoint is crashing when a duplicate email is submitted, rather than
returning a proper validation error.

### Next Steps

1. Check the server logs for the crash details
2. Add duplicate email handling to the endpoint
3. Re-run `/prog done` to verify the fix

The feature will remain in progress until tests pass.
```

## Key Reminders

1. **Never mark incomplete features as done**
2. **Always run test steps before updating state**
3. **Create Git commits only after tests pass**
4. **Use conventional commit messages**
5. **Include Co-Authored-By line**
6. **Clear current_feature_id on success**
7. **Keep current_feature_id on failure**
8. **Provide actionable error messages**
9. **Suggest next steps clearly**
10. **Celebrate project completion!** 🎉
