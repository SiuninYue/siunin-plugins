"""
Tests for routing queue management commands.

Task 6: prioritize_route, set_routing_queue, ROOT validation, queue preservation.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parent_data(queue=None, linked=None):
    """Build a minimal parent tracker payload."""
    return {
        "schema_version": progress_manager.CURRENT_SCHEMA_VERSION,
        "project_name": "Parent",
        "tracker_role": "parent",
        "project_code": progress_manager.ROOT_ROUTE_CODE,
        "routing_queue": queue if queue is not None else [progress_manager.ROOT_ROUTE_CODE],
        "linked_projects": linked if linked is not None else [],
        "features": [],
        "active_routes": [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# prioritize_route tests
# ---------------------------------------------------------------------------


class TestPrioritizeRoute:
    """Test prioritize_route moves a code to the front."""

    def test_prioritize_existing_code(self, tmp_path, monkeypatch, capsys):
        """Moving an existing code to the front updates queue."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(
            queue=[progress_manager.ROOT_ROUTE_CODE, "PT", "NO"],
            linked=[
                {"project_code": "PT", "project_root": "/plugins/pt"},
                {"project_code": "NO", "project_root": "/plugins/no"},
            ],
        )
        progress_manager.save_progress_json(data)

        result = progress_manager.prioritize_route("NO", output_json=False)
        assert result is True

        captured = capsys.readouterr()
        assert "Prioritized NO" in captured.out
        assert "NO -> ROOT -> PT" in captured.out

        saved = progress_manager.load_progress_json()
        assert saved["routing_queue"] == ["NO", progress_manager.ROOT_ROUTE_CODE, "PT"]

    def test_prioritize_root(self, tmp_path, monkeypatch, capsys):
        """ROOT can be prioritized even though it is not in linked_projects."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(queue=["PT", progress_manager.ROOT_ROUTE_CODE])
        progress_manager.save_progress_json(data)

        result = progress_manager.prioritize_route(progress_manager.ROOT_ROUTE_CODE, output_json=False)
        assert result is True

        saved = progress_manager.load_progress_json()
        assert saved["routing_queue"][0] == progress_manager.ROOT_ROUTE_CODE

    def test_prioritize_invalid_code(self, tmp_path, monkeypatch, capsys):
        """Prioritizing an unknown code returns an error."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(queue=[progress_manager.ROOT_ROUTE_CODE, "PT"])
        progress_manager.save_progress_json(data)

        result = progress_manager.prioritize_route("GHOST", output_json=False)
        assert result is False
        captured = capsys.readouterr()
        assert "GHOST" in captured.out

    def test_prioritize_json_output(self, tmp_path, monkeypatch, capsys):
        """JSON output mode returns structured payload."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(
            queue=[progress_manager.ROOT_ROUTE_CODE, "PT"],
            linked=[
                {"project_code": "PT", "project_root": "/plugins/pt"},
            ],
        )
        progress_manager.save_progress_json(data)

        result = progress_manager.prioritize_route("PT", output_json=True)
        assert result is True

        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "ok"
        assert payload["code"] == "PT"
        assert payload["routing_queue"] == ["PT", progress_manager.ROOT_ROUTE_CODE]

    def test_prioritize_non_parent_rejected(self, tmp_path, monkeypatch, capsys):
        """Non-parent tracker rejects prioritize."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data()
        data["tracker_role"] = "child"
        progress_manager.save_progress_json(data)

        result = progress_manager.prioritize_route("PT", output_json=False)
        assert result is False
        assert "only runs from a parent" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# set_routing_queue tests
# ---------------------------------------------------------------------------


class TestSetRoutingQueue:
    """Test set_routing_queue replaces queue with validated codes."""

    def test_set_queue_valid_codes(self, tmp_path, monkeypatch, capsys):
        """Setting queue with valid codes updates it in order."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(
            queue=[progress_manager.ROOT_ROUTE_CODE, "PT", "NO"],
            linked=[
                {"project_code": "PT", "project_root": "/plugins/pt"},
                {"project_code": "NO", "project_root": "/plugins/no"},
            ],
        )
        progress_manager.save_progress_json(data)

        result = progress_manager.set_routing_queue(
            ["NO", progress_manager.ROOT_ROUTE_CODE, "PT"], force=False, output_json=False
        )
        assert result is True

        saved = progress_manager.load_progress_json()
        assert saved["routing_queue"] == ["NO", progress_manager.ROOT_ROUTE_CODE, "PT"]

    def test_set_queue_requires_existing_codes(self, tmp_path, monkeypatch, capsys):
        """Without --force, existing queue codes must be present."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(
            queue=[progress_manager.ROOT_ROUTE_CODE, "PT", "NO"],
            linked=[
                {"project_code": "PT", "project_root": "/plugins/pt"},
                {"project_code": "NO", "project_root": "/plugins/no"},
            ],
        )
        progress_manager.save_progress_json(data)

        # Omitting NO should fail without --force
        result = progress_manager.set_routing_queue(
            [progress_manager.ROOT_ROUTE_CODE, "PT"], force=False, output_json=False
        )
        assert result is False
        captured = capsys.readouterr()
        assert "Missing existing queue code(s): NO" in captured.out

    def test_set_queue_force_allows_drop(self, tmp_path, monkeypatch, capsys):
        """With --force, dropping existing codes is allowed."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(
            queue=[progress_manager.ROOT_ROUTE_CODE, "PT", "NO"],
            linked=[
                {"project_code": "PT", "project_root": "/plugins/pt"},
                {"project_code": "NO", "project_root": "/plugins/no"},
            ],
        )
        progress_manager.save_progress_json(data)

        result = progress_manager.set_routing_queue(
            [progress_manager.ROOT_ROUTE_CODE, "PT"], force=True, output_json=False
        )
        assert result is True

        saved = progress_manager.load_progress_json()
        assert saved["routing_queue"] == [progress_manager.ROOT_ROUTE_CODE, "PT"]

    def test_set_queue_rejects_invalid_code(self, tmp_path, monkeypatch, capsys):
        """Invalid non-ROOT code is rejected."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(queue=[progress_manager.ROOT_ROUTE_CODE])
        progress_manager.save_progress_json(data)

        result = progress_manager.set_routing_queue(
            ["GHOST"], force=False, output_json=False
        )
        assert result is False
        assert "Invalid code(s): GHOST" in capsys.readouterr().out

    def test_set_queue_root_always_valid(self, tmp_path, monkeypatch, capsys):
        """ROOT is always valid even when not in linked_projects."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(queue=[progress_manager.ROOT_ROUTE_CODE])
        progress_manager.save_progress_json(data)

        result = progress_manager.set_routing_queue(
            [progress_manager.ROOT_ROUTE_CODE], force=False, output_json=False
        )
        assert result is True

    def test_set_queue_json_output(self, tmp_path, monkeypatch, capsys):
        """JSON output mode returns structured payload."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data(
            queue=[progress_manager.ROOT_ROUTE_CODE, "PT"],
            linked=[
                {"project_code": "PT", "project_root": "/plugins/pt"},
            ],
        )
        progress_manager.save_progress_json(data)

        result = progress_manager.set_routing_queue(
            ["PT", progress_manager.ROOT_ROUTE_CODE], force=False, output_json=True
        )
        assert result is True

        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "ok"
        assert payload["routing_queue"] == ["PT", progress_manager.ROOT_ROUTE_CODE]

    def test_set_queue_non_parent_rejected(self, tmp_path, monkeypatch, capsys):
        """Non-parent tracker rejects set-queue."""
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager._STORAGE_READY_ROOT = None
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        data = _make_parent_data()
        data["tracker_role"] = "child"
        progress_manager.save_progress_json(data)

        result = progress_manager.set_routing_queue(
            [progress_manager.ROOT_ROUTE_CODE], force=False, output_json=False
        )
        assert result is False
        assert "only runs from a parent" in capsys.readouterr().out
