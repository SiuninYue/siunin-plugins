"""Scope fail-closed regression tests for monorepo tracker selection."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import progress_manager


def _init_tracker(temp_dir: Path, plugin_name: str, project_name: str) -> Path:
    plugin_root = temp_dir / "plugins" / plugin_name
    plugin_root.mkdir(parents=True, exist_ok=True)

    assert progress_manager.configure_project_scope(f"plugins/{plugin_name}") is True
    assert progress_manager.init_tracking(project_name, force=True) is True

    progress_manager._PROJECT_ROOT_OVERRIDE = None
    progress_manager._REPO_ROOT = None
    progress_manager._STORAGE_READY_ROOT = None
    return plugin_root


def _progress_path(plugin_root: Path) -> Path:
    return plugin_root / "docs" / "progress-tracker" / "state" / "progress.json"


def _load_progress(plugin_root: Path) -> dict:
    return json.loads(_progress_path(plugin_root).read_text(encoding="utf-8"))


def _save_progress(plugin_root: Path, payload: dict) -> None:
    _progress_path(plugin_root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_monorepo_root_blocks_mutating_command_when_scope_is_ambiguous(temp_dir, capsys):
    """Mutating commands must fail closed at monorepo root when multiple trackers exist."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    _init_tracker(temp_dir, "alpha-plugin", "Alpha Tracker")
    _init_tracker(temp_dir, "beta-plugin", "Beta Tracker")

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        ["progress_manager.py", "add-feature", "Feature X", "Step 1"],
    ):
        result = progress_manager.main()

    output = capsys.readouterr().out
    assert result in (False, 1)  # Accept both bool and int for error returns
    assert "Ambiguous monorepo scope" in output
    assert "prog --project-root plugins/<name>" in output


def test_explicit_project_root_recovers_mutating_command_from_monorepo_root(temp_dir):
    """The same mutating command should succeed once --project-root is specified."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    target_root = _init_tracker(temp_dir, "alpha-plugin", "Alpha Tracker")
    _init_tracker(temp_dir, "beta-plugin", "Beta Tracker")

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/alpha-plugin",
            "add-feature",
            "Feature Y",
            "Step Y",
        ],
    ):
        result = progress_manager.main()

    assert result is True

    progress_file = target_root / "docs" / "progress-tracker" / "state" / "progress.json"
    payload = json.loads(progress_file.read_text(encoding="utf-8"))
    assert any(feature["name"] == "Feature Y" for feature in payload.get("features", []))


@pytest.mark.parametrize(
    "mutating_tail",
    [
        ["set-current", "1"],  # /prog next path
        ["add-feature", "Feature X", "Step 1"],
        ["update-feature", "1", "Feature X Updated", "Step 2"],
        ["complete", "1", "--skip-archive"],
        ["done"],
    ],
)
def test_child_route_mismatch_blocks_core_mutating_commands(temp_dir, capsys, mutating_tail):
    """Child mutating commands must fail closed when parent active_routes points elsewhere."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    parent_root = _init_tracker(temp_dir, "parent-plugin", "Parent Tracker")
    child_root = _init_tracker(temp_dir, "child-plugin", "Child Tracker")

    parent_payload = _load_progress(parent_root)
    parent_payload["tracker_role"] = "parent"
    parent_payload["project_code"] = "PT"
    parent_payload["linked_projects"] = [
        {
            "project_root": "plugins/child-plugin",
            "project_code": "NO",
            "label": "Child Tracker",
        }
    ]
    parent_payload["routing_queue"] = ["NO"]
    parent_payload["active_routes"] = [
        {"project_code": "PT", "feature_ref": "PT-F1"},
    ]
    _save_progress(parent_root, parent_payload)

    child_payload = _load_progress(child_root)
    child_payload["tracker_role"] = "child"
    child_payload["project_code"] = "NO"
    child_payload["features"] = [
        {"id": 1, "name": "Child Feature", "test_steps": ["true"], "completed": False}
    ]
    child_payload["current_feature_id"] = 1
    child_payload["workflow_state"] = {"phase": "execution_complete"}
    _save_progress(child_root, child_payload)

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        ["progress_manager.py", "--project-root", "plugins/child-plugin", *mutating_tail],
    ):
        result = progress_manager.main()

    output = capsys.readouterr().out
    assert result in (False, 1)  # Accept both bool and int for error returns
    assert "Route Preflight" in output
    assert "--project-root" in output
    assert "cd " in output


def test_child_mutating_blocks_when_not_registered_in_parent(temp_dir, capsys):
    """Unregistered child tracker should be blocked with actionable routing guidance."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    parent_root = _init_tracker(temp_dir, "parent-plugin", "Parent Tracker")
    child_root = _init_tracker(temp_dir, "child-plugin", "Child Tracker")

    parent_payload = _load_progress(parent_root)
    parent_payload["tracker_role"] = "parent"
    parent_payload["project_code"] = "PT"
    parent_payload["linked_projects"] = []
    parent_payload["routing_queue"] = []
    parent_payload["active_routes"] = []
    _save_progress(parent_root, parent_payload)

    child_payload = _load_progress(child_root)
    child_payload["tracker_role"] = "child"
    child_payload["project_code"] = "NO"
    _save_progress(child_root, child_payload)

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        ["progress_manager.py", "--project-root", "plugins/child-plugin", "add-feature", "F", "S"],
    ):
        result = progress_manager.main()

    output = capsys.readouterr().out
    assert result in (False, 1)  # Accept both bool and int for error returns
    assert "not registered in any parent linked_projects" in output
    assert "link-project --project-root" in output
    assert "--project-root" in output


def test_child_mutating_allowed_when_parent_route_matches(temp_dir):
    """Child mutating command should proceed when parent active_routes matches child code."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    parent_root = _init_tracker(temp_dir, "parent-plugin", "Parent Tracker")
    child_root = _init_tracker(temp_dir, "child-plugin", "Child Tracker")

    parent_payload = _load_progress(parent_root)
    parent_payload["tracker_role"] = "parent"
    parent_payload["project_code"] = "PT"
    parent_payload["linked_projects"] = [
        {
            "project_root": "plugins/child-plugin",
            "project_code": "NO",
            "label": "Child Tracker",
        }
    ]
    parent_payload["routing_queue"] = ["NO"]
    parent_payload["active_routes"] = [
        {"project_code": "NO", "feature_ref": "NO-F1"},
    ]
    _save_progress(parent_root, parent_payload)

    child_payload = _load_progress(child_root)
    child_payload["tracker_role"] = "child"
    child_payload["project_code"] = "NO"
    _save_progress(child_root, child_payload)

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/child-plugin",
            "add-feature",
            "Allowed Feature",
            "Step 1",
        ],
    ):
        result = progress_manager.main()

    assert result is True
    payload = _load_progress(child_root)
    assert any(feature["name"] == "Allowed Feature" for feature in payload.get("features", []))
