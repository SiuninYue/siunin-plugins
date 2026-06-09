# F26 Plan: Round 6 — Backlog and Intake Mutation Commands Extraction

**Feature:** F26 "progress_manager facade 收口 Round 6：Backlog and Intake Mutation Commands 外移"
**Complexity:** standard (score 42, sonnet)
**Parent plan:** `docs/plans/2026-06-03-progress-manager-facade-rounds.md`

## Goal

Extract 9 backlog/intake mutation functions from `progress_manager.py` into a new `work_item_commands.py` module, following the established injection pattern from Rounds 1-5. Also extract `add_task_item` (called by `smart_intake`) and the related helper `_push_bug_to_routing_queue` to keep the module self-contained.

Reduce `progress_manager.py` line count by ≥ 300 lines vs F24 baseline of 7121.

## Target Functions

| Function | Lines in PM | Move To |
|---|---|---|
| `add_update` | 4726–4821 | work_item_commands |
| `list_updates` | 4824–4855 | work_item_commands |
| `add_retro` | 4858–4906 | work_item_commands |
| `set_feature_owner` | 4909–4937 | work_item_commands |
| `add_feature` | 4940–4986 | work_item_commands |
| `update_feature` | 4989–5030 | work_item_commands |
| `defer_features` | 5033–5101 | work_item_commands |
| `resume_deferred_features` | 5104–5143 | work_item_commands |
| `add_task_item` | 5305–5395 | work_item_commands |
| `smart_intake` | 5402–5541 | work_item_commands |
| `_push_bug_to_routing_queue` | 5197–5256 | work_item_commands |

**Helpers to move (used only by target functions):**
- `_next_update_id` (4682–4690)
- `_collect_auto_update_refs` (4700–4715)
- `_compact_update_refs` (4718–4722)
- `_apply_imported_feature_contract` (1300–1305)
- `_SMART_INTAKE_PRIORITY_MAP` constant (5398–5399)

**Constants to move to `work_item_commands.py` (re-exported back in PM):**
- `WORK_ITEM_TAXONOMY`
- `WORKFLOW_PROFILE_VALUES`
- `WORKFLOW_PROFILE_DEFAULT`
- `UPDATE_CATEGORIES`
- `UPDATE_SOURCES`
- `UPDATE_REFS_INLINE_LIMIT`

## Dependency Analysis

### Direct leaf-module imports in `work_item_commands.py` (no reverse deps):
```python
from state_io import (
    OWNER_ROLES,
    _normalize_optional_string,
    _clear_feature_defer_state,
    _default_owners,
    _normalize_feature_owners,
    _normalize_feature_contract,
    _iso_now,
    _normalize_ref_tokens,
)
from progress_prompt_builders import _is_deferred as _is_feature_deferred
from contract_importer import ContractImporter, ContractImportError
from prog_paths import find_project_root
```

### Injected via `WorkItemCommandsServices` (to avoid reverse deps):
```python
load_progress_json_fn
save_progress_json_fn
generate_progress_md_fn
save_progress_md_fn
update_runtime_context_fn    # for defer_features, resume_deferred_features
notify_parent_sync_fn        # for add_feature
add_bug_internal_fn          # for smart_intake commit="bug"
```

Note: `_push_bug_to_routing_queue` is moved INTO `work_item_commands.py` so `smart_intake_command` calls it directly (no injection needed for this helper).

Note: `add_task_item_command` is in the same module, so `smart_intake_command` calls it directly.

## Implementation Plan

### Task 1: Write `hooks/scripts/work_item_commands.py`

Structure:
```
Module docstring
Imports (stdlib + leaf modules only)
Constants block (WORK_ITEM_TAXONOMY, etc.)
_SMART_INTAKE_PRIORITY_MAP
WorkItemCommandsServices dataclass
Helper functions (_next_update_id, _collect_auto_update_refs, _compact_update_refs,
                  _apply_imported_feature_contract, _push_bug_to_routing_queue)
Extracted command functions (each takes `svc: WorkItemCommandsServices` as first arg)
```

Naming convention: match `feature_commands.py` pattern — function named
`<original_name>_command(svc, ...)`.

### Task 2: Rewrite `progress_manager.py` facade section

1. Replace constant definitions (lines ~271-282) with:
   ```python
   from work_item_commands import (
       WORK_ITEM_TAXONOMY, WORKFLOW_PROFILE_VALUES, WORKFLOW_PROFILE_DEFAULT,
       UPDATE_CATEGORIES, UPDATE_SOURCES, UPDATE_REFS_INLINE_LIMIT,
   )
   ```

2. Remove `_apply_imported_feature_contract` definition (lines 1300-1305).

3. Remove `_next_update_id`, `_collect_auto_update_refs`, `_compact_update_refs`,
   `_push_bug_to_routing_queue`, `_SMART_INTAKE_PRIORITY_MAP` definitions.

4. Remove the bodies of all 10 target functions (keep signatures as wrappers).

5. Add factory:
   ```python
   def _make_work_item_commands_services():
       import work_item_commands
       return work_item_commands.WorkItemCommandsServices(
           load_progress_json_fn=load_progress_json,
           save_progress_json_fn=save_progress_json,
           generate_progress_md_fn=generate_progress_md,
           save_progress_md_fn=save_progress_md,
           update_runtime_context_fn=_update_runtime_context,
           notify_parent_sync_fn=_notify_parent_sync,
           add_bug_internal_fn=_add_bug_internal,
       )
   ```

6. Each function body becomes a thin wrapper:
   ```python
   def add_update(category, summary, ...):
       import work_item_commands
       return work_item_commands.add_update_command(
           _make_work_item_commands_services(), category, summary, ...
       )
   add_update.is_wrapper = True
   ```

### Task 3: Write unit tests in `tests/test_work_item_commands.py`

Cover:
- `add_update_command`: valid input, invalid category, invalid source, empty summary
- `list_updates_command`: empty, all, with limit
- `add_retro_command`: valid, missing feature_id
- `set_feature_owner_command`: valid assignment, clear owner (None), invalid role
- `add_feature_command`: creates feature with correct ID
- `update_feature_command`: updates name and test_steps
- `defer_features_command`: single feature, all pending, clears active
- `resume_deferred_features_command`: by group, resume_all
- `add_task_item_command`: valid, invalid priority, empty description
- `smart_intake_command`: preview mode, commit=bug/task/feature/update, low confidence

All tests use mock `WorkItemCommandsServices` — no filesystem I/O.

### Task 4: Run checks

```bash
bash scripts/check_pm_boundary.sh
python3 hooks/scripts/generate_prog_docs.py --check
uv run pytest tests/ -q
```

### Task 5: Verify line count reduction

```bash
wc -l hooks/scripts/progress_manager.py
# Must be <= 6821 (7121 - 300)
```

## Acceptance Criteria

1. `work_item_commands.py` exists with all 9 required functions as `*_command` variants
2. `progress_manager.py` facade wrappers call `work_item_commands.*_command` with injected services
3. `bash scripts/check_pm_boundary.sh` passes (no reverse imports)
4. `python3 hooks/scripts/generate_prog_docs.py --check` passes
5. `uv run pytest tests/ -q` passes (zero regressions)
6. `progress_manager.py` line count ≤ 6821

## Risk Notes

- `_apply_imported_feature_contract` currently at line 1300 (before the extract range); verify no other callers outside target functions before removing.
- Constants `WORKFLOW_PROFILE_VALUES` / `WORKFLOW_PROFILE_DEFAULT` used in `main()` argparse; re-export from `work_item_commands` in progress_manager to maintain compatibility.
- `_is_feature_deferred` remains in progress_manager (used in 8+ non-target sites); work_item_commands imports `_is_deferred` from `progress_prompt_builders` directly.

## Implementation Deviations

1. **`find_project_root`**: Instead of importing it directly, it was added to `WorkItemCommandsServices` and injected at runtime to improve module isolation and testability.
2. **`_iso_now`**: Implemented locally inside `work_item_commands.py` rather than being imported, making the module more self-contained.
