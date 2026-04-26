"""
Tests for child discovery without hardcoded plugin codes.

Task 3: _derive_plugin_code, _generate_plugin_code,
         _discover_plugin_catalog, _auto_discover_child_plugins
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager
import prog_paths


# ---------------------------------------------------------------------------
# _derive_plugin_code and _generate_plugin_code
# ---------------------------------------------------------------------------


class TestDerivePluginCode:
    """Test _derive_plugin_code produces correct codes."""

    def test_simple_two_segment(self):
        assert progress_manager._derive_plugin_code("note-organizer") == "NO"

    def test_three_segment(self):
        assert progress_manager._derive_plugin_code("super-product-manager") == "SPM"

    def test_existing_plugin(self):
        assert progress_manager._derive_plugin_code("progress-tracker") == "PT"

    def test_single_segment(self):
        assert progress_manager._derive_plugin_code("myapp") == "M"

    def test_underscore_separator(self):
        assert progress_manager._derive_plugin_code("my_cool_app") == "MCA"

    def test_truncation_to_8_chars(self):
        # A very long hyphenated name should be truncated
        long_name = "a-b-c-d-e-f-g-h-i-j"
        code = progress_manager._derive_plugin_code(long_name)
        assert len(code) <= 8
        assert code == "ABCDEFGHIJ"[:8]  # "ABCDEFGH"


class TestGeneratePluginCode:
    """Test _generate_plugin_code with collision handling."""

    def test_no_collision(self):
        result = progress_manager._generate_project_code("note-organizer", set())
        assert result == "NO"

    def test_collision_gets_suffix(self):
        result = progress_manager._generate_project_code("note-organizer", {"NO"})
        assert result == "NO2"

    def test_double_collision(self):
        result = progress_manager._generate_project_code("note-organizer", {"NO", "NO2"})
        assert result == "NO3"

    def test_collision_truncation(self):
        # Long base code + suffix must stay under 8 chars
        used = {"ABCDEFGH"}
        result = progress_manager._generate_project_code("a-b-c-d-e-f-g-h", used)
        assert len(result) <= 8


# ---------------------------------------------------------------------------
# _discover_plugin_catalog
# ---------------------------------------------------------------------------


class TestDiscoverPluginCatalog:
    """Test _discover_plugin_catalog read-only scan."""

    @pytest.fixture
    def mock_repo(self, tmp_path):
        """Create a mock monorepo with plugins."""
        import subprocess as sp

        repo = tmp_path / "repo"
        repo.mkdir()

        sp.run(["git", "init"], cwd=repo, capture_output=True)
        sp.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True)
        sp.run(["git", "config", "user.name", "Test User"], cwd=repo, capture_output=True)

        # Create parent tracker structure
        parent_state = repo / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)

        # Create plugins with plugin.json
        plugins_dir = repo / "plugins"
        plugins_dir.mkdir()

        # Initialized child: progress-tracker
        pt_dir = plugins_dir / "progress-tracker"
        pt_dir.mkdir()
        (pt_dir / ".claude-plugin").mkdir()
        (pt_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "progress-tracker"})
        )
        pt_state = pt_dir / "docs" / "progress-tracker" / "state"
        pt_state.mkdir(parents=True)
        (pt_state / "progress.json").write_text(json.dumps({"project_name": "PT"}))

        # Initialized child: note-organizer
        no_dir = plugins_dir / "note-organizer"
        no_dir.mkdir()
        (no_dir / ".claude-plugin").mkdir()
        (no_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "note-organizer"})
        )
        no_state = no_dir / "docs" / "progress-tracker" / "state"
        no_state.mkdir(parents=True)
        (no_state / "progress.json").write_text(json.dumps({"project_name": "NO"}))

        # Uninitialized child: package-manager (no tracker)
        pm_dir = plugins_dir / "package-manager"
        pm_dir.mkdir()
        (pm_dir / ".claude-plugin").mkdir()
        (pm_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "package-manager"})
        )

        # Create initial commit
        (repo / "README.md").write_text("# Test Repo")
        sp.run(["git", "add", "."], cwd=repo, capture_output=True)
        sp.run(["git", "commit", "-m", "Initial commit"], cwd=repo, capture_output=True)

        return repo

    def test_catalog_finds_initialized_and_uninitialized(self, mock_repo):
        """Catalog lists two initialized and one uninitialized plugin."""
        catalog = progress_manager._discover_plugin_catalog(mock_repo, mock_repo)
        assert len(catalog["initialized"]) == 2
        assert len(catalog["uninitialized"]) == 1

        names_init = [e["name"] for e in catalog["initialized"]]
        assert "progress-tracker" in names_init
        assert "note-organizer" in names_init

        names_uninit = [e["name"] for e in catalog["uninitialized"]]
        assert names_uninit == ["package-manager"]

    def test_catalog_is_read_only(self, mock_repo):
        """_discover_plugin_catalog never creates files."""
        pm_state = mock_repo / "plugins" / "package-manager" / "docs" / "progress-tracker"
        assert not pm_state.exists()

        catalog = progress_manager._discover_plugin_catalog(mock_repo, mock_repo)

        # Still no tracker directory created for uninitialized plugin
        assert not pm_state.exists()

    def test_catalog_skips_parent_root(self, mock_repo):
        """Catalog skips the parent root directory."""
        parent_pt_dir = mock_repo / "plugins" / "progress-tracker"
        # When parent_root == progress-tracker dir, it should be skipped
        catalog = progress_manager._discover_plugin_catalog(mock_repo, parent_pt_dir)
        # Only note-organizer should be initialized (progress-tracker is skipped)
        assert len(catalog["initialized"]) == 1
        assert catalog["initialized"][0]["name"] == "note-organizer"


# ---------------------------------------------------------------------------
# _auto_discover_child_plugins
# ---------------------------------------------------------------------------


class TestAutoDiscoverChildPlugins:
    """Test _auto_discover_child_plugins registration and writeback."""

    @pytest.fixture
    def parent_with_children(self, tmp_path):
        """Create a parent tracker with two initialized children."""
        import subprocess as sp

        repo = tmp_path / "repo"
        repo.mkdir()

        sp.run(["git", "init"], cwd=repo, capture_output=True)
        sp.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True)
        sp.run(["git", "config", "user.name", "Test User"], cwd=repo, capture_output=True)

        # Parent tracker
        parent_state = repo / "docs" / "progress-tracker" / "state"
        parent_state.mkdir(parents=True)

        plugins_dir = repo / "plugins"
        plugins_dir.mkdir()

        # Child: progress-tracker
        pt_dir = plugins_dir / "progress-tracker"
        pt_dir.mkdir()
        (pt_dir / ".claude-plugin").mkdir()
        (pt_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "progress-tracker"})
        )
        pt_state = pt_dir / "docs" / "progress-tracker" / "state"
        pt_state.mkdir(parents=True)
        (pt_state / "progress.json").write_text(json.dumps({"project_name": "PT Project"}))

        # Child: note-organizer
        no_dir = plugins_dir / "note-organizer"
        no_dir.mkdir()
        (no_dir / ".claude-plugin").mkdir()
        (no_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "note-organizer"})
        )
        no_state = no_dir / "docs" / "progress-tracker" / "state"
        no_state.mkdir(parents=True)
        (no_state / "progress.json").write_text(json.dumps({"project_name": "NO Project"}))

        (repo / "README.md").write_text("# Test Repo")
        sp.run(["git", "add", "."], cwd=repo, capture_output=True)
        sp.run(["git", "commit", "-m", "Initial commit"], cwd=repo, capture_output=True)

        return repo

    def test_discovery_registers_children_and_writes_back(
        self, parent_with_children
    ):
        """Discovery registers both children and writes back child metadata."""
        repo = parent_with_children

        # Set up parent data
        progress_manager._PROJECT_ROOT_OVERRIDE = repo
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None

        try:
            parent_data = {
                "schema_version": "2.1",
                "project_name": "Test Parent",
                "tracker_role": "parent",
                "project_code": progress_manager.ROOT_ROUTE_CODE,
                "routing_queue": [progress_manager.ROOT_ROUTE_CODE],
                "features": [],
                "current_feature_id": None,
            }

            result = progress_manager._auto_discover_child_plugins(
                project_root=repo,
                repo_root=repo,
                parent_data=parent_data,
            )

            # Both children should be discovered
            assert len(result["added_codes"]) == 2
            assert "PT" in result["added_codes"]
            assert "NO" in result["added_codes"]

            # Parent data should have linked_projects
            linked = parent_data.get("linked_projects", [])
            assert len(linked) == 2
            codes = [e.get("project_code") for e in linked if isinstance(e, dict)]
            assert "PT" in codes
            assert "NO" in codes

            # Queue should include ROOT + child codes
            queue = parent_data.get("routing_queue", [])
            assert progress_manager.ROOT_ROUTE_CODE in queue
            assert "PT" in queue
            assert "NO" in queue

            # Check child writeback
            pt_data = json.loads(
                (repo / "plugins" / "progress-tracker" / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
            )
            assert pt_data["tracker_role"] == "child"
            assert pt_data["project_code"] == "PT"

            no_data = json.loads(
                (repo / "plugins" / "note-organizer" / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
            )
            assert no_data["tracker_role"] == "child"
            assert no_data["project_code"] == "NO"
        finally:
            progress_manager._PROJECT_ROOT_OVERRIDE = None
            progress_manager._STORAGE_READY_ROOT = None
            progress_manager._REPO_ROOT = None

    def test_discovery_preserves_existing_queue_order(
        self, parent_with_children
    ):
        """Existing queue order is preserved, new codes appended."""
        repo = parent_with_children

        progress_manager._PROJECT_ROOT_OVERRIDE = repo
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None

        try:
            # PT is already in the queue and linked; NO is new
            parent_data = {
                "schema_version": "2.1",
                "project_name": "Test Parent",
                "tracker_role": "parent",
                "project_code": progress_manager.ROOT_ROUTE_CODE,
                "routing_queue": ["PT", progress_manager.ROOT_ROUTE_CODE],
                "linked_projects": [
                    {
                        "project_root": "plugins/progress-tracker",
                        "project_code": "PT",
                        "label": "progress-tracker",
                    }
                ],
                "features": [],
                "current_feature_id": None,
            }

            result = progress_manager._auto_discover_child_plugins(
                project_root=repo,
                repo_root=repo,
                parent_data=parent_data,
            )

            queue = parent_data["routing_queue"]
            # PT and ROOT should be preserved in their original order
            assert queue.index("PT") < queue.index(progress_manager.ROOT_ROUTE_CODE)
            # NO should be appended after
            assert "NO" in queue
            assert queue[-1] == "NO"
        finally:
            progress_manager._PROJECT_ROOT_OVERRIDE = None
            progress_manager._STORAGE_READY_ROOT = None
            progress_manager._REPO_ROOT = None