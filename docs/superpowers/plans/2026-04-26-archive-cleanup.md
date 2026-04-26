# Archive Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear active progress.json when all features are completed, so projects show 0/0 instead of stale counts.

**Architecture:** Add `_reset_active_progress(data)` function with fail-closed audit-first write ordering. Wire it into `complete_feature()` outside the `skip_archive` gate. Add `project_completed` boundary event to audit whitelist and all boundary consumers.

**Tech Stack:** Python 3, pytest, progress_manager.py, audit_log.py

---

### Task 1: Add `project_completed` to audit whitelist and write whitelist test

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/audit_log.py:18-30`
- Test: `plugins/progress-tracker/tests/test_audit_log_whitelist.py`

- [ ] **Step 1: Write the failing test**

Add a test to `test_audit_log_whitelist.py` asserting `project_completed` is in `ALLOWED_EVENT_TYPES`:

```python
def test_contains_project_completed_event(self):
    """project_completed must be in whitelist before _reset_active_progress can write it."""
    assert "project_completed" in audit_log.ALLOWED_EVENT_TYPES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_audit_log_whitelist.py::TestAllowedEventTypesConstant::test_contains_project_completed_event -v`
Expected: FAIL — `"project_completed" not in ALLOWED_EVENT_TYPES`

- [ ] **Step 3: Add `project_completed` to the whitelist**

In `audit_log.py`, add `"project_completed"` to `ALLOWED_EVENT_TYPES` (after `"manual_state_override"`):

```python
ALLOWED_EVENT_TYPES: frozenset = frozenset({
    # 核心状态变更事件（Feature 0 新增）
    "feature_completed",
    "feature_undone",
    "state_restored",
    "tracker_reset",
    "manual_state_override",
    "project_completed",
    # 现有生产代码已写入的事件类型（不可移除，否则静默丢数据）
    "schema_migration",
    "evaluator_assessment",
    "evaluator_backfill",
    "set_finish_state",
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_audit_log_whitelist.py::TestAllowedEventTypesConstant::test_contains_project_completed_event -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/audit_log.py plugins/progress-tracker/tests/test_audit_log_whitelist.py
git commit -m "feat(audit): add project_completed to ALLOWED_EVENT_TYPES"
```

---

### Task 2: Add `project_completed` boundary handling in `_replay_audit_events`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:3133-3168`
- Test: `plugins/progress-tracker/tests/test_reconcile_state.py`

- [ ] **Step 1: Write the failing test**

Add to `test_reconcile_state.py`:

```python
class TestProjectCompletedBoundary:
    def test_project_completed_clears_prior_states(self, project_scope):
        """project_completed is a boundary: all feature_completed before it are irrelevant."""
        _write_progress(project_scope["state_dir"],
                        [{"id": 1, "name": "F1", "completed": True}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=1,
                           ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "project_completed",
                           ts="2026-04-24T11:00:00Z")
        result = pm.cmd_reconcile_state(check_only=True)
        # After project_completed, feature 1's completion is pre-boundary
        assert result["drift"] is True
        assert any(d["feature_id"] == 1 and d["expected_completed"] is False
                    for d in result.get("drifted_features", []))

    def test_project_completed_acts_like_tracker_reset(self, project_scope):
        """project_completed and tracker_reset should produce identical reconcile results."""
        for event_type in ("project_completed", "tracker_reset"):
            state_dir = project_scope["state_dir"]
            # Clean slate
            _write_progress(state_dir, [{"id": 5, "name": "F5", "completed": False}])
            _write_audit_event(state_dir, "feature_completed", feature_id=5,
                               ts="2026-04-24T10:00:00Z")
            _write_audit_event(state_dir, event_type,
                               ts="2026-04-24T11:00:00Z")
            result = pm.cmd_reconcile_state(check_only=True)
            # After boundary, feature 5 completed in progress but not in audit (post-boundary)
            assert result["diagnosis"] == "needs_manual_review" or result["drift"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_reconcile_state.py::TestProjectCompletedBoundary -v`
Expected: FAIL — `project_completed` not handled in `_replay_audit_events`

- [ ] **Step 3: Implement boundary handling in `_replay_audit_events`**

In `progress_manager.py`, modify `_replay_audit_events` (line ~3148) to include `project_completed`:

```python
relevant_types = {"feature_completed", "feature_undone", "tracker_reset", "project_completed"}
sorted_records = sorted(
    [r for r in audit_records if r.get("event_type") in relevant_types],
    key=lambda r: r.get("timestamp", ""),
)

states: Dict[int, str] = {}
last_event_was_reset = False
for record in sorted_records:
    et = record["event_type"]
    if et in ("tracker_reset", "project_completed"):
        # Both are boundaries: clear all prior replayed states
        states.clear()
        last_event_was_reset = True
    elif et == "feature_completed" and record.get("feature_id") is not None:
        states[record["feature_id"]] = "completed"
        last_event_was_reset = False
    elif et == "feature_undone" and record.get("feature_id") is not None:
        states[record["feature_id"]] = "not_completed"
        last_event_was_reset = False
return states, last_event_was_reset
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_reconcile_state.py::TestProjectCompletedBoundary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py plugins/progress-tracker/tests/test_reconcile_state.py
git commit -m "feat(reconcile): handle project_completed as audit boundary in _replay_audit_events"
```

---

### Task 3: Add `project_completed` boundary handling in `find_backfill_candidates`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:3345-3373`
- Test: `plugins/progress-tracker/tests/test_backfill_event.py`

- [ ] **Step 1: Write the failing test**

Add to `test_backfill_event.py`:

```python
class TestBackfillAfterProjectCompleted:
    def test_ignores_pre_boundary_feature_completed(self, project_scope):
        """After project_completed, old-cycle feature_completed should not suppress backfill."""
        _write_progress(project_scope["state_dir"],
                        [{"id": 1, "name": "New F1", "completed": True,
                          "completed_at": "2026-04-25T00:00:00Z"}])
        # Old cycle: feature 1 was completed before project_completed
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=1,
                           ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "project_completed",
                           ts="2026-04-24T11:00:00Z")
        # New cycle: feature 1 completed but no audit event post-boundary
        candidates = pm.find_backfill_candidates()
        assert 1 in [c["feature_id"] for c in candidates]

    def test_no_candidates_when_post_boundary_event_exists(self, project_scope):
        """After project_completed, new-cycle feature_completed suppresses backfill."""
        _write_progress(project_scope["state_dir"],
                        [{"id": 1, "name": "New F1", "completed": True,
                          "completed_at": "2026-04-25T00:00:00Z"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=1,
                           ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "project_completed",
                           ts="2026-04-24T11:00:00Z")
        # New cycle event after boundary
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=1,
                           ts="2026-04-25T10:00:00Z")
        candidates = pm.find_backfill_candidates()
        assert candidates == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_backfill_event.py::TestBackfillAfterProjectCompleted -v`
Expected: FAIL — `project_completed` not checked in boundary scan

- [ ] **Step 3: Implement boundary handling in `find_backfill_candidates`**

In `progress_manager.py`, modify the boundary scan in `find_backfill_candidates` (line ~3352-3357):

```python
        # 幂等性须考虑 reset/project_completed 边界：
        # 只看最后一次 tracker_reset 或 project_completed 之后的 feature_completed
        # 边界之前的完成事件不应阻止边界之后合法的 backfill
        BOUNDARY_EVENT_TYPES = {"tracker_reset", "project_completed"}
        last_reset_idx = -1
        for i, r in enumerate(all_records):
            if r.get("event_type") in BOUNDARY_EVENT_TYPES:
                last_reset_idx = i
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_backfill_event.py::TestBackfillAfterProjectCompleted -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py plugins/progress-tracker/tests/test_backfill_event.py
git commit -m "feat(backfill): handle project_completed as boundary in find_backfill_candidates"
```

---

### Task 4: Implement `_reset_active_progress()` with fail-closed audit-first write ordering

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Create: `plugins/progress-tracker/tests/test_reset_active_progress.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reset_active_progress.py`:

```python
"""Tests for _reset_active_progress: clearing active state on project completion."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log
import progress_manager as pm

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _write_progress, _write_audit_event


def _make_fully_completed_data():
    """Progress data where all features are completed."""
    return {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [
            {"id": 1, "name": "F1", "completed": True,
             "completed_at": "2026-01-02T00:00:00Z"},
            {"id": 2, "name": "F2", "completed": True,
             "completed_at": "2026-01-03T00:00:00Z"},
        ],
        "current_feature_id": None,
        "bugs": [{"id": "BUG-001", "description": "test bug", "status": "fixed"}],
        "updates": [{"id": "UPD-001", "summary": "test update"}],
        "retrospectives": [{"id": "RET-001", "summary": "test retro"}],
        "current_bug_id": "BUG-001",
        "workflow_state": {"phase": "execution_complete"},
        "runtime_context": {
            "current_feature_id": 2,
            "workflow_phase": "execution_complete",
            "current_task": None,
            "total_tasks": 3,
            "next_action": "run /prog done",
        },
    }


def _write_full_progress(state_dir, data=None):
    """Write full progress data to state_dir."""
    if data is None:
        data = _make_fully_completed_data()
    path = state_dir / "progress.json"
    path.write_text(json.dumps(data))
    return path


class TestResetActiveProgress:
    def test_clears_features_bugs_updates_retrospectives(self, project_scope):
        """_reset_active_progress clears all tracked collections."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)

        pm._reset_active_progress(data)

        assert data["features"] == []
        assert data["bugs"] == []
        assert data["updates"] == []
        assert data["retrospectives"] == []

    def test_clears_current_ids_and_workflow_state(self, project_scope):
        """_reset_active_progress clears current IDs and removes workflow_state."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)

        pm._reset_active_progress(data)

        assert data["current_feature_id"] is None
        assert data["current_bug_id"] is None
        assert "workflow_state" not in data

    def test_resets_runtime_context_work_fields(self, project_scope):
        """_reset_active_progress clears work-specific fields in runtime_context."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)

        pm._reset_active_progress(data)

        rc = data["runtime_context"]
        assert rc["current_feature_id"] is None
        assert rc["workflow_phase"] is None
        assert rc["current_task"] is None
        assert rc["total_tasks"] is None
        assert rc["next_action"] is None

    def test_preserves_runtime_context_structure(self, project_scope):
        """_reset_active_progress preserves non-work fields in runtime_context."""
        data = _make_fully_completed_data()
        data["runtime_context"]["branch"] = "main"
        data["runtime_context"]["project_root"] = "/tmp/test"
        _write_full_progress(project_scope["state_dir"], data)

        pm._reset_active_progress(data)

        rc = data["runtime_context"]
        assert rc["branch"] == "main"
        assert rc["project_root"] == "/tmp/test"

    def test_updates_updated_at(self, project_scope):
        """_reset_active_progress sets updated_at to current time."""
        data = _make_fully_completed_data()
        old_updated = data["updated_at"]
        _write_full_progress(project_scope["state_dir"], data)

        pm._reset_active_progress(data)

        assert data["updated_at"] != old_updated

    def test_saves_progress_json(self, project_scope):
        """_reset_active_progress persists the cleared state to disk."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)

        pm._reset_active_progress(data)

        # Re-read from disk
        saved = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert saved["features"] == []
        assert saved["current_feature_id"] is None

    def test_records_project_completed_audit_event(self, project_scope):
        """_reset_active_progress writes project_completed event to audit.log."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)

        pm._reset_active_progress(data)

        records = audit_log.read_audit_log(
            ascending=True, project_root=str(project_scope["root"]))
        assert any(r["event_type"] == "project_completed" for r in records)

    def test_regenerates_progress_md(self, project_scope):
        """_reset_active_progress regenerates progress.md for 0/0 state."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)
        # Write initial progress.md
        md_path = project_scope["state_dir"] / "progress.md"
        md_path.write_text("# old content")

        pm._reset_active_progress(data)

        new_md = md_path.read_text()
        assert "0/0" in new_md or "0" in new_md

    def test_fail_closed_on_audit_write_error(self, project_scope):
        """If audit write fails, active state must NOT be cleared."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)
        original_features = list(data["features"])
        original_bugs = list(data["bugs"])

        with patch.object(pm, "record_feature_state_event",
                          side_effect=ValueError("audit write failed")):
            pm._reset_active_progress(data)

        # Active state must remain intact — fail-closed
        assert data["features"] == original_features
        assert data["bugs"] == original_bugs
        assert data["current_feature_id"] is None  # already None in test data, but verify

        # On-disk must also remain unchanged
        saved = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert len(saved["features"]) == 2


class TestResetActiveProgressFailClosedOnAuditError:
    def test_does_not_save_when_audit_fails(self, project_scope):
        """When record_feature_state_event raises, save_progress_json must not be called."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)

        with patch.object(pm, "record_feature_state_event",
                          side_effect=ValueError("audit write failed")):
            pm._reset_active_progress(data)

        # Disk must still have old data
        saved = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert len(saved["features"]) == 2
        assert len(saved["bugs"]) == 1

    def test_does_not_generate_md_when_audit_fails(self, project_scope):
        """When audit write fails, progress.md must not be regenerated."""
        data = _make_fully_completed_data()
        _write_full_progress(project_scope["state_dir"], data)
        md_path = project_scope["state_dir"] / "progress.md"
        md_path.write_text("# OLD MARKER 12345")

        with patch.object(pm, "record_feature_state_event",
                          side_effect=ValueError("audit write failed")):
            pm._reset_active_progress(data)

        assert "OLD MARKER 12345" in md_path.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_reset_active_progress.py -v`
Expected: FAIL — `_reset_active_progress` does not exist yet

- [ ] **Step 3: Implement `_reset_active_progress`**

Add the function in `progress_manager.py`, after `archive_current_progress` (around line 3873):

```python
def _reset_active_progress(data: Dict[str, Any]) -> None:
    """Clear completed project state from active progress.json.

    Called when _is_project_fully_completed() is true. Fail-closed:
    writes the project_completed audit boundary event FIRST; if that
    fails, the active state is left untouched so old-cycle events
    cannot corrupt the next reconcile/backfill cycle.

    Args:
        data: The in-memory progress.json dict (will be modified in place).
    """
    # Fail-closed: write audit boundary BEFORE clearing state.
    # If audit write fails, do NOT clear — otherwise old-cycle
    # feature_completed events would corrupt the next cycle's
    # reconcile/backfill.
    try:
        record_feature_state_event(
            event_type="project_completed",
            feature_id=None,
            feature_name=None,
        )
    except Exception as e:
        logger.error(f"Failed to write project_completed audit event: {e}")
        print(f"Error: Could not record project_completed event. Active state NOT cleared.")
        return

    data["features"] = []
    data["bugs"] = []
    data["updates"] = []
    data["retrospectives"] = []
    data["current_feature_id"] = None
    data["current_bug_id"] = None
    data.pop("workflow_state", None)

    # runtime_context: preserve structure, clear work-specific fields
    if isinstance(data.get("runtime_context"), dict):
        data["runtime_context"].update({
            "current_feature_id": None,
            "workflow_phase": None,
            "current_task": None,
            "total_tasks": None,
            "next_action": None,
        })

    data["updated_at"] = _iso_now()
    save_progress_json(data)

    # Regenerate progress.md for 0/0 state
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print("Active progress cleared — project state is now 0/0.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_reset_active_progress.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py plugins/progress-tracker/tests/test_reset_active_progress.py
git commit -m "feat: add _reset_active_progress with fail-closed audit-first write ordering"
```

---

### Task 5: Wire `_reset_active_progress` into `complete_feature()` call site

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:7936-7946`
- Create: `plugins/progress-tracker/tests/test_complete_feature_clears_state.py`

- [ ] **Step 1: Write the failing integration tests**

Create `tests/test_complete_feature_clears_state.py`:

```python
"""Integration tests: complete_feature clears active state when all features done."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log
import progress_manager as pm

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _write_progress, _write_audit_event


def _write_full_completed_project(state_dir, feature_count=2):
    """Write progress.json with all features completed."""
    features = [
        {"id": i + 1, "name": f"F{i+1}", "completed": True,
         "development_stage": "completed", "lifecycle_state": "archived",
         "completed_at": f"2026-01-0{i+2}T00:00:00Z",
         "commit_hash": f"abc{i+1}"}
        for i in range(feature_count)
    ]
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": features,
        "current_feature_id": None,
        "bugs": [{"id": "BUG-001", "description": "test bug", "status": "fixed"}],
        "updates": [{"id": "UPD-001", "summary": "test update"}],
        "retrospectives": [{"id": "RET-001", "summary": "test retro"}],
        "current_bug_id": "BUG-001",
    }
    path = state_dir / "progress.json"
    path.write_text(json.dumps(data))
    return data


class TestCompleteFeatureClearsState:
    def test_clears_active_state_on_last_feature(self, project_scope):
        """complete_feature on the last feature clears features/bugs/updates/retrospectives."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=2)

        pm.complete_feature(feature_id=2, skip_archive=True)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []
        assert data["bugs"] == []
        assert data["updates"] == []
        assert data["retrospectives"] == []
        assert data["current_feature_id"] is None
        assert data["current_bug_id"] is None

    def test_clears_with_skip_archive(self, project_scope):
        """_reset_active_progress runs even with skip_archive=True."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1)

        pm.complete_feature(feature_id=1, skip_archive=True)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []

    def test_clears_when_archive_throws(self, project_scope):
        """_reset_active_progress runs even if archive_current_progress raises."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1)

        with patch.object(pm, "archive_current_progress", side_effect=OSError("disk full")):
            pm.complete_feature(feature_id=1, skip_archive=False)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        assert data["features"] == []

    def test_records_project_completed_event(self, project_scope):
        """complete_feature on last feature writes project_completed to audit.log."""
        _write_full_completed_project(project_scope["state_dir"], feature_count=1)

        pm.complete_feature(feature_id=1, skip_archive=True)

        records = audit_log.read_audit_log(
            ascending=True, project_root=str(project_scope["root"]))
        assert any(r["event_type"] == "project_completed" for r in records)

    def test_does_not_clear_if_not_fully_completed(self, project_scope):
        """If not all features are complete, _reset_active_progress is NOT called."""
        features = [
            {"id": 1, "name": "F1", "completed": True,
             "development_stage": "completed", "commit_hash": "abc1"},
            {"id": 2, "name": "F2", "completed": False},
        ]
        _write_progress(project_scope["state_dir"], features, current_id=None)
        # Write full data dict manually for extra fields
        path = project_scope["state_dir"] / "progress.json"
        data = json.loads(path.read_text())
        data["bugs"] = [{"id": "BUG-001", "description": "test bug", "status": "fixed"}]
        path.write_text(json.dumps(data))

        pm.complete_feature(feature_id=1, skip_archive=True)

        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        # bugs should still be there — reset not triggered
        assert len(data["bugs"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_complete_feature_clears_state.py -v`
Expected: FAIL — `_reset_active_progress` not yet called from `complete_feature`

- [ ] **Step 3: Wire `_reset_active_progress` into `complete_feature()`**

Modify `complete_feature()` in `progress_manager.py`. Find the block starting at line ~7936:

```python
        refreshed = load_progress_json()
        if refreshed and _is_project_fully_completed(refreshed):
            completed_archive = archive_current_progress(reason="completed")
            if completed_archive:
                print(
                    "Archived completed run as "
                    f"{completed_archive.get('archive_id')} "
                    f"(reason={completed_archive.get('reason')})"
                )

        return True
```

Replace with:

```python
        refreshed = load_progress_json()
        if refreshed and _is_project_fully_completed(refreshed):
            try:
                completed_archive = archive_current_progress(reason="completed")
                if completed_archive:
                    print(
                        "Archived completed run as "
                        f"{completed_archive.get('archive_id')} "
                        f"(reason={completed_archive.get('reason')})"
                    )
            except Exception as e:
                # Archive I/O can fail (mkdir, copy2, save_history).
                # Best-effort: log and continue — reset must still happen.
                logger.error(f"Completed-run archive failed: {e}")
                print(f"Warning: Completed-run archive failed, but active state will still be cleared.")

    # ── Outside if not skip_archive — always runs ──
    refreshed = load_progress_json()
    if refreshed and _is_project_fully_completed(refreshed):
        _reset_active_progress(refreshed)

    return True
```

**Important**: The second `refreshed = load_progress_json()` and the `_is_project_fully_completed` / `_reset_active_progress` block must be **outside** the `if not skip_archive` block. The first `refreshed` block (with `archive_current_progress`) stays inside `if not skip_archive`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_complete_feature_clears_state.py tests/test_reset_active_progress.py -v`
Expected: PASS

- [ ] **Step 5: Run full regression**

Run: `cd plugins/progress-tracker && python -m pytest tests/ -v --tb=short`
Expected: All existing tests pass, new tests pass

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py plugins/progress-tracker/tests/test_complete_feature_clears_state.py
git commit -m "feat(complete_feature): wire _reset_active_progress outside skip_archive gate"
```

---

### Task 6: Run full test suite and fix any regressions

**Files:** None new — validation only

- [ ] **Step 1: Run full PT test suite**

Run: `cd plugins/progress-tracker && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Run reconcile and backfill tests specifically**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_reconcile_state.py tests/test_backfill_event.py tests/test_audit_log_whitelist.py -v`
Expected: All pass

- [ ] **Step 3: Verify no regressions in done/cleanup tests**

Run: `cd plugins/progress-tracker && python -m pytest tests/test_auto_archive_on_completion.py tests/test_cleanup_after_done.py tests/test_cmd_done_cleanup_integration.py -v`
Expected: All pass

- [ ] **Step 4: Final commit if any fixes needed**

Only commit if fixes were required.

---

## Self-Review Checklist

- [x] **Spec coverage**: Task 1 = audit whitelist, Task 2 = `_replay_audit_events`, Task 3 = `find_backfill_candidates`, Task 4 = `_reset_active_progress` implementation, Task 5 = call site wiring, Task 6 = regression check
- [x] **Placeholder scan**: No TBD/TODO/placeholder steps — all code is concrete
- [x] **Type consistency**: `_reset_active_progress(data: Dict[str, Any])` signature used consistently; `BOUNDARY_EVENT_TYPES` defined in-place in `find_backfill_candidates`; `project_completed` string literal consistent across all files
- [x] **Fail-closed**: Task 4 test `test_fail_closed_on_audit_error` and `test_does_not_save_when_audit_fails` verify audit write failure prevents state clear
- [x] **skip_archive decoupling**: Task 5 `test_clears_with_skip_archive` verifies reset runs outside the gate
- [x] **Archive exception resilience**: Task 5 `test_clears_when_archive_throws` verifies reset runs even when `archive_current_progress` throws