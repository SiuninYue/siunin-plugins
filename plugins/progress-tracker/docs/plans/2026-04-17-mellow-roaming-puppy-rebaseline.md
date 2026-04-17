# Rebaseline Plan: mellow-roaming-puppy (2026-04-17)

## Goal

Rebaseline execution of [2026-04-09-mellow-roaming-puppy.md](./2026-04-09-mellow-roaming-puppy.md) against current repository reality, then continue delivery without redoing completed work.

## Why Rebaseline

- The original plan was written on 2026-04-09 and execution was interrupted by additional RouteV1 features (F20-F24).
- Core files (especially `hooks/scripts/progress_manager.py`) continued to evolve after PR-3 landed.
- Plan checkboxes are no longer a reliable source of truth for implementation status.

## Current Baseline (as of 2026-04-17)

- Project status: `20/27` completed.
- Completed in this session:
  - Closed F10 (`evaluator_gate`) via `/prog done`.
  - Fixed F10 acceptance command path drift (plugin-root relative path).
- Pending feature set:
  - F11 `review_router`
  - F12 `ship_check`
  - F13 `sprint_ledger`
  - F14 `wf_state_machine + wf_auto_driver + hook`
  - F25/F26/F27 follow-up improvements (post-RouteV1)

## Legacy PR Mapping (Old Plan -> Current Reality)

| Legacy PR in 2026-04-09 plan | Current feature(s) | Status | Evidence |
|---|---|---|---|
| PR-1 `/prog-start` cleanup | F8 | Done | Feature closed in progress state |
| PR-2 `set-finish-state` gate | F9 | Done | Feature closed in progress state |
| PR-3 `evaluator_gate` + schema 2.1 | F10 | Done | Commits `356cfb1`, `067cafb`; F10 closed on 2026-04-17 |
| PR-4 `review_router` | F11 | Pending | Not implemented |
| PR-5 `ship_check` | F12 | Pending | Not implemented |
| PR-6 `sprint_ledger` | F13 | Pending | Not implemented |
| PR-7 `wf_state_machine` + `wf_auto_driver` | F14 | Pending | Not implemented |

## Conflict Audit Summary

- Post-PR-3 changes touched `progress_manager.py` (F22/F23/F24 path).
- Targeted regression matrix executed:
  - `pytest -q tests/test_evaluator_gate.py`
  - `pytest -q tests/test_schema_2_1_migration.py`
  - `pytest -q tests/test_parent_writeback.py`
  - `pytest -q tests/test_scope_fail_closed.py`
  - `pytest -q tests/test_dispatch_child_feature.py`
- Result: `46 passed` (no functional conflict detected in covered areas).

## Behavioral Decision (Recorded)

- Enforce strict evaluator gate behavior:
  - If `quality_gates.evaluator.status != "pass"`: block `/prog done` (exit code `6`).
  - This includes missing/implicit evaluator runs (e.g. `pending`).
- Rationale: align code behavior with the optimized PR-3 gate definition and avoid silent closeout without independent evaluation evidence.

## Execution Batches

### Batch 0 (Completed in this session)

- [x] Reconcile old plan with current feature map.
- [x] Run conflict/regression audit matrix (`46 passed`).
- [x] Fix F10 acceptance command path drift:
  - `pytest -q plugins/progress-tracker/tests/test_evaluator_gate.py`
  - -> `pytest -q tests/test_evaluator_gate.py`
- [x] Execute closeout:
  - `prog --project-root plugins/progress-tracker done --run-all --skip-archive`
  - F10 closed successfully.

### Batch 1 (Next): F11 `review_router`

- [ ] Add failing tests for review lane routing contract.
- [ ] Implement `hooks/scripts/review_router.py`.
- [ ] Integrate route initialization + `cmd_done` review gate.
- [ ] Update `skills/feature-complete/SKILL.md` review lane instructions.
- [ ] Run targeted tests and close F11.

### Batch 2 (After F11): F12 `ship_check`

- [ ] Add `ship_check` contract tests.
- [ ] Implement ship gate and wire into `/prog done`.
- [ ] Add docs-sync evidence validation path.
- [ ] Run targeted tests and close F12.

### Batch 3 (After F12): F13 `sprint_ledger`

- [ ] Add ledger tests and schema contract coverage.
- [ ] Implement `sprint_ledger.py` and persistence hooks.
- [ ] Integrate with planning/execution workflow artifacts.
- [ ] Run targeted tests and close F13.

### Batch 4 (After F13): F14 `wf_state_machine + wf_auto_driver`

- [ ] Add FSM and auto-driver tests.
- [ ] Implement state machine + driver modules.
- [ ] Wire hook entrypoints for automatic progression.
- [ ] Run full regression and close F14.

## Exit Criteria for This Rebaseline

- F11/F12/F13/F14 all closed in progress tracker.
- `/prog done` gates align with implemented policy and tests.
- Remaining follow-ups (F25/F26/F27) tracked as separate post-hybrid improvements.
