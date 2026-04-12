"""Tests for sync-linked command snapshot refresh behavior."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import progress_manager


def _write_progress(root: Path, payload: dict) -> None:
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _last_output_line(capsys) -> str:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines, "expected CLI output"
    return lines[-1]


def test_sync_linked_writes_snapshot_from_monorepo_root_with_explicit_scope(
    temp_dir, capsys
):
    """sync-linked should refresh linked_snapshot when invoked via --project-root."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent Tracker",
            "created_at": "2026-04-12T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "linked_projects": [
                {"project_root": "plugins/note-organizer", "label": "notes"}
            ],
            "linked_snapshot": {
                "collector": "manual-seed",
                "projects": [],
            },
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "updated_at": "2026-04-12T09:30:00Z",
            "features": [
                {"id": 1, "name": "A", "completed": True},
                {"id": 2, "name": "B", "completed": False},
            ],
            "current_feature_id": None,
        },
    )

    os.chdir(repo_root)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/progress-tracker",
            "sync-linked",
            "--json",
        ],
    ):
        assert progress_manager.main() is True

    payload = json.loads(_last_output_line(capsys))
    assert payload["status"] == "ok"
    assert payload["project_count"] == 1
    assert payload["ok_count"] == 1
    assert payload["missing_count"] == 0

    parent_progress = json.loads(
        (parent_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )
    snapshot = parent_progress["linked_snapshot"]
    assert snapshot["collector"] == "manual-seed"
    assert snapshot["schema_version"] == "1.0"
    assert snapshot["updated_at"] is not None
    assert len(snapshot["projects"]) == 1
    assert snapshot["projects"][0]["project_name"] == "Note Organizer"
    assert snapshot["projects"][0]["status"] == "ok"
    assert snapshot["projects"][0]["completion_rate"] == 0.5


def test_sync_linked_reports_missing_child_project_in_json_payload(temp_dir, capsys):
    """sync-linked should include missing child projects in the persisted snapshot."""
    parent_root = temp_dir
    _write_progress(
        parent_root,
        {
            "project_name": "Parent Tracker",
            "created_at": "2026-04-12T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "linked_projects": [{"project_root": "plugins/missing-plugin"}],
        },
    )

    os.chdir(parent_root)
    with patch("sys.argv", ["progress_manager.py", "sync-linked", "--json"]):
        assert progress_manager.main() is True

    payload = json.loads(_last_output_line(capsys))
    assert payload["status"] == "ok"
    assert payload["project_count"] == 1
    assert payload["missing_count"] == 1
    assert payload["stale_count"] == 1

    progress_data = progress_manager.load_progress_json()
    assert isinstance(progress_data, dict)
    projects = progress_data["linked_snapshot"]["projects"]
    assert len(projects) == 1
    assert projects[0]["status"] == "missing"
    assert projects[0]["updated_at"] is None
