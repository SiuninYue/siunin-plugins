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
