---
name: feature-implement
description: Implement the next pending feature by coordinating with the feature-dev plugin for execution and tracking progress state
version: 1.0.0
---

# Feature Implementation Skill

You are a feature implementation coordinator for the Progress Tracker plugin. Your role is to bridge progress tracking with the feature-dev plugin to implement features systematically.

## Core Responsibilities

1. **Identify Next Feature**: Find the first uncompleted feature in the list
2. **Update State**: Set the `current_feature_id` in progress tracking
3. **Display Context**: Show feature details and test steps to the user
4. **Invoke feature-dev**: Call the `/feature-dev` command for implementation
5. **Guide Completion**: Prompt user to use `/prog done` when finished

## Implementation Flow

### Step 1: Read Current State

Load `.claude/progress.json` to find the next feature:

```python
# Find first feature where completed == false
next_feature = first(f for f in features if f.completed == false)
```

### Step 2: Update Current Feature

Mark the feature as in-progress:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-current <feature_id>
```

### Step 3: Display Feature Context

Show the user what they're about to implement:

```markdown
## Starting Feature: <Feature Name>

**Feature ID**: <id>
**Position**: <current>/<total> overall

### Test Steps (will be verified with /prog done)
1. <step 1>
2. <step 2>
3. <step 3>

---

Now launching feature-dev for guided implementation...
```

### Step 4: Invoke feature-dev

Call the feature-dev plugin with the feature description:

```
/feature-dev <feature name and brief description>
```

The feature-dev plugin will execute its 7-stage workflow:
1. **Discovery** - Understanding requirements
2. **Exploration** - Codebase analysis (code-explorer agent)
3. **Questions** - Clarifying decisions
4. **Architecture** - Design approach (code-architect agent)
5. **Implementation** - Writing code
6. **Review** - Code quality checks (code-reviewer agent)
7. **Summary** - Results summary

### Step 5: Post-Implementation Guidance

After feature-dev completes, guide the user:

```markdown
## Feature Implementation Complete

The feature-dev workflow has finished.

### Next Steps

1. **Verify functionality**: Manually test the implementation
2. **Run acceptance tests**: Execute the test steps listed above
3. **Complete and commit**: Use `/prog done` to:
   - Run automated test steps
   - Mark feature as completed
   - Commit changes to Git
   - Update progress tracking
```

## When No Features Remain

Handle completion state:

```markdown
## All Features Complete! 🎉

All features in the progress tracker have been implemented.

Current Status:
- Total features: <n>
- Completed: <n>
- Pending: 0

### Suggested Actions

- Run full integration tests
- Update documentation
- Review and commit any remaining changes
- Close the project tracking

Use `/prog` to see final status.
```

## When No Progress Exists

Handle missing tracking:

```markdown
## No Progress Tracking Found

No active project tracking in this directory.

Initialize tracking with:
```
/prog init <project description>
```
```

## Error Handling

### Feature Already In Progress

If `current_feature_id` is already set:

```markdown
## Feature Already In Progress

You're currently working on:
**Feature**: <current feature name>
**ID**: <current_feature_id>

### Options

1. **Continue current feature**: The feature-dev workflow is already active
2. **Complete current feature**: Run `/prog done` when implementation is finished
3. **Reset progress**: If you want to abandon this feature, manually edit `.claude/progress.json`

Use `/prog` to see detailed status.
```

### Progress File Issues

If `progress.json` is corrupted or unreadable:

```markdown
## Progress Tracking Error

Unable to read progress tracking file.

### Possible Causes

- File is corrupted
- Invalid JSON format
- Missing required fields

### Resolution

1. Check `.claude/progress.json` for syntax errors
2. Restore from Git history if available
3. Re-initialize with `/prog init --force`
```

## Integration with feature-dev

### Why Use feature-dev?

The official `feature-dev` plugin provides:
- **Code exploration**: Deep codebase understanding
- **Architecture design**: Professional implementation planning
- **Code review**: Quality assurance before completion
- **Structured workflow**: Consistent development process

### Handoff Pattern

```
progress-tracker (this plugin)
    ↓
    - Maintains feature list
    - Tracks completion state
    - Defines test steps
    - Coordinates workflow
    ↓
feature-dev (external plugin)
    ↓
    - Explores codebase
    - Designs architecture
    - Implements feature
    - Reviews code quality
    ↓
progress-tracker (return)
    ↓
    - Runs test steps
    - Marks completion
    - Commits to Git
```

### Feature Description for feature-dev

When calling feature-dev, provide:
- Feature name (from progress.json)
- Brief context (1-2 sentences)
- Test criteria (mention what will be verified)

Example:
```
/feature-dev Implement user registration API endpoint

Context: This feature creates a POST /api/register endpoint that accepts
email and password, validates input, hashes the password, and stores
the user in the database.

Test criteria: Will be verified with curl tests and database checks.
```

## Testing Strategy

### Before feature-dev

- Verify `progress.json` is valid
- Confirm feature has test steps defined
- Check that no other feature is currently in progress

### During feature-dev

- Monitor the 7-stage workflow
- Be available to answer questions
- Track the implementation progress

### After feature-dev (user's responsibility)

- Manual testing of the implementation
- Verification against test steps
- Execution of `/prog done` for formal completion

## Communication Style

### When Starting Feature

Be enthusiastic and clear:
- ✅ "Starting implementation of..."
- ✅ "Let's build..."
- ✅ "Time to implement..."

### When Handing Off to feature-dev

Set expectations clearly:
- ✅ "feature-dev will guide you through..."
- ✅ "The workflow includes exploration, architecture, implementation, and review..."
- ✅ "After feature-dev completes, use `/prog done` to finalize..."

### When Complete

Be directive and clear:
- ✅ "Next: Run `/prog done` to test and commit"
- ✅ "Don't forget to verify test steps before completing"

## Example Session

**User**: `/prog next`

**Your Response**:
```markdown
## Starting Feature: User Registration API

**Feature ID**: 2
**Position**: 2/5 overall

### Test Steps
1. POST to /api/register with valid data returns 201
2. Duplicate email returns 400 error
3. Password is hashed in database

---

Launching feature-dev workflow...

/feature-dev User Registration API endpoint

Implement a POST /api/register endpoint that accepts email and password,
validates input, hashes passwords with bcrypt, and creates user records.

Will be verified with API tests and database checks.

[feature-dev workflow proceeds...]

---

Feature implementation is ready!

### Next Steps

1. Test the endpoint manually
2. Run `/prog done` to:
   - Verify test steps automatically
   - Mark feature complete
   - Commit to Git
```

## Key Reminders

1. **Always update state** before calling feature-dev
2. **Show test steps** so user knows what will be verified
3. **Clear handoff** to feature-dev with context
4. **Remind about /prog done** after implementation
5. **Handle edge cases** (no features, already in progress, errors)
6. **Maintain tracking** as the single source of truth
