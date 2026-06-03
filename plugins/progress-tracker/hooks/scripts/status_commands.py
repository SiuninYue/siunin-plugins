"""
status_commands.py — Status display commands.

Extracted from progress_manager.py (F20 Round 1 modularisation).

This module owns the status/display command cluster:
- _build_status_handoff_block
- _display_root_dashboard
- _get_stale_bugs
- status

All progress_manager-owned helpers that cannot be imported directly are
injected via a StatusCommandServices dataclass.  Submodule imports (route_commands,
route_sync, git_utils, progress_prompt_builders, summary_projector) are used directly.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import doc_generator
import progress_prompt_builders
import route_commands
import route_sync
import git_utils
import worktree_handler
from state_io import DEFAULT_TRACKER_ROLE, compare_contexts

from summary_projector import (
    load_status_summary_projection as _load_summary_projection_impl,
    _format_relative_time_for_summary,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Injected-services container
# ---------------------------------------------------------------------------

@dataclass
class StatusCommandServices:
    """Bundle of callbacks injected from progress_manager to avoid reverse deps."""

    # Core data access
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    find_project_root_fn: Callable[[], Path]
    load_checkpoints_fn: Callable[..., Dict[str, Any]]

    # Summary projection callbacks (forwarded into summary_projector)
    apply_schema_defaults_fn: Callable[[Dict[str, Any]], None]
    validate_plan_path_fn: Callable[..., Dict[str, Any]]
    validate_plan_document_fn: Callable[..., Dict[str, Any]]

    # Per-data helpers that remain in progress_manager
    analyze_reconcile_state_fn: Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]
    load_progress_history_fn: Callable[[], List[Dict[str, Any]]]
    collect_git_context_fn: Callable[[], Dict[str, Any]]


# ---------------------------------------------------------------------------
# _build_status_handoff_block
# ---------------------------------------------------------------------------

def _build_status_handoff_block(
    data: Dict[str, Any],
    completed: int,
    total: int,
    project_root: str,
    *,
    services: StatusCommandServices,
) -> Optional[str]:
    """Build context handoff block for /prog status output."""
    git_ctx = services.collect_git_context_fn()
    current_branch = git_ctx.get("branch")
    return progress_prompt_builders.build_status_handoff_block(
        data, completed, total, project_root, current_branch=current_branch
    )


# ---------------------------------------------------------------------------
# _display_root_dashboard
# ---------------------------------------------------------------------------

def _display_root_dashboard(
    data: Dict[str, Any],
    project_root: Path,
    repo_root: Path,
    *,
    services: StatusCommandServices,
    output_json: bool = False,
) -> bool:
    """Render monorepo root dashboard by pulling child summaries.

    Uses ``load_status_summary_projection()`` for initialized children,
    falls back to ``linked_snapshot`` entries when summary loading fails,
    and renders ``-- not initialized --`` for uninitialized plugins.
    """
    catalog = route_commands._discover_plugin_catalog(repo_root, parent_root=project_root)

    # Build code -> linked_snapshot entry lookup for fallback
    linked_snapshot = data.get("linked_snapshot")
    snapshot_projects: List[Dict[str, Any]] = []
    if isinstance(linked_snapshot, dict):
        snapshot_projects = linked_snapshot.get("projects") or []
        if not isinstance(snapshot_projects, list):
            snapshot_projects = []
    snapshot_by_code: Dict[str, Dict[str, Any]] = {}
    for sp in snapshot_projects:
        if isinstance(sp, dict):
            code = sp.get("project_code")
            if isinstance(code, str) and code.strip():
                snapshot_by_code[code.strip().upper()] = sp

    # Build code -> linked_projects entry for name/label resolution
    linked_projects = data.get("linked_projects") or []
    if not isinstance(linked_projects, list):
        linked_projects = []
    linked_by_root: Dict[str, Dict[str, Any]] = {}
    for lp in linked_projects:
        if isinstance(lp, dict):
            raw_root = lp.get("project_root") or lp.get("path") or lp.get("root")
            if raw_root:
                resolved = route_sync._resolve_linked_project_root(
                    str(raw_root).strip(), project_root, repo_root
                )
                linked_by_root[str(resolved)] = lp

    # Active routes
    active_routes_raw: List[Any] = data.get("active_routes") or []
    active_routes_map: Dict[str, Dict[str, Any]] = {}
    for route in active_routes_raw:
        if isinstance(route, dict):
            code = route.get("project_code")
            if isinstance(code, str) and code.strip():
                active_routes_map[code.strip().upper()] = route

    # --- Build child rows ---
    child_rows: List[Dict[str, Any]] = []
    uninitialized_rows: List[Dict[str, Any]] = []

    for child_info in catalog["initialized"]:
        child_root = child_info["root"]
        plugin_name = child_info["name"]

        # Resolve code from linked_projects or child payload
        code = None
        lp_entry = linked_by_root.get(str(child_root))
        if isinstance(lp_entry, dict):
            raw_code = lp_entry.get("project_code")
            if isinstance(raw_code, str) and raw_code.strip():
                code = raw_code.strip().upper()

        if code is None:
            child_data, _ = route_sync._load_progress_payload_at_root(
                child_root,
                apply_schema_defaults_fn=services.apply_schema_defaults_fn,
            )
            if isinstance(child_data, dict):
                raw_code = child_data.get("project_code")
                if isinstance(raw_code, str) and raw_code.strip():
                    code = raw_code.strip().upper()

        if code is None:
            code = route_commands._generate_project_code(
                plugin_name,
                set(r.get("code", "") for r in child_rows if r.get("code")),
            )

        # Load summary via projection loader
        summary: Optional[Dict[str, Any]] = None
        summary_err: Optional[str] = None
        try:
            summary = _load_summary_projection_impl(
                str(child_root),
                apply_schema_defaults_fn=services.apply_schema_defaults_fn,
                load_checkpoints_fn=services.load_checkpoints_fn,
                validate_plan_path_fn=services.validate_plan_path_fn,
                validate_plan_document_fn=services.validate_plan_document_fn,
            )
        except Exception as exc:
            summary_err = str(exc)

        if summary and isinstance(summary, dict):
            progress = summary.get("progress", {})
            completed = progress.get("completed", 0) if isinstance(progress, dict) else 0
            total = progress.get("total", 0) if isinstance(progress, dict) else 0
            percentage = progress.get("percentage", 0) if isinstance(progress, dict) else 0
            next_action = summary.get("next_action", {})
            next_name = ""
            if isinstance(next_action, dict):
                if next_action.get("type") == "feature":
                    next_name = next_action.get("feature_name", "")
                else:
                    next_name = next_action.get("message", "")
            status_text = "(complete)" if completed >= total and total > 0 else (next_name or "--")
        else:
            # Fallback to linked_snapshot
            sp = snapshot_by_code.get(code)
            if sp:
                completed = sp.get("completed", 0)
                total = sp.get("total", 0)
                rate = sp.get("completion_rate", 0.0)
                percentage = int(rate * 100)
                active_ref = sp.get("active_feature_ref")
                status_text = active_ref if active_ref else "(snapshot fallback)"
            else:
                completed = 0
                total = 0
                percentage = 0
                status_text = "(unreachable)"
            if summary_err:
                logger.debug(f"Summary load failed for {code}: {summary_err}")

        route = active_routes_map.get(code)
        active_marker = " *" if route else ""

        child_rows.append({
            "code": code,
            "name": plugin_name,
            "completed": completed,
            "total": total,
            "percentage": percentage,
            "status_text": status_text + active_marker,
            "active": route is not None,
        })

    for child_info in catalog["uninitialized"]:
        uninitialized_rows.append({
            "code": "--",
            "name": child_info["name"],
            "completed": 0,
            "total": 0,
            "percentage": 0,
            "status_text": "-- not initialized --",
            "active": False,
        })

    # --- Root features ---
    features = data.get("features", [])
    if not isinstance(features, list):
        features = []
    feature_items = [f for f in features if isinstance(f, dict)]
    root_completed = sum(1 for f in feature_items if f.get("completed", False))
    root_total = len(feature_items)
    root_pending = [f for f in feature_items if not f.get("completed", False)]

    # --- Active route and queue ---
    routing_queue: List[str] = data.get("routing_queue") or []

    active_route_code = None
    active_feature_name = None
    for code, route in active_routes_map.items():
        active_route_code = code
        ref = route.get("feature_ref") or route.get("feature_name")
        if ref:
            active_feature_name = ref
        break

    if output_json:
        payload: Dict[str, Any] = {
            "status": "ok",
            "dashboard_type": "monorepo",
            "project_name": data.get("project_name", "Unknown"),
            "children": [
                {
                    "code": r["code"],
                    "plugin_name": r["name"],
                    "completed": r["completed"],
                    "total": r["total"],
                    "percentage": r["percentage"],
                    "next_action": r["status_text"].rstrip(" *"),
                    "active": r["active"],
                }
                for r in child_rows
            ],
            "uninitialized_plugins": [
                {"plugin_name": r["name"], "status": r["status_text"]}
                for r in uninitialized_rows
            ],
            "root_features": {
                "completed": root_completed,
                "total": root_total,
                "pending": [
                    {"id": f.get("id"), "name": f.get("name")}
                    for f in root_pending
                ],
            },
            "active_route": {
                "project_code": active_route_code,
                "feature_ref": active_feature_name,
            } if active_route_code else None,
            "queue": [str(c) for c in routing_queue],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return True

    # --- Text output ---
    print("\n## Monorepo Dashboard")
    print("")
    print("| Code | Plugin           | Done  | Pct  | Next Action    |")
    print("|------|------------------|-------|------|----------------|")
    for r in child_rows:
        pct_str = f"{r['percentage']}%"
        done_str = f"{r['completed']}/{r['total']}"
        print(f"| {r['code']:<4} | {r['name']:<16} | {done_str:>5} | {pct_str:>4} | {r['status_text']:<14} |")
    for r in uninitialized_rows:
        print(f"| {r['code']:<4} | {r['name']:<16} | {r['completed']:>5} | {r['percentage']:>4}% | {r['status_text']:<14} |")

    if root_total > 0 or root_pending:
        print(f"\nRoot Features: {root_completed}/{root_total} completed")
        for f in root_pending:
            print(f"  [ ] {f.get('name', 'Unknown')}")

    queue_str = " -> ".join(str(c) for c in routing_queue) if routing_queue else "(empty)"
    n_active = len(active_routes_raw)

    if n_active == 0:
        print(f"\nActive Route: none  |  Queue: {queue_str}")
    elif n_active == 1:
        route = active_routes_raw[0] if isinstance(active_routes_raw[0], dict) else {}
        code = route.get("project_code") or active_route_code or "?"
        ref = route.get("feature_ref") or route.get("feature_name") or active_feature_name or "?"
        print(f"\nActive Route: {code} -> {ref}  |  Queue: {queue_str}")
        print(f"→ Resume: /prog next  (routes to {code} active feature)")
    else:
        print(f"\nActive Routes ({n_active} parallel — WARNING):")
        for route in active_routes_raw:
            if not isinstance(route, dict):
                continue
            c = route.get("project_code") or "?"
            r = route.get("feature_ref") or route.get("feature_name") or "?"
            print(f"  {c} -> {r}")
        first_code = (
            active_routes_raw[0].get("project_code")
            if isinstance(active_routes_raw[0], dict)
            else "?"
        ) or "?"
        print(f"RecommendedRoute: {first_code}  |  Queue: {queue_str}")

    return True


# ---------------------------------------------------------------------------
# _get_stale_bugs
# ---------------------------------------------------------------------------

def _get_stale_bugs(data: dict, now: datetime) -> List[dict]:
    """Return P0/P1 bugs exceeding their stale threshold.

    Thresholds (strict >): P0 (priority=high) => 3 days; P1 (priority=medium) => 7 days.
    Excludes: fixed, false_positive. Time base: updated_at preferred, fallback created_at.
    Output: P0 first, then P1; same priority sorted by stale_days descending.
    """
    THRESHOLDS = {"high": 3, "medium": 7}
    TERMINAL = {"fixed", "false_positive"}

    result = []
    for bug in data.get("bugs") or []:
        if not isinstance(bug, dict):
            continue
        priority = bug.get("priority", "low")
        if priority not in THRESHOLDS:
            continue
        if bug.get("status") in TERMINAL:
            continue
        raw_ts = bug.get("updated_at") or bug.get("created_at")
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(raw_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.warning(f"Skipping bug {bug.get('id')}: unparseable timestamp {raw_ts!r}")
            continue
        stale_days = (now - ts).total_seconds() / 86400
        if stale_days > THRESHOLDS[priority]:
            result.append({**bug, "_stale_days": stale_days, "_priority": priority})

    def _sort_key(b):
        tier = 0 if b["_priority"] == "high" else 1
        return (tier, -b["_stale_days"])

    result.sort(key=_sort_key)
    return result


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def status(
    *,
    services: StatusCommandServices,
    output_json: bool = False,
) -> bool:
    """Display current progress status."""
    data = services.load_progress_json_fn()
    if not data:
        msg = "No progress tracking found. Use '/prog init' to start tracking."
        if output_json:
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return False

    # Parent tracker: route to root dashboard (CONSTRAINT-004)
    tracker_role = str(data.get("tracker_role") or DEFAULT_TRACKER_ROLE).strip().lower()
    if tracker_role == "parent":
        project_root = services.find_project_root_fn()
        repo_root = route_commands._resolve_repo_root(project_root)
        return _display_root_dashboard(
            data, project_root, repo_root, services=services, output_json=output_json
        )

    project_name = data.get("project_name", "Unknown")
    features = data.get("features", [])
    current_id = data.get("current_feature_id")
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}
    runtime_context = data.get("runtime_context")
    summary = _load_summary_projection_impl(
        apply_schema_defaults_fn=services.apply_schema_defaults_fn,
        load_checkpoints_fn=services.load_checkpoints_fn,
        validate_plan_path_fn=services.validate_plan_path_fn,
        validate_plan_document_fn=services.validate_plan_document_fn,
    )
    summary_progress = summary.get("progress", {})
    summary_next_action = summary.get("next_action", {})
    summary_plan_health = summary.get("plan_health", {})
    summary_risk = summary.get("risk_blocker", {})
    summary_snapshot = summary.get("recent_snapshot", {})

    # Calculate statistics
    total = summary_progress.get("total")
    completed = summary_progress.get("completed")
    percentage = summary_progress.get("percentage")
    if not isinstance(total, int):
        total = len(features)
    if not isinstance(completed, int):
        completed = sum(
            1 for f in features if isinstance(f, dict) and f.get("completed", False)
        )
    if not isinstance(percentage, int):
        percentage = completed * 100 // total if total > 0 else 0
    in_progress = current_id is not None
    deferred_count = sum(
        1
        for f in features
        if isinstance(f, dict)
        and not f.get("completed", False)
        and f.get("id") != current_id
        and worktree_handler._is_feature_deferred(f)
    )

    print(f"\n## Project: {project_name}")
    print(f"**Status**: {completed}/{total} completed ({percentage}%)")
    plan_status = summary_plan_health.get("status", "N/A")
    plan_message = summary_plan_health.get("message", "无活跃计划")
    risk_message = summary_risk.get("message", "正常")
    snapshot_text = summary_snapshot.get("relative_time", "暂无快照")
    print(f"**Plan Health**: {plan_status} ({plan_message})")
    print(f"**Risk/Blocker**: {risk_message}")
    print(f"**Recent Snapshot**: {snapshot_text}")
    if isinstance(summary_next_action, dict) and summary_next_action.get("type") == "feature":
        next_name = summary_next_action.get("feature_name", "Unknown")
        next_stage = summary_next_action.get("stage_label")
        if next_stage:
            print(f"**Summary Next**: {next_name} ({next_stage})")
        else:
            print(f"**Summary Next**: {next_name}")
    if deferred_count > 0:
        print(f"**Deferred Pending**: {deferred_count}")

    if current_id is not None:
        current_feature = next((f for f in features if f.get("id") == current_id), None)
        if current_feature:
            print(
                f"**Current Feature**: {current_feature.get('name', 'Unknown')} (in progress)"
            )
            if workflow_state:
                phase = workflow_state.get("phase", "unknown")
                current_task = workflow_state.get("current_task")
                total_tasks = workflow_state.get("total_tasks")
                next_action = workflow_state.get("next_action")
                print(f"**Workflow Phase**: {phase}")
                if current_task is not None or total_tasks is not None:
                    task_progress = f"{current_task if current_task is not None else '?'}"
                    if total_tasks is not None:
                        task_progress += f"/{total_tasks}"
                    print(f"**Task Progress**: {task_progress}")
                if next_action:
                    print(f"**Next Action**: {next_action}")

                execution_context = workflow_state.get("execution_context")
                if execution_context:
                    print(
                        f"**Execution Context**: "
                        f"{git_utils._format_context_summary(execution_context)}"
                    )
                if runtime_context:
                    print(
                        f"**Current Session Context**: "
                        f"{git_utils._format_context_summary(runtime_context)}"
                    )

                context_hint = compare_contexts(execution_context, runtime_context)
                if context_hint.get("status") in {
                    "mismatch",
                    "path_mismatch",
                    "branch_mismatch",
                }:
                    print(
                        "**Context Warning**: "
                        f"{context_hint.get('message')} "
                        f"(expected {context_hint.get('expected_branch') or '?'} @ "
                        f"{context_hint.get('expected_worktree_path') or '?'})"
                    )

    reconcile_report = services.analyze_reconcile_state_fn(data)
    if reconcile_report.get("diagnosis") != "in_sync":
        print(
            f"**Reality Check**: {reconcile_report.get('diagnosis')} "
            f"→ {reconcile_report.get('recommended_next_step')}"
        )
        print(f"**Reality Note**: {reconcile_report.get('reason')}")

    # Display features
    if completed > 0:
        print("\n### Completed:")
        for f in features:
            if f.get("completed", False):
                print(f"  [x] {f.get('name', 'Unknown')}")
                owner_summary = doc_generator._format_feature_owners(f)
                if owner_summary:
                    print(f"     Owners: {owner_summary}")

    if in_progress:
        print("\n### In Progress:")
        for f in features:
            if f.get("id") == current_id:
                print(f"  [*] {f.get('name', 'Unknown')}")
                owner_summary = doc_generator._format_feature_owners(f)
                if owner_summary:
                    print(f"     Owners: {owner_summary}")
                test_steps = f.get("test_steps", [])
                if test_steps:
                    print("     Test steps:")
                    for step in test_steps:
                        print(f"       - {step}")

    deferred = [
        f
        for f in features
        if isinstance(f, dict)
        and not f.get("completed", False)
        and f.get("id") != current_id
        and worktree_handler._is_feature_deferred(f)
    ]
    remaining = [
        f
        for f in features
        if isinstance(f, dict)
        and not f.get("completed", False)
        and f.get("id") != current_id
        and not worktree_handler._is_feature_deferred(f)
    ]
    if remaining:
        print("\n### Pending:")
        for f in remaining:
            print(f"  [ ] {f.get('name', 'Unknown')}")
            owner_summary = doc_generator._format_feature_owners(f)
            if owner_summary:
                print(f"     Owners: {owner_summary}")

    if deferred:
        print("\n### Deferred:")
        for f in deferred:
            defer_reason = f.get("defer_reason") or "No reason provided"
            defer_group = f.get("defer_group")
            defer_line = f"  [~] {f.get('name', 'Unknown')} — {defer_reason}"
            if defer_group:
                defer_line += f" (group: {defer_group})"
            print(defer_line)

    # Stale P0/P1 bug warnings
    stale_bugs = _get_stale_bugs(data, datetime.now(tz=timezone.utc))
    if stale_bugs:
        print("\n### Bug Warnings:")
        for bug in stale_bugs:
            tier = "P0" if bug.get("_priority") == "high" else "P1"
            desc = (bug.get("description") or "")[:60]
            days = int(bug.get("_stale_days", 0))
            raw_ts = bug.get("updated_at") or bug.get("created_at") or ""
            last_date = raw_ts[:10] if raw_ts else "unknown"
            print(f"  [{tier}] {bug.get('id')}: {desc} (stale {days}d, last: {last_date})")

    updates = data.get("updates", [])
    if updates:
        # Sort ascending by created_at before slicing so [-5:] gets the most recent 5.
        def _upd_ts(u):
            return u.get("created_at") or ""
        sorted_updates = sorted(updates, key=_upd_ts)
        shown = sorted_updates[-5:]
        total_count = len(updates)
        hidden = total_count - len(shown)
        print(f"\n### Recent Updates (showing {len(shown)}/{total_count}):")
        for update in shown:
            line = (
                f"  [{update.get('id', 'UPD-???')}] "
                f"{update.get('category', 'status')}: {update.get('summary', '')}"
            )
            if update.get("feature_id") is not None:
                line += f" (feature:{update['feature_id']})"
            if update.get("role") and update.get("owner"):
                line += f" [{update['role']}={update['owner']}]"
            print(line)
        if hidden > 0:
            print(f"  +{hidden} more updates (run: prog list-updates)")

    if deferred and not remaining and not in_progress:
        print(
            "\nUse `prog resume --all` or `prog resume --defer-group <group>` "
            "to continue deferred features."
        )

    # Display linked projects matrix
    linked_snapshot = data.get("linked_snapshot")
    if isinstance(linked_snapshot, dict):
        linked_projects_list = linked_snapshot.get("projects")
        if isinstance(linked_projects_list, list) and linked_projects_list:
            linked_updated_at = linked_snapshot.get("updated_at")
            snapshot_age = (
                f" (snapshot: {_format_relative_time_for_summary(linked_updated_at)})"
                if linked_updated_at
                else ""
            )
            print(f"\n### Linked Projects{snapshot_age}:")
            for proj in linked_projects_list:
                proj_name = proj.get("project_name") or proj.get("project_root", "Unknown")
                proj_status = proj.get("status", "unknown")
                completed_n = proj.get("completed", 0)
                total_n = proj.get("total", 0)
                rate = proj.get("completion_rate", 0.0)
                pct = int(rate * 100)
                stale_marker = " [stale]" if proj.get("is_stale") else ""
                active_feature_ref = proj.get("active_feature_ref")
                active_marker = f" | active: {active_feature_ref}" if active_feature_ref else ""
                updated = proj.get("updated_at")
                updated_str = (
                    f" | {_format_relative_time_for_summary(updated)}" if updated else ""
                )
                if proj_status == "ok":
                    print(
                        f"  [{proj_name}] {completed_n}/{total_n} ({pct}%)"
                        f"{active_marker}{stale_marker}{updated_str}"
                    )
                elif proj_status == "missing":
                    print(f"  [{proj_name}] missing{stale_marker}")
                else:
                    print(f"  [{proj_name}] {proj_status}{stale_marker}")

    # Display parallel active_routes conflict warning (F20)
    active_routes_raw: List[Any] = data.get("active_routes") or []
    parallel_routes = route_sync._detect_parallel_active_routes(active_routes_raw)
    if parallel_routes:
        print("\n### [WARNING] Parallel Active Routes:")
        for route in parallel_routes:
            code = route.get("project_code", "?")
            ref = route.get("feature_ref") or "(no feature_ref)"
            print(f"  {code} -> {ref}")
        print(
            "  Multiple projects executing simultaneously — "
            "run 'prog route-status' for details."
        )

    # Display archive history summary
    history = services.load_progress_history_fn()
    if history:
        latest = history[-1]
        archive_id = latest.get("archive_id", "?")
        project_name_arch = latest.get("project_name", "?")
        reason = latest.get("reason", "?")
        archived_at = latest.get("archived_at")
        archived_str = (
            _format_relative_time_for_summary(archived_at) if archived_at else archived_at or "?"
        )
        total_archives = len(history)
        print(f"\n### Archive History ({total_archives} total):")
        print(
            f"  Latest: [{archive_id}] {project_name_arch} | {reason} | {archived_str}"
        )

    # Output context handoff block
    project_root_str = str(services.find_project_root_fn().resolve())
    handoff = _build_status_handoff_block(
        data, completed, total, project_root_str, services=services
    )
    if handoff:
        print(f"\n---\n**Paste into a new session to continue:**\n\n{handoff}\n---")

    return True
