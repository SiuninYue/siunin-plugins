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

import re
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
# Public API
# ---------------------------------------------------------------------------

def _infer_categories_from_text(feature: Dict[str, Any]) -> List[str]:
    """Fallback: infer categories from feature text fields.

    Scans feature name, description, and change_spec.in_scope.
    Keyword matching uses word boundaries to avoid false positives such as
    matching "api" inside "capability".
    """
    text = " ".join([
        feature.get("name", ""),
        feature.get("description", ""),
        *feature.get("change_spec", {}).get("in_scope", []),
    ]).lower()
    found: Set[str] = set()
    for keyword, category in _KEYWORD_MAP.items():
        if re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", text):
            found.add(category)
    return sorted(found)


def required_reviews(feature: Dict[str, Any], persist: bool = False) -> List[str]:
    """Return sorted list of required review lane IDs for the given feature.

    Source priority:
      1. feature.change_spec.categories (explicit — no inference)
      2. keyword inference from feature.name + feature.description + change_spec.in_scope
      3. fail-closed: always include eng, qa, docs

    design and devex are optional: included only when matching category present.
    """
    change_spec = feature.setdefault("change_spec", {})
    categories: List[str] = change_spec.get("categories") or []
    inferred = False
    if not categories:
        categories = _infer_categories_from_text(feature)
        inferred = True

    if persist and inferred and categories and not change_spec.get("categories"):
        change_spec["categories"] = categories

    lanes: Set[str] = set()
    for cat in categories:
        extra = _LANE_RULES.get(cat)
        if extra:
            lanes.update(extra)
        else:
            # unknown category: fail-closed — add always-required lanes
            lanes.update(_ALWAYS_REQUIRED)

    if not lanes:
        # no categories (or all produced nothing) — default to always-required
        lanes.update(_ALWAYS_REQUIRED)

    return sorted(lanes)


def initialize_reviews(feature: Dict[str, Any]) -> None:
    """Populate quality_gates.reviews with required/pending/passed lanes.

    Idempotent: if quality_gates.reviews.required is already non-empty,
    this function does nothing (prevents overwriting in-progress review state).
    """
    feature.setdefault("quality_gates", {})
    reviews = feature["quality_gates"].setdefault(
        "reviews", {"required": [], "passed": [], "pending": []}
    )
    reviews.setdefault("required", [])
    reviews.setdefault("passed", [])
    reviews.setdefault("pending", [])

    if reviews["required"]:
        # Already initialized — do not overwrite existing state.
        return

    lanes = required_reviews(feature)
    reviews["required"] = lanes
    reviews["pending"] = [lane for lane in lanes if lane not in reviews["passed"]]


def mark_review_passed(feature: Dict[str, Any], lane: str) -> None:
    """Record that a review lane has been completed.

    Updates both passed (append) and pending (remove) in-place.
    Idempotent: calling twice with the same lane has no additional effect.
    Unknown lanes (not in required) are silently ignored.
    """
    reviews = feature.get("quality_gates", {}).get("reviews", {})
    required: List[str] = reviews.get("required", [])
    if lane not in required:
        return

    passed: List[str] = reviews.setdefault("passed", [])
    if lane not in passed:
        passed.append(lane)

    pending: List[str] = reviews.setdefault("pending", [])
    if lane in pending:
        pending.remove(lane)


def get_pending_lanes(feature: Dict[str, Any]) -> List[str]:
    """Return canonical pending lanes: required minus passed.

    Always recomputes from source-of-truth fields; treats stored pending as cache.
    Returns [] if reviews not initialized (safe default for gate checks).
    """
    reviews = feature.get("quality_gates", {}).get("reviews", {})
    required: List[str] = reviews.get("required", [])
    passed: List[str] = reviews.get("passed", [])
    return [lane for lane in required if lane not in passed]
