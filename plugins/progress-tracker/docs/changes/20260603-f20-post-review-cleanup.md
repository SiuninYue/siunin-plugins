# F20 Post-Review Cleanup: Boundary Docs, Service Injection, Module Map

**Change ID:** 20260603-f20-post-review-cleanup  
**Date:** 2026-06-03  
**Component:** `progress_manager` facade convergence

## Problem

After F20 Round 0-1 landed, review found three follow-up issues:

- The boundary change record still described line-precise allowlist matching,
  while the checker now filters allowlisted files by file name to avoid line
  drift.
- `StatusCommandServices` carried callbacks for helpers that already live in
  leaf modules and do not need facade injection.
- `git_utils.collect_git_context()` still probed `sys.modules["progress_manager"]`,
  creating a hidden facade-aware coupling even without a direct import.

The F20 plan also required a post-Round-1 module map, but the navigation
artifact did not exist yet.

## Fix

- Updated the R0 change record to describe file-scoped allowlist behavior.
- Reduced `StatusCommandServices` to callbacks that still need facade-owned
  state or compatibility semantics.
- Switched status rendering to direct leaf-module calls for defer checks,
  owner formatting, route conflict detection, repo-root resolution, and child
  payload loading.
- Removed the `sys.modules["progress_manager"]` probe from
  `git_utils.collect_git_context()`.
- Added explicit `collect_git_context_fn` injection for runtime/execution
  context builders so existing facade patch compatibility remains intact.
- Added `docs/progress-tracker/architecture/progress-manager-module-map.md`.

## Validation

Required validation passed:

```bash
scripts/check_pm_boundary.sh
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
uv run pytest plugins/progress-tracker/tests/test_root_dashboard.py plugins/progress-tracker/tests/test_status_linked_summary.py plugins/progress-tracker/tests/test_summary_writeback.py plugins/progress-tracker/tests/test_progress_ui_status.py -q
```

Full regression validation:

```bash
uv run pytest plugins/progress-tracker/tests -q
```

Result: `1077 passed, 1 warning`.

## Rollback Steps

Revert this cleanup commit to restore the prior F20 Round 0-1 implementation.

## Residual Risk

The allowlist remains file-scoped until the Final round. New reverse imports in
allowlisted files are suppressed by design, so the allowlist should remain small
and should be removed as each legacy module is cleaned up.
