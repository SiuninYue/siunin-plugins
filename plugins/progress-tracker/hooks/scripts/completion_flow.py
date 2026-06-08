"""
completion_flow.py — Completion (prog done) flow extracted from progress_manager.py.

This module contains all completion-related functions for the /prog done workflow.
It uses dependency injection via CompletionFlowServices to avoid importing progress_manager.
"""

import copy
import json
import logging
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import progress_prompt_builders
import git_utils
import worktree_handler
from prog_paths import get_state_dir, get_project_memory_path
from state_io import _clear_feature_defer_state, DEFAULT_TRACKER_ROLE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------

try:
    from review_router import (
        get_pending_lanes as _get_pending_lanes,
        initialize_reviews as _initialize_reviews,
    )
    REVIEW_ROUTER_AVAILABLE = True
except ImportError:
    REVIEW_ROUTER_AVAILABLE = False

try:
    from sprint_ledger import (
        SprintLedgerError,
        record as record_sprint_artifact,
        require_sprint_contract,
    )
    SPRINT_LEDGER_AVAILABLE = True
except ImportError:
    SPRINT_LEDGER_AVAILABLE = False

    class SprintLedgerError(Exception):
        pass

    def require_sprint_contract(feature):
        return None

    def record_sprint_artifact(**kwargs):
        return None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FINISH_PENDING_STATE = "finish_pending"


# ---------------------------------------------------------------------------
# CompletionFlowServices dataclass
# ---------------------------------------------------------------------------

@dataclass
class CompletionFlowServices:
    load_progress_json_fn: Callable[[], Optional[dict]]
    save_progress_json_fn: Callable[[dict], None]
    find_project_root_fn: Callable[[], Path]
    generate_progress_md_fn: Callable[[dict], str]
    save_progress_md_fn: Callable[[str], None]
    record_sprint_artifact_fn: Callable[..., None]
    require_sprint_contract_fn: Callable[[dict], None]
    notify_parent_sync_fn: Callable[[str], None]
    repo_root: Optional[Path] = None
    record_feature_state_event_fn: Optional[Callable[..., None]] = None
    update_runtime_context_fn: Optional[Callable[[dict, str], None]] = None
    auto_state_commit_fn: Optional[Callable[[str, str], None]] = None
    archive_current_progress_fn: Optional[Callable[..., Any]] = None
    reset_active_progress_fn: Optional[Callable[[dict], None]] = None
    archive_feature_docs_fn: Optional[Callable[[int, str], Dict[str, Any]]] = None
    get_next_feature_fn: Optional[Callable[[], Optional[dict]]] = None
    validate_plan_document_fn: Optional[Callable[[str], dict]] = None
    collect_git_context_fn: Optional[Callable[[], Dict[str, Any]]] = None
    get_head_commit_fn: Optional[Callable[[], Optional[str]]] = None
    analyze_reconcile_state_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# AcceptanceTestResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class AcceptanceTestResult:
    """Per-step execution result for `/prog done` acceptance checks."""

    step: str
    command: str
    success: bool
    output: str
    duration_ms: int
    error: Optional[str] = None
    exit_code: Optional[int] = None


# ---------------------------------------------------------------------------
# Pure helper functions (no services needed)
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    """Return current local timestamp with trailing Z for compatibility."""
    return datetime.now().isoformat() + "Z"


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 timestamps with optional trailing Z."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.astimezone()
        return parsed
    except (TypeError, ValueError):
        logger.debug(f"Invalid ISO timestamp: {value}")
        return None


def _clear_feature_finish_pending(feature: Dict[str, Any]) -> None:
    """Clear transient finish-pending metadata on a feature object."""
    feature.pop("finish_pending_reason", None)
    feature.pop("last_done_attempt_at", None)


def _extract_test_step_command(step: str) -> Optional[str]:
    """Normalize a test step into an executable command string when possible."""
    normalized = step.strip()
    if not normalized:
        return None
    if normalized.startswith("DoD:"):
        return None
    if normalized.startswith("#") or normalized.startswith("//"):
        return None

    for prefix in ("运行:", "运行：", "Run:", "run:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break

    return normalized or None


def _extract_relative_path_candidates_from_command(command: str) -> List[str]:
    """Extract relative path-like tokens from a shell command for cwd heuristics."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return []

    candidates: List[str] = []
    for token in tokens:
        if not token or token.startswith("-"):
            continue
        if token in {"&&", "||", "|", ";"}:
            continue
        if "=" in token and "/" not in token and not token.startswith(("./", "../")):
            # Likely ENV assignment (e.g., FOO=bar), not a file path.
            continue
        if token.startswith(("/", "~")):
            continue
        if "/" not in token and not token.startswith(("./", "../")):
            continue
        candidates.append(token)
    return candidates


def _is_executable_test_step(step: str) -> bool:
    """Return whether a test step should be executed as a shell command."""
    command = _extract_test_step_command(step)
    if not command:
        return False

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False

    if not tokens:
        return False

    command_token: Optional[str] = None
    for token in tokens:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", token):
            continue
        command_token = token
        break

    if not command_token:
        return False

    if command_token.startswith(("./", "../", "/", "~/")):
        return True

    if command_token in {"[", "test"}:
        return True

    return shutil.which(command_token) is not None


def _resolve_acceptance_command_cwd(
    command: str,
    project_root: Path,
    repo_root: Optional[Path],
) -> Path:
    """
    Pick a stable cwd for acceptance commands.

    Default is project_root. When command contains repo-relative paths that
    exist only under repo_root (common in worktree/plugin-root runs), execute
    from repo_root to avoid false "path not found" failures.
    """
    if repo_root is None:
        return project_root

    resolved_repo_root = repo_root.resolve()
    resolved_project_root = project_root.resolve()
    if resolved_repo_root == resolved_project_root:
        return resolved_project_root

    candidates = _extract_relative_path_candidates_from_command(command)
    if not candidates:
        return resolved_project_root

    missing_in_project = False
    has_repo_fallback = False
    for raw_candidate in candidates:
        project_candidate = (resolved_project_root / raw_candidate).resolve()
        repo_candidate = (resolved_repo_root / raw_candidate).resolve()

        project_exists = project_candidate.exists()
        repo_exists = repo_candidate.exists()
        if not project_exists:
            missing_in_project = True
        if repo_exists and not project_exists:
            has_repo_fallback = True

    if missing_in_project and has_repo_fallback:
        return resolved_repo_root

    return resolved_project_root


def _is_project_fully_completed(data: Dict[str, Any]) -> bool:
    """Return True when all tracked features are completed."""
    features = data.get("features", [])
    if not isinstance(features, list):
        return False
    feature_items = [item for item in features if isinstance(item, dict)]
    if not feature_items:
        return False
    return all(bool(item.get("completed")) for item in feature_items)


# ---------------------------------------------------------------------------
# Functions with services injection
# ---------------------------------------------------------------------------

def complete_feature_ai_metrics(feature_id: int, services: CompletionFlowServices) -> bool:
    """Mark AI metrics completion timestamp and duration for a feature."""
    data = services.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    now = datetime.now().astimezone()
    now_iso = now.isoformat().replace("+00:00", "Z")

    ai_metrics = feature.get("ai_metrics", {})
    if not isinstance(ai_metrics, dict):
        ai_metrics = {}

    started_at = _parse_iso_timestamp(ai_metrics.get("started_at"))
    if not started_at:
        started_at = now
        ai_metrics["started_at"] = now_iso

    duration_seconds = int(max(0, (now - started_at).total_seconds()))

    ai_metrics["finished_at"] = now_iso
    ai_metrics["duration_seconds"] = duration_seconds
    feature["ai_metrics"] = ai_metrics

    services.save_progress_json_fn(data)

    # Update progress.md
    md_content = services.generate_progress_md_fn(data)
    services.save_progress_md_fn(md_content)

    print(f"AI metrics finalized for feature {feature_id}: duration={duration_seconds}s")
    return True


def save_archive_record(feature_id: int, archive_result: Dict[str, Any], services: CompletionFlowServices) -> None:
    """
    Save archive record to progress.json for traceability.

    Args:
        feature_id: The ID of the completed feature
        archive_result: The result dict from archive_feature_docs()
    """
    try:
        data = services.load_progress_json_fn()
        if not data:
            logger.warning("Could not save archive record - no progress data found")
            return

        features = data.get("features", [])
        feature = next((f for f in features if f.get("id") == feature_id), None)

        if not feature:
            logger.warning(f"Could not save archive record - feature {feature_id} not found")
            return

        # Store archive info
        feature["archive_info"] = {
            "archived_at": datetime.now().isoformat() + "Z",
            "files_moved": len(archive_result.get("archived_files", [])),
            "files": archive_result.get("archived_files", [])
        }
        if archive_result.get("success", False):
            feature["lifecycle_state"] = "archived"

        services.save_progress_json_fn(data)
        logger.info(f"Archive record saved for feature {feature_id}")

    except Exception as e:
        logger.error(f"Failed to save archive record: {e}")


def _run_acceptance_tests(
    feature: Dict[str, Any],
    services: CompletionFlowServices,
    run_all: bool = False,
) -> Tuple[bool, List[AcceptanceTestResult]]:
    """Execute command-like acceptance steps from the target feature."""
    steps = feature.get("test_steps", [])
    if not isinstance(steps, list):
        steps = []

    project_root = services.find_project_root_fn().resolve()
    repo_root: Optional[Path]
    if services.repo_root:
        repo_root = Path(services.repo_root).resolve()
    else:
        repo_root = None
    all_passed = True
    results: List[AcceptanceTestResult] = []

    for raw_step in steps:
        if not isinstance(raw_step, str):
            continue
        command = _extract_test_step_command(raw_step)
        if not command or not _is_executable_test_step(raw_step):
            print(f"[DONE][SKIP] {raw_step}")
            continue

        print(f"[DONE][RUN] {command}")
        started_at = time.monotonic()
        command_cwd = _resolve_acceptance_command_cwd(
            command=command,
            project_root=project_root,
            repo_root=repo_root,
        )
        if command_cwd != project_root:
            print(
                f"[DONE][INFO] acceptance cwd adjusted: {project_root} -> {command_cwd}"
            )

        success = False
        error: Optional[str] = None
        output = ""
        exit_code: Optional[int] = None

        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(command_cwd),
                timeout=300,
                check=False,
            )
            exit_code = completed.returncode
            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()
            if stdout:
                print(stdout)
            if stderr:
                print(stderr)

            output = "\n".join(part for part in (stdout, stderr) if part).strip()
            success = completed.returncode == 0
            if not success:
                error = stderr or f"command exited with code {completed.returncode}"
        except subprocess.TimeoutExpired as exc:
            timeout_message = "timeout after 300 seconds"
            stdout = exc.stdout.decode("utf-8", "ignore") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", "ignore") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            output = "\n".join(part.strip() for part in (stdout, stderr) if part).strip()
            error = timeout_message
            print(f"[DONE][ERROR] {timeout_message}")
        except Exception as exc:  # pragma: no cover - defensive branch
            error = str(exc)
            print(f"[DONE][ERROR] {error}")

        duration_ms = int((time.monotonic() - started_at) * 1000)
        results.append(
            AcceptanceTestResult(
                step=raw_step,
                command=command,
                success=success,
                output=output,
                duration_ms=duration_ms,
                error=error,
                exit_code=exit_code,
            )
        )

        if not success:
            all_passed = False
            if not run_all:
                break

    if not results:
        print("[DONE] No executable acceptance commands found; treating as pass.")

    return all_passed, results


def _cleanup_old_done_reports(report_dir: Path, feature_id: int, keep_latest: int = 5) -> None:
    """Keep only a bounded number of `/prog done` reports per feature."""
    pattern = f"feature-{feature_id}-done-attempt-*.json"
    reports = sorted(report_dir.glob(pattern), key=lambda candidate: candidate.name, reverse=True)
    for old_report in reports[keep_latest:]:
        try:
            old_report.unlink()
        except OSError:
            logger.warning(f"Failed to remove old done report: {old_report}")


def _save_done_test_report(
    feature_id: int,
    feature_name: str,
    results: List[AcceptanceTestResult],
    success: bool,
    services: CompletionFlowServices,
) -> Optional[Path]:
    """Persist acceptance execution report for `/prog done` attempts."""
    try:
        state_dir = get_state_dir(services.find_project_root_fn())
        report_dir = state_dir / "test_reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        report_path = report_dir / f"feature-{feature_id}-done-attempt-{timestamp}.json"
        payload = {
            "feature_id": feature_id,
            "feature_name": feature_name,
            "done_attempt_at": _iso_now(),
            "overall_success": success,
            "results": [
                {
                    "step": result.step,
                    "command": result.command,
                    "success": result.success,
                    "output_summary": result.output[:500],
                    "duration_ms": result.duration_ms,
                    "exit_code": result.exit_code,
                    "error": result.error[:500] if result.error else None,
                }
                for result in results
            ],
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _cleanup_old_done_reports(report_dir, feature_id)
        return report_path
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning(f"Failed to save done report for feature {feature_id}: {exc}")
        return None


def _format_failure_reason(results: List[AcceptanceTestResult]) -> str:
    """Build compact finish-pending reason from failed acceptance checks."""
    failed = [result for result in results if not result.success]
    if not failed:
        return "acceptance verification failed"

    reasons: List[str] = []
    for result in failed[:3]:
        reason = result.command
        if result.error:
            reason += f" -> {result.error[:120]}"
        reasons.append(reason)
    if len(failed) > 3:
        reasons.append(f"+{len(failed) - 3} more failures")
    return "; ".join(reasons)


def _validate_done_preconditions(
    data: Dict[str, Any],
    services: CompletionFlowServices,
) -> Tuple[bool, str, int, Optional[Dict[str, Any]]]:
    """Validate deterministic gate checks before `/prog done` execution."""
    current_id = data.get("current_feature_id")
    if current_id is None:
        tracker_role = str(data.get("tracker_role") or DEFAULT_TRACKER_ROLE)
        project_code = data.get("project_code")
        scope_hint = services.find_project_root_fn()
        return (
            False,
            "No active feature. Run /prog next first. "
            f"(scope={scope_hint}, tracker_role={tracker_role}, project_code={project_code})",
            1,
            None,
        )

    features = data.get("features", [])
    feature = next((item for item in features if item.get("id") == current_id), None)
    if not feature:
        return False, f"Feature {current_id} not found.", 4, None

    if feature.get("completed", False):
        return False, f"Feature {current_id} is already completed.", 5, feature

    workflow_state = data.get("workflow_state", {})
    phase = workflow_state.get("phase") if isinstance(workflow_state, dict) else None
    if phase != "execution_complete":
        return (
            False,
            f"Current workflow phase is '{phase}'. Required phase is 'execution_complete'.",
            2,
            feature,
        )

    return True, "", 0, feature


def _validate_completion_reconcile(
    data: Dict[str, Any], feature_id: int, services: CompletionFlowServices
) -> Tuple[bool, str, int]:
    """Block completion when reconcile reports state drift that needs repair."""
    reconcile_report = services.analyze_reconcile_state_fn(data) if services.analyze_reconcile_state_fn else {"diagnosis": None}
    diagnosis = reconcile_report.get("diagnosis")

    if diagnosis in {"scope_mismatch", "context_mismatch"}:
        return False, f"reconcile gate: {diagnosis}", 10

    if diagnosis == "needs_manual_review":
        current_id = data.get("current_feature_id")
        if current_id == feature_id:
            suggested = reconcile_report.get("recommended_next_step")
            if suggested in {"repair workflow_state", "clear invalid current_feature_id"}:
                return False, f"reconcile gate: needs_manual_review ({suggested})", 10

    return True, "", 0


def _validate_completion_plan_document(
    data: Dict[str, Any], feature_id: int, services: CompletionFlowServices
) -> Tuple[bool, str, int]:
    """Validate plan document content before completion gates close."""
    features = data.get("features", [])
    feature = next((item for item in features if item.get("id") == feature_id), None)
    if feature is None:
        return False, f"Feature {feature_id} not found", 4

    workflow_state = data.get("workflow_state")
    plan_path: Optional[str] = None
    if isinstance(workflow_state, dict):
        raw_plan_path = workflow_state.get("plan_path")
        if isinstance(raw_plan_path, str):
            normalized = raw_plan_path.strip()
            if normalized:
                plan_path = normalized

    if not plan_path:
        raw_feature_plan = feature.get("plan_path")
        if isinstance(raw_feature_plan, str):
            normalized_feature_plan = raw_feature_plan.strip()
            if normalized_feature_plan:
                plan_path = normalized_feature_plan

    if not plan_path:
        ai_metrics = feature.get("ai_metrics", {})
        workflow_path = (
            str(ai_metrics.get("workflow_path", "")).strip().lower()
            if isinstance(ai_metrics, dict)
            else ""
        )
        if workflow_path == "direct_tdd":
            return True, "", 0
        return False, "No plan_path found in workflow_state or feature metadata", 11

    if services.validate_plan_document_fn is None:
        return True, "", 0
    validation = services.validate_plan_document_fn(plan_path)
    if not validation.get("valid"):
        errors = validation.get("errors", [])
        if not errors:
            return False, "plan document validation failed", 11
        return False, "; ".join(str(item) for item in errors), 11

    return True, "", 0


def _finalize_completion_state_in_memory(
    data: Dict[str, Any], feature_id: int, services: CompletionFlowServices, commit_hash: Optional[str] = None
) -> Tuple[Dict[str, Any], bool]:
    """Mark feature completion in-memory only; caller owns all I/O."""
    features = data.get("features", [])
    feature = next((item for item in features if item.get("id") == feature_id), None)
    if feature is None:
        raise ValueError(f"Feature {feature_id} not found")

    if feature.get("completed"):
        return data, False

    ai_metrics = feature.get("ai_metrics", {})
    if not isinstance(ai_metrics, dict):
        ai_metrics = {}
    if not ai_metrics.get("finished_at"):
        now = datetime.now().astimezone()
        now_iso = now.isoformat().replace("+00:00", "Z")
        started_at = _parse_iso_timestamp(ai_metrics.get("started_at"))
        if not started_at:
            started_at = now
            ai_metrics["started_at"] = now_iso
        ai_metrics["finished_at"] = now_iso
        ai_metrics["duration_seconds"] = int(max(0, (now - started_at).total_seconds()))
    feature["ai_metrics"] = ai_metrics

    feature["completed"] = True
    feature["development_stage"] = "completed"
    feature["lifecycle_state"] = "verified"
    feature["completed_at"] = _iso_now()
    _clear_feature_defer_state(feature)
    _clear_feature_finish_pending(feature)
    feature["integration_status"] = "merged_and_cleaned"
    feature["finish_state_resolved_at"] = _iso_now()
    feature.pop("finish_state_resolved_reason", None)
    if commit_hash:
        feature["commit_hash"] = commit_hash

    workflow_state = data.get("workflow_state")
    if isinstance(workflow_state, dict):
        plan_path = workflow_state.get("plan_path")
        if isinstance(plan_path, str) and plan_path.strip():
            feature["plan_path"] = plan_path.strip()

    data["current_feature_id"] = None
    data.pop("workflow_state", None)
    if services.update_runtime_context_fn:
        services.update_runtime_context_fn(data, "finalize")

    return data, True


def _record_feature_completed_event(
    feature_id: int, feature_name: str, services: CompletionFlowServices, commit_hash: str = ""
) -> None:
    """Append feature_completed audit event for a real state transition only."""
    if services.record_feature_state_event_fn:
        services.record_feature_state_event_fn(
            event_type="feature_completed",
            feature_id=feature_id,
            feature_name=feature_name,
            extra_details={"commit_hash": commit_hash} if commit_hash else None,
        )


def _append_capability_memory(feature: Dict[str, Any], commit_hash: str, services: CompletionFlowServices) -> None:
    """Best-effort project memory append using project_memory module API."""
    try:
        import project_memory
        project_root = services.find_project_root_fn()
        memory_path = get_project_memory_path(project_root)

        payload = {
            "title": feature.get("name", "Unknown Feature"),
            "summary": f"Completed feature {feature.get('id')}: {feature.get('name', '')}",
            "tags": feature.get("change_spec", {}).get("categories", []),
            "confidence": 1.0,
            "source": {
                "origin": "prog_done",
                "feature_id": feature.get("id"),
                "commit_hash": commit_hash,
            },
        }
        memory, _, _ = project_memory.load_memory(path=memory_path)
        result = project_memory.append_capability(memory, payload)
        if result.get("status") == "inserted":
            project_memory.save_memory(memory, path=memory_path)
            return
        if result.get("status") == "deduped":
            return
        project_memory.save_memory(memory, path=memory_path)
    except Exception as exc:
        print(f"[DONE] Warning: capability memory append failed: {exc}", file=sys.stderr)


def _run_post_done_cleanup(ctx: dict, services: CompletionFlowServices, skip: bool = False) -> None:
    """Orchestrate post-done cleanup of worktree and feature branch.

    Called after _notify_parent_sync().  All steps are non-blocking; no
    exception propagates to cmd_done().

    Args:
        ctx: dict with keys branch, workspace_mode, worktree_path.
        skip: when True (--no-cleanup), print a notice and return immediately.
    """
    if skip:
        print("[DONE] --no-cleanup: skipping cleanup")
        return

    branch = ctx.get("branch", "")
    workspace_mode = ctx.get("workspace_mode", "unknown")
    worktree_path = ctx.get("worktree_path")

    if workspace_mode == "unknown":
        print("[CLEANUP] WARN: non-git context, skipping cleanup")
        return

    project_root = services.find_project_root_fn()

    if worktree_handler._is_worktree_dirty(worktree_path if workspace_mode == "worktree" else None, project_root=project_root):
        print("[CLEANUP] WARN: dirty worktree, skipping cleanup")
        return

    # Cache upstream info BEFORE deleting the local branch —
    # tracking metadata disappears once the branch is removed.
    remote, remote_branch = git_utils._resolve_upstream(branch, project_root=project_root)

    if workspace_mode == "worktree":
        git_utils._remove_worktree(worktree_path, project_root=project_root)
        git_utils._delete_local_branch(branch, project_root=project_root)
        git_utils._delete_remote_branch(remote, remote_branch, project_root=project_root)

    elif workspace_mode == "in_place":
        git_utils._delete_local_branch(branch, project_root=project_root)
        git_utils._delete_remote_branch(remote, remote_branch, project_root=project_root)


def _build_done_handoff_block(
    data: Dict[str, Any],
    project_root: str,
    services: CompletionFlowServices,
) -> Optional[str]:
    """Build the post-completion handoff block for `/prog done`."""
    next_feature = services.get_next_feature_fn() if services.get_next_feature_fn else None
    return progress_prompt_builders.build_done_handoff_block(data, next_feature, project_root)


def _build_project_completion_summary(
    data: Dict[str, Any],
    project_root: str,
) -> str:
    """Build a concise summary when no more pending features remain."""
    return progress_prompt_builders.build_project_completion_summary(data, project_root)


def _run_done_preflight(data: Dict[str, Any], services: CompletionFlowServices) -> Tuple[bool, list]:
    """Batch-validate all completion gates and return (all_passed, results)."""
    results: list = []

    # --- Gate 1: Preconditions ---
    valid, reason, code, feature = _validate_done_preconditions(data, services)
    results.append({"gate": 1, "name": "Preconditions", "passed": valid,
                    "reason": reason, "exit_code": code})
    if not valid and feature is None:
        # No feature object at all — nothing to evaluate for gates 2-9.
        return False, results

    if feature is None:
        # Gate 1 passed but feature is None (should not happen — defensive).
        return False, results

    feature_id = int(feature.get("id"))

    # --- Gate 2: Reconcile ---
    valid, reason, code = _validate_completion_reconcile(data, feature_id, services)
    results.append({"gate": 2, "name": "Reconcile State", "passed": valid,
                    "reason": reason, "exit_code": code})

    # --- Gate 3: Plan Document ---
    valid, reason, code = _validate_completion_plan_document(data, feature_id, services)
    results.append({"gate": 3, "name": "Plan Document", "passed": valid,
                    "reason": reason, "exit_code": code})

    # --- Gate 4: Sprint Ledger ---
    if not SPRINT_LEDGER_AVAILABLE:
        results.append({"gate": 4, "name": "Sprint Ledger", "passed": False,
                        "reason": "sprint_ledger module unavailable", "exit_code": 9})
    else:
        try:
            services.require_sprint_contract_fn(feature)
            results.append({"gate": 4, "name": "Sprint Ledger", "passed": True,
                            "reason": "", "exit_code": 0})
        except SprintLedgerError as exc:
            results.append({"gate": 4, "name": "Sprint Ledger", "passed": False,
                            "reason": str(exc), "exit_code": 9})

    # --- Gate 5: Acceptance Tests ---
    all_passed, test_results = _run_acceptance_tests(feature, services, run_all=True)
    if not all_passed:
        passed_n = sum(1 for r in test_results if r.success)
        reason = f"{passed_n}/{len(test_results)} passed"
    else:
        reason = "all passed"
    results.append({"gate": 5, "name": "Acceptance Tests", "passed": all_passed,
                    "reason": reason, "exit_code": 3 if not all_passed else 0})

    # Reload after acceptance, matching cmd_done line 9088-9094
    refreshed = services.load_progress_json_fn()
    gate_feat = None
    if refreshed:
        gate_feat = next((f for f in refreshed.get("features", [])
                          if f.get("id") == feature_id), None)

    if gate_feat is None:
        results.append({"gate": 6, "name": "Evaluator Gate", "passed": False,
                        "reason": f"feature {feature_id} not found after acceptance reload",
                        "exit_code": 4})
        results.append({"gate": 7, "name": "Review Gate", "passed": None,
                        "reason": "skipped (feature not found)", "exit_code": 0})
        results.append({"gate": 8, "name": "Ship Check", "passed": None,
                        "reason": "skipped (feature not found)", "exit_code": 0})
        results.append({"gate": 9, "name": "Finalization", "passed": None,
                        "reason": "skipped (destructive)", "exit_code": 0})
        return not any(r["passed"] is False for r in results), results

    # --- Gate 6: Evaluator ---
    eval_status = gate_feat.get("quality_gates", {}).get("evaluator", {}).get("status")
    if eval_status != "pass":
        results.append({"gate": 6, "name": "Evaluator Gate", "passed": False,
                        "reason": f"status={eval_status!r}", "exit_code": 6})
    else:
        results.append({"gate": 6, "name": "Evaluator Gate", "passed": True,
                        "reason": "", "exit_code": 0})

    # --- Gate 7: Reviews ---
    if not REVIEW_ROUTER_AVAILABLE:
        results.append({"gate": 7, "name": "Review Gate", "passed": True,
                        "reason": "review router unavailable; gate skipped", "exit_code": 0})
    else:
        copy_feat = copy.deepcopy(gate_feat)
        try:
            _initialize_reviews(copy_feat)
        except Exception as exc:
            results.append({"gate": 7, "name": "Review Gate", "passed": False,
                            "reason": f"review initialization failed: {exc}", "exit_code": 7})
        else:
            pending = _get_pending_lanes(copy_feat)
            if pending:
                results.append({"gate": 7, "name": "Review Gate", "passed": False,
                                "reason": f"pending lanes: {pending}", "exit_code": 7})
            else:
                results.append({"gate": 7, "name": "Review Gate", "passed": True,
                                "reason": "all required lanes passed", "exit_code": 0})

    # --- Gate 8: Ship Check ---
    ship_status = gate_feat.get("quality_gates", {}).get("ship_check", {}).get("status")
    if ship_status != "pass":
        results.append({"gate": 8, "name": "Ship Check", "passed": False,
                        "reason": f"status={ship_status!r}", "exit_code": 8})
    else:
        results.append({"gate": 8, "name": "Ship Check", "passed": True,
                        "reason": "", "exit_code": 0})

    # --- Gate 9: Finalization (not executed) ---
    results.append({"gate": 9, "name": "Finalization", "passed": None,
                    "reason": "skipped (destructive — only runs in full flow)",
                    "exit_code": 0})

    all_blocked = any(r["passed"] is False for r in results)
    return not all_blocked, results


def _print_preflight_report(results: list, feature_id, feature_name: str) -> None:
    """Print a formatted preflight report for all gate results."""
    passed_n = sum(1 for r in results if r["passed"] is True)
    failed_n = sum(1 for r in results if r["passed"] is False)
    skipped_n = sum(1 for r in results if r["passed"] is None)
    total = len(results)

    print("=" * 60)
    print(f"[PREFLIGHT] Feature {feature_id}: {feature_name}")
    print(f"[PREFLIGHT] {passed_n}/{total} gates passed", end="")
    if failed_n:
        print(f", {failed_n} FAILED", end="")
    if skipped_n:
        print(f", {skipped_n} SKIPPED", end="")
    print()
    print("=" * 60)

    def _icon(passed) -> str:
        if passed is True:
            return "PASS"
        if passed is False:
            return "FAIL"
        return "SKIP"

    for r in results:
        icon = _icon(r["passed"])
        print(f"  [{icon}] Gate {r['gate']}: {r.get('name', '')}")
        if r.get("reason"):
            print(f"       {r['reason']}")

    print("=" * 60)
    if failed_n:
        print("[PREFLIGHT] RESULT: BLOCKED — fix FAILED gates above"
              " before running `prog done`")
    else:
        print("[PREFLIGHT] RESULT: READY — all gates passed."
              " Run `prog done` to complete.")


def cmd_done(services: CompletionFlowServices, commit_hash=None, run_all: bool = False, skip_archive: bool = False,
             no_cleanup: bool = False, check_only: bool = False) -> int:
    """Close current feature through deterministic acceptance gatekeeping."""
    data = services.load_progress_json_fn()
    if not data:
        print("[DONE] No progress tracking found")
        return 4

    if check_only:
        all_passed, results = _run_done_preflight(data, services)
        feature_id_for_report = data.get("current_feature_id")
        if feature_id_for_report is not None and results:
            feat_for_report = next(
                (f for f in data.get("features", [])
                 if f.get("id") == feature_id_for_report), None)
            feature_name_for_report = (
                feat_for_report.get("name", f"Feature {feature_id_for_report}")
                if feat_for_report else "Unknown")
        else:
            feature_name_for_report = "N/A"
            feature_id_for_report = feature_id_for_report or 0
        _print_preflight_report(
            results, feature_id_for_report, feature_name_for_report)
        if all_passed:
            return 0
        # Return the first failing gate's exit code for script compatibility.
        for r in results:
            if r["passed"] is False:
                return r["exit_code"]
        return 1  # unreachable (all_passed was False, so some gate must have failed)

    valid, reason, code, feature = _validate_done_preconditions(data, services)
    if not valid:
        print(f"[DONE] BLOCKED: {reason}")
        return code

    assert feature is not None  # preconditions guarantee feature presence
    feature_id = int(feature.get("id"))
    feature_name = feature.get("name", f"Feature {feature_id}")

    valid, reason, code = _validate_completion_reconcile(data, feature_id, services)
    if not valid:
        print(f"[DONE] BLOCKED: {reason}", file=sys.stderr)
        return code

    valid, reason, code = _validate_completion_plan_document(data, feature_id, services)
    if not valid:
        print(f"[DONE] BLOCKED: plan document validation failed: {reason}", file=sys.stderr)
        return code

    if not SPRINT_LEDGER_AVAILABLE:
        print("[DONE] BLOCKED: sprint_ledger module unavailable.", file=sys.stderr)
        return 9

    try:
        services.require_sprint_contract_fn(feature)
    except SprintLedgerError as exc:
        print(f"[DONE] BLOCKED: {exc}", file=sys.stderr)
        return 9

    print(f"[DONE] Running acceptance tests for Feature {feature_id}: {feature_name}")

    all_passed, results = _run_acceptance_tests(feature, services, run_all=run_all)
    report_path = _save_done_test_report(
        feature_id=feature_id,
        feature_name=feature_name,
        results=results,
        success=all_passed,
        services=services,
    )
    if report_path:
        try:
            artifact_path = str(report_path.relative_to(services.find_project_root_fn()))
        except ValueError:
            artifact_path = str(report_path)
        try:
            passed_count = sum(1 for result in results if result.success)
            services.record_sprint_artifact_fn(
                feature_id=feature_id,
                phase="evaluation",
                artifact_path=artifact_path,
                metadata={
                    "success": bool(all_passed),
                    "passed": passed_count,
                    "total": len(results),
                    "run_all": bool(run_all),
                },
            )
        except SprintLedgerError as exc:
            print(
                f"[DONE] BLOCKED: failed to persist sprint ledger artifact: {exc}",
                file=sys.stderr,
            )
            return 9

    if not all_passed:
        refreshed = services.load_progress_json_fn()
        if refreshed:
            current_feature = next(
                (item for item in refreshed.get("features", []) if item.get("id") == feature_id),
                None,
            )
            if current_feature:
                current_feature["integration_status"] = FINISH_PENDING_STATE
                current_feature["finish_pending_reason"] = _format_failure_reason(results)
                current_feature["last_done_attempt_at"] = _iso_now()
                current_feature.pop("finish_state_resolved_at", None)
                current_feature.pop("finish_state_resolved_reason", None)
                services.save_progress_json_fn(refreshed)

        passed_count = sum(1 for result in results if result.success)
        total_count = len(results)
        print(f"[DONE] Acceptance failed ({passed_count}/{total_count} passed)")
        if report_path:
            try:
                relative_report = report_path.relative_to(services.find_project_root_fn())
            except ValueError:
                relative_report = report_path
            print(f"[DONE] Report: {relative_report}")
        return 3

    print("[DONE] Acceptance passed")

    gate_feat = None
    refreshed_for_gate = services.load_progress_json_fn()
    if refreshed_for_gate:
        gate_feat = next(
            (f for f in refreshed_for_gate.get("features", []) if f.get("id") == feature_id),
            None,
        )
    if gate_feat is None:
        print(f"[DONE] BLOCKED: feature {feature_id} not found during gate checks.", file=sys.stderr)
        return 4

    evaluator_payload = gate_feat.get("quality_gates", {}).get("evaluator", {})
    eval_status = evaluator_payload.get("status")
    if eval_status != "pass":
        print(
            f"[DONE] BLOCKED: evaluator gate not passed "
            f"(status={eval_status!r}). "
            "Run evaluator subagent and call _store_evaluator_result before /prog-done.",
            file=sys.stderr,
        )
        return 6

    # F-11: review gate — enforce existing review requirements before archiving.
    # Only check lanes when reviews have been explicitly initialized (required is
    # non-empty). When reviews have not been initialized yet, get_pending_lanes
    # returns [] safely (see review_router docstring), so the gate passes.
    if REVIEW_ROUTER_AVAILABLE:
        pending_lanes = _get_pending_lanes(gate_feat)
        if pending_lanes:
            print(
                f"[DONE] BLOCKED: pending reviews: {pending_lanes}. "
                "Run: prog review-pass --feature-id <id> --lane <lane>",
                file=sys.stderr,
            )
            return 7

    # PR-5: ship_check gate — must pass before archiving.
    # Only block when ship_check has been explicitly run and set to a non-pass state.
    ship_payload = gate_feat.get("quality_gates", {}).get("ship_check", {})
    ship_status = ship_payload.get("status")
    if ship_status is not None and ship_status != "pass":
        print(
            f"[DONE] BLOCKED: ship_check not passed (status={ship_status!r}). "
            f"Run `prog ship-check --feature-id {feature_id}` first.",
            file=sys.stderr,
        )
        return 8

    # Snapshot git context before finalize clears workflow_state.
    git_ctx = services.collect_git_context_fn() if services.collect_git_context_fn else {}
    cleanup_ctx = {
        "branch": git_ctx.get("branch", ""),
        "workspace_mode": git_ctx.get("workspace_mode", "unknown"),
        "worktree_path": git_ctx.get("worktree_path"),
    }

    resolved_commit = commit_hash or (services.get_head_commit_fn() if services.get_head_commit_fn else None)
    data_for_finalize = services.load_progress_json_fn()
    if not data_for_finalize:
        print("[DONE] Failed to load progress state before finalization", file=sys.stderr)
        return 4

    data_final, did_transition = _finalize_completion_state_in_memory(
        data_for_finalize, feature_id, services, commit_hash=resolved_commit
    )
    if not did_transition:
        print(f"[DONE] Feature {feature_id} already completed; no-op.")
        return 0

    services.save_progress_json_fn(data_final)
    services.save_progress_md_fn(services.generate_progress_md_fn(data_final))

    _record_feature_completed_event(feature_id, feature_name, services, resolved_commit or "")

    if not skip_archive and services.archive_feature_docs_fn is not None:
        try:
            archive_result = services.archive_feature_docs_fn(feature_id, feature_name)
            if archive_result.get("archived_files"):
                print(f"Archived {len(archive_result['archived_files'])} file(s)")
            if archive_result.get("errors"):
                print("Warning: Some files could not be archived (feature still marked complete)")
            data_post_archive = services.load_progress_json_fn()
            if data_post_archive:
                save_archive_record(feature_id, archive_result, services)
        except Exception as exc:
            logger.error(f"Archive failed but feature completed: {exc}")
            print("Warning: Document archiving failed but feature is marked complete")

    data_for_memory = services.load_progress_json_fn()
    if data_for_memory:
        feat_for_memory = next(
            (f for f in data_for_memory.get("features", []) if f.get("id") == feature_id),
            None,
        )
        if feat_for_memory is not None:
            _append_capability_memory(feat_for_memory, resolved_commit or "", services)

    data_final_check = services.load_progress_json_fn()
    if data_final_check and _is_project_fully_completed(data_final_check):
        try:
            if services.archive_current_progress_fn:
                services.archive_current_progress_fn(reason="completed")
        except Exception as exc:
            logger.error(f"Completed-run archive failed: {exc}")
            print("Warning: Completed-run archive failed, but active state will still be cleared.")
        data_post_reset = services.load_progress_json_fn()
        if data_post_reset:
            if services.reset_active_progress_fn:
                services.reset_active_progress_fn(data_post_reset)

    if services.auto_state_commit_fn:
        services.auto_state_commit_fn(f"F{feature_id}", "done")

    print(f"[DONE] Feature {feature_id} completed")
    if resolved_commit:
        print(f"[DONE] Commit: {resolved_commit}")
    if report_path:
        try:
            relative_report = report_path.relative_to(services.find_project_root_fn())
        except ValueError:
            relative_report = report_path
        print(f"[DONE] Report: {relative_report}")

    refreshed = services.load_progress_json_fn()
    completion_output = None
    if refreshed:
        project_root_str = str(services.find_project_root_fn().resolve())
        completion_output = _build_done_handoff_block(refreshed, project_root_str, services)
        if completion_output is None:
            completion_output = _build_project_completion_summary(refreshed, project_root_str)

    services.notify_parent_sync_fn("clear")
    try:
        _run_post_done_cleanup(cleanup_ctx, services, skip=no_cleanup)
    except Exception as exc:
        print(f"[CLEANUP] WARN: unexpected cleanup error (feature still completed): {exc}")

    if completion_output:
        print(completion_output)

    return 0


def complete_feature(feature_id, services: CompletionFlowServices, commit_hash=None, skip_archive=False):
    """Mark a feature as completed."""
    data = services.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)

    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    valid, reason, _ = _validate_completion_reconcile(data, feature_id, services)
    if not valid:
        print(f"Cannot complete feature: {reason}")
        return False

    resolved_commit = commit_hash or ""
    data, did_transition = _finalize_completion_state_in_memory(
        data,
        feature_id,
        services,
        commit_hash=resolved_commit if resolved_commit else None,
    )
    if not did_transition:
        return True

    services.save_progress_json_fn(data)
    services.save_progress_md_fn(services.generate_progress_md_fn(data))

    _record_feature_completed_event(
        feature_id,
        feature.get("name", f"Feature {feature_id}"),
        services,
        resolved_commit,
    )

    print(f"Completed feature: {feature.get('name', 'Unknown')}")
    if commit_hash:
        print(f"Recorded commit: {commit_hash}")

    # Archive documents (non-blocking)
    if not skip_archive and services.archive_feature_docs_fn is not None:
        try:
            feature_name = feature.get("name", f"Feature {feature_id}")
            print(f"\nArchiving documents for {feature_name}...")
            archive_result = services.archive_feature_docs_fn(feature_id, feature_name)

            if archive_result["archived_files"]:
                print(f"Archived {len(archive_result['archived_files'])} file(s)")

            # Save archive record regardless of individual file errors.
            refreshed = services.load_progress_json_fn()
            if refreshed:
                save_archive_record(feature_id, archive_result, services)

            if archive_result["errors"]:
                print(f"Warning: Some files could not be archived (feature still marked complete)")

        except Exception as e:
            # Archive failures should not prevent feature completion
            logger.error(f"Archive failed but feature completed: {e}")
            print(f"Warning: Document archiving failed but feature is marked complete")

        refreshed = services.load_progress_json_fn()
        if refreshed and _is_project_fully_completed(refreshed):
            try:
                if services.archive_current_progress_fn:
                    completed_archive = services.archive_current_progress_fn(reason="completed")
                    if completed_archive:
                        print(
                            "Archived completed run as "
                            f"{completed_archive.get('archive_id')} "
                            f"(reason={completed_archive.get('reason')})"
                        )
            except Exception as e:
                # Archive I/O can fail (mkdir, copy2, save_history).
                # Best-effort: log and continue — reset must still happen.
                logger.error(f"Completed-run archive failed: {e}")
                print(f"Warning: Completed-run archive failed, but active state will still be cleared.")

    refreshed = services.load_progress_json_fn()
    if refreshed:
        feat_for_memory = next((f for f in refreshed.get("features", []) if f.get("id") == feature_id), None)
        if feat_for_memory:
            _append_capability_memory(feat_for_memory, resolved_commit, services)

    # ── Outside if not skip_archive — always runs ──
    refreshed = services.load_progress_json_fn()
    if refreshed and _is_project_fully_completed(refreshed):
        if services.reset_active_progress_fn:
            services.reset_active_progress_fn(refreshed)

    return True
