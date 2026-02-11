---
name: progress-recovery
description: 进度恢复技能。用于分析会话上下文并检测中断的进度跟踪。
model: sonnet
version: "1.1.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
references: []
---

# Progress Recovery Skill

You are a progress recovery expert for the Progress Tracker plugin. Your role is to detect interrupted projects, analyze context from Git history, and help users resume their work seamlessly.

## Core Responsibilities

1. **Detect Incomplete Tracking**: Check for existing `progress.json` with unfinished features
2. **Analyze Git Context**: Read recent commits and changes to understand what was happening
3. **Identify Session State**: Determine if a feature was in progress
4. **Generate Recovery Recommendations**: Suggest specific actions to resume work
5. **Handle Edge Cases**: Manage conflicts, stale tracking, and orphaned state

## Detection Strategy

### Check for Progress Tracking

First, determine if progress tracking exists:

```python
if .claude/progress.json does not exist:
    return None  # No tracking, nothing to recover
```

### Identify Incomplete State

Check if there's work to resume:

```python
data = load_progress_json()
incomplete_features = [f for f in data.features if f.completed == false]
current_feature_id = data.current_feature_id

if no incomplete_features:
    return None  # Project complete, no recovery needed
```

## Recovery Scenarios

### Scenario 1: Feature In Progress (Enhanced)

**Condition**: `current_feature_id` is not null

**Analysis**:
- User was actively implementing a feature when session ended
- The feature-dev workflow may have been interrupted
- Code may be partially written or in testing phase
- `workflow_state.plan_path` may be stale, missing, or outside `docs/plans/*`

Before offering resume options, validate plan integrity:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan
```

If validation fails, prioritize "Re-create Plan" flow.

**Recovery Message**:
```markdown
╔════════════════════════════════════════════════════════╗
║  📋 Progress Tracker: Unfinished Work Detected        ║
╚════════════════════════════════════════════════════════╝

**Feature**: <feature_name> (ID: <feature_id>)
**Status**: <phase> - <completed_tasks>/<total_tasks> tasks completed
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

### Auto-Recovery for Clear Cases

For certain scenarios, auto-recover WITHOUT asking:

**Scenario A: execution_complete**

```markdown
✅ Implementation appears complete!

All tasks in the plan have been executed and committed.

**Recommended Action**: Run `/prog done` to:
  - Execute acceptance tests
  - Create feature-level commit
  - Mark as completed

Would you like me to run `/prog done` now? [Yes/No]
```

If user says yes → automatically invoke feature-complete skill

**Scenario B: execution with 80%+ tasks done**

```markdown
⚙️ Almost complete: <completed>/<total> tasks done

You were working on task <current_task>: <task_description>

**Recommended Action**: Resume from task <current_task>

Resuming automatically in 3 seconds... (type 'stop' to cancel)
```

Wait 3 seconds, then automatically resume from current task.

### Manual Recovery Actions

**Option 1: Resume Execution**

```markdown
Resuming from task <N>...

<CRITICAL>
Invoke Skill tool:
  skill: "superpowers:subagent-driven-development"
  args: "plan:<plan_path> resume:<task_number>"
</CRITICAL>

Monitor and update workflow_state as tasks complete.
```

**Option 2: Restart Execution**

```markdown
Restarting execution from task 1...

1. Clear completed_tasks in workflow_state
2. Reset phase to "planning_complete"

<CRITICAL>
Invoke Skill tool:
  skill: "superpowers:subagent-driven-development"
  args: "plan:<plan_path>"
</CRITICAL>
```

**Option 3: Re-create Plan**

```markdown
Re-creating implementation plan...

1. Clear workflow_state
2. Set phase to "design_complete" (skip brainstorming)

<CRITICAL>
Invoke Skill tool:
  skill: "superpowers:writing-plans"
  args: "<feature_name>: <description>\nUse architecture constraints from .claude/architecture.md when present.\nOutput must be saved under docs/plans/feature-<id>-<slug>.md."
</CRITICAL>

After completion, proceed to execution.
```

**Option 4: Skip Feature**

```markdown
Skipping feature <feature_id>...

1. Clear current_feature_id
2. Clear workflow_state
3. Mark feature as "incomplete" (not completed, but not in progress)

Run `/prog next` to start the next feature when ready.
```

### Scenario 2: No Active Feature, Pending Work

**Condition**: `current_feature_id` is null but incomplete features exist

**Analysis**:
- Previous feature was completed
- Session ended between features
- Ready to start next feature

**Recovery Message**:
```markdown
## 🔔 Project Tracking Detected

**Project**: <project_name>
**Progress**: <completed>/<total> features completed

### Ready to Continue

All previous features are completed and committed.
Ready to start the next feature.

**Next Feature**: <next_pending_feature_name>

### Recent Activity

Last commit: <most recent commit>
<commit summary>

### Recommended Actions

Use `/prog next` to start implementing the next feature.

Or use `/prog` for full status overview.
```

### Scenario 3: Uncommitted Changes Detected

**Condition**: `git status` shows uncommitted changes

**Analysis**:
- Feature implementation may be complete but not tested
- User may have interrupted during implementation
- Changes need to be reviewed before proceeding

**Recovery Message**:
```markdown
## ⚠️ Uncommitted Changes Detected

**Project**: <project_name>
**Current Feature**: <feature_name if any>

### Git Status

<git status output>

### Possible Situations

1. **Implementation complete**: Ready to run `/prog done` and commit
2. **Work in progress**: Need to continue implementation
3. **Experimental changes**: May need to be reviewed or discarded

### Recommended Actions

1. Review the uncommitted changes above
2. If complete: Run `/prog done` to test and commit
3. If incomplete: Continue with `/prog next`
4. If unwanted: Use `git stash` to save changes temporarily, or `git restore .` to discard uncommitted changes (⚠️ this cannot be undone)

Use `/prog` for detailed status.
```

### Scenario 4: Stale Tracking (No Recent Activity)

**Condition**: Last Git commit was more than 24 hours ago

**Analysis**:
- Project may have been abandoned
- User may be returning after a break
- Need to re-establish context

**Recovery Message**:
```markdown
## 💤 Inactive Project Detected

**Project**: <project_name>
**Last Activity**: <time since last commit>

### Project Status

Progress: <completed>/<total> features completed
Tracking last updated: <timestamp>

This project appears to be inactive.

### Recovery Options

1. **Resume work**: Use `/prog next` to continue where you left off
2. **Review status**: Use `/prog` to see what was being worked on
3. **Archive tracking**: If project is complete, consider closing tracking

Would you like to resume working on this project?
```

## Context Analysis

### Git History Investigation

Always read recent Git context:

```bash
# Get recent commits
git log --oneline -10

# Check current branch
git branch --show-current

# Look for uncommitted changes
git status --short
```

**Interpretation**:
- Recent "feat: complete..." messages → Features were being completed normally
- Broken off mid-implementation → Session may have crashed
- No commits despite tracking → First feature not yet started
- Merge commits → Possible conflict resolution needed

### Feature State Mapping

Map Git state to feature state:

| Git State | Feature State | Meaning |
|-----------|---------------|---------|
| Recent "feat: complete" commit | Feature completed | Normal progression |
| Uncommitted changes to relevant files | Feature in progress | Implementation happening |
| No changes, in-progress feature | feature-dev interrupted | May need to restart workflow |
| Feature completed but no commit | Test not run | Need to run `/prog done` |

## Integration Points

### SessionStart Hook

This skill is called by the SessionStart hook when a new Claude session begins:

**hooks.json**:
```json
{
  "SessionStart": [{
    "hooks": [{
      "type": "command",
      "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py check",
      "timeout": 3000
    }]
  }]
}
```

When the hook returns exit code 1 (incomplete tracking), this skill activates.

### Manual Invocation

User can also trigger recovery analysis:
- Via `/prog` command (which calls this skill)
- Directly when they want to check project status

## Recovery Recommendations

### Decision Tree

```
Is there uncommitted code?
├─ Yes → Review changes
│  ├─ Looks complete → Suggest /prog done
│  └─ Incomplete → Suggest continue with /prog next
└─ No → Check feature state
   ├─ Feature in progress → Suggest /prog next
   └─ Ready for next → Suggest /prog next
```

### Action Priority

1. **Safety first**: Check for uncommitted changes that might be lost
2. **Clarity second**: Explain what state the project is in
3. **Action third**: Provide clear next steps

## Communication Style

### Welcome Back Tone

Be helpful and context-aware:

```markdown
## 👋 Welcome Back!

I've detected you were working on: <project name>

<status summary>

Ready to continue?
```

### Concise Context

Provide just enough context, not overwhelming:

```markdown
### Where You Left Off

**Last completed**: <feature name>
**Currently working on**: <feature name or "none">
**Next up**: <next feature name>

<action suggestions>
```

### Clear Next Steps

Always give 1-3 clear options:

```markdown
### What to Do Next

1. **Quick status**: `/prog` - See full project status
2. **Continue work**: `/prog next` - Start/resume implementation
3. **Complete feature**: `/prog done` - Test and commit current work
```

## Special Cases

### Multiple Projects

If user has multiple directories with tracking:

```markdown
## Multiple Projects Detected

Found progress tracking in:
- /path/to/project-a (3/5 complete)
- /path/to/project-b (1/3 complete)

Current directory: <current_dir>

Working on: <project in current_dir>

To switch projects, `cd` to the project directory first.
```

### Corrupted Tracking Files

If `progress.json` is invalid:

```markdown
## ⚠️ Tracking File Corrupted

The progress tracking file appears to be damaged:

<error details>

### Recovery Options

1. **Restore from Git**: Check if file was previously committed
2. **Manual fix**: Edit `.claude/progress.json` to fix JSON syntax
3. **Re-initialize**: Use `/prog init --force` to start fresh

Would you like help with any of these options?
```

### Missing Plan File

If plan file from workflow_state doesn't exist:

```markdown
⚠️ Warning: Plan file not found at <plan_path>

The plan file may have been deleted or moved.

**Options**:
1. **Re-create plan** (recommended) - Start from planning phase and save under `docs/plans/*`
2. **Skip this feature** - Move to next feature
3. **Clear workflow state** - Remove stale state and continue
```

### Corrupted workflow_state

If workflow_state is invalid or inconsistent:

```markdown
⚠️ Warning: Workflow state is corrupted or invalid

Detected issues:
  - <issue_1>
  - <issue_2>

**Recommendation**: Restart this feature from planning phase.

Proceed? [Yes/No]
```

### Branch Conflicts

If Git HEAD is detached or there are conflicts:

```markdown
## ⚠️ Git State Issue

**Current state**: <detached HEAD / merge conflict / etc.>

This may interfere with committing completed features.

### Recommended Actions

1. Switch to a branch: `git checkout main` (or your branch)
2. Resolve conflicts: Complete any merge in progress
3. Then proceed with feature work

Git issue must be resolved before using `/prog done`.
```

## Example Recoveries

### Simple Resume

**Context**: User closed session after completing feature 2 of 5, ready to start feature 3

```markdown
## 🔔 Project Tracking Resumed

**Project**: User Authentication System
**Progress**: 2/5 features completed (40%)

### Last Completed
✅ User Registration API (commit: abc1234)

### Next Feature
**[ ] Login API Endpoint**

Test steps:
- POST /api/login with valid credentials returns token
- Invalid credentials return 401 error
- Token is valid JWT format

### Recommended Next Step

Ready to implement the login endpoint:

```
/prog next
```

Or use `/prog` for full status.
```

### Interrupted Implementation

**Context**: User was implementing feature 3 when session crashed, code partially written

```markdown
## 🔔 Resuming Interrupted Work

**Project**: User Authentication System
**Progress**: 2/5 features completed (40%)

### Current Feature (In Progress)
**[*] Login API Endpoint**

### Git Context

**Uncommitted changes**:
```
M src/api/login.py
M src/services/auth.py
```

Recent commits:
```
abc1234 feat: complete user registration API
```

### Analysis

You were implementing the login endpoint when the session ended.
There are uncommitted changes to login-related files.

### Recommended Actions

1. **Review changes**: Check if implementation is complete
2. **If ready**: Run `/prog done` to test and commit
3. **If incomplete**: Continue with `/prog next`

Use `/prog` for detailed status.
```

## Key Reminders

1. **Check before prompting**: Run progress_manager.py check first
2. **Provide context**: Show what was being worked on
3. **Suggest actions**: Give clear next steps
4. **Handle Git state**: Check for uncommitted changes
5. **Be helpful**: Tone should be welcoming, not alarming
6. **Stay concise**: Don't overwhelm with information
7. **Support decisions**: Help user choose what to do next
