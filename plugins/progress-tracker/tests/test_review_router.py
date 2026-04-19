#!/usr/bin/env python3
"""review_router contract tests (F-11)."""

import pytest
from review_router import _LANE_RULES, required_reviews, initialize_reviews, mark_review_passed, get_pending_lanes

def test_lane_rules_defines_backend():
    assert "backend" in _LANE_RULES
    assert {"eng", "qa", "docs"}.issubset(_LANE_RULES["backend"])

def test_lane_rules_frontend_includes_design():
    assert "design" in _LANE_RULES.get("frontend", set())

def test_lane_rules_sdk_includes_devex():
    assert "devex" in _LANE_RULES.get("sdk", set())

def test_lane_rules_docs_only_has_docs():
    assert _LANE_RULES.get("docs") == {"docs"}
