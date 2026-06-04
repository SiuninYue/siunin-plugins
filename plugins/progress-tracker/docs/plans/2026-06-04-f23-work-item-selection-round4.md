# F23 Work-Item Selection Round 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract work-item selection and `next-feature` command behavior out of `progress_manager.py` while preserving the existing CLI and import contract.

**Architecture:** Create `work_item_selector.py` for pure selection and dispatch helpers, and `next_feature_commands.py` for command rendering, state writes, and CLI orchestration. `progress_manager.py` remains the facade: it imports the new command functions inside wrapper bodies, passes required callbacks through dataclass service objects, and marks moved compatibility exports with `is_wrapper = True`.

**Tech Stack:** Python 3.14, argparse, pytest, existing progress-tracker modules (`readiness_validator`, `state_reconciler`, `state_io`, `route_utils`, `git_utils`, `progress_prompt_builders`), `scripts/check_pm_boundary.sh`, and `generate_prog_docs.py --check`.

---

## Scope

Move these implementation bodies out of `plugins/progress-tracker/hooks/scripts/progress_manager.py`:

- `get_next_feature`
- `_get_dispatched_child_feature`
- `_select_next_work_item`
- `next_feature`

Keep backward-compatible facade names in `progress_manager.py`. Tests may continue importing from `progress_manager`.

Do not change command semantics, planning gate semantics, routing priority, finish-pending behavior, active-route writeback behavior, or task branch behavior.

## File Structure

- Create `plugins/progress-tracker/hooks/scripts/work_item_selector.py`
  - Owns next feature lookup, child/root dispatch selection, bug/task/feature priority selection, and route conflict checks.
  - Accepts injected callbacks for state loading, root discovery, linked project loading, timestamp parsing, and defer checks.
- Create `plugins/progress-tracker/hooks/scripts/next_feature_commands.py`
  - Owns `next_feature_command(output_json=False, ack_planning_risk=False, services=...)`.
  - Handles rendering JSON/text output, planning gate checks, task activation, branch creation, active-route bookkeeping, and progress markdown regeneration.
- Modify `plugins/progress-tracker/hooks/scripts/progress_manager.py`
  - Replace moved bodies with thin wrapper functions and injected service builders.
  - Keep parser wiring unchanged.
  - Mark wrapper exports with `is_wrapper = True`.
- Modify tests only where direct monkeypatch targets need to point at new modules in addition to facade compatibility.
- Update `plugins/progress-tracker/docs/progress-tracker/architecture/progress-manager-module-map.md`.
- Append one F23 change record to `plugins/progress-tracker/docs/changes/index.jsonl` and add its markdown record.

## Task 1: Extract Pure Selection Helpers

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/work_item_selector.py`
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_dispatch_child_feature.py`
- Test: `plugins/progress-tracker/tests/test_unified_selection.py`

- [ ] **Step 1: Write focused import and parity tests**

Add tests that import the new module directly and verify facade compatibility still works:

```python
import work_item_selector
import progress_manager


def test_get_dispatched_child_feature_facade_delegates():
    assert progress_manager._get_dispatched_child_feature.is_wrapper is True
    assert callable(work_item_selector.get_dispatched_child_feature)


def test_select_next_work_item_facade_delegates():
    assert progress_manager._select_next_work_item.is_wrapper is True
    assert callable(work_item_selector.select_next_work_item)
```

- [ ] **Step 2: Run tests and confirm the new-module assertions fail**

Run:

```bash
uv run pytest plugins/progress-tracker/tests/test_dispatch_child_feature.py plugins/progress-tracker/tests/test_unified_selection.py -q
```

Expected: fail because `work_item_selector.py` does not exist and facade functions are not wrappers yet.

- [ ] **Step 3: Create `work_item_selector.py` with injected services**

Use this module shape:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WorkItemSelectorServices:
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    is_feature_deferred_fn: Callable[[Dict[str, Any]], bool]
    parse_iso_timestamp_fn: Callable[[str], Optional[datetime]]
    resolve_linked_project_root_fn: Callable[[str, Path, Path], Path]
    load_progress_payload_at_root_fn: Callable[[Path], tuple[Optional[Dict[str, Any]], Optional[str]]]
    stale_after_hours: int
    root_route_code: str
```

Move the body of `get_next_feature()` into `get_next_feature(svc)`.
Move `_get_dispatched_child_feature(...)` into `get_dispatched_child_feature(..., svc)`.
Move `_select_next_work_item(...)` into `select_next_work_item(..., svc)`.

- [ ] **Step 4: Keep behavior identical during the move**

Preserve these exact behaviors:

- skip completed and deferred features
- root route returns root-level pending features
- unknown child route prints `[WARN] Code "<code>" not found in linked_projects, skipping`
- non-terminal active routes block dispatch unless stale
- P0 bug > P1 bug > standalone task > child/root dispatch > P2 bug > feature fallback
- fixed and false-positive bugs are skipped
- active BUG routes are skipped

- [ ] **Step 5: Replace facade functions with wrappers**

Use local imports inside wrappers to avoid import-time cycles:

```python
def get_next_feature():
    """Get the next incomplete feature."""
    is_wrapper = True
    from work_item_selector import WorkItemSelectorServices, get_next_feature as _impl
    return _impl(_work_item_selector_services())
get_next_feature.is_wrapper = True
```

Repeat for `_get_dispatched_child_feature` and `_select_next_work_item`. `_work_item_selector_services()` should be a small private facade helper in `progress_manager.py`.

- [ ] **Step 6: Run focused selector tests**

Run:

```bash
uv run pytest plugins/progress-tracker/tests/test_dispatch_child_feature.py plugins/progress-tracker/tests/test_unified_selection.py -q
```

Expected: all tests pass.

## Task 2: Extract `next_feature` Command Orchestration

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/next_feature_commands.py`
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`
- Test: `plugins/progress-tracker/tests/test_scope_fail_closed.py`

- [ ] **Step 1: Add command facade tests**

Add assertions that `progress_manager.next_feature.is_wrapper is True` and that `next_feature_commands.next_feature_command` is importable.

- [ ] **Step 2: Run tests and confirm the command-module assertion fails**

Run:

```bash
uv run pytest plugins/progress-tracker/tests/test_progress_manager.py -k "next_feature or planning_gate or finish_pending" -q
```

Expected: fail until `next_feature_commands.py` exists and the facade wrapper is in place.

- [ ] **Step 3: Create `next_feature_commands.py` with injected services**

Use this module shape:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional


@dataclass
class NextFeatureCommandServices:
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    save_progress_json_fn: Callable[[Dict[str, Any]], None]
    generate_progress_md_fn: Callable[[Dict[str, Any]], str]
    save_progress_md_fn: Callable[[str], None]
    find_project_root_fn: Callable[[], Path]
    detect_default_branch_fn: Callable[[Path], Optional[str]]
    run_git_fn: Callable[..., tuple[int, str, str]]
    update_runtime_context_fn: Callable[[Dict[str, Any], str], bool]
    collect_linked_project_statuses_fn: Callable[..., list[dict]]
    analyze_reconcile_state_fn: Callable[[Dict[str, Any]], Dict[str, Any]]
    evaluate_planning_readiness_fn: Callable[..., Dict[str, Any]]
    select_next_work_item_fn: Callable[[Dict[str, Any], Path, Path], Optional[Dict[str, Any]]]
    get_next_feature_fn: Callable[[], Optional[Dict[str, Any]]]
    finish_pending_state: str
    linked_snapshot_schema_version: str
    root_route_code: str
    repo_root: Optional[Path]
```

Move the body of `next_feature()` into `next_feature_command(output_json, ack_planning_risk, svc)`.

- [ ] **Step 4: Preserve output payloads exactly**

Do not rename JSON fields or message strings for these paths:

- `finish_pending`
- `implementation_ahead_of_tracker`
- `scope_mismatch`
- `context_mismatch`
- parent bug dispatch
- parent task dispatch
- child/root dispatch
- no actionable route queue
- filtered BUG-only queue
- standalone task activation
- no actionable feature
- planning missing/warn block
- normal feature payload

- [ ] **Step 5: Replace `progress_manager.next_feature` with a wrapper**

Use:

```python
def next_feature(output_json: bool = False, ack_planning_risk: bool = False) -> bool:
    """Print the next actionable feature (skipping completed/deferred)."""
    is_wrapper = True
    from next_feature_commands import NextFeatureCommandServices, next_feature_command
    return next_feature_command(
        output_json=output_json,
        ack_planning_risk=ack_planning_risk,
        svc=_next_feature_command_services(),
    )
next_feature.is_wrapper = True
```

- [ ] **Step 6: Run focused command tests**

Run:

```bash
uv run pytest plugins/progress-tracker/tests/test_progress_manager.py -k "next_feature or planning_gate or finish_pending" -q
uv run pytest plugins/progress-tracker/tests/test_task_execution_semantics.py plugins/progress-tracker/tests/test_scope_fail_closed.py -q
```

Expected: all selected tests pass.

## Task 3: Boundary, Docs, and Change Record

**Files:**
- Modify: `plugins/progress-tracker/docs/progress-tracker/architecture/progress-manager-module-map.md`
- Modify: `plugins/progress-tracker/docs/changes/index.jsonl`
- Create: `plugins/progress-tracker/docs/changes/20260604-f23-work-item-selection-round4.md`

- [ ] **Step 1: Update module map**

Add Round 4 ownership:

```markdown
| Round 4 | `work_item_selector.py` | `get_next_feature`, child/root dispatch, priority work-item selection. |
| Round 4 | `next_feature_commands.py` | `next-feature` command orchestration, output rendering, task activation, and selection state writes. |
```

- [ ] **Step 2: Add change record**

Append one JSONL object:

```json
{"change_id":"20260604-f23-work-item-selection-round4","date":"2026-06-04","feature_id":23,"summary":"Extract work-item selection and next-feature command orchestration from progress_manager facade.","record_path":"plugins/progress-tracker/docs/changes/20260604-f23-work-item-selection-round4.md"}
```

Create the markdown record with scope, files changed, validation commands, and rollback notes.

- [ ] **Step 3: Run required checks**

Run:

```bash
scripts/check_pm_boundary.sh
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
```

Expected: both pass.

- [ ] **Step 4: Run focused and broad regression**

Run:

```bash
uv run pytest plugins/progress-tracker/tests/test_dispatch_child_feature.py plugins/progress-tracker/tests/test_unified_selection.py plugins/progress-tracker/tests/test_task_execution_semantics.py plugins/progress-tracker/tests/test_scope_fail_closed.py -q
uv run pytest plugins/progress-tracker/tests/test_progress_manager.py -k "next_feature or planning_gate or finish_pending" -q
uv run pytest plugins/progress-tracker/tests/ -q
```

Expected: focused tests and full progress-tracker suite pass.

## Sprint Contract

Scope: Extract work-item selection and `next-feature` command logic into dedicated modules with injected dependencies while preserving all public facade imports and CLI behavior.

Done criteria:

- `work_item_selector.py` owns pure selection and dispatch helpers.
- `next_feature_commands.py` owns `next-feature` command orchestration.
- `progress_manager.py` retains wrappers marked with `is_wrapper = True`.
- No submodule imports `progress_manager`.
- Required docs and change records are updated.
- Required boundary and docs checks pass.
- Focused and full progress-tracker regression suites pass.

Test plan:

- `scripts/check_pm_boundary.sh`
- `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check`
- `uv run pytest plugins/progress-tracker/tests/test_dispatch_child_feature.py plugins/progress-tracker/tests/test_unified_selection.py plugins/progress-tracker/tests/test_task_execution_semantics.py plugins/progress-tracker/tests/test_scope_fail_closed.py -q`
- `uv run pytest plugins/progress-tracker/tests/test_progress_manager.py -k "next_feature or planning_gate or finish_pending" -q`
- `uv run pytest plugins/progress-tracker/tests/ -q`
