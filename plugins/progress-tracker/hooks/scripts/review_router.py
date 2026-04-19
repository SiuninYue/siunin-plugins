#!/usr/bin/env python3
"""Review lane router (F-11).

Determines which review lanes are required for a feature based on its
change_categories, then persists the result into quality_gates.reviews.

Lane types:
  Required (always): eng, qa, docs
  Optional (by category): design (frontend/ui), devex (sdk/api/cli)

Public API:
  required_reviews(feature) -> list[str]
  initialize_reviews(feature) -> None          # idempotent; writes quality_gates.reviews
  mark_review_passed(feature, lane: str) -> None
  get_pending_lanes(feature) -> list[str]      # canonical read model
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

# ---------------------------------------------------------------------------
# Lane rules: category -> set of required lanes
# ---------------------------------------------------------------------------
_LANE_RULES: Dict[str, Set[str]] = {
    "backend":  {"eng", "qa", "docs"},
    "frontend": {"eng", "qa", "docs", "design"},
    "ui":       {"eng", "qa", "docs", "design"},
    "sdk":      {"eng", "qa", "docs", "devex"},
    "api":      {"eng", "qa", "docs", "devex"},
    "cli":      {"eng", "qa", "docs", "devex"},
    "docs":     {"docs"},
    "schema":   {"eng", "qa", "docs"},
    "security": {"eng", "qa", "docs"},
    "infra":    {"eng", "qa", "docs"},
}

_ALWAYS_REQUIRED: Set[str] = {"eng", "qa", "docs"}

# Keywords used for fallback inference when change_spec.categories is absent
_KEYWORD_MAP: Dict[str, str] = {
    "frontend":  "frontend",
    "ui":        "ui",
    "sdk":       "sdk",
    "api":       "api",
    "cli":       "cli",
    "docs":      "docs",
    "readme":    "docs",
    "schema":    "schema",
    "security":  "security",
    "infra":     "infra",
    "backend":   "backend",
}

# ---------------------------------------------------------------------------
# Stubs — to be implemented in subsequent tasks
# ---------------------------------------------------------------------------
def required_reviews(feature: Dict[str, Any]) -> List[str]:
    raise NotImplementedError

def initialize_reviews(feature: Dict[str, Any]) -> None:
    raise NotImplementedError

def mark_review_passed(feature: Dict[str, Any], lane: str) -> None:
    raise NotImplementedError

def get_pending_lanes(feature: Dict[str, Any]) -> List[str]:
    raise NotImplementedError
