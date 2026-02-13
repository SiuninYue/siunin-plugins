---
name: feature-implement
description: This skill should be used when the user runs "/prog next", asks to "implement next feature", "start next feature", "continue implementation", or needs to resume interrupted feature execution. Coordinates deterministic complexity routing across simple (haiku), standard (sonnet), and complex (opus) paths with fallback to the standard path.
model: sonnet
version: "3.2.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
references:
  - "superpowers:brainstorming"
  - "superpowers:writing-plans"
  - "superpowers:subagent-driven-development"
  - "superpowers:test-driven-development"
  - "./references/complexity-assessment.md"
  - "./references/superpowers-integration.md"
  - "./references/session-playbook.md"
---

# Feature Implementation Skill

Coordinate `/prog next` execution by selecting the next feature, routing to the correct implementation path, and keeping workflow state resumable.

## Core Responsibilities

1. Select the next actionable feature from `.claude/progress.json`.
2. Set and persist workflow state before delegating implementation.
3. Route work by deterministic complexity rules.
4. Ensure all commands use `${CLAUDE_PLUGIN_ROOT}` absolute plugin path style.
5. Hand off cleanly to `/prog done` after implementation.

## Use This Skill For

- `/prog next` command execution.
- Recovery-driven continuation after interrupted feature work.
- Any request to start or continue the next pending feature.

## Required Read Order

1. Read `.claude/progress.json` and identify:
   - `current_feature_id`
   - next incomplete feature
   - `workflow_state` (if present)
2. If `.claude/architecture.md` exists, read constraints and apply them.
3. Before any delegation, create lightweight checkpoint:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py auto-checkpoint
```

## Main Flow

### Step 1: Validate Current State

- If no progress file exists: instruct user to run `/prog init <goal>`.
- If all features are complete: show completion message and stop.
- If `current_feature_id` is already set and not complete:
  - treat as resume path
  - point user to `/prog` or `progress-tracker:progress-recovery`
  - do not overwrite active feature without explicit user confirmation.

### Step 2: Select and Lock Feature

- Pick first feature where `completed == false`.
- Persist as active feature:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-current <feature_id>
```

- Display:
  - feature ID and name
  - acceptance test steps
  - architecture constraints (if any)

### Step 3: Score Complexity

Use `references/complexity-assessment.md` to calculate:

- `complexity_score`
- `complexity_bucket`
- `selected_model`
- `workflow_path`

Persist AI metrics immediately:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> \
  --complexity-score <score> \
  --selected-model <haiku|sonnet|opus> \
  --workflow-path <direct_tdd|plan_execute|full_design_plan_execute>
```

### Step 4: Route by Bucket

#### 4A) Simple (`0-15`)

- Delegate to `progress-tracker:feature-implement-simple`.
- Keep flow RED -> GREEN -> REFACTOR.
- Update `workflow_state.phase` to execution before delegation.

#### 4B) Standard (`16-25`)

- Remain in this coordinator.
- Default path:
  1. Optional `superpowers:brainstorming` when requirements are ambiguous.
  2. `superpowers:writing-plans` to produce executable task plan.
  3. `superpowers:subagent-driven-development` to execute plan with TDD.
- Update workflow state transitions:
  - `planning_complete` once plan is accepted
  - `execution` while tasks run
  - `execution_complete` when implementation is finished

#### 4C) Complex (`26-40`)

- Delegate to `progress-tracker:feature-implement-complex`.
- Expect architecture-heavy path with explicit brainstorming + planning + execution gates.

#### 4D) Fallback Rule

If delegation fails for simple/complex path, fallback to standard coordinator path and continue with sonnet workflow.

### Step 5: Persist Workflow State

Use these commands when phase changes:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase <design_complete|planning_complete|execution|execution_complete> \
  --plan-path <docs/plans/...> \
  --next-action "<human-readable next action>"
```

For task completion checkpoints during execution:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-workflow-task <task_id> completed
```

### Step 6: Completion Handoff

When implementation is done:

- summarize what was implemented
- confirm expected acceptance steps
- instruct user to run `/prog done` for verification + completion

Do not mark the feature complete in this skill.

## Recovery Rules

When an interrupted workflow is detected:

- Validate plan integrity before resuming:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan
```

- If plan is invalid/missing, regenerate plan before continuing execution.
- If git working tree is inconsistent, ask user to resolve before proceeding.

For detailed resume playbooks and message templates, read `references/session-playbook.md`.

## Error Handling

### No Progress Tracking

Return concise guidance:

- "No progress tracking found. Run `/prog init <goal>` first."

### No Pending Feature

Return completion summary and suggest:

- `/prog` to review status
- new `/prog init` if starting another project

### Invalid Feature Lock

If `current_feature_id` points to missing feature, clear invalid state via recovery workflow, then recalculate next incomplete feature.

## Required Output Shape

When this skill starts a feature, always include:

1. Active feature (`id + name`)
2. Complexity result (`score + bucket + selected_model`)
3. Workflow path chosen
4. Immediate next command (`/prog done` when implementation completes)

## Additional Resources

- `references/complexity-assessment.md`:
  - scoring rubric and forced override rules.
- `references/superpowers-integration.md`:
  - integration design and layered quality model.
- `references/session-playbook.md`:
  - detailed resume flows, interruption handling, and recovery messaging.
