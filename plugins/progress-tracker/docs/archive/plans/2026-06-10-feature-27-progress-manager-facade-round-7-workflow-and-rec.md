# F27 Plan: Round 7 — Workflow and Reconcile Commands Extraction

**Feature:** F27 "progress_manager facade 收口 Round 7：Workflow and Reconcile Commands 外移"
**Complexity:** standard (score 42, sonnet)
**Parent plan:** `docs/plans/2026-06-03-progress-manager-facade-rounds.md`

## Goal

Extract 8 workflow-state and reconcile-diagnostic functions from `progress_manager.py`
into a new `workflow_commands.py` module, following the established injection pattern
from Rounds 1-6 (most recently `work_item_commands.py` in F26).

Decrease `progress_manager.py` line count vs F26 baseline of 6528 lines.

## Target Functions

| Function | Lines in PM | Move To |
|---|---|---|
| `analyze_reconcile_state` | 1448–1625 | workflow_commands |
| `reconcile` | 1628–1680 | workflow_commands |
| `cmd_reconcile_state` | 1824–1983 | workflow_commands |
| `set_workflow_state` | 5069–5120 | workflow_commands |
| `update_workflow_task` | 5123–5152 | workflow_commands |
| `clear_workflow_state` | 5155–5174 | workflow_commands |
| `health_check` | 5177–5250 | workflow_commands |
| `validate_plan` | 5253–5297 | workflow_commands |

**Helpers to move (used only by target functions):**
- `_collect_feature_artifact_evidence` (1368–1420) — only caller is `analyze_reconcile_state`
- `_collect_git_change_evidence` (1423–1440) — only caller is `analyze_reconcile_state`
- `_normalize_reconcile_step` (1443–1445) — only caller is `analyze_reconcile_state`
- `_replay_audit_events` (1786–1821) — only caller is `cmd_reconcile_state`

**Constants to move to `workflow_commands.py` (re-exported back in PM):**
- `RECONCILE_DIAGNOSES` (279–286)
- `RECONCILE_NEXT_STEPS` (287–293)

## Dependency Analysis

### Direct leaf-module imports in `workflow_commands.py` (no reverse deps)

```python
import git_utils
from prog_paths import get_tracker_docs_root, PROGRESS_JSON
from progress_prompt_builders import _is_deferred as _is_feature_deferred
from state_io import _normalize_context_path, compare_contexts

try:
    import audit_log
except ImportError:  # pragma: no cover - optional module
    audit_log = None

try:
    from git_validator import is_git_repository, safe_git_command
    GIT_VALIDATOR_AVAILABLE = True
except ImportError:  # pragma: no cover - optional module
    GIT_VALIDATOR_AVAILABLE = False
```

`git_utils._run_git` replaces the `progress_manager._run_git` wrapper inside
`_collect_git_change_evidence` (no test patches `progress_manager._run_git` for the
reconcile path — verified via grep).

`_normalize_context_path` / `compare_contexts` are pure functions whose canonical
definitions already live in `state_io` (both `git_utils` and `progress_manager`
just re-export them) — import the canonical versions directly.

### Injected via `WorkflowCommandsServices` (to avoid reverse deps / preserve patchability)

```python
load_progress_json_fn
save_progress_json_fn
generate_progress_md_fn
save_progress_md_fn
update_runtime_context_fn          # progress_manager._update_runtime_context
update_execution_context_fn        # progress_manager._update_execution_context
build_runtime_context_fn           # progress_manager.build_runtime_context
validate_plan_path_fn              # progress_manager.validate_plan_path
validate_plan_document_fn          # progress_manager.validate_plan_document
find_project_root_fn               # progress_manager.find_project_root (_PROJECT_ROOT_OVERRIDE-aware)
get_progress_dir_fn                # progress_manager.get_progress_dir
load_checkpoints_fn                # progress_manager.load_checkpoints
latest_checkpoint_entry_for_feature_fn  # progress_manager._latest_checkpoint_entry_for_feature
build_checkpoint_context_fn        # progress_manager._build_checkpoint_context
```

Notes:
- `validate_plan_path` and `validate_plan_document` stay in `progress_manager.py`
  (both are imported directly by `progress_ui_server.py`, `summary_projector.py`,
  `completion_flow.py`, `status_commands.py`); inject rather than duplicate.
- `_update_runtime_context` / `_update_execution_context` / `build_runtime_context`
  stay in `progress_manager.py` because `tests/test_workflow_state.py` patches
  `progress_manager.collect_git_context` and relies on these wrappers resolving
  that name at call time. Reimplementing them via `git_utils` directly inside
  `workflow_commands.py` would silently bypass that patch point.
- `_latest_checkpoint_entry_for_feature` / `_build_checkpoint_context` /
  `load_checkpoints` stay in `progress_manager.py` because they have a second
  caller outside the F27 scope (~line 3676, git-auto-preflight diagnostics).
  Inject as callbacks instead of duplicating.
- `_is_feature_deferred` → import `_is_deferred as _is_feature_deferred` from
  `progress_prompt_builders` directly (same pattern as `work_item_commands.py`).
- `_iso_now` → implement locally in `workflow_commands.py` (same deviation as F26).

## Implementation Plan

### Task 1: Write `hooks/scripts/workflow_commands.py`

Structure:
```
Module docstring
Imports (stdlib + leaf modules + optional audit_log/git_validator)
Constants block (RECONCILE_DIAGNOSES, RECONCILE_NEXT_STEPS)
WorkflowCommandsServices dataclass
_iso_now() helper
_persist_progress(data, svc) helper (save_progress_json + regenerate progress.md)
Helper functions (_collect_feature_artifact_evidence, _collect_git_change_evidence,
                  _normalize_reconcile_step, _replay_audit_events)
Extracted command functions (each takes `svc: WorkflowCommandsServices` keyword-only,
                              matching work_item_commands.py convention)
```

Command functions and signatures:
- `set_workflow_state_command(phase=None, plan_path=None, next_action=None, *, svc) -> bool`
- `update_workflow_task_command(task_id, status, *, svc) -> bool`
- `clear_workflow_state_command(*, svc) -> bool`
- `health_check_command(*, svc) -> int`
- `validate_plan_command(plan_path=None, *, svc) -> bool`
- `analyze_reconcile_state_command(data=None, *, svc) -> Dict[str, Any]`
- `reconcile_command(output_json=False, *, svc) -> bool` (calls `analyze_reconcile_state_command(data, svc=svc)` internally)
- `cmd_reconcile_state_command(check_only=False, auto_commit=False, *, svc) -> Dict[str, Any]`

Each function body is a verbatim port of the current `progress_manager.py` logic,
with:
- `load_progress_json()` → `svc.load_progress_json_fn()`
- `save_progress_json(data)` → `svc.save_progress_json_fn(data)`
- `generate_progress_md(data)` / `save_progress_md(...)` → `svc.generate_progress_md_fn` / `svc.save_progress_md_fn` (use `_persist_progress` helper where the original calls both back-to-back)
- `_update_execution_context(...)` / `_update_runtime_context(...)` → `svc.update_execution_context_fn` / `svc.update_runtime_context_fn`
- `build_runtime_context(...)` → `svc.build_runtime_context_fn`
- `validate_plan_path(...)` / `validate_plan_document(...)` → `svc.validate_plan_path_fn` / `svc.validate_plan_document_fn`
- `find_project_root()` → `svc.find_project_root_fn()`
- `get_progress_dir()` → `svc.get_progress_dir_fn()`
- `load_checkpoints()` → `svc.load_checkpoints_fn()`
- `_latest_checkpoint_entry_for_feature(...)` / `_build_checkpoint_context(...)` → `svc.latest_checkpoint_entry_for_feature_fn` / `svc.build_checkpoint_context_fn`
- `_is_feature_deferred(...)` → `_is_feature_deferred(...)` (module-level import alias, unchanged call sites)
- `_run_git(...)` (inside `_collect_git_change_evidence`) → `git_utils._run_git(...)`
- `_iso_now()` → local `_iso_now()`
- `compare_contexts` / `_normalize_context_path` → module-level imports, unchanged call sites

### Task 2: Rewrite `progress_manager.py` facade section

1. Add re-export import near the existing `from work_item_commands import (...)` block
   (~line 158):
   ```python
   from workflow_commands import RECONCILE_DIAGNOSES, RECONCILE_NEXT_STEPS
   ```

2. Remove `RECONCILE_DIAGNOSES` / `RECONCILE_NEXT_STEPS` definitions (lines 279–293).

3. Remove `_collect_feature_artifact_evidence`, `_collect_git_change_evidence`,
   `_normalize_reconcile_step` definitions (lines 1368–1446) — no wrappers needed,
   internal-only helpers.

4. Add `_make_workflow_commands_services()` factory where the removed helpers used
   to start (~line 1368):
   ```python
   def _make_workflow_commands_services():
       import workflow_commands
       return workflow_commands.WorkflowCommandsServices(
           load_progress_json_fn=load_progress_json,
           save_progress_json_fn=save_progress_json,
           generate_progress_md_fn=generate_progress_md,
           save_progress_md_fn=save_progress_md,
           update_runtime_context_fn=_update_runtime_context,
           update_execution_context_fn=_update_execution_context,
           build_runtime_context_fn=build_runtime_context,
           validate_plan_path_fn=validate_plan_path,
           validate_plan_document_fn=validate_plan_document,
           find_project_root_fn=find_project_root,
           get_progress_dir_fn=get_progress_dir,
           load_checkpoints_fn=load_checkpoints,
           latest_checkpoint_entry_for_feature_fn=_latest_checkpoint_entry_for_feature,
           build_checkpoint_context_fn=_build_checkpoint_context,
       )
   ```

5. Replace `analyze_reconcile_state` body (1448–1625) with thin wrapper:
   ```python
   def analyze_reconcile_state(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
       import workflow_commands
       return workflow_commands.analyze_reconcile_state_command(
           data, svc=_make_workflow_commands_services()
       )
   analyze_reconcile_state.is_wrapper = True
   ```

6. Replace `reconcile` body (1628–1680) with thin wrapper delegating to
   `workflow_commands.reconcile_command`, marked `reconcile.is_wrapper = True`.

7. Remove `_replay_audit_events` definition (1786–1821).

8. Replace `cmd_reconcile_state` body (1824–1983) with thin wrapper delegating to
   `workflow_commands.cmd_reconcile_state_command`, marked
   `cmd_reconcile_state.is_wrapper = True`.

9. Replace `set_workflow_state`, `update_workflow_task`, `clear_workflow_state`,
   `health_check`, `validate_plan` bodies (5069–5297) with thin wrappers, each
   calling the corresponding `workflow_commands.*_command` with
   `svc=_make_workflow_commands_services()`.

10. **Wrapper marking rule (boundary contract):** every one of the 8 facade
    wrappers — `analyze_reconcile_state`, `reconcile`, `cmd_reconcile_state`,
    `set_workflow_state`, `update_workflow_task`, `clear_workflow_state`,
    `health_check`, `validate_plan` — must carry `is_wrapper = True`, matching
    the module-boundaries rule for backward-compat shims and the F26 precedent
    in `work_item_commands` wrappers.

### Task 3: Write unit tests in `tests/test_workflow_commands.py`

Cover, using a hand-built `WorkflowCommandsServices` with stub/mock callbacks
(plus `tmp_path` for the few functions that touch the filesystem via injected
`find_project_root_fn` / `get_progress_dir_fn`):

- `set_workflow_state_command`: phase transition, invalid plan_path rejected,
  no-active-feature error path
- `update_workflow_task_command`: marks task completed, advances `current_task`
- `clear_workflow_state_command`: clears existing state, no-op when absent
- `health_check_command`: healthy path (data_valid + git_healthy), degraded path
  (load failure)
- `validate_plan_command`: explicit plan_path, workflow_state fallback,
  direct_tdd skip, missing-plan error
- `analyze_reconcile_state_command`: `in_sync`, `needs_manual_review`
  (invalid current_feature_id), `implementation_ahead_of_tracker`
  (execution_complete)
- `reconcile_command`: text and `output_json=True` output shapes, missing-tracking
  case
- `cmd_reconcile_state_command`: no audit events → no drift, drift detected +
  fixed (check_only=False), check_only=True leaves progress.json untouched

### Task 3b: Write facade contract tests in `tests/test_workflow_commands_extraction_contract.py`

Follow the F26 precedent (`tests/test_work_item_commands_extraction_contract.py`):

- `test_workflow_command_exports_and_facade_wrappers`:
  - all 8 `workflow_commands.*_command` functions are callable
  - all 8 `progress_manager` facade wrappers have `is_wrapper is True`:
    `analyze_reconcile_state`, `reconcile`, `cmd_reconcile_state`,
    `set_workflow_state`, `update_workflow_task`, `clear_workflow_state`,
    `health_check`, `validate_plan`
- `test_reconcile_constants_are_re_exported_from_progress_manager`:
  - `progress_manager.RECONCILE_DIAGNOSES == workflow_commands.RECONCILE_DIAGNOSES`
  - `progress_manager.RECONCILE_NEXT_STEPS == workflow_commands.RECONCILE_NEXT_STEPS`
- `test_progress_manager_line_budget_meets_f27_target`:
  - `progress_manager.py` line count < 6528 (F26 baseline)

This protects the facade compatibility surface independently of the
injected-unit tests in Task 3: wrappers exist, are marked, constants stay
re-exported, and the line budget is enforced in CI rather than only manually.

### Task 4: Run checks

```bash
bash scripts/check_pm_boundary.sh
python3 hooks/scripts/generate_prog_docs.py --check
uv run pytest tests/ -q
```

### Task 5: Verify line count reduction

```bash
wc -l hooks/scripts/progress_manager.py
# Must be < 6528 (F26 baseline)
```

## Acceptance Criteria

1. `workflow_commands.py` exists with `set_workflow_state_command`,
   `update_workflow_task_command`, `clear_workflow_state_command`,
   `validate_plan_command`, `health_check_command`,
   `analyze_reconcile_state_command`, `reconcile_command`,
   `cmd_reconcile_state_command`.
2. `progress_manager.py` facade wrappers call `workflow_commands.*_command` with
   an injected `WorkflowCommandsServices`, and **all 8 wrappers carry
   `is_wrapper = True`** (boundary-contract requirement, same as F26).
3. `tests/test_workflow_commands_extraction_contract.py` exists and passes:
   module exports callable, all 8 facade wrappers marked `is_wrapper`,
   `RECONCILE_DIAGNOSES` / `RECONCILE_NEXT_STEPS` re-exported from the facade,
   line budget < 6528 enforced as a test.
4. `bash scripts/check_pm_boundary.sh` passes (no reverse imports).
5. `python3 hooks/scripts/generate_prog_docs.py --check` passes.
6. `uv run pytest tests/ -q` passes (zero regressions vs 1153-pass baseline, plus
   new `test_workflow_commands.py` and
   `test_workflow_commands_extraction_contract.py` tests).
7. `progress_manager.py` line count < 6528.

## Risk Notes

- `tests/test_workflow_state.py` patches `progress_manager.collect_git_context`
  and expects `set_workflow_state` / `update_workflow_task` to record
  `execution_context` using the patched value — preserved by injecting
  `_update_execution_context` / `_update_runtime_context` (which resolve
  `collect_git_context` at call time in `progress_manager`'s namespace) rather
  than reimplementing via `git_utils` directly.
- `tests/test_reconcile_state.py` and `tests/test_progress_manager.py::TestReconcile`
  rely on `_PROJECT_ROOT_OVERRIDE`-based root resolution; `find_project_root_fn`
  must be re-resolved per call via `_make_workflow_commands_services()` (not
  cached at import time) so patches on `progress_manager.find_project_root` /
  `progress_manager._PROJECT_ROOT_OVERRIDE` continue to take effect.
- `_latest_checkpoint_entry_for_feature` / `_build_checkpoint_context` /
  `load_checkpoints` have a second call site (~line 3676) outside the F27 scope;
  do not delete them from `progress_manager.py` — only inject as callbacks.

## Implementation Deviations

1. **`health_check_command` exception branch**: the original `health_check` left
   `data` unbound when `load_progress_json()` raised, which would crash the
   later `(data_valid or not data)` expression with `UnboundLocalError`. The
   extracted version assigns `data = None` in the `except` branch so the
   degraded path returns a valid payload instead of crashing. No behavior
   change on the normal path (`load_progress_json` swallows I/O errors and
   returns `None` in practice).
2. **`_collect_feature_artifact_evidence` signature**: takes an explicit `svc`
   parameter (it needs `find_project_root_fn`), unlike the other two reconcile
   helpers which stay dependency-free.
