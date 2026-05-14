# Design: `prog init --force` Confirm-Destroy Protection

**Date:** 2026-05-14
**Status:** Approved
**Scope:** `plugins/progress-tracker`

## Problem

`prog init --force` silently archives and overwrites real project data with no safeguard. In a prior incident, a test's `configure_project_scope` call failed silently, leaving `_PROJECT_ROOT_OVERRIDE` unset. The subsequent `init_tracking("Test", force=True)` resolved to the real PT plugin directory and archived 17 features (13 completed) of live project data.

The root cause was two failures stacking: (1) no assertion on `configure_project_scope` return value in tests, and (2) no safety net in `init_tracking` itself.

## Goal

Prevent AI (or any caller) from accidentally destroying real project data via `prog init --force`. Even if test isolation fails again, the default behavior of `init_tracking` must refuse to overwrite data that contains completed work.

## Design

### Protection Threshold

Trigger protection when `completed_count > 0`, where:

```python
completed_count = sum(1 for f in existing.get("features", []) if f.get("completed"))
```

Uses the `completed` boolean field (not `status`), which is the canonical completion field in the schema.

Known tradeoff: a project with features but none completed (all pending) is still overwritable with `--force` alone. Accepted — this matches the intent of the threshold.

### Change 1: Python API — `init_tracking()`

File: `progress_manager.py`, near line 5102.

Add `confirm_destroy=False` parameter. Inside the `force` branch, **before** `archive_current_progress()`, add the guard:

```python
def init_tracking(project_name, features=None, force=False, confirm_destroy=False):
    ...
    if force:
        existing = load_progress_json()
        if isinstance(existing, dict) and not confirm_destroy:
            completed_count = sum(
                1 for f in existing.get("features", []) if f.get("completed")
            )
            if completed_count > 0:
                project = existing.get("project_name", "unknown")
                print(
                    f"ERROR: {completed_count} completed feature(s) detected in "
                    f"'{project}'. Refusing to overwrite real project data.\n"
                    "Pass confirm_destroy=True (API) or --confirm-destroy (CLI) to proceed."
                )
                return False
        # existing guard for parent_project_root ...
        archived_entry = archive_current_progress(reason="reinitialize")
```

### Change 2: CLI — `prog init` subparser

File: `progress_manager.py`, near line 11415.

```python
init_parser.add_argument(
    "--confirm-destroy",
    action="store_true",
    help="Required when force-reinitializing a project with completed features.",
)
```

### Change 3: CLI dispatch

File: `progress_manager.py`, near line 12065.

```python
if args.command == "init":
    return init_tracking(
        args.project_name,
        force=args.force,
        confirm_destroy=getattr(args, "confirm_destroy", False),
    )
```

### Change 4: Fix affected tests (Plan B — test isolation hardening)

All tests that call `init_tracking(force=True)` directly must:
1. Add `confirm_destroy=True` (tests legitimately need to reinitialize)
2. Add `assert configure_project_scope(...) is True` before any `init_tracking` call

Files to update:
- `tests/test_auto_state_commit.py` — all `TestGetDirtyStateFiles` and related tests
- `tests/test_reinit_archive_naming.py` — all reinit tests
- `tests/test_progress_manager.py` — `TestInitTracking` class

## Error Message (final form)

```
ERROR: 13 completed feature(s) detected in 'progress-tracker-sop-compliance-optimization'.
Refusing to overwrite real project data.
Pass confirm_destroy=True (API) or --confirm-destroy (CLI) to proceed.
```

## Testing

Minimum required tests (TDD):

1. `test_init_force_blocked_when_completed_features_exist` — `init_tracking(force=True)` returns False when completed > 0
2. `test_init_force_confirm_destroy_bypasses_protection` — `init_tracking(force=True, confirm_destroy=True)` proceeds normally
3. `test_init_force_allowed_when_no_completed_features` — `init_tracking(force=True)` proceeds when all features are pending
4. `test_init_force_allowed_on_empty_project` — no regression on fresh init
5. `test_cli_init_force_blocked_without_confirm_destroy` — CLI returns non-zero exit when data has completed features
6. `test_cli_init_force_confirm_destroy_succeeds` — CLI proceeds with both flags

## Files Changed

| File | Change |
|------|--------|
| `hooks/scripts/progress_manager.py` | Add `confirm_destroy` param + guard logic + CLI flag + dispatch |
| `tests/test_progress_manager.py` | Add `confirm_destroy=True` + assert scope in existing force tests |
| `tests/test_reinit_archive_naming.py` | Add `confirm_destroy=True` to all reinit calls |
| `tests/test_auto_state_commit.py` | Add assert on `configure_project_scope` + `confirm_destroy=True` |
| New: `tests/test_init_confirm_destroy.py` | 6 new TDD tests for the protection behavior |
