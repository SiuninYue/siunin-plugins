# F22 Plan: progress_manager Facade Round 3 — Feature Activation and Stage Commands

**Feature ID:** 22  
**Bucket:** complex (upgraded from standard; confidence=low, fallback scoring)  
**Workflow path:** full_design_plan_execute  
**Approved:** 2026-06-04

## Goal

Extract `set_current` and `set_development_stage` from `progress_manager.py` into a new module
`feature_commands.py`. Keep thin compatibility wrappers in `progress_manager.py`.

## Architecture Constraints

- `feature_commands.py` must NOT import `progress_manager` (no reverse dependency).
- Facade-owned state IO and git-side-effects injected via `FeatureCommandsServices` dataclass.
- Leaf-to-leaf imports allowed for modules that do not depend on `progress_manager`.
- Wrappers in `progress_manager.py` must be marked `is_wrapper = True`.
- Must pass `scripts/check_pm_boundary.sh` and `generate_prog_docs.py --check`.

## Interface Design

### FeatureCommandsServices (dataclass)

```python
@dataclass
class FeatureCommandsServices:
    load_progress_json_fn:      Callable[[], Optional[Dict[str, Any]]]
    save_progress_json_fn:      Callable[[Dict[str, Any]], None]
    generate_progress_md_fn:    Callable[[Dict[str, Any]], str]
    save_progress_md_fn:        Callable[[str], None]
    update_runtime_context_fn:  Callable[[Dict[str, Any], str], bool]
    auto_state_commit_fn:       Callable[[str, str], Optional[str]]   # facade git side-effect
    notify_parent_sync_fn:      Callable[[str], None]                  # facade parent-route side-effect
```

### Leaf-to-leaf imports (direct, no injection)

| Import | Source module | Rationale |
|---|---|---|
| `validate_feature_readiness`, `print_readiness_error`, `print_readiness_warnings` | `readiness_validator` | No PM dependency |
| `_is_feature_deferred` | `progress_prompt_builders` | No PM dependency |
| `_initialize_reviews`, `REVIEW_ROUTER_AVAILABLE` | `review_router` (try/except ImportError) | Optional plugin, dynamic import |

### Constants reused inline

- `DEVELOPMENT_STAGES` — import from `state_io` or inline from PM constant
- `_iso_now` — inline utility (datetime.utcnow().isoformat())

## Tasks

### T1: Analyze Extraction Scope
- Confirm line ranges: `set_current` (L3861–L3929), `set_development_stage` (L3931–L3984)
- Verify `_is_feature_deferred` location in `progress_prompt_builders`
- Verify `review_router` dynamic import pattern used elsewhere in codebase
- Confirm `DEVELOPMENT_STAGES` import source

### T2: Write Tests — RED phase

Create `tests/test_feature_commands.py` with 7 scenarios using mock `FeatureCommandsServices`:

**set_current tests:**

1. `test_set_current_success` — valid non-deferred feature passes readiness:
   - stage → `developing`, lifecycle → `implementing`
   - `started_at` recorded
   - `workflow_state` initialized to `{"phase": "planning"}`
   - reviews initialized via `initialize_reviews`
   - `update_runtime_context_fn` called with source `"set_current"`
   - `save_progress_json_fn` called once
   - `auto_state_commit_fn` called with `(f"F{id}", "start")`
   - `notify_parent_sync_fn` called with `"activate"`

2. `test_set_current_feature_not_found` — nonexistent feature_id:
   - returns `False`, no save/commit/notify calls

3. `test_set_current_deferred_blocked` — deferred feature:
   - returns `False`, no state mutation

4. `test_set_current_readiness_blocked` — readiness check returns invalid:
   - `print_readiness_error` called, returns `False`, no save

**set_development_stage tests:**

5. `test_set_development_stage_to_developing` — valid current feature:
   - stage → `developing`, lifecycle → `implementing`
   - `started_at` recorded (if not already set)
   - save and context update called

6. `test_set_development_stage_planning_and_completed`:
   - `planning` → lifecycle → `approved`
   - `completed` → lifecycle → `verified`
   - save and context update called for each

7. `test_set_development_stage_invalid_cases`:
   - unknown stage → returns `False` before any load
   - no active current_feature_id + no feature_id arg → returns `False`

Run `pytest tests/test_feature_commands.py` — expect **FAIL** (module not yet created).

### T3: Implement feature_commands.py — GREEN phase

Create `hooks/scripts/feature_commands.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
import datetime

from readiness_validator import (
    validate_feature_readiness,
    print_readiness_error,
    print_readiness_warnings,
)
from progress_prompt_builders import _is_feature_deferred

try:
    from review_router import _initialize_reviews, REVIEW_ROUTER_AVAILABLE
except ImportError:
    REVIEW_ROUTER_AVAILABLE = False
    def _initialize_reviews(feature): pass

DEVELOPMENT_STAGES = [...]  # import from state_io or inline

@dataclass
class FeatureCommandsServices:
    ...  # as above

def set_current_command(feature_id: int, svc: FeatureCommandsServices) -> bool: ...
def set_development_stage_command(stage: str, svc: FeatureCommandsServices, feature_id: Optional[int] = None) -> bool: ...
```

Run `pytest tests/test_feature_commands.py` — expect **PASS**.

### T4: Update progress_manager.py Wrappers

Replace bodies of `set_current` and `set_development_stage` with:

```python
def set_current(feature_id):
    """Set the current feature being worked on."""
    is_wrapper = True
    from feature_commands import set_current_command, FeatureCommandsServices
    return set_current_command(feature_id, FeatureCommandsServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        update_runtime_context_fn=_update_runtime_context,
        auto_state_commit_fn=_auto_state_commit,
        notify_parent_sync_fn=_notify_parent_sync,
    ))

def set_development_stage(stage, feature_id=None):
    """Set development_stage for the target feature."""
    is_wrapper = True
    from feature_commands import set_development_stage_command, FeatureCommandsServices
    return set_development_stage_command(stage, FeatureCommandsServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        update_runtime_context_fn=_update_runtime_context,
        auto_state_commit_fn=_auto_state_commit,
        notify_parent_sync_fn=_notify_parent_sync,
    ), feature_id=feature_id)
```

### T5: Boundary and Docs Checks

```bash
scripts/check_pm_boundary.sh
python3 hooks/scripts/generate_prog_docs.py --check
```

Both must exit 0.

### T6: Full Regression

```bash
uv run pytest -q
```

Expect 1077+ PASS, 0 FAIL.

### T7: DoD Closeout

- Update `docs/progress-tracker/architecture/progress-manager-module-map.md`:
  Add `feature_commands.py` row to Extracted Ownership table:
  `| Feature activation + stage commands | feature_commands.py | F22 wrappers only | set_current, set_development_stage extracted. Callbacks: load/save json, gen/save md, update_ctx, auto_state_commit, notify_parent_sync. |`
- Append record to `docs/changes/index.jsonl`:
  `{"date":"2026-06-04","feature_id":22,"round":3,"module":"feature_commands.py","extracted":["set_current","set_development_stage"]}`
- Register Round 4 feature OR write explicit defer decision

## Acceptance Mapping

| Task | Acceptance Criterion | Verification Method |
|------|---------------------|---------------------|
| T2: RED tests | 7 test cases created, all FAIL before implementation | `pytest tests/test_feature_commands.py` exits non-zero |
| T3: GREEN impl | All 7 tests pass after `feature_commands.py` created | `pytest tests/test_feature_commands.py` exits 0 |
| T4: PM wrappers | `set_current` and `set_development_stage` in PM marked `is_wrapper=True` | `grep is_wrapper hooks/scripts/progress_manager.py` |
| T5: Boundary checks | No reverse imports from submodules to PM | `scripts/check_pm_boundary.sh` exits 0; `generate_prog_docs.py --check` exits 0 |
| T6: Regression | Full test suite passes with no regressions | `uv run pytest -q` — 1077+ PASS, 0 FAIL |
| T7: DoD docs | Module map updated; changes index appended; Round 4 registered or deferred | Files updated and committed |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Callback injection misses a side-effect path | Medium | High — silent behavioral regression | TDD with mock services capturing every call; full regression suite |
| `_notify_parent_sync` or `_auto_state_commit` not injectable (private/closure) | Low | Medium — requires refactor of PM internals | Verify accessibility in T1 analysis; expose as module-level if needed |
| `review_router` dynamic import fallback silently skips review init | Low | Low — review initialization is best-effort | Test both import-success and ImportError paths in T2 |
| Round 4 scope undefined → facade cleanup stalls | High | Medium — technical debt accumulates | T7 requires explicit Round 4 registration or defer decision before F22 closeout |
