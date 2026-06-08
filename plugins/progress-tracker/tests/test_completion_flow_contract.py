"""
RED tests for completion_flow module (Task 2 of TDD extraction).

These tests import from `completion_flow`, which does NOT exist yet.
Running this file confirms the RED state: ModuleNotFoundError.
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

# Ensure hooks/scripts is on sys.path (same as conftest.py)
_SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ──────────────────────────────────────────────────────────────────────────────
# This import will raise ModuleNotFoundError until completion_flow.py is created.
# ──────────────────────────────────────────────────────────────────────────────
from completion_flow import (  # noqa: E402
    AcceptanceTestResult,
    CompletionFlowServices,
    complete_feature_ai_metrics,
    save_archive_record,
    _run_acceptance_tests,
    _format_failure_reason,
    _validate_done_preconditions,
    cmd_done,
    complete_feature,
)


# ─────────────────────────── helpers ──────────────────────────────────────────

def _iso_minutes_ago(minutes: int) -> str:
    """Return an ISO-8601 timestamp for `minutes` ago."""
    ts = datetime.now(tz=timezone.utc) - timedelta(minutes=minutes)
    return ts.isoformat().replace("+00:00", "Z")


def _base_feature(feature_id: int = 1, **overrides) -> Dict[str, Any]:
    f = {
        "id": feature_id,
        "name": f"Feature {feature_id}",
        "completed": False,
        "development_stage": "in_development",
        "integration_status": "in_progress",
        "test_steps": [],
        "ai_metrics": {},
        "quality_gates": {"evaluator": {"status": "pass"}},
    }
    f.update(overrides)
    return f


def _base_data(
    feature_id: int = 1,
    phase: str = "execution_complete",
    feature_overrides: Optional[Dict] = None,
) -> Dict[str, Any]:
    feature = _base_feature(feature_id, **(feature_overrides or {}))
    return {
        "current_feature_id": feature_id,
        "features": [feature],
        "workflow_state": {
            "phase": phase,
            "plan_path": f"docs/features/F{feature_id}/plan.md",
        },
    }


def _noop_services(**overrides) -> CompletionFlowServices:
    """Return a CompletionFlowServices with safe no-op defaults."""
    defaults = dict(
        load_progress_json_fn=lambda: None,
        save_progress_json_fn=lambda _d: None,
        find_project_root_fn=lambda: Path("."),
        generate_progress_md_fn=lambda _d: "",
        save_progress_md_fn=lambda _s: None,
        record_sprint_artifact_fn=lambda **kw: None,
        require_sprint_contract_fn=lambda _f: None,
        notify_parent_sync_fn=lambda _s: None,
    )
    defaults.update(overrides)
    return CompletionFlowServices(**defaults)


# ─────────────────────────── Test 1 ───────────────────────────────────────────

def test_complete_feature_ai_metrics_records_duration():
    """AI metrics finalization writes finished_at and a non-negative duration."""
    started_at = _iso_minutes_ago(5)
    feature = _base_feature(1, ai_metrics={"started_at": started_at})
    data = {
        "current_feature_id": 1,
        "features": [feature],
        "workflow_state": {"phase": "execution_complete"},
    }

    saved: Dict[str, Any] = {}

    def capture_save(d: dict) -> None:
        saved.update(d)

    services = _noop_services(
        load_progress_json_fn=lambda: data,
        save_progress_json_fn=capture_save,
        generate_progress_md_fn=lambda _d: "",
        save_progress_md_fn=lambda _s: None,
    )

    result = complete_feature_ai_metrics(feature_id=1, services=services)
    assert result is True

    saved_feature = next(
        (f for f in saved.get("features", []) if f.get("id") == 1), None
    )
    assert saved_feature is not None, "Feature must appear in saved data"
    ai = saved_feature.get("ai_metrics", {})
    assert "finished_at" in ai, "finished_at must be set after completion"
    assert isinstance(ai["duration_seconds"], int), "duration_seconds must be int"
    assert ai["duration_seconds"] >= 0, "duration must be non-negative"


# ─────────────────────────── Test 2 ───────────────────────────────────────────

def test_save_archive_record_writes_archive_info():
    """save_archive_record stores archive_info with files_moved count."""
    feature = _base_feature(1)
    data = {"current_feature_id": 1, "features": [feature], "workflow_state": {}}
    saved: Dict[str, Any] = {}

    def capture_save(d: dict) -> None:
        import copy
        saved.update(copy.deepcopy(d))

    services = _noop_services(
        load_progress_json_fn=lambda: data,
        save_progress_json_fn=capture_save,
    )

    archive_result = {
        "archived_files": ["docs/a.md", "docs/b.md"],
        "success": True,
        "errors": [],
    }

    save_archive_record(feature_id=1, archive_result=archive_result, services=services)

    saved_feature = next(
        (f for f in saved.get("features", []) if f.get("id") == 1), None
    )
    assert saved_feature is not None
    archive_info = saved_feature.get("archive_info")
    assert isinstance(archive_info, dict), "archive_info must be a dict"
    assert archive_info.get("files_moved") == 2, "files_moved should match archived_files length"


# ─────────────────────────── Test 3 ───────────────────────────────────────────

def test_run_acceptance_tests_passes_for_vacuous_feature():
    """A feature with no test_steps should trivially pass with empty results."""
    feature = _base_feature(1, test_steps=[])
    services = _noop_services(find_project_root_fn=lambda: Path("."))

    all_passed, results = _run_acceptance_tests(feature=feature, services=services)

    assert all_passed is True, "No steps means vacuous pass"
    assert results == [], "No steps means no results"


# ─────────────────────────── Test 4 ───────────────────────────────────────────

def test_format_failure_reason_returns_non_empty_for_failures():
    """_format_failure_reason returns non-empty string for failed results."""
    failed = AcceptanceTestResult(
        step="run tests",
        command="pytest",
        success=False,
        output="error output",
        duration_ms=100,
        error="exit code 1",
    )

    reason = _format_failure_reason([failed])

    assert isinstance(reason, str)
    assert len(reason) > 0, "Must return a non-empty failure reason"


# ─────────────────────────── Test 5 ───────────────────────────────────────────

def test_validate_done_preconditions_blocks_missing_feature():
    """_validate_done_preconditions returns False when no current_feature_id."""
    data: Dict[str, Any] = {
        "current_feature_id": None,
        "features": [],
        "workflow_state": {"phase": "execution_complete"},
    }
    services = _noop_services(find_project_root_fn=lambda: Path("."))

    ok, reason, code, feature = _validate_done_preconditions(data=data, services=services)

    assert ok is False, "Must be blocked when current_feature_id is None"
    assert isinstance(reason, str) and len(reason) > 0


# ─────────────────────────── Test 6 ───────────────────────────────────────────

def test_cmd_done_check_only_returns_zero_when_all_pass():
    """cmd_done with check_only=True returns 0 when preflight succeeds."""
    data = _base_data(feature_id=1, phase="execution_complete")

    services = _noop_services(
        load_progress_json_fn=lambda: data,
    )

    preflight_results = [
        {"gate": "preconditions", "passed": True, "exit_code": 0, "message": "ok"},
    ]

    import completion_flow  # noqa: F401
    with patch.object(completion_flow, "_run_done_preflight",
                      return_value=(True, preflight_results)):
        exit_code = cmd_done(services=services, check_only=True)

    assert exit_code == 0, f"Expected 0 but got {exit_code}"


# ─────────────────────────── Test 7 ───────────────────────────────────────────

def test_complete_feature_finalizes_state():
    """complete_feature marks feature as completed with the right terminal states."""
    data = _base_data(
        feature_id=1,
        phase="execution_complete",
        feature_overrides={
            "quality_gates": {"evaluator": {"status": "pass"}},
        },
    )

    saved: Dict[str, Any] = {}

    def capture_save(d: dict) -> None:
        import copy
        saved.update(copy.deepcopy(d))

    services = _noop_services(
        load_progress_json_fn=lambda: data,
        save_progress_json_fn=capture_save,
        generate_progress_md_fn=lambda _d: "",
        save_progress_md_fn=lambda _s: None,
        record_feature_state_event_fn=lambda *a, **kw: None,
        archive_feature_docs_fn=lambda _id, _name=None: {
            "archived_files": [],
            "errors": [],
            "success": True,
        },
        validate_plan_document_fn=lambda _path: {"valid": True},
        collect_git_context_fn=lambda: {},
        get_head_commit_fn=lambda: None,
    )

    import completion_flow  # noqa: F401
    with patch.object(
        completion_flow,
        "_validate_completion_reconcile",
        return_value=(True, "", 0),
    ):
        result = complete_feature(
            feature_id=1,
            services=services,
            commit_hash="abc123",
            skip_archive=True,
        )

    assert result is True, "complete_feature must return True on success"

    saved_feature = next(
        (f for f in saved.get("features", []) if f.get("id") == 1), None
    )
    assert saved_feature is not None, "Feature must be present in saved data"
    assert saved_feature.get("completed") is True, "completed must be True"
    assert saved_feature.get("development_stage") == "completed"
    assert saved_feature.get("integration_status") == "merged_and_cleaned"


# ─────────────────────────── Test 8 ───────────────────────────────────────────

def test_cmd_done_triggers_callbacks():
    """cmd_done calls auto_state_commit_fn('F1','done') and notify_parent_sync_fn('clear')."""
    data = _base_data(feature_id=1, phase="execution_complete")

    auto_state_commit = MagicMock()
    notify_parent_sync = MagicMock()

    saved_data: Dict[str, Any] = {}

    def capture_save(d: dict) -> None:
        import copy
        saved_data.update(copy.deepcopy(d))

    services = _noop_services(
        load_progress_json_fn=lambda: data,
        save_progress_json_fn=capture_save,
        generate_progress_md_fn=lambda _d: "",
        save_progress_md_fn=lambda _s: None,
        record_feature_state_event_fn=lambda *a, **kw: None,
        auto_state_commit_fn=auto_state_commit,
        notify_parent_sync_fn=notify_parent_sync,
        archive_feature_docs_fn=lambda _id, _name=None: {
            "archived_files": [],
            "errors": [],
            "success": True,
        },
        validate_plan_document_fn=lambda _path: {"valid": True},
        collect_git_context_fn=lambda: {},
        get_head_commit_fn=lambda: None,
    )

    import completion_flow  # noqa: F401

    # Patch heavy internal gates so the flow reaches the callback stage.
    with (
        patch.object(completion_flow, "_validate_done_preconditions",
                     return_value=(True, "", 0, data["features"][0])),
        patch.object(completion_flow, "_validate_completion_reconcile",
                     return_value=(True, "", 0)),
        patch.object(completion_flow, "_validate_completion_plan_document",
                     return_value=(True, "", 0)),
        patch.object(completion_flow, "_run_acceptance_tests",
                     return_value=(True, [])),
        patch.object(completion_flow, "complete_feature",
                     return_value=True),
    ):
        exit_code = cmd_done(
            services=services,
            commit_hash="abc",
            skip_archive=True,
            no_cleanup=True,
        )

    assert exit_code == 0, f"Expected 0 but got {exit_code}"
    auto_state_commit.assert_called_once_with("F1", "done")
    notify_parent_sync.assert_called_with("clear")
