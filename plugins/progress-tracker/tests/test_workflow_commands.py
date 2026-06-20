"""Injected-unit tests for workflow_commands.py (F27 extraction)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

_HOOKS_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import workflow_commands
from workflow_commands import WorkflowCommandsServices


def _make_svc(data, tmp_path, **overrides):
    """Build a WorkflowCommandsServices over an in-memory data dict."""
    saved = []
    md_saved = []

    defaults = dict(
        load_progress_json_fn=lambda: data,
        save_progress_json_fn=saved.append,
        generate_progress_md_fn=lambda d: "# md",
        save_progress_md_fn=md_saved.append,
        update_runtime_context_fn=lambda d, source: False,
        update_execution_context_fn=lambda ws, source: None,
        build_runtime_context_fn=lambda d, source: {},
        validate_plan_path_fn=lambda p, require_exists=False: {
            "valid": True,
            "normalized_path": p,
            "error": None,
        },
        validate_plan_document_fn=lambda p: {"valid": True, "errors": [], "warnings": []},
        find_project_root_fn=lambda: tmp_path,
        get_progress_dir_fn=lambda: tmp_path / "docs" / "progress-tracker" / "state",
        load_checkpoints_fn=lambda: {"entries": []},
        latest_checkpoint_entry_for_feature_fn=lambda checkpoints, fid: None,
        build_checkpoint_context_fn=lambda entry: None,
    )
    defaults.update(overrides)
    svc = WorkflowCommandsServices(**defaults)
    return svc, saved, md_saved


def _base_data(**extra):
    data = {
        "project_name": "WC Test",
        "features": [
            {"id": 1, "name": "F1", "test_steps": ["s"], "completed": False},
        ],
        "current_feature_id": 1,
    }
    data.update(extra)
    return data


class TestSetWorkflowState:
    def test_phase_transition_persists(self, tmp_path):
        data = _base_data()
        svc, saved, md_saved = _make_svc(data, tmp_path)

        result = workflow_commands.set_workflow_state_command(phase="planning", svc=svc)

        assert result is True
        assert saved and saved[0]["workflow_state"]["phase"] == "planning"
        assert md_saved == [""]

    def test_invalid_plan_path_rejected(self, tmp_path):
        data = _base_data()
        svc, saved, _ = _make_svc(
            data,
            tmp_path,
            validate_plan_path_fn=lambda p, require_exists=False: {
                "valid": False,
                "normalized_path": None,
                "error": "bad path",
            },
        )

        result = workflow_commands.set_workflow_state_command(
            phase="execution", plan_path="docs/notes/x.md", svc=svc
        )

        assert result is False
        assert saved == []

    def test_no_active_feature_errors(self, tmp_path):
        data = _base_data(current_feature_id=None)
        svc, saved, _ = _make_svc(data, tmp_path)

        result = workflow_commands.set_workflow_state_command(phase="planning", svc=svc)

        assert result is False
        assert saved == []


class TestUpdateWorkflowTask:
    def test_marks_task_completed_and_advances(self, tmp_path):
        data = _base_data(workflow_state={"phase": "execution", "total_tasks": 5})
        svc, saved, _ = _make_svc(data, tmp_path)

        result = workflow_commands.update_workflow_task_command(3, "completed", svc=svc)

        assert result is True
        ws = saved[0]["workflow_state"]
        assert 3 in ws["completed_tasks"]
        assert ws["current_task"] == 4

    def test_duplicate_completion_is_idempotent(self, tmp_path):
        data = _base_data(
            workflow_state={
                "phase": "execution",
                "completed_tasks": [3],
                "current_task": 4,
            }
        )
        svc, saved, _ = _make_svc(data, tmp_path)

        workflow_commands.update_workflow_task_command(3, "completed", svc=svc)

        ws = saved[0]["workflow_state"]
        assert ws["completed_tasks"].count(3) == 1


class TestClearWorkflowState:
    def test_clears_existing_state(self, tmp_path):
        data = _base_data(workflow_state={"phase": "execution"})
        svc, saved, _ = _make_svc(data, tmp_path)

        result = workflow_commands.clear_workflow_state_command(svc=svc)

        assert result is True
        assert "workflow_state" not in saved[0]

    def test_noop_when_absent(self, tmp_path):
        data = _base_data()
        svc, saved, _ = _make_svc(data, tmp_path)

        result = workflow_commands.clear_workflow_state_command(svc=svc)

        assert result is True
        assert saved == []


class TestHealthCheck:
    def test_healthy_returns_zero(self, tmp_path, capsys):
        data = _base_data(bugs=[])
        svc, _, _ = _make_svc(data, tmp_path)

        with patch.object(workflow_commands, "GIT_VALIDATOR_AVAILABLE", True), \
             patch.object(workflow_commands, "is_git_repository", lambda: True):
            result = workflow_commands.health_check_command(svc=svc)

        payload = json.loads(capsys.readouterr().out)
        assert result == 0
        assert payload["status"] == "healthy"
        assert payload["features_count"] == 1

    def test_degraded_when_git_unhealthy(self, tmp_path, capsys):
        data = _base_data()
        svc, _, _ = _make_svc(data, tmp_path)

        with patch.object(workflow_commands, "GIT_VALIDATOR_AVAILABLE", True), \
             patch.object(workflow_commands, "is_git_repository", lambda: False):
            result = workflow_commands.health_check_command(svc=svc)

        payload = json.loads(capsys.readouterr().out)
        assert result == 1
        assert payload["status"] == "degraded"


class TestValidatePlan:
    def test_explicit_plan_path_passes(self, tmp_path, capsys):
        data = _base_data()
        svc, _, _ = _make_svc(data, tmp_path)

        result = workflow_commands.validate_plan_command("docs/plans/p.md", svc=svc)

        assert result is True
        assert "Plan validation passed" in capsys.readouterr().out

    def test_falls_back_to_workflow_state_plan(self, tmp_path, capsys):
        data = _base_data(workflow_state={"plan_path": "docs/plans/from-state.md"})
        seen = []
        svc, _, _ = _make_svc(
            data,
            tmp_path,
            validate_plan_document_fn=lambda p: (
                seen.append(p) or {"valid": True, "errors": [], "warnings": []}
            ),
        )

        result = workflow_commands.validate_plan_command(svc=svc)

        assert result is True
        assert seen == ["docs/plans/from-state.md"]

    def test_direct_tdd_skips_plan_requirement(self, tmp_path, capsys):
        data = _base_data()
        data["features"][0]["ai_metrics"] = {"workflow_path": "direct_tdd"}
        svc, _, _ = _make_svc(data, tmp_path)

        result = workflow_commands.validate_plan_command(svc=svc)

        assert result is True
        assert "direct_tdd" in capsys.readouterr().out

    def test_missing_plan_fails(self, tmp_path, capsys):
        data = _base_data()
        svc, _, _ = _make_svc(data, tmp_path)

        result = workflow_commands.validate_plan_command(svc=svc)

        assert result is False

    def test_invalid_document_reports_errors(self, tmp_path, capsys):
        data = _base_data()
        svc, _, _ = _make_svc(
            data,
            tmp_path,
            validate_plan_document_fn=lambda p: {
                "valid": False,
                "errors": ["missing Tasks section"],
                "warnings": [],
            },
        )

        result = workflow_commands.validate_plan_command("docs/plans/p.md", svc=svc)

        assert result is False
        assert "missing Tasks section" in capsys.readouterr().out


class TestAnalyzeReconcileState:
    def test_invalid_data_needs_manual_review(self, tmp_path):
        svc, _, _ = _make_svc(None, tmp_path)

        report = workflow_commands.analyze_reconcile_state_command(svc=svc)

        assert report["diagnosis"] == "needs_manual_review"
        assert report["recommended_next_step"] == "repair workflow_state"

    def test_invalid_current_feature_needs_manual_review(self, tmp_path):
        data = _base_data(current_feature_id=999)
        svc, _, _ = _make_svc(data, tmp_path)

        report = workflow_commands.analyze_reconcile_state_command(data, svc=svc)

        assert report["diagnosis"] == "needs_manual_review"
        assert report["recommended_next_step"] == "clear invalid current_feature_id"

    def test_execution_complete_is_implementation_ahead(self, tmp_path):
        data = _base_data(workflow_state={"phase": "execution_complete"})
        svc, _, _ = _make_svc(data, tmp_path)

        report = workflow_commands.analyze_reconcile_state_command(data, svc=svc)

        assert report["diagnosis"] == "implementation_ahead_of_tracker"
        assert report["recommended_next_step"] == "/prog done"

    def test_no_active_feature_suggests_prog_next(self, tmp_path):
        data = _base_data(current_feature_id=None)
        svc, _, _ = _make_svc(data, tmp_path)

        report = workflow_commands.analyze_reconcile_state_command(data, svc=svc)

        assert report["diagnosis"] == "in_sync"
        assert report["recommended_next_step"] == "/prog next"


class TestReconcileCommand:
    def test_missing_tracking_returns_false(self, tmp_path, capsys):
        svc, _, _ = _make_svc(None, tmp_path)

        result = workflow_commands.reconcile_command(svc=svc)

        assert result is False
        assert "No progress tracking found" in capsys.readouterr().out

    def test_json_output_shape(self, tmp_path, capsys):
        data = _base_data()
        svc, _, _ = _make_svc(data, tmp_path)

        result = workflow_commands.reconcile_command(output_json=True, svc=svc)

        assert result is True
        payload = json.loads(capsys.readouterr().out)
        assert payload["diagnosis"] in workflow_commands.RECONCILE_DIAGNOSES
        assert payload["recommended_next_step"] in workflow_commands.RECONCILE_NEXT_STEPS

    def test_text_output_includes_diagnosis(self, tmp_path, capsys):
        data = _base_data()
        svc, _, _ = _make_svc(data, tmp_path)

        result = workflow_commands.reconcile_command(svc=svc)

        out = capsys.readouterr().out
        assert result is True
        assert "## Reconcile" in out
        assert "Diagnosis:" in out


class _StubAuditLog:
    def __init__(self, records):
        self._records = records

    def read_audit_log(self, ascending=True, project_root=None):
        return list(self._records)

    def deduplicate_audit_log(self, records):
        return {
            "kept": list(records),
            "id_conflicts": 0,
            "semantic_duplicates_removed": [],
        }


class TestCmdReconcileState:
    def test_no_events_no_drift(self, tmp_path, capsys):
        data = _base_data()
        svc, saved, _ = _make_svc(data, tmp_path)

        with patch.object(workflow_commands, "audit_log", _StubAuditLog([])):
            result = workflow_commands.cmd_reconcile_state_command(
                check_only=True, svc=svc
            )

        assert result["drift"] is False
        assert saved == []

    def test_drift_detected_and_fixed(self, tmp_path):
        data = _base_data()
        svc, saved, _ = _make_svc(data, tmp_path)
        records = [
            {
                "event_type": "feature_completed",
                "feature_id": 1,
                "timestamp": "2026-06-01T00:00:00Z",
            }
        ]

        with patch.object(workflow_commands, "audit_log", _StubAuditLog(records)):
            result = workflow_commands.cmd_reconcile_state_command(
                check_only=False, svc=svc
            )

        assert result["drift"] is True
        assert result["drifted_features"] == [1]
        assert result["fixed"] is True
        assert saved[0]["features"][0]["completed"] is True

    def test_check_only_does_not_save(self, tmp_path):
        data = _base_data()
        svc, saved, _ = _make_svc(data, tmp_path)
        records = [
            {
                "event_type": "feature_completed",
                "feature_id": 1,
                "timestamp": "2026-06-01T00:00:00Z",
            }
        ]

        with patch.object(workflow_commands, "audit_log", _StubAuditLog(records)):
            result = workflow_commands.cmd_reconcile_state_command(
                check_only=True, svc=svc
            )

        assert result["drift"] is True
        assert result["fixed"] is False
        assert saved == []

    def test_audit_log_unavailable_returns_empty_result(self, tmp_path, capsys):
        data = _base_data()
        svc, saved, _ = _make_svc(data, tmp_path)

        with patch.object(workflow_commands, "audit_log", None):
            result = workflow_commands.cmd_reconcile_state_command(svc=svc)

        assert result["drift"] is False
        assert "audit_log module unavailable" in capsys.readouterr().out
