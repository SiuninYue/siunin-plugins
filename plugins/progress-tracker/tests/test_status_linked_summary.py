"""Tests for status() linked project matrix and archive history summary display."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import progress_manager


def _write_progress(root: Path, payload: dict) -> None:
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _base_progress(project_name: str = "Test Project") -> dict:
    return {
        "project_name": project_name,
        "schema_version": "2.0",
        "features": [],
        "current_feature_id": None,
        "updates": [],
        "retrospectives": [],
        "linked_projects": [],
        "linked_snapshot": {
            "schema_version": "1.0",
            "updated_at": "2026-04-12T10:00:00Z",
            "projects": [],
        },
    }


def test_status_shows_linked_project_matrix(temp_dir, capsys):
    """status() should display linked project matrix when linked_snapshot.projects is non-empty."""
    data = _base_progress("Parent Project")
    data["linked_snapshot"]["projects"] = [
        {
            "status": "ok",
            "project_name": "Note Organizer",
            "completed": 3,
            "total": 5,
            "completion_rate": 0.6,
            "updated_at": "2026-04-12T09:00:00Z",
            "is_stale": False,
        }
    ]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.status()

    assert result is True
    output = capsys.readouterr().out
    assert "Linked Projects" in output
    assert "Note Organizer" in output
    assert "3/5" in output
    assert "60%" in output


def test_status_shows_stale_marker(temp_dir, capsys):
    """status() should show [stale] marker for stale linked projects."""
    data = _base_progress("Parent Project")
    data["linked_snapshot"]["projects"] = [
        {
            "status": "ok",
            "project_name": "Old Child",
            "completed": 1,
            "total": 4,
            "completion_rate": 0.25,
            "updated_at": "2026-01-01T00:00:00Z",
            "is_stale": True,
        }
    ]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.status()

    assert result is True
    output = capsys.readouterr().out
    assert "Linked Projects" in output
    assert "[stale]" in output
    assert "Old Child" in output


def test_status_shows_missing_linked_project(temp_dir, capsys):
    """status() should show 'missing' for linked projects whose progress.json is absent."""
    data = _base_progress("Parent Project")
    data["linked_snapshot"]["projects"] = [
        {
            "status": "missing",
            "project_name": "Ghost Project",
            "completed": 0,
            "total": 0,
            "completion_rate": 0.0,
            "updated_at": None,
            "is_stale": True,
        }
    ]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.status()

    assert result is True
    output = capsys.readouterr().out
    assert "Linked Projects" in output
    assert "Ghost Project" in output
    assert "missing" in output


def test_status_shows_invalid_linked_project(temp_dir, capsys):
    """status() should show raw status string for unrecognised project status values."""
    data = _base_progress("Parent Project")
    data["linked_snapshot"]["projects"] = [
        {
            "status": "invalid",
            "project_name": "Broken Child",
            "completed": 0,
            "total": 0,
            "completion_rate": 0.0,
            "updated_at": None,
            "is_stale": False,
        }
    ]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.status()

    assert result is True
    output = capsys.readouterr().out
    assert "Linked Projects" in output
    assert "Broken Child" in output
    assert "invalid" in output


def test_status_hides_linked_section_when_empty(temp_dir, capsys):
    """status() should not show Linked Projects section when snapshot.projects is empty."""
    data = _base_progress("Solo Project")
    # linked_snapshot.projects is empty list — default
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.status()

    assert result is True
    output = capsys.readouterr().out
    assert "Linked Projects" not in output


def test_status_shows_archive_history_summary(temp_dir, capsys):
    """status() should display archive history count and latest entry."""
    history = [
        {
            "archive_id": "proj-20260101T120000-abc",
            "project_name": "Old Run",
            "reason": "completion",
            "archived_at": "2026-01-01T12:00:00Z",
            "completed_features": 5,
            "total_features": 5,
        }
    ]
    history_path = (
        temp_dir
        / "docs"
        / "progress-tracker"
        / "state"
        / progress_manager.PROGRESS_HISTORY_JSON
    )
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")

    data = _base_progress("Current Project")
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.status()

    assert result is True
    output = capsys.readouterr().out
    assert "Archive History" in output
    assert "1 total" in output
    assert "Old Run" in output
    assert "completion" in output


def test_status_hides_archive_section_when_no_history(temp_dir, capsys):
    """status() should not show Archive History section when no archives exist."""
    data = _base_progress("Fresh Project")
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.status()

    assert result is True
    output = capsys.readouterr().out
    assert "Archive History" not in output


def test_status_handles_missing_linked_snapshot_key(temp_dir, capsys):
    """status() should not crash when linked_snapshot key is entirely absent."""
    data = _base_progress("Minimal Project")
    del data["linked_snapshot"]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.status()

    assert result is True
    output = capsys.readouterr().out
    assert "Linked Projects" not in output


def test_generate_prog_docs_check_passes() -> None:
    """generate_prog_docs.py --check must report docs are up to date."""
    root = Path(__file__).resolve().parents[1]
    script = root / "hooks" / "scripts" / "generate_prog_docs.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
