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
features = existing.get("features") if isinstance(existing.get("features"), list) else []
completed_count = sum(
    1 for f in features if isinstance(f, dict) and bool(f.get("completed", False))
)
```

Uses the `completed` boolean field (not `status`), which is the canonical completion field in the schema.
`isinstance(f, dict)` guards against corrupt/null entries; `bool(..., False)` makes the check explicit for truthy values.

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
            raw_features = existing.get("features")
            feature_list = raw_features if isinstance(raw_features, list) else []
            completed_count = sum(
                1 for f in feature_list
                if isinstance(f, dict) and bool(f.get("completed", False))
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

`init_tracking(force=True)` calls spread across more than 3 test files. Apply the following rules uniformly across all test files:

**Rule A — `configure_project_scope` assertions:**
Every test that explicitly calls `configure_project_scope(...)` must assert the return value:
```python
assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
```
This catches silent failures before any state-mutating call.

**Rule B — `confirm_destroy=True` additions:**
Only add `confirm_destroy=True` to `init_tracking(force=True)` calls in tests where the existing project could plausibly have `completed_count > 0` (i.e., tests that set up features and complete them before reinitializing). Tests that initialize a fresh project with no prior data do not need the flag.

Affected files include (but are not limited to):
- `tests/test_auto_state_commit.py`
- `tests/test_reinit_archive_naming.py`
- `tests/test_progress_manager.py`

The implementer must grep for all `init_tracking.*force=True` and `configure_project_scope` call sites and apply the rules above.

## Error Message (final form)

```
ERROR: 13 completed feature(s) detected in 'progress-tracker-sop-compliance-optimization'.
Refusing to overwrite real project data.
Pass confirm_destroy=True (API) or --confirm-destroy (CLI) to proceed.
```

## Testing

Minimum required tests (TDD), all in new file `tests/test_init_confirm_destroy.py`:

1. `test_init_force_blocked_when_completed_features_exist` — `init_tracking(force=True)` returns False when completed > 0
2. `test_init_force_confirm_destroy_bypasses_protection` — `init_tracking(force=True, confirm_destroy=True)` proceeds normally
3. `test_init_force_allowed_when_no_completed_features` — `init_tracking(force=True)` proceeds when all features are pending (no confirm_destroy needed)
4. `test_init_force_allowed_on_empty_project` — no regression on fresh init
5. `test_cli_init_force_blocked_without_confirm_destroy` — CLI returns non-zero exit when data has completed features
6. `test_cli_init_force_confirm_destroy_succeeds` — CLI proceeds with `--force --confirm-destroy`
7. `test_cli_confirm_destroy_without_force_is_noop` — `prog init --confirm-destroy "Name"` (without `--force`) behaves identically to `prog init "Name"`: no error, no special handling. The flag is silently ignored when `--force` is absent.

## Files Changed

| File | Change |
|------|--------|
| `hooks/scripts/progress_manager.py` | Add `confirm_destroy` param + guard logic + CLI flag + dispatch + Usage doc update |
| `tests/test_progress_manager.py` | Apply Rule A/B per Change 4 |
| `tests/test_reinit_archive_naming.py` | Apply Rule A/B per Change 4 |
| `tests/test_auto_state_commit.py` | Apply Rule A/B per Change 4 |
| All other test files with `init_tracking.*force=True` | Apply Rule A/B per Change 4 |
| New: `tests/test_init_confirm_destroy.py` | 7 new TDD tests for the protection behavior |

### Change 5: CLI Usage doc sync

File: `progress_manager.py`, top-of-file Usage comment.

Update the `init` command signature from:
```
init [--force] <project_name>
```
to:
```
init [--force] [--confirm-destroy] <project_name>
```

This prevents CLI help text from drifting out of sync with the actual implementation.
