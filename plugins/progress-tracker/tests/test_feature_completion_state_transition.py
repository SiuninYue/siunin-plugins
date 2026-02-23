"""
Test feature-complete skill behavior: development_stage state transitions.

Verifies that /prog done (via feature-complete skill) correctly sets
development_stage = 'completed' and manages the full state transition
from planning → developing → completed.
"""

import json
from datetime import datetime

import pytest

import progress_manager


class TestFeatureCompletionStateTransition:
    """Test development_stage transitions during feature completion."""

    @pytest.fixture
    def feature_in_planning(self, temp_dir):
        """Create progress tracking with feature in 'planning' stage."""
        data = {
            "project_name": "Test Project",
            "created_at": datetime.now().isoformat(),
            "features": [
                {
                    "id": 1,
                    "name": "Test Feature",
                    "test_steps": ["step 1", "step 2"],
                    "completed": False,
                    "development_stage": "planning"
                }
            ],
            "current_feature_id": 1,
            "updated_at": datetime.now().isoformat(),
            "schema_version": "2.0"
        }

        claude_dir = temp_dir / '.claude'
        claude_dir.mkdir(parents=True, exist_ok=True)

        progress_file = claude_dir / 'progress.json'
        progress_file.write_text(json.dumps(data, indent=2))

        return progress_file

    def test_feature_starts_in_planning_stage(self, feature_in_planning):
        """Feature should start in 'planning' development_stage."""
        data = progress_manager.load_progress_json()
        feature = data["features"][0]

        assert feature["id"] == 1
        assert feature["development_stage"] == "planning"
        assert feature["completed"] is False

    def test_set_development_stage_to_developing(self, feature_in_planning):
        """Can transition from planning to developing."""
        # Set to developing
        result = progress_manager.set_development_stage("developing")
        assert result is True

        # Verify it's set
        data = progress_manager.load_progress_json()
        feature = data["features"][0]
        assert feature["development_stage"] == "developing"

    def test_complete_feature_sets_development_stage_completed(self, feature_in_planning):
        """Feature completion should set development_stage = 'completed'."""
        # First transition to developing
        progress_manager.set_development_stage("developing")

        # Then complete the feature
        result = progress_manager.complete_feature(1, commit_hash="abc123")
        assert result is True

        # Verify development_stage is 'completed'
        data = progress_manager.load_progress_json()
        feature = data["features"][0]

        assert feature["development_stage"] == "completed"
        assert feature["completed"] is True

    def test_complete_feature_records_completed_at_timestamp(self, feature_in_planning):
        """Feature completion should record completed_at timestamp."""
        before_complete = datetime.now().isoformat()

        progress_manager.complete_feature(1, commit_hash="abc123")

        after_complete = datetime.now().isoformat()

        data = progress_manager.load_progress_json()
        feature = data["features"][0]

        assert "completed_at" in feature
        completed_at = feature["completed_at"]

        # Verify timestamp is between before and after
        assert before_complete <= completed_at <= after_complete

    def test_complete_feature_clears_current_feature_id(self, feature_in_planning):
        """Feature completion should clear current_feature_id."""
        data = progress_manager.load_progress_json()
        assert data["current_feature_id"] == 1

        progress_manager.complete_feature(1, commit_hash="abc123")

        data = progress_manager.load_progress_json()
        assert data["current_feature_id"] is None

    def test_full_state_transition_planning_to_developing_to_completed(self, feature_in_planning):
        """
        Test the full state transition:
        planning → developing → completed
        """
        # Initial state: planning
        data = progress_manager.load_progress_json()
        feature = data["features"][0]
        assert feature["development_stage"] == "planning"

        # Transition to developing
        progress_manager.set_development_stage("developing")
        data = progress_manager.load_progress_json()
        feature = data["features"][0]
        assert feature["development_stage"] == "developing"
        assert feature["completed"] is False

        # Transition to completed
        progress_manager.complete_feature(1, commit_hash="xyz789")
        data = progress_manager.load_progress_json()
        feature = data["features"][0]
        assert feature["development_stage"] == "completed"
        assert feature["completed"] is True
        assert "completed_at" in feature
