#!/usr/bin/env python3
"""Integration tests for SPM -> PROG beta synchronization flow."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PROG_SCRIPT_DIR = REPO_ROOT / "plugins" / "progress-tracker" / "hooks" / "scripts"
SPM_SCRIPT_DIR = REPO_ROOT / "plugins" / "super-product-manager" / "scripts"

sys.path.insert(0, str(PROG_SCRIPT_DIR))
sys.path.insert(0, str(SPM_SCRIPT_DIR))

import progress_manager
import meeting_workflow


def _reset_prog_module_state() -> None:
    progress_manager._PROJECT_ROOT_OVERRIDE = None
    progress_manager._REPO_ROOT = None
    progress_manager._STORAGE_READY_ROOT = None


def _init_temp_progress_project(project_root: Path) -> None:
    _reset_prog_module_state()
    features = [
        {
            "id": 1,
            "name": "Feature A",
            "test_steps": ["Step 1"],
            "completed": False,
        },
        {
            "id": 2,
            "name": "Feature B",
            "test_steps": ["Step 2"],
            "completed": False,
        },
    ]
    assert progress_manager.init_tracking("SPM-PROG Beta", features=features, force=True)


def test_meeting_creates_artifacts_and_syncs_meeting_update(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_temp_progress_project(tmp_path)

    result = meeting_workflow.create_meeting_record(
        topic="beta kickoff",
        summary="Kickoff aligned scope and risks",
        decisions=["Freeze beta scope"],
        action_items=["Create integration tests"],
        refs=["docs/plans/2026-03-09-spm-prog-beta-design.md"],
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert Path(result["meeting_file"]).exists()
    assert Path(result["action_items_file"]).exists()
    assert result["sync"]["ok"] is True

    data = progress_manager.load_progress_json()
    updates = data["updates"]
    assert any(
        item["category"] == "meeting"
        and item["summary"] == "Kickoff aligned scope and risks"
        and item["source"] == "spm_meeting"
        for item in updates
    )


def test_assign_sets_feature_owner_and_writes_assignment_update(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_temp_progress_project(tmp_path)

    result = meeting_workflow.assign_feature_owner(
        feature_id=1,
        role="coding",
        owner="alice",
        note="Alice owns coding stream",
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["sync"]["owner_result"]["ok"] is True
    assert result["sync"]["update_result"]["ok"] is True

    data = progress_manager.load_progress_json()
    feature = next(f for f in data["features"] if f["id"] == 1)
    assert feature["owners"]["coding"] == "alice"

    assert any(
        item["category"] == "assignment"
        and item["feature_id"] == 1
        and item["role"] == "coding"
        and item["owner"] == "alice"
        for item in data["updates"]
    )


def test_followup_sync_failure_does_not_block_action_item_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_temp_progress_project(tmp_path)

    seed = meeting_workflow.create_meeting_record(
        topic="followup-seed",
        summary="Seed meeting",
        decisions=["Track blocker"],
        action_items=["Resolve staging issue"],
        project_root=tmp_path,
    )
    assert seed["ok"] is True
    action_id = seed["action_item_ids"][0]

    monkeypatch.setattr(
        meeting_workflow.prog_bridge,
        "sync_followup",
        lambda **kwargs: {"ok": False, "error": "prog_failed", "stderr": "simulated"},
    )

    result = meeting_workflow.followup_action_item(
        action_id=action_id,
        status="blocked",
        note="Blocked by unavailable staging env",
        feature_id=1,
        next_action="Request staging access",
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["sync"]["ok"] is False
    assert result["sync_errors"]

    action_items_path = Path(result["action_items_file"])
    payload = json.loads(action_items_path.read_text(encoding="utf-8"))
    updated = next(item for item in payload if item["id"] == action_id)
    assert updated["status"] == "blocked"
    assert updated["summary"] == "Blocked by unavailable staging env"
