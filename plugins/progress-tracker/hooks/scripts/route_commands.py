"""
route_commands.py — Active routes CLI operations and preflight guards.

Extracted from progress_manager.py (F18 modularisation).
"""
import re
import json
import shlex
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Sequence, Tuple

import state_io
import route_sync
import git_utils
from prog_paths import resolve_repo_root

logger = logging.getLogger(__name__)

ROOT_ROUTE_CODE = "ROOT"
DEFAULT_TRACKER_ROLE = state_io.DEFAULT_TRACKER_ROLE
ROUTE_PREFLIGHT_EXEMPT_COMMANDS = {
    "init",
    "link-project",
    "route-select",
}


def _derive_plugin_code(plugin_name: str) -> str:
    """Derive a short project code from a plugin name."""
    segments = re.split(r"[-_]+", plugin_name.strip())
    code = "".join(seg[0].upper() for seg in segments if seg)
    return code[:8]


def _generate_project_code(plugin_name: str, used_codes: Set[str]) -> str:
    """Generate a unique project code, handling collisions."""
    base = _derive_plugin_code(plugin_name)
    if base not in used_codes:
        return base
    for suffix in range(2, 100):
        candidate = f"{base}{suffix}"[:8]
        if candidate not in used_codes:
            logger.warning(
                f"Code collision: derived '{base}' already used; "
                f"assigned '{candidate}' for plugin '{plugin_name}'"
            )
            return candidate
    for prefix_len in range(7, 3, -1):
        for suffix in range(2, 100):
            candidate = f"{base[:prefix_len]}{suffix}"
            if len(candidate) <= 8 and candidate not in used_codes:
                logger.warning(
                    f"Code collision exhausted for plugin '{plugin_name}'; "
                    f"using fallback '{candidate}'"
                )
                return candidate
    fallback = base[:6] + "XX"
    if fallback not in used_codes:
        return fallback
    raise ValueError(f"Cannot generate unique project code for '{plugin_name}'")


def _discover_plugin_catalog(
    repo_root: Path,
    parent_root: Path,
) -> Dict[str, List[Dict[str, Any]]]:
    """Scan repo_root/plugins/* for .claude-plugin/plugin.json."""
    plugins_dir = repo_root / "plugins"
    if not plugins_dir.is_dir():
        return {"initialized": [], "uninitialized": []}

    initialized: List[Dict[str, Any]] = []
    uninitialized: List[Dict[str, Any]] = []

    for child_dir in sorted(plugins_dir.iterdir()):
        if not child_dir.is_dir():
            continue
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

        tracker_file = child_dir / "docs" / "progress-tracker" / "state" / "progress.json"
        if tracker_file.is_file():
            initialized.append(entry)
        else:
            uninitialized.append(entry)

    return {"initialized": initialized, "uninitialized": uninitialized}


def _link_child_to_parent(
    parent_data: Dict[str, Any],
    parent_root: Path,
    repo_root: Path,
    child_root: Path,
    code: str,
    label: Optional[str] = None,
    append_to_queue: bool = True,
    child_wt_root: Optional[Path] = None,
    *,
    load_progress_payload_at_root_fn: Callable[[Path], Tuple[Optional[Dict[str, Any]], Optional[str]]],
    save_progress_payload_at_root_fn: Callable[[Path, Dict[str, Any]], None],
    resolve_main_repo_path_fn: Callable[[Path], Path],
) -> None:
    """Register a child tracker in the parent's linked_projects and queue."""
    normalized_code = route_sync._normalize_project_code(code) or code.upper()[:8]

    # Write child metadata
    child_data, _ = load_progress_payload_at_root_fn(child_root)
    if child_data is None and child_wt_root is not None and child_wt_root.resolve() != child_root.resolve():
        child_data, _ = load_progress_payload_at_root_fn(child_wt_root)
    if isinstance(child_data, dict):
        child_data["tracker_role"] = "child"
        child_data["project_code"] = normalized_code
        child_data["parent_project_root"] = route_sync._serialize_project_root_for_config(
            parent_root, repo_root, resolve_main_repo_path_fn=resolve_main_repo_path_fn
        )
        save_progress_payload_at_root_fn(child_root, child_data)

    if child_wt_root is not None and child_wt_root.resolve() != child_root.resolve():
        wt_child_data, _ = load_progress_payload_at_root_fn(child_wt_root)
        if isinstance(wt_child_data, dict):
            wt_child_data["tracker_role"] = "child"
            wt_child_data["project_code"] = normalized_code
            wt_child_data["parent_project_root"] = route_sync._serialize_project_root_for_config(
                parent_root, repo_root, resolve_main_repo_path_fn=resolve_main_repo_path_fn
            )
            save_progress_payload_at_root_fn(child_wt_root, wt_child_data)

    if label is None:
        child_name = child_data.get("project_name") if isinstance(child_data, dict) else None
        label = (
            child_name.strip()
            if isinstance(child_name, str) and child_name.strip()
            else child_root.name
        )
    normalized_label = label.strip() if isinstance(label, str) and label.strip() else child_root.name

    configured_project_root = route_sync._serialize_project_root_for_config(
        child_root, repo_root, resolve_main_repo_path_fn=resolve_main_repo_path_fn
    )

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
            route_sync._resolve_linked_project_root(entry_root_raw, parent_root, repo_root)
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
    *,
    load_progress_payload_at_root_fn: Callable[[Path], Tuple[Optional[Dict[str, Any]], Optional[str]]],
    save_progress_payload_at_root_fn: Callable[[Path, Dict[str, Any]], None],
    resolve_main_repo_path_fn: Callable[[Path], Path],
) -> Dict[str, Any]:
    """Discover and register initialized child trackers."""
    catalog = _discover_plugin_catalog(repo_root, parent_root=project_root)

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

        child_data, _ = load_progress_payload_at_root_fn(child_root)
        resolved_code = None
        if isinstance(child_data, dict):
            existing_code = child_data.get("project_code")
            if isinstance(existing_code, str) and existing_code.strip():
                resolved_code = existing_code.strip().upper()

        if resolved_code is None:
            resolved_code = _generate_project_code(plugin_name, used_codes)

        used_codes.add(resolved_code)

        already_linked = False
        for entry in existing_linked:
            if isinstance(entry, dict):
                entry_root_raw = entry.get("project_root") or entry.get("path") or entry.get("root")
                entry_root = (
                    route_sync._resolve_linked_project_root(str(entry_root_raw).strip(), project_root, repo_root)
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
                load_progress_payload_at_root_fn=load_progress_payload_at_root_fn,
                save_progress_payload_at_root_fn=save_progress_payload_at_root_fn,
                resolve_main_repo_path_fn=resolve_main_repo_path_fn,
            )
            added_codes.append(resolved_code)
        else:
            if isinstance(child_data, dict):
                child_data.setdefault("tracker_role", "child")
                child_data.setdefault("project_code", resolved_code)
                child_data.setdefault(
                    "parent_project_root",
                    route_sync._serialize_project_root_for_config(
                        project_root,
                        repo_root,
                        resolve_main_repo_path_fn=resolve_main_repo_path_fn,
                    ),
                )
                save_progress_payload_at_root_fn(child_root, child_data)

    if not existing_queue:
        all_codes: Set[str] = set()
        final_codes: List[str] = [ROOT_ROUTE_CODE]
        for info in catalog["initialized"]:
            child_data_tmp, _ = load_progress_payload_at_root_fn(info["root"])
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


def discover_children(
    *,
    project_root: Path,
    output_json: bool = False,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    load_progress_payload_at_root_fn: Callable[[Path], Tuple[Optional[Dict[str, Any]], Optional[str]]],
    save_progress_json_fn: Callable[[Dict[str, Any]], None],
    save_progress_md_fn: Callable[[str], None],
    generate_progress_md_fn: Callable[[Dict[str, Any]], str],
    update_runtime_context_fn: Callable[[Dict[str, Any], str], None],
    save_progress_payload_at_root_fn: Callable[[Path, Dict[str, Any]], None],
    resolve_main_repo_path_fn: Callable[[Path], Path],
) -> bool:
    """Discover and register child trackers under a parent."""
    repo_root = resolve_repo_root(cwd=project_root)

    data = load_progress_json_fn()
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

    result = _auto_discover_child_plugins(
        project_root,
        repo_root,
        data,
        load_progress_payload_at_root_fn=load_progress_payload_at_root_fn,
        save_progress_payload_at_root_fn=save_progress_payload_at_root_fn,
        resolve_main_repo_path_fn=resolve_main_repo_path_fn,
    )

    update_runtime_context_fn(data, "discover_children")
    save_progress_json_fn(data)
    save_progress_md_fn("")

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


def route_status(
    *,
    output_json: bool = False,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
) -> bool:
    """Display routing_queue, active_routes, and conflict summary."""
    data = load_progress_json_fn()
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

    linked_codes: set = set()
    for entry in linked_projects:
        if isinstance(entry, dict):
            code_raw = entry.get("project_code")
            if isinstance(code_raw, str) and code_raw.strip():
                linked_codes.add(code_raw.strip().upper())

    conflicts: List[Dict[str, Any]] = []

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

    for item in routing_queue:
        if not isinstance(item, str):
            continue
        code = item.strip().upper()
        if code and code != ROOT_ROUTE_CODE and code not in linked_codes:
            conflicts.append(
                {"type": "B", "code": code, "message": f"{code} in routing_queue but not in linked_projects"}
            )

    parallel_routes = route_sync._detect_parallel_active_routes(active_routes)
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


def prioritize_route(
    code: str,
    *,
    output_json: bool = False,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    save_progress_json_fn: Callable[[Dict[str, Any]], None],
    save_progress_md_fn: Callable[[str], None],
    generate_progress_md_fn: Callable[[Dict[str, Any]], str],
    update_runtime_context_fn: Callable[[Dict[str, Any], str], None],
) -> bool:
    """Move a queue entry to the front of routing_queue."""
    data = load_progress_json_fn()
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
    if normalized_code != ROOT_ROUTE_CODE and normalized_code not in linked_codes:
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

    new_queue = [normalized_code] + [c for c in routing_queue if c != normalized_code]
    data["routing_queue"] = new_queue

    update_runtime_context_fn(data, "prioritize_route")
    save_progress_json_fn(data)
    save_progress_md_fn("")

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
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    save_progress_json_fn: Callable[[Dict[str, Any]], None],
    save_progress_md_fn: Callable[[str], None],
    generate_progress_md_fn: Callable[[Dict[str, Any]], str],
    update_runtime_context_fn: Callable[[Dict[str, Any], str], None],
) -> bool:
    """Replace routing_queue with the provided ordered list of codes."""
    data = load_progress_json_fn()
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

    normalized_codes: List[str] = []
    for c in codes:
        if isinstance(c, str) and c.strip():
            normalized_codes.append(c.strip().upper())

    invalid_codes = [c for c in normalized_codes if c != ROOT_ROUTE_CODE and c not in linked_codes]
    if invalid_codes:
        msg = f"Invalid code(s): {', '.join(invalid_codes)}"
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

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

    update_runtime_context_fn(data, "set_routing_queue")
    save_progress_json_fn(data)
    save_progress_md_fn("")

    if output_json:
        print(json.dumps({
            "status": "ok",
            "routing_queue": normalized_codes,
        }, ensure_ascii=False))
    else:
        print(f"Queue set: {' -> '.join(normalized_codes)}")
    return True


def _resolve_repo_root(project_root: Path) -> Path:
    """Resolve the git repo root from the project root."""
    return resolve_repo_root(cwd=project_root)


def route_select(
    project_code: str,
    *,
    project_root: Path,
    feature_ref: Optional[str] = None,
    output_json: bool = False,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    save_progress_json_fn: Callable[[Dict[str, Any]], None],
    save_progress_md_fn: Callable[[str], None],
    generate_progress_md_fn: Callable[[Dict[str, Any]], str],
    update_runtime_context_fn: Callable[[Dict[str, Any], str], None],
    collect_git_context_fn: Callable[[], Dict[str, Any]],
) -> bool:
    """Upsert active_routes entry for project_code (unique key), merging duplicates."""
    data = load_progress_json_fn()
    if not data:
        message = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    normalized_code = route_sync._normalize_project_code(project_code)
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
        else:
            other_routes.append(route)

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
        merged = dict(existing_entry)
        merged["project_code"] = normalized_code
        merged["feature_ref"] = final_ref
        upserted_entry = merged

    _git_ctx = collect_git_context_fn()
    upserted_entry["worktree_path"] = _git_ctx.get("worktree_path")
    upserted_entry["branch"] = _git_ctx.get("branch")

    new_routes = other_routes + [upserted_entry]
    data["active_routes"] = new_routes

    update_runtime_context_fn(data, "route_select")
    save_progress_json_fn(data)
    save_progress_md_fn("")

    action = "updated" if existing_entry is not None else "inserted"
    parallel_routes = route_sync._detect_parallel_active_routes(new_routes)
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


def _discover_parent_route_bindings_for_child(
    child_project_root: Path,
    repo_root: Path,
    *,
    resolve_main_repo_path_fn: Callable[[Path], Path],
) -> List[Dict[str, Any]]:
    """Discover parent trackers that link to the given child tracker root."""
    candidate_roots: List[Path] = [repo_root]
    plugins_dir = repo_root / "plugins"
    if plugins_dir.is_dir():
        candidate_roots.extend(sorted(path for path in plugins_dir.iterdir() if path.is_dir()))

    discovered: List[Dict[str, Any]] = []
    seen_roots: Set[Path] = set()
    child_resolved = child_project_root.resolve()
    repo_resolved = repo_root.resolve()

    for candidate_root in candidate_roots:
        resolved_root = candidate_root.resolve()
        if resolved_root in seen_roots or resolved_root == child_resolved:
            continue
        seen_roots.add(resolved_root)

        payload, _ = route_sync._load_progress_payload_at_root(resolved_root, apply_schema_defaults_fn=state_io._apply_schema_defaults_core)
        if not isinstance(payload, dict):
            continue
        state_io._normalize_route_schema(payload)
        tracker_role = str(payload.get("tracker_role") or DEFAULT_TRACKER_ROLE).strip().lower()
        if tracker_role != "parent":
            continue

        matched_entry: Optional[Dict[str, Any]] = None
        for spec in route_sync._iter_linked_project_specs(payload):
            linked_root = route_sync._resolve_linked_project_root(
                spec["raw_project_root"],
                resolved_root,
                repo_resolved,
            )
            if linked_root == child_resolved or resolve_main_repo_path_fn(linked_root) == resolve_main_repo_path_fn(child_resolved):
                entry = spec.get("entry")
                matched_entry = entry if isinstance(entry, dict) else {}
                break

        if matched_entry is None:
            continue

        active_routes = payload.get("active_routes")
        if not isinstance(active_routes, list):
            active_routes = []

        discovered.append(
            {
                "project_root": resolved_root,
                "linked_entry": matched_entry,
                "active_routes": active_routes,
            }
        )

    return discovered


def _print_route_preflight_block(
    *,
    reason: str,
    command: str,
    argv: Sequence[str],
    child_project_root: Path,
    repo_root: Path,
    child_code: Optional[str],
    parent_project_root: Optional[Path],
    extract_command_tail_fn: Callable[[Sequence[str], str], Sequence[str]],
    scope_hint_fn: Callable[[Path, Path], str],
) -> None:
    """Print deterministic route preflight recovery guidance."""
    command_tail = extract_command_tail_fn(argv, command)
    command_tail_text = " ".join(shlex.quote(token) for token in command_tail) if command_tail else command
    child_scope = shlex.quote(scope_hint_fn(child_project_root, repo_root))
    code_hint = child_code or "<PROJECT_CODE>"

    print(f"[Route Preflight] BLOCKED: {reason}")
    print(f"Current tracker: {child_project_root}")
    if parent_project_root is not None:
        print(f"Detected parent tracker: {parent_project_root}")

    print("Recovery:")
    print(f"  cd {repo_root}")
    if parent_project_root is None:
        print(
            '  # Identify parent tracker root: directory whose progress.json has tracker_role="parent"'
        )
        print(
            "  plugins/progress-tracker/prog "
            f"--project-root {child_scope} link-project --code {code_hint} "
            "--parent-root <parent_tracker_root>"
        )
        print(
            "  plugins/progress-tracker/prog --project-root <parent_tracker_root> "
            f"route-select --project {code_hint} --feature-ref {code_hint}-F<number>"
        )
    else:
        parent_scope = shlex.quote(scope_hint_fn(parent_project_root, repo_root))
        print(
            "  plugins/progress-tracker/prog "
            f"--project-root {parent_scope} route-select --project {code_hint} "
            f"--feature-ref {code_hint}-F<number>"
        )
    print(f"  cd {child_project_root}")
    print(
        "  plugins/progress-tracker/prog "
        f"--project-root {child_scope} {command_tail_text}"
    )


def enforce_route_preflight(
    command: str,
    argv: Sequence[str],
    *,
    project_root: Path,
    repo_root: Path,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    resolve_main_repo_path_fn: Callable[[Path], Path],
    extract_command_tail_fn: Callable[[Sequence[str], str], Sequence[str]],
    scope_hint_fn: Callable[[Path, Path], str],
) -> bool:
    """Fail-closed preflight for child tracker mutating commands."""
    if command in ROUTE_PREFLIGHT_EXEMPT_COMMANDS:
        return True

    data = load_progress_json_fn()
    if not isinstance(data, dict):
        return True

    tracker_role = str(data.get("tracker_role") or DEFAULT_TRACKER_ROLE).strip().lower()
    if tracker_role != "child":
        return True

    child_project_root = project_root.resolve()
    effective_repo_root = repo_root.resolve()
    child_code_raw = data.get("project_code")
    child_code = route_sync._normalize_project_code(child_code_raw) if isinstance(child_code_raw, str) else None

    parent_bindings = _discover_parent_route_bindings_for_child(
        child_project_root=child_project_root,
        repo_root=effective_repo_root,
        resolve_main_repo_path_fn=resolve_main_repo_path_fn,
    )

    if child_code is None:
        _print_route_preflight_block(
            reason="Child tracker has no project_code; route ownership cannot be verified.",
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=effective_repo_root,
            child_code=None,
            parent_project_root=parent_bindings[0]["project_root"] if parent_bindings else None,
            extract_command_tail_fn=extract_command_tail_fn,
            scope_hint_fn=scope_hint_fn,
        )
        return False

    if not parent_bindings:
        _print_route_preflight_block(
            reason=(
                f"Child project_code={child_code} is not registered in any parent linked_projects. "
                "Mutating command denied."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=effective_repo_root,
            child_code=child_code,
            parent_project_root=None,
            extract_command_tail_fn=extract_command_tail_fn,
            scope_hint_fn=scope_hint_fn,
        )
        return False

    if len(parent_bindings) > 1:
        _print_route_preflight_block(
            reason=(
                f"Child project_code={child_code} is linked by multiple parent trackers "
                f"({len(parent_bindings)} matches). Mutating command denied until routing is unambiguous."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=effective_repo_root,
            child_code=child_code,
            parent_project_root=parent_bindings[0]["project_root"],
            extract_command_tail_fn=extract_command_tail_fn,
            scope_hint_fn=scope_hint_fn,
        )
        return False

    parent_binding = parent_bindings[0]
    parent_project_root = parent_binding["project_root"]
    linked_entry = parent_binding.get("linked_entry", {})
    linked_code_raw = linked_entry.get("project_code") if isinstance(linked_entry, dict) else None
    linked_code = route_sync._normalize_project_code(linked_code_raw) if isinstance(linked_code_raw, str) else None
    if linked_code is not None and linked_code != child_code:
        _print_route_preflight_block(
            reason=(
                f"Parent registration mismatch: child reports {child_code}, "
                f"but parent linked_projects expects {linked_code}."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=effective_repo_root,
            child_code=child_code,
            parent_project_root=parent_project_root,
            extract_command_tail_fn=extract_command_tail_fn,
            scope_hint_fn=scope_hint_fn,
        )
        return False

    active_route_codes: List[str] = []
    for route in parent_binding.get("active_routes", []):
        if not isinstance(route, dict):
            continue
        route_code_raw = route.get("project_code")
        if not isinstance(route_code_raw, str):
            continue
        route_code = route_sync._normalize_project_code(route_code_raw)
        if route_code is not None:
            active_route_codes.append(route_code)

    if child_code not in active_route_codes:
        if command == "set-current" and not active_route_codes:
            print(
                f"[WARNING] Route preflight bootstrap: {child_code} not in parent "
                "active_routes (empty). Allowing set-current to bootstrap the route entry."
            )
            return True

        active_display = ", ".join(sorted(set(active_route_codes))) if active_route_codes else "(none)"
        _print_route_preflight_block(
            reason=(
                f"Parent active route mismatch: expected {child_code}, current active routes: {active_display}. "
                "Mutating command denied."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=effective_repo_root,
            child_code=child_code,
            parent_project_root=parent_project_root,
            extract_command_tail_fn=extract_command_tail_fn,
            scope_hint_fn=scope_hint_fn,
        )
        return False

    return True
