#!/usr/bin/env python3
"""evaluator_gate contract tests (PR-3)."""

import pytest

from evaluator_gate import assess, EvaluatorResult, EvaluatorDefect


def test_assess_returns_pass_when_no_defects():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={"test_coverage": 0.9, "defects": []},
    )
    assert result.status == "pass"
    assert result.score >= 80
    assert result.defects == []


def test_assess_returns_retry_on_blocking_defect():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={
            "test_coverage": 0.9,
            "defects": [
                {"id": "D1", "severity": "blocking", "description": "memory leak"},
            ],
        },
    )
    assert result.status == "retry"
    assert any(d.severity == "blocking" for d in result.defects)


def test_assess_fails_when_coverage_below_threshold():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={"test_coverage": 0.5, "defects": []},
    )
    assert result.status == "retry"
    assert any("coverage" in d.description.lower() for d in result.defects)


def test_assess_escalates_to_required_reviews_on_security_defect():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={
            "test_coverage": 0.9,
            "defects": [
                {"id": "D1", "severity": "major", "description": "auth bypass possible"},
            ],
        },
    )
    assert result.status == "required_reviews"


def test_assess_result_serializes_to_quality_gates_evaluator_schema():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={"test_coverage": 0.9, "defects": []},
    )
    payload = result.to_quality_gate_payload()
    assert set(payload.keys()) == {"status", "score", "defects", "last_run_at", "evaluator_model"}
    assert payload["status"] == "pass"


def test_quality_gate_payload_uses_defects_not_issues():
    """Naming alignment: payload key must be 'defects', not 'issues' (matches EvaluatorDefect class)."""
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={
            "test_coverage": 0.85,
            "defects": [{"id": "D1", "severity": "minor", "description": "nit"}],
        },
    )
    payload = result.to_quality_gate_payload()
    assert "defects" in payload
    assert "issues" not in payload
    assert isinstance(payload["defects"], list)


def test_evaluator_model_field_is_present_in_payload():
    """User refinement: evaluator_model must be in payload for audit traceability."""
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={"test_coverage": 0.9, "defects": []},
    )
    payload = result.to_quality_gate_payload()
    assert "evaluator_model" in payload


# Integration: _store_evaluator_result writes to quality_gates.evaluator
def test_prog_done_writes_evaluator_result_to_quality_gates(tmp_path, monkeypatch):
    import progress_manager
    monkeypatch.chdir(tmp_path)
    progress_manager.init_tracking("Eval Project", force=True)
    progress_manager.add_feature("Feature A", ["pytest dummy"])
    progress_manager.set_current(1)
    progress_manager._store_evaluator_result(
        feature_id=1,
        result=assess(
            feature={"id": 1, "name": "Feature A"},
            rubric={"test_coverage_min": 0.8, "require_changelog": False},
            signals={"test_coverage": 0.95, "defects": []},
        ),
    )
    data = progress_manager.load_progress_json()
    feat = data["features"][0]
    assert feat["quality_gates"]["evaluator"]["status"] == "pass"
    assert feat["quality_gates"]["evaluator"]["score"] >= 80
    assert "evaluator_model" in feat["quality_gates"]["evaluator"]
