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
