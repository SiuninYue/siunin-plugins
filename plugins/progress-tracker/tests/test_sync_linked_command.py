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


def test_link_project_registers_child_and_updates_parent_route_fields(temp_dir, capsys):
    """link-project should bind child tracker + parent linked routing metadata."""
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
            "linked_projects": [],
            "routing_queue": [],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-12T00:00:00Z",
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
            "--json",
        ],
    ):
        assert progress_manager.main() is True

    payload = json.loads(_last_output_line(capsys))
    assert payload["status"] == "ok"
    assert payload["project_code"] == "NO"

    parent_progress = json.loads(
        (parent_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert parent_progress["tracker_role"] == "parent"
    assert parent_progress["routing_queue"] == ["NO"]
    assert parent_progress["linked_projects"] == [
        {
            "project_root": "plugins/note-organizer",
            "project_code": "NO",
            "label": "Note Organizer",
        }
    ]

    child_progress = json.loads(
        (child_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert child_progress["tracker_role"] == "child"
    assert child_progress["project_code"] == "NO"


def test_link_project_fails_when_child_progress_missing(temp_dir, capsys):
    """link-project should fail fast when child tracker file does not exist."""
    parent_root = temp_dir / "plugins" / "progress-tracker"
    parent_root.mkdir(parents=True, exist_ok=True)
    _write_progress(
        parent_root,
        {
            "project_name": "Parent Tracker",
            "created_at": "2026-04-12T00:00:00Z",
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
            "plugins/missing-child",
            "link-project",
            "--code",
            "MC",
        ],
    ):
        assert progress_manager.main() is False

    output = capsys.readouterr().out
    assert "linked child progress.json not found" in output


def test_link_project_updates_existing_entry_and_route_fields(temp_dir, capsys):
    """link-project should update existing child code across linked/routing metadata."""
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
                {
                    "project_root": "plugins/note-organizer",
                    "project_code": "OLD",
                    "label": "Old Label",
                }
            ],
            "routing_queue": ["OLD", "OLD", "API"],
            "active_routes": [
                {"project_code": "OLD", "feature_ref": "OLD-F1"},
                {"project_code": "API", "feature_ref": "API-F2"},
            ],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-12T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "child",
            "project_code": "OLD",
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
            "--json",
        ],
    ):
        assert progress_manager.main() is True

    payload = json.loads(_last_output_line(capsys))
    assert payload["status"] == "ok"
    assert payload["routing_queue"] == ["API", "NO"]
    assert payload["active_routes"] == [
        {"project_code": "NO", "feature_ref": "OLD-F1"},
        {"project_code": "API", "feature_ref": "API-F2"},
    ]

    parent_progress = json.loads(
        (parent_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert parent_progress["linked_projects"] == [
        {
            "project_root": "plugins/note-organizer",
            "project_code": "NO",
            "label": "Note Organizer",
        }
    ]
    assert parent_progress["routing_queue"] == ["API", "NO"]
    assert parent_progress["active_routes"] == [
        {"project_code": "NO", "feature_ref": "OLD-F1"},
        {"project_code": "API", "feature_ref": "API-F2"},
    ]


def test_link_project_dedupes_duplicate_project_code_entries(temp_dir, capsys):
    """link-project should keep a single linked_projects entry for one project_code."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    repo_root = temp_dir
    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "note-organizer"
    old_root = repo_root / "plugins" / "legacy-notes"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)
    old_root.mkdir(parents=True, exist_ok=True)

    _write_progress(
        parent_root,
        {
            "project_name": "Parent Tracker",
            "created_at": "2026-04-12T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "linked_projects": [
                {
                    "project_root": "plugins/legacy-notes",
                    "project_code": "NO",
                    "label": "legacy",
                },
                {
                    "project_root": "plugins/note-organizer",
                    "project_code": "NO",
                    "label": "duplicate",
                },
            ],
            "routing_queue": ["NO", "NO"],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-12T00:00:00Z",
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
            "--json",
        ],
    ):
        assert progress_manager.main() is True

    payload = json.loads(_last_output_line(capsys))
    assert payload["status"] == "ok"
    assert payload["routing_queue"] == ["NO"]

    parent_progress = json.loads(
        (parent_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )
    linked_projects = parent_progress["linked_projects"]
    assert len(linked_projects) == 1
    assert linked_projects[0]["project_root"] == "plugins/note-organizer"
    assert linked_projects[0]["project_code"] == "NO"


def test_link_project_fails_when_child_is_parent_tracker(temp_dir, capsys):
    """link-project should reject child trackers that are already parent trackers."""
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
            "linked_projects": [],
            "routing_queue": [],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-12T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "parent",
            "project_code": "NO",
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
        assert progress_manager.main() is False

    output = capsys.readouterr().out
    assert "already a parent tracker" in output


def test_link_project_fails_when_child_has_conflicting_code(temp_dir, capsys):
    """link-project should fail when child already has a different child project_code."""
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
            "linked_projects": [],
            "routing_queue": [],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "created_at": "2026-04-12T00:00:00Z",
            "features": [],
            "current_feature_id": None,
            "tracker_role": "child",
            "project_code": "LEGACY",
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
        assert progress_manager.main() is False

    output = capsys.readouterr().out
    assert "already linked with project_code=LEGACY" in output


def test_sync_linked_includes_new_route_fields(temp_dir, capsys):
    """sync-linked snapshot projects include project_code/child_project_code/workspace/route_status."""
    import os as _os
    _os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

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
                {
                    "project_root": "plugins/note-organizer",
                    "project_code": "NO",
                    "label": "Note Organizer",
                }
            ],
            "linked_snapshot": {"projects": []},
            "active_routes": [{"project_code": "NO", "feature_ref": "NO-F1"}],
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
            "current_feature_id": 2,
            "project_code": "NO",
            "runtime_context": {"workspace_mode": "worktree"},
        },
    )

    import os
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

    parent_progress = json.loads(
        (parent_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )
    project = parent_progress["linked_snapshot"]["projects"][0]
    assert project["project_code"] == "NO"
    assert project["child_project_code"] == "NO"
    assert project["workspace"] == "worktree"
    assert project["route_status"] == "active"


def test_sync_linked_route_status_idle_when_not_in_active_routes(temp_dir, capsys):
    """route_status should be 'idle' when project_code is not in parent active_routes."""
    import os as _os
    _os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

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
                {
                    "project_root": "plugins/note-organizer",
                    "project_code": "NO",
                    "label": "Note Organizer",
                }
            ],
            "linked_snapshot": {"projects": []},
            "active_routes": [],  # NO is NOT in active_routes
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "updated_at": "2026-04-12T09:30:00Z",
            "features": [{"id": 1, "name": "A", "completed": False}],
            "current_feature_id": None,
            "project_code": "NO",
            "runtime_context": {"workspace_mode": "in_place"},
        },
    )

    import os
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

    parent_progress = json.loads(
        (parent_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )
    project = parent_progress["linked_snapshot"]["projects"][0]
    assert project["project_code"] == "NO"
    assert project["child_project_code"] == "NO"
    assert project["workspace"] == "in_place"
    assert project["route_status"] == "idle"


def test_sync_linked_project_code_fallback_to_child_payload(temp_dir, capsys):
    """project_code should fall back to child payload when linked_projects entry has none."""
    import os as _os
    _os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

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
                # No project_code in this entry — only project_root + label
                {"project_root": "plugins/note-organizer", "label": "Note Organizer"}
            ],
            "linked_snapshot": {"projects": []},
            "active_routes": [],
        },
    )
    _write_progress(
        child_root,
        {
            "project_name": "Note Organizer",
            "updated_at": "2026-04-12T09:30:00Z",
            "features": [{"id": 1, "name": "A", "completed": True}],
            "current_feature_id": None,
            "project_code": "NO",  # child has code even though parent entry does not
            "runtime_context": {"workspace_mode": "in_place"},
        },
    )

    import os
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

    parent_progress = json.loads(
        (parent_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )
    project = parent_progress["linked_snapshot"]["projects"][0]
    # Falls back to child payload project_code
    assert project["project_code"] == "NO"
    assert project["child_project_code"] == "NO"
    assert project["route_status"] == "idle"
