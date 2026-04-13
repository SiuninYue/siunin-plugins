"""Schema defaults for linked project coordination metadata."""

from __future__ import annotations

import json

import progress_manager


def test_load_progress_json_backfills_linked_schema_defaults(temp_dir):
    """Legacy payloads should gain linked schema defaults on load."""
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_name": "Parent tracker",
        "created_at": "2026-04-09T00:00:00Z",
        "features": [],
        "current_feature_id": None,
    }
    (state_dir / "progress.json").write_text(json.dumps(payload), encoding="utf-8")

    data = progress_manager.load_progress_json()

    assert data["linked_projects"] == []
    assert data["linked_snapshot"] == {
        "schema_version": "1.0",
        "updated_at": None,
        "projects": [],
    }
    assert data["tracker_role"] == "standalone"
    assert data["project_code"] is None
    assert data["routing_queue"] == []
    assert data["active_routes"] == []


def test_load_progress_json_normalizes_invalid_linked_schema_shapes(temp_dir):
    """Invalid linked/route schema shapes should normalize to safe defaults."""
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_name": "Parent tracker",
        "created_at": "2026-04-09T00:00:00Z",
        "features": [],
        "current_feature_id": None,
        "linked_projects": "not-a-list",
        "linked_snapshot": ["not-a-dict"],
        "tracker_role": {"bad": "shape"},
        "project_code": ["bad-shape"],
        "routing_queue": "not-a-list",
        "active_routes": {"bad": "shape"},
    }
    (state_dir / "progress.json").write_text(json.dumps(payload), encoding="utf-8")

    data = progress_manager.load_progress_json()

    assert data["linked_projects"] == []
    assert data["linked_snapshot"] == {
        "schema_version": "1.0",
        "updated_at": None,
        "projects": [],
    }
    assert data["tracker_role"] == "standalone"
    assert data["project_code"] is None
    assert data["routing_queue"] == []
    assert data["active_routes"] == []


def test_save_progress_json_preserves_unknown_fields_with_linked_route_schema(temp_dir):
    """Saving should keep unknown fields while backfilling linked/route defaults."""
    payload = {
        "project_name": "Parent tracker",
        "created_at": "2026-04-09T00:00:00Z",
        "features": [],
        "current_feature_id": None,
        "linked_projects": [
            {
                "project_root": "plugins/progress-tracker",
                "label": "tracker",
                "custom_entry_flag": True,
            }
        ],
        "linked_snapshot": {
            "projects": [{"project_name": "tracker", "completed": 1, "total": 1}],
            "collector": "manual-seed",
        },
        "tracker_role": " parent ",
        "project_code": " PT ",
        "routing_queue": ["PT", "NO"],
        "active_routes": [
            {"project_code": "PT", "feature_ref": "PT-F1", "custom_route_flag": True}
        ],
        "x_parent_marker": {"retain": True},
    }

    progress_manager.save_progress_json(payload, touch_updated_at=False)

    progress_file = temp_dir / "docs" / "progress-tracker" / "state" / "progress.json"
    reloaded = json.loads(progress_file.read_text(encoding="utf-8"))

    assert reloaded["x_parent_marker"] == {"retain": True}
    assert reloaded["linked_snapshot"]["collector"] == "manual-seed"
    assert reloaded["linked_snapshot"]["schema_version"] == "1.0"
    assert reloaded["linked_snapshot"]["updated_at"] is None
    assert reloaded["linked_snapshot"]["projects"] == [
        {"project_name": "tracker", "completed": 1, "total": 1}
    ]
    assert reloaded["linked_projects"][0]["custom_entry_flag"] is True
    assert reloaded["tracker_role"] == "parent"
    assert reloaded["project_code"] == "PT"
    assert reloaded["routing_queue"] == ["PT", "NO"]
    assert reloaded["active_routes"] == [
        {"project_code": "PT", "feature_ref": "PT-F1", "custom_route_flag": True}
    ]
