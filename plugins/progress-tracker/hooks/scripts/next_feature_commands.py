"""``next-feature`` command orchestration.

Extracted from ``progress_manager.py`` (F23 facade refactor). This module owns
command rendering and state writes for work-item selection; the facade injects
all repository-specific services.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional


@dataclass
class NextFeatureCommandServices:
    """Injected callbacks and constants for ``next_feature_command``."""

    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    save_progress_json_fn: Callable[[Dict[str, Any]], None]
    generate_progress_md_fn: Callable[[Dict[str, Any]], str]
    save_progress_md_fn: Callable[[str], None]
    find_project_root_fn: Callable[[], Path]
    detect_default_branch_fn: Callable[[Optional[Path]], Optional[str]]
    run_git_fn: Callable[..., tuple[int, str, str]]
    update_runtime_context_fn: Callable[[Dict[str, Any], str], bool]
    collect_linked_project_statuses_fn: Callable[..., list]
    analyze_reconcile_state_fn: Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]
    evaluate_planning_readiness_fn: Callable[..., Dict[str, Any]]
    select_next_work_item_fn: Callable[
        [Dict[str, Any], Path, Path], Optional[Dict[str, Any]]
    ]
    get_next_feature_fn: Callable[[], Optional[Dict[str, Any]]]
    iso_now_fn: Callable[[], str]
    debug_fn: Callable[[str], None]
    finish_pending_state: str
    linked_snapshot_schema_version: str
    root_route_code: str
    repo_root: Optional[Path]


def _activate_task(
    *,
    data: Dict[str, Any],
    task_id: Any,
    task_name: Any,
    parent_fid: Any,
    is_standalone: bool,
    project_root: Path,
    output_json: bool,
    svc: NextFeatureCommandServices,
) -> bool:
    """Activate a standalone or feature-bound task."""
    original_branch = None
    branch_name = f"task/{task_id}"

    if is_standalone:
        git_dir = project_root / ".git"
        if git_dir.exists():
            rc_orig, orig_out, _ = svc.run_git_fn(
                ["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(project_root)
            )
            if rc_orig == 0:
                original_branch = orig_out.strip()

            # Branch from the default branch, not current HEAD, to avoid
            # carrying unrelated changes into the squash merge.
            task_base = svc.detect_default_branch_fn(project_root) or "main"
            rc_verify, _, _ = svc.run_git_fn(
                ["rev-parse", "--verify", "--quiet", task_base],
                cwd=str(project_root),
            )
            if rc_verify == 0:
                rc, _, err = svc.run_git_fn(
                    ["checkout", "-b", branch_name, task_base],
                    cwd=str(project_root),
                )
            else:
                rc, _, err = svc.run_git_fn(
                    ["checkout", "-b", branch_name],
                    cwd=str(project_root),
                )
            if rc != 0:
                print(f"Error: could not create branch {branch_name}: {err}")
                return False

    try:
        data["current_task_id"] = task_id
        data["updated_at"] = svc.iso_now_fn()
        svc.save_progress_json_fn(data)
    except Exception as exc:
        if is_standalone and original_branch:
            svc.run_git_fn(["checkout", original_branch], cwd=str(project_root))
            svc.run_git_fn(["branch", "-D", branch_name], cwd=str(project_root))
        print(f"Error: failed to save task state: {exc}", file=sys.stderr)
        return False

    action = "prog next --done"
    if output_json:
        print(json.dumps({
            "status": "ok",
            "item_type": "task",
            "id": task_id,
            "name": task_name,
            "priority_tier": None,
            "action": action,
            "feature_id": parent_fid,
            "test_steps": [],
        }, ensure_ascii=False))
    else:
        print(f"Task selected: {task_id}")
        print(f"{task_id}: {task_name}")
        print(f"Run: {action}")
    return True


def next_feature_command(
    output_json: bool = False,
    ack_planning_risk: bool = False,
    svc: Optional[NextFeatureCommandServices] = None,
) -> bool:
    """Print the next actionable feature (skipping completed/deferred)."""
    if svc is None:
        raise ValueError("NextFeatureCommandServices is required")

    data = svc.load_progress_json_fn()
    if data:
        features = data.get("features", [])
        pending_finish_feature = next(
            (
                feature
                for feature in features
                if isinstance(feature, dict)
                and feature.get("integration_status") == svc.finish_pending_state
            ),
            None,
        )
        if pending_finish_feature:
            pending_id = pending_finish_feature.get("id")
            message = (
                f"Feature {pending_id} is in finish_pending. "
                f"Run `prog set-finish-state --feature-id {pending_id} "
                "--status <merged_and_cleaned|pr_open|kept_with_reason>` first."
            )
            payload = {
                "status": "blocked",
                "reason": "finish_pending",
                "feature_id": pending_id,
                "message": message,
                "recommended_next_step": (
                    f"prog set-finish-state --feature-id {pending_id} "
                    "--status <merged_and_cleaned|pr_open|kept_with_reason>"
                ),
            }
            if output_json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(payload["message"])
            return False

        reconcile_report = svc.analyze_reconcile_state_fn(data)
        diagnosis = reconcile_report.get("diagnosis")
        if diagnosis == "implementation_ahead_of_tracker":
            payload = {
                "status": "blocked",
                "reason": diagnosis,
                "recommended_next_step": reconcile_report.get("recommended_next_step"),
                "message": (
                    "Active feature appears implementation-ahead-of-tracker. "
                    "Run `prog reconcile` and `/prog done` before selecting another feature."
                ),
            }
            if output_json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(payload["message"])
            return False
        if diagnosis in {"scope_mismatch", "context_mismatch"}:
            payload = {
                "status": "blocked",
                "reason": diagnosis,
                "recommended_next_step": reconcile_report.get("recommended_next_step"),
                "message": (
                    "Feature selection is blocked due to scope/context mismatch. "
                    "Run `prog reconcile` and follow the suggested correction first."
                ),
            }
            if output_json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(payload["message"])
            return False

    # RouteV1: parent dispatching (PT-F13: unified work-item selection)
    if data and data.get("tracker_role") == "parent":
        rq = data.get("routing_queue") or []
        rq_has_non_bug = any(
            isinstance(entry, str) and not entry.startswith("BUG-")
            for entry in rq
        )
        try:
            project_root = svc.find_project_root_fn()
            repo_root = svc.repo_root or project_root
            work_item = svc.select_next_work_item_fn(data, project_root, repo_root)
        except Exception as exc:
            svc.debug_fn(f"Parent dispatch failed: {exc}")
            work_item = None

        if work_item is not None:
            item_type = work_item.get("item_type")

            if item_type == "bug":
                bug_id = work_item["id"]
                bug_name = work_item["name"]
                tier = work_item.get("priority_tier")
                action = work_item.get("action") or f"/prog-fix {bug_id}"
                if output_json:
                    print(json.dumps({
                        "status": "ok",
                        "item_type": "bug",
                        "id": bug_id,
                        "name": bug_name,
                        "priority_tier": tier,
                        "action": action,
                        "feature_id": None,
                        "test_steps": [],
                    }, ensure_ascii=False))
                else:
                    tier_label = f" {tier}" if tier else ""
                    print(f"[NEXT]{tier_label} Bug: {bug_id}")
                    print(f"{bug_id}: {bug_name}")
                    print(f"Run: {action}")
                try:
                    ar_list = data.get("active_routes")
                    if not isinstance(ar_list, list):
                        ar_list = []
                    ar_list = [
                        route for route in ar_list
                        if not (
                            isinstance(route, dict)
                            and route.get("project_code") == bug_id
                        )
                    ]
                    ar_list.append({
                        "project_code": bug_id,
                        "feature_ref": bug_id,
                        "feature_name": bug_name,
                        "assigned_at": svc.iso_now_fn(),
                        "status": "active",
                    })
                    data["active_routes"] = ar_list
                    svc.update_runtime_context_fn(data, source="next_dispatch")
                    svc.save_progress_json_fn(data)
                    md_content = svc.generate_progress_md_fn(data)
                    svc.save_progress_md_fn(md_content)
                except Exception as exc:
                    svc.debug_fn(f"Bug dispatch bookkeeping failed: {exc}")
                return True

            if item_type == "task":
                task_id = work_item["id"]
                task_name = work_item["name"]
                tasks = data.get("tasks") or []
                task_record = next(
                    (
                        task for task in tasks
                        if isinstance(task, dict) and task.get("id") == task_id
                    ),
                    None,
                )
                parent_fid = (
                    task_record.get("parent_feature_id") if task_record else None
                )
                is_standalone = parent_fid is None
                return _activate_task(
                    data=data,
                    task_id=task_id,
                    task_name=task_name,
                    parent_fid=parent_fid,
                    is_standalone=is_standalone,
                    project_root=project_root,
                    output_json=output_json,
                    svc=svc,
                )

            if item_type in ("child", "root"):
                dispatch_result = work_item.get("dispatch_result") or {}
                code = dispatch_result.get("child_project_code")
                fid = dispatch_result.get("next_feature_id")
                fname = dispatch_result.get("next_feature_name")
                action = dispatch_result.get("action_required")
                pos = dispatch_result.get("position", "?")
                if output_json:
                    print(json.dumps(dispatch_result, ensure_ascii=False))
                else:
                    if code == svc.root_route_code:
                        print(f"[NEXT] Root-level feature (routing_queue position {pos}):")
                    else:
                        print(f"[NEXT] Dispatching to [{code}] (routing_queue position {pos}):")
                    print(f"F{fid}: {fname}")
                    print(f"Run: {action}")
                if code and code != svc.root_route_code:
                    try:
                        ar_list = data.get("active_routes")
                        if not isinstance(ar_list, list):
                            ar_list = []
                        ar_list = [
                            route for route in ar_list
                            if not (
                                isinstance(route, dict)
                                and route.get("project_code") == code
                            )
                        ]
                        ar_list.append({
                            "project_code": code,
                            "feature_ref": f"F{fid}",
                            "feature_name": fname,
                            "assigned_at": svc.iso_now_fn(),
                            "status": "active",
                        })
                        data["active_routes"] = ar_list
                        statuses = svc.collect_linked_project_statuses_fn(
                            data,
                            project_root=project_root,
                            repo_root=repo_root,
                            active_routes=ar_list,
                        )
                        linked_snapshot = data.get("linked_snapshot")
                        if not isinstance(linked_snapshot, dict):
                            linked_snapshot = {}
                        linked_snapshot["schema_version"] = (
                            svc.linked_snapshot_schema_version
                        )
                        linked_snapshot["updated_at"] = svc.iso_now_fn()
                        linked_snapshot["projects"] = statuses
                        data["linked_snapshot"] = linked_snapshot
                        svc.update_runtime_context_fn(data, source="next_dispatch")
                        svc.save_progress_json_fn(data)
                        md_content = svc.generate_progress_md_fn(data)
                        svc.save_progress_md_fn(md_content)
                    except Exception as exc:
                        svc.debug_fn(f"Child dispatch bookkeeping failed: {exc}")
                return True

            # item_type == "feature": fall through to the legacy feature
            # rendering path below so planning preflight still runs.

        if rq and rq_has_non_bug and (
            work_item is None or work_item.get("item_type") not in ("feature",)
        ):
            no_action_msg = (
                "No actionable feature found in routing_queue. "
                "Check queue configuration with 'prog route-status'."
            )
            if output_json:
                print(json.dumps({
                    "status": "none",
                    "message": no_action_msg,
                    "routing_queue": rq,
                }, ensure_ascii=False))
            else:
                print(no_action_msg)
            return False

        if rq and not rq_has_non_bug and work_item is None:
            no_action_msg = (
                "No actionable work item. All routing_queue bug entries are "
                "filtered (fixed / in-progress) and no tasks or features "
                "remain."
            )
            if output_json:
                print(json.dumps({
                    "status": "none",
                    "message": no_action_msg,
                    "routing_queue": rq,
                }, ensure_ascii=False))
            else:
                print(no_action_msg)
            return True

    # Standalone task activation (non-parent / leaf projects).
    if data:
        tasks = data.get("tasks") or []
        pending_task = next(
            (
                task for task in tasks
                if isinstance(task, dict) and task.get("status") == "pending"
            ),
            None,
        )
        if pending_task is not None:
            task_id = pending_task.get("id")
            task_name = pending_task.get("description", task_id)
            parent_fid = pending_task.get("parent_feature_id")
            is_standalone = parent_fid is None
            project_root = svc.find_project_root_fn()
            return _activate_task(
                data=data,
                task_id=task_id,
                task_name=task_name,
                parent_fid=parent_fid,
                is_standalone=is_standalone,
                project_root=project_root,
                output_json=output_json,
                svc=svc,
            )

    feature = svc.get_next_feature_fn()
    if not feature:
        if output_json:
            print(json.dumps({"status": "none", "message": "No actionable feature found"}))
        else:
            print("No actionable feature found.")
        return False

    payload = {
        "status": "ok",
        "feature_id": feature.get("id"),
        "name": feature.get("name"),
        "test_steps": feature.get("test_steps", []),
        "deferred": bool(feature.get("deferred", False)),
    }

    planning_report = svc.evaluate_planning_readiness_fn(
        data, feature_id=feature.get("id")
    )
    if planning_report["status"] in {"missing", "warn"} and not ack_planning_risk:
        blocked = {
            "status": "blocked",
            "reason": f"planning_{planning_report['status']}",
            "feature_id": feature.get("id"),
            "required": planning_report["required"],
            "missing": planning_report["missing"],
            "optional_missing": planning_report["optional_missing"],
            "refs": planning_report["refs"],
            "message": planning_report["message"],
            "recommended_next_step": (
                "Run SPM planning commands, or re-run with "
                "`prog next-feature --ack-planning-risk` to continue."
            ),
        }
        if output_json:
            print(json.dumps(blocked, ensure_ascii=False))
        else:
            print(blocked["message"])
            print(blocked["recommended_next_step"])
        return False

    payload["planning"] = planning_report

    if output_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Next actionable feature: [{payload['feature_id']}] {payload['name']}")
    return True
