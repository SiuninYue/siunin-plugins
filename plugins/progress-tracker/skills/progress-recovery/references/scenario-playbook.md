# Scenario Playbook (Progress Recovery)

## Scenario 1: Active Feature, Execution Complete

- Signal: `current_feature_id != null`, `phase=execution_complete`
- Recommendation: `/prog done`
- Risk: skipping verification and leaving feature open

## Scenario 2: Active Feature, Mid Execution

- Signal: `phase=execution`
- Validate plan first.
- If plan valid: resume next unfinished task.
- If invalid: regenerate plan and continue.

## Scenario 3: No Active Feature, Pending Work

- Signal: `current_feature_id == null`, unfinished features exist
- Recommendation: `/prog next`

## Scenario 4: Dirty Working Tree

- Signal: `git status --porcelain` not empty
- Recommendation:
  1. commit/stash/discard explicitly
  2. then resume workflow

## Scenario 5: Invalid Workflow Metadata

Examples:

- active feature ID not found
- phase set but no plan path
- completed task IDs exceed total tasks

Recommendation: repair metadata before delegating new work.

## Scenario 6: Planning Clarifying Phase

- Signal: `phase=planning:clarifying`
- Read `Questions` field from persisted workflow state (or inline context).
- Re-ask questions to user.
- After user answers, proceed to `planning:draft` (do not re-run brainstorming).

## Scenario 7: Planning Draft Phase

- Signal: `phase=planning:draft`, valid plan exists
- Display `PlanSummary` from workflow state.
- Wait for user to confirm (approved) or request changes.
- Do NOT re-run brainstorming — plan already exists.
- If plan file missing: use `PlanSummary` to reconstruct without brainstorming.

## Scenario 8: Planning Approved Phase

- Signal: `phase=planning:approved`
- Read persisted `feature.ai_metrics.complexity_bucket`.
- Route directly to implementation path by bucket (no clarifying questions, no plan writing).
- If bucket unavailable: default to `standard`, output warning.

## Scenario 9: Route Preflight Blocked (Worktree Monorepo)

- Signal: mutating prog command fails with `[Route Preflight] BLOCKED: Child project_code=<X> is not registered in any parent linked_projects`
- Note: read-only commands (`prog status`, `prog check`) never reach the route-preflight guard and will not surface this error.
- Root cause: `enforce_route_preflight()` calls `_discover_parent_route_bindings_for_child()`, which scans `repo_root` and `repo_root/plugins/*` for parent trackers with a matching `linked_projects` entry. The worktree clone may lack `tracker_role: "parent"` or have stale `linked_projects` paths.
- Recovery:
  1. Identify the parent **tracker** root — the directory whose `progress.json` has `tracker_role: "parent"` (usually the original repo root, not the worktree).
  2. Register the worktree child in the parent's `linked_projects`:
     ```bash
     plugins/progress-tracker/prog \
       --project-root <worktree_path>/plugins/<child_dir> \
       link-project \
       --code <PROJECT_CODE> \
       --parent-root <parent_tracker_root>
     ```
  3. Select the route:
     ```bash
     plugins/progress-tracker/prog \
       --project-root <parent_tracker_root> \
       route-select \
       --project <PROJECT_CODE> \
       --feature-ref <CODE>-F<number>
     ```
  4. Verify: retry the original mutating command inside the worktree child project.
- Prevention: `git-auto` proactively runs the fix after worktree creation for child projects (see `git-auto/references/worktree-decision.md`).
