---
name: feature-implement
description: This skill should be used when the user runs "/prog next", asks to "implement next feature", "start next feature", "continue implementation", or needs to resume interrupted feature execution. Coordinates deterministic complexity routing across simple (haiku), standard (sonnet), and complex (opus) paths with fallback to the standard path.
model: sonnet
version: "3.0.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
references: ["superpowers:brainstorming", "superpowers:writing-plans", "superpowers:subagent-driven-development", "superpowers:test-driven-development", "./references/complexity-assessment.md"]
---

# Feature Implementation Skill (Superpowers Integration)

You are a feature implementation coordinator for the Progress Tracker plugin. Your role is to bridge progress tracking with **Superpowers workflow skills** to implement features systematically with enforced TDD and quality gates.

## Core Responsibilities

1. **Identify Next Feature**: Find the first uncompleted feature in the list
2. **Update State**: Set the `current_feature_id` in progress tracking
3. **Display Context**: Show feature details and test steps to the user
4. **Orchestrate Superpowers Workflow**: Coordinate brainstorming, planning, and TDD execution
5. **Guide Completion**: Prompt user to use `/prog done` when finished

## Implementation Flow

### Step 1: Read Current State

Load `.claude/progress.json` to find the next feature:

```python
# Find first feature where completed == false
next_feature = first(f for f in features if f.completed == false)
```

**ALSO**: Check for architecture context at `.claude/architecture.md`:

- If exists, read technology stack and design decisions
- Use this context when invoking brainstorming or planning
- Reference architectural constraints in implementation guidance

### Pre-Step: Auto Checkpoint

Before starting any implementation workflow, call:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py auto-checkpoint
```

This creates a lightweight `.claude/checkpoints.json` snapshot only when:
- A feature is currently in progress
- More than 30 minutes passed since the last checkpoint

### Step 2: Update Current Feature

Mark the feature as in-progress:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-current <feature_id>
```

### Step 3: Display Feature Context

Show the user what they're about to implement:

```markdown
╔════════════════════════════════════════════════════════╗
║  🚀 Starting Feature Implementation                    ║
╚════════════════════════════════════════════════════════╝

**Feature**: <Feature Name>
**Feature ID**: <id>
**Progress**: Feature <current>/<total> in project

### Acceptance Test Steps (to be verified with `/prog done`)
✓ <step 1>
✓ <step 2>
✓ <step 3>

---

Assessing complexity and selecting workflow...
```

### Step 4: Complexity Assessment

Before invoking Superpowers skills, assess feature complexity:

| Complexity | Indicators | Workflow Path |
|------------|-----------|---------------|
| **Simple** | Single file change, clear requirements, <3 test steps | Skip brainstorming → writing-plans → TDD |
| **Standard** | Multiple files, 3-5 test steps, clear requirements | Optional brainstorming → writing-plans → subagent-driven |
| **Complex** | >5 files, unclear requirements, architecture decisions needed | Full brainstorming → writing-plans → subagent-driven |

**Assessment criteria**:
- Number of files likely to change
- Number of test steps
- Presence of design decisions in feature description
- Whether feature involves new architecture patterns

### Step 5: Route by Complexity (Deterministic Delegation)

Use the fixed score thresholds from `references/complexity-assessment.md`:
- 0-15: `simple`
- 16-25: `standard`
- 26-40: `complex`

Display a concise model-routing summary:

```markdown
## Complexity & Model Selection

Feature: <feature_name>
Score: <score>/40
Bucket: <simple|standard|complex>
Model: <🟢 haiku|🟡 sonnet|🔴 opus>
Workflow: <direct_tdd|plan_execute|full_design_plan_execute>
```

#### 5A: Simple Path (Delegate to Haiku Skill)

When score <= 15:

<CRITICAL>
Invoke the skill tool:

```text
Skill("progress-tracker:feature-implement-simple", args="<feature_name>: <one_line_description>")
```

Do not execute inline simple flow in this coordinator.
</CRITICAL>

#### 5B: Standard Path (Stay in Coordinator / Sonnet)

When 16 <= score <= 25:

1. Execute planning:
```text
Skill("superpowers:writing-plans", args="<feature_name>: <one_line_description>")
```
2. Update workflow state:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "planning_complete" \
  --plan-path "<returned_plan_path>" \
  --next-action "execution"
```
3. Execute implementation:
```text
Skill("superpowers:subagent-driven-development", args="plan:<returned_plan_path>")
```
4. Mark execution complete and write AI metrics:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "execution_complete" \
  --next-action "verify_and_complete"

python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> \
  --complexity-score <score> \
  --selected-model sonnet \
  --workflow-path plan_execute
```

#### 5C: Complex Path (Delegate to Opus Skill)

When score >= 26:

<CRITICAL>
Invoke the skill tool:

```text
Skill("progress-tracker:feature-implement-complex", args="<feature_name>: <one_line_description>")
```

Do not execute inline complex flow in this coordinator.
</CRITICAL>

#### 5D: Delegation Failure Fallback

If simple/complex delegation fails for any reason:

1. Inform user that delegation failed and standard flow is being used.
2. Continue with Standard Path (`writing-plans` -> `subagent-driven-development`).
3. Write AI metrics with `selected_model = sonnet` and `workflow_path = plan_execute`.

### Step 6: Post-Implementation Guidance

After Superpowers workflow completes, guide the user:

```markdown
╔════════════════════════════════════════════════════════╗
║  ✅ Feature Implementation Complete                    ║
╚════════════════════════════════════════════════════════╝

**Summary**:
  - Plan: docs/plans/<date>-<feature>.md
  - Tasks completed: <N>/<N>
  - Commits created: <N>
  - All tests: PASSING

**Quality Gates Passed**:
  ✓ TDD enforcement (RED-GREEN-REFACTOR per task)
  ✓ Spec compliance review (matches plan requirements)
  ✓ Code quality review (patterns, maintainability)

**What's Next**:

  1️⃣ **Manual Testing** (optional but recommended)
     Test the feature end-to-end to ensure it works as expected

  2️⃣ **Run Acceptance Tests**
     Execute: `/prog done`

     This will:
     - Run the acceptance test steps defined earlier
     - Create a feature-level Git commit
     - Mark the feature as completed
     - Move to the next feature

---

Run `/prog done` when ready to finalize this feature.
```

## Workflow State Tracking

To support session recovery, update `progress.json` with workflow state:

```json
{
  "current_feature_id": 2,
  "workflow_state": {
    "phase": "execution",
    "plan_path": "docs/plans/2026-01-20-feature-name.md",
    "completed_tasks": [1, 2],
    "current_task": 3,
    "total_tasks": 5,
    "next_action": "verify_and_complete"
  }
}
```

**Phase values**:
- `design_complete` - Brainstorming done, ready for planning
- `planning_complete` - Plan created, ready for execution
- `execution` - Currently executing tasks
- `execution_complete` - All tasks done, ready for verification

Update this state immediately after each phase:
1. After design → `set-workflow-state --phase "design_complete"`
2. After planning → `set-workflow-state --phase "planning_complete" --plan-path "<path>"`
3. During execution → `update-workflow-task --task-id <N> --status completed`
4. After execution → `set-workflow-state --phase "execution_complete"`

Use these progress_manager.py commands:
```bash
# Set workflow phase and metadata
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "<phase>" \
  --plan-path "<plan_path>" \
  --next-action "<next_action>"

# Mark individual task as completed
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-workflow-task <task_number> completed
```

## When No Features Remain

Handle completion state:

```markdown
## All Features Complete! 🎉

All features in the progress tracker have been implemented and verified.

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
**Workflow phase**: <phase from workflow_state>

### Options

1. **Continue current feature**: Resume from current task
2. **Complete current feature**: Run `/prog done` when implementation is finished
3. **Abandon and restart**: Run `/prog next --reset` to abandon and start fresh

Use `/prog` to see detailed status.
```

### Mid-Workflow Session Recovery

If session interrupted during Superpowers workflow:

```markdown
╔════════════════════════════════════════════════════════╗
║  📋 Progress Tracker: Unfinished Work Detected        ║
╚════════════════════════════════════════════════════════╝

**Feature**: <feature_name> (ID: <feature_id>)
**Phase**: <phase> (<completed_tasks>/<total_tasks> tasks done)
**Plan**: <plan_path>
**Last updated**: <time_since_last_update>

You were in the middle of implementing this feature when the session ended.

### Recovery Options

1️⃣ **Resume from Task <N>** (Recommended)
   Continue where you left off
   Status: Tasks 1-<N-1> completed, task <N> in progress

2️⃣ **Restart Execution**
   Re-run all tasks from the beginning
   Useful if previous tasks had issues

3️⃣ **Re-create Plan**
   Go back to planning phase
   Useful if requirements changed

4️⃣ **Skip Feature**
   Mark as incomplete and move to next feature
   You can come back later with `/prog next --feature <id>`

Which option? (Enter 1-4)
```

**Auto-recovery for clear cases**:
- If `phase == "execution_complete"` → Auto-prompt for `/prog done`
- If `phase == "execution"` AND 80%+ tasks done → Auto-resume from current task

## Integration with Superpowers

### Why Use Superpowers?

Superpowers provides:
- **Enforced TDD**: Mandatory RED-GREEN-REFACTOR cycle
- **Systematic planning**: Bite-sized tasks with complete context
- **Dual-stage review**: Spec compliance + code quality
- **Subagent isolation**: Fresh context per task prevents drift
- **Proven workflows**: Battle-tested development patterns

### Handoff Pattern

```
progress-tracker (this plugin)
    ↓
    - Maintains feature list
    - Tracks completion state
    - Defines acceptance test steps
    - Assesses complexity
    ↓
superpowers skills
    ↓
    - brainstorming: Design exploration (if complex)
    - writing-plans: Task breakdown
    - subagent-driven-development: TDD execution with review
    - test-driven-development: Direct TDD (if simple)
    ↓
progress-tracker (return)
    ↓
    - Runs feature-level acceptance tests
    - Marks completion
    - Creates feature commit
    - Updates progress.json
```

### Quality Gates Comparison

| Gate | Owner | When | Purpose |
|------|-------|------|---------|
| TDD enforcement | Superpowers | During implementation | Unit-level correctness |
| Spec compliance review | Superpowers | After each task | Matches plan requirements |
| Code quality review | Superpowers | After spec passes | Maintainability, patterns |
| Acceptance test steps | Progress-tracker | Feature completion | Feature-level verification |

**They're complementary**: Superpowers ensures code quality during development; progress-tracker ensures feature acceptance at completion.

## Feature Description Best Practices

When displaying feature context to Superpowers skills, provide:
- Feature name (from progress.json)
- Brief context (1-2 sentences)
- Test criteria (what will be verified in `/prog done`)

Example:
```markdown
Feature: Implement user registration API endpoint

Context: This feature creates a POST /api/register endpoint that accepts
email and password, validates input, hashes the password with bcrypt, and 
stores the user in the PostgreSQL database.

Acceptance criteria (from progress.json test_steps):
1. POST with valid data returns 201 Created
2. Duplicate email returns 400 Bad Request
3. Password is bcrypt-hashed in database
4. User record has created_at timestamp
```

## Testing Strategy

### Before Superpowers Workflow

- Verify `progress.json` is valid JSON
- Confirm feature has test steps defined
- Check that no other feature is currently in progress
- Ensure git working directory is clean (for clean commits)

### During Superpowers Workflow

- Monitor the workflow phases (design → planning → execution)
- Be available to answer brainstorming questions
- Track completed tasks via workflow_state updates

### After Superpowers Workflow (User's Responsibility)

- Manual end-to-end testing of the feature
- Verification against acceptance test steps
- Execution of `/prog done` for formal completion and Git commit

## Communication Style

### When Starting Feature

Be clear and set expectations:
- ✅ "Starting implementation of..."
- ✅ "Assessing complexity..."
- ✅ "This feature is [simple|standard|complex], using [workflow path]"

### When Invoking Superpowers Skills

Explain what's happening:
- ✅ "Using superpowers:brainstorming to explore design alternatives..."
- ✅ "Creating implementation plan with superpowers:writing-plans..."
- ✅ "Executing tasks with superpowers:subagent-driven-development (TDD + dual review)..."

### When Complete

Be directive and clear:
- ✅ "Next: Run `/prog done` to verify acceptance tests and commit"
- ✅ "All Superpowers quality gates passed. Ready for feature-level verification."

## Example Session

**User**: `/prog next`

**Your Response**:
```markdown
## Starting Feature: User Registration API

**Feature ID**: 2
**Position**: 2/5 overall

### Acceptance Test Steps
1. POST to /api/register with valid data returns 201
2. Duplicate email returns 400 error  
3. Password is bcrypt-hashed in database
4. User record has created_at timestamp

---

**Complexity Assessment**: Standard
- Multiple files (routes, service, model)
- Clear requirements
- Standard API pattern

**Workflow**: Planning → Subagent-driven execution

---

**Phase 1: Planning** (superpowers:writing-plans)

Creating implementation plan for User Registration API...

[Invoke superpowers:writing-plans skill internally]

Plan created: docs/plans/2026-01-20-user-registration.md

**Tasks breakdown**:
1. Create user model with validation (3min)
2. Add bcrypt password hashing (2min)
3. Implement POST /api/register route (4min)
4. Add duplicate email check (2min)
5. Integration tests (3min)

---

**Phase 2: Execution** (superpowers:subagent-driven-development)

Dispatching fresh subagent for each task with TDD + dual review...

[Invoke superpowers:subagent-driven-development skill]

Task 1/5: Create user model
- RED: Test model validation fails → ❌
- GREEN: Add User model with email/password fields → ✅
- REFACTOR: Extract validation to separate method → ✅
- Spec review: ✅ Matches plan requirements
- Quality review: ✅ Follows project patterns
- Committed: "feat(model): add User model with validation"

Task 2/5: Add bcrypt hashing
[... similar TDD cycle ...]

[... tasks 3-5 ...]

---

## Implementation Complete ✅

All 5 tasks passed TDD and code review.

**Summary**:
- Plan: docs/plans/2026-01-20-user-registration.md
- Commits: 5 commits created
- Tests: All unit tests passing

**Next Steps**:
1. Test the endpoint manually (curl or Postman)
2. Run `/prog done` to execute acceptance tests and finalize
```

## Key Reminders

1. **Always assess complexity** before choosing workflow path
2. **Update workflow_state** for session recovery support
3. **Show acceptance test steps** so user knows what will be verified in `/prog done`
4. **Clear handoff** to Superpowers skills with full context
5. **Remind about /prog done** after Superpowers workflow completes
6. **Handle edge cases** (no features, already in progress, mid-workflow recovery)
7. **Maintain tracking state** as the single source of truth

## Superpowers Skills Reference

| Skill | When to Use | What It Does |
|-------|-------------|--------------|
| `superpowers:brainstorming` | Complex features needing design | Socratic exploration, alternative approaches, design validation |
| `superpowers:writing-plans` | All non-trivial features | Breaks work into 2-5min TDD tasks with complete context |
| `superpowers:subagent-driven-development` | Standard/complex features | Fresh subagent per task, TDD enforcement, dual review |
| `superpowers:test-driven-development` | Simple features | Direct RED-GREEN-REFACTOR cycle |
| `superpowers:requesting-code-review` | Manual review needed | Pre-review checklist, spec compliance checks |

All Superpowers skills enforce TDD and maintain high quality standards. They're designed to be invoked by coordinator skills like this one.
