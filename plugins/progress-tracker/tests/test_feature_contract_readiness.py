"""Tests for feature contract readiness, lifecycle transitions, and retro separation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


@pytest.fixture
def temp_dir(tmp_path):
    """Run each test in an isolated directory."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)


def test_load_progress_json_backfills_feature_contract_defaults(temp_dir):
    """Legacy feature entries should gain contract defaults on load."""
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_name": "Legacy",
        "created_at": "2026-03-09T00:00:00Z",
        "features": [
            {
                "id": 7,
                "name": "Search API",
                "test_steps": ["curl /search", "assert 200"],
                "completed": False,
            }
        ],
        "current_feature_id": 7,
    }
    (state_dir / "progress.json").write_text(json.dumps(payload), encoding="utf-8")

    data = progress_manager.load_progress_json()
    feature = data["features"][0]

    assert feature["lifecycle_state"] == "approved"
    assert feature["requirement_ids"] == ["REQ-007"]
    assert feature["change_spec"]["why"]
    assert feature["change_spec"]["in_scope"]
    assert feature["change_spec"]["out_of_scope"]
    assert feature["change_spec"]["risks"]
    assert feature["acceptance_scenarios"]


def test_requirement_ids_change_spec_acceptance_scenarios_defaults(temp_dir):
    """Keyword-targeted test for CLI acceptance command filtering."""
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_name": "Legacy",
        "created_at": "2026-03-09T00:00:00Z",
        "features": [{"id": 11, "name": "Import Contracts", "test_steps": ["step"], "completed": False}],
        "current_feature_id": 11,
    }
    (state_dir / "progress.json").write_text(json.dumps(payload), encoding="utf-8")

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    assert feature["requirement_ids"] == ["REQ-011"]
    assert feature["change_spec"]["why"]
    assert feature["acceptance_scenarios"]


def test_validate_feature_readiness_detects_missing_contract_fields(temp_dir):
    """Readiness validator should reject incomplete feature contracts."""
    feature = {
        "id": 3,
        "name": "Billing",
        "test_steps": ["run billing smoke test"],
        "completed": False,
        "lifecycle_state": "approved",
        "requirement_ids": [],
        "acceptance_scenarios": [],
        "change_spec": {
            "why": "",
            "in_scope": [],
            "out_of_scope": [],
            "risks": [],
        },
    }

    report = progress_manager.validate_feature_readiness(feature)

    assert report["valid"] is False
    assert any("requirement_ids" in err for err in report["errors"])
    assert any("acceptance_scenarios" in err for err in report["errors"])
    assert any("change_spec.why" in err for err in report["errors"])


def test_set_development_stage_developing_requires_readiness(temp_dir):
    """/prog-next start path should fail if feature readiness contract is invalid."""
    progress_manager.init_tracking("Readiness Gate", force=True)
    progress_manager.add_feature("Feature A", ["step 1"])
    progress_manager.set_current(1)

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = []
    feature["acceptance_scenarios"] = []
    feature["change_spec"] = {"why": "", "in_scope": [], "out_of_scope": [], "risks": []}
    progress_manager.save_progress_json(data)

    assert progress_manager.set_development_stage("developing") is False


def test_prog_next_blocks_when_any_feature_has_finish_pending(temp_dir, capsys):
    """`/prog-next` should refuse to advance while any feature is in finish_pending."""
    progress_manager.init_tracking("Block Next", force=True)
    progress_manager.add_feature("Feature A", ["step 1"])

    data = progress_manager.load_progress_json()
    data["features"][0]["integration_status"] = "finish_pending"
    data["features"][0]["finish_pending_reason"] = "manual test"
    progress_manager.save_progress_json(data)

    result = progress_manager.next_feature(output_json=True)
    assert result is False

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["status"] == "blocked"
    assert payload["reason"] == "finish_pending"
    assert "set-finish-state" in payload["message"]


def test_lifecycle_transitions_from_start_to_complete(temp_dir):
    """Feature lifecycle should move approved -> implementing -> verified."""
    progress_manager.init_tracking("Lifecycle", force=True)
    progress_manager.add_feature("Feature B", ["step 1"])
    progress_manager.set_current(1)
    assert progress_manager.set_development_stage("developing") is True

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    assert feature["lifecycle_state"] == "implementing"

    assert progress_manager.complete_feature(1, skip_archive=True) is True

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    assert feature["lifecycle_state"] == "verified"


def test_complete_feature_sets_archived_lifecycle_when_archive_succeeds(temp_dir, monkeypatch):
    """Successful archive should move lifecycle verified -> archived."""
    progress_manager.init_tracking("Archive Lifecycle", force=True)
    progress_manager.add_feature("Feature C", ["step 1"])
    progress_manager.set_current(1)
    assert progress_manager.set_development_stage("developing") is True

    def fake_archive(_feature_id, _feature_name=None):
        return {"success": True, "archived_files": [], "skipped_files": [], "errors": []}

    monkeypatch.setattr(progress_manager, "archive_feature_docs", fake_archive)

    assert progress_manager.complete_feature(1, skip_archive=False) is True

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    assert feature["lifecycle_state"] == "archived"


def test_add_retro_is_separate_from_archive_records(temp_dir):
    """Retrospectives should be stored separately from archive_info."""
    progress_manager.init_tracking("Retro", force=True)
    progress_manager.add_feature("Feature D", ["step 1"])

    assert progress_manager.add_retro(
        feature_id=1,
        summary="Found flaky fixture ordering issue",
        root_cause="Fixture setup had hidden ordering dependency",
        action_items=["Stabilize fixture setup", "Add regression test"],
    ) is True

    data = progress_manager.load_progress_json()
    assert "retrospectives" in data
    assert len(data["retrospectives"]) == 1
    entry = data["retrospectives"][0]
    assert entry["feature_id"] == 1
    assert entry["summary"]

    feature = data["features"][0]
    assert "archive_info" not in feature


def test_add_update_auto_attaches_requirement_refs(temp_dir):
    """Updates linked to feature should include requirement refs automatically."""
    progress_manager.init_tracking("Refs", force=True)
    progress_manager.add_feature("Feature E", ["step 1"])

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = ["REQ-001", "REQ-010"]
    feature["change_spec"]["change_id"] = "CHG-auth-login"
    progress_manager.save_progress_json(data)

    assert progress_manager.add_update(
        category="status",
        summary="Kickoff complete",
        feature_id=1,
        source="manual",
    ) is True

    data = progress_manager.load_progress_json()
    refs = data["updates"][-1]["refs"]
    assert "req:REQ-001" in refs
    assert "req:REQ-010" in refs
    assert "change:CHG-auth-login" in refs


def test_add_update_refs_overflow_is_captured_without_dropping_data(temp_dir):
    """Auto refs should be compacted with overflow preserved in dedicated fields."""
    progress_manager.init_tracking("Refs Overflow", force=True)
    progress_manager.add_feature("Feature F", ["step 1"])

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = [f"REQ-{idx:03d}" for idx in range(1, 21)]
    feature["change_spec"]["change_id"] = "CHG-bulk-import"
    progress_manager.save_progress_json(data)

    assert progress_manager.add_update(
        category="status",
        summary="Large refs payload",
        feature_id=1,
        source="manual",
    ) is True

    data = progress_manager.load_progress_json()
    update = data["updates"][-1]
    assert len(update["refs"]) == progress_manager.UPDATE_REFS_INLINE_LIMIT
    assert update["refs_overflow_count"] == len(update["refs_overflow"])

    all_refs = update["refs"] + update["refs_overflow"]
    assert len(all_refs) == 21
    assert "change:CHG-bulk-import" in all_refs


def test_add_update_manual_refs_are_protected_from_auto_injection(temp_dir):
    """Explicit refs should remain authoritative and not merge auto refs."""
    progress_manager.init_tracking("Refs Manual", force=True)
    progress_manager.add_feature("Feature G", ["step 1"])

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = ["REQ-001", "REQ-002"]
    feature["change_spec"]["change_id"] = "CHG-should-not-appear"
    progress_manager.save_progress_json(data)

    assert progress_manager.add_update(
        category="status",
        summary="Manual refs only",
        feature_id=1,
        source="manual",
        refs=["manual:ticket-123", "req:REQ-manual", "manual:ticket-123", " "],
    ) is True

    data = progress_manager.load_progress_json()
    update = data["updates"][-1]
    assert update["refs"] == ["manual:ticket-123", "req:REQ-manual"]
    assert "refs_overflow" not in update
