"""Regression tests for re-init archive naming and traceability metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path

import progress_manager


def test_reinit_archives_progress_and_status_files_with_traceable_metadata(temp_dir):
    """Force re-init should archive active progress + status files with traceable metadata."""
    assert progress_manager.init_tracking("First Project", force=True) is True
    assert progress_manager.add_feature("Feature A", ["step-a"]) is True

    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    status_v1 = state_dir / "status_summary.v1.json"
    legacy_status = state_dir / "status_summary.json"
    status_v1.write_text(
        json.dumps({"schema_version": "status_summary.v1", "progress": {"completed": 0}}),
        encoding="utf-8",
    )
    legacy_status.write_text(
        json.dumps({"schema_version": "legacy", "progress": {"completed": 0}}),
        encoding="utf-8",
    )

    assert progress_manager.init_tracking("Second Project", force=True) is True

    history = progress_manager._load_progress_history()
    assert len(history) == 1

    entry = history[0]
    assert entry["reason"] == "reinitialize"
    assert entry["project_name"] == "First Project"
    assert isinstance(entry.get("archive_id"), str)

    archived_artifacts = entry.get("archived_artifacts")
    assert isinstance(archived_artifacts, list)

    by_kind = {
        item["kind"]: item
        for item in archived_artifacts
        if isinstance(item, dict) and isinstance(item.get("kind"), str)
    }
    assert {"progress_json", "progress_md", "status_summary_v1", "status_summary_legacy"} <= set(
        by_kind
    )

    state_root = Path("docs/progress-tracker/state")
    progress_json_rel = by_kind["progress_json"]["archive_path"]
    progress_md_rel = by_kind["progress_md"]["archive_path"]
    status_v1_rel = by_kind["status_summary_v1"]["archive_path"]
    status_legacy_rel = by_kind["status_summary_legacy"]["archive_path"]

    assert re.match(
        r"^progress_archive/\d{8}T\d{12}-first-project-reinitialize\.progress\.json$",
        progress_json_rel,
    )
    assert re.match(
        r"^progress_archive/\d{8}T\d{12}-first-project-reinitialize\.progress\.md$",
        progress_md_rel,
    )
    assert re.match(
        r"^progress_archive/\d{8}T\d{12}-first-project-reinitialize\.status-summary\.v1\.json$",
        status_v1_rel,
    )
    assert re.match(
        r"^progress_archive/\d{8}T\d{12}-first-project-reinitialize\.status-summary\.legacy\.json$",
        status_legacy_rel,
    )

    assert (state_root / progress_json_rel).exists()
    assert (state_root / progress_md_rel).exists()
    assert (state_root / status_v1_rel).exists()
    assert (state_root / status_legacy_rel).exists()

    archived_payload = json.loads((state_root / progress_json_rel).read_text(encoding="utf-8"))
    assert archived_payload["project_name"] == "First Project"
    assert archived_payload["features"][0]["name"] == "Feature A"


def test_reinit_archive_ids_are_collision_safe_and_history_is_not_overwritten(
    temp_dir, monkeypatch
):
    """Repeated force re-init must not overwrite older archived snapshots on archive-id collision."""
    assert progress_manager.init_tracking("Original Project", force=True) is True
    assert progress_manager.add_feature("Feature Original", ["step-original"]) is True

    monkeypatch.setattr(
        progress_manager,
        "_make_archive_id",
        lambda project_name, reason=None: "fixed-reinit-archive-id",
    )

    assert progress_manager.init_tracking("Middle Project", force=True) is True
    history_after_first = progress_manager._load_progress_history()
    assert len(history_after_first) == 1
    first_entry = history_after_first[0]
    first_archive_json = Path("docs/progress-tracker/state") / first_entry["progress_json"]
    assert first_archive_json.exists()
    first_payload_before = json.loads(first_archive_json.read_text(encoding="utf-8"))
    assert first_payload_before["project_name"] == "Original Project"

    assert progress_manager.init_tracking("Latest Project", force=True) is True
    history = progress_manager._load_progress_history()
    assert len(history) == 2

    archive_ids = [entry["archive_id"] for entry in history]
    assert len(set(archive_ids)) == 2
    assert all(archive_id.startswith("fixed-reinit-archive-id") for archive_id in archive_ids)

    first_payload_after = json.loads(first_archive_json.read_text(encoding="utf-8"))
    assert first_payload_after["project_name"] == "Original Project"

    second_archive_json = Path("docs/progress-tracker/state") / history[1]["progress_json"]
    assert second_archive_json.exists()
    second_payload = json.loads(second_archive_json.read_text(encoding="utf-8"))
    assert second_payload["project_name"] == "Middle Project"
