# Progress Tracker Module Boundaries

## Purpose

Keep `progress_manager.py` as a stable entrypoint and prevent future business-logic backflow into a monolithic file.

## Scope

- Applies to: `plugins/progress-tracker/hooks/scripts/*.py`
- Primary entrypoint: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

## Boundary Rules

1. `progress_manager.py` responsibilities are limited to:
   - CLI parser wiring
   - command dispatch
   - thin wrappers and compatibility shims (`is_wrapper = True`)
2. New business logic must live in dedicated submodules.
3. Submodules must not import `progress_manager` (no reverse dependency).
4. Cross-layer access must use explicit parameter/callback injection.
5. `progress_manager.py` line budget is hard-capped at `<= 10000`.

## Module Placement Checklist

Before adding logic:

1. Can it fit an existing module (`route_*`, `state_io`, `git_utils`, etc.)?
2. If no, create a new focused module (for example `*_commands.py` or `*_gateway.py`).
3. Add/keep a wrapper export in `progress_manager.py` only when backward compatibility requires it.
4. Ensure wrapper sets `is_wrapper = True` for mock/test stability.

## Validation

Run:

```bash
scripts/check_pm_boundary.sh
```

This script enforces:

- rule-file consistency (`AGENTS.md` / `CLAUDE.md` / `GEMINI.md`)
- `progress_manager.py` line budget
- no submodule reverse-import of `progress_manager`
