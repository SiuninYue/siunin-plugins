"""Tests for F24 parent writeback on link-project / init / add-feature / done."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import progress_manager


def _write_progress(root: Path, payload: dict) -> None:
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _read_progress(root: Path) -> dict:
    return json.loads(
        (root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )


def test_link_project_writes_parent_project_root_to_child(temp_dir, capsys):
    """After link-project, child progress.json should contain parent_project_root."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "linked_projects": [],
            "linked_snapshot": {"projects": []},
            "active_routes": [],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
        },
    )

    os.chdir(parent_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "link-project",
            "--code",
            "NO",
        ],
    ):
        assert progress_manager.main() is True

    child_data = _read_progress(child_root)
    assert "parent_project_root" in child_data
    parent_raw = child_data["parent_project_root"]
    assert "progress-tracker" in parent_raw


def test_notify_parent_sync_updates_linked_snapshot_after_add_feature(temp_dir, capsys):
    """add-feature on child should trigger parent linked_snapshot refresh."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "parent",
            "linked_projects": [
                {"project_root": "plugins/note-organizer", "project_code": "NO", "label": "NO"}
            ],
            "linked_snapshot": {"projects": []},
            "active_routes": [{"project_code": "NO", "feature_ref": "NO-F1"}],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "child",
            "project_code": "NO",
            "parent_project_root": "plugins/progress-tracker",
        },
    )

    os.chdir(child_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "add-feature",
            "My Feature",
            "run pytest",
        ],
    ):
        assert progress_manager.main() is True

    parent_data = _read_progress(parent_root)
    projects = parent_data.get("linked_snapshot", {}).get("projects", [])
    assert len(projects) == 1
    assert projects[0]["total"] == 1
    assert projects[0]["completed"] == 0


def test_notify_parent_sync_updates_snapshot_after_init(temp_dir, capsys):
    """init on child (when parent_project_root is pre-set) triggers parent snapshot refresh."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "parent",
            "linked_projects": [
                {"project_root": "plugins/note-organizer", "project_code": "NO", "label": "NO"}
            ],
            "linked_snapshot": {"projects": []},
            "active_routes": [],
        },
    )
    # Child already exists with parent_project_root (from prior link-project)
    _write_progress(
        child_root,
        {
            "project_name": "Old Name",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "child",
            "project_code": "NO",
            "parent_project_root": "plugins/progress-tracker",
        },
    )

    os.chdir(child_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "init",
            "Note Organizer v2",
            "--force",
        ],
    ):
        assert progress_manager.main() is True

    parent_data = _read_progress(parent_root)
    projects = parent_data.get("linked_snapshot", {}).get("projects", [])
    assert len(projects) == 1
    assert projects[0]["total"] == 0


def test_notify_parent_sync_warn_only_when_parent_missing(temp_dir, capsys):
    """If parent_project_root points to a missing tracker, warn-only, do not block.

    Uses a standalone (non-child) project with parent_project_root set to simulate
    a scenario where the parent tracker file has been removed after linking.
    Route preflight is not triggered for non-child trackers.
    """
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    child_root = repo_root / "plugins" / "note-organizer"
    child_root.mkdir(parents=True, exist_ok=True)

    # Standalone project with parent_project_root set but parent tracker absent
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-17T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "parent_project_root": "plugins/progress-tracker",
        },
    )

    os.chdir(child_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/note-organizer",
            "add-feature",
            "My Feature",
            "run pytest",
        ],
    ):
        result = progress_manager.main()

    assert result is True
    output = capsys.readouterr().out
    assert "WARNING" in output or "warning" in output.lower() or "parent" in output.lower()
