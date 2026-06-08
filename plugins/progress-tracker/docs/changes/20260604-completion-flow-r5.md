# Change: Round 5 — Completion Pipeline Extraction to `completion_flow.py`

**Change ID:** `20260604-completion-flow-r5`  
**Date:** 2026-06-05  
**Feature ID:** F24  
**Round:** 5  

## Summary

Extracted the completion pipeline from `progress_manager.py` into a new dedicated module `completion_flow.py`. This is Round 5 of the facade convergence series (Rounds 0–4 extracted status/readiness/feature/next-feature clusters).

## What Was Extracted

19 functions moved to `completion_flow.py`:

| Function | Responsibility |
|----------|---------------|
| `cmd_done` | Main completion entry point, all acceptance gates |
| `complete_feature` | High-level completion orchestration |
| `_run_done_preflight` | Batch-validate all 9 completion gates |
| `_print_preflight_report` | Formatted gate report output |
| `_validate_done_preconditions` | Phase/feature existence gate |
| `_validate_completion_reconcile` | Reconcile drift gate |
| `_validate_completion_plan_document` | Plan document validity gate |
| `_finalize_completion_state_in_memory` | In-memory feature state finalization |
| `_record_feature_completed_event` | Audit event emission |
| `_append_capability_memory` | Project memory append |
| `_run_acceptance_tests` | Acceptance test execution pipeline |
| `_cleanup_old_done_reports` | Test report rotation |
| `_save_done_test_report` | Acceptance report persistence |
| `_format_failure_reason` | Failure summary formatting |
| `_run_post_done_cleanup` | Post-done worktree/branch cleanup |
| `_build_done_handoff_block` | Done handoff block rendering |
| `_build_project_completion_summary` | Project completion summary |
| `complete_feature_ai_metrics` | AI metrics finalization |
| `save_archive_record` | Archive record persistence |

Plus helper functions: `_is_project_fully_completed`, `_iso_now`, `_parse_iso_timestamp`, `_clear_feature_finish_pending`, `_extract_test_step_command`, `_is_executable_test_step`, `_extract_relative_path_candidates_from_command`, `_resolve_acceptance_command_cwd`.

Also moved constants: `FINISH_PENDING_STATE`, `AcceptanceTestResult` dataclass.

## Architecture

### `CompletionFlowServices` Injection Interface

All service-level operations are injected via a `CompletionFlowServices` dataclass rather than direct global calls. This prevents any reverse import of `progress_manager`.

Key injected callbacks: `load_progress_json_fn`, `save_progress_json_fn`, `find_project_root_fn`, `generate_progress_md_fn`, `save_progress_md_fn`, `record_sprint_artifact_fn`, `require_sprint_contract_fn`, `notify_parent_sync_fn`, `archive_feature_docs_fn`, `collect_git_context_fn`, `get_head_commit_fn`, `analyze_reconcile_state_fn`, and others.

### Facade Wrappers

`progress_manager.py` retains thin wrappers for backward compatibility:

```python
def cmd_done(commit_hash=None, run_all=False, skip_archive=False, no_cleanup=False, check_only=False):
    return completion_flow.cmd_done(_make_completion_flow_services(), ...)
cmd_done.is_wrapper = True
```

### `_make_completion_flow_services()` Factory

Added a factory function in `progress_manager.py` that wires all facade-level functions and globals into a `CompletionFlowServices` instance.

## Impact

- `progress_manager.py`: 8122 → 7121 lines (−1001 lines)
- New module: `completion_flow.py` (~1280 lines)
- New test file: `tests/test_completion_flow_contract.py` (8 contract tests)
- Updated test patches: `test_cmd_done_cleanup_integration.py`, `test_auto_state_commit.py`, `test_cleanup_after_done.py`

## Test Results

- `scripts/check_pm_boundary.sh`: PASS (no reverse imports)
- `generate_prog_docs.py --check`: PASS
- `test_completion_flow_contract.py`: 8/8 PASS
- Full suite: 1095 passed, 55 warnings (baseline was 1087; +8 from new contract tests)

## Rollback

```bash
git revert <round-5-commit-hash>
```
