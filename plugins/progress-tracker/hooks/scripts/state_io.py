"""
state_io.py — Atomic file I/O and schema normalisation helpers.

Extracted from progress_manager.py (F18 modularisation).

Note: load_progress_json / save_progress_json / _apply_schema_defaults remain in
progress_manager.py because they call get_progress_dir() and feature-normalisation
helpers that depend on progress_manager's global state.  Those will be migrated in
a future phase once the global-scope coupling is resolved.
"""
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Schema constants (moved here from progress_manager; re-imported there)
# ---------------------------------------------------------------------------

LINKED_SNAPSHOT_SCHEMA_VERSION = "1.0"
TRACKER_ROLES = ("standalone", "parent", "child")
DEFAULT_TRACKER_ROLE = "standalone"

# ---------------------------------------------------------------------------
# Atomic file I/O
# ---------------------------------------------------------------------------


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace a text file via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Linked snapshot schema normalisation
# ---------------------------------------------------------------------------


def _default_linked_snapshot() -> Dict[str, Any]:
    """Build default snapshot metadata for linked project status aggregation."""
    return {
        "schema_version": LINKED_SNAPSHOT_SCHEMA_VERSION,
        "updated_at": None,
        "projects": [],
    }


def _normalize_linked_schema(data: Dict[str, Any]) -> None:
    """Backfill linked_projects and linked_snapshot top-level schema fields."""
    linked_projects = data.get("linked_projects")
    if not isinstance(linked_projects, list):
        linked_projects = []
    data["linked_projects"] = linked_projects

    linked_snapshot = data.get("linked_snapshot")
    defaults = _default_linked_snapshot()
    if not isinstance(linked_snapshot, dict):
        data["linked_snapshot"] = defaults
        return

    for key, value in defaults.items():
        linked_snapshot.setdefault(key, value)

    if not isinstance(linked_snapshot.get("projects"), list):
        linked_snapshot["projects"] = []

    data["linked_snapshot"] = linked_snapshot


def _normalize_route_schema(data: Dict[str, Any]) -> None:
    """Backfill routing metadata fields used by RouteV1 coordination."""
    tracker_role = data.get("tracker_role")
    if not isinstance(tracker_role, str):
        normalized_tracker_role = DEFAULT_TRACKER_ROLE
    else:
        normalized_tracker_role = tracker_role.strip().lower()
        if normalized_tracker_role not in TRACKER_ROLES:
            normalized_tracker_role = DEFAULT_TRACKER_ROLE
    data["tracker_role"] = normalized_tracker_role

    project_code = data.get("project_code")
    if isinstance(project_code, str):
        stripped_project_code = project_code.strip()
        data["project_code"] = stripped_project_code or None
    else:
        data["project_code"] = None

    routing_queue = data.get("routing_queue")
    if not isinstance(routing_queue, list):
        routing_queue = []
    data["routing_queue"] = routing_queue

    active_routes = data.get("active_routes")
    if not isinstance(active_routes, list):
        active_routes = []
    data["active_routes"] = active_routes


# ---------------------------------------------------------------------------
# Feature quality-gate / sprint-contract schema defaults
# ---------------------------------------------------------------------------


def _default_sprint_contract(feature: Dict[str, Any]) -> None:
    """PR-3/schema-2.1: inject sprint_contract defaults if absent."""
    if os.environ.get("PROG_DISABLE_V2") == "1" and "sprint_contract" in feature:
        return
    feature.setdefault(
        "sprint_contract",
        {
            "scope": "",
            "done_criteria": [],
            "test_plan": [],
            "accepted_by": None,
            "accepted_at": None,
        },
    )


def _default_quality_gates(feature: Dict[str, Any]) -> None:
    """PR-3/schema-2.1: deep-merge quality_gates defaults (handles partial existing data)."""
    if os.environ.get("PROG_DISABLE_V2") == "1" and "quality_gates" in feature:
        return
    default_evaluator = {
        "status": "pending",
        "score": None,
        "defects": [],
        "last_run_at": None,
        "evaluator_model": None,
    }
    default_reviews: Dict[str, List] = {"required": [], "passed": [], "pending": []}
    default_ship_check = {"status": "pending", "failures": [], "last_run_at": None}

    if "quality_gates" not in feature:
        feature["quality_gates"] = {
            "evaluator": default_evaluator,
            "reviews": default_reviews,
            "ship_check": default_ship_check,
        }
        return

    qg = feature["quality_gates"]
    if not isinstance(qg.get("evaluator"), dict):
        qg["evaluator"] = default_evaluator
    else:
        for k, v in default_evaluator.items():
            qg["evaluator"].setdefault(k, v)
    if "reviews" not in qg:
        qg["reviews"] = default_reviews
    else:
        for k, v in default_reviews.items():
            qg["reviews"].setdefault(k, v)
    if "ship_check" not in qg:
        qg["ship_check"] = default_ship_check
    else:
        for k, v in default_ship_check.items():
            qg["ship_check"].setdefault(k, v)


def _sync_reviews_pending_cache(feature: Dict[str, Any]) -> None:
    """Keep reviews.pending as a derived cache from required - passed."""
    quality_gates = feature.get("quality_gates")
    if not isinstance(quality_gates, dict):
        return
    reviews = quality_gates.get("reviews")
    if not isinstance(reviews, dict):
        return

    required_raw = reviews.get("required")
    passed_raw = reviews.get("passed")
    required = required_raw if isinstance(required_raw, list) else []
    passed = passed_raw if isinstance(passed_raw, list) else []
    reviews["pending"] = [lane for lane in required if lane not in passed]


def _default_handoff(feature: Dict[str, Any]) -> None:
    """PR-3/schema-2.1: inject handoff defaults if absent."""
    if os.environ.get("PROG_DISABLE_V2") == "1" and "handoff" in feature:
        return
    feature.setdefault(
        "handoff",
        {
            "from_phase": None,
            "to_phase": None,
            "artifact_path": None,
            "created_at": None,
        },
    )
