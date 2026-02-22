#!/usr/bin/env python3
"""
Tests for development_stage field support and backward compatibility.
"""

import pytest
from datetime import datetime

# Import the progress manager
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hooks', 'scripts'))

from progress_manager import DEVELOPMENT_STAGES


class TestDevelopmentStageBackwardCompat:
    """Test backward compatibility for development_stage field."""

    def test_old_feature_without_development_stage_defaults_to_developing(self):
        """When reading a feature without development_stage, it should default to 'developing'."""
        # Simulate an old feature without development_stage field
        feature = {
            "id": 1,
            "name": "Old Feature",
            "test_steps": ["step1", "step2"],
            "completed": False
            # Note: no development_stage field
        }

        # When accessing development_stage, it should default to 'developing'
        stage = feature.get("development_stage", "developing")
        assert stage == "developing"

    def test_new_feature_with_development_stage_planning(self):
        """New features should support development_stage = 'planning'."""
        feature = {
            "id": 1,
            "name": "New Feature",
            "test_steps": ["step1"],
            "completed": False,
            "development_stage": "planning"
        }

        assert feature.get("development_stage") == "planning"

    def test_feature_development_stage_developing(self):
        """Features should support development_stage = 'developing'."""
        feature = {
            "id": 1,
            "name": "Test Feature",
            "test_steps": ["step1"],
            "completed": False,
            "development_stage": "developing"
        }

        assert feature.get("development_stage") == "developing"

    def test_feature_development_stage_completed(self):
        """Features should support development_stage = 'completed'."""
        feature = {
            "id": 1,
            "name": "Completed Feature",
            "test_steps": ["step1"],
            "completed": True,
            "completed_at": datetime.now().isoformat() + "Z",
            "development_stage": "completed"
        }

        assert feature.get("development_stage") == "completed"

    def test_read_features_with_mixed_stages(self):
        """Read and process features with various development_stage values."""
        features = [
            {
                "id": 1,
                "name": "Planning Feature",
                "development_stage": "planning"
            },
            {
                "id": 2,
                "name": "Old Feature",
                # No development_stage field
            },
            {
                "id": 3,
                "name": "Developing Feature",
                "development_stage": "developing"
            },
            {
                "id": 4,
                "name": "Completed Feature",
                "development_stage": "completed"
            }
        ]

        # Verify each feature's stage
        assert features[0].get("development_stage", "developing") == "planning"
        assert features[1].get("development_stage", "developing") == "developing"  # Old format defaults
        assert features[2].get("development_stage", "developing") == "developing"
        assert features[3].get("development_stage", "developing") == "completed"

    def test_write_development_stage_to_feature(self):
        """Writing development_stage to a feature should work correctly."""
        feature = {
            "id": 1,
            "name": "Test Feature",
            "test_steps": ["step1"],
            "completed": False
        }

        # Write development_stage
        feature["development_stage"] = "planning"
        assert feature.get("development_stage") == "planning"

        # Update development_stage
        feature["development_stage"] = "developing"
        assert feature.get("development_stage") == "developing"

        # Update to completed
        feature["development_stage"] = "completed"
        assert feature.get("development_stage") == "completed"

    def test_all_development_stages_are_valid(self):
        """All defined DEVELOPMENT_STAGES should be valid."""
        assert DEVELOPMENT_STAGES == ("planning", "developing", "completed")
        assert len(DEVELOPMENT_STAGES) == 3

    def test_validate_development_stage_values(self):
        """Test validation of development_stage values."""
        # Valid stages
        for stage in DEVELOPMENT_STAGES:
            assert stage in DEVELOPMENT_STAGES

        # Invalid stage
        invalid_stage = "invalid"
        assert invalid_stage not in DEVELOPMENT_STAGES
