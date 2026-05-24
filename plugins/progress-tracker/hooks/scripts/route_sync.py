"""
route_sync.py — Linked project and active-routes state sync helpers.

Extracted from progress_manager.py (F18 modularisation).

Contains:
- Linked project spec iteration / path resolution / worktree-aware translation.
- Linked snapshot freshness checks and feature completion counters.
- active_routes upsert/remove/parallel-detection helpers.
- _notify_parent_sync: child → parent linked_snapshot + active_routes writeback.

Note: collect_linked_project_statuses and sync_linked remain in progress_manager.py
(not extracted per F18 plan).

Lazy-imports from progress_manager are used for helpers that still live in
progress_manager.py to avoid circular-import issues (e.g. find_project_root,
load_progress_json, save_progress_json, generate_progress_md, _iso_now,
_parse_iso_timestamp, load_status_summary_projection, _apply_schema_defaults,
_save_progress_payload_at_root, _resolve_main_repo_path, _REPO_ROOT).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from prog_paths import get_progress_json_path
from state_io import LINKED_SNAPSHOT_SCHEMA_VERSION
from pm_runtime import get_progress_manager_module

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LINKED_STATUS_STALE_HOURS = 24


# ---------------------------------------------------------------------------
# Linked project spec iteration / path resolution
# ---------------------------------------------------------------------------


def _iter_linked_project_specs(progress_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract normalized linked project specs from progress payload."""
    linked_projects = progress_data.get("linked_projects")
    if not isinstance(linked_projects, list):
        return []

    specs: List[Dict[str, Any]] = []
    for entry in linked_projects:
        if isinstance(entry, dict):
            raw_root = (
                entry.get("project_root")
                or entry.get("path")
                or entry.get("root")
            )
            label = entry.get("label")
        elif isinstance(entry, str):
            raw_root = entry
            label = None
            entry = {"project_root": entry}
        else:
            continue

        raw_root_text = str(raw_root or "").strip()
        if not raw_root_text:
            continue

        specs.append(
            {
                "raw_project_root": raw_root_text,
                "label": str(label).strip() if isinstance(label, str) and label.strip() else None,
                "entry": entry,
            }
        )

    return specs


def _resolve_linked_project_root(
    raw_root: str,
    project_root: Path,
    repo_root: Path,
) -> Path:
    """Resolve linked project root from absolute or relative configuration."""
    candidate = Path(raw_root).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    repo_candidate = (repo_root / candidate).resolve()
    project_candidate = (project_root / candidate).resolve()

    if repo_candidate.exists():
        return repo_candidate
    if project_candidate.exists():
        return project_candidate
    if repo_root != project_root:
        return repo_candidate
    return project_candidate


def _get_main_repo_root(project_root: Path) -> Optional[Path]:
    """
    通过 git rev-parse --absolute-git-dir 检测是否在 worktree 内。
    如果是，则返回主仓库根目录，否则返回 None。
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        )
        git_dir = Path(result.stdout.strip()).resolve()
        parts = git_dir.parts
        # 寻找连续的 ".git" 和 "worktrees"
        for i in range(len(parts) - 2):
            if parts[i] == ".git" and parts[i + 1] == "worktrees":
                main_git_dir = Path(*parts[: i + 1])
                return main_git_dir.parent.resolve()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Feature completion / snapshot freshness
# ---------------------------------------------------------------------------


def _count_feature_completion(features: Any) -> Tuple[int, int]:
    """Return (completed, total) from a progress features payload."""
    if not isinstance(features, list):
        return (0, 0)

    total = 0
    completed = 0
    for feature in features:
        if not isinstance(feature, dict):
            continue
        total += 1
        if bool(feature.get("completed")):
            completed += 1
    return (completed, total)


def _is_linked_snapshot_stale(
    updated_at: Optional[str],
    now: datetime,
    stale_after_hours: int,
) -> bool:
    """Return True when linked snapshot timestamp is missing/invalid/too old."""
    # Lazy import: _parse_iso_timestamp lives in progress_manager.py
    _pm = get_progress_manager_module()

    timestamp = _pm._parse_iso_timestamp(updated_at)
    if timestamp is None:
        return True

    reference_time = now
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    age_seconds = (reference_time - timestamp.astimezone(reference_time.tzinfo)).total_seconds()
    return age_seconds > max(stale_after_hours, 0) * 3600


# ---------------------------------------------------------------------------
# active_routes upsert / remove / parallel detection
# ---------------------------------------------------------------------------


def _detect_parallel_active_routes(active_routes: List[Any]) -> List[Dict[str, Any]]:
    """Return one entry per distinct project_code when 2+ distinct codes exist (F20).

    Returns an empty list when there is no parallel conflict (0 or 1 distinct codes).
    Duplicate entries for the same project_code are collapsed to the first seen.
    """
    if not isinstance(active_routes, list) or len(active_routes) < 2:
        return []
    seen: Dict[str, Dict[str, Any]] = {}
    for route in active_routes:
        if not isinstance(route, dict):
            continue
        code_raw = route.get("project_code")
        if not isinstance(code_raw, str) or not code_raw.strip():
            continue
        code = code_raw.strip().upper()
        if code not in seen:
            seen[code] = route
    if len(seen) >= 2:
        return list(seen.values())
    return []


def _normalize_project_code(raw_code: str) -> Optional[str]:
    """Normalize and validate RouteV1 project code tokens."""
    token = str(raw_code or "").strip().upper()
    if not token:
        return None
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", token):
        return None
    return token


def _serialize_project_root_for_config(project_root: Path, repo_root: Path) -> str:
    """Persist linked project roots as repo-relative paths when possible.
    Supports git worktree by translating both sides to their main repo equivalents.
    """
    # Lazy import: _resolve_main_repo_path stays in progress_manager.py
    _pm = get_progress_manager_module()

    resolved_root = _pm._resolve_main_repo_path(project_root)
    resolved_repo = _pm._resolve_main_repo_path(repo_root)
    try:
        return resolved_root.relative_to(resolved_repo).as_posix()
    except ValueError:
        try:
            return resolved_root.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return str(resolved_root)


def _load_progress_payload_at_root(project_root: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load a progress payload from an explicit root without mutating scope globals."""
    # Lazy import: _apply_schema_defaults stays in progress_manager.py
    _pm = get_progress_manager_module()

    json_path = get_progress_json_path(project_root)
    if not json_path.exists():
        return None, f"linked child progress.json not found: {json_path}"
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"failed to load linked child progress.json: {exc}"
    if not isinstance(payload, dict):
        return None, f"linked child progress.json must contain a JSON object: {json_path}"
    _pm._apply_schema_defaults(payload)
    return payload, None


def _format_route_feature_ref(feature_id: int, project_code: str) -> str:
    """Format feature ref string: project_code='PT', feature_id=14 → 'PT-F14'."""
    return f"{project_code}-F{feature_id}"


def _upsert_active_route(
    parent_data: Dict[str, Any],
    project_code: str,
    feature_ref: str,
) -> None:
    """Upsert active_routes entry for project_code (in-place), deduplicating."""
    # Lazy import: _iso_now lives in progress_manager.py
    _pm = get_progress_manager_module()

    active_routes: List[Any] = parent_data.get("active_routes") or []
    if not isinstance(active_routes, list):
        active_routes = []
    normalized_code = project_code.strip().upper()
    other = [
        r for r in active_routes
        if isinstance(r, dict)
        and r.get("project_code", "").strip().upper() != normalized_code
    ]
    other.append({
        "project_code": normalized_code,
        "feature_ref": feature_ref,
        "assigned_at": _pm._iso_now(),
    })
    parent_data["active_routes"] = other


def _remove_active_route(parent_data: Dict[str, Any], project_code: str) -> None:
    """Remove active_routes entry for project_code (in-place)."""
    active_routes: List[Any] = parent_data.get("active_routes") or []
    if not isinstance(active_routes, list):
        parent_data["active_routes"] = []
        return
    normalized_code = project_code.strip().upper()
    parent_data["active_routes"] = [
        r for r in active_routes
        if not (
            isinstance(r, dict)
            and r.get("project_code", "").strip().upper() == normalized_code
        )
    ]


# ---------------------------------------------------------------------------
# Parent writeback (child → parent linked_snapshot + active_routes)
# ---------------------------------------------------------------------------


def _notify_parent_sync(route_event: str = "refresh") -> None:
    """Trigger parent linked_snapshot refresh after child state changes.

    route_event:
      "refresh"  — refresh linked_snapshot only (default, backward-compatible)
      "activate" — also upsert child's current feature into parent active_routes
      "clear"    — also remove child's entry from parent active_routes

    Reads parent_project_root from the current child tracker.
    On any error (missing parent, invalid data), prints WARNING and returns.
    Never raises — always warn-only.
    """
    # Lazy import: progress_manager-resident helpers
    _pm = get_progress_manager_module()

    try:
        child_data = _pm.load_progress_json()
        if not isinstance(child_data, dict):
            return
        parent_raw = child_data.get("parent_project_root")
        if not parent_raw or not str(parent_raw).strip():
            return

        child_root = _pm.find_project_root().resolve()
        repo_root = Path(_pm._REPO_ROOT or child_root).resolve()
        parent_root = _resolve_linked_project_root(str(parent_raw).strip(), child_root, repo_root)

        # Best-effort summary refresh before parent writeback (Task 7)
        try:
            _pm.load_status_summary_projection(str(child_root))
        except Exception as exc:
            logger.debug(f"Summary refresh failed during parent sync: {exc}")

        parent_data, err = _load_progress_payload_at_root(parent_root)
        if parent_data is None:
            print(
                f"[WARNING] Parent writeback skipped: cannot load parent tracker "
                f"at {parent_root}: {err}"
            )
            return

        active_routes = parent_data.get("active_routes") or []
        statuses = _pm.collect_linked_project_statuses(
            parent_data,
            project_root=parent_root,
            active_routes=active_routes,
        )

        linked_snapshot = parent_data.get("linked_snapshot")
        if not isinstance(linked_snapshot, dict):
            linked_snapshot = {}
        linked_snapshot["schema_version"] = LINKED_SNAPSHOT_SCHEMA_VERSION
        linked_snapshot["updated_at"] = _pm._iso_now()
        linked_snapshot["projects"] = statuses
        parent_data["linked_snapshot"] = linked_snapshot

        child_code_raw = child_data.get("project_code")
        child_code = (
            _normalize_project_code(child_code_raw)
            if isinstance(child_code_raw, str) and child_code_raw.strip()
            else None
        )

        if route_event == "activate" and child_code:
            current_fid = child_data.get("current_feature_id")
            if current_fid is not None:
                feature_ref = _format_route_feature_ref(current_fid, child_code)
                _upsert_active_route(parent_data, child_code, feature_ref)
                # Warn if other routes are already active (parallel execution)
                other_codes = [
                    r.get("project_code", "").strip().upper()
                    for r in (parent_data.get("active_routes") or [])
                    if isinstance(r, dict)
                    and r.get("project_code", "").strip().upper() != child_code
                ]
                if other_codes:
                    print(
                        f"[WARNING] Parallel active routes detected after activating "
                        f"{child_code}: other active route(s): {', '.join(other_codes)}"
                    )
        elif route_event == "clear" and child_code:
            _remove_active_route(parent_data, child_code)

        _pm._save_progress_payload_at_root(parent_root, parent_data)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARNING] Parent writeback failed: {exc}")
