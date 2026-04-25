"""
Tests for root dashboard pull aggregation.

Task 4: _display_root_dashboard, status() parent routing,
         summary pull, snapshot fallback, uninitialized visibility.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parent_project(tmp_path, monkeypatch):
    """Create a mock parent project with initialized and uninitialized children."""
    import subprocess as sp

    repo = tmp_path / "parent-repo"
    repo.mkdir()

    # Initialize git repo
    sp.run(["git", "init"], cwd=repo, capture_output=True)
    sp.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True)
    sp.run(["git", "config", "user.name", "Test User"], cwd=repo, capture_output=True)

    # Create plugins/ directory
    plugins_dir = repo / "plugins"
    plugins_dir.mkdir()

    # ---- Child A: initialized with progress.json ----
    child_a = plugins_dir / "child-a"
    child_a.mkdir()
    (child_a / ".claude-plugin").mkdir()
    (child_a / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "child-a"})
    )
    state_a = child_a / "docs" / "progress-tracker" / "state"
    state_a.mkdir(parents=True)
    progress_a = {
        "schema_version": progress_manager.CURRENT_SCHEMA_VERSION,
        "project_name": "Child A",
        "project_code": "CA",
        "tracker_role": "child",
        "features": [
            {"id": 1, "name": "Feature A1", "completed": True},
            {"id": 2, "name": "Feature A2", "completed": False},
        ],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }
    (state_a / "progress.json").write_text(json.dumps(progress_a, indent=2))

    # ---- Child B: initialized with progress.json ----
    child_b = plugins_dir / "child-b"
    child_b.mkdir()
    (child_b / ".claude-plugin").mkdir()
    (child_b / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "child-b"})
    )
    state_b = child_b / "docs" / "progress-tracker" / "state"
    state_b.mkdir(parents=True)
    progress_b = {
        "schema_version": progress_manager.CURRENT_SCHEMA_VERSION,
        "project_name": "Child B",
        "project_code": "CB",
        "tracker_role": "child",
        "features": [
            {"id": 1, "name": "Feature B1", "completed": False},
        ],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }
    (state_b / "progress.json").write_text(json.dumps(progress_b, indent=2))

    # ---- Child C: uninitialized (plugin.json but no progress.json) ----
    child_c = plugins_dir / "child-c"
    child_c.mkdir()
    (child_c / ".claude-plugin").mkdir()
    (child_c / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "child-c"})
    )

    # Create initial commit
    (repo / "README.md").write_text("# Parent Repo")
    sp.run(["git", "add", "."], cwd=repo, capture_output=True)
    sp.run(["git", "commit", "-m", "Initial commit"], cwd=repo, capture_output=True)

    # Override project root so progress_manager finds our temp repo
    progress_manager._PROJECT_ROOT_OVERRIDE = repo
    progress_manager._STORAGE_READY_ROOT = None
    progress_manager._REPO_ROOT = None
    monkeypatch.setattr("os.getcwd", lambda: str(repo))

    return repo


@pytest.fixture
def parent_data(parent_project):
    """Create a parent tracker data dict with linked children."""
    repo = parent_project
    plugins_dir = repo / "plugins"

    data = {
        "schema_version": progress_manager.CURRENT_SCHEMA_VERSION,
        "project_name": "Test Parent",
        "tracker_role": "parent",
        "project_code": "ROOT",
        "routing_queue": ["ROOT", "CA", "CB"],
        "features": [
            {"id": 100, "name": "Root Feature 1", "completed": False},
        ],
        "linked_projects": [
            {
                "project_root": str(plugins_dir / "child-a"),
                "project_code": "CA",
                "label": "Child A",
            },
            {
                "project_root": str(plugins_dir / "child-b"),
                "project_code": "CB",
                "label": "Child B",
            },
        ],
        "linked_snapshot": {
            "schema_version": "1.0",
            "updated_at": "2024-01-02T00:00:00Z",
            "projects": [
                {
                    "status": "ok",
                    "project_name": "Child A",
                    "completed": 1,
                    "total": 2,
                    "completion_rate": 0.5,
                    "project_code": "CA",
                    "active_feature_ref": None,
                    "is_stale": False,
                },
                {
                    "status": "ok",
                    "project_name": "Child B",
                    "completed": 0,
                    "total": 1,
                    "completion_rate": 0.0,
                    "project_code": "CB",
                    "active_feature_ref": None,
                    "is_stale": False,
                },
            ],
        },
        "active_routes": [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }
    return data


# ---------------------------------------------------------------------------
# _display_root_dashboard tests
# ---------------------------------------------------------------------------


class TestDisplayRootDashboard:
    """Test _display_root_dashboard directly."""

    def test_pulls_child_summaries(self, parent_project, parent_data, capsys):
        """Dashboard should load child summaries via projection loader."""
        repo = parent_project
        result = progress_manager._display_root_dashboard(
            parent_data, repo, repo, output_json=False
        )
        assert result is True

        captured = capsys.readouterr()
        text = captured.out

        # Should show both initialized children with real progress
        assert "Child A" in text or "child-a" in text
        assert "Child B" in text or "child-b" in text
        # Should show progress numbers from summary
        assert "1/2" in text or "0/1" in text

    def test_shows_uninitialized_plugins(self, parent_project, parent_data, capsys):
        """Uninitialized plugins must show '-- not initialized --'."""
        repo = parent_project
        progress_manager._display_root_dashboard(
            parent_data, repo, repo, output_json=False
        )
        captured = capsys.readouterr()
        assert "-- not initialized --" in captured.out
        assert "child-c" in captured.out

    def test_shows_root_features(self, parent_project, parent_data, capsys):
        """Dashboard should display root-level features."""
        repo = parent_project
        progress_manager._display_root_dashboard(
            parent_data, repo, repo, output_json=False
        )
        captured = capsys.readouterr()
        assert "Root Feature 1" in captured.out

    def test_shows_active_route_and_queue(self, parent_project, parent_data, capsys):
        """Dashboard should render active route and queue."""
        # Add an active route
        data = dict(parent_data)
        data["active_routes"] = [
            {"project_code": "CA", "feature_ref": "CA-F2", "status": "active"}
        ]
        repo = parent_project
        progress_manager._display_root_dashboard(
            data, repo, repo, output_json=False
        )
        captured = capsys.readouterr()
        assert "Active Route:" in captured.out
        assert "Queue:" in captured.out
        assert "ROOT" in captured.out
        assert "CA" in captured.out
        assert "CB" in captured.out

    def test_json_output(self, parent_project, parent_data, capsys):
        """Dashboard must support JSON output mode."""
        repo = parent_project
        result = progress_manager._display_root_dashboard(
            parent_data, repo, repo, output_json=True
        )
        assert result is True

        captured = capsys.readouterr()
        payload = json.loads(captured.out)

        assert payload["status"] == "ok"
        assert payload["dashboard_type"] == "monorepo"
        assert payload["project_name"] == "Test Parent"
        assert isinstance(payload["children"], list)
        assert isinstance(payload["uninitialized_plugins"], list)
        assert payload["root_features"]["total"] == 1
        assert payload["queue"] == ["ROOT", "CA", "CB"]

    def test_summary_fallback_to_linked_snapshot(self, parent_project, parent_data, capsys):
        """When load_status_summary_projection fails, fallback to linked_snapshot."""
        repo = parent_project

        # Patch load_status_summary_projection to always fail
        def _broken_loader(project_root=None):
            raise RuntimeError("simulated summary failure")

        with patch.object(progress_manager, "load_status_summary_projection", _broken_loader):
            progress_manager._display_root_dashboard(
                parent_data, repo, repo, output_json=False
            )

        captured = capsys.readouterr()
        text = captured.out

        # Should still render dashboard using snapshot fallback data
        assert "Child A" in text or "child-a" in text
        assert "Child B" in text or "child-b" in text

    def test_corrupt_summary_does_not_crash(self, parent_project, parent_data, capsys):
        """Corrupt child summary JSON must not crash the dashboard."""
        repo = parent_project
        child_a_state = repo / "plugins" / "child-a" / "docs" / "progress-tracker" / "state"

        # Write invalid JSON to the status_summary.v1.json (if it exists) or
        # corrupt the progress.json so summary rebuild fails gracefully
        corrupt_file = child_a_state / "progress.json"
        corrupt_file.write_text("NOT JSON")

        # Rebuild parent_data without the broken child in linked_snapshot
        # so we test the loader failure path for that specific child
        progress_manager._display_root_dashboard(
            parent_data, repo, repo, output_json=False
        )
        captured = capsys.readouterr()
        # Dashboard should still render (with fallback or skipped child)
        assert "## Monorepo Dashboard" in captured.out


# ---------------------------------------------------------------------------
# status() parent routing tests
# ---------------------------------------------------------------------------


class TestStatusParentRouting:
    """Test status() routes parent trackers to _display_root_dashboard."""

    def test_parent_status_routes_to_dashboard(self, parent_project, parent_data, monkeypatch, capsys):
        """When tracker_role is parent, status() should show monorepo dashboard."""
        repo = parent_project

        # Save parent data to progress.json
        progress_manager.save_progress_json(parent_data)

        # Ensure find_project_root returns our repo
        monkeypatch.setattr(progress_manager, "find_project_root", lambda: repo)

        result = progress_manager.status(output_json=False)
        assert result is True

        captured = capsys.readouterr()
        assert "## Monorepo Dashboard" in captured.out

    def test_parent_status_json_mode(self, parent_project, parent_data, monkeypatch, capsys):
        """Parent status with --json should emit JSON dashboard."""
        repo = parent_project
        progress_manager.save_progress_json(parent_data)
        monkeypatch.setattr(progress_manager, "find_project_root", lambda: repo)

        result = progress_manager.status(output_json=True)
        assert result is True

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["dashboard_type"] == "monorepo"
        assert payload["status"] == "ok"

    def test_non_parent_status_unchanged(self, tmp_path, monkeypatch, capsys):
        """Non-parent trackers should show normal status output."""
        import subprocess as sp

        project = tmp_path / "standalone"
        project.mkdir()
        sp.run(["git", "init"], cwd=project, capture_output=True)
        sp.run(["git", "config", "user.email", "test@example.com"], cwd=project, capture_output=True)
        sp.run(["git", "config", "user.name", "Test User"], cwd=project, capture_output=True)
        (project / "README.md").write_text("# Standalone")
        sp.run(["git", "add", "."], cwd=project, capture_output=True)
        sp.run(["git", "commit", "-m", "Initial commit"], cwd=project, capture_output=True)

        progress_manager._PROJECT_ROOT_OVERRIDE = project
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(project))

        progress_manager.init_tracking("Standalone Project")
        result = progress_manager.status(output_json=False)
        assert result is True

        captured = capsys.readouterr()
        assert "## Project: Standalone Project" in captured.out
        assert "## Monorepo Dashboard" not in captured.out
