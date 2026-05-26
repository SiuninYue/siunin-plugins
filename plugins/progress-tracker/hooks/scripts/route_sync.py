"""
route_sync.py — Active routes management and linked snapshot tracking.

Extracted from progress_manager.py (F18 modularisation).
"""
import re
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Set

import state_io
from prog_paths import get_progress_json_path, get_progress_md_path

LINKED_SNAPSHOT_SCHEMA_VERSION = "1.0"
_COLLECT_LINKED_DISPATCH_DEPTH = 0
_NOTIFY_PARENT_DISPATCH_DEPTH = 0


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Helper to parse ISO-8601 string to a datetime object (timezone aware)."""
    if not isinstance(value, str):
        return None
    try:
        # Handle trailing Z
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


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
    Detect whether we are in a worktree and return main repo root if so.
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
        for i in range(len(parts) - 2):
            if parts[i] == ".git" and parts[i+1] == "worktrees":
                main_git_dir = Path(*parts[:i+1])
                return main_git_dir.parent.resolve()
    except Exception:
        pass
    return None


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
        if "completed" in feature:
            is_completed = bool(feature.get("completed"))
        else:
            lifecycle_state = str(feature.get("lifecycle_state") or "").strip().lower()
            development_stage = str(feature.get("development_stage") or "").strip().lower()
            # Legacy payload fallback when schema omitted explicit completed flag.
            is_completed = lifecycle_state == "archived" or development_stage == "completed"
        if is_completed:
            completed += 1
    return (completed, total)


def _is_linked_snapshot_stale(
    updated_at: Optional[str],
    now: datetime,
    stale_after_hours: int,
) -> bool:
    """Return True when linked snapshot timestamp is missing/invalid/too old."""
    timestamp = _parse_iso_timestamp(updated_at)
    if timestamp is None:
        return True

    reference_time = now
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    age_seconds = (reference_time - timestamp.astimezone(reference_time.tzinfo)).total_seconds()
    return age_seconds > max(stale_after_hours, 0) * 3600


def collect_linked_project_statuses(
    progress_data: Dict[str, Any],
    *,
    project_root: Path,
    repo_root: Path,
    now: Optional[datetime] = None,
    stale_after_hours: int = 24,
    active_routes: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Collect linked project progress snapshots in read-only mode.
    """
    global _COLLECT_LINKED_DISPATCH_DEPTH
    import sys
    pm = sys.modules.get("progress_manager")
    if (
        _COLLECT_LINKED_DISPATCH_DEPTH == 0
        and pm is not None
        and hasattr(pm, "collect_linked_project_statuses")
    ):
        pm_func = pm.collect_linked_project_statuses
        if getattr(pm_func, "is_wrapper", None) is not True:
            # Route back if the wrapper itself was patched, but guard against
            # patched implementations that re-enter this function.
            _COLLECT_LINKED_DISPATCH_DEPTH += 1
            try:
                return pm_func(
                    progress_data,
                    project_root=project_root,
                    repo_root=repo_root,
                    now=now,
                    stale_after_hours=stale_after_hours,
                    active_routes=active_routes,
                )
            finally:
                _COLLECT_LINKED_DISPATCH_DEPTH -= 1

    effective_project_root = project_root.resolve()
    effective_repo_root = repo_root.resolve()
    reference_time = now or datetime.now(timezone.utc)

    _active_route_codes: Set[str] = set()
    if isinstance(active_routes, list):
        for _r in active_routes:
            if isinstance(_r, dict):
                _code = _r.get("project_code")
                if isinstance(_code, str) and _code.strip():
                    _active_route_codes.add(_code.strip().upper())

    statuses: List[Dict[str, Any]] = []
    for spec in _iter_linked_project_specs(progress_data):
        spec_project_code: Optional[str] = None
        _raw_code = spec.get("entry", {}).get("project_code")
        if isinstance(_raw_code, str) and _raw_code.strip():
            spec_project_code = _raw_code.strip().upper()

        linked_root = _resolve_linked_project_root(
            spec["raw_project_root"], effective_project_root, effective_repo_root
        )
        progress_path = get_progress_json_path(linked_root)
        fallback_name = spec.get("label") or linked_root.name

        status: Dict[str, Any] = {
            "status": "missing",
            "configured_project_root": spec["raw_project_root"],
            "project_root": str(linked_root),
            "project_name": fallback_name,
            "completed": 0,
            "total": 0,
            "completion_rate": 0.0,
            "updated_at": None,
            "is_stale": True,
            "active_feature_ref": None,
            "project_code": None,
            "child_project_code": None,
            "workspace": "unknown",
            "route_status": "idle",
        }

        if not progress_path.exists():
            status["project_code"] = spec_project_code
            if spec_project_code is None:
                status["route_status"] = "unknown"
            elif spec_project_code in _active_route_codes:
                status["route_status"] = "active"
            statuses.append(status)
            continue

        try:
            payload = json.loads(progress_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("progress payload must be object")
            state_io._apply_schema_defaults_core(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            status["status"] = "invalid"
            status["error"] = str(exc)
            status["project_code"] = spec_project_code
            if spec_project_code is None:
                status["route_status"] = "unknown"
            elif spec_project_code in _active_route_codes:
                status["route_status"] = "active"
            statuses.append(status)
            continue

        project_name = payload.get("project_name")
        if isinstance(project_name, str) and project_name.strip():
            status["project_name"] = project_name.strip()

        completed, total = _count_feature_completion(payload.get("features"))
        updated_at = payload.get("updated_at")
        if not isinstance(updated_at, str) or not updated_at.strip():
            updated_at = None

        status["status"] = "ok"
        status["completed"] = completed
        status["total"] = total
        status["completion_rate"] = (completed / total) if total > 0 else 0.0
        status["updated_at"] = updated_at
        status["is_stale"] = _is_linked_snapshot_stale(
            updated_at,
            reference_time,
            stale_after_hours,
        )

        child_code_raw = payload.get("project_code")
        child_code = None
        if isinstance(child_code_raw, str) and child_code_raw.strip():
            child_code = child_code_raw.strip().upper()
        status["child_project_code"] = child_code

        resolved_code = spec_project_code or child_code
        status["project_code"] = resolved_code

        _VALID_WORKSPACE_MODES = {"worktree", "in_place", "unknown"}
        rt_ctx = payload.get("runtime_context")
        if isinstance(rt_ctx, dict):
            wm = rt_ctx.get("workspace_mode")
            if isinstance(wm, str) and wm.strip() in _VALID_WORKSPACE_MODES:
                status["workspace"] = wm.strip()

        if resolved_code is None:
            status["route_status"] = "unknown"
        elif resolved_code in _active_route_codes:
            status["route_status"] = "active"

        project_code_val = payload.get("project_code")
        current_feature_id = payload.get("current_feature_id")
        if isinstance(project_code_val, str) and project_code_val.strip() and isinstance(current_feature_id, int):
            status["active_feature_ref"] = f"{project_code_val.strip()}-F{current_feature_id}"

        statuses.append(status)

    return statuses


def _normalize_project_code(raw_code: str) -> Optional[str]:
    """Normalize and validate RouteV1 project code tokens."""
    token = str(raw_code or "").strip().upper()
    if not token:
        return None
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", token):
        return None
    return token


def _serialize_project_root_for_config(
    project_root: Path,
    repo_root: Path,
    resolve_main_repo_path_fn: Callable[[Path], Path],
) -> str:
    """Persist linked project roots as repo-relative paths when possible."""
    resolved_root = resolve_main_repo_path_fn(project_root)
    resolved_repo = resolve_main_repo_path_fn(repo_root)
    try:
        return resolved_root.relative_to(resolved_repo).as_posix()
    except ValueError:
        try:
            return resolved_root.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return str(resolved_root)


def _load_progress_payload_at_root(
    project_root: Path,
    apply_schema_defaults_fn: Callable[[Dict[str, Any]], None],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load a progress payload from an explicit root without mutating scope globals."""
    json_path = get_progress_json_path(project_root)
    if not json_path.exists():
        return None, f"linked child progress.json not found: {json_path}"
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"failed to load linked child progress.json: {exc}"
    if not isinstance(payload, dict):
        return None, f"linked child progress.json must contain a JSON object: {json_path}"
    apply_schema_defaults_fn(payload)
    return payload, None


def _format_route_feature_ref(feature_id: int, project_code: str) -> str:
    """Format feature ref string."""
    return f"{project_code}-F{feature_id}"


def _upsert_active_route(
    parent_data: Dict[str, Any],
    project_code: str,
    feature_ref: str,
    now_str: str,
) -> None:
    """Upsert active_routes entry for project_code (in-place), deduplicating."""
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
        "assigned_at": now_str,
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


def _detect_parallel_active_routes(active_routes: List[Any]) -> List[Dict[str, Any]]:
    """Return one entry per distinct project_code when 2+ distinct codes exist (F20)."""
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


def _notify_parent_sync(
    child_data: Dict[str, Any],
    child_root: Path,
    repo_root: Path,
    route_event: str,
    load_progress_payload_fn: Callable[[Path], Tuple[Optional[Dict[str, Any]], Optional[str]]],
    save_progress_payload_fn: Callable[[Path, Dict[str, Any]], None],
    load_status_summary_projection_fn: Callable[[str], None],
    iso_now_fn: Callable[[], str],
) -> None:
    """Trigger parent linked_snapshot refresh after child state changes."""
    global _NOTIFY_PARENT_DISPATCH_DEPTH
    import sys
    pm = sys.modules.get("progress_manager")
    if (
        _NOTIFY_PARENT_DISPATCH_DEPTH == 0
        and pm is not None
        and hasattr(pm, "_notify_parent_sync")
    ):
        pm_func = pm._notify_parent_sync
        if getattr(pm_func, "is_wrapper", None) is not True:
            _NOTIFY_PARENT_DISPATCH_DEPTH += 1
            try:
                # Route back if the wrapper itself was patched!
                # Since the wrapper in progress_manager takes only route_event,
                # we invoke it with route_event.
                return pm_func(route_event)
            finally:
                _NOTIFY_PARENT_DISPATCH_DEPTH -= 1

    try:
        parent_raw = child_data.get("parent_project_root")
        if not parent_raw or not str(parent_raw).strip():
            return

        parent_root = _resolve_linked_project_root(str(parent_raw).strip(), child_root, repo_root)

        # Best-effort summary refresh before parent writeback
        try:
            load_status_summary_projection_fn(str(child_root))
        except Exception as exc:
            pass

        parent_data, err = load_progress_payload_fn(parent_root)
        if parent_data is None:
            print(
                f"[WARNING] Parent writeback skipped: cannot load parent tracker "
                f"at {parent_root}: {err}"
            )
            return

        active_routes = parent_data.get("active_routes") or []
        statuses = collect_linked_project_statuses(
            parent_data,
            project_root=parent_root,
            repo_root=repo_root,
            active_routes=active_routes,
        )

        linked_snapshot = parent_data.get("linked_snapshot")
        if not isinstance(linked_snapshot, dict):
            linked_snapshot = {}
        linked_snapshot["schema_version"] = LINKED_SNAPSHOT_SCHEMA_VERSION
        linked_snapshot["updated_at"] = iso_now_fn()
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
                _upsert_active_route(parent_data, child_code, feature_ref, iso_now_fn())
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

        save_progress_payload_fn(parent_root, parent_data)
    except Exception as exc:
        print(f"[WARNING] Parent writeback failed: {exc}")
