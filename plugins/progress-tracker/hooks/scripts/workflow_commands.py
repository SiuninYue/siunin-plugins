"""Workflow-state and reconcile commands extracted from ``progress_manager.py``.

This module owns workflow-state mutations and reconcile diagnostics while
keeping ``progress_manager.py`` as a thin facade. It imports only leaf modules
directly and receives progress_manager-owned side effects via
``WorkflowCommandsServices``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import git_utils
from prog_paths import PROGRESS_JSON, get_tracker_docs_root
from progress_prompt_builders import _is_deferred as _is_feature_deferred
from state_io import _normalize_context_path, compare_contexts

try:
    import audit_log
except ImportError:  # pragma: no cover - optional module
    audit_log = None

try:
    from git_validator import is_git_repository, safe_git_command
    GIT_VALIDATOR_AVAILABLE = True
except ImportError:  # pragma: no cover - optional module
    GIT_VALIDATOR_AVAILABLE = False
    is_git_repository = None
    safe_git_command = None

logger = logging.getLogger(__name__)


RECONCILE_DIAGNOSES = (
    "in_sync",
    "implementation_ahead_of_tracker",
    "tracker_ahead_of_implementation",
    "scope_mismatch",
    "context_mismatch",
    "needs_manual_review",
)
RECONCILE_NEXT_STEPS = (
    "/prog done",
    "/prog next",
    "resume implementation",
    "switch to recorded context",
    "repair workflow_state",
    "clear invalid current_feature_id",
)


@dataclass
class WorkflowCommandsServices:
    """Injected callbacks used by workflow-state and reconcile commands."""

    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    save_progress_json_fn: Callable[[Dict[str, Any]], None]
    generate_progress_md_fn: Callable[[Dict[str, Any]], str]
    save_progress_md_fn: Callable[[str], None]
    update_runtime_context_fn: Callable[..., bool]
    update_execution_context_fn: Callable[..., None]
    build_runtime_context_fn: Callable[..., Dict[str, Any]]
    validate_plan_path_fn: Callable[..., Dict[str, Optional[str]]]
    validate_plan_document_fn: Callable[..., Dict[str, Any]]
    find_project_root_fn: Callable[[], Path]
    get_progress_dir_fn: Callable[[], Path]
    load_checkpoints_fn: Callable[[], Dict[str, Any]]
    latest_checkpoint_entry_for_feature_fn: Callable[
        [Optional[Dict[str, Any]], Optional[int]], Optional[Dict[str, Any]]
    ]
    build_checkpoint_context_fn: Callable[
        [Optional[Dict[str, Any]]], Optional[Dict[str, Any]]
    ]


def _iso_now() -> str:
    """Return current local timestamp with trailing Z for compatibility."""
    return datetime.now().isoformat() + "Z"


def _persist_progress(data: Dict[str, Any], svc: WorkflowCommandsServices) -> None:
    svc.save_progress_json_fn(data)
    svc.save_progress_md_fn("")


def _collect_feature_artifact_evidence(
    feature_id: Optional[int],
    workflow_state: Dict[str, Any],
    svc: WorkflowCommandsServices,
) -> Dict[str, Any]:
    """Collect lightweight file-based evidence for reconcile diagnostics."""
    if feature_id is None:
        return {
            "plan_path": None,
            "plan_exists": False,
            "testing_artifact_count": 0,
            "archive_artifact_count": 0,
            "artifacts_present": False,
        }

    project_root = svc.find_project_root_fn()
    docs_root = get_tracker_docs_root(project_root)

    plan_path_raw = workflow_state.get("plan_path")
    plan_path = plan_path_raw if isinstance(plan_path_raw, str) else None
    plan_exists = bool(plan_path and (project_root / plan_path).exists())

    testing_matches: set[str] = set()
    testing_dir = docs_root / "testing"
    if testing_dir.exists():
        patterns = (
            f"feature-{feature_id}-*.md",
            f"feature-{feature_id}_*.md",
            f"*feature-{feature_id}*.md",
        )
        for pattern in patterns:
            for path in testing_dir.glob(pattern):
                if path.is_file():
                    testing_matches.add(str(path))

    archive_matches: set[str] = set()
    archive_feature_dir = docs_root / "archive" / "features"
    if archive_feature_dir.exists():
        patterns = (
            f"feature-{feature_id}-*.md",
            f"feature-{feature_id}_*.md",
            f"*feature-{feature_id}*.md",
        )
        for pattern in patterns:
            for path in archive_feature_dir.glob(pattern):
                if path.is_file():
                    archive_matches.add(str(path))

    return {
        "plan_path": plan_path,
        "plan_exists": plan_exists,
        "testing_artifact_count": len(testing_matches),
        "archive_artifact_count": len(archive_matches),
        "artifacts_present": bool(plan_exists or testing_matches or archive_matches),
    }


def _collect_git_change_evidence(project_root: Path) -> Dict[str, Any]:
    """Collect lightweight working-tree evidence for reconcile diagnostics."""
    exit_code, stdout, _ = git_utils._run_git(
        ["status", "--porcelain"],
        cwd=str(project_root),
        timeout=5,
    )
    if exit_code != 0:
        return {
            "git_changes_detected": None,
            "git_changed_files": None,
        }

    changed_lines = [line for line in stdout.splitlines() if line.strip()]
    return {
        "git_changes_detected": bool(changed_lines),
        "git_changed_files": len(changed_lines),
    }


def _normalize_reconcile_step(step: str) -> str:
    """Guarantee reconcile recommendations stay in the allowed stable set."""
    return step if step in RECONCILE_NEXT_STEPS else "repair workflow_state"


def analyze_reconcile_state_command(
    data: Optional[Dict[str, Any]] = None,
    *,
    svc: WorkflowCommandsServices,
) -> Dict[str, Any]:
    """Analyze tracker drift vs implementation evidence and return stable diagnostics."""
    if data is None:
        data = svc.load_progress_json_fn()

    if not isinstance(data, dict):
        return {
            "active_feature": None,
            "tracker_state": {},
            "evidence": {},
            "diagnosis": "needs_manual_review",
            "recommended_next_step": "repair workflow_state",
            "reason": "Progress tracking data is missing or invalid.",
        }

    features = data.get("features", [])
    if not isinstance(features, list):
        features = []
    current_id = data.get("current_feature_id")
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}
    runtime_context = data.get("runtime_context", {})
    if not isinstance(runtime_context, dict):
        runtime_context = {}

    active_feature = None
    if isinstance(current_id, int):
        active_feature = next(
            (feature for feature in features if isinstance(feature, dict) and feature.get("id") == current_id),
            None,
        )

    execution_context = workflow_state.get("execution_context", {})
    if not isinstance(execution_context, dict):
        execution_context = {}
    expected_context = execution_context
    if not (expected_context.get("branch") or expected_context.get("worktree_path")):
        latest_feature_checkpoint = svc.latest_checkpoint_entry_for_feature_fn(
            svc.load_checkpoints_fn(), current_id if isinstance(current_id, int) else None
        )
        expected_context = svc.build_checkpoint_context_fn(latest_feature_checkpoint) or {}

    current_context = svc.build_runtime_context_fn(data, source="manual")
    context_hint = compare_contexts(expected_context, current_context)

    project_root = svc.find_project_root_fn()
    normalized_project_root = _normalize_context_path(str(project_root))
    execution_project_root = _normalize_context_path(execution_context.get("project_root"))
    runtime_project_root = _normalize_context_path(runtime_context.get("project_root"))
    execution_tracker_root = _normalize_context_path(execution_context.get("tracker_root"))
    runtime_tracker_root = _normalize_context_path(runtime_context.get("tracker_root"))

    feature_artifacts = _collect_feature_artifact_evidence(
        feature_id=current_id if isinstance(current_id, int) else None,
        workflow_state=workflow_state,
        svc=svc,
    )
    git_evidence = _collect_git_change_evidence(project_root)

    total_features = len([feature for feature in features if isinstance(feature, dict)])
    completed_features = sum(
        1
        for feature in features
        if isinstance(feature, dict) and feature.get("completed", False)
    )
    incomplete_features = [
        feature
        for feature in features
        if isinstance(feature, dict) and not feature.get("completed", False)
    ]
    actionable_incomplete = [
        feature for feature in incomplete_features if not _is_feature_deferred(feature)
    ]

    tracker_state = {
        "project_name": data.get("project_name", "Unknown"),
        "current_feature_id": current_id,
        "feature_count": total_features,
        "completed_count": completed_features,
        "incomplete_count": len(incomplete_features),
        "actionable_incomplete_count": len(actionable_incomplete),
        "workflow_phase": workflow_state.get("phase"),
        "workflow_plan_path": workflow_state.get("plan_path"),
        "workflow_has_execution_context": bool(execution_context),
        "runtime_context_recorded": bool(runtime_context),
    }

    active_feature_summary: Optional[Dict[str, Any]] = None
    if isinstance(active_feature, dict):
        active_feature_summary = {
            "id": active_feature.get("id"),
            "name": active_feature.get("name"),
            "completed": bool(active_feature.get("completed", False)),
            "development_stage": active_feature.get("development_stage"),
            "deferred": _is_feature_deferred(active_feature),
        }

    evidence: Dict[str, Any] = {
        "current_branch": current_context.get("branch"),
        "current_worktree_path": current_context.get("worktree_path"),
        "context_status": context_hint.get("status"),
        "execution_project_root": execution_project_root,
        "runtime_project_root": runtime_project_root,
        "execution_tracker_root": execution_tracker_root,
        "runtime_tracker_root": runtime_tracker_root,
        **feature_artifacts,
        **git_evidence,
    }

    diagnosis = "in_sync"
    recommended_next_step = "/prog next" if current_id is None else "resume implementation"
    reason = "Tracker and implementation context are aligned."

    if current_id is not None and active_feature is None:
        diagnosis = "needs_manual_review"
        recommended_next_step = "clear invalid current_feature_id"
        reason = "current_feature_id does not point to an existing feature."
    elif (
        execution_tracker_root
        and normalized_project_root
        and execution_tracker_root != normalized_project_root
    ):
        diagnosis = "scope_mismatch"
        recommended_next_step = "switch to recorded context"
        reason = "Recorded project scope differs from the current command scope."
    elif context_hint.get("status") in {"mismatch", "path_mismatch", "branch_mismatch"}:
        diagnosis = "context_mismatch"
        recommended_next_step = "switch to recorded context"
        reason = context_hint.get("message") or "Execution context does not match the current session."
    elif current_id is None and workflow_state:
        diagnosis = "needs_manual_review"
        recommended_next_step = "repair workflow_state"
        reason = "workflow_state exists without an active current_feature_id."
    elif isinstance(active_feature, dict):
        feature_completed = bool(active_feature.get("completed", False))
        feature_deferred = _is_feature_deferred(active_feature)
        phase = workflow_state.get("phase")
        development_stage = active_feature.get("development_stage")

        if feature_deferred:
            diagnosis = "needs_manual_review"
            recommended_next_step = "clear invalid current_feature_id"
            reason = "Active feature is marked deferred; tracker state is inconsistent."
        elif feature_completed:
            diagnosis = "tracker_ahead_of_implementation"
            recommended_next_step = "clear invalid current_feature_id"
            reason = "Active feature is already marked completed but still selected as current."
        elif phase == "execution_complete" or development_stage == "completed":
            diagnosis = "implementation_ahead_of_tracker"
            recommended_next_step = "/prog done"
            reason = "Implementation reached execution_complete/completed stage but feature is not closed."
        elif feature_artifacts.get("artifacts_present") and git_evidence.get("git_changes_detected"):
            diagnosis = "implementation_ahead_of_tracker"
            recommended_next_step = "/prog done"
            reason = "Implementation artifacts and local changes suggest tracker closure may be pending."
        else:
            diagnosis = "in_sync"
            recommended_next_step = "resume implementation"
            reason = "Active feature is in-progress and tracker reflects that state."
    elif actionable_incomplete:
        diagnosis = "in_sync"
        recommended_next_step = "/prog next"
        reason = "No active feature is set; tracker is ready to start the next actionable feature."
    else:
        diagnosis = "in_sync"
        recommended_next_step = "/prog next"
        reason = "No actionable pending features remain in the current scope."

    return {
        "active_feature": active_feature_summary,
        "tracker_state": tracker_state,
        "evidence": evidence,
        "diagnosis": (
            diagnosis if diagnosis in RECONCILE_DIAGNOSES else "needs_manual_review"
        ),
        "recommended_next_step": _normalize_reconcile_step(recommended_next_step),
        "reason": reason,
    }


def reconcile_command(
    output_json: bool = False,
    *,
    svc: WorkflowCommandsServices,
) -> bool:
    """Print reconcile diagnostics and suggested next step."""
    data = svc.load_progress_json_fn()
    if not data:
        if output_json:
            print(
                json.dumps(
                    {
                        "status": "missing_tracking",
                        "diagnosis": "needs_manual_review",
                        "recommended_next_step": "/prog next",
                        "message": "No progress tracking found. Use '/prog init' first.",
                    }
                )
            )
        else:
            print("No progress tracking found. Use '/prog init' first.")
        return False

    report = analyze_reconcile_state_command(data, svc=svc)
    if output_json:
        print(json.dumps(report, ensure_ascii=False))
        return True

    print("## Reconcile")
    active_feature = report.get("active_feature")
    if active_feature:
        print(
            f"Active feature: [{active_feature.get('id')}] "
            f"{active_feature.get('name', 'Unknown')}"
        )
    else:
        print("Active feature: none")

    tracker_state = report.get("tracker_state", {})
    evidence = report.get("evidence", {})
    print(
        "Tracker summary: "
        f"phase={tracker_state.get('workflow_phase') or 'none'}, "
        f"current_feature_id={tracker_state.get('current_feature_id')}, "
        f"completed={tracker_state.get('completed_count')}/{tracker_state.get('feature_count')}"
    )
    print(
        "Evidence: "
        f"context={evidence.get('context_status') or 'unknown'}, "
        f"plan_exists={evidence.get('plan_exists')}, "
        f"artifacts_present={evidence.get('artifacts_present')}, "
        f"git_changes={evidence.get('git_changes_detected')}"
    )
    print(f"Diagnosis: {report.get('diagnosis')}")
    print(f"Recommended next step: {report.get('recommended_next_step')}")
    print(f"Reason: {report.get('reason')}")
    return True


def _replay_audit_events(
    audit_records: List[Dict[str, Any]],
) -> Tuple[Dict[int, str], bool]:
    """按时间戳升序回放事件，重建每个 feature 的期望完成状态。

    - tracker_reset / project_completed 是边界：清空已累积状态，边界之前的事件不再有效
    - feature_completed → "completed"
    - feature_undone → "not_completed"

    Returns:
        (states, last_event_was_reset)
        - states: {feature_id: "completed" | "not_completed"}
        - last_event_was_reset: True 表示边界事件是最后一个事件，之后无任何
          feature 状态变更。此时 reconcile 应将所有 completed=True 的 feature 视为 drift。
    """
    relevant_types = {"feature_completed", "feature_undone", "tracker_reset", "project_completed"}
    sorted_records = sorted(
        [r for r in audit_records if r.get("event_type") in relevant_types],
        key=lambda r: r.get("timestamp", ""),
    )

    states: Dict[int, str] = {}
    last_event_was_reset = False
    for record in sorted_records:
        et = record["event_type"]
        if et in ("tracker_reset", "project_completed"):
            # 两者都是边界：清空所有已回放状态
            states.clear()
            last_event_was_reset = True
        elif et == "feature_completed" and record.get("feature_id") is not None:
            states[record["feature_id"]] = "completed"
            last_event_was_reset = False  # reset 后有完成事件，reset 不再是最终边界
        elif et == "feature_undone" and record.get("feature_id") is not None:
            states[record["feature_id"]] = "not_completed"
            last_event_was_reset = False
    return states, last_event_was_reset


def cmd_reconcile_state_command(
    check_only: bool = False,
    auto_commit: bool = False,
    *,
    svc: WorkflowCommandsServices,
) -> Dict[str, Any]:
    """通过 audit.log 事件回放检测并修复 progress.json 的 drift。

    不接受 project_root 参数：使用注入的 find_project_root_fn 与其余
    progress_manager 命令保持一致。测试通过 _PROJECT_ROOT_OVERRIDE 注入。

    Returns:
        {"drift": bool, "drifted_features": [int], "diff": [...],
         "fixed": bool, "committed": bool, "dedup_stats": {...}}
    """
    result: Dict[str, Any] = {
        "drift": False,
        "drifted_features": [],
        "diff": [],
        "fixed": False,
        "committed": False,
        "dedup_stats": {},
    }

    if audit_log is None:
        print("[reconcile-state] audit_log module unavailable")
        return result

    # 1. 读取并去重 audit.log（显式传 project_root，避免跨 plugin 读错）
    effective_root = str(svc.find_project_root_fn())
    raw_records = audit_log.read_audit_log(ascending=True, project_root=effective_root)
    if raw_records:
        dedup = audit_log.deduplicate_audit_log(raw_records)
        records = dedup["kept"]
        result["dedup_stats"] = {
            "original": len(raw_records),
            "kept": len(records),
            "id_conflicts": dedup["id_conflicts"],
            "semantic_dupes": len(dedup["semantic_duplicates_removed"]),
        }
    else:
        records = []

    # 2. 回放事件，重建期望状态
    expected_states, last_event_was_reset = _replay_audit_events(records)

    # 3. 加载 progress.json（必须在 reset boundary 检查前加载）
    data = svc.load_progress_json_fn()
    if not data:
        print("[reconcile-state] No progress.json found")
        return result

    features_map = {f["id"]: f for f in data.get("features", [])}
    diff_items = []

    if not expected_states and not last_event_was_reset:
        print("[reconcile-state] No state-change events in audit.log. Nothing to reconcile.")
        return result

    if last_event_was_reset and not expected_states:
        # tracker_reset 是最后一个事件，之后无任何完成事件
        # → 所有 completed=True 的 feature 均是 drift（reset 后应恢复初始态）
        print("[reconcile-state] Last audit event was tracker_reset with no subsequent completions.")
        print("[reconcile-state] All currently completed features are drift candidates.")
        for feature in data.get("features", []):
            if feature.get("completed", False):
                diff_items.append({
                    "feature_id": feature["id"],
                    "feature_name": feature.get("name", f"Feature {feature['id']}"),
                    "expected_completed": False,
                    "actual_completed": True,
                    "audit_verdict": "not_completed (post-reset boundary)",
                })
    else:
        for fid, expected in expected_states.items():
            feature = features_map.get(fid)
            if feature is None:
                continue
            actual_completed = feature.get("completed", False)
            expected_completed = (expected == "completed")
            if actual_completed != expected_completed:
                diff_items.append({
                    "feature_id": fid,
                    "feature_name": feature.get("name", f"Feature {fid}"),
                    "expected_completed": expected_completed,
                    "actual_completed": actual_completed,
                    "audit_verdict": expected,
                })

    result["drifted_features"] = [d["feature_id"] for d in diff_items]
    result["diff"] = diff_items
    result["drift"] = len(diff_items) > 0

    # 4. 打印 diff（始终）
    if not diff_items:
        print("[reconcile-state] OK — no drift detected")
    else:
        print(f"[reconcile-state] DRIFT DETECTED: {len(diff_items)} feature(s)")
        for item in diff_items:
            print(
                f"  Feature {item['feature_id']} '{item['feature_name']}': "
                f"audit='{item['audit_verdict']}', "
                f"progress.json completed={item['actual_completed']}"
            )

    if check_only or not diff_items:
        return result

    # 5. 修复 progress.json（强制写，不用 setdefault）
    print("[reconcile-state] Fixing progress.json...")
    for item in diff_items:
        feature = features_map.get(item["feature_id"])
        if feature is None:
            continue
        if item["expected_completed"]:
            # 强制写完整完成状态
            feature["completed"] = True
            feature["development_stage"] = "completed"
            feature["lifecycle_state"] = "archived"
        else:
            # 撤销完成：清理完成相关字段
            feature["completed"] = False
            feature["development_stage"] = "developing"
            feature["lifecycle_state"] = "implementing"
            feature.pop("completed_at", None)
            feature.pop("commit_hash", None)

    svc.save_progress_json_fn(data)
    result["fixed"] = True
    print(f"[reconcile-state] Fixed {len(diff_items)} feature(s) in progress.json")
    print("[reconcile-state] NOTE: Not committed. Run 'git commit' manually, or use --auto-commit.")

    # 6. 可选 auto-commit
    if auto_commit:
        try:
            import subprocess
            progress_json_path = svc.get_progress_dir_fn() / PROGRESS_JSON
            try:
                rel_path = str(progress_json_path.relative_to(Path.cwd()))
            except ValueError:
                rel_path = str(progress_json_path)
            commit_msg = (
                f"fix(reconcile): auto-reconcile progress.json [{len(diff_items)} fix(es)] [skip ci]"
            )
            r1 = subprocess.run(
                ["git", "add", rel_path],
                capture_output=True, text=True, timeout=30,
            )
            if r1.returncode == 0:
                r2 = subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    capture_output=True, text=True, timeout=30,
                )
                result["committed"] = r2.returncode == 0
                if result["committed"]:
                    print(f"[reconcile-state] Auto-committed: {commit_msg}")
                else:
                    print(f"[reconcile-state] Auto-commit failed: {r2.stderr.strip()}")
        except Exception as e:
            print(f"[reconcile-state] Auto-commit error: {e}")

    return result


def set_workflow_state_command(
    phase=None,
    plan_path=None,
    next_action=None,
    *,
    svc: WorkflowCommandsServices,
):
    """Set workflow state for current feature."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    if data.get("current_feature_id") is None:
        print("Error: No feature currently in progress")
        return False

    workflow_state = data.get("workflow_state", {})

    effective_phase = phase or workflow_state.get("phase")
    candidate_plan_path = (
        plan_path if plan_path is not None else workflow_state.get("plan_path")
    )
    require_existing_plan = effective_phase in [
        "planning:draft",
        "planning:approved",
        "planning:review",
        "planning_complete",
        "execution",
        "execution_complete",
    ]
    plan_validation = svc.validate_plan_path_fn(
        candidate_plan_path, require_exists=require_existing_plan
    )
    if not plan_validation["valid"]:
        print(f"Error: Invalid plan_path - {plan_validation['error']}")
        return False

    if phase:
        workflow_state["phase"] = phase
    if plan_path is not None:
        workflow_state["plan_path"] = plan_validation["normalized_path"]
    if next_action:
        workflow_state["next_action"] = next_action

    workflow_state["updated_at"] = _iso_now()
    svc.update_execution_context_fn(workflow_state, source="set_workflow_state")

    data["workflow_state"] = workflow_state
    svc.update_runtime_context_fn(data, source="set_workflow_state")
    _persist_progress(data, svc)

    print(f"Workflow state updated: phase={phase or workflow_state.get('phase')}")
    return True


def update_workflow_task_command(
    task_id,
    status,
    *,
    svc: WorkflowCommandsServices,
):
    """Update task completion status in workflow_state."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    workflow_state = data.get("workflow_state", {})

    if status == "completed":
        completed_tasks = workflow_state.get("completed_tasks", [])
        if task_id not in completed_tasks:
            completed_tasks.append(task_id)
            workflow_state["completed_tasks"] = completed_tasks
            workflow_state["current_task"] = task_id + 1

    workflow_state["updated_at"] = _iso_now()
    svc.update_execution_context_fn(workflow_state, source="update_workflow_task")

    data["workflow_state"] = workflow_state
    svc.update_runtime_context_fn(data, source="update_workflow_task")
    _persist_progress(data, svc)

    total = workflow_state.get("total_tasks", 0)
    print(f"Task {task_id}/{total} marked as {status}")
    return True


def clear_workflow_state_command(*, svc: WorkflowCommandsServices):
    """Clear workflow state from progress tracking."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    if "workflow_state" in data:
        del data["workflow_state"]
        _persist_progress(data, svc)

        print("Workflow state cleared")
        return True

    print("No workflow state to clear")
    return True


def health_check_command(*, svc: WorkflowCommandsServices):
    """
    Perform health check and return JSON metrics.

    This command is used to monitor the health of the progress tracker
    and provide recommendations for timeout settings.

    Returns:
        int: 0 if healthy, 1 if degraded

    Output:
        JSON with status, response_time_ms, and recommended_timeout
    """
    start = time.time()

    # Load progress to check data integrity
    try:
        data = svc.load_progress_json_fn()
        load_time = time.time() - start

        if data:
            features = data.get("features", [])
            bugs = data.get("bugs", [])
            data_valid = True
        else:
            features = []
            bugs = []
            data_valid = False  # No tracking file is OK
    except Exception as e:
        logger.error(f"Health check failed to load progress: {e}")
        data = None
        data_valid = False
        features = []
        bugs = []
        load_time = time.time() - start

    # Check git connectivity
    git_start = time.time()
    try:
        if GIT_VALIDATOR_AVAILABLE:
            git_healthy = is_git_repository()
        else:
            # Basic check
            exit_code, _, _ = safe_git_command(
                ['git', 'status', '--porcelain'],
                timeout=2
            ) if GIT_VALIDATOR_AVAILABLE else (0, "", "")
            git_healthy = exit_code in (0, 128)  # 0=success, 128=not in repo
        git_time = time.time() - git_start
    except Exception:
        git_healthy = False
        git_time = time.time() - git_start

    total = time.time() - start

    # Calculate recommended timeout (3x current response time, minimum 10 seconds)
    recommended_timeout = max(10, int(total * 3))

    health_data = {
        "status": "healthy" if (data_valid or not data) and git_healthy else "degraded",
        "response_time_ms": int(total * 1000),
        "load_time_ms": int(load_time * 1000),
        "git_time_ms": int(git_time * 1000),
        "git_healthy": git_healthy,
        "data_valid": data_valid or not data,
        "features_count": len(features),
        "bugs_count": len(bugs),
        "recommended_timeout": recommended_timeout
    }

    print(json.dumps(health_data))

    # Return 0 if healthy, 1 if degraded
    return 0 if health_data["status"] == "healthy" else 1


def validate_plan_command(
    plan_path: Optional[str] = None,
    *,
    svc: WorkflowCommandsServices,
):
    """Validate workflow plan path and minimum plan document structure."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    resolved_plan_path = plan_path
    if not resolved_plan_path:
        workflow_state = data.get("workflow_state", {})
        resolved_plan_path = workflow_state.get("plan_path")

    if not resolved_plan_path:
        current_id = data.get("current_feature_id")
        features = data.get("features", [])
        current_feature = next(
            (item for item in features if item.get("id") == current_id),
            None,
        )
        ai_metrics = current_feature.get("ai_metrics") if isinstance(current_feature, dict) else {}
        workflow_path = (
            str(ai_metrics.get("workflow_path") or "").strip().lower()
            if isinstance(ai_metrics, dict)
            else ""
        )
        if workflow_path == "direct_tdd":
            print(
                "Plan validation skipped: direct_tdd workflow does not require workflow_state.plan_path."
            )
            return True

        print("Error: No plan path provided and no workflow_state.plan_path found")
        return False

    plan_result = svc.validate_plan_document_fn(resolved_plan_path)
    if not plan_result["valid"]:
        print("Plan validation failed:")
        for err in plan_result["errors"]:
            print(f"- {err}")
        return False

    print(f"Plan validation passed: {resolved_plan_path}")
    for warning in plan_result.get("warnings", []):
        print(f"Plan validation warning: {warning}")
    return True
