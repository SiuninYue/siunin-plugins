"""Tests for linked child-project status discovery and read-only aggregation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import progress_manager


def _write_progress(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_collect_linked_project_statuses_discovers_and_reads_child_progress(tmp_path):
    """Collector should discover child path and return normalized status fields."""
    repo_root = tmp_path
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"

    _write_progress(
        child_root / "docs" / "progress-tracker" / "state" / "progress.json",
        {
            "project_name": "Note Organizer",
            "updated_at": "2026-04-12T09:30:00Z",
            "features": [
                {"id": 1, "name": "A", "completed": True},
                {"id": 2, "name": "B", "completed": False},
            ],
        },
    )

    parent_data = {
        "linked_projects": [
            {"project_root": "plugins/note-organizer", "label": "notes"},
        ]
    }
    statuses = progress_manager.collect_linked_project_statuses(
        parent_data,
        project_root=parent_root,
        repo_root=repo_root,
        now=datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
        stale_after_hours=24,
    )

    assert len(statuses) == 1
    status = statuses[0]
    assert status["project_name"] == "Note Organizer"
    assert status["completion_rate"] == 0.5
    assert status["updated_at"] == "2026-04-12T09:30:00Z"
    assert status["is_stale"] is False


def test_collect_linked_project_statuses_marks_stale_and_keeps_missing_read_only(tmp_path):
    """Collector should mark stale snapshots and avoid creating missing project files."""
    repo_root = tmp_path
    parent_root = repo_root / "plugins" / "progress-tracker"
    stale_child_root = repo_root / "plugins" / "legacy-plugin"
    missing_child_root = repo_root / "plugins" / "missing-plugin"

    _write_progress(
        stale_child_root / "docs" / "progress-tracker" / "state" / "progress.json",
        {
            "project_name": "Legacy Plugin",
            "updated_at": "2026-04-10T09:30:00Z",
            "features": [{"id": 1, "name": "Only", "completed": True}],
        },
    )

    parent_data = {
        "linked_projects": [
            {"project_root": "plugins/legacy-plugin"},
            {"project_root": "plugins/missing-plugin"},
        ]
    }
    statuses = progress_manager.collect_linked_project_statuses(
        parent_data,
        project_root=parent_root,
        repo_root=repo_root,
        now=datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
        stale_after_hours=24,
    )

    assert len(statuses) == 2
    assert statuses[0]["project_name"] == "Legacy Plugin"
    assert statuses[0]["is_stale"] is True

    assert statuses[1]["status"] == "missing"
    assert statuses[1]["is_stale"] is True
    assert statuses[1]["updated_at"] is None

    missing_progress = (
        missing_child_root / "docs" / "progress-tracker" / "state" / "progress.json"
    )
    assert not missing_progress.exists()


def test_collect_linked_project_statuses_includes_active_feature_ref_with_namespace(tmp_path):
    """Collector should include active_feature_ref when project_code and current_feature_id are present."""
    repo_root = tmp_path
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "progress-tracker"

    _write_progress(
        child_root / "docs" / "progress-tracker" / "state" / "progress.json",
        {
            "project_name": "Progress Tracker",
            "project_code": "PT",
            "current_feature_id": 18,
            "updated_at": "2026-04-12T09:30:00Z",
            "features": [
                {"id": 1, "name": "A", "completed": True},
                {"id": 18, "name": "Namespace Feature", "completed": False},
            ],
        },
    )

    parent_data = {
        "linked_projects": [
            {"project_root": "plugins/progress-tracker", "label": "tracker"},
        ]
    }
    statuses = progress_manager.collect_linked_project_statuses(
        parent_data,
        project_root=parent_root,
        repo_root=repo_root,
        now=datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
        stale_after_hours=24,
    )

    assert len(statuses) == 1
    status = statuses[0]
    assert status["active_feature_ref"] == "PT-F18"


def test_collect_linked_project_statuses_disambiguates_same_feature_id(tmp_path):
    """Collector should distinguish F2 from PT-F2 and NO-F2 using project_code."""
    repo_root = tmp_path
    parent_root = repo_root / "plugins" / "progress-tracker"
    pt_root = repo_root / "plugins" / "progress-tracker"
    no_root = repo_root / "plugins" / "note-organizer"

    _write_progress(
        pt_root / "docs" / "progress-tracker" / "state" / "progress.json",
        {
            "project_name": "Progress Tracker",
            "project_code": "PT",
            "current_feature_id": 2,
            "updated_at": "2026-04-12T09:30:00Z",
            "features": [{"id": 2, "name": "Feature 2", "completed": False}],
        },
    )

    _write_progress(
        no_root / "docs" / "progress-tracker" / "state" / "progress.json",
        {
            "project_name": "Note Organizer",
            "project_code": "NO",
            "current_feature_id": 2,
            "updated_at": "2026-04-12T09:30:00Z",
            "features": [{"id": 2, "name": "Feature 2", "completed": False}],
        },
    )

    parent_data = {
        "linked_projects": [
            {"project_root": "plugins/progress-tracker"},
            {"project_root": "plugins/note-organizer"},
        ]
    }
    statuses = progress_manager.collect_linked_project_statuses(
        parent_data,
        project_root=parent_root,
        repo_root=repo_root,
        now=datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
        stale_after_hours=24,
    )

    assert len(statuses) == 2
    assert statuses[0]["active_feature_ref"] == "PT-F2"
    assert statuses[1]["active_feature_ref"] == "NO-F2"


def test_collect_linked_project_statuses_active_feature_ref_null_without_project_code(tmp_path):
    """Collector should return None for active_feature_ref when project_code is missing."""
    repo_root = tmp_path
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"

    _write_progress(
        child_root / "docs" / "progress-tracker" / "state" / "progress.json",
        {
            "project_name": "Note Organizer",
            "current_feature_id": 5,
            "updated_at": "2026-04-12T09:30:00Z",
            "features": [{"id": 5, "name": "Feature 5", "completed": False}],
        },
    )

    parent_data = {
        "linked_projects": [
            {"project_root": "plugins/note-organizer"},
        ]
    }
    statuses = progress_manager.collect_linked_project_statuses(
        parent_data,
        project_root=parent_root,
        repo_root=repo_root,
        now=datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
        stale_after_hours=24,
    )

    assert len(statuses) == 1
    status = statuses[0]
    assert status["active_feature_ref"] is None
