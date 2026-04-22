#!/usr/bin/env python3
"""review_router contract tests (F-11)."""

import pytest
# _LANE_RULES tested here; other symbols used in Tasks 2-5 tests below
from review_router import (  # noqa: F401
    _LANE_RULES,
    required_reviews,
    initialize_reviews,
    mark_review_passed,
    get_pending_lanes,
)

def test_lane_rules_defines_backend():
    assert "backend" in _LANE_RULES
    assert {"eng", "qa", "docs"}.issubset(_LANE_RULES["backend"])

def test_lane_rules_frontend_includes_design():
    assert "design" in _LANE_RULES.get("frontend", set())

def test_lane_rules_sdk_includes_devex():
    assert "devex" in _LANE_RULES.get("sdk", set())

def test_lane_rules_docs_only_has_docs():
    assert _LANE_RULES.get("docs") == {"docs"}


# --- required_reviews() ---

def _make_feature(
    name: str = "test feature",
    categories=None,
    in_scope=None,
    description: str = "",
) -> dict:
    return {
        "id": 99,
        "name": name,
        "description": description,
        "change_spec": {
            "why": "test",
            "in_scope": in_scope or [],
            "out_of_scope": [],
            "risks": [],
            **({"categories": categories} if categories is not None else {}),
        },
    }


def test_required_reviews_explicit_categories_backend():
    feat = _make_feature(categories=["backend"])
    lanes = required_reviews(feat)
    assert set(lanes) == {"eng", "qa", "docs"}


def test_required_reviews_explicit_categories_frontend_adds_design():
    feat = _make_feature(categories=["frontend"])
    lanes = required_reviews(feat)
    assert "design" in lanes
    assert {"eng", "qa", "docs"}.issubset(set(lanes))


def test_required_reviews_explicit_categories_sdk_adds_devex():
    feat = _make_feature(categories=["sdk"])
    lanes = required_reviews(feat)
    assert "devex" in lanes
    assert {"eng", "qa", "docs"}.issubset(set(lanes))


def test_required_reviews_explicit_categories_docs_only():
    feat = _make_feature(categories=["docs"])
    lanes = required_reviews(feat)
    assert set(lanes) == {"docs"}


def test_required_reviews_multiple_categories_union():
    feat = _make_feature(categories=["frontend", "sdk"])
    lanes = required_reviews(feat)
    assert {"eng", "qa", "docs", "design", "devex"}.issubset(set(lanes))


def test_required_reviews_keyword_inference_fallback_frontend():
    feat = _make_feature(name="落地 frontend ui 组件")
    lanes = required_reviews(feat)
    assert "design" in lanes


def test_required_reviews_keyword_inference_fallback_sdk():
    feat = _make_feature(name="update sdk api handlers")
    lanes = required_reviews(feat)
    assert "devex" in lanes


def test_required_reviews_fail_closed_unknown_category():
    feat = _make_feature(categories=["totally_unknown_xyz"])
    lanes = required_reviews(feat)
    assert set(lanes) >= {"eng", "qa", "docs"}


def test_required_reviews_no_categories_defaults_to_always_required():
    feat = _make_feature()
    lanes = required_reviews(feat)
    assert set(lanes) >= {"eng", "qa", "docs"}


def test_required_reviews_design_not_in_backend():
    feat = _make_feature(categories=["backend"])
    lanes = required_reviews(feat)
    assert "design" not in lanes


def test_required_reviews_devex_not_in_backend():
    feat = _make_feature(categories=["backend"])
    lanes = required_reviews(feat)
    assert "devex" not in lanes


def test_required_reviews_mixed_known_and_unknown_categories_fail_closed():
    """Unknown category alongside docs-only category must still add eng/qa."""
    feat = _make_feature(categories=["docs", "totally_unknown"])
    lanes = required_reviews(feat)
    assert {"eng", "qa"}.issubset(set(lanes)), \
        "fail-closed: unknown category should trigger eng/qa even alongside docs"


def test_required_reviews_in_scope_keyword_inference():
    """in_scope keywords should also drive inference when name has no match."""
    feat = _make_feature(name="general refactor", in_scope=["sdk integration"])
    lanes = required_reviews(feat)
    assert "devex" in lanes


def test_required_reviews_description_keyword_inference():
    feat = _make_feature(name="general refactor", description="update api boundary")
    lanes = required_reviews(feat)
    assert "devex" in lanes


def test_required_reviews_keyword_match_uses_boundaries():
    """Avoid false-positive 'api' match inside 'capability'."""
    feat = _make_feature(name="capability uplift only")
    lanes = required_reviews(feat)
    assert "devex" not in lanes


def test_required_reviews_inference_persists_to_change_spec():
    feat = _make_feature(name="update api handler")
    required_reviews(feat, persist=True)
    assert feat["change_spec"].get("categories") is not None
    assert "api" in feat["change_spec"]["categories"]


def test_required_reviews_explicit_categories_not_overwritten():
    feat = _make_feature(categories=["backend"])
    required_reviews(feat, persist=True)
    assert feat["change_spec"]["categories"] == ["backend"]


def test_required_reviews_persist_idempotent_no_json_drift():
    feat = _make_feature(name="update api handler")
    lanes_first = required_reviews(feat, persist=True)
    cats_first = list(feat["change_spec"].get("categories", []))

    lanes_second = required_reviews(feat, persist=True)
    cats_second = list(feat["change_spec"].get("categories", []))

    assert lanes_first == lanes_second
    assert cats_first == cats_second


def test_required_reviews_mixed_docs_and_backend_does_not_short_circuit():
    feat = _make_feature(categories=["docs", "backend"])
    lanes = required_reviews(feat)
    assert {"eng", "qa", "docs"}.issubset(set(lanes))
    assert "eng" in lanes
    assert "docs" in lanes


# --- initialize_reviews() ---

def test_initialize_reviews_writes_required_and_empty_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    reviews = feat["quality_gates"]["reviews"]
    assert set(reviews["required"]) == {"eng", "qa", "docs"}
    assert reviews["passed"] == []
    assert reviews["pending"] == []


def test_initialize_reviews_idempotent_does_not_overwrite_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    feat["quality_gates"]["reviews"]["passed"].append("eng")
    initialize_reviews(feat)  # second call must NOT reset
    reviews = feat["quality_gates"]["reviews"]
    assert "eng" in reviews["passed"]


def test_initialize_reviews_creates_quality_gates_if_absent():
    feat = _make_feature(categories=["backend"])
    # No quality_gates at all
    initialize_reviews(feat)
    assert "quality_gates" in feat
    assert "reviews" in feat["quality_gates"]


def test_initialize_reviews_frontend_includes_design():
    feat = _make_feature(categories=["frontend"])
    initialize_reviews(feat)
    reviews = feat["quality_gates"]["reviews"]
    assert "design" in reviews["required"]


def test_initialize_reviews_scope_creep_does_not_auto_update():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    assert "design" not in feat["quality_gates"]["reviews"]["required"]

    feat["change_spec"]["categories"] = ["backend", "frontend"]
    initialize_reviews(feat)

    assert "design" not in feat["quality_gates"]["reviews"]["required"]


# --- mark_review_passed() ---

def test_mark_review_passed_appends_to_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    reviews = feat["quality_gates"]["reviews"]
    assert "eng" in reviews["passed"]


def test_mark_review_passed_idempotent_on_double_pass():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    mark_review_passed(feat, "eng")  # second call: no duplicate
    reviews = feat["quality_gates"]["reviews"]
    assert reviews["passed"].count("eng") == 1


def test_mark_review_passed_ignores_unknown_lane():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    # Should not raise; unknown lane is silently ignored
    mark_review_passed(feat, "nonexistent_lane")
    reviews = feat["quality_gates"]["reviews"]
    assert "nonexistent_lane" not in reviews["passed"]


# --- get_pending_lanes() ---

def test_get_pending_lanes_returns_required_minus_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    pending = get_pending_lanes(feat)
    assert "eng" not in pending
    assert "qa" in pending
    assert "docs" in pending


def test_get_pending_lanes_empty_when_all_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    for lane in ["eng", "qa", "docs"]:
        mark_review_passed(feat, lane)
    assert get_pending_lanes(feat) == []


def test_get_pending_lanes_returns_empty_when_reviews_not_initialized():
    feat = _make_feature()
    # No initialize_reviews call — should return empty, not raise
    result = get_pending_lanes(feat)
    assert result == []


def test_get_pending_lanes_ignores_stored_pending_field():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    feat["quality_gates"]["reviews"]["pending"] = []
    pending = get_pending_lanes(feat)
    assert "qa" in pending
    assert "docs" in pending


def test_get_pending_lanes_detects_partial_passed_with_empty_pending_field():
    feat = _make_feature(categories=["backend"])
    feat.setdefault("quality_gates", {})["reviews"] = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": [],
    }
    pending = get_pending_lanes(feat)
    assert set(pending) == {"qa", "docs"}


# --- progress_manager integration: set_current initializes reviews ---

import sys
import json
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager


def _make_progress_json_with_feature(tmp_path: Path, categories=None) -> Path:
    """Write a minimal progress.json with one pending feature."""
    feature = {
        "id": 42,
        "name": "test feature for review router integration",
        "completed": False,
        "deferred": False,
        "lifecycle_state": "approved",
        "development_stage": "planning",
        "change_spec": {
            "why": "test",
            "in_scope": ["test"],
            "out_of_scope": [],
            "risks": [],
            **({"categories": categories} if categories is not None else {}),
        },
        "requirement_ids": ["REQ-042"],
        "acceptance_scenarios": ["Scenario: passes"],
        "quality_gates": {
            "evaluator": {"status": "pending", "score": None, "defects": [], "last_run_at": None, "evaluator_model": None},
            "reviews": {"required": [], "passed": [], "pending": []},
            "ship_check": {"status": "pending", "failures": [], "last_run_at": None},
        },
        "sprint_contract": {
            "scope": "review-gate regression",
            "done_criteria": ["all required lanes passed"],
            "test_plan": ["pytest -q tests/test_review_router.py"],
            "accepted_by": "test-suite",
            "accepted_at": "2026-01-01T00:00:00Z",
        },
        "handoff": {"from_phase": None, "to_phase": None, "artifact_path": None, "created_at": None},
    }
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [feature],
        "current_feature_id": None,
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
    }
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True)
    progress_file = state_dir / "progress.json"
    progress_file.write_text(json.dumps(data))
    return tmp_path


def test_set_current_initializes_reviews_when_empty(tmp_path):
    proj_root = _make_progress_json_with_feature(tmp_path, categories=["backend"])
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        progress_manager.set_current(42)

    progress_file = proj_root / "docs" / "progress-tracker" / "state" / "progress.json"
    data = json.loads(progress_file.read_text())
    feat = next(f for f in data["features"] if f["id"] == 42)
    reviews = feat["quality_gates"]["reviews"]
    assert set(reviews["required"]) == {"eng", "qa", "docs"}
    assert reviews["passed"] == []
    assert set(reviews["pending"]) == {"eng", "qa", "docs"}


def test_set_current_does_not_reset_existing_reviews(tmp_path):
    proj_root = _make_progress_json_with_feature(tmp_path, categories=["backend"])
    # Pre-populate reviews as if eng was already passed
    progress_file = proj_root / "docs" / "progress-tracker" / "state" / "progress.json"
    data = json.loads(progress_file.read_text())
    feat = next(f for f in data["features"] if f["id"] == 42)
    feat["quality_gates"]["reviews"] = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": ["qa", "docs"],
    }
    progress_file.write_text(json.dumps(data))

    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        progress_manager.set_current(42)

    data2 = json.loads(progress_file.read_text())
    feat2 = next(f for f in data2["features"] if f["id"] == 42)
    reviews2 = feat2["quality_gates"]["reviews"]
    assert "eng" in reviews2["passed"]   # preserved


# --- progress_manager integration: review-pass command ---

def test_review_pass_is_in_mutating_commands():
    assert "review-pass" in progress_manager.MUTATING_COMMANDS


def test_cmd_review_pass_returns_3_when_feature_not_found(tmp_path):
    proj_root = _make_progress_json_with_feature(tmp_path, categories=["backend"])
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_review_pass(999, "eng")
    assert rc == 3


def test_cmd_review_pass_returns_4_when_required_lanes_empty(tmp_path):
    proj_root = _make_progress_json_with_feature(tmp_path, categories=["backend"])
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_review_pass(42, "eng")
    assert rc == 4


def test_cmd_review_pass_returns_5_when_lane_not_required(tmp_path):
    proj_root = _make_progress_json_with_feature(tmp_path, categories=["backend"])
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        progress_manager.set_current(42)
        rc = progress_manager.cmd_review_pass(42, "design")
    assert rc == 5


def test_cmd_review_pass_marks_lane_and_returns_0(tmp_path):
    proj_root = _make_progress_json_with_feature(tmp_path, categories=["backend"])
    progress_file = proj_root / "docs" / "progress-tracker" / "state" / "progress.json"
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        progress_manager.set_current(42)
        rc = progress_manager.cmd_review_pass(42, "eng")
    assert rc == 0
    data = json.loads(progress_file.read_text())
    feat = next(f for f in data["features"] if f["id"] == 42)
    reviews = feat["quality_gates"]["reviews"]
    assert "eng" in reviews["passed"]


# --- progress_manager integration: cmd_done blocked by pending reviews ---

def _make_progress_with_execution_complete(tmp_path: Path, reviews: dict) -> Path:
    """Write progress.json with feature in execution_complete phase, configurable reviews."""
    feature = {
        "id": 55,
        "name": "feature for done gate test",
        "completed": False,
        "deferred": False,
        "lifecycle_state": "implementing",
        "development_stage": "developing",
        "change_spec": {
            "why": "test", "in_scope": [], "out_of_scope": [], "risks": [],
        },
        "requirement_ids": ["REQ-055"],
        "acceptance_scenarios": [],
        "integration_status": None,
        "quality_gates": {
            "evaluator": {"status": "pass", "score": 100, "defects": [], "last_run_at": "2026-01-01T00:00:00Z", "evaluator_model": None},
            "reviews": reviews,
            "ship_check": {"status": "pending", "failures": [], "last_run_at": None},
        },
        "sprint_contract": {
            "scope": "done gate review routing",
            "done_criteria": ["required review lanes passed"],
            "test_plan": ["pytest -q tests/test_review_router.py"],
            "accepted_by": "test-suite",
            "accepted_at": "2026-01-01T00:00:00Z",
        },
        "handoff": {"from_phase": None, "to_phase": None, "artifact_path": None, "created_at": None},
    }
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [feature],
        "current_feature_id": 55,
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
        "workflow_state": {"phase": "execution_complete"},
    }
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "progress.json").write_text(json.dumps(data))
    return tmp_path


def test_load_progress_json_recomputes_reviews_pending_cache(tmp_path):
    reviews = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": [],
    }
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        data = progress_manager.load_progress_json()
    assert data is not None
    feat = next(f for f in data["features"] if f["id"] == 55)
    assert set(feat["quality_gates"]["reviews"]["pending"]) == {"qa", "docs"}


def test_cmd_done_returns_7_when_required_lanes_pending(tmp_path):
    reviews = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": ["qa", "docs"],
    }
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done()
    assert rc == 7, f"Expected 7 (review gate), got {rc}"


def test_cmd_done_not_blocked_when_all_lanes_passed(tmp_path):
    reviews = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng", "qa", "docs"],
        "pending": [],
    }
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done()
    assert rc != 7, f"Review gate must not block when all lanes passed (got rc={rc})"


def test_cmd_done_returns_7_when_pending_field_corrupt_but_passed_incomplete(tmp_path):
    reviews = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": [],
    }
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done()
    assert rc == 7, (
        "Gate must detect pending lanes via required-passed, "
        f"not stored pending field (got {rc})"
    )


def test_cmd_done_returns_7_when_no_reviews_configured(tmp_path):
    reviews = {"required": [], "passed": [], "pending": []}
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done()
    assert rc == 7
    data = json.loads(
        (proj_root / "docs" / "progress-tracker" / "state" / "progress.json").read_text()
    )
    feat = next(f for f in data["features"] if f["id"] == 55)
    required = feat["quality_gates"]["reviews"]["required"]
    assert {"eng", "qa", "docs"}.issubset(set(required))
