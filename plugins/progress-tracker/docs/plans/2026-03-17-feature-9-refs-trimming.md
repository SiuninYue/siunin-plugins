# Feature 9 Plan: refs 智能裁剪

**Feature ID:** 9
**Name:** refs 智能裁剪
**Complexity:** 18 (Standard)
**Workflow:** plan_execute

## Goal

Guarantee update refs behavior is safe and deterministic:
- auto-attach refs from feature contracts when no manual refs are provided;
- capture overflow refs instead of silently dropping;
- protect manually provided refs from auto-injection side effects.

## Tasks

1. Add refs normalization + trimming helpers in `progress_manager.py`.
2. Apply helper pipeline inside `add_update()` for both auto and manual refs inputs.
3. Persist overflow metadata (`refs_overflow`, `refs_overflow_count`) when trimming occurs.
4. Surface overflow summary in `list_updates` output without breaking existing format.
5. Add regression tests for:
   - auto refs injection;
   - overflow capture path;
   - manual refs protection path.

## Acceptance Mapping

- `pytest tests/test_feature_contract_readiness.py -q -k "refs"` validates auto refs + overflow/manual protections.
- `pytest tests/test_progress_manager.py -q -k "add_update or refs or updates"` validates CLI/path-level update handling.
- `python3 hooks/scripts/progress_manager.py --project-root . list-updates --limit 5` validates runtime output path remains stable.

## Risks

- Introducing overflow fields could break consumers that assume update objects only contain legacy keys.
- Ref ordering changes could affect snapshots if tests rely on stable sequence.
