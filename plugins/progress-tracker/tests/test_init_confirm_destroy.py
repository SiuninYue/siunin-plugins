"""Tests for prog init --force confirm-destroy protection (spec: 2026-05-14)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import sys

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


def _mark_feature_completed(temp_dir: Path, feature_index: int = 0) -> None:
    """Write completed=True onto a feature in the current project's progress.json."""
    json_path = (
        temp_dir / "docs" / "progress-tracker" / "state" / "progress.json"
    )
    data = json.loads(json_path.read_text())
    data["features"][feature_index]["completed"] = True
    json_path.write_text(json.dumps(data))


class TestInitForceConfirmDestroy:
    def test_init_force_blocked_when_completed_features_exist(self, temp_dir, capsys):
        """init_tracking(force=True) returns False and prints an error when completed_count > 0."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        _mark_feature_completed(temp_dir)

        result = progress_manager.init_tracking("New Project", force=True)

        assert result is False
        captured = capsys.readouterr()
        assert "completed feature(s) detected" in captured.out
        assert "confirm_destroy=True" in captured.out
        # Verify original data was NOT overwritten
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "Real Project"

    def test_init_force_confirm_destroy_bypasses_protection(self, temp_dir):
        """init_tracking(force=True, confirm_destroy=True) proceeds despite completed features."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        _mark_feature_completed(temp_dir)

        result = progress_manager.init_tracking(
            "New Project", force=True, confirm_destroy=True
        )

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "New Project"

    def test_init_force_allowed_when_no_completed_features(self, temp_dir):
        """init_tracking(force=True) without confirm_destroy proceeds when all features are pending."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        # Feature remains completed=False — no confirm_destroy needed

        result = progress_manager.init_tracking("New Project", force=True)

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "New Project"

    def test_init_force_allowed_on_empty_project(self, temp_dir):
        """init_tracking(force=True) on a project with no features proceeds without confirm_destroy."""
        progress_manager.init_tracking("First", force=True)

        result = progress_manager.init_tracking("Second", force=True)

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "Second"

    def test_cli_init_force_blocked_without_confirm_destroy(self, temp_dir, capsys):
        """CLI: prog init --force returns False and prints error when completed features exist."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        _mark_feature_completed(temp_dir)

        with patch(
            "sys.argv",
            ["progress_manager.py", "init", "--force", "New Project"],
        ):
            result = progress_manager.main()

        assert result is False
        captured = capsys.readouterr()
        assert "completed feature(s) detected" in captured.out

    def test_cli_init_force_confirm_destroy_succeeds(self, temp_dir):
        """CLI: prog init --force --confirm-destroy proceeds with completed features."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        _mark_feature_completed(temp_dir)

        with patch(
            "sys.argv",
            ["progress_manager.py", "init", "--force", "--confirm-destroy", "New Project"],
        ):
            result = progress_manager.main()

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "New Project"

    def test_cli_confirm_destroy_without_force_is_noop(self, temp_dir):
        """CLI: --confirm-destroy without --force is silently ignored; init proceeds normally."""
        with patch(
            "sys.argv",
            ["progress_manager.py", "init", "--confirm-destroy", "My Project"],
        ):
            result = progress_manager.main()

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "My Project"
