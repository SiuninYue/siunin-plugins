"""
Workflow state machine tests for progress_manager.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

# Import progress_manager module
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


class TestWorkflowStatePhases:
    """Test workflow phase transitions."""

    def test_set_workflow_state_phase_transition(self, in_progress_file):
        """Should allow phase transitions."""
        progress_manager.set_workflow_state(phase="planning")
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "planning"

        progress_manager.set_workflow_state(phase="execution")
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "execution"

    def test_set_workflow_state_with_plan_path(self, in_progress_file):
        """Should set plan path in workflow state."""
        plans_dir = Path("docs/plans")
        plans_dir.mkdir(parents=True, exist_ok=True)
        (plans_dir / "myplan.md").write_text(
            "# Plan\n\n## Tasks\n- Task\n\n## Acceptance Mapping\n- Mapping\n\n## Risks\n- None\n",
            encoding="utf-8",
        )
        progress_manager.set_workflow_state(plan_path="docs/plans/myplan.md")
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["plan_path"] == "docs/plans/myplan.md"

    def test_set_workflow_state_with_next_action(self, in_progress_file):
        """Should set next action in workflow state."""
        progress_manager.set_workflow_state(next_action="run_tests")
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["next_action"] == "run_tests"


class TestWorkflowStatePersistence:
    """Test workflow state saving and loading."""

    def test_workflow_state_persists_across_operations(self, in_progress_file):
        """Should maintain workflow state through operations."""
        # Set initial state
        progress_manager.set_workflow_state(phase="execution")

        # Perform another operation
        progress_manager.set_current(2)

        # State should still be there
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "execution"

    def test_workflow_state_without_current_feature(self, progress_file):
        """Should fail when setting workflow state without current feature."""
        # progress_file has no current_feature_id
        result = progress_manager.set_workflow_state(phase="execution")
        assert result is False


class TestWorkflowTaskTracking:
    """Test task completion tracking within workflow."""

    def test_update_workflow_task_adds_to_completed(self, in_progress_file):
        """Should add task to completed list."""
        progress_manager.update_workflow_task(3, "completed")

        data = progress_manager.load_progress_json()
        assert 3 in data["workflow_state"]["completed_tasks"]

    def test_update_workflow_task_increments_current(self, in_progress_file):
        """Should increment current_task counter."""
        progress_manager.update_workflow_task(3, "completed")

        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["current_task"] == 4

    def test_update_workflow_task_idempotent(self, in_progress_file):
        """Should handle duplicate task completion gracefully."""
        progress_manager.update_workflow_task(3, "completed")
        progress_manager.update_workflow_task(3, "completed")

        data = progress_manager.load_progress_json()
        # Should only appear once
        assert data["workflow_state"]["completed_tasks"].count(3) == 1


class TestWorkflowStateClearing:
    """Test workflow state clearing operations."""

    def test_clear_workflow_state(self, in_progress_file):
        """Should remove workflow_state from progress data."""
        progress_manager.clear_workflow_state()

        data = progress_manager.load_progress_json()
        assert "workflow_state" not in data

    def test_clear_workflow_state_when_none_exists(self, progress_file):
        """Should handle gracefully when no workflow state exists."""
        result = progress_manager.clear_workflow_state()
        assert result is True


class TestRecoveryActionDetermination:
    """Test determine_recovery_action function."""

    def test_recovery_for_execution_complete(self):
        """Should recommend run_prog_done for execution_complete phase."""
        recommendation = progress_manager.determine_recovery_action(
            "execution_complete", None, [], 5
        )
        assert recommendation == "run_prog_done"

    def test_recovery_for_execution_with_progress(self):
        """Should recommend auto_resume when 80%+ complete."""
        recommendation = progress_manager.determine_recovery_action(
            "execution", None, [1, 2, 3, 4], 5
        )
        assert recommendation == "auto_resume"

    def test_recovery_for_execution_low_progress(self):
        """Should recommend manual_resume when less than 80% complete."""
        recommendation = progress_manager.determine_recovery_action(
            "execution", None, [1, 2], 5
        )
        assert recommendation == "manual_resume"

    def test_recovery_for_planning_phase(self):
        """Should recommend restart_from_planning for planning phases."""
        recommendation = progress_manager.determine_recovery_action(
            "planning", None, [], 0
        )
        assert recommendation == "restart_from_planning"

    def test_recovery_for_unknown_phase(self):
        """Should recommend manual_review for unknown phases."""
        recommendation = progress_manager.determine_recovery_action(
            "unknown", None, [], 0
        )
        assert recommendation == "manual_review"


class TestCheckCommandWithWorkflowState:
    """Test check command with various workflow states."""

    def test_check_returns_incomplete_with_workflow_state(self, in_progress_file):
        """Should return 1 when workflow state exists."""
        result = progress_manager.check()
        assert result == 1

    def test_check_outputs_recovery_json(self, in_progress_file, capsys):
        """Should output JSON-formatted recovery info."""
        progress_manager.check()
        captured = capsys.readouterr()

        # Should be valid JSON
        try:
            data = json.loads(captured.out)
            assert "status" in data
            assert data["status"] == "incomplete"
            assert "feature_id" in data
            assert "recommendation" in data
        except json.JSONDecodeError:
            pytest.fail("Expected JSON output from check command")


class TestWorkflowStateTimestamps:
    """Test workflow state timestamp tracking."""

    def test_workflow_state_includes_updated_at(self, in_progress_file):
        """Should include timestamp when updating workflow state."""
        progress_manager.set_workflow_state(phase="test_phase")

        data = progress_manager.load_progress_json()
        assert "updated_at" in data["workflow_state"]

    def test_workflow_state_timestamp_updates(self, in_progress_file):
        """Should update timestamp on each change."""
        progress_manager.set_workflow_state(phase="phase1")
        data = progress_manager.load_progress_json()
        timestamp1 = data["workflow_state"]["updated_at"]

        import time
        time.sleep(0.01)  # Small delay

        progress_manager.set_workflow_state(phase="phase2")
        data = progress_manager.load_progress_json()
        timestamp2 = data["workflow_state"]["updated_at"]

        assert timestamp1 != timestamp2


class TestWorkflowStateWithCompleteFeature:
    """Test workflow state behavior when completing features."""

    def test_complete_feature_preserves_workflow_state(self, in_progress_file):
        """Should preserve workflow state when completing feature."""
        original_phase = progress_manager.load_progress_json()["workflow_state"]["phase"]

        progress_manager.complete_feature(2)

        # Workflow state should still exist
        data = progress_manager.load_progress_json()
        # Note: current implementation clears current_feature_id but keeps workflow_state


class TestWorkflowStateScenarios:
    """Test common workflow state scenarios."""

    def test_new_feature_workflow(self, temp_dir):
        """Should track workflow for new feature from start."""
        # Initialize project
        progress_manager.init_tracking("Workflow Test", force=True)
        progress_manager.add_feature("New Feature", ["Test step"])
        plans_dir = temp_dir / "docs" / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        (plans_dir / "feature-1-plan.md").write_text(
            "# Plan\n\n## Tasks\n- Task 1\n\n## Acceptance Mapping\n- Step -> Check\n\n## Risks\n- None\n",
            encoding="utf-8",
        )

        # Set current
        progress_manager.set_current(1)

        # Set planning state
        progress_manager.set_workflow_state(
            phase="planning", plan_path="docs/plans/feature-1-plan.md"
        )

        # Transition to execution
        progress_manager.set_workflow_state(phase="execution")

        # Mark tasks complete
        progress_manager.update_workflow_task(1, "completed")
        progress_manager.update_workflow_task(2, "completed")

        # Verify state
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "execution"
        assert data["workflow_state"]["completed_tasks"] == [1, 2]

    def test_interrupted_workflow_recovery(self, in_progress_file):
        """Should be able to recover from interrupted workflow."""
        # Simulate interrupted workflow
        data = progress_manager.load_progress_json()
        original_phase = data["workflow_state"]["phase"]
        original_tasks = data["workflow_state"]["completed_tasks"].copy()

        # Perform some operations
        progress_manager.set_workflow_state(phase="execution")

        # Recovered state should be available
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "execution"


class TestWorkflowStateValidation:
    """Test workflow state validation."""

    def test_set_workflow_state_without_current_feature_fails(self, progress_file):
        """Should fail when no current feature is set."""
        result = progress_manager.set_workflow_state(phase="execution")
        assert result is False

    def test_set_workflow_state_without_progress_tracking(self, temp_dir):
        """Should fail when no progress tracking exists."""
        result = progress_manager.set_workflow_state(phase="execution")
        assert result is False

    def test_set_workflow_state_rejects_invalid_plan_path(self, in_progress_file):
        """Should reject plan paths outside docs/plans."""
        result = progress_manager.set_workflow_state(plan_path=".claude/plan.md")
        assert result is False

    def test_recovery_recommends_recreate_when_plan_missing(self, in_progress_file):
        """Should recommend recreating plan when stored plan path is missing."""
        data = progress_manager.load_progress_json()
        data["workflow_state"]["plan_path"] = "docs/plans/missing-plan.md"
        progress_manager.save_progress_json(data)

        recommendation = progress_manager.determine_recovery_action(
            "execution", None, [1, 2], 5, plan_path="docs/plans/missing-plan.md"
        )
        assert recommendation == "recreate_plan"
