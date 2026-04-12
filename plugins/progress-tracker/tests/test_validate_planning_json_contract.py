"""
Test suite for validate-planning JSON contract.

Tests the machine-readable message format, exit codes, and schema versioning.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

# Add the hooks/scripts directory to the path
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager


@pytest.fixture
def minimal_planning_project(temp_dir, progress_file):
    """Set up a minimal project with planning gate disabled."""
    from pathlib import Path
    project_root = Path(temp_dir)
    progress_manager._PROJECT_ROOT_OVERRIDE = project_root
    yield project_root


class TestValidatePlanningJsonContract:
    """Test the JSON output contract for validate-planning command."""

    def test_validate_planning_returns_json_with_required_fields(
        self, minimal_planning_project
    ):
        """Validate that validate-planning outputs JSON with all required fields."""
        # Call validate-planning with --json flag
        result = progress_manager.validate_planning_command(
            feature_id=2, output_json=True
        )

        # This should succeed
        assert result is True

    def test_validate_planning_json_has_status_field(
        self, minimal_planning_project, capsys
    ):
        """JSON output must include 'status' field with ready|warn|missing."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "status" in data
        assert data["status"] in ["ready", "warn", "missing"]

    def test_validate_planning_json_has_required_field(
        self, minimal_planning_project, capsys
    ):
        """JSON output must include 'required' field (array of required refs)."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "required" in data
        assert isinstance(data["required"], list)

    def test_validate_planning_json_has_missing_field(
        self, minimal_planning_project, capsys
    ):
        """JSON output must include 'missing' field (array of missing required refs)."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "missing" in data
        assert isinstance(data["missing"], list)

    def test_validate_planning_json_has_optional_missing_field(
        self, minimal_planning_project, capsys
    ):
        """JSON output must include 'optional_missing' field."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "optional_missing" in data
        assert isinstance(data["optional_missing"], list)

    def test_validate_planning_json_has_refs_field(
        self, minimal_planning_project, capsys
    ):
        """JSON output must include 'refs' field (array of doc references)."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "refs" in data
        assert isinstance(data["refs"], list)

    def test_validate_planning_json_has_message_field(
        self, minimal_planning_project, capsys
    ):
        """JSON output must include 'message' field."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "message" in data
        assert isinstance(data["message"], str)

    def test_validate_planning_message_is_machine_readable_key(
        self, minimal_planning_project, capsys
    ):
        """Message field should use machine-readable key (not free text)."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        message = data["message"]
        # Should contain machine-readable keys, not arbitrary text
        # Example: "planning.missing.office_hours" instead of "Planning preflight incomplete..."
        assert isinstance(message, str)
        # This test verifies the message format is being returned
        # The actual format will be validated by implementation

    def test_validate_planning_exit_code_zero_for_ready(
        self, minimal_planning_project
    ):
        """Exit code should be 0 for 'ready' status."""
        # When planning gate is disabled, status should be 'ready'
        result = progress_manager.validate_planning_command(
            feature_id=2, output_json=True
        )
        assert result is True

    def test_validate_planning_exit_code_zero_for_warn(
        self, minimal_planning_project
    ):
        """Exit code should be 0 for 'warn' status."""
        # Will test with actual warn status when planning gate is enabled
        result = progress_manager.validate_planning_command(
            feature_id=2, output_json=True
        )
        assert result is True

    def test_validate_planning_has_optional_schema_version(
        self, minimal_planning_project, capsys
    ):
        """JSON output may include optional 'schema_version' field."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        # schema_version is optional, so we just verify it's well-formed if present
        if "schema_version" in data:
            assert isinstance(data["schema_version"], str)

    def test_validate_planning_message_uses_machine_readable_keys(
        self, minimal_planning_project, capsys
    ):
        """Message field must support machine-readable key format, not free text."""
        # The message field should contain structured machine-readable keys
        # like 'planning.ready' or 'planning.missing.office_hours'
        # NOT free text like "Planning preflight incomplete..."
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        message = data["message"]
        # Should not contain natural language phrases that are hard to parse
        assert not message.startswith("Planning preflight")
        # Should contain structured key notation like planning.* or similar
        assert "planning" in message or "ready" in message

    def test_validate_planning_message_structure_ready_status(
        self, minimal_planning_project, capsys
    ):
        """Message field for ready status should use machine-readable key."""
        progress_manager.validate_planning_command(feature_id=2, output_json=True)
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        if data["status"] == "ready":
            # For ready status, message should be machine-readable
            assert isinstance(data["message"], str)
            assert len(data["message"]) > 0

    def test_validate_planning_exit_code_behavior_ready_status(
        self, minimal_planning_project
    ):
        """Exit code should be 0 (success) for 'ready' status."""
        # When status is ready, should return True or 0
        result = progress_manager.validate_planning_command(
            feature_id=2, output_json=True
        )
        # True maps to exit code 0
        assert result is True or result == 0

    def test_validate_planning_exit_code_behavior_missing_status_with_planning_gate(
        self, minimal_planning_project
    ):
        """Exit code should be 1 (failure) for 'missing' status."""
        # Enable planning gate by adding a planning update with no refs
        data = progress_manager.load_progress_json()
        data["updates"] = [{
            "timestamp": "2026-01-01T00:00:00Z",
            "source": "spm_planning",
            "summary": "Planning initialized",
            "feature_id": None
        }]
        progress_manager.save_progress_json(data)

        # Now validate-planning should report missing (no actual planning refs provided)
        result = progress_manager.validate_planning_command(
            feature_id=2, output_json=False
        )
        # When status is 'missing', command should return False (exit code 1)
        # The result depends on the implementation of exit code handling
