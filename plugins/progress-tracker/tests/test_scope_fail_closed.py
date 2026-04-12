"""Scope fail-closed regression tests for monorepo tracker selection."""

import json
import os
from pathlib import Path
from unittest.mock import patch

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
    assert result is False
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
