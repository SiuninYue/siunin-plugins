"""
Tests for monorepo root initialization and path resolution.

Task 0: Root prog wrapper script
Task 1: Repo root path resolution
Task 2: Parent init without overwrite + ROOT_ROUTE_CODE
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import prog_paths
import progress_manager


# ---------------------------------------------------------------------------
# Task 0: Root prog wrapper tests
# ---------------------------------------------------------------------------


class TestRootProgWrapper:
    """Test the root-level prog wrapper that forwards to progress-tracker."""

    @pytest.fixture
    def fake_repo(self, tmp_path):
        """Create a fake monorepo with a stub prog inside plugins/progress-tracker."""
        repo = tmp_path / "repo"
        repo.mkdir()
        plugins_dir = repo / "plugins"
        plugins_dir.mkdir()
        pt_dir = plugins_dir / "progress-tracker"
        pt_dir.mkdir()
        hooks_scripts = pt_dir / "hooks" / "scripts"
        hooks_scripts.mkdir(parents=True)

        # Stub prog that echoes its arguments so we can verify forwarding
        stub_prog = pt_dir / "prog"
        stub_prog.write_text(
            textwrap.dedent("""\
                #!/usr/bin/env bash
                echo "STUB_ARGS: $@"
            """)
        )
        stub_prog.chmod(0o755)

        # Create root prog wrapper
        root_prog = repo / "prog"
        root_prog.write_text(
            textwrap.dedent("""\
                #!/usr/bin/env bash
                set -euo pipefail
                SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
                PT_PROG="$SCRIPT_DIR/plugins/progress-tracker/prog"
                if [[ ! -x "$PT_PROG" ]]; then
                  echo "Error: progress-tracker prog not found at $PT_PROG" >&2
                  exit 1
                fi
                HAS_PROJECT_ROOT=0
                for arg in "$@"; do
                  case "$arg" in
                    --project-root|--project-root=*) HAS_PROJECT_ROOT=1; break ;;
                  esac
                done
                if [[ "$HAS_PROJECT_ROOT" -eq 0 ]]; then
                  exec "$PT_PROG" --project-root "$SCRIPT_DIR" "$@"
                else
                  exec "$PT_PROG" "$@"
                fi
            """)
        )
        root_prog.chmod(0o755)

        return repo

    def test_wrapper_injects_project_root_when_absent(self, fake_repo):
        """Without --project-root, wrapper auto-injects SCRIPT_DIR."""
        result = subprocess.run(
            [str(fake_repo / "prog"), "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert f"--project-root {fake_repo}" in result.stdout

    def test_wrapper_preserves_explicit_project_root(self, fake_repo):
        """With explicit --project-root, wrapper does not double-inject."""
        custom_root = fake_repo / "plugins" / "progress-tracker"
        result = subprocess.run(
            [str(fake_repo / "prog"), "--project-root", str(custom_root), "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        # Should contain the custom root, not the auto-injected one
        assert f"--project-root {custom_root}" in result.stdout
        # Should NOT contain a second project-root pointing to the repo root
        output = result.stdout
        # Count occurrences of --project-root
        count = output.count("--project-root")
        assert count == 1, f"Expected 1 --project-root, got {count}: {output}"

    def test_wrapper_preserves_project_root_equals_syntax(self, fake_repo):
        """With --project-root=VALUE syntax, wrapper preserves it."""
        custom_root = fake_repo / "plugins" / "progress-tracker"
        result = subprocess.run(
            [str(fake_repo / "prog"), f"--project-root={custom_root}", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert f"--project-root={custom_root}" in result.stdout

    def test_wrapper_errors_when_pt_prog_missing(self, tmp_path):
        """Wrapper reports error when progress-tracker/prog is absent."""
        repo = tmp_path / "repo_empty"
        repo.mkdir()
        # No plugins/progress-tracker directory
        root_prog = repo / "prog"
        root_prog.write_text(
            textwrap.dedent("""\
                #!/usr/bin/env bash
                set -euo pipefail
                SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
                PT_PROG="$SCRIPT_DIR/plugins/progress-tracker/prog"
                if [[ ! -x "$PT_PROG" ]]; then
                  echo "Error: progress-tracker prog not found at $PT_PROG" >&2
                  exit 1
                fi
            """)
        )
        root_prog.chmod(0o755)

        result = subprocess.run(
            [str(root_prog), "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "Error" in result.stderr or "not found" in result.stderr


# ---------------------------------------------------------------------------
# Task 1: Repo root path resolution tests (placeholder, filled in Task 1)
# ---------------------------------------------------------------------------

class TestRepoRootPathResolution:
    """Test resolve_target_project_root() for monorepo root."""

    @pytest.fixture
    def mock_monorepo(self, tmp_path):
        """Create a mock monorepo structure with plugins/ directory."""
        import subprocess as sp

        repo = tmp_path / "monorepo"
        repo.mkdir()

        # Initialize git repo
        sp.run(["git", "init"], cwd=repo, capture_output=True)
        sp.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True)
        sp.run(["git", "config", "user.name", "Test User"], cwd=repo, capture_output=True)

        # Create plugins/ directory with a child project
        plugins_dir = repo / "plugins"
        plugins_dir.mkdir()
        child_dir = plugins_dir / "child-plugin"
        child_dir.mkdir()
        (child_dir / ".claude-plugin").mkdir()
        (child_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "child-plugin"})
        )

        # Create tracker structure in child
        state_dir = child_dir / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True)

        # Create initial commit
        (repo / "README.md").write_text("# Test Repo")
        sp.run(["git", "add", "."], cwd=repo, capture_output=True)
        sp.run(["git", "commit", "-m", "Initial commit"], cwd=repo, capture_output=True)

        return repo

    @pytest.fixture
    def mock_standalone(self, tmp_path):
        """Create a standalone (non-monorepo) project."""
        import subprocess as sp

        project = tmp_path / "standalone"
        project.mkdir()

        sp.run(["git", "init"], cwd=project, capture_output=True)
        sp.run(["git", "config", "user.email", "test@example.com"], cwd=project, capture_output=True)
        sp.run(["git", "config", "user.name", "Test User"], cwd=project, capture_output=True)

        state_dir = project / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True)

        (project / "README.md").write_text("# Standalone")
        sp.run(["git", "add", "."], cwd=project, capture_output=True)
        sp.run(["git", "commit", "-m", "Initial commit"], cwd=project, capture_output=True)

        return project

    def test_repo_root_resolves_to_itself(self, mock_monorepo):
        """When CWD is exactly the repo root, resolve returns (repo_root, repo_root)."""
        target, repo = prog_paths.resolve_target_project_root(cwd=mock_monorepo)
        assert target == mock_monorepo
        assert repo == mock_monorepo

    def test_repo_root_via_project_root_arg(self, mock_monorepo):
        """--project-root pointing at repo root resolves to (repo_root, repo_root)."""
        target, repo = prog_paths.resolve_target_project_root(
            project_root_arg=str(mock_monorepo), cwd=mock_monorepo
        )
        assert target == mock_monorepo
        assert repo == mock_monorepo

    def test_cwd_under_repo_root_outside_plugins_ambiguous(self, mock_monorepo):
        """CWD under repo root but outside plugins/ remains ambiguous."""
        scripts_dir = mock_monorepo / "scripts"
        scripts_dir.mkdir()
        with pytest.raises(prog_paths.ProjectRootResolutionError):
            prog_paths.resolve_target_project_root(cwd=scripts_dir)

    def test_cwd_inside_plugin_resolves_to_plugin(self, mock_monorepo):
        """CWD inside a plugin directory resolves to that plugin root."""
        child_dir = mock_monorepo / "plugins" / "child-plugin"
        target, repo = prog_paths.resolve_target_project_root(cwd=child_dir)
        assert target == child_dir
        assert repo == mock_monorepo

    def test_standalone_project_unchanged(self, mock_standalone):
        """Non-monorepo standalone project resolution remains unchanged."""
        target, repo = prog_paths.resolve_target_project_root(cwd=mock_standalone)
        assert target == mock_standalone
        assert repo == mock_standalone


# ---------------------------------------------------------------------------
# Task 2: Parent init without overwrite + ROOT_ROUTE_CODE
# ---------------------------------------------------------------------------


class TestParentInit:
    """Test parent tracker initialization with ROOT_ROUTE_CODE."""

    @pytest.fixture
    def parent_project(self, tmp_path, monkeypatch):
        """Create a mock parent project with plugins/ directory."""
        import subprocess as sp

        repo = tmp_path / "parent-repo"
        repo.mkdir()

        # Initialize git repo
        sp.run(["git", "init"], cwd=repo, capture_output=True)
        sp.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True)
        sp.run(["git", "config", "user.name", "Test User"], cwd=repo, capture_output=True)

        # Create plugins/ directory (makes this a parent-root candidate)
        plugins_dir = repo / "plugins"
        plugins_dir.mkdir()
        child_dir = plugins_dir / "child-plugin"
        child_dir.mkdir()
        (child_dir / ".claude-plugin").mkdir()
        (child_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "child-plugin"})
        )

        # Create initial commit
        (repo / "README.md").write_text("# Parent Repo")
        sp.run(["git", "add", "."], cwd=repo, capture_output=True)
        sp.run(["git", "commit", "-m", "Initial commit"], cwd=repo, capture_output=True)

        # Set project root override to point at our temp repo
        progress_manager._PROJECT_ROOT_OVERRIDE = repo
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(repo))

        return repo

    @pytest.fixture
    def standalone_project(self, tmp_path, monkeypatch):
        """Create a standalone project without plugins/."""
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

        return project

    def test_parent_init_sets_tracker_role(self, parent_project):
        """Parent init sets tracker_role=parent and project_code=ROOT."""
        result = progress_manager.init_tracking("Test Parent Repo")
        assert result is True

        data = progress_manager.load_progress_json()
        assert data["tracker_role"] == "parent"
        assert data["project_code"] == "ROOT"
        assert data["routing_queue"] == ["ROOT"]

    def test_parent_init_no_overwrite(self, parent_project):
        """Repeated init without --force preserves existing data."""
        progress_manager.init_tracking("First Init")

        # Modify the data
        data = progress_manager.load_progress_json()
        data["features"] = [{"id": 1, "name": "test feature", "test_steps": ["step1"]}]
        progress_manager.save_progress_json(data)

        # Re-init without force should fail and preserve data
        result = progress_manager.init_tracking("Second Init")
        assert result is False

        # Data should still have the feature we added
        preserved = progress_manager.load_progress_json()
        assert preserved["project_name"] == "First Init"
        assert len(preserved["features"]) == 1
        assert preserved["features"][0]["name"] == "test feature"

    def test_standalone_init_no_parent_role(self, standalone_project):
        """Standalone init does not set parent role or ROOT code."""
        result = progress_manager.init_tracking("Standalone Project")
        assert result is True

        data = progress_manager.load_progress_json()
        # Standalone should not have parent tracker fields
        assert data.get("tracker_role") != "parent"
        assert data.get("project_code") != "ROOT"

    def test_root_route_code_constant(self):
        """ROOT_ROUTE_CODE is the string 'ROOT'."""
        assert progress_manager.ROOT_ROUTE_CODE == "ROOT"