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

def _make_feature(name: str = "test feature", categories=None, in_scope=None) -> dict:
    return {
        "id": 99,
        "name": name,
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


# --- initialize_reviews() ---

def test_initialize_reviews_writes_required_and_pending():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    reviews = feat["quality_gates"]["reviews"]
    assert set(reviews["required"]) == {"eng", "qa", "docs"}
    assert set(reviews["pending"]) == {"eng", "qa", "docs"}
    assert reviews["passed"] == []


def test_initialize_reviews_idempotent_does_not_overwrite():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    feat["quality_gates"]["reviews"]["passed"].append("eng")
    feat["quality_gates"]["reviews"]["pending"].remove("eng")
    initialize_reviews(feat)  # second call must NOT reset
    reviews = feat["quality_gates"]["reviews"]
    assert "eng" in reviews["passed"]
    assert "eng" not in reviews["pending"]


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
    assert "design" in reviews["pending"]


# --- mark_review_passed() ---

def test_mark_review_passed_moves_lane_from_pending_to_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    reviews = feat["quality_gates"]["reviews"]
    assert "eng" in reviews["passed"]
    assert "eng" not in reviews["pending"]


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
