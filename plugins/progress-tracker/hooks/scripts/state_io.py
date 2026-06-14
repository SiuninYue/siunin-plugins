"""
state_io.py — Atomic file I/O and schema normalisation helpers.

Extracted from progress_manager.py (F18 modularisation).
"""
import os
import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

LINKED_SNAPSHOT_SCHEMA_VERSION = "1.0"
TRACKER_ROLES = ("standalone", "parent", "child")
DEFAULT_TRACKER_ROLE = "standalone"

OWNER_ROLES = ("architecture", "coding", "testing")
LIFECYCLE_STATES = ("approved", "implementing", "verified", "archived")
CURRENT_SCHEMA_VERSION = "2.1"

PROGRESS_JSON = "progress.json"
PROGRESS_MD = "progress.md"

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
# File loading / saving with dependency injection
# ---------------------------------------------------------------------------

def load_progress_json(
    progress_dir: Path,
    apply_schema_defaults: Callable[[Dict[str, Any]], None],
) -> Optional[Dict[str, Any]]:
    """Load the progress.json file from the specified directory."""
    json_path = progress_dir / PROGRESS_JSON

    if not json_path.exists():
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                print(f"Error: {json_path} is not a valid JSON object.")
                return None
            apply_schema_defaults(data)
            return data
    except json.JSONDecodeError:
        print(f"Error: {json_path} is corrupted.")
        return None


def save_progress_json(
    progress_dir: Path,
    data: Dict[str, Any],
    touch_updated_at: bool = True,
    apply_schema_defaults: Optional[Callable[[Dict[str, Any]], None]] = None,
    now_fn: Optional[Callable[[], str]] = None,
) -> None:
    """Save data to progress.json file in progress_dir with optional updated_at touch."""
    progress_dir.mkdir(parents=True, exist_ok=True)
    json_path = progress_dir / PROGRESS_JSON

    if apply_schema_defaults is not None:
        apply_schema_defaults(data)

    if touch_updated_at and now_fn is not None:
        data["updated_at"] = now_fn()

    payload = json.dumps(data, indent=2, ensure_ascii=False)
    _atomic_write_text(json_path, payload)


def load_progress_md(progress_dir: Path) -> Optional[str]:
    """Load the progress.md file content."""
    md_path = progress_dir / PROGRESS_MD

    if not md_path.exists():
        return None

    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()


def save_progress_md(progress_dir: Path, content: str) -> None:
    """Save content to progress.md file."""
    progress_dir.mkdir(parents=True, exist_ok=True)
    md_path = progress_dir / PROGRESS_MD
    _atomic_write_text(md_path, content)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _normalize_optional_string(value: Optional[str]) -> Optional[str]:
    """Helper to strip and normalize string values to None if empty."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _default_owners() -> Dict[str, Optional[str]]:
    """Build default feature owners payload for known roles."""
    return {role: None for role in OWNER_ROLES}


def _normalize_feature_owners(feature: Dict[str, Any]) -> None:
    """Ensure feature owners map exists with known role keys."""
    owners = feature.get("owners")
    if not isinstance(owners, dict):
        owners = {}
    for role in OWNER_ROLES:
        owners.setdefault(role, None)
    feature["owners"] = owners


def _normalize_feature_defer_state(feature: Dict[str, Any]) -> None:
    """Ensure feature defer metadata is present and type-safe."""
    feature["deferred"] = bool(feature.get("deferred", False))
    feature["defer_reason"] = _normalize_optional_string(feature.get("defer_reason"))
    feature["deferred_at"] = _normalize_optional_string(feature.get("deferred_at"))
    feature["defer_group"] = _normalize_optional_string(feature.get("defer_group"))


def _clear_feature_defer_state(feature: Dict[str, Any]) -> None:
    """Clear defer metadata while keeping schema-compatible fields."""
    feature["deferred"] = False
    feature["defer_reason"] = None
    feature["deferred_at"] = None
    feature["defer_group"] = None


def _default_requirement_ids(feature: Dict[str, Any]) -> List[str]:
    """Build deterministic fallback requirement IDs for legacy features."""
    feature_id = feature.get("id")
    if isinstance(feature_id, int) and feature_id >= 0:
        return [f"REQ-{feature_id:03d}"]
    return ["REQ-000"]


def _default_change_spec(feature: Dict[str, Any]) -> Dict[str, Any]:
    """Build baseline change_spec for schema backfill."""
    feature_name = str(feature.get("name") or "Unnamed feature").strip()
    return {
        "why": f"Deliver {feature_name} with traceable acceptance coverage.",
        "in_scope": [feature_name],
        "out_of_scope": ["Unrelated refactors and behavior changes outside this feature."],
        "risks": ["Potential regression in adjacent workflows; verify with listed test_steps."],
    }


def _default_acceptance_scenarios(feature: Dict[str, Any]) -> List[str]:
    """Build fallback acceptance scenarios from test steps."""
    test_steps = feature.get("test_steps")
    if isinstance(test_steps, list):
        scenarios = [str(step).strip() for step in test_steps if str(step).strip()]
        if scenarios:
            return [f"Scenario: {step}" for step in scenarios]

    feature_name = str(feature.get("name") or "feature").strip()
    return [f"Scenario: {feature_name} baseline behavior works as expected."]


def _derive_lifecycle_state(feature: Dict[str, Any]) -> str:
    """Derive lifecycle state from legacy completion/development fields."""
    if feature.get("archive_info"):
        return "archived"

    if bool(feature.get("completed", False)):
        return "verified"

    stage = feature.get("development_stage")
    if stage == "developing":
        return "implementing"
    if stage == "completed":
        return "verified"

    return "approved"


def _normalize_feature_contract(feature: Dict[str, Any]) -> None:
    """Backfill schema 2.1 feature contract fields while preserving explicit values."""
    lifecycle_state = feature.get("lifecycle_state")
    if lifecycle_state not in LIFECYCLE_STATES:
        feature["lifecycle_state"] = _derive_lifecycle_state(feature)

    requirement_ids = feature.get("requirement_ids")
    if not isinstance(requirement_ids, list):
        feature["requirement_ids"] = _default_requirement_ids(feature)

    change_spec = feature.get("change_spec")
    if not isinstance(change_spec, dict):
        feature["change_spec"] = _default_change_spec(feature)
    else:
        defaults = _default_change_spec(feature)
        for key, value in defaults.items():
            change_spec.setdefault(key, value)

    acceptance_scenarios = feature.get("acceptance_scenarios")
    if not isinstance(acceptance_scenarios, list):
        feature["acceptance_scenarios"] = _default_acceptance_scenarios(feature)


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


def _apply_schema_defaults_core(data: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Backfill backward-compatible defaults for evolving schema fields.
    Returns (old_version, new_version) if migrated.
    """
    old_version = data.get("schema_version")
    if "schema_version" not in data:
        data["schema_version"] = CURRENT_SCHEMA_VERSION

    features = data.get("features")
    if not isinstance(features, list):
        features = []
    data["features"] = features
    for feature in features:
        if isinstance(feature, dict):
            _normalize_feature_owners(feature)
            _normalize_feature_defer_state(feature)
            _normalize_feature_contract(feature)
            _default_quality_gates(feature)
            _sync_reviews_pending_cache(feature)
            _default_sprint_contract(feature)
            _default_handoff(feature)

    migrated = None
    # Upgrade schema version and return migration tuple on first migration
    if old_version == "2.0" and data.get("schema_version") != "2.1":
        data["schema_version"] = "2.1"
        migrated = ("2.0", "2.1")
    elif old_version is None or old_version not in ("2.0", "2.1"):
        data["schema_version"] = CURRENT_SCHEMA_VERSION

    _normalize_linked_schema(data)
    _normalize_route_schema(data)

    updates = data.get("updates")
    if not isinstance(updates, list):
        updates = []
    data["updates"] = [item for item in updates if isinstance(item, dict)]

    retrospectives = data.get("retrospectives")
    if not isinstance(retrospectives, list):
        retrospectives = []
    data["retrospectives"] = [item for item in retrospectives if isinstance(item, dict)]

    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    data["tasks"] = [t for t in tasks if isinstance(t, dict)]

    return migrated

def _normalize_ref_tokens(refs: Optional[List[str]]) -> List[str]:
    """Normalize and deduplicate ref tokens while preserving encounter order."""
    normalized: List[str] = []
    seen = set()
    for raw in refs or []:
        if not isinstance(raw, str):
            continue
        token = raw.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized



def _normalize_context_path(value: Optional[str]) -> Optional[str]:
    """Normalize paths for cross-platform comparison."""
    if not value:
        return None
    try:
        return Path(value).resolve().as_posix()
    except Exception:
        return str(value).replace("\\", "/")


def compare_contexts(
    expected: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compare expected execution context with current/runtime context.

    Returns a normalized hint object suitable for recovery/status output.
    """
    if not isinstance(expected, dict):
        expected = {}
    if not isinstance(current, dict):
        current = {}

    expected_branch = _normalize_optional_string(expected.get("branch"))
    expected_path = _normalize_context_path(expected.get("worktree_path"))
    current_branch = _normalize_optional_string(current.get("branch"))
    current_path = _normalize_context_path(current.get("worktree_path"))

    expected_has_signal = bool(expected_branch or expected_path)
    current_has_signal = bool(current_branch or current_path)

    result: Dict[str, Any] = {
        "status": "unknown",
        "severity": "info",
        "expected_branch": expected_branch,
        "expected_worktree_path": expected_path,
        "current_branch": current_branch,
        "current_worktree_path": current_path,
        "message": "No execution context available yet.",
    }

    if not expected_has_signal:
        return result

    if not current_has_signal:
        result.update(
            {
                "status": "unknown",
                "severity": "warning",
                "message": "Current session context is unavailable; cannot verify worktree/branch alignment.",
            }
        )
        return result

    expected_needs_path = bool(expected_path)
    expected_needs_branch = bool(expected_branch)

    path_missing_current = expected_needs_path and not current_path
    branch_missing_current = expected_needs_branch and not current_branch

    path_mismatch = bool(expected_path and current_path and expected_path != current_path)
    branch_mismatch = bool(expected_branch and current_branch and expected_branch != current_branch)

    if path_mismatch or branch_mismatch:
        if path_mismatch and branch_mismatch:
            status = "mismatch"
        elif path_mismatch:
            status = "path_mismatch"
        else:
            status = "branch_mismatch"

        msg_parts: List[str] = ["Current session does not match the last recorded execution context"]
        details: List[str] = []
        if path_mismatch:
            details.append("worktree path differs")
        if branch_mismatch:
            details.append("branch differs")
        if path_missing_current:
            details.append("current worktree path unavailable")
        if branch_missing_current:
            details.append("current branch unavailable")
        if details:
            msg_parts.append(f"({', '.join(details)})")

        result.update(
            {
                "status": status,
                "severity": "warning",
                "message": " ".join(msg_parts) + ".",
            }
        )
        return result

    missing_parts: List[str] = []
    if path_missing_current:
        missing_parts.append("worktree path")
    if branch_missing_current:
        missing_parts.append("branch")
    if missing_parts:
        result.update(
            {
                "status": "unknown",
                "severity": "warning",
                "message": (
                    "Current session context is incomplete; cannot verify "
                    + " and ".join(missing_parts)
                    + " alignment."
                ),
            }
        )
        return result

    if (not expected_needs_path or expected_path == current_path) and (
        not expected_needs_branch or expected_branch == current_branch
    ):
        result.update(
            {
                "status": "match",
                "severity": "info",
                "message": "Current session matches the last recorded execution context.",
            }
        )
        return result

    result.update(
        {
            "status": "unknown",
            "severity": "warning",
            "message": "Current session context could not be fully compared with the recorded execution context.",
        }
    )
    return result


# ---------------------------------------------------------------------------
# Checkpoints & Schema defaults
# ---------------------------------------------------------------------------

CHECKPOINTS_JSON = "checkpoints.json"
CHECKPOINT_MAX_ENTRIES = 50


def apply_schema_defaults(data: Dict[str, Any]) -> None:
    """Apply default schema values to progress data in-place."""
    _apply_schema_defaults_core(data)


def load_checkpoints(progress_dir: Path) -> Dict[str, Any]:
    """Load checkpoints from progress_dir/checkpoints.json."""
    return load_checkpoints_from_file(progress_dir / CHECKPOINTS_JSON)


def load_checkpoints_from_file(path: Path) -> Dict[str, Any]:
    """Load checkpoints from explicit file path."""
    if not path.exists():
        return {
            "last_checkpoint_at": None,
            "max_entries": CHECKPOINT_MAX_ENTRIES,
            "entries": [],
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        import logging
        logging.getLogger("progress_tracker.state_io").warning(
            f"Corrupted checkpoints file: {path}. Reinitializing."
        )
        return {
            "last_checkpoint_at": None,
            "max_entries": CHECKPOINT_MAX_ENTRIES,
            "entries": [],
        }

    if not isinstance(data, dict):
        return {
            "last_checkpoint_at": None,
            "max_entries": CHECKPOINT_MAX_ENTRIES,
            "entries": [],
        }

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        entries = []

    max_entries = data.get("max_entries", CHECKPOINT_MAX_ENTRIES)
    if not isinstance(max_entries, int) or max_entries <= 0:
        max_entries = CHECKPOINT_MAX_ENTRIES

    return {
        "last_checkpoint_at": data.get("last_checkpoint_at"),
        "max_entries": max_entries,
        "entries": entries,
    }
