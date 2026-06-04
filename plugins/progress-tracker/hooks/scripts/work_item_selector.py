"""Work-item selection helpers for ``prog next-feature``.

Extracted from ``progress_manager.py`` (F23 facade refactor). This module
contains selection business logic only and depends on injected services for
state, route loading, and timestamp behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class WorkItemSelectorServices:
    """Injected callbacks and constants for work-item selection."""

    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    is_feature_deferred_fn: Callable[[Dict[str, Any]], bool]
    parse_iso_timestamp_fn: Callable[[Optional[str]], Optional[datetime]]
    now_fn: Callable[[], datetime]
    warn_fn: Callable[[str], None]
    resolve_linked_project_root_fn: Callable[[str, Path, Path], Path]
    load_progress_payload_at_root_fn: Callable[
        [Path], Tuple[Optional[Dict[str, Any]], Optional[str]]
    ]
    stale_after_hours: int
    root_route_code: str


def _as_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime for age calculations."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_next_feature(svc: WorkItemSelectorServices) -> Optional[Dict[str, Any]]:
    """Return the first incomplete, non-deferred feature."""
    data = svc.load_progress_json_fn()
    if not data:
        return None

    features = data.get("features", [])
    for feature in features:
        if not isinstance(feature, dict):
            continue
        if not feature.get("completed", False) and not svc.is_feature_deferred_fn(feature):
            return feature

    return None


def get_dispatched_child_feature(
    routing_queue: List[str],
    active_routes: List[Any],
    linked_projects: List[Any],
    project_root: Path,
    repo_root: Path,
    svc: WorkItemSelectorServices,
    parent_data: Optional[Dict[str, Any]] = None,
    stale_after_hours: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Scan routing_queue and return the first dispatchable feature, or None.

    Supports the configured root route code for root-level features and child
    project codes for child dispatch. Emits warnings for unknown non-root codes.
    """
    stale_threshold = (
        svc.stale_after_hours if stale_after_hours is None else stale_after_hours
    )

    # Build lookup: code -> linked_project_entry
    lp_lookup: Dict[str, Any] = {}
    for entry in linked_projects:
        if isinstance(entry, dict) and entry.get("project_code"):
            lp_lookup[entry["project_code"]] = entry

    # Build set of conflicted codes from active_routes (child-only)
    conflicted: set = set()
    for route in active_routes:
        if not isinstance(route, dict):
            continue
        status = route.get("status")
        if status in {"done", "cancelled"}:
            continue
        assigned_at = route.get("assigned_at")
        is_stale = False
        if assigned_at:
            ts = svc.parse_iso_timestamp_fn(assigned_at)
            if ts is not None:
                now = _as_utc(svc.now_fn())
                ts_utc = _as_utc(ts)
                age_hours = (now - ts_utc).total_seconds() / 3600
                if age_hours > stale_threshold:
                    is_stale = True
        if not is_stale:
            code = route.get("project_code")
            if code:
                conflicted.add(code)

    # Scan routing_queue for the first dispatchable entry
    for position, code in enumerate(routing_queue, start=1):
        # ROOT: return root-level pending feature
        if code == svc.root_route_code:
            if not isinstance(parent_data, dict):
                continue
            root_features = parent_data.get("features", [])
            if not isinstance(root_features, list):
                continue
            for feature in root_features:
                if not isinstance(feature, dict):
                    continue
                if (
                    not feature.get("completed", False)
                    and not svc.is_feature_deferred_fn(feature)
                ):
                    return {
                        "dispatched_to": "root",
                        "child_project_code": svc.root_route_code,
                        "child_project_root": str(project_root),
                        "next_feature_id": feature.get("id"),
                        "next_feature_name": feature.get("name"),
                        "action_required": "prog next",
                        "position": position,
                    }
            continue

        # Unknown non-ROOT code: warn and skip (CONSTRAINT-008)
        if code not in lp_lookup:
            svc.warn_fn(f'Code "{code}" not found in linked_projects, skipping')
            continue

        # Child active-route conflict
        if code in conflicted:
            continue

        entry = lp_lookup[code]
        raw_project_root = (
            entry.get("project_root") or entry.get("path") or entry.get("root")
        )
        if not raw_project_root:
            continue
        child_root = svc.resolve_linked_project_root_fn(
            raw_project_root, project_root, repo_root
        )
        child_data, error = svc.load_progress_payload_at_root_fn(child_root)
        if error or not child_data:
            continue
        feature = None
        for candidate in child_data.get("features", []):
            if not isinstance(candidate, dict):
                continue
            if (
                not candidate.get("completed", False)
                and not svc.is_feature_deferred_fn(candidate)
            ):
                feature = candidate
                break
        if feature is None:
            continue
        return {
            "dispatched_to": "child",
            "child_project_code": code,
            "child_project_root": str(child_root),
            "next_feature_id": feature.get("id"),
            "next_feature_name": feature.get("name"),
            "action_required": f"cd {child_root} && prog next",
            "position": position,
        }

    return None


def select_next_work_item(
    data: Dict[str, Any],
    project_root: Path,
    repo_root: Path,
    svc: WorkItemSelectorServices,
) -> Optional[Dict[str, Any]]:
    """Unified work-item selector with priority ordering.

    Priority order:
        P0 bug > P1 bug > standalone task > feature_task (child/root) > P2 bug
    """
    # ------------------------------------------------------------------
    # Step 1: active_route conflict set for BUG-* entries.
    # Stale routes are treated as non-conflicting, matching child dispatch.
    # ------------------------------------------------------------------
    active_bug_ids: set = set()
    for route in data.get("active_routes") or []:
        if not isinstance(route, dict):
            continue
        status = route.get("status")
        if status in ("done", "cancelled"):
            continue
        assigned_at = route.get("assigned_at")
        if assigned_at:
            ts = svc.parse_iso_timestamp_fn(assigned_at)
            if ts is not None:
                now = _as_utc(svc.now_fn())
                ts_utc = _as_utc(ts)
                age_hours = (now - ts_utc).total_seconds() / 3600
                if age_hours > svc.stale_after_hours:
                    continue
        code = route.get("project_code", "")
        if isinstance(code, str) and code.startswith("BUG-"):
            active_bug_ids.add(code)

    # ------------------------------------------------------------------
    # Step 2: bucket routing_queue entries by priority tier.
    # ------------------------------------------------------------------
    bugs_map: Dict[str, Dict[str, Any]] = {
        bug["id"]: bug
        for bug in (data.get("bugs") or [])
        if isinstance(bug, dict) and isinstance(bug.get("id"), str)
    }
    skip_statuses = {"fixed", "false_positive"}

    p0_bugs: List[tuple] = []
    p1_bugs: List[tuple] = []
    p2_bugs: List[tuple] = []
    other_entries: List[str] = []

    for entry in data.get("routing_queue") or []:
        if not isinstance(entry, str):
            continue
        if entry.startswith("BUG-"):
            bug = bugs_map.get(entry)
            if bug is None:
                continue
            if bug.get("status") in skip_statuses:
                continue
            if entry in active_bug_ids:
                continue
            prio = bug.get("priority", "medium")
            if prio == "high":
                p0_bugs.append((entry, bug))
            elif prio == "low":
                p2_bugs.append((entry, bug))
            else:
                p1_bugs.append((entry, bug))
        else:
            other_entries.append(entry)

    def _bug_item(bug_id: str, bug: Dict[str, Any], tier: str) -> Dict[str, Any]:
        return {
            "item_type": "bug",
            "id": bug_id,
            "name": bug.get("description", bug_id),
            "priority_tier": tier,
            "action": f"/prog-fix {bug_id}",
            "dispatched_to": "bug",
        }

    def _task_item(task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = task.get("id")
        return {
            "item_type": "task",
            "id": task_id,
            "name": task.get("description", task_id),
            "priority_tier": None,
            "action": "prog next --done",
            "dispatched_to": "task",
        }

    # ------------------------------------------------------------------
    # Step 3: priority traversal.
    # ------------------------------------------------------------------
    for bug_id, bug in p0_bugs:
        return _bug_item(bug_id, bug, "P0")

    for bug_id, bug in p1_bugs:
        return _bug_item(bug_id, bug, "P1")

    for task in data.get("tasks") or []:
        if isinstance(task, dict) and task.get("status") == "pending":
            return _task_item(task)

    if other_entries:
        active_routes = data.get("active_routes") or []
        linked_projects = data.get("linked_projects") or []
        dispatch_result = get_dispatched_child_feature(
            other_entries,
            active_routes,
            linked_projects,
            project_root,
            repo_root,
            svc=svc,
            parent_data=data,
        )
        if dispatch_result:
            dispatched_to = dispatch_result.get("dispatched_to", "child")
            item_type = "root" if dispatched_to == "root" else "child"
            return {
                "item_type": item_type,
                "id": dispatch_result.get("next_feature_id"),
                "name": dispatch_result.get("next_feature_name"),
                "priority_tier": None,
                "action": dispatch_result.get("action_required"),
                "dispatched_to": dispatched_to,
                "dispatch_result": dispatch_result,
            }

    for bug_id, bug in p2_bugs:
        return _bug_item(bug_id, bug, "P2")

    # ------------------------------------------------------------------
    # Step 4: feature fallback via get_next_feature().
    # ------------------------------------------------------------------
    feature = get_next_feature(svc)
    if feature:
        return {
            "item_type": "feature",
            "id": feature.get("id"),
            "name": feature.get("name"),
            "priority_tier": None,
            "action": "prog next",
            "dispatched_to": "feature",
            "feature": feature,
        }

    return None
