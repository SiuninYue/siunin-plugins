"""Feature command operations: set-current and set-development-stage.

Extracted from ``progress_manager.py`` (F22 facade refactor). This module
contains no reverse dependency on ``progress_manager``; all side effects are
injected via :class:`FeatureCommandsServices`. Leaf modules
(``readiness_validator``, ``progress_prompt_builders``, ``review_router``) are
imported directly.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from readiness_validator import (
    print_readiness_error,
    print_readiness_warnings,
    validate_feature_readiness,
)
from progress_prompt_builders import _is_deferred

try:
    from review_router import initialize_reviews as _initialize_reviews
    REVIEW_ROUTER_AVAILABLE = True
except ImportError:  # pragma: no cover - review_router is an optional plugin
    REVIEW_ROUTER_AVAILABLE = False

    def _initialize_reviews(feature):  # type: ignore[misc]
        pass


# Inlined to avoid importing progress_manager (no reverse dependency).
DEVELOPMENT_STAGES = ("planning", "developing", "completed")


def _iso_now() -> str:
    return datetime.datetime.utcnow().isoformat()


@dataclass
class FeatureCommandsServices:
    """Injected side-effect callbacks for feature commands."""

    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    save_progress_json_fn: Callable[[Dict[str, Any]], None]
    generate_progress_md_fn: Callable[[Dict[str, Any]], str]
    save_progress_md_fn: Callable[[str], None]
    update_runtime_context_fn: Callable[[Dict[str, Any], str], bool]
    auto_state_commit_fn: Callable[[str, str], Optional[str]]
    notify_parent_sync_fn: Callable[[str], None]


def set_current_command(feature_id: int, svc: FeatureCommandsServices) -> bool:
    """Set the current feature being worked on."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)

    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    if _is_deferred(feature):
        defer_reason = feature.get("defer_reason") or "Deferred feature"
        print(
            f"Feature ID {feature_id} is deferred and cannot be set as current: "
            f"{defer_reason}. Run `prog resume` first."
        )
        return False

    if not feature.get("completed", False):
        readiness_report = validate_feature_readiness(feature)
        if not readiness_report["valid"]:
            print_readiness_error(feature, readiness_report)
            return False
        if readiness_report["warnings"]:
            print_readiness_warnings(readiness_report)
            print("")

    previous_current_id = data.get("current_feature_id")
    data["current_feature_id"] = feature_id

    # Selecting a feature for work should immediately enter active development.
    if not feature.get("completed", False):
        feature["development_stage"] = "developing"
        feature["lifecycle_state"] = "implementing"
        if not feature.get("started_at"):
            feature["started_at"] = _iso_now()

    if previous_current_id != feature_id:
        data.pop("workflow_state", None)
        # Defensive init so an interrupted skill still has a resumable phase.
        if not feature.get("completed", False):
            data["workflow_state"] = {"phase": "planning", "updated_at": _iso_now()}

    # Initialize review lanes when starting a new feature (idempotent).
    if not feature.get("completed", False) and REVIEW_ROUTER_AVAILABLE:
        _initialize_reviews(feature)

    svc.update_runtime_context_fn(data, "set_current")
    svc.save_progress_json_fn(data)

    svc.save_progress_md_fn("")

    svc.auto_state_commit_fn(f"F{feature_id}", "start")

    # Notify parent tracker to upsert active_routes for this child feature.
    if not feature.get("completed", False):
        svc.notify_parent_sync_fn("activate")

    print(f"Set current feature: {feature.get('name', 'Unknown')}")
    return True


def set_development_stage_command(
    stage: str,
    svc: FeatureCommandsServices,
    feature_id: Optional[int] = None,
) -> bool:
    """Set development_stage for the target feature (defaults to current)."""
    if stage not in DEVELOPMENT_STAGES:
        print(
            f"Invalid development_stage '{stage}'. "
            f"Must be one of: {DEVELOPMENT_STAGES}"
        )
        return False

    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    target_feature_id = (
        feature_id if feature_id is not None else data.get("current_feature_id")
    )
    if target_feature_id is None:
        print("Error: No active feature. Run '/prog-next' first or pass --feature-id.")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == target_feature_id), None)
    if not feature:
        print(f"Feature ID {target_feature_id} not found")
        return False

    if stage == "developing" and not feature.get("completed", False):
        readiness_report = validate_feature_readiness(feature)
        if not readiness_report["valid"]:
            print_readiness_error(feature, readiness_report)
            return False
        if readiness_report["warnings"]:
            print_readiness_warnings(readiness_report)
            print("")

    feature["development_stage"] = stage
    if stage == "developing" and not feature.get("started_at"):
        feature["started_at"] = _iso_now()
    if stage == "developing":
        feature["lifecycle_state"] = "implementing"
    elif stage == "planning" and not feature.get("completed", False):
        feature["lifecycle_state"] = "approved"
    elif stage == "completed":
        feature["lifecycle_state"] = "verified"

    svc.update_runtime_context_fn(data, "set_development_stage")
    svc.save_progress_json_fn(data)

    svc.save_progress_md_fn("")

    print(
        f"Feature #{target_feature_id} stage set to '{stage}': "
        f"{feature.get('name', 'Unknown')}"
    )
    return True
