"""Tests for route-status and route-select commands."""
from __future__ import annotations

import json
import sys
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


def _base_progress() -> dict:
    return {
        "project_name": "Test Project",
        "schema_version": "2.0",
        "features": [],
        "current_feature_id": None,
        "updates": [],
        "retrospectives": [],
        "tracker_role": "parent",
        "project_code": "PT",
        "linked_projects": [
            {"project_root": "plugins/note-organizer", "project_code": "NO", "label": "Note Organizer"},
        ],
        "routing_queue": ["NO"],
        "active_routes": [],
        "linked_snapshot": {"schema_version": "1.0", "updated_at": None, "projects": []},
    }


# --- route-status tests ---

def test_route_status_shows_routing_queue(temp_dir, capsys):
    """route_status() prints routing_queue codes."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "NO" in output


def test_route_status_shows_active_routes(temp_dir, capsys):
    """route_status() prints active_routes entries."""
    data = _base_progress()
    data["active_routes"] = [{"project_code": "NO", "feature_ref": "NO-F3"}]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "NO-F3" in output


def test_route_status_detects_conflict_type_a(temp_dir, capsys):
    """route_status() detects Type A: duplicate project_code in active_routes."""
    data = _base_progress()
    data["active_routes"] = [
        {"project_code": "NO", "feature_ref": "NO-F1"},
        {"project_code": "NO", "feature_ref": "NO-F2"},
    ]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "conflict" in output.lower() or "duplicate" in output.lower()


def test_route_status_detects_conflict_type_b(temp_dir, capsys):
    """route_status() detects Type B: code in routing_queue not in linked_projects."""
    data = _base_progress()
    data["routing_queue"] = ["NO", "GHOST"]  # GHOST not in linked_projects
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "GHOST" in output
    assert "conflict" in output.lower() or "not linked" in output.lower() or "unlinked" in output.lower()


def test_route_status_no_conflicts(temp_dir, capsys):
    """route_status() shows no conflict section when clean."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "conflict" not in output.lower()


def test_route_status_json_output(temp_dir, capsys):
    """route_status(output_json=True) emits valid JSON with routing_queue, active_routes, conflicts."""
    data = _base_progress()
    data["active_routes"] = [{"project_code": "NO", "feature_ref": "NO-F1"}]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status(output_json=True)

    assert result is True
    payload = json.loads(capsys.readouterr().out)
    assert payload["routing_queue"] == ["NO"]
    assert payload["active_routes"] == [{"project_code": "NO", "feature_ref": "NO-F1"}]
    assert "conflicts" in payload
    assert isinstance(payload["conflicts"], list)


# --- route-select tests ---

def test_route_select_inserts_new_entry(temp_dir, capsys):
    """route_select() inserts new active_routes entry when code not present."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref="NO-F3")

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    routes = saved["active_routes"]
    assert len(routes) == 1
    assert routes[0]["project_code"] == "NO"
    assert routes[0]["feature_ref"] == "NO-F3"


def test_route_select_updates_existing_entry(temp_dir):
    """route_select() updates feature_ref for existing project_code entry."""
    data = _base_progress()
    data["active_routes"] = [{"project_code": "NO", "feature_ref": "NO-F1"}]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref="NO-F5")

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    routes = saved["active_routes"]
    assert len(routes) == 1
    assert routes[0]["feature_ref"] == "NO-F5"


def test_route_select_deduplicates_existing_duplicates(temp_dir):
    """route_select() merges duplicate project_code entries into a single record (fixes Type A conflict)."""
    data = _base_progress()
    data["active_routes"] = [
        {"project_code": "NO", "feature_ref": "NO-F1"},
        {"project_code": "NO", "feature_ref": "NO-F2"},
    ]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref="NO-F3")

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    routes = saved["active_routes"]
    # Must be collapsed to a single entry
    no_routes = [r for r in routes if r.get("project_code") == "NO"]
    assert len(no_routes) == 1
    assert no_routes[0]["feature_ref"] == "NO-F3"


def test_route_select_preserves_feature_ref_when_not_provided(temp_dir):
    """route_select() preserves existing feature_ref when --feature-ref not given."""
    data = _base_progress()
    data["active_routes"] = [{"project_code": "NO", "feature_ref": "NO-F2"}]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref=None)

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    assert saved["active_routes"][0]["feature_ref"] == "NO-F2"


def test_route_select_empty_feature_ref_when_new_and_not_provided(temp_dir):
    """route_select() uses empty string when new entry and no --feature-ref given."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref=None)

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    assert saved["active_routes"][0]["feature_ref"] == ""


def test_route_select_json_output(temp_dir, capsys):
    """route_select(output_json=True) emits valid JSON with updated active_routes."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref="NO-F1", output_json=True)

    assert result is True
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert any(r["project_code"] == "NO" for r in payload["active_routes"])


# --- CLI-level (main()) tests ---

def test_cli_route_status_json(temp_dir, capsys):
    """CLI: `prog route-status --json` parses correctly and returns exit 0."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    argv = ["progress_manager.py", "--project-root", str(temp_dir), "route-status", "--json"]
    with patch("sys.argv", argv):
        result = progress_manager.main()

    assert result is True or result == 0
    payload = json.loads(capsys.readouterr().out)
    assert "routing_queue" in payload
    assert "conflicts" in payload


def test_cli_route_select_project(temp_dir, capsys):
    """CLI: `prog route-select --project NO --feature-ref NO-F1` parses and writes correctly."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    argv = [
        "progress_manager.py",
        "--project-root", str(temp_dir),
        "route-select",
        "--project", "NO",
        "--feature-ref", "NO-F1",
    ]
    with patch("sys.argv", argv):
        result = progress_manager.main()

    assert result is True or result == 0
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    routes = [r for r in saved["active_routes"] if r.get("project_code") == "NO"]
    assert len(routes) == 1
    assert routes[0]["feature_ref"] == "NO-F1"
