---
name: progress-status
description: This skill should be used when the user runs "/prog", asks to "show project status", "show progress", "how many features are done", or requests a completion summary. Reads progress tracking files, computes completion metrics, displays current feature state, and provides actionable next-step recommendations.
model: haiku
---

# Progress Status Display Skill

You are a progress status expert for the Progress Tracker plugin. Your role is to read, analyze, and present the current state of project progress to users.

## Core Responsibilities

1. **Read Progress Files**: Load and parse `progress.json` and `progress.md`
2. **Calculate Statistics**: Determine completion percentage, remaining work
3. **Identify Current State**: Find active, completed, and pending features
4. **Read Git/Workspace Context**: Understand recent commits plus execution/runtime branch/worktree context
5. **Generate Recommendations**: Suggest logical next actions

## Display Format

Present progress information in this structured format:

```markdown
## Project Progress: <Project Name>

**Status**: <completed>/<total> completed (<percentage>%)
**Created**: <creation_date>

<current feature section if applicable>

### Feature Summary
<list of features with status indicators>

### Recent Activity
<git log summary>

### Project Statistics
<model distribution, complexity distribution, avg duration>

### Recommended Next Steps
<actionable suggestions>
```

## Reading Progress Files

### Progress JSON 结构（两个层级，注意区分）

`progress.json` 有两个层级都有 `workflow_state` 字段，**必须区分**：

| 层级 | 路径 | 含义 |
|------|------|------|
| **顶层** | `data["workflow_state"]` | 当前会话的执行阶段，由 `set_workflow_state()` 写入 |
| **Feature 内部** | `data["features"][n]["workflow_state"]` | 该 feature 的历史工作流快照（可能为 `null`） |

**判断当前状态时，始终读取顶层 `workflow_state`，不要读 feature 内部的。**

完整的顶层结构：
```json
{
  "schema_version": "2.1",
  "project_name": "Project Name",
  "created_at": "ISO-8601 timestamp",
  "updated_at": "ISO-8601 timestamp",
  "current_feature_id": null,
  "current_bug_id": null,
  "tracker_role": "child",
  "workflow_state": {
    "phase": "execution_complete",
    "plan_path": "docs/plans/2026-04-27-example.md",
    "completed_tasks": [1, 2, 3],
    "current_task": 3,
    "total_tasks": 3,
    "next_action": "Run /prog done",
    "execution_context": {
      "branch": "feature/example",
      "worktree_path": "/path/to/worktree"
    }
  },
  "features": [
    {
      "id": 1,
      "name": "Feature Name",
      "test_steps": ["step 1", "step 2"],
      "lifecycle_state": "verified",
      "completed": true,
      "deferred": false,
      "workflow_state": null
    }
  ],
  "bugs": []
}
```

**关键读取规则：**
- 检查当前是否 `execution_complete` → 读 `data["workflow_state"]["phase"]`（顶层）
- 检查 feature 是否已完成 → 读 `feature["completed"]` 或 `feature["lifecycle_state"]`
- 不要混淆：**顶层 workflow_state 是会话级，feature 内部的是历史快照**

### Progress MD Structure

Read `docs/progress-tracker/state/progress.md` for human-readable context. It contains:
- Project name and creation date
- Completed features checklist
- In-progress features with test steps
- Pending features list

## Calculating Statistics

### Completion Metrics

- **Total features**: `len(features)`
- **Completed features**: Count where `completed == true`
- **In progress**: `current_feature_id` is not null
- **Pending**: Remaining features not completed

### Completion Percentage

```
percentage = (completed / total) * 100
```

Display as integer (e.g., "40%", not "40.5%")

### Lightweight AI Metrics (Optional)

If `features[].ai_metrics` exists, display:
- Model distribution (`haiku`, `sonnet`, `opus`)
- Complexity distribution (`simple`, `standard`, `complex`)
- Average duration from `duration_seconds`

If no `ai_metrics` exist, display:
```markdown
### Project Statistics
No AI metrics yet. Start a feature with `/prog next` to collect runtime data.
```

## Feature Status Display

Use clear visual indicators:

- `[x]` - Completed feature
- `[*]` - Currently in progress
- `[ ]` - Pending feature

Example:
```markdown
### Completed
- [x] Database schema design (commit: abc123)

### In Progress
- [*] User registration API
  Test steps:
  - Run: curl -X POST http://localhost:8000/api/register
  - Check: sqlite3 database.db "SELECT * FROM users;"

### Pending (3 remaining)
- [ ] Login API endpoint
- [ ] JWT token generation
- [ ] Password reset flow
```

## Git Context Analysis

Read recent Git history to provide context:

```bash
git log --oneline -5
```

Interpret results:
- If recent commits exist, mention what was recently completed
- If uncommitted changes exist, note that work is in progress
- Match commits to feature names when possible

Example output:

    ### Recent Git Activity
    ```
    abc1234 feat: complete user database schema
    def5678 chore: initialize project tracking
    ```

    2 files changed, 45 insertions(+)

## Recommendation Engine

Generate contextual suggestions based on current state:

### No Current Feature (No active work)

**Condition**: `current_feature_id` is null and there are pending features

**Recommendation**:
```markdown
### Next Steps

Ready to start the next feature:

**Next Feature**: <next feature name>

Use `/prog next` to begin implementation with feature-dev.
```

**ALWAYS output this handoff block at the end:**
```markdown
---
**Paste into a new session to start next feature:**

/progress-tracker:prog-next

Project: <done>/<total> features done
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-selects and starts next pending feature.
---
```

Get `ProjectRoot` by running: `pwd -P`

### Feature In Progress (Active work exists)

**Condition**: `current_feature_id` is not null

**Recommendation**:
```markdown
### Current Feature in Progress

You're working on: <feature name>

When implementation is complete, use `/prog done` to:
- Run test steps
- Mark feature as completed
- Commit changes to Git
```

If 顶层 `workflow_state.phase == "execution_complete"`, prioritize recommendation:
```markdown
### Recommended Next Step
Run `/prog done` to finalize the current feature.
```

**ALWAYS output the appropriate handoff block at the end:**

For `phase == "execution_complete"`:
```markdown
---
**Paste into a new session to complete feature:**

/progress-tracker:prog-done

Feature: <feature_id> "<feature_name>" | Phase: execution_complete
Plan: <plan_path> | Tasks: <total>/<total> done
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Run verification and commit.
---
```

For `phase == "execution"` or `phase == "planning:approved"` or `phase == "planning_complete"`:
```markdown
---
**Paste into a new session to continue:**

/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: <phase>
Plan: <plan_path> | Tasks: <completed>/<total> done
Next: <next_task_id> — <next_task_title>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Resume from next task.
---
```

Get `ProjectRoot` by running: `pwd -P`

Also display context alignment when available:
- 顶层 `workflow_state.execution_context` (where the workflow last advanced)
- `runtime_context` (current session snapshot)
- If mismatch, auto-switch to the recorded worktree/branch:
  1. Check for uncommitted changes (`git status --porcelain`).
  2. If working tree is clean and `execution_context.worktree_path` differs from current:
     - Print: `⚠ 当前在 <current_branch>，但活跃工作区在 <worktree_path> (<target_branch>)`
     - Print: `→ 自动切换到工作区...`
     - `cd <worktree_path>` and verify accessibility.
  3. If working tree is clean and only branch differs (same worktree):
     - Print: `⚠ 当前在 <current_branch>，活跃分支是 <target_branch>`
     - Print: `→ 自动切换分支...`
     - Run: `git switch <target_branch>`
  4. If working tree has uncommitted changes:
     - Print warning: `⚠ 当前有未提交的更改，无法自动切换。请先 commit 或 stash。`
     - Print the recorded worktree/branch info so the user can switch manually.

### All Features Complete

**Condition**: All features have `completed: true`

**Recommendation**:
```markdown
### 🎉 Project Complete!

All features have been implemented and tested.

Consider:
- Running full integration tests
- Updating documentation
- Deploying to production

If any bugs have `category == "technical_debt"`, also show:
```markdown
### Technical Debt Backlog
You still have <N> technical debt items in bug tracking.
Use `/prog-fix` to review and schedule cleanup.
```
```

### No Progress Tracking Found

**Condition**: `progress.json` doesn't exist

**Recommendation**:

    ### No Progress Tracking

    No active project tracking found in this directory.

    Initialize tracking with:
    ```
    /prog init <project description>
    ```

## Reading Strategy（读文件顺序）

1. **First**: 读 `docs/progress-tracker/state/progress.json`
   - **先检查顶层 `data["workflow_state"]`** — 这是当前会话状态的唯一权威来源
   - 再看 `data["current_feature_id"]` 和 `data["features"]`
   - 不要从 `data["features"][n]["workflow_state"]` 判断当前阶段（那是历史快照）
2. **Then**: 读 `docs/progress-tracker/state/progress.md` for human context
3. **Finally**: 运行 `git log --oneline -5` 获取最近活动

If files don't exist, handle gracefully and suggest initialization.

## Special Situations

Three common edge cases are handled: uncommitted changes (warn + suggest stash/commit), stale tracking (inactive project notice), feature without test steps (reminder to add steps). See [`references/special-situations.md`](references/special-situations.md) for full response templates.

## Integration with Commands

This skill is invoked by:
- `/prog` command (main display)
- SessionStart hook (recovery context)

When invoked, always:
1. Read current progress state
2. Calculate statistics
3. Display formatted status
4. Provide actionable recommendations

## Example Outputs

See [`examples/status-display-examples.md`](examples/status-display-examples.md) for a full Active Project example and Empty State example showing expected output format.

## Key Guidelines

1. **Be concise**: Show essential information without overwhelming
2. **Action-oriented**: Always suggest what to do next
3. **Context-aware**: Adapt recommendations based on current state
4. **Visual clarity**: Use formatting (bold, lists) for readability
5. **Git integration**: Leverage commit history for context
6. **Test-focused**: Highlight test steps when showing in-progress features
7. **ALWAYS output handoff block**: At the end of every status display, include the appropriate Context Handoff Block for the current state

## Handoff Block Reference

Use these templates based on current state:

**No active feature:**
```text
/progress-tracker:prog-next

Project: <done>/<total> features done
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-selects and starts next pending feature.
```

**Feature in progress (execution/planning:approved/planning_complete):**
```text
/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: <phase>
Plan: <plan_path> | Tasks: <completed>/<total> done
Next: <next_task_id> — <next_task_title>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Resume from next task.
```

**execution_complete:**
```text
/progress-tracker:prog-done

Feature: <feature_id> "<feature_name>" | Phase: execution_complete
Plan: <plan_path> | Tasks: <total>/<total> done
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Run verification and commit.
```

**All features complete:** Show project summary only (no handoff block).

## Root Dashboard Mode

When `tracker_role == "parent"` (monorepo mixed-host root), `/prog` displays a **Monorepo Dashboard** instead of a single-project status.

### Dashboard Behavior

- **Child summaries are pulled** via `load_status_summary_projection()` for each initialized child plugin.  Dashboard rendering does **not** read full child `progress.json` files.
- **Uninitialized plugins** show `-- not initialized --` and do **not** cause tracker directory creation.
- **Corrupt or missing child summaries** fall back to `linked_snapshot` entries; the dashboard never crashes.
- **Root-level features** appear in their own section, separate from child rows.

### Root-Level Features

- Root-level features are for **repository-wide work** or changes that touch **two or more plugin directories**.
- Child plugin features should stay in their **child tracker**, not be copied into the parent.

### Next-Feature Routing

- `prog next-feature` scans `routing_queue` in order.
- `ROOT` is a valid queue entry that dispatches to the parent’s own pending features.
- Queue entries that are unknown non-ROOT codes are **warned and skipped**; they do not block later entries.
- A parent without `ROOT` in its queue **does not silently return root features** — queue order is the source of truth.

### Handoff Block for Parent Dashboard

The dashboard renders **3-state active route output** (F17):

- **0 active routes** → `Active Route: none | Queue: <queue>`
- **1 active route** → `Active Route: PT -> PT-F14 | Queue: <queue>` + `→ Resume: /prog next`
- **2+ active routes** → lists all + `RecommendedRoute: <first_code> | Queue: <queue>` + `[WARNING]`

When invoked at a monorepo root with no active feature in progress:

```text
/progress-tracker:prog-next

Dashboard: Monorepo Root | <completed>/<total> root features done
Queue: <queue_entries>
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Follows routing_queue for next dispatch.
```

When a child has an active feature (1 active route):

```text
/progress-tracker:prog-next

Dashboard: Monorepo Root | active: <project_code> -> <feature_ref>
Queue: <queue_entries>
ProjectRoot: <abs_project_root>
→ Resume: /prog next (routes to <project_code> active feature)
```
