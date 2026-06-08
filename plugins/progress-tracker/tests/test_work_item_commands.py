"""Unit tests for work_item_commands.py extracted from progress_manager.

All tests use mock WorkItemCommandsServices — no filesystem I/O.
Covers the 10 extracted command functions and key behavior contracts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# Ensure hooks/scripts is on path
_HOOKS_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import work_item_commands
from work_item_commands import (
    WorkItemCommandsServices,
    add_feature_command,
    add_retro_command,
    add_task_item_command,
    add_update_command,
    defer_features_command,
    list_updates_command,
    resume_deferred_features_command,
    set_feature_owner_command,
    smart_intake_command,
    update_feature_command,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_svc(data: Dict[str, Any]) -> WorkItemCommandsServices:
    """Build a mock services object backed by a single in-memory dict."""
    saved = {"data": data}

    def load():
        return saved["data"]

    def save(d):
        saved["data"] = d

    def gen_md(d):
        return ""

    def save_md(s):
        pass

    def update_ctx(d, source=None):
        return True

    def notify(event="refresh"):
        pass

    def add_bug_internal(**kwargs):
        bugs = saved["data"].setdefault("bugs", [])
        bug_id = f"BUG-{len(bugs) + 1:03d}"
        bugs.append({"id": bug_id, "priority": kwargs.get("priority", "medium")})
        saved["data"]["bugs"] = bugs
        return True, bug_id

    svc = WorkItemCommandsServices(
        load_progress_json_fn=load,
        save_progress_json_fn=save,
        generate_progress_md_fn=gen_md,
        save_progress_md_fn=save_md,
        update_runtime_context_fn=update_ctx,
        notify_parent_sync_fn=notify,
        add_bug_internal_fn=add_bug_internal,
        find_project_root_fn=lambda: Path("/fake/root"),
    )
    return svc


def _base_data() -> Dict[str, Any]:
    return {
        "features": [],
        "updates": [],
        "retrospectives": [],
        "bugs": [],
        "tasks": [],
        "routing_queue": [],
        "current_feature_id": None,
    }


# ---------------------------------------------------------------------------
# add_update_command
# ---------------------------------------------------------------------------

class TestAddUpdateCommand:
    def test_valid_update(self):
        data = _base_data()
        svc = _make_svc(data)
        result = add_update_command("status", "first update", svc=svc)
        assert result is True
        updates = svc.load_progress_json_fn()["updates"]
        assert len(updates) == 1
        assert updates[0]["id"] == "UPD-001"
        assert updates[0]["category"] == "status"
        assert updates[0]["summary"] == "first update"

    def test_invalid_category_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        result = add_update_command("invalid_cat", "summary", svc=svc)
        assert result is False
        assert svc.load_progress_json_fn()["updates"] == []

    def test_invalid_source_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        result = add_update_command("status", "summary", svc=svc, source="bad_source")
        assert result is False

    def test_empty_summary_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        result = add_update_command("status", "  ", svc=svc)
        assert result is False

    def test_manual_refs_take_priority_over_auto_refs(self):
        """Manual refs must override auto-generated refs even when feature_id is provided."""
        data = _base_data()
        data["features"] = [
            {
                "id": 1,
                "requirement_ids": ["REQ-001"],
                "change_spec": {"change_id": "CHANGE-001"},
            }
        ]
        svc = _make_svc(data)
        manual_refs = ["doc:manual.md"]
        result = add_update_command(
            "decision", "manual wins", svc=svc,
            feature_id=1, refs=manual_refs,
        )
        assert result is True
        update = svc.load_progress_json_fn()["updates"][0]
        # Manual refs override auto-refs
        assert update["refs"] == ["doc:manual.md"]
        assert "req:REQ-001" not in update.get("refs", [])

    def test_auto_refs_applied_when_no_manual_refs(self):
        """Auto refs derived from feature contract when no manual refs given."""
        data = _base_data()
        data["features"] = [
            {"id": 2, "requirement_ids": ["REQ-002"], "change_spec": {}}
        ]
        svc = _make_svc(data)
        result = add_update_command(
            "status", "auto refs test", svc=svc, feature_id=2, refs=None
        )
        assert result is True
        update = svc.load_progress_json_fn()["updates"][0]
        assert "req:REQ-002" in update["refs"]

    def test_refs_overflow_when_exceeds_limit(self):
        """Refs beyond UPDATE_REFS_INLINE_LIMIT go into refs_overflow."""
        data = _base_data()
        svc = _make_svc(data)
        many_refs = [f"doc:file{i}.md" for i in range(20)]
        result = add_update_command("status", "overflow test", svc=svc, refs=many_refs)
        assert result is True
        update = svc.load_progress_json_fn()["updates"][0]
        assert len(update["refs"]) == work_item_commands.UPDATE_REFS_INLINE_LIMIT
        assert "refs_overflow" in update
        assert update["refs_overflow_count"] == 20 - work_item_commands.UPDATE_REFS_INLINE_LIMIT

    def test_sequential_id_generation(self):
        data = _base_data()
        svc = _make_svc(data)
        add_update_command("status", "first", svc=svc)
        add_update_command("decision", "second", svc=svc)
        updates = svc.load_progress_json_fn()["updates"]
        assert updates[0]["id"] == "UPD-001"
        assert updates[1]["id"] == "UPD-002"


# ---------------------------------------------------------------------------
# list_updates_command
# ---------------------------------------------------------------------------

class TestListUpdatesCommand:
    def test_empty_returns_true(self, capsys):
        data = _base_data()
        svc = _make_svc(data)
        result = list_updates_command(svc=svc)
        assert result is True
        assert "No updates" in capsys.readouterr().out

    def test_shows_all_by_default(self, capsys):
        data = _base_data()
        data["updates"] = [
            {"id": "UPD-001", "category": "status", "summary": "one", "source": "manual"},
            {"id": "UPD-002", "category": "decision", "summary": "two", "source": "manual"},
        ]
        svc = _make_svc(data)
        result = list_updates_command(svc=svc)
        assert result is True
        out = capsys.readouterr().out
        assert "UPD-001" in out
        assert "UPD-002" in out

    def test_limit_restricts_output(self, capsys):
        data = _base_data()
        data["updates"] = [
            {"id": f"UPD-{i:03d}", "category": "status", "summary": f"s{i}", "source": "manual"}
            for i in range(1, 5)
        ]
        svc = _make_svc(data)
        result = list_updates_command(limit=2, svc=svc)
        assert result is True
        out = capsys.readouterr().out
        assert "UPD-003" in out
        assert "UPD-004" in out
        assert "UPD-001" not in out

    def test_negative_limit_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        result = list_updates_command(limit=-1, svc=svc)
        assert result is False


# ---------------------------------------------------------------------------
# add_retro_command
# ---------------------------------------------------------------------------

class TestAddRetroCommand:
    def test_valid_retro(self, capsys):
        data = _base_data()
        data["features"] = [{"id": 1}]
        svc = _make_svc(data)
        result = add_retro_command(1, "summary", "root", svc=svc)
        assert result is True
        retros = svc.load_progress_json_fn()["retrospectives"]
        assert len(retros) == 1
        assert retros[0]["id"] == "RETRO-1-001"

    def test_unknown_feature_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        result = add_retro_command(99, "summary", "root", svc=svc)
        assert result is False

    def test_empty_summary_rejected(self):
        data = _base_data()
        data["features"] = [{"id": 1}]
        svc = _make_svc(data)
        result = add_retro_command(1, "", "root", svc=svc)
        assert result is False

    def test_action_items_filtered(self):
        data = _base_data()
        data["features"] = [{"id": 1}]
        svc = _make_svc(data)
        result = add_retro_command(
            1, "summary", "root", svc=svc,
            action_items=["  valid  ", "", "  "],
        )
        assert result is True
        retro = svc.load_progress_json_fn()["retrospectives"][0]
        assert retro["action_items"] == ["valid"]


# ---------------------------------------------------------------------------
# set_feature_owner_command
# ---------------------------------------------------------------------------

class TestSetFeatureOwnerCommand:
    def test_sets_owner(self):
        data = _base_data()
        data["features"] = [{"id": 1, "owners": {}}]
        svc = _make_svc(data)
        result = set_feature_owner_command(1, "architecture", "alice", svc=svc)
        assert result is True
        feat = svc.load_progress_json_fn()["features"][0]
        assert feat["owners"]["architecture"] == "alice"

    def test_clear_owner_with_none_sentinel(self):
        data = _base_data()
        data["features"] = [{"id": 1, "owners": {"architecture": "alice"}}]
        svc = _make_svc(data)
        result = set_feature_owner_command(1, "architecture", "none", svc=svc)
        assert result is True
        feat = svc.load_progress_json_fn()["features"][0]
        assert feat["owners"]["architecture"] is None

    def test_invalid_role_rejected(self):
        data = _base_data()
        data["features"] = [{"id": 1}]
        svc = _make_svc(data)
        result = set_feature_owner_command(1, "bad_role", "alice", svc=svc)
        assert result is False

    def test_unknown_feature_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        result = set_feature_owner_command(99, "coding", "bob", svc=svc)
        assert result is False


# ---------------------------------------------------------------------------
# add_feature_command
# ---------------------------------------------------------------------------

class TestAddFeatureCommand:
    def test_adds_feature_with_incremented_id(self):
        data = _base_data()
        data["features"] = [{"id": 5, "name": "existing"}]
        svc = _make_svc(data)

        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=None
        ):
            result = add_feature_command("new feature", [], svc=svc)

        assert result is True
        features = svc.load_progress_json_fn()["features"]
        assert len(features) == 2
        assert features[-1]["id"] == 6
        assert features[-1]["name"] == "new feature"

    def test_contract_import_success_applies_contract(self):
        """Contract fields should be merged when import succeeds."""
        data = _base_data()
        svc = _make_svc(data)
        contract = {
            "requirement_ids": ["REQ-100"],
            "change_spec": {"why": "test"},
            "acceptance_scenarios": ["Scenario: works"],
        }
        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=contract
        ):
            result = add_feature_command("contracted feature", [], svc=svc)

        assert result is True
        feat = svc.load_progress_json_fn()["features"][0]
        assert feat["requirement_ids"] == ["REQ-100"]
        assert feat["acceptance_scenarios"] == ["Scenario: works"]

    def test_contract_import_error_aborts(self):
        """ContractImportError must abort feature creation."""
        data = _base_data()
        svc = _make_svc(data)
        with patch.object(
            work_item_commands.ContractImporter,
            "import_for_feature",
            side_effect=work_item_commands.ContractImportError("bad contract"),
        ):
            result = add_feature_command("broken feature", [], svc=svc)

        assert result is False
        assert svc.load_progress_json_fn()["features"] == []

    def test_default_workflow_profile_applied(self):
        data = _base_data()
        svc = _make_svc(data)
        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=None
        ):
            add_feature_command("feat", [], svc=svc)
        feat = svc.load_progress_json_fn()["features"][0]
        assert feat["workflow_profile"] == work_item_commands.WORKFLOW_PROFILE_DEFAULT

    def test_notify_parent_sync_is_called(self):
        data = _base_data()
        svc = _make_svc(data)
        svc.notify_parent_sync_fn = MagicMock()
        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=None
        ):
            result = add_feature_command("new feature", [], svc=svc)
        assert result is True
        svc.notify_parent_sync_fn.assert_called_once_with("refresh")


# ---------------------------------------------------------------------------
# update_feature_command
# ---------------------------------------------------------------------------

class TestUpdateFeatureCommand:
    def test_updates_name(self):
        data = _base_data()
        data["features"] = [{"id": 1, "name": "old"}]
        svc = _make_svc(data)
        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=None
        ):
            result = update_feature_command(1, "new name", svc=svc)
        assert result is True
        assert svc.load_progress_json_fn()["features"][0]["name"] == "new name"

    def test_updates_test_steps(self):
        data = _base_data()
        data["features"] = [{"id": 1, "name": "feat", "test_steps": []}]
        svc = _make_svc(data)
        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=None
        ):
            result = update_feature_command(1, "feat", svc=svc, test_steps=["step 1"])
        assert result is True
        assert svc.load_progress_json_fn()["features"][0]["test_steps"] == ["step 1"]

    def test_contract_import_error_aborts(self):
        data = _base_data()
        data["features"] = [{"id": 1, "name": "feat"}]
        svc = _make_svc(data)
        with patch.object(
            work_item_commands.ContractImporter,
            "import_for_feature",
            side_effect=work_item_commands.ContractImportError("broken"),
        ):
            result = update_feature_command(1, "new name", svc=svc)
        assert result is False

    def test_unknown_feature_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=None
        ):
            result = update_feature_command(99, "name", svc=svc)
        assert result is False

    def test_empty_name_rejected(self):
        data = _base_data()
        data["features"] = [{"id": 1, "name": "feat"}]
        svc = _make_svc(data)
        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=None
        ):
            result = update_feature_command(1, "  ", svc=svc)
        assert result is False


# ---------------------------------------------------------------------------
# defer_features_command
# ---------------------------------------------------------------------------

class TestDeferFeaturesCommand:
    def test_defer_single_feature(self):
        data = _base_data()
        data["features"] = [{"id": 1, "completed": False, "deferred": False}]
        svc = _make_svc(data)
        result = defer_features_command(1, False, "not ready", svc=svc)
        assert result is True
        feat = svc.load_progress_json_fn()["features"][0]
        assert feat["deferred"] is True
        assert feat["defer_reason"] == "not ready"

    def test_defer_all_pending(self):
        data = _base_data()
        data["features"] = [
            {"id": 1, "completed": False, "deferred": False},
            {"id": 2, "completed": False, "deferred": False},
            {"id": 3, "completed": True, "deferred": False},
        ]
        svc = _make_svc(data)
        result = defer_features_command(None, True, "freeze", svc=svc)
        assert result is True
        features = svc.load_progress_json_fn()["features"]
        pending = [f for f in features if not f.get("completed")]
        assert all(f["deferred"] for f in pending)

    def test_clears_active_feature_when_deferred(self):
        data = _base_data()
        data["current_feature_id"] = 1
        data["workflow_state"] = {"phase": "execution"}
        data["features"] = [{"id": 1, "completed": False, "deferred": False}]
        svc = _make_svc(data)
        defer_features_command(1, False, "paused", svc=svc)
        saved = svc.load_progress_json_fn()
        assert saved["current_feature_id"] is None
        assert "workflow_state" not in saved

    def test_empty_reason_rejected(self):
        data = _base_data()
        data["features"] = [{"id": 1, "completed": False}]
        svc = _make_svc(data)
        result = defer_features_command(1, False, "", svc=svc)
        assert result is False

    def test_update_runtime_context_is_called(self):
        data = _base_data()
        data["features"] = [{"id": 1, "completed": False, "deferred": False}]
        svc = _make_svc(data)
        svc.update_runtime_context_fn = MagicMock(return_value=True)
        result = defer_features_command(1, False, "paused", svc=svc)
        assert result is True
        svc.update_runtime_context_fn.assert_called_once()
        _, kwargs = svc.update_runtime_context_fn.call_args
        assert kwargs.get("source") == "defer"


# ---------------------------------------------------------------------------
# resume_deferred_features_command
# ---------------------------------------------------------------------------

class TestResumeDeferredFeaturesCommand:
    def test_resume_by_group(self):
        data = _base_data()
        data["features"] = [
            {"id": 1, "completed": False, "deferred": True, "defer_group": "sprint-3", "defer_reason": "x", "deferred_at": "now"},
            {"id": 2, "completed": False, "deferred": True, "defer_group": "sprint-4", "defer_reason": "y", "deferred_at": "now"},
        ]
        svc = _make_svc(data)
        result = resume_deferred_features_command("sprint-3", False, svc=svc)
        assert result is True
        features = svc.load_progress_json_fn()["features"]
        assert features[0]["deferred"] is False
        assert features[1]["deferred"] is True

    def test_resume_all(self):
        data = _base_data()
        data["features"] = [
            {"id": 1, "completed": False, "deferred": True, "defer_group": "a", "defer_reason": "x", "deferred_at": "now"},
            {"id": 2, "completed": False, "deferred": True, "defer_group": "b", "defer_reason": "y", "deferred_at": "now"},
        ]
        svc = _make_svc(data)
        result = resume_deferred_features_command(None, True, svc=svc)
        assert result is True
        features = svc.load_progress_json_fn()["features"]
        assert all(not f["deferred"] for f in features)

    def test_no_matching_group_returns_false(self):
        data = _base_data()
        data["features"] = [
            {"id": 1, "completed": False, "deferred": True, "defer_group": "sprint-3"}
        ]
        svc = _make_svc(data)
        result = resume_deferred_features_command("nonexistent", False, svc=svc)
        assert result is False

    def test_update_runtime_context_is_called(self):
        data = _base_data()
        data["features"] = [
            {"id": 1, "completed": False, "deferred": True, "defer_group": "g", "defer_reason": "x", "deferred_at": "now"}
        ]
        svc = _make_svc(data)
        svc.update_runtime_context_fn = MagicMock(return_value=True)
        result = resume_deferred_features_command("g", False, svc=svc)
        assert result is True
        svc.update_runtime_context_fn.assert_called_once()
        _, kwargs = svc.update_runtime_context_fn.call_args
        assert kwargs.get("source") == "resume"


# ---------------------------------------------------------------------------
# add_task_item_command
# ---------------------------------------------------------------------------

class TestAddTaskItemCommand:
    def test_creates_task(self):
        data = _base_data()
        svc = _make_svc(data)
        task_id = add_task_item_command("do something", svc=svc)
        assert task_id == "TASK-001"
        tasks = svc.load_progress_json_fn()["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["description"] == "do something"

    def test_invalid_priority_raises(self):
        data = _base_data()
        svc = _make_svc(data)
        with pytest.raises(ValueError, match="Invalid priority"):
            add_task_item_command("task", svc=svc, priority="P9")

    def test_empty_description_raises(self):
        data = _base_data()
        svc = _make_svc(data)
        with pytest.raises(ValueError, match="cannot be empty"):
            add_task_item_command("", svc=svc)

    def test_description_too_long_raises(self):
        data = _base_data()
        svc = _make_svc(data)
        with pytest.raises(ValueError, match="too long"):
            add_task_item_command("x" * 2001, svc=svc)

    def test_invalid_workflow_profile_raises(self):
        data = _base_data()
        svc = _make_svc(data)
        with pytest.raises(ValueError, match="Invalid workflow_profile"):
            add_task_item_command("task", svc=svc, workflow_profile="bad_profile")

    def test_sequential_id_generation(self):
        data = _base_data()
        svc = _make_svc(data)
        id1 = add_task_item_command("first", svc=svc)
        id2 = add_task_item_command("second", svc=svc)
        assert id1 == "TASK-001"
        assert id2 == "TASK-002"


# ---------------------------------------------------------------------------
# smart_intake_command
# ---------------------------------------------------------------------------

class TestSmartIntakeCommand:
    def _candidate(self, type_: str, confidence: float = 0.9, **profile_extra) -> str:
        profile = {"description": "test item", **profile_extra}
        return json.dumps({"type": type_, "confidence": confidence, "profile": profile})

    def test_preview_mode_no_mutation(self, capsys):
        data = _base_data()
        svc = _make_svc(data)
        result = smart_intake_command(self._candidate("feature"), svc=svc)
        assert result is True
        saved = svc.load_progress_json_fn()
        assert saved["features"] == []

    def test_low_confidence_shows_clarification(self, capsys):
        data = _base_data()
        svc = _make_svc(data)
        result = smart_intake_command(self._candidate("bug", confidence=0.4), svc=svc)
        assert result is True
        out = capsys.readouterr().out
        assert "needs_clarification" in out

    def test_commit_bug_writes_and_pushes_routing_queue(self):
        """commit=bug must write to bugs[] AND push bug id into routing_queue."""
        data = _base_data()
        svc = _make_svc(data)
        result = smart_intake_command(
            self._candidate("bug", priority="P0"),
            svc=svc, commit="bug",
        )
        assert result is True
        saved = svc.load_progress_json_fn()
        assert len(saved["bugs"]) == 1
        bug_id = saved["bugs"][0]["id"]
        # Bug must be in routing_queue
        assert bug_id in saved["routing_queue"]

    def test_commit_bug_high_priority_inserted_before_lower(self):
        """P0 (high) bug must be inserted before existing P1 (medium) bug in routing_queue."""
        data = _base_data()
        # Pre-populate a medium-priority bug in the queue
        data["bugs"] = [{"id": "BUG-001", "priority": "medium"}]
        data["routing_queue"] = ["BUG-001"]
        svc = _make_svc(data)

        # Override add_bug_internal to return a known ID at high priority
        def add_bug_high(**kwargs):
            data["bugs"].append({"id": "BUG-002", "priority": "high"})
            return True, "BUG-002"

        svc = WorkItemCommandsServices(
            load_progress_json_fn=svc.load_progress_json_fn,
            save_progress_json_fn=svc.save_progress_json_fn,
            generate_progress_md_fn=svc.generate_progress_md_fn,
            save_progress_md_fn=svc.save_progress_md_fn,
            update_runtime_context_fn=svc.update_runtime_context_fn,
            notify_parent_sync_fn=svc.notify_parent_sync_fn,
            add_bug_internal_fn=add_bug_high,
            find_project_root_fn=svc.find_project_root_fn,
        )
        result = smart_intake_command(
            self._candidate("bug", priority="P0"), svc=svc, commit="bug"
        )
        assert result is True
        queue = svc.load_progress_json_fn()["routing_queue"]
        assert queue[0] == "BUG-002"  # high priority first

    def test_commit_task_creates_task(self):
        data = _base_data()
        svc = _make_svc(data)
        result = smart_intake_command(
            self._candidate("task"), svc=svc, commit="task"
        )
        assert result is True
        assert len(svc.load_progress_json_fn()["tasks"]) == 1

    def test_commit_feature_creates_feature(self):
        data = _base_data()
        svc = _make_svc(data)
        with patch.object(
            work_item_commands.ContractImporter, "import_for_feature", return_value=None
        ):
            result = smart_intake_command(
                self._candidate("feature"), svc=svc, commit="feature"
            )
        assert result is True
        assert len(svc.load_progress_json_fn()["features"]) == 1

    def test_commit_update_creates_update(self):
        data = _base_data()
        svc = _make_svc(data)
        candidate = json.dumps({
            "type": "update",
            "confidence": 0.9,
            "profile": {"description": "a decision", "category": "decision"},
        })
        result = smart_intake_command(candidate, svc=svc, commit="update")
        assert result is True
        updates = svc.load_progress_json_fn()["updates"]
        assert len(updates) == 1
        assert updates[0]["category"] == "decision"

    def test_invalid_json_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        result = smart_intake_command("not json", svc=svc)
        assert result is False

    def test_invalid_type_rejected(self):
        data = _base_data()
        svc = _make_svc(data)
        result = smart_intake_command(
            json.dumps({"type": "alien", "confidence": 0.9, "profile": {"description": "x"}}),
            svc=svc,
        )
        assert result is False

    def test_unknown_commit_type_rejected(self, capsys):
        data = _base_data()
        svc = _make_svc(data)
        result = smart_intake_command(
            self._candidate("task"), svc=svc, commit="unknown"
        )
        assert result is False
        assert "unknown commit type" in capsys.readouterr().out
