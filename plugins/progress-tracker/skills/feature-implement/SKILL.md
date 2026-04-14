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
   - `ProjectRoot` → absolute project root path (used for all `prog` commands)

2. If `Worktree` is present: **store `worktree_path` as the execution root for all shell commands**.

   > **Claude Code — CWD does NOT persist between Bash tool calls.**  
   > A standalone `cd <worktree_path>` affects only that single call and has no effect on subsequent calls.  
   > Do NOT use a bare `cd` to set context.  
   > Instead, prefix **every** shell command that must run in the feature directory with:  
   > `cd <worktree_path> && <command>`

   Verify the path is accessible before proceeding:
   ```bash
   ls <worktree_path>
   ```
   If the path is inaccessible, warn the user and stop.

3. If `Branch` is present: verify the checked-out branch matches.
   - If `worktree_path` is present:
     ```bash
     cd <worktree_path> && git branch --show-current
     ```
   - If `worktree_path` is absent (in-place session):
     ```bash
     git branch --show-current
     ```
   If branch doesn't match, stop and ask the user to switch to `<branch>` first; do not run `git checkout` automatically.

4. **Skip entirely** (do not run): Steps 1 full re-read, Step 2.4 memory overlap check, Step 2.5 git preflight, complexity re-scoring.

5. Route directly by `Phase`:
   - `execution_complete` → output the `prog-done` handoff block and stop (do not re-implement)
   - `execution` → jump to Step 4 route with existing plan, resume from `Next` task
   - `planning_complete` → jump to Step 4B subagent execution with existing plan
   - `planning` → jump to Step 3 complexity scoring
   - `planning:approved` → verify worktree accessible (if present) → read inline `Bucket:` field and route execution directly:
     - Skip: Steps 2.4, 2.5, brainstorming, writing-plans
     - Bucket routing (priority: inline `Bucket:` > persisted `feature.ai_metrics.complexity_bucket` > standard fallback):
       - `simple` → delegate to `feature-implement-simple`
       - `standard` → Step 4B coordinator
       - `complex` → delegate to `feature-implement-complex`
     - If `Bucket` missing or invalid: read persisted `feature.ai_metrics.complexity_bucket` once (fallback only); if still unavailable → default to `standard` and output warning: "Bucket unknown, defaulting to standard" — do NOT stop execution
   - `planning:draft` → display `PlanSummary`, wait for user approval/changes; do NOT re-run brainstorming
   - `planning:clarifying` → read `Questions` field, re-ask questions, proceed to draft after answers received

6. `ProjectRoot` present → pass `--project-root <project_root>` to **every** `prog` CLI call.
   Branch/worktree mismatch validation still applies (ProjectRoot only determines command directory, does not bypass checks).

**The inline context is the source of truth.** Do not re-read `progress.json` to "verify" it — that defeats the purpose.

---

## Core Responsibilities

1. Select the next actionable feature from `docs/progress-tracker/state/progress.json`.
2. Set and persist workflow state before delegating implementation.
3. Route work by deterministic complexity rules.
4. Ensure all commands use `plugins/progress-tracker/prog` entry point.
5. Hand off cleanly to `/prog done` after implementation.
6. Run Git/worktree preflight before delegation.
7. Apply review + verification gates before claiming implementation complete.
8. Persist execution context (branch/worktree) whenever workflow state/task progress advances.

## Use This Skill For

- `/prog next` command execution.
- Recovery-driven continuation after interrupted feature work.
- Any request to start or continue the next pending feature.

## Execution Context Requirements

**CRITICAL**: All `plugins/progress-tracker/prog` commands MUST be executed from the project root directory.

If not already in the project root, first run:
```bash
cd <project-root>
```

The `prog` tool uses relative paths and requires being in the correct project directory to resolve files correctly.

## Required Read Order

1. Read `docs/progress-tracker/state/progress.json` and identify:
   - `current_feature_id`
   - next actionable feature (skip `deferred=true`)
   - `workflow_state` (if present)
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
  - Check `workflow_state.phase`:
    - `execution_complete` → tell user to run `/prog done`, stop here.
    - `execution` or `planning_complete` → resume from next unfinished task (skip to Step 2.5, use existing plan_path).
    - `planning` or missing → continue normally from Step 2.
  - Do not overwrite active feature or re-run git preflight if `workflow_state.execution_context` already matches current branch/worktree.

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

### Step 2.4: Project Memory Overlap Warning (Read-Only, Silent)

**Only run this step if `workflow_state.phase` is not already set** (i.e., this is a fresh feature start, not a resume).

1. Run: `plugins/progress-tracker/prog memory read` (project_memory.py read)
2. If memory is empty or returns error → skip, continue silently.
3. If memory has entries, do a lightweight keyword match (feature name vs capability IDs) — no deep Claude reasoning.
4. Only surface a warning if there is a clear name/keyword collision. Otherwise, stay silent.
5. Never block `/prog next`.

### Step 2.5: Unified Git Auto Preflight

**Skip this step if resuming** (phase was `execution` or `planning_complete`) **and `workflow_state.execution_context` matches the current branch/worktree.** Just continue from the saved plan.

Otherwise, run preflight:

```bash
plugins/progress-tracker/prog git-auto-preflight --json
```

Parse JSON result and branch by `decision`:

1. `ALLOW_IN_PLACE` → continue without workspace changes.
2. `REQUIRE_WORKTREE` → `Skill("using-git-worktrees", args="Set up isolated workspace for feature-<id>")`
3. `DELEGATE_GIT_AUTO` → `Skill("progress-tracker:git-auto", args="Resolve workspace/git preflight blockers")`

Rules:
- Never block `/prog next` permanently; if delegation fails, return actionable recovery guidance.
- Surface `reason_codes` and top `issues` in a short warning summary.

### Step 3: Planning Sub-Phase Flow

Before complexity scoring, initiate the planning sub-phase to clarify requirements.

#### Sub-phase A: Clarifying

0. **[Pre-step]** Complete complexity scoring using `references/complexity-assessment.md`, persist AI metrics:
   ```bash
   plugins/progress-tracker/prog set-feature-ai-metrics <feature_id> \
     --complexity-score <score> \
     --selected-model <haiku|sonnet|opus> \
     --workflow-path <direct_tdd|plan_execute|full_design_plan_execute>
   ```
1. Analyze feature, identify 2-4 design decision questions (skip obvious ones).
2. Set workflow state:
   ```bash
   plugins/progress-tracker/prog set-workflow-state --phase "planning:clarifying"
   ```
3. Output `planning:clarifying` handoff block (see `progress-recovery/references/communication-templates.md`).
4. Ask questions directly to user. **STOP.**

#### Sub-phase B: Draft

1. Use `writing-plans` skill (incorporating user answers) to generate plan.
2. Generate `PlanSummary` — single line, semicolon-separated, 3-5 key points.
3. Set workflow state:
   ```bash
   plugins/progress-tracker/prog set-workflow-state --phase "planning:draft" --plan-path <path>
   ```
4. Display complete plan.
5. Output `planning:draft` handoff block. **STOP.**

#### Sub-phase C: Approved

1. Set workflow state:
   ```bash
   plugins/progress-tracker/prog set-workflow-state --phase "planning:approved" --plan-path <path>
   ```
2. Output `planning:approved` handoff block.
3. Immediately route by persisted `complexity_bucket` and begin execution (same session — do NOT STOP).

**Valid `--phase` values:** `planning`, `planning:clarifying`, `planning:draft`, `planning:approved`, `planning_complete`, `execution`, `execution_complete`
(`planning_complete` retained for backward compatibility)

### Step 4: Route by Bucket

#### 4A) Simple (`0-15`)

- Delegate to `progress-tracker:feature-implement-simple`.
- Keep flow RED -> GREEN -> REFACTOR.
- Update `workflow_state.phase` to execution before delegation.

#### 4B) Standard (`16-25`)

- Remain in this coordinator.
- Default path:
  1. Run `brainstorming` when behavior/design decisions are still open.
  2. `writing-plans` to produce executable task plan.
  3. `subagent-driven-development` to execute plan with TDD.
  4. `requesting-code-review` for final diff validation.
  5. `verification-before-completion` before phase transition to `execution_complete`.
- Update workflow state transitions:
  - `planning_complete` once plan is accepted
  - `execution` while tasks run
  - `execution_complete` when implementation is finished

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
- `set-workflow-state` and `update-workflow-task` now also persist `workflow_state.execution_context` (branch/worktree).
- Recovery flows and `/prog done` should use this context to detect worktree/branch mismatches.

### Step 6: Completion Handoff

When implementation is done:

- summarize what was implemented (2-3 bullet points)
- confirm expected acceptance steps
- confirm review + verification gates were executed
- output a Context Handoff Block (see template below)

Do not mark the feature complete in this skill.

Use the Context Handoff Block templates from `progress-recovery/references/communication-templates.md`:
- `execution_complete` → use the `prog-done` block template
- `execution` / `planning_complete` → use the `prog-next` block template
- `planning` → use the planning block template
- `planning:clarifying` → use the `planning:clarifying` block template
- `planning:draft` → use the `planning:draft` block template
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
→ Context pre-loaded. Switch to worktree/branch above first if not already there.
```

**Phase = `execution` or `planning_complete`:**
```text
/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: <phase>
Plan: <plan_path> | Tasks: <completed>/<total> done
Next: <next_task_id> — <next_task_title>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Switch to worktree/branch above first if not already there.
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

## Additional Resources

- `references/complexity-assessment.md`:
  - scoring rubric and forced override rules.
- `references/superpowers-integration.md`:
  - integration design and layered quality model.
- `references/session-playbook.md`:
  - detailed resume flows, interruption handling, and recovery messaging.
