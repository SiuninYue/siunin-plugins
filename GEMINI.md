# Claude-Plugins Project Agent Rules

## Scope

- These rules apply only to this repository: `/Users/siunin/Projects/Claude-Plugins`.
- These are project-level rules, not global machine/user rules.

## Rule Sync Contract

- `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` must stay identical in policy intent.
- Any rule change must update all three files in the same commit.

## Git/GitHub Conventions

- For this environment, commands starting with `gh` should run with elevated host permissions.
- Prefer SSH Git remotes: `git@github.com:<owner>/<repo>.git`.

## Progress Tracker Modularization Boundary

Applies to: `plugins/progress-tracker/**`

- Follow:
  - `plugins/progress-tracker/docs/progress-tracker/architecture/module-boundaries.md`
- New business logic must be implemented in submodules under:
  - `plugins/progress-tracker/hooks/scripts/*.py`
- `progress_manager.py` is an entrypoint/shim layer. It may contain:
  - CLI argument parsing and command dispatch
  - Thin wrappers that delegate into submodules
  - Backward-compat export shims with `is_wrapper = True`
- Submodules must not import `progress_manager` (no reverse dependency).
- If submodules need state/locks/IO helpers from `progress_manager`, use callback injection.

## Required Checks For Progress Tracker Changes

When a change touches `plugins/progress-tracker/**` or these rule files:

- Run `scripts/check_pm_boundary.sh`
- Run `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check`

Fail-closed policy: if checks fail, do not merge.
