---
name: progress-recovery
description: This skill should be used when the user runs "/prog", asks to "resume progress", "recover interrupted workflow", "continue unfinished feature", or returns after an interrupted development session.
model: sonnet
version: "1.2.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
references:
  - "./references/scenario-playbook.md"
  - "./references/communication-templates.md"
---

# Progress Recovery Skill

Detect interrupted progress-tracker sessions and provide deterministic resume actions.

## Core Responsibilities

1. Detect whether recoverable work exists.
2. Analyze workflow phase and plan validity.
3. Recommend the safest next action.
4. Keep state consistent before user resumes work.

## Use This Skill For

- Session-start recovery after interruption
- `/prog` requests where progress appears stale or incomplete
- Explicit user requests to resume unfinished work

## Detection Flow

### Step 1: Check Tracking Existence

If `.claude/progress.json` does not exist, recovery is not needed.

### Step 2: Evaluate Completion State

- If all features are complete: return completion summary and stop.
- If incomplete features exist: continue analysis.

### Step 3: Identify Active Context

Read from progress state:

- `current_feature_id`
- `workflow_state.phase`
- `workflow_state.plan_path`
- `workflow_state.completed_tasks`
- `workflow_state.total_tasks`

If there is an active feature, validate plan path:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan
```

### Step 4: Check Working Tree Safety

Use `git status --porcelain` to detect uncommitted changes.

- If dirty tree conflicts with resume path, show safe options before continuing.

## Recovery Decision Rules

### Case A: Active Feature + `execution_complete`

- Recommended action: run `/prog done`.
- Rationale: implementation finished, verification pending.

### Case B: Active Feature + `execution`

- If plan is valid: resume execution from next unfinished task.
- If plan invalid/missing: recreate plan first, then resume.

### Case C: Active Feature + `planning_complete` or `design_complete`

- Resume from planning/execution boundary.
- Confirm user wants to continue same feature before state changes.

### Case D: No Active Feature + Pending Features

- Recommended action: `/prog next`.
- Include latest completed feature for context.

### Case E: Corrupted or Inconsistent State

- Report inconsistency clearly.
- Recommend minimal repair path (rebuild plan or clear invalid workflow metadata).
- Do not silently mutate state.

Detailed branching logic is in `references/scenario-playbook.md`.

## Required Commands

### Validate Plan Integrity

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan
```

### Re-check Recovery Signal (hook/manual parity)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py check
```

## Output Requirements

Recovery responses must include:

1. Current project and completion percentage
2. Current feature (if any)
3. Workflow phase and plan validity
4. Ranked next actions (1-3 options)

Keep message concise by default; expand only when user asks for details.

## Communication Rules

- Prefer action-first guidance over narrative.
- Avoid ambiguity when state is risky.
- Explicitly call out when manual confirmation is required.

Use ready-to-send response formats from `references/communication-templates.md`.

## Escalation Guidance

Recommend escalation when:

- repeated resume attempts fail
- plan artifacts are repeatedly invalid
- git state prevents safe continuation

Escalation actions:

1. Save current findings
2. Propose concrete repair action
3. Ask user which recovery path to apply
