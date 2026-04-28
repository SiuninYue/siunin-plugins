# Plan: F6 Harden command lifecycle boundaries and architecture immutability guard

**Feature**: F6 "Harden command lifecycle boundaries and architecture immutability guard"
**Complexity**: 12 (simple / direct_tdd)
**Created**: 2026-04-28

## Goal

所有现有生命周期边界契约测试均已通过（53 tests green）。本计划唯一的缺口是：  
第 3 个验收场景 "Validate done flow does not mutate architecture.md" 没有对应的正式测试和运行时守卫。

## Acceptance Mapping

| Acceptance Scenario | Covered By |
|---|---|
| closeout contract tests pass | `test_feature_complete_closeout_contract.py` (4 tests) — already green |
| workflow state tests pass | `test_workflow_state.py` + `test_wf_state_machine.py` (49 tests) — already green |
| done flow does not mutate architecture.md | **NEW** guard in `archive_feature_docs` + **NEW** tests in `test_cmd_done_cleanup_integration.py` |

## Scope

**In-scope:**
- Add `_IMMUTABLE_PROTECTED_FILES` constant + `_is_immutable_protected()` helper in `progress_manager.py`
- Apply guard in `archive_feature_docs()` at both file-move sites (plan_path route + glob route)
- Add 2 tests to `test_cmd_done_cleanup_integration.py`

**Out-of-scope:**
- Changes to SKILL.md content
- Changes to workflow state machine
- Any other test files

## Tasks

### T1 — RED: Write guard-branch test (fails before implementation)

**File**: `plugins/progress-tracker/tests/test_cmd_done_cleanup_integration.py`

Add test `test_archive_docs_skips_protected_architecture_md`:
- Set `_PROJECT_ROOT_OVERRIDE` to `tmp_path`
- Create `docs/plans/architecture.md` in `tmp_path` (simulates mis-configured plan_path)
- Set feature `plan_path = "docs/plans/architecture.md"` via progress.json
- Call `progress_manager.archive_feature_docs(feature_id)`
- Assert: `docs/plans/architecture.md` still exists (not moved)
- Assert: `result["skipped_files"]` contains an entry referencing "architecture.md"

**Expected**: RED before guard implementation.

### T2 — GREEN: Implement guard in progress_manager.py

**File**: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

1. Add module-level constant (near other constants, after imports):
   ```python
   # Files that must never be moved or deleted by archive flows
   _IMMUTABLE_PROTECTED_FILES: frozenset[str] = frozenset({"architecture.md"})
   ```

2. Add helper function:
   ```python
   def _is_immutable_protected(path: Path) -> bool:
       """Return True if this file is protected from archival mutations."""
       return path.name in _IMMUTABLE_PROTECTED_FILES
   ```

3. In `archive_feature_docs()`, apply guard at **plan_path route** (before `shutil.move`):
   ```python
   if _is_immutable_protected(plan_file):
       logger.warning("Skipping protected file from archival: %s", plan_file)
       result["skipped_files"].append(f"Protected: {plan_path_from_feature}")
       # fall through to glob patterns — do not move
   else:
       shutil.move(str(plan_file), str(dst_file))
       result["archived_files"].append(...)
   ```

4. In `archive_feature_docs()`, apply guard at **glob route** (inside `for src_file in matching_files`):
   ```python
   if _is_immutable_protected(src_file):
       logger.warning("Skipping protected file from archival: %s", src_file)
       result["skipped_files"].append(f"Protected: {src_file.name}")
       continue
   ```

After T2: T1 test turns GREEN.

### T3 — Functional test: done flow preserves architecture.md

**File**: `plugins/progress-tracker/tests/test_cmd_done_cleanup_integration.py`

Add test `test_cmd_done_preserves_architecture_md`:
- Using `seeded_done_env` fixture (already provides fully-gated env)
- Create `docs/progress-tracker/architecture/architecture.md` in `seeded_done_env` tmp_path
- Call `cmd_done()`
- Assert: `architecture.md` still exists, content unchanged

**Expected**: GREEN immediately (documents the invariant at functional level).

### T4 — Verify: Run all F6 target tests

```bash
pytest -q \
  plugins/progress-tracker/tests/test_feature_complete_closeout_contract.py \
  plugins/progress-tracker/tests/test_workflow_state.py \
  plugins/progress-tracker/tests/test_wf_state_machine.py \
  plugins/progress-tracker/tests/test_cmd_done_cleanup_integration.py \
  --tb=short
```

Expected: all pass (55+ tests green).

## Risks

- `seeded_done_env` fixture uses single `_FEATURE_ID=25`; new tests reuse same fixture — no conflict expected
- Guard uses `path.name` match (filename only) — not full path — to catch any location where architecture.md might appear

## Implementation Order

RED (T1) → GREEN-impl (T2) → Functional-GREEN (T3) → Verify (T4)
