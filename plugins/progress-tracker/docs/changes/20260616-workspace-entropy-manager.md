# Workspace Entropy Manager (F25)

**Date:** 2026-06-16
**Feature:** PT-F25
**Component:** `hooks/scripts/workspace_entropy.py`

## Shipped Commands

- `prog entropy-check [--json]` — Inspect workspace entropy without mutation. Returns dirty_changes, branches, routes, worktrees, and decision (ok | safe_fix_available | block).
- `prog entropy-fix [--safe] [--apply] [--json]` — Apply green actions (delete merged branches). Red blocks always abort with `reason=workspace_entropy_red`.

## Green / Yellow / Red Policy

- **Green (auto):** Delete local merged branches not protected and not checked out. Auto-commit tracker state files (whitelisted prefixes only).
- **Yellow (reserved):** Named stash / quarantine branch for ambiguous source edits (not yet implemented — reserved for future iteration).
- **Red (always block):** Deletions of unmerged source files. Force-push, hard-reset, discard uncommitted tracked source changes.

## next_feature Integration

`prog next` now runs `run_safe_entropy_preflight` before work-item selection. Red entropy blocks next_feature with `reason=workspace_entropy_red`. Non-red entropy does not block.

## Test Commands

```bash
uv run pytest tests/test_workspace_entropy.py -q
uv run pytest tests/test_next_feature_entropy_preflight.py -q
uv run pytest tests/ -q
scripts/check_pm_boundary.sh
python3 hooks/scripts/generate_prog_docs.py --check
```

## Rollback Strategy

Revert the F25 commits. Remove `entropy-check` and `entropy-fix` parser entries from `progress_manager.py`. Remove `entropy_preflight_fn` from `NextFeatureCommandServices` and its wire-up in progress_manager.py. The `workspace_entropy.py` module can be deleted. Audit trail (entropy-fix output) is stdout-only and needs no rollback.
