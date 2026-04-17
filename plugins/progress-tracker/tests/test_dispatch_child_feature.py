"""Tests for F22 _get_dispatched_child_feature and next_feature parent dispatch."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import progress_manager
from progress_manager import _get_dispatched_child_feature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_progress(root: Path, payload: dict) -> None:
    """Write a progress.json under <root>/docs/progress-tracker/state/."""
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _child_payload(features: list) -> dict:
    """Minimal child progress.json payload."""
    return {
        "project_name": "Child Project",
        "schema_version": "2.0",
        "features": features,
        "current_feature_id": None,
    }


def _linked_entry(code: str, project_root: Path) -> dict:
    """Build a linked_projects entry with absolute path."""
    return {
        "code": code,
        "project_root": str(project_root),
    }


# ---------------------------------------------------------------------------
# Unit Tests for _get_dispatched_child_feature
# ---------------------------------------------------------------------------

class TestGetDispatchedChildFeature:

    def test_dispatch_first_in_queue(self, tmp_path):
        """First entry in routing_queue with pending feature is dispatched."""
        child_pm = tmp_path / "child_pm"
        child_pm.mkdir()
        child_no = tmp_path / "child_no"
        child_no.mkdir()

        routing_queue = ["PM", "NO"]
        active_routes = []
        linked_projects = [
            _linked_entry("PM", child_pm),
            _linked_entry("NO", child_no),
        ]
        child_pm_data = _child_payload([{"id": 1, "name": "F1 name", "completed": False}])

        with patch(
            "progress_manager._load_progress_payload_at_root",
            side_effect=lambda root: (child_pm_data, None) if root == child_pm.resolve() else (None, "not found"),
        ):
            result = _get_dispatched_child_feature(
                routing_queue, active_routes, linked_projects,
                project_root=tmp_path, repo_root=tmp_path,
            )

        assert result is not None
        assert result["child_project_code"] == "PM"
        assert result["next_feature_id"] == 1

    def test_dispatch_skips_active_routes(self, tmp_path):
        """PM with non-terminal active route is skipped; NO is dispatched."""
        child_pm = tmp_path / "child_pm"
        child_pm.mkdir()
        child_no = tmp_path / "child_no"
        child_no.mkdir()

        routing_queue = ["PM", "NO"]
        # PM has a non-terminal route with no status (defaults to non-terminal).
        # The function reads "child_project_code" or "code" from active_routes entries.
        active_routes = [{"child_project_code": "PM", "assigned_at": None}]
        linked_projects = [
            _linked_entry("PM", child_pm),
            _linked_entry("NO", child_no),
        ]
        child_no_data = _child_payload([{"id": 5, "name": "NO feature", "completed": False}])

        def _mock_load(root):
            if root == child_no.resolve():
                return child_no_data, None
            return None, "not found"

        with patch("progress_manager._load_progress_payload_at_root", side_effect=_mock_load):
            result = _get_dispatched_child_feature(
                routing_queue, active_routes, linked_projects,
                project_root=tmp_path, repo_root=tmp_path,
            )

        assert result is not None
        assert result["child_project_code"] == "NO"

    def test_dispatch_skips_only_active_not_done(self, tmp_path):
        """PM route with status 'done' (terminal) is NOT skipped."""
        child_pm = tmp_path / "child_pm"
        child_pm.mkdir()

        routing_queue = ["PM"]
        active_routes = [{"child_project_code": "PM", "status": "done"}]
        linked_projects = [_linked_entry("PM", child_pm)]
        child_pm_data = _child_payload([{"id": 2, "name": "PM pending", "completed": False}])

        with patch(
            "progress_manager._load_progress_payload_at_root",
            return_value=(child_pm_data, None),
        ):
            result = _get_dispatched_child_feature(
                routing_queue, active_routes, linked_projects,
                project_root=tmp_path, repo_root=tmp_path,
            )

        assert result is not None
        assert result["child_project_code"] == "PM"

    def test_dispatch_stale_route_unblocks(self, tmp_path):
        """PM route with a very old assigned_at (stale) does NOT block dispatching."""
        child_pm = tmp_path / "child_pm"
        child_pm.mkdir()

        routing_queue = ["PM"]
        active_routes = [{"child_project_code": "PM", "assigned_at": "2020-01-01T00:00:00+00:00"}]
        linked_projects = [_linked_entry("PM", child_pm)]
        child_pm_data = _child_payload([{"id": 3, "name": "PM stale feature", "completed": False}])

        with patch(
            "progress_manager._load_progress_payload_at_root",
            return_value=(child_pm_data, None),
        ):
            result = _get_dispatched_child_feature(
                routing_queue, active_routes, linked_projects,
                project_root=tmp_path, repo_root=tmp_path,
                stale_after_hours=1,  # 1 hour threshold → 2020 timestamp is definitely stale
            )

        assert result is not None
        assert result["child_project_code"] == "PM"

    def test_dispatch_empty_queue_fallback(self, tmp_path):
        """Empty routing_queue returns None."""
        child_pm = tmp_path / "child_pm"
        child_pm.mkdir()

        routing_queue = []
        active_routes = []
        linked_projects = [_linked_entry("PM", child_pm)]
        child_pm_data = _child_payload([{"id": 1, "name": "PM feature", "completed": False}])

        with patch(
            "progress_manager._load_progress_payload_at_root",
            return_value=(child_pm_data, None),
        ):
            result = _get_dispatched_child_feature(
                routing_queue, active_routes, linked_projects,
                project_root=tmp_path, repo_root=tmp_path,
            )

        assert result is None

    def test_dispatch_all_children_done_fallback(self, tmp_path):
        """All child features completed → returns None."""
        child_pm = tmp_path / "child_pm"
        child_pm.mkdir()

        routing_queue = ["PM"]
        active_routes = []
        linked_projects = [_linked_entry("PM", child_pm)]
        child_pm_data = _child_payload([{"id": 1, "name": "done feature", "completed": True}])

        with patch(
            "progress_manager._load_progress_payload_at_root",
            return_value=(child_pm_data, None),
        ):
            result = _get_dispatched_child_feature(
                routing_queue, active_routes, linked_projects,
                project_root=tmp_path, repo_root=tmp_path,
            )

        assert result is None


# ---------------------------------------------------------------------------
# Integration Tests for next_feature() parent dispatch
# ---------------------------------------------------------------------------

class TestNextFeatureIntegration:

    def _write_parent(self, root: Path, child_pm: Path, child_no: Path, active_routes: list) -> None:
        payload = {
            "project_name": "Parent Project",
            "schema_version": "2.0",
            "tracker_role": "parent",
            "routing_queue": ["PM", "NO"],
            "active_routes": active_routes,
            "linked_projects": [
                {"project_root": str(child_pm), "project_code": "PM", "code": "PM"},
                {"project_root": str(child_no), "project_code": "NO", "code": "NO"},
            ],
            "features": [],
            "current_feature_id": None,
        }
        _write_progress(root, payload)

    def test_integration_next_feature_dispatches_to_child(self, temp_dir, capsys):
        """next_feature() dispatches to NO when PM is done and PM child has no pending features."""
        child_pm = temp_dir / "child_pm"
        child_pm.mkdir()
        child_no = temp_dir / "child_no"
        child_no.mkdir()

        # PM active route is terminal (done); "child_project_code" is the key read by _get_dispatched_child_feature
        self._write_parent(
            temp_dir, child_pm, child_no,
            active_routes=[{"child_project_code": "PM", "status": "done"}],
        )
        _write_progress(child_pm, _child_payload([
            {"id": 1, "name": "PM feature", "completed": True},
        ]))
        _write_progress(child_no, _child_payload([
            {"id": 2, "name": "NO feature", "completed": False},
        ]))

        with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
            result = progress_manager.next_feature(output_json=True)

        assert result is True
        output = capsys.readouterr().out
        payload = json.loads(output)
        assert payload["dispatched_to"] == "child"
        assert payload["child_project_code"] == "NO"
        assert payload["next_feature_id"] == 2

    def test_integration_skips_conflicted_child(self, temp_dir, capsys):
        """next_feature() skips PM (conflicted active route) and dispatches to NO."""
        child_pm = temp_dir / "child_pm"
        child_pm.mkdir()
        child_no = temp_dir / "child_no"
        child_no.mkdir()

        # PM has an active (non-terminal) route; "child_project_code" is the key read by _get_dispatched_child_feature
        self._write_parent(
            temp_dir, child_pm, child_no,
            active_routes=[{"child_project_code": "PM", "assigned_at": None}],
        )
        _write_progress(child_pm, _child_payload([
            {"id": 1, "name": "PM pending feature", "completed": False},
        ]))
        _write_progress(child_no, _child_payload([
            {"id": 3, "name": "NO pending feature", "completed": False},
        ]))

        with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
            result = progress_manager.next_feature(output_json=True)

        assert result is True
        output = capsys.readouterr().out
        payload = json.loads(output)
        assert payload["dispatched_to"] == "child"
        assert payload["child_project_code"] == "NO"
        assert payload["next_feature_id"] == 3
