# Archive Cleanup: Clear Active Progress on Project Completion

**Date**: 2026-04-26
**Project**: progress-tracker (PT)
**Bug Ref**: Discovered during status review — SPM (6/6) and NO (10/10) show completed features instead of 0/0

## Problem

When all features in a project are completed, `complete_feature()` calls `archive_current_progress(reason="completed")` which only creates a backup snapshot. The active `progress.json` retains all completed features indefinitely, causing:

- Completed projects show stale counts (e.g., SPM 6/6, NO 10/10) instead of 0/0
- Stale `runtime_context` with dead branch references and feature IDs
- Confusion about whether a project has ongoing work

## Design

### Approach: Independent `_reset_active_progress()` function (Option C)

Add a new function `_reset_active_progress(data)` that clears completed project state from the active `progress.json`. Called in `complete_feature()` when `_is_project_fully_completed()` is true — regardless of whether `archive_current_progress()` succeeded. Archive is a best-effort backup; the active state must be cleaned up either way.

### Changes

#### 1. New function: `_reset_active_progress(data)`

**File**: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

Clears these fields:
- `features` → `[]`
- `bugs` → `[]`
- `updates` → `[]`
- `retrospectives` → `[]`
- `current_feature_id` → `None`
- `current_bug_id` → `None`
- `workflow_state` → removed

Preserves structure, clears work fields in `runtime_context`:
- `current_feature_id` → `None`
- `workflow_phase` → `None`
- `current_task` → `None`
- `total_tasks` → `None`
- `next_action` → `None`

Also:
- Records `project_completed` event in `audit.log` **first** (fail-closed: if audit write fails, do not clear active state)
- Updates `updated_at` to `_iso_now()`
- Calls `save_progress_json(data)`
- Regenerates `progress.md` for empty state
- Prints confirmation: `"Active progress cleared — project state is now 0/0."`

**Write order is critical**: `project_completed` is a boundary event that downstream consumers (`_replay_audit_events`, `find_backfill_candidates`) rely on to delimit project cycles. The audit event must be durably recorded **before** the active state is cleared. If the audit write fails, the active state must not be cleared — otherwise old-cycle `feature_completed` events would corrupt the new cycle's reconcile/backfill. This is the same fail-closed pattern used by `reset_tracking()`, which writes `tracker_reset` to audit.log before deleting progress files.

#### 2. Call site: `complete_feature()`

**File**: `plugins/progress-tracker/hooks/scripts/progress_manager.py` (line ~7936)

The fully-completed check and reset must live **outside** the `if not skip_archive` block. Only `archive_current_progress()` itself is gated by `skip_archive`; the reset must always run when all features are complete, otherwise `prog done --skip-archive` on the last feature would leave stale active state.

```python
# ── Inside existing if not skip_archive block ──
if not skip_archive:
    try:
        feature_name = feature.get("name", f"Feature {feature_id}")
        print(f"\nArchiving documents for {feature_name}...")
        archive_result = archive_feature_docs(feature_id, feature_name)
        # ... existing archive logic ...
    except Exception as e:
        # Archive failures should not prevent feature completion
        logger.error(f"Archive failed but feature completed: {e}")
        print(f"Warning: Document archiving failed but feature is marked complete")

    refreshed = load_progress_json()
    if refreshed and _is_project_fully_completed(refreshed):
        try:
            completed_archive = archive_current_progress(reason="completed")
            if completed_archive:
                print(
                    "Archived completed run as "
                    f"{completed_archive.get('archive_id')} "
                    f"(reason={completed_archive.get('reason')})"
                )
        except Exception as e:
            # Archive I/O can fail (mkdir, copy2, save_history).
            # Best-effort: log and continue — reset must still happen.
            logger.error(f"Completed-run archive failed: {e}")
            print(f"Warning: Completed-run archive failed, but active state will still be cleared.")

# ── Outside if not skip_archive — always runs ──
refreshed = load_progress_json()
if refreshed and _is_project_fully_completed(refreshed):
    _reset_active_progress(refreshed)
```

Note: `_reset_active_progress` is called regardless of `skip_archive` and regardless of whether `archive_current_progress()` succeeded or threw. Archive is best-effort; active state cleanup must always happen.

#### 3. Audit log: Add `project_completed` event type

**File**: `plugins/progress-tracker/hooks/scripts/audit_log.py`

Add `"project_completed"` to `ALLOWED_EVENT_TYPES`.

#### 4. Audit boundary handling: `project_completed`

**File**: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

All audit-boundary consumers that treat `tracker_reset` as a state boundary must also treat `project_completed` as a boundary. After a `project_completed` event, prior `feature_completed` events belong to the archived project cycle and must not influence the new cycle.

Affected consumers:

1. **`_replay_audit_events()`**: Add `project_completed` alongside `tracker_reset` so it clears all prior feature states when replaying.

2. **`find_backfill_candidates()`**: Currently only checks `tracker_reset` to find the last reset boundary (line ~3356). Must also check `project_completed` — after a project completion, the old cycle's `feature_completed` events should not suppress backfill for new-cycle features that happen to reuse the same IDs. Update the boundary scan to:
   ```python
   BOUNDARY_EVENT_TYPES = {"tracker_reset", "project_completed"}
   for i, r in enumerate(all_records):
       if r.get("event_type") in BOUNDARY_EVENT_TYPES:
           last_reset_idx = i
   ```

#### 5. Tests

Add tests in `plugins/progress-tracker/tests/`:

- **`test_complete_feature_clears_active_state`**: Verify that calling `complete_feature` on the last feature resets `features`, `bugs`, `updates`, `retrospectives` to empty arrays, clears `current_feature_id`/`current_bug_id`, removes `workflow_state`, and resets `runtime_context` work fields.
- **`test_complete_feature_clears_with_skip_archive`**: Verify that `_reset_active_progress` runs even when `skip_archive=True`. Call `complete_feature(feature_id, skip_archive=True)` on the last feature and confirm the active state is still cleared to 0/0.
- **`test_complete_feature_clears_when_archive_throws`**: Mock `archive_current_progress` to raise `OSError`. Call `complete_feature` on the last feature and confirm `_reset_active_progress` still runs and active state is cleared to 0/0.
- **`test_reset_active_progress_fail_closed_on_audit_error`**: Mock `record_feature_state_event` to raise `ValueError`. Verify that `_reset_active_progress` does NOT clear active state (features/bugs/updates/retrospectives remain intact) when the audit boundary event write fails.
- **`test_project_completed_audit_event`**: Verify `project_completed` event is recorded in audit.log.
- **`test_reconcile_after_project_completed`**: Verify that reconcile logic treats `project_completed` as a state boundary (like `tracker_reset`).
- **`test_backfill_after_project_completed_id_reuse`**: Verify that `find_backfill_candidates()` correctly ignores `feature_completed` events before a `project_completed` boundary, even when feature IDs are reused in the new cycle.

### What stays the same

- `archive_current_progress()` — only backs up, does not modify active state
- `prog reset` — its own destructive path, deletes files entirely
- `progress-status` skill — handles 0/0 natively (empty features array)
- Parent tracker `linked_snapshot` and `active_routes` — separate concern, not in scope