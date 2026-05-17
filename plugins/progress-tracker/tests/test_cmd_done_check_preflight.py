"""
Integration tests for cmd_done(check_only=True) — the `prog done --check` preflight.

Verifies:
- Gate 1 failure w/o feature → only Gate 1 in results, exit code from Gate 1
- Gate 1 failure w/ feature (wrong phase) → ALL 9 gates emitted, exit code from Gate 1
- All gates pass → exit 0
- Gate-level failures report correct exit codes (6=evaluator, 11=plan, etc.)
- State is NOT mutated after check_only (no finish_pending, no completed=true)
- 9 results always returned when feature exists
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import progress_manager
from progress_manager import _run_done_preflight


_FEATURE_ID = 99


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_progress_json(
    tmp_path: Path,
    *,
    phase: str = "execution_complete",
    current_feature_id: int | None = _FEATURE_ID,
    feature_overrides: dict | None = None,
    workflow_overrides: dict | None = None,
    plan_text: str | None = None,
) -> Path:
    """Write progress.json into tmp_path.  Returns the project root."""
    plan_path = f"docs/plans/2026-01-01-feature-{_FEATURE_ID}.md"
    plan_abs = tmp_path / plan_path
    plan_abs.parent.mkdir(parents=True, exist_ok=True)
    plan_abs.write_text(
        plan_text
        or "# Feature Plan\n\n## Tasks\n\n- [ ] Task 1\n\n## Acceptance Mapping\n\n- AC1\n\n## Risks\n\n- None\n",
        encoding="utf-8",
    )

    feature = {
        "id": _FEATURE_ID,
        "name": "test-feature",
        "completed": False,
        "deferred": False,
        "lifecycle_state": "implementing",
        "development_stage": "developing",
        "change_spec": {
            "why": "test",
            "in_scope": [],
            "out_of_scope": [],
            "risks": [],
        },
        "requirement_ids": [f"REQ-{_FEATURE_ID:03d}"],
        "acceptance_scenarios": [],
        "test_steps": [],
        "integration_status": None,
        "quality_gates": {
            "evaluator": {
                "status": "pass",
                "score": 100,
                "defects": [],
                "last_run_at": "2026-01-01T00:00:00Z",
            },
            "ship_check": {
                "status": "pass",
                "failures": [],
                "last_run_at": "2026-01-01T00:00:00Z",
            },
            "reviews": {
                "required": ["eng"],
                "passed": ["eng"],
                "pending": [],
            },
        },
        "sprint_contract": {
            "scope": "test",
            "done_criteria": [],
            "test_plan": [],
        },
        "handoff": {},
        "plan_path": plan_path,
    }
    if feature_overrides:
        feature.update(feature_overrides)

    workflow_state = {"phase": phase, "plan_path": plan_path}
    if workflow_overrides:
        workflow_state.update(workflow_overrides)

    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [feature],
        "current_feature_id": current_feature_id,
        "updates": [],
        "retrospectives": [],
        "runtime_context": {},
        "linked_projects": [],
        "linked_snapshot": {},
        "tracker_role": "standalone",
        "project_code": None,
        "routing_queue": [],
        "active_routes": [],
        "bugs": [],
        "current_bug_id": None,
        "workflow_state": workflow_state,
    }
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True)
    progress_file = state_dir / "progress.json"
    progress_file.write_text(json.dumps(data, indent=2))
    return tmp_path


def _snapshot_progress_json(root: Path) -> dict:
    return json.loads((root / "docs" / "progress-tracker" / "state" / "progress.json").read_text())


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_env(tmp_path):
    """Fully-passing gate environment for cmd_done(check_only=True)."""
    proj_root = _make_progress_json(tmp_path)

    with (
        patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root),
        patch("progress_manager.require_sprint_contract", return_value=None),
        patch("progress_manager.record_sprint_artifact", return_value=None),
        patch("progress_manager._save_done_test_report", return_value=None),
    ):
        yield proj_root


# ---------------------------------------------------------------------------
# Tests: gate coverage
# ---------------------------------------------------------------------------

def test_check_no_active_feature_returns_only_gate1(tmp_path):
    """No current_feature_id → Gate 1 FAIL, no further gates, exit 1."""
    proj_root = _make_progress_json(tmp_path, current_feature_id=None)

    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done(check_only=True)

    assert rc == 1, f"expected exit 1 (Gate 1 code for no active feature), got {rc}"


def test_check_wrong_phase_emits_all_9_gates(seeded_env):
    """Phase='execution' → Gate 1 FAIL but feature exists, so gates 2-9 still run."""
    # Patch the loaded data to have wrong phase
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )
    data["workflow_state"]["phase"] = "execution"
    (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").write_text(
        json.dumps(data, indent=2)
    )

    all_passed, results = _run_done_preflight(data)

    assert len(results) == 9, f"expected 9 gates, got {len(results)}"
    assert results[0]["passed"] is False  # Gate 1 FAIL
    assert results[0]["exit_code"] == 2  # wrong phase
    # Gates 2-8 should have been evaluated
    for i in range(1, 8):
        assert results[i]["passed"] is not None, f"Gate {i+1} should have been evaluated"


def test_check_no_active_feature_results_length(seeded_env):
    """No active feature → only 1 gate result, exit code from gate 1."""
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )
    data["current_feature_id"] = None

    all_passed, results = _run_done_preflight(data)
    assert len(results) == 1
    assert results[0]["gate"] == 1
    assert results[0]["passed"] is False
    assert results[0]["exit_code"] == 1
    assert not all_passed


# ---------------------------------------------------------------------------
# Tests: exit code semantics
# ---------------------------------------------------------------------------

def test_check_returns_first_failing_gate_code(seeded_env):
    """When multiple gates fail, exit code is the first failing gate's code."""
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )
    # Gate 1 FAIL (phase wrong) → exit code 2
    data["workflow_state"]["phase"] = "execution"
    (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").write_text(
        json.dumps(data, indent=2)
    )

    rc = progress_manager.cmd_done(check_only=True)
    assert rc == 2, f"expected exit 2 (first failing gate), got {rc}"


def test_check_returns_evaluator_code_when_evaluator_fails(seeded_env):
    """Gate 6 (evaluator) is the first failure → exit code 6."""
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )
    data["features"][0]["quality_gates"]["evaluator"]["status"] = "pending"
    # Must persist — _run_done_preflight reloads progress.json after acceptance tests.
    (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").write_text(
        json.dumps(data, indent=2)
    )

    all_passed, results = _run_done_preflight(data)
    assert not all_passed
    # Find first failing gate
    first_fail = next(r for r in results if r["passed"] is False)
    assert first_fail["gate"] == 6
    assert first_fail["exit_code"] == 6


def test_check_returns_plan_code_when_plan_invalid(seeded_env):
    """Gate 3 (plan) failure → exit code 11."""
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )
    # Remove the plan file to trigger plan validation failure
    plan_path = data["workflow_state"]["plan_path"]
    (seeded_env / plan_path).unlink()

    all_passed, results = _run_done_preflight(data)
    assert not all_passed
    assert results[2]["gate"] == 3
    assert results[2]["passed"] is False
    assert results[2]["exit_code"] == 11


def test_check_all_pass_returns_zero(seeded_env):
    """All gates pass → exit 0."""
    rc = progress_manager.cmd_done(check_only=True)
    assert rc == 0, f"expected exit 0 (all pass), got {rc}"


# ---------------------------------------------------------------------------
# Tests: state immutability
# ---------------------------------------------------------------------------

def test_check_does_not_mutate_progress_json(seeded_env):
    """check_only=True must not persist any state changes."""
    before = _snapshot_progress_json(seeded_env)

    progress_manager.cmd_done(check_only=True)

    after = _snapshot_progress_json(seeded_env)

    # Feature must remain incomplete
    feat = after["features"][0]
    assert feat["completed"] is False, "check_only must not mark feature completed"
    assert feat.get("integration_status") != "finish_pending", (
        "check_only must not set finish_pending"
    )
    assert after.get("current_feature_id") == _FEATURE_ID, (
        "check_only must not clear current_feature_id"
    )
    assert after.get("workflow_state") is not None, (
        "check_only must not remove workflow_state"
    )


def test_check_acceptance_failure_does_not_write_finish_pending(seeded_env):
    """Even when acceptance fails, check_only must not persist finish_pending."""
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )
    # Add a failing acceptance step
    data["features"][0]["test_steps"] = ["echo fail && exit 1"]
    (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").write_text(
        json.dumps(data, indent=2)
    )

    all_passed, results = _run_done_preflight(data)
    # Gate 5 should be FAIL
    gate5 = results[4]
    assert gate5["gate"] == 5
    assert gate5["passed"] is False

    # State must NOT be mutated
    after = _snapshot_progress_json(seeded_env)
    feat = after["features"][0]
    assert feat.get("integration_status") != "finish_pending"
    assert "finish_pending_reason" not in feat


# ---------------------------------------------------------------------------
# Tests: result structure
# ---------------------------------------------------------------------------

def test_check_result_structure(seeded_env):
    """Each result dict has the expected keys."""
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )

    all_passed, results = _run_done_preflight(data)

    assert len(results) == 9
    for r in results:
        assert "gate" in r
        assert "name" in r
        assert "passed" in r
        assert "reason" in r
        assert "exit_code" in r
        assert isinstance(r["gate"], int)
        assert isinstance(r["name"], str)
        assert r["passed"] in (True, False, None)
        assert isinstance(r["exit_code"], int)


def test_check_gate9_is_always_skipped(seeded_env):
    """Gate 9 (Finalization) is always passed=None (skipped)."""
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )

    all_passed, results = _run_done_preflight(data)
    assert results[8]["gate"] == 9
    assert results[8]["passed"] is None
    assert results[8]["exit_code"] == 0


def test_check_reviews_unsatisfied_reports_pending_lanes(seeded_env):
    """When required reviews are not all passed, Gate 7 is FAIL."""
    data = json.loads(
        (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )
    data["features"][0]["quality_gates"]["reviews"] = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": [],
    }
    # Must persist — _run_done_preflight reloads progress.json after acceptance tests.
    (seeded_env / "docs" / "progress-tracker" / "state" / "progress.json").write_text(
        json.dumps(data, indent=2)
    )

    all_passed, results = _run_done_preflight(data)
    gate7 = results[6]
    assert gate7["gate"] == 7
    assert gate7["passed"] is False
    assert gate7["exit_code"] == 7
    assert "qa" in gate7["reason"]
