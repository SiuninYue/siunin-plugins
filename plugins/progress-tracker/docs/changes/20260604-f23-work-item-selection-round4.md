# 20260604-f23-work-item-selection-round4

## Summary

Extracted work-item selection and `next-feature` command orchestration from
`hooks/scripts/progress_manager.py` into focused collaborator modules.

## Scope

- Created `hooks/scripts/work_item_selector.py` for pure selection helpers:
  `get_next_feature`, child/root dispatch selection, and unified bug/task/feature
  priority selection.
- Created `hooks/scripts/next_feature_commands.py` for `next-feature` command
  orchestration, JSON/text output, task activation, planning-gate rendering, and
  parent active-route bookkeeping.
- Kept `progress_manager.py` as the compatibility facade with wrappers marked
  `is_wrapper = True`.
- Updated `docs/progress-tracker/architecture/progress-manager-module-map.md`
  to record Round 4 ownership.

## Validation

- `uv run pytest plugins/progress-tracker/tests/test_dispatch_child_feature.py plugins/progress-tracker/tests/test_unified_selection.py -q`
- `uv run pytest plugins/progress-tracker/tests/test_progress_manager.py -k 'next_feature or planning_gate or finish_pending' -q`
- `uv run pytest plugins/progress-tracker/tests/test_task_execution_semantics.py plugins/progress-tracker/tests/test_scope_fail_closed.py -q`
- `scripts/check_pm_boundary.sh`

## Rollback

Revert this change record and the Round 4 extraction commit. The facade wrappers
can be restored by moving the extracted function bodies back into
`progress_manager.py` if a compatibility issue is found.
