"""Tests for automatic run archival when all features are completed."""

from __future__ import annotations

import json
import re
from pathlib import Path

import progress_manager


def test_auto_archive_triggers_when_last_feature_is_completed(temp_dir):
    """Completing the final feature should archive the whole run and index it."""
    assert progress_manager.init_tracking("Completion Run", force=True) is True
    assert progress_manager.add_feature("Final Feature", ["echo ok"]) is True
    assert progress_manager.set_current(1) is True

    assert progress_manager.complete_feature(1) is True

    history = progress_manager._load_progress_history()
    assert len(history) == 1

    entry = history[0]
    assert entry["reason"] == "completed"
    assert entry["project_name"] == "Completion Run"
    assert entry["completed_features"] == 1
    assert entry["total_features"] == 1
    assert entry["current_feature_id"] is None

    progress_json_rel = entry.get("progress_json")
    assert isinstance(progress_json_rel, str)
    assert re.match(
        r"^progress_archive/\d{8}T\d{12}-completion-run-completed\.progress\.json$",
        progress_json_rel,
    )

    progress_md_rel = entry.get("progress_md")
    assert isinstance(progress_md_rel, str)
    assert re.match(
        r"^progress_archive/\d{8}T\d{12}-completion-run-completed\.progress\.md$",
        progress_md_rel,
    )

    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    archived_json = state_dir / progress_json_rel
    archived_md = state_dir / progress_md_rel
    assert archived_json.exists()
    assert archived_md.exists()
    assert (state_dir / "progress_history.json").exists()

    archived_payload = json.loads(archived_json.read_text(encoding="utf-8"))
    assert archived_payload["project_name"] == "Completion Run"
    assert archived_payload["current_feature_id"] is None
    assert archived_payload["features"][0]["completed"] is True


def test_auto_archive_skips_when_project_is_not_fully_completed(temp_dir):
    """Completing a non-final feature must not create a completion archive entry."""
    assert progress_manager.init_tracking("Partial Run", force=True) is True
    assert progress_manager.add_feature("Feature A", ["echo a"]) is True
    assert progress_manager.add_feature("Feature B", ["echo b"]) is True
    assert progress_manager.set_current(1) is True

    assert progress_manager.complete_feature(1) is True

    history = progress_manager._load_progress_history()
    completed_entries = [item for item in history if item.get("reason") == "completed"]
    assert completed_entries == []

    progress_data = progress_manager.load_progress_json()
    assert isinstance(progress_data, dict)
    assert progress_data["features"][0]["completed"] is True
    assert progress_data["features"][1]["completed"] is False
