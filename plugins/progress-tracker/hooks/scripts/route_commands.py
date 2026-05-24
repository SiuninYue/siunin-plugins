"""
route_commands.py — Routing CLI commands and route preflight guard.

Extracted from progress_manager.py (F18 modularisation).

Contains:
- Plugin catalog discovery and project-code generation helpers.
- `_link_child_to_parent` — core child registration used by both manual
  `link-project` and automatic discovery.
- `_auto_discover_child_plugins` — monorepo scan-and-register flow.
- CLI command entry points: `discover_children`, `route_status`,
  `prioritize_route`, `set_routing_queue`, `route_select`.

Lazy-imports from progress_manager are used for helpers that still live in
progress_manager.py and for functions/attributes that tests patch via
``progress_manager.X`` (e.g. ``load_progress_json``, ``save_progress_json``,
``generate_progress_md``, ``find_project_root``, ``collect_git_context``,
``_resolve_main_repo_path``, ``_save_progress_payload_at_root``,
``_REPO_ROOT``, ``ROOT_ROUTE_CODE``, ``ROUTE_PREFLIGHT_EXEMPT_COMMANDS``).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from prog_paths import resolve_repo_root
from route_sync import (
    _detect_parallel_active_routes,
    _format_route_feature_ref,  # noqa: F401 — re-exported for callers
    _iter_linked_project_specs,
    _load_progress_payload_at_root,
    _normalize_project_code,
    _remove_active_route,  # noqa: F401 — re-exported for callers
    _resolve_linked_project_root,
    _serialize_project_root_for_config,
    _upsert_active_route,  # noqa: F401 — re-exported for callers
)
from state_io import DEFAULT_TRACKER_ROLE, _normalize_route_schema
from pm_runtime import get_progress_manager_module

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (mirror of progress_manager constants for self-contained imports).
# Authoritative values still live in progress_manager; tests that patch via
# ``progress_manager.ROOT_ROUTE_CODE`` must resolve through the lazy accessor.
# ---------------------------------------------------------------------------

PROGRESS_JSON = "progress.json"


def _pm():
    """Return the active progress_manager module for CLI scope and test patches."""
    return get_progress_manager_module()


def _resolve_repo_root(project_root: Path) -> Path:
    """Resolve the git repo root from the project root."""
    return resolve_repo_root(cwd=project_root)


# ---------------------------------------------------------------------------
# Plugin catalog discovery and code generation
# ---------------------------------------------------------------------------


def _derive_plugin_code(plugin_name: str) -> str:
    """Derive a short project code from a plugin name.

    Takes the first letter of each hyphen/underscore-separated segment,
    uppercase.  Truncates to 8 chars max.

    Examples:
        "note-organizer" → "NO"
        "super-product-manager" → "SPM"
        "progress-tracker" → "PT"
    """
    segments = re.split(r"[-_]+", plugin_name.strip())
    code = "".join(seg[0].upper() for seg in segments if seg)
    return code[:8]


def _generate_project_code(plugin_name: str, used_codes: Set[str]) -> str:
    """Generate a unique project code, handling collisions.

    If the derived code is in ``used_codes``, appends numeric suffix 2, 3, …
    up to the 8-char maximum.  Emits a warning when a suffix is applied.
    """
    base = _derive_plugin_code(plugin_name)
    if base not in used_codes:
        return base
    # Collision – truncate base to leave room for suffix within 8-char limit
    for suffix in range(2, 100):
        candidate = f"{base}{suffix}"[:8]
        if candidate not in used_codes:
            logger.warning(
                f"Code collision: derived '{base}' already used; "
                f"assigned '{candidate}' for plugin '{plugin_name}'"
            )
            return candidate
    # Fallback: try progressively shorter bases with suffixes
    for prefix_len in range(7, 3, -1):
        for suffix in range(2, 100):
            candidate = f"{base[:prefix_len]}{suffix}"
            if len(candidate) <= 8 and candidate not in used_codes:
                logger.warning(
                    f"Code collision exhausted for plugin '{plugin_name}'; "
                    f"using fallback '{candidate}'"
                )
                return candidate
    # Ultimate fallback
    fallback = base[:6] + "XX"
    if fallback not in used_codes:
        return fallback
    raise ValueError(f"Cannot generate unique project code for '{plugin_name}'")


def _discover_plugin_catalog(
    repo_root: Path,
    parent_root: Path,
) -> Dict[str, List[Dict[str, Any]]]:
    """Scan repo_root/plugins/* for .claude-plugin/plugin.json.

    Pure read-only — never writes to parent or child trackers, never calls
    ``ensure_tracker_layout``, never registers links.

    Returns ``{"initialized": [...], "uninitialized": [...]}`` where each
    entry is ``{"name": str, "root": Path, "plugin_json": dict}``.
    """
    plugins_dir = repo_root / "plugins"
    if not plugins_dir.is_dir():
        return {"initialized": [], "uninitialized": []}

    initialized: List[Dict[str, Any]] = []
    uninitialized: List[Dict[str, Any]] = []

    for child_dir in sorted(plugins_dir.iterdir()):
        if not child_dir.is_dir():
            continue
        # Skip the parent itself
        if child_dir.resolve() == parent_root.resolve():
            continue

        plugin_json_path = child_dir / ".claude-plugin" / "plugin.json"
        if not plugin_json_path.is_file():
            continue

        try:
            plugin_json = json.loads(plugin_json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(plugin_json, dict):
            continue

        plugin_name = plugin_json.get("name", child_dir.name)
        entry = {"name": plugin_name, "root": child_dir, "plugin_json": plugin_json}

        tracker_file = child_dir / "docs" / "progress-tracker" / "state" / PROGRESS_JSON
        if tracker_file.is_file():
            initialized.append(entry)
        else:
            uninitialized.append(entry)

    return {"initialized": initialized, "uninitialized": uninitialized}


# ---------------------------------------------------------------------------
# Child registration (shared by link-project and discover-children)
# ---------------------------------------------------------------------------


def _link_child_to_parent(
    parent_data: Dict[str, Any],
    parent_root: Path,
    repo_root: Path,
    child_root: Path,
    code: str,
    label: Optional[str] = None,
    append_to_queue: bool = True,
    child_wt_root: Optional[Path] = None,
) -> None:
    """Register a child tracker in the parent's linked_projects and queue.

    Extracted from ``link_project()`` so discovery can reuse the core
    registration logic without the CLI scaffolding.
    """
    pm = _pm()
    normalized_code = _normalize_project_code(code) or code.upper()[:8]

    # Write child metadata
    child_data, _ = _load_progress_payload_at_root(child_root)
    if child_data is None and child_wt_root is not None and child_wt_root.resolve() != child_root.resolve():
        child_data, _ = _load_progress_payload_at_root(child_wt_root)
    if isinstance(child_data, dict):
        child_data["tracker_role"] = "child"
        child_data["project_code"] = normalized_code
        child_data["parent_project_root"] = _serialize_project_root_for_config(
            parent_root, repo_root
        )
        pm._save_progress_payload_at_root(child_root, child_data)

    # If worktree root is provided and distinct, update it too
    if child_wt_root is not None and child_wt_root.resolve() != child_root.resolve():
        wt_child_data, _ = _load_progress_payload_at_root(child_wt_root)
        if isinstance(wt_child_data, dict):
            wt_child_data["tracker_role"] = "child"
            wt_child_data["project_code"] = normalized_code
            wt_child_data["parent_project_root"] = _serialize_project_root_for_config(
                parent_root, repo_root
            )
            pm._save_progress_payload_at_root(child_wt_root, wt_child_data)

    # Infer label
    if label is None:
        child_name = child_data.get("project_name") if isinstance(child_data, dict) else None
        label = (
            child_name.strip()
            if isinstance(child_name, str) and child_name.strip()
            else child_root.name
        )
    normalized_label = label.strip() if isinstance(label, str) and label.strip() else child_root.name

    configured_project_root = _serialize_project_root_for_config(child_root, repo_root)

    # Upsert linked_projects
    linked_projects = parent_data.get("linked_projects")
    if not isinstance(linked_projects, list):
        linked_projects = []

    target_written = False
    deduped: List[Any] = []
    for entry in linked_projects:
        entry_root_raw = None
        entry_code_raw = None
        if isinstance(entry, dict):
            raw_value = entry.get("project_root") or entry.get("path") or entry.get("root")
            entry_root_raw = str(raw_value).strip() if raw_value is not None else None
            entry_code_raw = entry.get("project_code")

        entry_root = (
            _resolve_linked_project_root(entry_root_raw, parent_root, repo_root)
            if entry_root_raw
            else None
        )

        matches_target = (entry_root == child_root) or (
            isinstance(entry_code_raw, str) and entry_code_raw.strip().upper() == normalized_code
        )
        if matches_target:
            if target_written:
                continue
            base = entry if isinstance(entry, dict) else {}
            updated = dict(base)
            updated["project_root"] = configured_project_root
            updated["project_code"] = normalized_code
            updated["label"] = normalized_label
            deduped.append(updated)
            target_written = True
            continue

        deduped.append(entry)

    if not target_written:
        deduped.append(
            {
                "project_root": configured_project_root,
                "project_code": normalized_code,
                "label": normalized_label,
            }
        )

    parent_data["linked_projects"] = deduped
    parent_data["tracker_role"] = "parent"

    # Update routing_queue
    if append_to_queue:
        routing_queue = parent_data.get("routing_queue")
        if not isinstance(routing_queue, list):
            routing_queue = []
        if normalized_code not in routing_queue:
            routing_queue.append(normalized_code)
        parent_data["routing_queue"] = routing_queue


def _auto_discover_child_plugins(
    project_root: Path,
    repo_root: Path,
    parent_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Discover and register initialized child trackers.

    Calls ``_discover_plugin_catalog`` internally.  Preserves existing queue
    order and appends newly discovered codes.
    """
    pm = _pm()
    catalog = _discover_plugin_catalog(repo_root, parent_root=project_root)

    # Collect used codes from existing queue + linked_projects
    existing_queue: List[str] = parent_data.get("routing_queue") or []
    if not isinstance(existing_queue, list):
        existing_queue = []
    existing_linked = parent_data.get("linked_projects") or []
    if not isinstance(existing_linked, list):
        existing_linked = []

    used_codes: Set[str] = set()
    for item in existing_queue:
        if isinstance(item, str) and item.strip():
            used_codes.add(item.strip().upper())
    for entry in existing_linked:
        if isinstance(entry, dict):
            code_raw = entry.get("project_code")
            if isinstance(code_raw, str) and code_raw.strip():
                used_codes.add(code_raw.strip().upper())

    added_codes: List[str] = []
    warnings: List[str] = []

    for child_info in catalog["initialized"]:
        child_root: Path = child_info["root"]
        plugin_name: str = child_info["name"]

        # Code resolution priority:
        # 1. Existing project_code in child progress.json
        # 2. Derive from plugin name
        child_data, _ = _load_progress_payload_at_root(child_root)
        resolved_code = None
        if isinstance(child_data, dict):
            existing_code = child_data.get("project_code")
            if isinstance(existing_code, str) and existing_code.strip():
                resolved_code = existing_code.strip().upper()

        if resolved_code is None:
            resolved_code = _generate_project_code(plugin_name, used_codes)

        used_codes.add(resolved_code)

        # Check if already linked
        already_linked = False
        for entry in existing_linked:
            if isinstance(entry, dict):
                entry_root_raw = entry.get("project_root") or entry.get("path") or entry.get("root")
                entry_root = (
                    _resolve_linked_project_root(str(entry_root_raw).strip(), project_root, repo_root)
                    if entry_root_raw
                    else None
                )
                if entry_root == child_root:
                    already_linked = True
                    break

        if not already_linked:
            _link_child_to_parent(
                parent_data,
                parent_root=project_root,
                repo_root=repo_root,
                child_root=child_root,
                code=resolved_code,
                append_to_queue=True,
            )
            added_codes.append(resolved_code)
        else:
            # Even if already linked, write back child metadata if missing
            if isinstance(child_data, dict):
                child_data.setdefault("tracker_role", "child")
                child_data.setdefault("project_code", resolved_code)
                child_data.setdefault(
                    "parent_project_root",
                    _serialize_project_root_for_config(project_root, repo_root),
                )
                pm._save_progress_payload_at_root(child_root, child_data)

    # Initialize empty queue as [ROOT] + sorted(initialized_codes) if queue is empty
    if not existing_queue:
        # Re-derive properly with all codes considered
        all_codes: Set[str] = set()
        final_codes: List[str] = [pm.ROOT_ROUTE_CODE]
        for info in catalog["initialized"]:
            child_data_tmp, _ = _load_progress_payload_at_root(info["root"])
            code = None
            if isinstance(child_data_tmp, dict):
                code = child_data_tmp.get("project_code")
                if isinstance(code, str) and code.strip():
                    code = code.strip().upper()
            if code is None:
                code = _generate_project_code(info["name"], all_codes)
            all_codes.add(code)
            if code not in final_codes:
                final_codes.append(code)
        parent_data["routing_queue"] = final_codes

    final_queue: List[str] = list(parent_data.get("routing_queue") or [])

    # Build uninitialized list for output
    uninitialized_plugins = [
        {"name": info["name"], "root": str(info["root"])}
        for info in catalog["uninitialized"]
    ]

    return {
        "added_codes": added_codes,
        "uninitialized_plugins": uninitialized_plugins,
        "warnings": warnings,
        "final_queue": final_queue,
    }


# ---------------------------------------------------------------------------
# CLI command entry points
# ---------------------------------------------------------------------------


def discover_children(*, output_json: bool = False) -> bool:
    """Discover and register child trackers under a parent."""
    pm = _pm()
    project_root = pm.find_project_root()
    repo_root = _resolve_repo_root(project_root)

    data = pm.load_progress_json()
    if not isinstance(data, dict):
        msg = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    tracker_role = str(data.get("tracker_role") or DEFAULT_TRACKER_ROLE).strip().lower()
    if tracker_role != "parent":
        msg = "discover-children only runs from a parent tracker."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    result = _auto_discover_child_plugins(project_root, repo_root, data)

    pm._update_runtime_context(data, source="discover_children")
    pm.save_progress_json(data)
    pm.save_progress_md(pm.generate_progress_md(data))

    if output_json:
        payload = {
            "status": "ok",
            **result,
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Discovered {len(result['added_codes'])} new child plugin(s)")
        if result["added_codes"]:
            print(f"  Added: {', '.join(result['added_codes'])}")
        if result["uninitialized_plugins"]:
            names = [p["name"] for p in result["uninitialized_plugins"]]
            print(f"  Uninitialized: {', '.join(names)}")
        if result["warnings"]:
            for w in result["warnings"]:
                print(f"  [WARN] {w}")
        print(f"  Queue: {' -> '.join(result['final_queue'])}")

    return True


def route_status(*, output_json: bool = False) -> bool:
    """Display routing_queue, active_routes, and conflict summary."""
    pm = _pm()
    data = pm.load_progress_json()
    if not data:
        message = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    routing_queue: List[str] = data.get("routing_queue") or []
    if not isinstance(routing_queue, list):
        routing_queue = []

    active_routes: List[Any] = data.get("active_routes") or []
    if not isinstance(active_routes, list):
        active_routes = []

    linked_projects: List[Any] = data.get("linked_projects") or []
    if not isinstance(linked_projects, list):
        linked_projects = []

    # Collect linked project codes for conflict Type B check
    linked_codes: set = set()
    for entry in linked_projects:
        if isinstance(entry, dict):
            code_raw = entry.get("project_code")
            if isinstance(code_raw, str) and code_raw.strip():
                linked_codes.add(code_raw.strip().upper())

    # Detect conflicts
    conflicts: List[Dict[str, Any]] = []

    # Type A: duplicate project_code in active_routes
    seen_codes: Dict[str, int] = {}
    for route in active_routes:
        if not isinstance(route, dict):
            continue
        code_raw = route.get("project_code")
        if not isinstance(code_raw, str):
            continue
        code = code_raw.strip().upper()
        seen_codes[code] = seen_codes.get(code, 0) + 1
    for code, count in seen_codes.items():
        if count > 1:
            conflicts.append(
                {"type": "A", "code": code, "message": f"duplicate in active_routes ({count} entries)"}
            )

    # Type B: routing_queue code not in linked_projects (ROOT is exempt per CONSTRAINT-006)
    root_code = pm.ROOT_ROUTE_CODE
    for item in routing_queue:
        if not isinstance(item, str):
            continue
        code = item.strip().upper()
        if code and code != root_code and code not in linked_codes:
            conflicts.append(
                {"type": "B", "code": code, "message": f"{code} in routing_queue but not in linked_projects"}
            )

    # Type C: 2+ distinct project_codes in active_routes (parallel execution conflict) (F20)
    parallel_routes = _detect_parallel_active_routes(active_routes)
    if parallel_routes:
        codes = [str(r.get("project_code", "?")) for r in parallel_routes]
        conflicts.append(
            {"type": "C", "codes": codes, "message": f"parallel active routes: {', '.join(codes)}"}
        )

    if output_json:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "routing_queue": routing_queue,
                    "active_routes": active_routes,
                    "conflicts": conflicts,
                },
                ensure_ascii=False,
            )
        )
        return True

    print("Route Status")
    print("============")
    print(f"routing_queue: {routing_queue or '(empty)'}")
    print()
    if active_routes:
        print("active_routes:")
        for route in active_routes:
            if isinstance(route, dict):
                code = route.get("project_code", "?")
                ref = route.get("feature_ref") or "(no feature_ref)"
                print(f"  {code} -> {ref}")
    else:
        print("active_routes: (empty)")
    if conflicts:
        print()
        print("Conflicts:")
        for c in conflicts:
            print(f"  [{c['type']}] {c['message']}")
    return True


def prioritize_route(code: str, *, output_json: bool = False) -> bool:
    """Move a queue entry to the front of routing_queue.

    Validates that ``code`` is ``ROOT_ROUTE_CODE`` or an existing linked child code.
    """
    pm = _pm()
    data = pm.load_progress_json()
    if not isinstance(data, dict):
        msg = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    tracker_role = str(data.get("tracker_role") or "").strip().lower()
    if tracker_role != "parent":
        msg = "prioritize only runs from a parent tracker."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    routing_queue: List[str] = data.get("routing_queue") or []
    if not isinstance(routing_queue, list):
        routing_queue = []

    linked_projects: List[Any] = data.get("linked_projects") or []
    if not isinstance(linked_projects, list):
        linked_projects = []

    linked_codes: set = set()
    for entry in linked_projects:
        if isinstance(entry, dict):
            raw = entry.get("project_code")
            if isinstance(raw, str) and raw.strip():
                linked_codes.add(raw.strip().upper())

    normalized_code = code.strip().upper()
    root_code = pm.ROOT_ROUTE_CODE
    if normalized_code != root_code and normalized_code not in linked_codes:
        msg = f"Code '{code}' is not in routing_queue or linked_projects."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    if normalized_code not in routing_queue:
        msg = f"Code '{code}' is not in routing_queue."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    # Move to front, preserving order of remaining entries
    new_queue = [normalized_code] + [c for c in routing_queue if c != normalized_code]
    data["routing_queue"] = new_queue

    pm._update_runtime_context(data, source="prioritize_route")
    pm.save_progress_json(data)
    pm.save_progress_md(pm.generate_progress_md(data))

    if output_json:
        print(json.dumps({
            "status": "ok",
            "code": normalized_code,
            "routing_queue": new_queue,
        }, ensure_ascii=False))
    else:
        print(f"Prioritized {normalized_code}. Queue: {' -> '.join(new_queue)}")
    return True


def set_routing_queue(
    codes: List[str],
    *,
    force: bool = False,
    output_json: bool = False,
) -> bool:
    """Replace routing_queue with the provided ordered list of codes.

    Validates every code is ``ROOT_ROUTE_CODE`` or an existing linked child code.
    Requires all existing queue codes unless ``force`` is True.
    """
    pm = _pm()
    data = pm.load_progress_json()
    if not isinstance(data, dict):
        msg = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    tracker_role = str(data.get("tracker_role") or "").strip().lower()
    if tracker_role != "parent":
        msg = "set-queue only runs from a parent tracker."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    routing_queue: List[str] = data.get("routing_queue") or []
    if not isinstance(routing_queue, list):
        routing_queue = []

    linked_projects: List[Any] = data.get("linked_projects") or []
    if not isinstance(linked_projects, list):
        linked_projects = []

    linked_codes: set = set()
    for entry in linked_projects:
        if isinstance(entry, dict):
            raw = entry.get("project_code")
            if isinstance(raw, str) and raw.strip():
                linked_codes.add(raw.strip().upper())

    # Normalize input codes
    normalized_codes: List[str] = []
    for c in codes:
        if isinstance(c, str) and c.strip():
            normalized_codes.append(c.strip().upper())

    # Validate each code
    root_code = pm.ROOT_ROUTE_CODE
    invalid_codes = [c for c in normalized_codes if c != root_code and c not in linked_codes]
    if invalid_codes:
        msg = f"Invalid code(s): {', '.join(invalid_codes)}"
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    # Require all existing queue codes unless --force
    existing_set = set(routing_queue)
    new_set = set(normalized_codes)
    if not force and not existing_set.issubset(new_set):
        missing = sorted(existing_set - new_set)
        msg = (
            f"Missing existing queue code(s): {', '.join(missing)}. "
            "Use --force to replace the queue anyway."
        )
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    data["routing_queue"] = normalized_codes

    pm._update_runtime_context(data, source="set_routing_queue")
    pm.save_progress_json(data)
    pm.save_progress_md(pm.generate_progress_md(data))

    if output_json:
        print(json.dumps({
            "status": "ok",
            "routing_queue": normalized_codes,
        }, ensure_ascii=False))
    else:
        print(f"Queue set: {' -> '.join(normalized_codes)}")
    return True


def route_select(
    project_code: str,
    *,
    feature_ref: Optional[str] = None,
    output_json: bool = False,
) -> bool:
    """Upsert active_routes entry for project_code (unique key), merging duplicates."""
    pm = _pm()
    data = pm.load_progress_json()
    if not data:
        message = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    normalized_code = _normalize_project_code(project_code)
    if normalized_code is None:
        message = (
            "Error: Invalid --project value. Use 1-32 chars matching "
            "[A-Z][A-Z0-9_]* (example: NO, APP2, CORE_API)."
        )
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    active_routes: List[Any] = data.get("active_routes") or []
    if not isinstance(active_routes, list):
        active_routes = []

    # Collect existing entry for the target code (take first match for feature_ref preservation)
    existing_entry: Optional[Dict[str, Any]] = None
    other_routes: List[Any] = []
    for route in active_routes:
        if not isinstance(route, dict):
            other_routes.append(route)
            continue
        route_code_raw = route.get("project_code")
        route_code = (
            str(route_code_raw).strip().upper()
            if isinstance(route_code_raw, str) and route_code_raw.strip()
            else None
        )
        if route_code == normalized_code:
            if existing_entry is None:
                existing_entry = dict(route)
            # Skip duplicates — deduplication happens by writing only one entry below
        else:
            other_routes.append(route)

    # Determine final feature_ref
    if feature_ref is not None:
        final_ref = feature_ref
    elif existing_entry is not None:
        final_ref = existing_entry.get("feature_ref", "")
        if not isinstance(final_ref, str):
            final_ref = ""
    else:
        final_ref = ""

    upserted_entry: Dict[str, Any] = {"project_code": normalized_code, "feature_ref": final_ref}
    if existing_entry is not None:
        # Preserve extra fields (e.g. worktree_path, custom flags) from first match
        merged = dict(existing_entry)
        merged["project_code"] = normalized_code
        merged["feature_ref"] = final_ref
        upserted_entry = merged

    # Record current worktree_path and branch for scope consistency checks (F21)
    _git_ctx = pm.collect_git_context()
    upserted_entry["worktree_path"] = _git_ctx.get("worktree_path")
    upserted_entry["branch"] = _git_ctx.get("branch")

    new_routes = other_routes + [upserted_entry]
    data["active_routes"] = new_routes

    pm._update_runtime_context(data, source="route_select")
    pm.save_progress_json(data)
    pm.save_progress_md(pm.generate_progress_md(data))

    action = "updated" if existing_entry is not None else "inserted"
    parallel_routes = _detect_parallel_active_routes(new_routes)
    if output_json:
        result_payload: Dict[str, Any] = {
            "status": "ok",
            "project_code": normalized_code,
            "active_routes": new_routes,
        }
        if parallel_routes:
            result_payload["warning"] = "parallel_active_routes"
            result_payload["parallel_codes"] = [
                r.get("project_code") for r in parallel_routes
            ]
        print(json.dumps(result_payload, ensure_ascii=False))
    else:
        ref_display = final_ref or "(empty)"
        print(f"route-select: {action} {normalized_code} -> {ref_display}")
        if parallel_routes:
            codes_str = ", ".join(
                str(r.get("project_code", "?")) for r in parallel_routes
            )
            print(f"[WARNING] Parallel Active Routes detected: {codes_str}")
            print("  Multiple projects executing simultaneously. Run 'prog route-status' for details.")
    return True
