# F24: progress_manager Facade Round 5 — Completion Flow Extraction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the completion pipeline from `progress_manager.py` into a dedicated `completion_flow.py` collaborator module. The facade retains thin wrappers with `is_wrapper = True`. No submodule may reverse-import `progress_manager`.

**Architecture:**
- New module: `completion_flow.py` — owns all completion pipeline logic
- `CompletionFlowServices` dataclass — injectable callbacks for facade-level state/git/doc operations
- Optional sub-split (do NOT pre-split unless a single function exceeds 300 lines cleanly): `acceptance_runner.py` for `_run_acceptance_tests` cluster
- Facade `progress_manager.py` retains only wrapper shims

**Working directory for all commands:** `/Users/siunin/Projects/Claude-Plugins/.claude/worktrees/feature-24-completion-flow/plugins/progress-tracker`

## Target Functions to Extract

Functions to move to `completion_flow.py`:

| Function | Current line | Size (approx) | Notes |
|----------|-------------|---------------|-------|
| `complete_feature_ai_metrics` | 4062 | ~40 lines | uses load/save progress + generate md |
| `save_archive_record` | 4129 | ~33 lines | uses load/save progress |
| `_run_acceptance_tests` | 4303 | ~100 lines | uses prog subprocess calls |
| `_cleanup_old_done_reports` | 4403 | ~11 lines | pure file IO |
| `_save_done_test_report` | 4414 | ~43 lines | uses find_project_root |
| `_format_failure_reason` | 4457 | ~17 lines | pure logic |
| `_validate_done_preconditions` | 4474 | ~38 lines | uses load_progress_json |
| `_validate_completion_reconcile` | 4512 | ~20 lines | pure validation |
| `_validate_completion_plan_document` | 4532 | ~45 lines | uses find_project_root + git |
| `_finalize_completion_state_in_memory` | 4578 | ~49 lines | moves out; avoids reverse import |
| `_record_feature_completed_event` | 4629 | ~11 lines | moves out; uses record_feature_state_event_fn |
| `_append_capability_memory` | 4641 | ~29 lines | moves out; project memory append |
| `_run_post_done_cleanup` + git helpers | 4671 | ~60 lines | moves post-done cleanup and git wrapper shims |
| `_build_done_handoff_block` + summary | 3184 | ~20 lines | moves done console output formatting functions |
| `_run_done_preflight` | 4834 | ~117 lines | uses multiple collectors |
| `_print_preflight_report` | 4951 | ~39 lines | pure output |
| `cmd_done` | 4990 | ~266 lines | main entry; uses many injected fn |
| `complete_feature` | 5475 | ~94 lines | orchestrates full completion |

**Already a wrapper / Keep in place (Do NOT move):**
- `archive_feature_docs` (4116) — already delegates to `doc_generator`; add/keep `is_wrapper = True`
- `_is_immutable_protected` (4103) — keep in facade (used by `archive_feature_docs` wrapper)
- `_close_current_task` + standalone/feature-bound task helpers (4736-4831) — keep in facade (task domain logic)
- `_collect_ship_signals` (5256) — Keep as wrapper in facade to minimize regression risk on `cmd_ship_check`.

## Module Constants & Optional Import Guards Resettlement

To keep `completion_flow.py` self-contained and avoid reverse-importing `progress_manager`:
1. **Optional Import Guards**: Re-establish `SPRINT_LEDGER_AVAILABLE` and `REVIEW_ROUTER_AVAILABLE` dynamically at the top of `completion_flow.py` using `try/except ImportError` blocks.
2. **State Constant**: Define `FINISH_PENDING_STATE` directly inside `completion_flow.py`. In `progress_manager.py`, import it: `from completion_flow import FINISH_PENDING_STATE` to avoid duplication.
3. **Helpers Resettlement**: 
   - Move the implementation of `_is_project_fully_completed` (currently line 2479) to `completion_flow.py`. In facade, re-import it: `from completion_flow import _is_project_fully_completed`.
   - Preserve the existing facade patch seam for `collect_git_context` and `_get_head_commit` by injecting them through `CompletionFlowServices` as `collect_git_context_fn` and `get_head_commit_fn`. Do not call `git_utils.collect_git_context(...)` or `git_utils._get_head_commit(...)` directly from the extracted `cmd_done` / `complete_feature` flow.

## Patch Seams & Test Adaptation

Since the core pipeline functions (e.g. `_run_acceptance_tests`, `_save_done_test_report`, `_run_post_done_cleanup`, `_finalize_completion_state_in_memory`) are being moved from `progress_manager.py` to `completion_flow.py`, any existing tests that patch these functions on `progress_manager` will fail because the delegated wrapper will not hit the mocked facade functions.

Facade-level git helper seams are preserved by service injection. Existing tests that patch `progress_manager.collect_git_context` or `progress_manager._get_head_commit` should continue to work after extraction, because `_make_completion_flow_services()` will pass those facade wrappers into `completion_flow`.

**Action Required**: Update existing test files (specifically `tests/test_cmd_done_cleanup_integration.py` and `tests/test_auto_state_commit.py`) to mock/patch the target functions on the `completion_flow` module instead of `progress_manager`:
* Change `patch("progress_manager._run_post_done_cleanup")` to `patch("completion_flow._run_post_done_cleanup")`
* Change `patch("progress_manager._run_acceptance_tests")` to `patch("completion_flow._run_acceptance_tests")`
* Change `patch("progress_manager._finalize_completion_state_in_memory")` to `patch("completion_flow._finalize_completion_state_in_memory")`
* Change `patch("progress_manager._save_done_test_report")` to `patch("completion_flow._save_done_test_report")`

## `CompletionFlowServices` Interface

```python
@dataclass
class CompletionFlowServices:
    load_progress_json_fn: Callable[[], Optional[dict]]
    save_progress_json_fn: Callable[[dict], None]
    find_project_root_fn: Callable[[], Path]
    generate_progress_md_fn: Callable[[dict], str]
    save_progress_md_fn: Callable[[str], None]
    record_sprint_artifact_fn: Callable[..., None]
    require_sprint_contract_fn: Callable[[dict], None]
    notify_parent_sync_fn: Callable[[str], None]  # Signature fixed to receive string event parameter
    repo_root: Optional[Path] = None
    record_feature_state_event_fn: Callable[..., None] = None
    update_runtime_context_fn: Callable[[dict, str], None] = None
    auto_state_commit_fn: Callable[[str, str], None] = None
    archive_current_progress_fn: Callable[..., Any] = None
    reset_active_progress_fn: Callable[[dict], None] = None
    archive_feature_docs_fn: Callable[[int, str], Dict[str, Any]] = None
    # Added to decouple from facade context and avoid reverse imports
    get_next_feature_fn: Callable[[], Optional[dict]] = None
    validate_plan_document_fn: Callable[[str], dict] = None
    collect_git_context_fn: Callable[[], Dict[str, Any]] = None
    get_head_commit_fn: Callable[[], Optional[str]] = None
```

## Execution Preconditions

- Rounds 0–4 merged; `work_item_selector.py`, `next_feature_commands.py`, `feature_commands.py`, `readiness_validator.py`, `summary_projector.py`, `status_commands.py` all exist.
- `scripts/check_pm_boundary.sh` passes on the current branch before any extraction begins.
- pytest baseline: `uv run pytest tests/ -q` must green-pass before extraction.

## Tasks

### Task 1: Baseline verification

- [ ] Run `scripts/check_pm_boundary.sh` from the working directory — must pass with zero errors.
- [ ] Run `uv run pytest tests/ -q` — record baseline pass count.
- [ ] Note the current `wc -l hooks/scripts/progress_manager.py` line count.

### Task 2: Write RED tests

Write targeted tests for the extracted functions **before** moving them. These tests import from `completion_flow` (not yet created) and should fail with `ModuleNotFoundError` until Task 3.

Create `tests/test_completion_flow_contract.py` with 8 targeted tests:

- [ ] `test_complete_feature_ai_metrics_records_duration` — call `complete_feature_ai_metrics` with a feature that has `ai_metrics.started_at`; assert `finished_at` and `duration_seconds` are set.
- [ ] `test_save_archive_record_writes_archive_info` — provide a feature stub; assert `archive_info` dict is written back.
- [ ] `test_run_acceptance_tests_passes_for_vacuous_feature` — provide feature with empty `test_steps`; assert `(True, [])` returned.
- [ ] `test_format_failure_reason_returns_non_empty_for_failures` — pass a failed `AcceptanceTestResult`; assert non-empty string.
- [ ] `test_validate_done_preconditions_blocks_missing_feature` — call with data that has no `current_feature_id`; assert `(False, ...)`.
- [ ] `test_cmd_done_check_only_returns_zero_when_all_pass` — wire stub services; assert return 0.
- [ ] `test_complete_feature_finalizes_state` — wire stub services; assert `completed_at`, `development_stage=completed`, and `integration_status` set.
- [ ] `test_cmd_done_triggers_callbacks` — mock callbacks and verify `auto_state_commit_fn` is called with correct arguments `(f"F{feature_id}", "done")` and `notify_parent_sync_fn("clear")` is invoked.

### Task 3: Create `completion_flow.py`

- [ ] Create `hooks/scripts/completion_flow.py`.
- [ ] Define `CompletionFlowServices` dataclass (see Interface Contract above).
- [ ] Implement `FINISH_PENDING_STATE` constant and dynamic import guards `SPRINT_LEDGER_AVAILABLE`, `REVIEW_ROUTER_AVAILABLE` locally at the top of `completion_flow.py`.
- [ ] Move all target functions (see table) into `completion_flow.py` with injected `services` parameter added. Include `_is_project_fully_completed` (currently line 2479) in the extraction list.
- [ ] Replace every direct call to `load_progress_json`, `save_progress_json`, `find_project_root`, `generate_progress_md`, `save_progress_md`, `record_sprint_artifact`, `require_sprint_contract`, `_notify_parent_sync`, `_update_runtime_context`, `_auto_state_commit`, `archive_current_progress`, `_reset_active_progress`, `archive_feature_docs`, `get_next_feature`, `validate_plan_document`, `collect_git_context`, `_get_head_commit` with the corresponding `services.*_fn` call or property.
- [ ] Do NOT import `progress_manager` in `completion_flow.py` — use only: `Path`, `json`, `datetime`, `sys`, `subprocess`, `dataclasses`, `typing`, and existing leaf modules (`prog_paths`, `state_io`, `sprint_ledger`, `ship_check`, `evaluator_gateway`, etc.).
- [ ] Run RED tests → they should now pass (GREEN).

### Task 4: Add facade wrappers in `progress_manager.py`

- [ ] In `progress_manager.py`, add a `_make_completion_flow_services()` factory function that returns `CompletionFlowServices` populated with the facade's own `load_progress_json`, `save_progress_json`, `find_project_root`, `generate_progress_md`, `save_progress_md`, `record_sprint_artifact`, `require_sprint_contract`, `_notify_parent_sync`, `_update_runtime_context`, `_auto_state_commit`, `archive_current_progress`, `_reset_active_progress`, `archive_feature_docs`, `get_next_feature`, `validate_plan_document`, `collect_git_context`, `_get_head_commit` and global `_REPO_ROOT`.
- [ ] Replace each extracted function body with a one-liner delegating to `completion_flow.<func>(_make_completion_flow_services(), ...)`.
- [ ] Mark every wrapper with `<func>.is_wrapper = True`.
- [ ] Ensure `archive_feature_docs` already has `is_wrapper = True` (it should from prior rounds).
- [ ] Keep `_is_immutable_protected` in the facade (it's a pure helper used by the existing `archive_feature_docs` wrapper).
- [ ] Keep `_collect_ship_signals` in facade as a wrapper (do not modify `cmd_ship_check` in facade).
- [ ] Re-import `FINISH_PENDING_STATE` and `_is_project_fully_completed` in facade: `from completion_flow import FINISH_PENDING_STATE, _is_project_fully_completed`.

### Task 5: Boundary and docs checks

- [ ] `cd /Users/siunin/Projects/Claude-Plugins/.claude/worktrees/feature-24-completion-flow && scripts/check_pm_boundary.sh` — must pass.
- [ ] `python3 hooks/scripts/generate_prog_docs.py --check` — must pass.

### Task 6: Full regression + focused tests

- [ ] `uv run pytest tests/test_completion_flow_contract.py -v` — all 8 tests green.
- [ ] Update existing regression tests (specifically in `tests/test_cmd_done_cleanup_integration.py` and `tests/test_auto_state_commit.py`) to mock/patch moved helper functions on the `completion_flow` module instead of `progress_manager` (`_run_post_done_cleanup`, `_run_acceptance_tests`, `_finalize_completion_state_in_memory`, `_save_done_test_report`). Keep existing `progress_manager.collect_git_context` / `progress_manager._get_head_commit` patches unchanged; service injection preserves those seams.
- [ ] `uv run pytest tests/test_progress_manager.py -k "done or complete_feature or archive" -q` — all pass.
- [ ] `uv run pytest tests/ -q` — full suite passes with no new failures.
- [ ] Confirm `wc -l hooks/scripts/progress_manager.py` decreased by ≥ 1000 lines vs baseline.

### Task 7: Update module map and changes index

- [ ] Update `docs/progress-tracker/architecture/progress-manager-module-map.md` to add a Round 5 row for `completion_flow.py`.
- [ ] Append one JSON record to `docs/changes/index.jsonl` with:
  - `change_id`: `20260604-completion-flow-r5`
  - `date`, `component`, `feature_id: 24`, `round: 5`
  - `summary`, `fixes` list, `touched_files`, `test_command`, `test_result`
  - `rollback_strategy`, `record_path`
- [ ] Create `docs/changes/20260604-completion-flow-r5.md` with the full change narrative.

### Task 8: Register Round 6 feature

Before closing F24, register the next facade convergence round:

- [ ] Run: `plugins/progress-tracker/prog add-feature "progress_manager facade 收口 Round 6：Backlog and Intake Mutation Commands 外移" --project-root plugins/progress-tracker` with appropriate test steps.
  - Target module: `work_item_commands.py` or `backlog_commands.py`
  - Candidate moves: `smart_intake`, `add_feature`, `update_feature`, `defer_features`, `resume_deferred_features`, `add_update`, `list_updates`, `add_retro`, `set_feature_owner`

## Acceptance Criteria

1. `completion_flow.py` exists and owns all listed target functions.
2. `progress_manager.py` contains only wrappers (`is_wrapper = True`) for the extracted functions.
3. `scripts/check_pm_boundary.sh` passes — no `completion_flow.py` reverse-imports `progress_manager`.
4. `python3 hooks/scripts/generate_prog_docs.py --check` passes.
5. Full pytest suite passes with no regressions.
6. `docs/changes/index.jsonl` has a new Round 5 record.
7. `progress-manager-module-map.md` lists Round 5 ownership.
8. Round 6 feature registered in progress.json.
