#!/usr/bin/env python3
"""
Behavior tests for /prog start command functionality.

Tests verify:
1. Error when no active feature exists
2. Sets development_stage = 'developing' when feature is active
3. Records started_at timestamp
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Import progress_manager module
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temp directory and change to it."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)


@pytest.fixture
def sample_progress_data():
    """Sample progress tracking data with multiple features."""
    return {
        "project_name": "Test Project",
        "created_at": "2026-02-22T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Feature 1",
                "test_steps": [],
                "completed": True,
            },
            {
                "id": 2,
                "name": "Feature 2",
                "test_steps": [],
                "completed": False,
                "development_stage": "planning",
            },
        ],
        "current_feature_id": None,
        "updated_at": "2026-02-22T00:00:00Z",
        "schema_version": "2.0",
    }


class TestProgStartErrorHandling:
    """Test /prog start error conditions."""

    def test_no_progress_tracking_exists(self, temp_dir):
        """Should error when no progress tracking found."""
        with patch("progress_manager.load_progress_json", return_value=None):
            result = progress_manager.set_development_stage("developing")
            assert result is False

    def test_no_active_feature(self, temp_dir, sample_progress_data):
        """Should error when no active feature (current_feature_id is None)."""
        sample_progress_data["current_feature_id"] = None
        with patch(
            "progress_manager.load_progress_json", return_value=sample_progress_data
        ):
            result = progress_manager.set_development_stage("developing")
            assert result is False

    def test_feature_id_not_found(self, temp_dir, sample_progress_data):
        """Should error when feature ID doesn't exist."""
        sample_progress_data["current_feature_id"] = 999  # Non-existent
        with patch(
            "progress_manager.load_progress_json", return_value=sample_progress_data
        ):
            result = progress_manager.set_development_stage("developing")
            assert result is False


class TestProgStartSuccess:
    """Test /prog start success scenarios."""

    def test_sets_development_stage_developing(self, temp_dir, sample_progress_data, capsys):
        """Should set development_stage to 'developing' when feature is active."""
        sample_progress_data["current_feature_id"] = 2
        saved_data = None

        def mock_save(data):
            nonlocal saved_data
            saved_data = data

        with patch(
            "progress_manager.load_progress_json", return_value=sample_progress_data
        ), patch("progress_manager.save_progress_json", side_effect=mock_save), patch(
            "progress_manager.generate_progress_md", return_value=""
        ), patch("progress_manager.save_progress_md"):
            result = progress_manager.set_development_stage("developing")
            assert result is True
            assert saved_data["features"][1]["development_stage"] == "developing"

    def test_records_started_at_timestamp(self, temp_dir, sample_progress_data):
        """Should record started_at timestamp when transitioning to 'developing'."""
        sample_progress_data["current_feature_id"] = 2
        sample_progress_data["features"][1]["started_at"] = None  # Not set initially

        saved_data = None

        def mock_save(data):
            nonlocal saved_data
            saved_data = data

        with patch(
            "progress_manager.load_progress_json", return_value=sample_progress_data
        ), patch("progress_manager.save_progress_json", side_effect=mock_save), patch(
            "progress_manager.generate_progress_md", return_value=""
        ), patch("progress_manager.save_progress_md"):
            before_time = datetime.now().isoformat()
            result = progress_manager.set_development_stage("developing")
            after_time = datetime.now().isoformat()

            assert result is True
            started_at = saved_data["features"][1]["started_at"]
            assert started_at is not None
            assert started_at.endswith("Z")
            # Verify timestamp is between before and after (remove Z for comparison)
            assert before_time <= started_at[:-1] <= after_time

    def test_preserves_existing_started_at(self, temp_dir, sample_progress_data):
        """Should not overwrite existing started_at timestamp."""
        original_time = "2026-02-20T10:00:00Z"
        sample_progress_data["current_feature_id"] = 2
        sample_progress_data["features"][1]["started_at"] = original_time

        saved_data = None

        def mock_save(data):
            nonlocal saved_data
            saved_data = data

        with patch(
            "progress_manager.load_progress_json", return_value=sample_progress_data
        ), patch("progress_manager.save_progress_json", side_effect=mock_save), patch(
            "progress_manager.generate_progress_md", return_value=""
        ), patch("progress_manager.save_progress_md"):
            result = progress_manager.set_development_stage("developing")
            assert result is True
            assert saved_data["features"][1]["started_at"] == original_time
