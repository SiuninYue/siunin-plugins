# F20 Round 1: Extract summary_projector.py + status_commands.py

**Change ID**: 20260603-summary-status-r1-f20a  
**Date**: 2026-06-03  
**Feature**: F20 — progress_manager.py facade rounds

---

## Problem

`progress_manager.py` contained a 300+ line status/summary projection cluster
and a 300+ line status display cluster that had no business living in the
entrypoint/shim layer. These are distinct read-path concerns that follow the
modularisation boundary rules defined in `module-boundaries.md`.

---

## Extracted Modules

### `hooks/scripts/summary_projector.py` (new)

Owns the status summary projection read path (20 functions):

| Function | Purpose |
|---|---|
| `_read_json_dict` | JSON object reader with graceful failure |
| `_status_source_snapshot` | File fingerprint for drift detection |
| `_status_summary_source_fingerprint` | Aggregate source fingerprints |
| `_load_progress_data_for_summary` | Progress JSON loader with schema defaults |
| `_format_relative_time_for_summary` | Relative time formatting for display |
| `_normalize_feature_stage_for_summary` | Feature stage normalization |
| `_stage_label_for_summary` | Localized stage label lookup |
| `_determine_next_action_for_summary` | Next action computation |
| `_check_plan_health_for_summary` | Plan path/document health check |
| `_check_risk_blocker_for_summary` | Bug risk/blocker evaluation |
| `_load_recent_snapshot_for_summary` | Checkpoint snapshot field builder |
| `_build_status_summary_core` | Core summary field computation |
| `_extract_projection_source_fingerprint` | Extract persisted fingerprint |
| `_projection_has_required_core_fields` | Projection schema validation |
| `_projection_needs_rebuild` | Cache staleness check |
| `_legacy_summary_migration_info` | Legacy migration metadata |
| `_resolve_status_summary_target_root` | Target root resolution |
| `get_status_summary_projection_path` | Projection path resolver (public) |
| `_build_status_summary_projection` | Projection rebuild + persist |
| `load_status_summary_projection` | Main public entry point |

Injected callbacks (to avoid importing `progress_manager`):
- `apply_schema_defaults_fn`
- `load_checkpoints_fn`
- `validate_plan_path_fn`
- `validate_plan_document_fn`

### `hooks/scripts/status_commands.py` (new)

Owns status display commands (4 functions + 1 dataclass):

| Item | Purpose |
|---|---|
| `StatusCommandServices` | Dataclass bundling all injected callbacks |
| `_build_status_handoff_block` | Context handoff block builder |
| `_display_root_dashboard` | Monorepo parent dashboard renderer |
| `_get_stale_bugs` | Stale P0/P1 bug scanner |
| `status` | Main `prog status` command |

Directly imports from `route_commands`, `route_sync`, `git_utils`,
`progress_prompt_builders`, `summary_projector` — no reverse dependency on
`progress_manager`.

---

## Facade Wrappers

All 24 extracted functions remain accessible via `progress_manager` through
thin facade wrappers that delegate to the submodules. A helper factory
`_make_status_command_services()` wires all required callbacks:

```python
def _make_status_command_services():
    from status_commands import StatusCommandServices
    return StatusCommandServices(
        load_progress_json_fn=load_progress_json,
        find_project_root_fn=find_project_root,
        ...
    )
```

Public functions that tests access directly (`load_status_summary_projection`,
`get_status_summary_projection_path`, `status`) retain `is_wrapper = True`
markers.

---

## Validation

- `bash scripts/check_pm_boundary.sh` — PASS
- `python3 hooks/scripts/generate_prog_docs.py --check` — PASS
- `uv run pytest tests/test_root_dashboard.py tests/test_status_linked_summary.py tests/test_summary_writeback.py tests/test_progress_ui_status.py -q` — **50 passed**
- `progress_manager.py` line count: 9231 (well within 10,000 line budget)

---

## Rollback Steps

```bash
git revert HEAD  # reverts the Round 1 commit
```

This removes `summary_projector.py` and `status_commands.py` and restores the
original implementations in `progress_manager.py`.
