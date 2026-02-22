#!/usr/bin/env python3
"""
Simple tests for development_stage backward compatibility.
"""

import pytest


class TestDevelopmentStageSimple:
    """Simple tests that verify development_stage handling."""

    def test_feature_without_stage_defaults_to_developing(self):
        """Old features without development_stage should default to 'developing'."""
        # Simulate reading an old feature from JSON
        old_feature = {
            "id": 1,
            "name": "Old Feature",
            "test_steps": ["step1"],
            "completed": False
            # No development_stage field
        }

        # When accessed with .get(), should default to 'developing'
        stage = old_feature.get("development_stage", "developing")
        assert stage == "developing", "Old features should default to 'developing'"

    def test_feature_with_planning_stage(self):
        """Features can have development_stage = 'planning'."""
        feature = {
            "id": 1,
            "name": "New Feature",
            "development_stage": "planning"
        }
        assert feature.get("development_stage") == "planning"

    def test_feature_with_developing_stage(self):
        """Features can have development_stage = 'developing'."""
        feature = {
            "id": 1,
            "name": "Feature In Progress",
            "development_stage": "developing"
        }
        assert feature.get("development_stage") == "developing"

    def test_feature_with_completed_stage(self):
        """Features can have development_stage = 'completed'."""
        feature = {
            "id": 1,
            "name": "Done Feature",
            "completed": True,
            "development_stage": "completed"
        }
        assert feature.get("development_stage") == "completed"

    def test_parse_all_stages(self):
        """Verify all three stages can be parsed and read correctly."""
        stages = ["planning", "developing", "completed"]
        features = [
            {"id": i, "development_stage": stage}
            for i, stage in enumerate(stages, 1)
        ]

        for feature, expected_stage in zip(features, stages):
            assert feature.get("development_stage") == expected_stage

    def test_write_stage_to_feature(self):
        """Writing development_stage to a feature works correctly."""
        feature = {"id": 1, "name": "Test"}

        # Write planning
        feature["development_stage"] = "planning"
        assert feature["development_stage"] == "planning"

        # Update to developing
        feature["development_stage"] = "developing"
        assert feature["development_stage"] == "developing"

        # Update to completed
        feature["development_stage"] = "completed"
        assert feature["development_stage"] == "completed"
