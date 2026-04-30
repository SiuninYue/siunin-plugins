---
name: feature-implement
description: This skill should be used when the user runs "/prog next", asks to "implement next feature", "start next feature", "continue implementation", or needs to resume interrupted feature execution. Routes features to appropriate implementation paths based on complexity assessment.
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
  - "superpowers:using-git-worktrees"
  - "superpowers:writing-plans"
  - "superpowers:subagent-driven-development"
  - "superpowers:test-driven-development"
  - "superpowers:requesting-code-review"
  - "superpowers:verification-before-completion"
  - "./references/complexity-assessment.md"
  - "./references/superpowers-integration.md"
  - "./references/session-playbook.md"
---

# Feature Implementation Skill

Coordinate `/prog next` execution by selecting the next feature, routing to the correct implementation path, and keeping workflow state resumable.

## Inline Context Fast Path

**Check this FIRST before any other step.**

If the invocation includes inline context lines (`Feature:`, `Phase:`, `Plan:`, `Branch:`, `Worktree:`, `Next:`), treat them as pre-loaded state and do the following:

1. Parse inline context:
   - `Feature` → `feature_id` and `feature_name`
   - `Phase` → `workflow_state.phase`
   - `Plan` → `workflow_state.plan_path`
   - `PlanSummary` → single-line plan summary (semicolon-separated)
   - `Tasks` → completed/total counts
   - `Next` → next task to execute
   - `Branch` / `Worktree` → `execution_context`
   - `Bucket` → complexity bucket (`simple|standard|complex`)
   - `Questions` → clarifying questions (pipe-separated)
   - `ProjectRoot` → absolute path for all `prog` calls

2. If `Worktree` is present: **store `worktree_path` as the execution root for all shell commands**.

   > **CWD does NOT persist between Bash calls.** Never use a bare `cd`. Prefix every command: `cd <worktree_path> && <command>`

   Verify the path is accessible before proceeding:
   ```bash
   ls <worktree_path>
   ```
   If the path is inaccessible, warn the user and stop.

3. If `Branch` is present: verify the checked-out branch matches.
   - If `worktree_path` is present: `cd <worktree_path> && git branch --show-current`
   - If `worktree_path` is absent: `git branch --show-current`
   If branch doesn't match, **auto-switch** with a safety check:
   - Clean working tree → `git switch <branch>` and continue.
   - Uncommitted changes → STOP: warn user to commit or stash first.

4. **Skip entirely** (do not run): Steps 1 full re-read, Step 2.5 git preflight, complexity re-scoring.

5. Route directly by `Phase`:
   - `execution_complete` → output the `prog-done` handoff block and stop (do not re-implement)
   - `execution` → jump to Step 4 route with existing plan, resume from `Next` task
   - `planning_complete` → jump to Step 4B subagent execution with existing plan
   - `planning` → jump to Step 3 complexity scoring
   - `planning:review` → display `PlanSummary`, collect approval/changes, and STOP (single planning stop)
   - `planning:approved` → verify worktree accessible (if present) → read inline `Bucket:` field and route execution directly:
     - Skip: Steps 2.4, 2.5, brainstorming, writing-plans
     - Bucket routing (priority: inline `Bucket:` > persisted `feature.ai_metrics.complexity_bucket` > standard fallback):
       - `simple` → delegate to `feature-implement-simple`
       - `standard` → Step 4B coordinator
       - `complex` → delegate to `feature-implement-complex`
     - If `Bucket` missing or invalid: read persisted `feature.ai_metrics.complexity_bucket` once (fallback only); if still unavailable → default to `standard` and output warning: "Bucket unknown, defaulting to standard" — do NOT stop execution
   - `planning:draft` / `planning:clarifying` (legacy phase) → normalize to `planning:review` behavior: display current plan/questions, request one approval turn, then continue

6. `ProjectRoot` present → pass `--project-root <project_root>` to **every** `prog` CLI call.
   Branch/worktree mismatch validation still applies (ProjectRoot only determines command directory, does not bypass checks).

**Inline context is authoritative.** Do not re-read `progress.json` to verify it.

---

## Core Responsibilities

1. Select the next actionable feature from `docs/progress-tracker/state/progress.json`.
2. Set and persist workflow state before delegation.
3. Route work by deterministic complexity rules.
4. Ensure all commands use `plugins/progress-tracker/prog` entry point.
5. Hand off cleanly to `/prog done`.
6. Run Git/worktree preflight before delegation.
7. Apply review + verification gates before marking implementation complete.
8. Persist execution context whenever workflow state advances.

## Use This Skill For

- `/prog next` command.
- Resuming interrupted feature work.
- Starting or continuing a pending feature.

## Execution Context Requirements

**CRITICAL**: All `prog` commands must run from project root — the tool uses relative paths.

## Required Read Order

1. Read `docs/progress-tracker/state/progress.json` and identify:
   - `current_feature_id`
   - next actionable feature (skip `deferred=true`)
   - **顶层** `workflow_state`（if present）— 不要读 `features[n].workflow_state`
2. If `docs/progress-tracker/architecture/architecture.md` exists, read constraints and apply them.
3. Before any delegation, create lightweight checkpoint:

```bash
plugins/progress-tracker/prog auto-checkpoint
```
4. Run Git sync preflight:

```bash
plugins/progress-tracker/prog git-sync-check
```

## Main Flow

### Step 1: Validate Current State

- If no progress file exists: instruct user to run `/prog init <goal>`.
- If all features are complete: show completion message and stop.
- If `current_feature_id` is already set and not complete:
  - Check 顶层 `workflow_state.phase`:
    - `execution_complete` → tell user to run `/prog done`, stop here.
    - `execution` or `planning_complete` → resume from next unfinished task (skip to Step 2.5, use existing plan_path).
    - `planning` or missing → continue normally from Step 2.
  - Do not overwrite active feature or re-run git preflight if 顶层 `workflow_state.execution_context` already matches current branch/worktree.

### Step 2: Select and Lock Feature

- Resolve next actionable feature via CLI (skip deferred features):

```bash
plugins/progress-tracker/prog next-feature --json
```

- Persist as active feature:

```bash
plugins/progress-tracker/prog set-current <feature_id>
```

- `set-current` now auto-transitions the active feature into `developing`.
- Do not require `/prog-start` as an extra manual transition.

- Display:
  - feature ID and name
  - acceptance test steps
  - architecture constraints (if any)

### Step 2.5: Unified Git Auto Preflight

**Skip this step if resuming** (phase was `execution` or `planning_complete`) **and 顶层 `workflow_state.execution_context` matches the current branch/worktree.** Just continue from the saved plan.

Otherwise, run preflight:

```bash
plugins/progress-tracker/prog git-auto-preflight --json
```

Parse JSON result and branch by `decision`:

1. `ALLOW_IN_PLACE` → continue without workspace changes.
2. `REQUIRE_WORKTREE` → `Skill("superpowers:using-git-worktrees", args="Set up isolated workspace for feature-<id>")`
3. `DELEGATE_GIT_AUTO` → `Skill("progress-tracker:git-auto", args="Resolve workspace/git preflight blockers")`

Rules:
- Never block `/prog next` permanently; if delegation fails, return actionable recovery guidance.
- Surface `reason_codes` and top `issues` in a short warning summary.

### Step 3: Planning Sub-Phase Flow

1. Complete complexity scoring first and persist AI metrics:
   ```bash
   plugins/progress-tracker/prog set-feature-ai-metrics <feature_id> \
     --complexity-score <score> \
     --selected-model <haiku|sonnet|opus> \
     --workflow-path <direct_tdd|plan_execute|full_design_plan_execute>
   ```
2. If bucket is `simple`, skip planning entirely and jump straight to Step 4A.
3. If bucket is `standard` or `complex`, generate one executable plan (include clarifications inline instead of a separate clarifying stop), then set:
   ```bash
   plugins/progress-tracker/prog set-workflow-state --phase "planning:review" --plan-path <path>
   ```
4. Output `planning:review` handoff block and STOP once for user approval/edits.
5. After approval, set:
   ```bash
   plugins/progress-tracker/prog set-workflow-state --phase "planning:approved" --plan-path <path>
   ```
6. Route immediately by persisted bucket and continue execution in the same session.

**Valid `--phase` values:** `planning`, `planning:review`, `planning:approved`, `planning_complete`, `execution`, `execution_complete`  
Legacy phases `planning:clarifying` / `planning:draft` should be treated as `planning:review`.

### Step 4: Route by Bucket

#### 4A) Simple (`0-15`)

- Delegate to `progress-tracker:feature-implement-simple`.
- The simple skill handles execution note generation and phase transition
  to `execution` internally (Step 2).
- Keep flow RED -> GREEN -> REFACTOR.

#### 4B) Standard (`16-25`)

- Remain in this coordinator.
- Default path:
  1. Reuse approved plan from Step 3 (`planning:approved`).
  2. Enter execution phase:
  ```bash
  plugins/progress-tracker/prog set-workflow-state --phase "execution" --plan-path <path>
  ```
  3. `subagent-driven-development` to execute plan with TDD.
  4. Populate sprint contract from implemented scope:
  ```bash
  plugins/progress-tracker/prog set-sprint-contract \
    --feature-id <feature_id> \
    --scope "<brief scope description>" \
    --done-criteria "<criteria 1>" "<criteria 2>" \
    --test-plan "<test plan item 1>" "<test plan item 2>"
  ```
  5. Transition to `execution_complete`:
  ```bash
  plugins/progress-tracker/prog set-workflow-state --phase "execution_complete" --next-action "verify_and_complete"
  ```
- Update workflow state at each gate:
  ```bash
  plugins/progress-tracker/prog set-workflow-state --phase "planning_complete" --plan-path <path>
  plugins/progress-tracker/prog set-workflow-state --phase "execution" --plan-path <path>
  ```
- Do not run final review/evaluator/ship-check in this step; `/prog done` owns final gates.

Important compatibility rule:
- In `/prog next` flow, treat implementation as finished at "code + verification ready".
- Do not run branch-finalization actions from this skill path.
- Feature completion is handled by `/prog done`.

#### 4C) Complex (`26-40`)

- Delegate to `progress-tracker:feature-implement-complex`.
- Expect architecture-heavy path with explicit brainstorming + planning + execution gates.

#### 4D) Fallback Rule

If delegation fails for simple/complex path, fallback to standard coordinator path and continue with sonnet workflow.

### Step 5: Persist Workflow State

Use these commands when phase changes:

```bash
plugins/progress-tracker/prog set-workflow-state \
  --phase <design_complete|planning_complete|execution|execution_complete> \
  --plan-path <docs/plans/...> \
  --next-action "<human-readable next action>"
```

For task completion checkpoints during execution:

```bash
plugins/progress-tracker/prog update-workflow-task <task_id> completed
```

Context note:
- `set-workflow-state` and `update-workflow-task` now persist 顶层 `workflow_state.execution_context` (branch/worktree).
- Recovery flows and `/prog done` should use this top-level context to detect worktree/branch mismatches.

### Step 6: Completion Handoff

When implementation is done:

- summarize what was implemented (2-3 bullet points)
- confirm expected acceptance steps
- indicate that final gates (review/evaluator/ship-check) will be enforced by `/prog done`
- output a Context Handoff Block (see template below)

Do not mark the feature complete in this skill.

Use the Context Handoff Block templates from `progress-recovery/references/communication-templates.md`:
- `execution_complete` → use the `prog-done` block template
- `execution` / `planning_complete` → use the `prog-next` block template
- `planning` → use the planning block template
- `planning:review` → use the `planning:review` block template
- `planning:clarifying` / `planning:draft` (legacy) → map to `planning:review` template
- `planning:approved` → use the `planning:approved` block template

## Recovery Rules

When an interrupted workflow is detected:

- Validate plan integrity before resuming:

```bash
plugins/progress-tracker/prog validate-plan
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

If `current_feature_id` points to missing feature, clear invalid state via recovery workflow, then recalculate the next actionable (non-deferred) feature.

## Required Output Shape

When this skill starts a feature, always include:

1. Active feature (`id + name`)
2. Complexity result (`score + bucket + selected_model`)
3. Workflow path chosen
4. Current phase status — show `/prog done` instruction **only** when `phase=execution_complete`; during planning/execution show current phase and expected next step instead
5. Context Handoff Block at the end of every response:

**Phase = `execution_complete`:**
```text
/progress-tracker:prog-done

Feature: <feature_id> "<feature_name>" | Phase: execution_complete
Plan: <plan_path> | Tasks: <total>/<total> done
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-switches to correct branch if needed.
```

**Phase = `execution` or `planning_complete`:**
```text
/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: <phase>
Plan: <plan_path> | Tasks: <completed>/<total> done
Next: <next_task_id> — <next_task_title>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-switches to correct branch if needed.
```

**Phase = `planning:approved`:**
```text
/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: planning:approved
Plan: <plan_path>
Bucket: <simple|standard|complex>
Tasks: <total_count>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Routes by Bucket field.
```

**Source of truth for `<branch>`:** Use `git branch --show-current` (or `cd <worktree_path> && git branch --show-current`). Never read from `execution_context.branch` — it is stale.

## Additional Resources

- `references/complexity-assessment.md`:
  - scoring rubric and forced override rules.
- `references/superpowers-integration.md`:
  - integration design and layered quality model.
- `references/session-playbook.md`:
  - detailed resume flows, interruption handling, and recovery messaging.
