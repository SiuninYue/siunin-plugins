#!/usr/bin/env python3
"""
Progress Manager - Core state management for Progress Tracker plugin.

This script handles initialization, status checking, and state updates for
feature-based progress tracking.

Usage:
    python3 progress_manager.py init [--force] [--confirm-destroy] <project_name>
    python3 progress_manager.py status
    python3 progress_manager.py check
    python3 progress_manager.py reconcile [--json]
    python3 progress_manager.py next-feature [--json] [--ack-planning-risk]
    python3 progress_manager.py list-archives [--limit <n>]
    python3 progress_manager.py restore-archive <archive_id> [--force]
    python3 progress_manager.py git-sync-check
    python3 progress_manager.py git-auto-preflight [--json]
    python3 progress_manager.py set-current <feature_id>
    python3 progress_manager.py validate-readiness <feature_id>
    python3 progress_manager.py validate-planning --feature-id <id> [--json]
    python3 progress_manager.py fix-readiness <feature_id> [--add-requirement <REQ-ID>] [--set-why <text>] [--add-acceptance <text>]
    python3 progress_manager.py set-development-stage <planning|developing|completed> [--feature-id <id>]
    python3 progress_manager.py complete <feature_id>
    python3 progress_manager.py done [--commit <hash>] [--run-all] [--skip-archive] [--no-cleanup] [--check]
    python3 progress_manager.py set-finish-state --feature-id <id> --status <merged_and_cleaned|pr_open|kept_with_reason> [--reason <text>]
    python3 progress_manager.py set-feature-ai-metrics <feature_id> --complexity-score <score> --selected-model <model> --workflow-path <path>
    python3 progress_manager.py complete-feature-ai-metrics <feature_id>
    python3 progress_manager.py auto-checkpoint
    python3 progress_manager.py sync-linked [--json] [--stale-after-hours <hours>]
    python3 progress_manager.py link-project --project-root <path> --code <CODE> [--parent-root <path>] [--json]
    python3 progress_manager.py validate-plan [--plan-path <path>]
    python3 progress_manager.py generate-direct-tdd-note
    python3 progress_manager.py add-feature <name> <test_steps...>
    python3 progress_manager.py update-feature <feature_id> <name> [test_steps...]
    python3 progress_manager.py defer (--all-pending|--feature-id <id>) --reason <text> [--defer-group <id>]
    python3 progress_manager.py resume (--all|--defer-group <id>)
    python3 progress_manager.py reset
"""

import argparse
import json
import os
import re
import shlex
import sys
import copy
import subprocess
import shutil
import logging
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set, Sequence, Callable

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

try:
    import importlib.util as _importlib_util
    _scripts_dir = Path(__file__).parent
    _spec = _importlib_util.spec_from_file_location(
        "wf_state_machine", _scripts_dir / "wf_state_machine.py"
    )
    _wf_sm = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_wf_sm)
    compute_next_action = _wf_sm.compute_next_action
except Exception:
    compute_next_action = None  # fail-open

from prog_paths import (
    PROGRESS_ARCHIVE_DIR,
    PROGRESS_HISTORY_JSON,
    ProjectRootResolutionError,
    ensure_storage_migrated,
    ensure_tracker_layout,
    get_checkpoints_path,
    get_project_memory_path,
    get_progress_archive_dir,
    get_progress_history_path,
    get_progress_json_path,
    get_state_dir,
    get_tracker_docs_root,
    rel_progress_path,
    resolve_target_project_root,
    find_project_root as _find_project_root_impl,
)
from contract_importer import ContractImporter, ContractImportError
import lock_manager
from lock_manager import (
    PROGRESS_LOCK_FILE,
    PROGRESS_LOCK_TIMEOUT_SECONDS,
    PROGRESS_LOCK_POLL_INTERVAL_SECONDS,
)
import state_io
from state_io import (
    LINKED_SNAPSHOT_SCHEMA_VERSION,
    TRACKER_ROLES,
    DEFAULT_TRACKER_ROLE,
    OWNER_ROLES,
    LIFECYCLE_STATES,
    CURRENT_SCHEMA_VERSION,
    _atomic_write_text,
    _default_linked_snapshot,
    _normalize_linked_schema,
    _normalize_route_schema,
    _default_sprint_contract,
    _default_quality_gates,
    _sync_reviews_pending_cache,
    _default_handoff,
    _default_owners,
    _default_change_spec,
    _default_acceptance_scenarios,
    _normalize_feature_owners,
    _normalize_feature_defer_state,
    _clear_feature_defer_state,
    _normalize_feature_contract,
    _normalize_optional_string,
    _normalize_ref_tokens,
)
def __getattr__(name: str) -> Any:
    """Forward lock state aliases to lock_manager to avoid stale references."""
    if name == "_PROGRESS_LOCK_HANDLES":
        return lock_manager._PROGRESS_LOCK_HANDLES
    if name == "_PROGRESS_LOCK_DEPTHS":
        return lock_manager._PROGRESS_LOCK_DEPTHS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
def _progress_lock_path(project_root: Optional[Path] = None) -> Path:
    root = project_root if project_root is not None else find_project_root()
    return lock_manager._progress_lock_path(project_root=root)
def _acquire_progress_lock(
    timeout_seconds: float = PROGRESS_LOCK_TIMEOUT_SECONDS,
    project_root: Optional[Path] = None,
) -> None:
    root = project_root if project_root is not None else find_project_root()
    return lock_manager._acquire_progress_lock(timeout_seconds=timeout_seconds, project_root=root)
def _release_progress_lock(project_root: Optional[Path] = None) -> None:
    root = project_root if project_root is not None else find_project_root()
    return lock_manager._release_progress_lock(project_root=root)
@contextmanager
def progress_transaction(
    timeout_seconds: float = PROGRESS_LOCK_TIMEOUT_SECONDS,
    project_root: Optional[Path] = None,
):
    root = project_root if project_root is not None else find_project_root()
    with lock_manager.progress_transaction(timeout_seconds=timeout_seconds, project_root=root):
        yield
progress_transaction.is_wrapper = True
import completion_flow
from completion_flow import FINISH_PENDING_STATE, _is_project_fully_completed
import progress_prompt_builders
import readiness_validator
from work_item_commands import (
    UPDATE_CATEGORIES,
    UPDATE_REFS_INLINE_LIMIT,
    UPDATE_SOURCES,
    WORKFLOW_PROFILE_DEFAULT,
    WORKFLOW_PROFILE_VALUES,
    WORK_ITEM_TAXONOMY,
)
from readiness_validator import ReadinessValidatorServices
try:
    import audit_log
except ImportError:  # pragma: no cover - defensive import
    audit_log = None

try:
    import evaluator_gate as evaluator_gate_mod
except ImportError:  # pragma: no cover - optional module
    evaluator_gate_mod = None

try:
    from review_router import (
        get_pending_lanes as _get_pending_lanes,
        initialize_reviews as _initialize_reviews,
        mark_review_passed as _mark_review_passed,
    )
    REVIEW_ROUTER_AVAILABLE = True
except ImportError:
    REVIEW_ROUTER_AVAILABLE = False

try:
    from ship_check import run_ship_check as _run_ship_check
    SHIP_CHECK_AVAILABLE = True
except ImportError:  # pragma: no cover - optional module
    SHIP_CHECK_AVAILABLE = False

try:
    from sprint_ledger import (
        SprintLedgerError,
        record as record_sprint_artifact,
        require_sprint_contract,
    )
    SPRINT_LEDGER_AVAILABLE = True
except ImportError:  # pragma: no cover - optional module
    SPRINT_LEDGER_AVAILABLE = False

    class SprintLedgerError(Exception):
        """Fallback sprint ledger error when module is unavailable."""

    def require_sprint_contract(feature: Dict[str, Any]) -> None:
        """No-op fallback when sprint_ledger module is not importable."""
        return None

    def record_sprint_artifact(**kwargs: Any) -> None:
        """No-op fallback when sprint_ledger module is not importable."""
        return None

# Import git_validator for secure Git operations
try:
    from git_validator import (
        safe_git_command,
        validate_commit_hash,
        GitCommandError,
        is_git_repository,
        get_git_root,
        is_working_directory_clean,
        get_current_commit_hash
    )
    GIT_VALIDATOR_AVAILABLE = True
except ImportError:
    # Fallback if git_validator is not available
    GIT_VALIDATOR_AVAILABLE = False
    GitCommandError = subprocess.CalledProcessError

PROGRESS_JSON = "progress.json"
PROGRESS_MD = "progress.md"
CHECKPOINTS_JSON = "checkpoints.json"
CHECKPOINT_MAX_ENTRIES = 50
CHECKPOINT_INTERVAL_SECONDS = 1800
# State files managed by progress-tracker (whitelist for auto-commit)
STATE_FILE_NAMES = [
    PROGRESS_JSON,
    CHECKPOINTS_JSON,
    PROGRESS_HISTORY_JSON,
    "sprint_ledger.jsonl",
    "status_summary.v1.json",
    "audit.log",
    "project_memory.json",
    "migration_log.json",
]
STATE_DIR_NAMES = [
    "test_reports",
    "progress_archive",
]
PROGRESS_ARCHIVE_MAX_ENTRIES = 200
STATUS_SUMMARY_FILE = "status_summary.v1.json"
STATUS_SUMMARY_LEGACY_FILE = "status_summary.json"
STATUS_SUMMARY_SCHEMA_VERSION = "status_summary.v1"
STATUS_SUMMARY_CORE_FIELDS = (
    "progress",
    "next_action",
    "plan_health",
    "risk_blocker",
    "recent_snapshot",
)

# Schema version and roles are imported from state_io
DEFAULT_LINKED_STATUS_STALE_HOURS = 24
ROOT_ROUTE_CODE = "ROOT"
DEVELOPMENT_STAGES = ("planning", "developing", "completed")
VALID_FINISH_STATES = ("merged_and_cleaned", "pr_open", "kept_with_reason")
# FINISH_PENDING_STATE is imported from completion_flow
# Canonical relative paths (from project root) that must never be moved or deleted
# by archive_feature_docs or any other done-flow mutation.
_IMMUTABLE_PROTECTED_RELPATHS: frozenset[str] = frozenset({
    "docs/progress-tracker/architecture/architecture.md",
})
from workflow_commands import RECONCILE_DIAGNOSES, RECONCILE_NEXT_STEPS
MUTATING_COMMANDS = {
    "init",
    "set-current",
    "fix-readiness",
    "set-development-stage",
    "complete",
    "done",
    "set-finish-state",
    "add-feature",
    "update-feature",
    "defer",
    "resume",
    "add-update",
    "set-feature-owner",
    "undo",
    "reset",
    "set-workflow-state",
    "update-workflow-task",
    "clear-workflow-state",
    "set-feature-ai-metrics",
    "complete-feature-ai-metrics",
    "auto-checkpoint",
    "sync-linked",
    "link-project",
    "route-select",
    "sync-runtime-context",
    "restore-archive",
    "add-bug",
    "add-task",
    "update-bug",
    "remove-bug",
    "prioritize",
    "set-queue",
    "discover-children",
    "reconcile-evaluator",
    "review-pass",
    "ship-check",
    "backfill-event",
    "generate-direct-tdd-note",
    "set-sprint-contract",
}
ROUTE_PREFLIGHT_EXEMPT_COMMANDS = {
    "init",
    "link-project",
    "route-select",
}

# Ghost-command alias table. Maps deprecated/non-existent command names to
# their correct replacements. Takes priority over edit-distance suggestions.
_GHOST_COMMAND_ALIASES: Dict[str, str] = {
    "start-task": "next --done",
}

# Bug field standards (for consistency)
BUG_REQUIRED_FIELDS = ["id", "description", "status", "priority", "created_at"]
BUG_OPTIONAL_FIELDS = [
    "root_cause", "fix_summary", "fix_commit_hash", "verified_working",
    "repro_steps", "workaround", "quick_verification", "scheduled_position",
    "updated_at", "investigation", "category"
]

# Configure logging for diagnostics
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


# Resolved project scope (set per process / explicit override only)
_PROJECT_ROOT_OVERRIDE: Optional[Path] = None
_REPO_ROOT: Optional[Path] = None
_STORAGE_READY_ROOT: Optional[Path] = None


def get_plugin_root():
    """
    Get the plugin root directory with multiple fallback mechanisms.

    Priority:
    1. Environment variable CLAUDE_PLUGIN_ROOT
    2. Relative to script location (progress_manager.py)
    3. Common plugin installation paths

    Returns:
        Path: The plugin root directory

    Raises:
        RuntimeError: If plugin root cannot be determined
    """
    # 1. Try environment variable
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        root = Path(env_root)
        if validate_plugin_root(root):
            logger.info(f"Using CLAUDE_PLUGIN_ROOT: {root}")
            return root
        else:
            logger.warning(f"CLAUDE_PLUGIN_ROOT is set but invalid: {env_root}")

    # 2. Try relative to script location
    script_path = Path(__file__).resolve()
    # Script is at: <plugin_root>/hooks/scripts/progress_manager.py
    # So plugin root is 3 levels up
    relative_root = script_path.parent.parent.parent
    if validate_plugin_root(relative_root):
        logger.info(f"Using script-relative path: {relative_root}")
        return relative_root

    # 3. Try common installation paths
    common_paths = [
        # User-level plugin installation
        Path.home() / ".claude" / "plugins" / "progress-tracker",
        # System-wide plugin installation
        Path("/usr/local/lib/claude/plugins/progress-tracker"),
        # Development directory (when working on the plugin itself)
        Path(__file__).resolve().parent.parent.parent.parent.parent,
    ]

    for path in common_paths:
        if validate_plugin_root(path):
            logger.info(f"Using common path: {path}")
            return path

    # If all else fails, raise an error with helpful message
    raise RuntimeError(
        "Cannot determine plugin root directory. "
        "Set CLAUDE_PLUGIN_ROOT environment variable or ensure plugin is properly installed. "
        f"Searched: {env_root if env_root else 'not set'}, {relative_root}, {common_paths}"
    )


def validate_plugin_root(path):
    """
    Validate that a path is a valid plugin root directory.

    A valid plugin root should contain:
    - hooks/hooks.json or hooks/scripts/progress_manager.py
    - skills/ directory (optional but recommended)

    Args:
        path: Path to validate

    Returns:
        bool: True if path appears to be a valid plugin root
    """
    path = Path(path)

    # Check if path exists
    if not path.exists():
        return False

    # Check for key plugin files
    has_hooks_json = (path / "hooks" / "hooks.json").exists()
    has_progress_manager = (path / "hooks" / "scripts" / "progress_manager.py").exists()
    has_skills = (path / "skills").exists()
    has_commands = (path / "commands").exists()

    # At minimum, should have the progress_manager script
    if has_progress_manager:
        return True

    # Or hooks.json if using direct script loading
    if has_hooks_json and (has_skills or has_commands):
        return True

    return False


def configure_project_scope(project_root_arg: Optional[str]) -> bool:
    """Resolve and lock the target project root for this process."""
    global _PROJECT_ROOT_OVERRIDE, _REPO_ROOT, _STORAGE_READY_ROOT
    try:
        target_root, repo_root = resolve_target_project_root(project_root_arg=project_root_arg)
    except ProjectRootResolutionError as exc:
        print(f"Error: {exc}")
        return False
    # Keep explicit override only when --project-root was provided.
    # Without explicit override we re-resolve from cwd each call, which avoids
    # stale cached roots in long-running test/session processes.
    _PROJECT_ROOT_OVERRIDE = target_root if project_root_arg else None
    _REPO_ROOT = repo_root
    _STORAGE_READY_ROOT = None
    return True


def find_project_root() -> Path:
    """
    Resolve target project root.

    Rules:
    - explicit --project-root (if provided)
    - plugin subtree auto-detection (plugins/<name>/...)
    - monorepo root without explicit scope => error
    - standalone repository => repo root
    """
    global _PROJECT_ROOT_OVERRIDE
    return _find_project_root_impl(override=_PROJECT_ROOT_OVERRIDE)


def _ensure_storage_ready() -> None:
    """Ensure new docs/progress-tracker layout exists and legacy data is migrated once."""
    global _STORAGE_READY_ROOT
    target_root = find_project_root()
    if _STORAGE_READY_ROOT is not None and _STORAGE_READY_ROOT == target_root:
        return
    ensure_tracker_layout(target_root)
    migration_result = ensure_storage_migrated(target_root)
    if migration_result.get("migrated"):
        logger.info(
            "Migrated legacy progress storage to docs/progress-tracker "
            f"for project root: {target_root}"
        )
    _STORAGE_READY_ROOT = target_root


def get_progress_dir() -> Path:
    """Get docs/progress-tracker/state directory for progress tracking."""
    _ensure_storage_ready()
    return get_state_dir(find_project_root())


def validate_plan_path(
    plan_path: Optional[str],
    require_exists: bool = False,
    target_root: Optional[Path] = None,
    *,
    find_project_root_fn: Optional[Callable[[], Path]] = None,
) -> Dict[str, Optional[str]]:
    """
    Validate workflow plan path shape and optional existence.

    Accepted formats:
    - docs/plans/<YYYY-MM-DD-name>.md
    - docs/superpowers/plans/<YYYY-MM-DD-name>.md  (writing-plans skill)
    """
    import doc_generator
    return doc_generator.validate_plan_path(
        plan_path=plan_path,
        require_exists=require_exists,
        target_root=target_root,
        find_project_root_fn=find_project_root_fn or find_project_root,
    )
validate_plan_path.is_wrapper = True


def _normalize_plan_path_cli_arg(
    plan_path: Optional[str], project_root: Optional[Path] = None
) -> Optional[str]:
    """
    Normalize a plan_path value coming from CLI argument.

    If the path is absolute and falls under the project root, convert it to a
    relative path so that ``validate_plan_path`` can accept it.  All other
    values are returned unchanged.
    """
    if not plan_path:
        return plan_path

    p = Path(plan_path)
    if not p.is_absolute():
        return plan_path

    root = project_root or find_project_root()
    try:
        relative = p.relative_to(root)
        return str(relative).replace("\\", "/")
    except ValueError:
        return plan_path


def validate_plan_document(plan_path: str, target_root: Optional[Path] = None) -> Dict[str, Any]:
    import doc_generator
    return doc_generator.validate_plan_document(
        plan_path,
        target_root=target_root,
        find_project_root_fn=find_project_root,
        validate_plan_path_fn=validate_plan_path,
    )
validate_plan_document.is_wrapper = True




def _iter_linked_project_specs(progress_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return route_sync._iter_linked_project_specs(progress_data)
_iter_linked_project_specs.is_wrapper = True


def _resolve_linked_project_root(
    raw_root: str,
    project_root: Path,
    repo_root: Path,
) -> Path:
    return route_sync._resolve_linked_project_root(raw_root, project_root, repo_root)
_resolve_linked_project_root.is_wrapper = True


def _get_main_repo_root(project_root: Path) -> Optional[Path]:
    return route_sync._get_main_repo_root(project_root)
_get_main_repo_root.is_wrapper = True


def _resolve_main_repo_path(project_root: Path) -> Path:
    """若在 worktree 内，把 worktree 路径翻译为主仓库等效路径；不在则原样返回。"""
    main_root = _get_main_repo_root(project_root)
    if main_root is None:
        return project_root.resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        )
        wt_root = Path(result.stdout.strip()).resolve()
        rel_path = project_root.resolve().relative_to(wt_root)
        return (main_root / rel_path).resolve()
    except Exception:
        return project_root.resolve()


def _count_feature_completion(features: Any) -> Tuple[int, int]:
    return route_sync._count_feature_completion(features)
_count_feature_completion.is_wrapper = True


def _is_linked_snapshot_stale(
    updated_at: Optional[str],
    now: datetime,
    stale_after_hours: int,
) -> bool:
    return route_sync._is_linked_snapshot_stale(updated_at, now, stale_after_hours)
_is_linked_snapshot_stale.is_wrapper = True


def collect_linked_project_statuses(
    progress_data: Dict[str, Any],
    *,
    project_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    now: Optional[datetime] = None,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
    active_routes: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    p_root = project_root if project_root is not None else find_project_root()
    r_root = repo_root if repo_root is not None else Path(_REPO_ROOT or p_root)
    return route_sync.collect_linked_project_statuses(
        progress_data,
        project_root=p_root,
        repo_root=r_root,
        now=now,
        stale_after_hours=stale_after_hours,
        active_routes=active_routes,
    )
collect_linked_project_statuses.is_wrapper = True


def sync_linked(
    output_json: bool = False,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
    repair_routes: bool = False,
) -> bool:
    """Refresh and persist linked project status snapshot under linked_snapshot.

    When repair_routes=True, also rebuilds active_routes from child
    current_feature_id: upserts entries for active features and removes entries
    for completed/deferred/absent features.
    """
    data = load_progress_json()
    if not data:
        payload = {"status": "error", "message": "No progress tracking found"}
        if output_json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(payload["message"])
        return False

    stale_window_hours = max(stale_after_hours, 0)
    statuses = collect_linked_project_statuses(
        data,
        stale_after_hours=stale_window_hours,
        active_routes=data.get("active_routes") or [],
    )

    linked_snapshot = data.get("linked_snapshot")
    if not isinstance(linked_snapshot, dict):
        linked_snapshot = {}

    linked_snapshot["schema_version"] = LINKED_SNAPSHOT_SCHEMA_VERSION
    linked_snapshot["updated_at"] = _iso_now()
    linked_snapshot["projects"] = statuses
    data["linked_snapshot"] = linked_snapshot

    repaired_routes: List[Dict[str, Any]] = []
    if repair_routes:
        project_root = find_project_root().resolve()
        repo_root = Path(_REPO_ROOT or project_root).resolve()
        linked_projects = data.get("linked_projects") or []
        for lp in linked_projects:
            if not isinstance(lp, dict):
                continue
            lp_code_raw = lp.get("project_code")
            lp_code = (
                _normalize_project_code(lp_code_raw)
                if isinstance(lp_code_raw, str) and lp_code_raw.strip()
                else None
            )
            if not lp_code:
                continue
            raw_root = lp.get("project_root") or lp.get("path") or lp.get("root")
            if not raw_root:
                continue
            child_root = _resolve_linked_project_root(str(raw_root).strip(), project_root, repo_root)
            child_data, _ = _load_progress_payload_at_root(child_root)
            if not isinstance(child_data, dict):
                _remove_active_route(data, lp_code)
                repaired_routes.append({"project_code": lp_code, "action": "removed", "reason": "child unreadable"})
                continue
            current_fid = child_data.get("current_feature_id")
            if current_fid is None:
                _remove_active_route(data, lp_code)
                repaired_routes.append({"project_code": lp_code, "action": "removed", "reason": "no current feature"})
                continue
            features = child_data.get("features") or []
            feature = next((f for f in features if isinstance(f, dict) and f.get("id") == current_fid), None)
            if feature is None or feature.get("completed", False) or feature.get("deferred", False):
                _remove_active_route(data, lp_code)
                repaired_routes.append({"project_code": lp_code, "action": "removed", "reason": "feature completed/deferred"})
            else:
                feature_ref = _format_route_feature_ref(current_fid, lp_code)
                _upsert_active_route(data, lp_code, feature_ref)
                repaired_routes.append({"project_code": lp_code, "action": "upserted", "feature_ref": feature_ref})

    _update_runtime_context(data, source="sync_linked")
    save_progress_json(data)
    save_progress_md("")

    ok_count = sum(1 for item in statuses if item.get("status") == "ok")
    missing_count = sum(1 for item in statuses if item.get("status") == "missing")
    invalid_count = sum(1 for item in statuses if item.get("status") == "invalid")
    stale_count = sum(1 for item in statuses if item.get("is_stale") is True)

    payload: Dict[str, Any] = {
        "status": "ok",
        "project_count": len(statuses),
        "ok_count": ok_count,
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "stale_count": stale_count,
        "stale_after_hours": stale_window_hours,
        "snapshot": linked_snapshot,
    }
    if repair_routes:
        payload["repair_routes_applied"] = True
        payload["repaired_routes"] = repaired_routes

    if output_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        msg = (
            "Synced linked snapshot: "
            f"{len(statuses)} projects (ok={ok_count}, missing={missing_count}, "
            f"invalid={invalid_count}, stale={stale_count})"
        )
        if repair_routes:
            msg += f" | repaired {len(repaired_routes)} route(s)"
        print(msg)
    return True


def _detect_parallel_active_routes(active_routes: List[Any]) -> List[Dict[str, Any]]:
    return route_sync._detect_parallel_active_routes(active_routes)
_detect_parallel_active_routes.is_wrapper = True


def _normalize_project_code(raw_code: str) -> Optional[str]:
    return route_sync._normalize_project_code(raw_code)
_normalize_project_code.is_wrapper = True


def _serialize_project_root_for_config(project_root: Path, repo_root: Path) -> str:
    return route_sync._serialize_project_root_for_config(project_root, repo_root, resolve_main_repo_path_fn=_resolve_main_repo_path)
_serialize_project_root_for_config.is_wrapper = True


def _load_progress_payload_at_root(project_root: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    return route_sync._load_progress_payload_at_root(project_root, apply_schema_defaults_fn=_apply_schema_defaults)
_load_progress_payload_at_root.is_wrapper = True


def _save_progress_payload_at_root(
    project_root: Path,
    data: Dict[str, Any],
    *,
    touch_updated_at: bool = True,
) -> None:
    """Persist progress payload + markdown for an explicit root."""
    with progress_transaction(project_root=project_root):
        ensure_tracker_layout(project_root)
        _apply_schema_defaults(data)
        if touch_updated_at:
            data["updated_at"] = _iso_now()
        _atomic_write_text(
            get_progress_json_path(project_root),
            json.dumps(data, indent=2, ensure_ascii=False),
        )
        state_io.save_progress_md(get_state_dir(project_root), "")


def _format_route_feature_ref(feature_id: int, project_code: str) -> str:
    return route_sync._format_route_feature_ref(feature_id, project_code)
_format_route_feature_ref.is_wrapper = True


def _upsert_active_route(
    parent_data: Dict[str, Any],
    project_code: str,
    feature_ref: str,
) -> None:
    route_sync._upsert_active_route(parent_data, project_code, feature_ref, now_str=_iso_now())
_upsert_active_route.is_wrapper = True


def _remove_active_route(parent_data: Dict[str, Any], project_code: str) -> None:
    route_sync._remove_active_route(parent_data, project_code)
_remove_active_route.is_wrapper = True


def _notify_parent_sync(route_event: str = "refresh") -> None:
    child_data = load_progress_json()
    if not isinstance(child_data, dict):
        return
    child_root = find_project_root().resolve()
    repo_root = Path(_REPO_ROOT or child_root).resolve()
    route_sync._notify_parent_sync(
        child_data=child_data,
        child_root=child_root,
        repo_root=repo_root,
        route_event=route_event,
        load_progress_payload_fn=_load_progress_payload_at_root,
        save_progress_payload_fn=_save_progress_payload_at_root,
        load_status_summary_projection_fn=load_status_summary_projection,
        iso_now_fn=_iso_now,
    )
_notify_parent_sync.is_wrapper = True


def link_project(
    child_project_root: Optional[str],
    code: str,
    *,
    label: Optional[str] = None,
    output_json: bool = False,
) -> bool:
    """Register a child tracker under linked_projects and route queue."""
    raw_child_root = str(child_project_root or "").strip()
    if not raw_child_root:
        message = (
            "Error: link-project requires child --project-root "
            "(example: prog link-project --project-root plugins/note-organizer --code NO)"
        )
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    normalized_code = _normalize_project_code(code)
    if normalized_code is None:
        message = (
            "Error: Invalid --code value. Use 1-32 chars matching "
            "[A-Z][A-Z0-9_]* (example: NO, APP2, CORE_API)."
        )
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    parent_root = find_project_root().resolve()
    repo_root = Path(_REPO_ROOT or parent_root).resolve()
    child_wt_root = _resolve_linked_project_root(raw_child_root, parent_root, repo_root)
    child_root = _resolve_main_repo_path(child_wt_root)

    if child_root == parent_root:
        message = "Error: Child project root cannot be the same as parent project root."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    child_data, child_error = _load_progress_payload_at_root(child_root)
    if child_data is None and child_wt_root != child_root:
        child_data, child_error = _load_progress_payload_at_root(child_wt_root)
    if child_data is None:
        message = child_error or "Error: Unable to load child progress tracker data."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(f"Error: {message}")
        return False

    child_role_raw = child_data.get("tracker_role")
    if isinstance(child_role_raw, str):
        child_role = child_role_raw.strip().lower()
    else:
        child_role = DEFAULT_TRACKER_ROLE
    if child_role not in TRACKER_ROLES:
        child_role = DEFAULT_TRACKER_ROLE

    child_code_raw = child_data.get("project_code")
    child_code = _normalize_project_code(child_code_raw) if isinstance(child_code_raw, str) else None

    payload: Optional[Dict[str, Any]] = None
    with progress_transaction():
        parent_data = load_progress_json()
        if not parent_data:
            message = "No progress tracking found. Use init first."
            if output_json:
                print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
            else:
                print(message)
            return False

        parent_linked_projects = parent_data.get("linked_projects")
        if not isinstance(parent_linked_projects, list):
            parent_linked_projects = []
        parent_has_child_entry = False
        for entry in parent_linked_projects:
            entry_root_raw: Optional[str]
            if isinstance(entry, dict):
                raw_value = entry.get("project_root") or entry.get("path") or entry.get("root")
                entry_root_raw = str(raw_value).strip() if raw_value is not None else None
            elif isinstance(entry, str):
                entry_root_raw = entry.strip()
            else:
                continue
            if not entry_root_raw:
                continue
            entry_root = _resolve_linked_project_root(entry_root_raw, parent_root, repo_root)
            if entry_root == child_root:
                parent_has_child_entry = True
                break

        if child_role == "parent":
            message = (
                "Error: Child project is already a parent tracker. "
                "Cannot link it as a child tracker."
            )
            if output_json:
                print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
            else:
                print(message)
            return False
        if (
            child_role == "child"
            and child_code
            and child_code != normalized_code
            and not parent_has_child_entry
        ):
            message = (
                "Error: Child project already linked with "
                f"project_code={child_code}. Use matching --code or unlink first."
            )
            if output_json:
                print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
            else:
                print(message)
            return False

        # Collect previous codes for migration before delegating to helper.
        previous_codes: Set[str] = set()
        linked_projects = parent_data.get("linked_projects")
        if isinstance(linked_projects, list):
            for entry in linked_projects:
                if isinstance(entry, dict):
                    raw_value = entry.get("project_root") or entry.get("path") or entry.get("root")
                    entry_root_raw = str(raw_value).strip() if raw_value is not None else None
                    entry_code_raw = entry.get("project_code")
                    if entry_root_raw:
                        entry_root = _resolve_linked_project_root(entry_root_raw, parent_root, repo_root)
                        entry_code = (
                            str(entry_code_raw).strip().upper()
                            if isinstance(entry_code_raw, str) and entry_code_raw.strip()
                            else None
                        )
                        if entry_code and entry_root == child_root and entry_code != normalized_code:
                            previous_codes.add(entry_code)

        # Delegate core registration to _link_child_to_parent.
        _link_child_to_parent(
            parent_data, parent_root, repo_root, child_root, normalized_code, label=label, child_wt_root=child_wt_root
        )

        # Post-registration: migrate previous_codes in routing_queue.
        routing_queue = parent_data.get("routing_queue")
        if not isinstance(routing_queue, list):
            routing_queue = []
        normalized_queue: List[str] = []
        seen_queue_codes: Set[str] = set()
        for item in routing_queue:
            if not isinstance(item, str):
                continue
            token = item.strip().upper()
            if not token:
                continue
            if token in previous_codes:
                continue
            if token in seen_queue_codes:
                continue
            seen_queue_codes.add(token)
            normalized_queue.append(token)
        parent_data["routing_queue"] = normalized_queue

        # Post-registration: migrate previous_codes in active_routes.
        active_routes = parent_data.get("active_routes")
        if not isinstance(active_routes, list):
            active_routes = []
        normalized_routes: List[Any] = []
        seen_route_keys: Set[Tuple[str, str, str]] = set()
        for route in active_routes:
            if not isinstance(route, dict):
                normalized_routes.append(route)
                continue

            updated_route = dict(route)
            route_code_raw = updated_route.get("project_code")
            route_code = (
                str(route_code_raw).strip().upper()
                if isinstance(route_code_raw, str) and route_code_raw.strip()
                else None
            )
            if route_code in previous_codes:
                route_code = normalized_code
            if route_code:
                updated_route["project_code"] = route_code

            dedupe_key: Optional[Tuple[str, str, str]] = None
            if route_code:
                feature_ref = str(updated_route.get("feature_ref") or "").strip()
                worktree_path = str(updated_route.get("worktree_path") or "").strip()
                dedupe_key = (route_code, feature_ref, worktree_path)
            if dedupe_key and dedupe_key in seen_route_keys:
                continue
            if dedupe_key:
                seen_route_keys.add(dedupe_key)
            normalized_routes.append(updated_route)
        parent_data["active_routes"] = normalized_routes

        _update_runtime_context(parent_data, source="link_project")
        save_progress_json(parent_data)
        save_progress_md("")

        # Derive output values from updated parent_data.
        configured_project_root = _serialize_project_root_for_config(child_root, repo_root)
        linked_entry = None
        for entry in parent_data.get("linked_projects", []):
            if isinstance(entry, dict) and entry.get("project_code") == normalized_code:
                linked_entry = entry
                break
        normalized_label = linked_entry.get("label", child_root.name) if linked_entry else child_root.name

        payload = {
            "status": "ok",
            "project_code": normalized_code,
            "parent_project_root": str(parent_root),
            "child_project_root": str(child_root),
            "linked_project": {
                "project_root": configured_project_root,
                "project_code": normalized_code,
                "label": normalized_label,
            },
            "routing_queue": normalized_queue,
            "active_routes": normalized_routes,
        }

    if payload is None:
        return False

    if output_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(
            "Linked child project "
            f"{payload['linked_project']['project_root']} as {normalized_code}. "
            f"routing_queue={payload['routing_queue']}"
        )
    return True


# ---------------------------------------------------------------------------
# Monorepo child discovery helpers (F10)
# ---------------------------------------------------------------------------


def _derive_plugin_code(plugin_name: str) -> str:
    import route_commands
    return route_commands._derive_plugin_code(plugin_name)
_derive_plugin_code.is_wrapper = True


def _generate_project_code(plugin_name: str, used_codes: Set[str]) -> str:
    import route_commands
    return route_commands._generate_project_code(plugin_name, used_codes)
_generate_project_code.is_wrapper = True


def _discover_plugin_catalog(
    repo_root: Path,
    parent_root: Path,
) -> Dict[str, List[Dict[str, Any]]]:
    import route_commands
    return route_commands._discover_plugin_catalog(repo_root, parent_root)
_discover_plugin_catalog.is_wrapper = True


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
    import route_commands
    return route_commands._link_child_to_parent(
        parent_data, parent_root, repo_root, child_root, code,
        label=label, append_to_queue=append_to_queue, child_wt_root=child_wt_root,
        load_progress_payload_at_root_fn=_load_progress_payload_at_root,
        save_progress_payload_at_root_fn=_save_progress_payload_at_root,
        resolve_main_repo_path_fn=_resolve_main_repo_path,
    )
_link_child_to_parent.is_wrapper = True


def _auto_discover_child_plugins(
    project_root: Path,
    repo_root: Path,
    parent_data: Dict[str, Any],
) -> Dict[str, Any]:
    import route_commands
    return route_commands._auto_discover_child_plugins(
        project_root, repo_root, parent_data,
        load_progress_payload_at_root_fn=_load_progress_payload_at_root,
        save_progress_payload_at_root_fn=_save_progress_payload_at_root,
        resolve_main_repo_path_fn=_resolve_main_repo_path,
    )
_auto_discover_child_plugins.is_wrapper = True


def discover_children(*, output_json: bool = False) -> bool:
    import route_commands
    return route_commands.discover_children(
        project_root=find_project_root(),
        output_json=output_json,
        load_progress_json_fn=load_progress_json,
        load_progress_payload_at_root_fn=_load_progress_payload_at_root,
        save_progress_json_fn=save_progress_json,
        save_progress_md_fn=save_progress_md,
        generate_progress_md_fn=generate_progress_md,
        update_runtime_context_fn=_update_runtime_context,
        save_progress_payload_at_root_fn=_save_progress_payload_at_root,
        resolve_main_repo_path_fn=_resolve_main_repo_path,
    )
discover_children.is_wrapper = True


def route_status(*, output_json: bool = False) -> bool:
    import route_commands
    return route_commands.route_status(
        output_json=output_json,
        load_progress_json_fn=load_progress_json,
    )
route_status.is_wrapper = True


def prioritize_route(code: str, *, output_json: bool = False) -> bool:
    import route_commands
    return route_commands.prioritize_route(
        code,
        output_json=output_json,
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        save_progress_md_fn=save_progress_md,
        generate_progress_md_fn=generate_progress_md,
        update_runtime_context_fn=_update_runtime_context,
    )
prioritize_route.is_wrapper = True


def set_routing_queue(
    codes: List[str],
    *,
    force: bool = False,
    output_json: bool = False,
) -> bool:
    import route_commands
    return route_commands.set_routing_queue(
        codes,
        force=force,
        output_json=output_json,
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        save_progress_md_fn=save_progress_md,
        generate_progress_md_fn=generate_progress_md,
        update_runtime_context_fn=_update_runtime_context,
    )
set_routing_queue.is_wrapper = True


def _resolve_repo_root(project_root: Path) -> Path:
    import route_commands
    return route_commands._resolve_repo_root(project_root)
_resolve_repo_root.is_wrapper = True


def route_select(
    project_code: str,
    *,
    feature_ref: Optional[str] = None,
    output_json: bool = False,
) -> bool:
    import route_commands
    return route_commands.route_select(
        project_code,
        project_root=find_project_root(),
        feature_ref=feature_ref,
        output_json=output_json,
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        save_progress_md_fn=save_progress_md,
        generate_progress_md_fn=generate_progress_md,
        update_runtime_context_fn=_update_runtime_context,
        collect_git_context_fn=collect_git_context,
    )
route_select.is_wrapper = True


def _make_readiness_validator_services() -> ReadinessValidatorServices:
    """Build the injected-services bundle for readiness_validator commands."""
    return ReadinessValidatorServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
    )


def validate_feature_readiness(feature: Dict[str, Any]) -> Dict[str, Any]:
    return readiness_validator.validate_feature_readiness(feature)
validate_feature_readiness.is_wrapper = True


def print_readiness_warnings(report: Dict[str, Any]) -> None:
    return readiness_validator.print_readiness_warnings(report)
print_readiness_warnings.is_wrapper = True


def print_readiness_error(feature: Dict[str, Any], report: Dict[str, Any]) -> None:
    return readiness_validator.print_readiness_error(feature, report)
print_readiness_error.is_wrapper = True


def validate_readiness_command(feature_id: int) -> int:
    return readiness_validator.validate_readiness_command(
        feature_id, services=_make_readiness_validator_services()
    )
validate_readiness_command.is_wrapper = True


def validate_planning_command(feature_id: int, output_json: bool = False) -> bool:
    return readiness_validator.validate_planning_command(
        feature_id,
        services=_make_readiness_validator_services(),
        output_json=output_json,
    )
validate_planning_command.is_wrapper = True


def fix_readiness_command(
    feature_id: int,
    *,
    add_requirement: Optional[str] = None,
    set_why: Optional[str] = None,
    add_acceptance: Optional[str] = None,
) -> bool:
    return readiness_validator.fix_readiness_command(
        feature_id,
        services=_make_readiness_validator_services(),
        add_requirement=add_requirement,
        set_why=set_why,
        add_acceptance=add_acceptance,
    )
fix_readiness_command.is_wrapper = True


def import_contract_for_feature(feature_id: int) -> Optional[Dict[str, Any]]:
    """Import feature contract from deterministic docs/progress-tracker/contracts path."""
    importer = ContractImporter(find_project_root())
    return importer.import_for_feature(feature_id)


def _is_feature_deferred(feature: Dict[str, Any]) -> bool:
    """Return whether a feature is currently deferred.

    Delegates to progress_prompt_builders._is_deferred as the single source of truth.
    """
    return progress_prompt_builders._is_deferred(feature)


def _make_workflow_commands_services():
    import workflow_commands

    return workflow_commands.WorkflowCommandsServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        update_runtime_context_fn=_update_runtime_context,
        update_execution_context_fn=_update_execution_context,
        build_runtime_context_fn=build_runtime_context,
        validate_plan_path_fn=validate_plan_path,
        validate_plan_document_fn=validate_plan_document,
        find_project_root_fn=find_project_root,
        get_progress_dir_fn=get_progress_dir,
        load_checkpoints_fn=load_checkpoints,
        latest_checkpoint_entry_for_feature_fn=_latest_checkpoint_entry_for_feature,
        build_checkpoint_context_fn=_build_checkpoint_context,
    )


def analyze_reconcile_state(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Analyze tracker drift vs implementation evidence and return stable diagnostics."""
    import workflow_commands

    return workflow_commands.analyze_reconcile_state_command(
        data, svc=_make_workflow_commands_services()
    )
analyze_reconcile_state.is_wrapper = True


def reconcile(output_json: bool = False) -> bool:
    """Print reconcile diagnostics and suggested next step."""
    import workflow_commands

    return workflow_commands.reconcile_command(
        output_json=output_json,
        svc=_make_workflow_commands_services(),
    )
reconcile.is_wrapper = True


def _apply_schema_defaults(data: Dict[str, Any]) -> None:
    """Backfill backward-compatible defaults for evolving schema fields."""
    migrated = state_io._apply_schema_defaults_core(data)
    if migrated is not None:
        old_version, new_version = migrated
        _append_audit_event(
            event_type="schema_migration",
            details={"from": old_version, "to": new_version},
        )


def load_progress_json(progress_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load the progress.json file."""
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.load_progress_json(
        progress_dir=dir_path,
        apply_schema_defaults=_apply_schema_defaults,
    )


def _iso_now() -> str:
    """Return current local timestamp with trailing Z for compatibility."""
    return datetime.now().isoformat() + "Z"


def _append_audit_event(
    *,
    event_type: str,
    feature_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort append for non-FSM audit events."""
    if audit_log is None:
        return

    try:
        project_root = str(find_project_root())
        record: Dict[str, Any] = {
            "id": audit_log.generate_audit_id(project_root=project_root),
            "tx_id": audit_log.generate_tx_id(),
            "timestamp": _iso_now(),
            "event_type": event_type,
            "details": details or {},
        }
        if feature_id is not None:
            record["feature_id"] = feature_id
        audit_log.append_audit_record(record, project_root=project_root)
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("Failed to append audit record for %s: %s", event_type, exc)


def record_feature_state_event(
    event_type: str,
    feature_id: Optional[int],
    feature_name: Optional[str],
    extra_details: Optional[Dict[str, Any]] = None,
) -> None:
    """向当前项目的 audit.log 追加特征状态变更事件。

    使用 find_project_root() 确定写入路径，与 progress_manager 的其余路径一致，
    避免跨 plugin 时写入错误的 audit.log。

    Args:
        event_type: 必须在 ALLOWED_EVENT_TYPES 白名单内
        feature_id: 特征 ID（全局事件如 tracker_reset 传 None）
        feature_name: 特征名称（用于可读性，写入 details）
        extra_details: 额外详情（可选）
    """
    if audit_log is None:
        return

    # 使用与 _append_audit_event 相同的 project_root 解析逻辑
    effective_project_root = str(find_project_root())

    try:
        details: Dict[str, Any] = {}
        if feature_name:
            details["feature_name"] = feature_name
        if extra_details:
            details.update(extra_details)

        record: Dict[str, Any] = {
            "id": audit_log.generate_audit_id(project_root=effective_project_root),
            "tx_id": audit_log.generate_tx_id(),
            "timestamp": _iso_now(),
            "event_type": event_type,
        }
        if feature_id is not None:
            record["feature_id"] = feature_id
        if details:
            record["details"] = details

        audit_log.append_audit_record(record, project_root=effective_project_root)
    except ValueError as e:
        # ValueError 来自白名单校验（未知 event_type）—— 这是编程错误，应冒泡
        raise
    except Exception as e:
        # I/O 写失败不能静默吞掉：audit.log 是事实源，写入失败意味着状态不一致
        # 调用方（done/undo/reset）必须感知失败，否则 audit.log 丢事件但命令仍返回成功
        print(f"[audit] ERROR: Failed to record '{event_type}' event: {e}")
        raise


def cmd_reconcile_state(
    check_only: bool = False,
    auto_commit: bool = False,
) -> Dict[str, Any]:
    """通过 audit.log 事件回放检测并修复 progress.json 的 drift。"""
    import workflow_commands

    return workflow_commands.cmd_reconcile_state_command(
        check_only=check_only,
        auto_commit=auto_commit,
        svc=_make_workflow_commands_services(),
    )
cmd_reconcile_state.is_wrapper = True


def find_backfill_candidates(
    feature_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """找出已完成但 audit.log 缺少 feature_completed 事件的 feature。

    幂等性保证：已有 feature_completed（含 backfilled=True 的）也不是候选。

    Returns:
        [{"feature_id": int, "feature_name": str, "completed_at": str}]
    """
    data = load_progress_json()
    if not data:
        return []

    completed_in_audit: set = set()
    if audit_log is not None:
        effective_root = str(find_project_root())
        all_records = audit_log.read_audit_log(ascending=True, project_root=effective_root)

        # 幂等性须考虑 reset/project_completed 边界：
        # 只看最后一次 tracker_reset 或 project_completed 之后的 feature_completed
        # 边界之前的完成事件不应阻止边界之后合法的 backfill
        BOUNDARY_EVENT_TYPES = {"tracker_reset", "project_completed"}
        last_reset_idx = -1
        for i, r in enumerate(all_records):
            if r.get("event_type") in BOUNDARY_EVENT_TYPES:
                last_reset_idx = i

        for r in all_records[last_reset_idx + 1:]:
            if r.get("event_type") == "feature_completed" and r.get("feature_id") is not None:
                completed_in_audit.add(r["feature_id"])

    return [
        {
            "feature_id": f["id"],
            "feature_name": f.get("name", f"Feature {f['id']}"),
            "completed_at": f.get("completed_at", "unknown"),
        }
        for f in data.get("features", [])
        if f.get("completed", False)
        and (feature_id is None or f["id"] == feature_id)
        and f["id"] not in completed_in_audit
    ]


def cmd_backfill_event(
    feature_id: Optional[int] = None,
    yes: bool = False,
) -> Dict[str, Any]:
    """为已完成但缺少 feature_completed 审计事件的 feature 补录事件。

    幂等：已有 feature_completed（含 backfilled）的 feature 不重复写入。
    """
    if audit_log is None:
        print("[backfill-event] audit_log module unavailable")
        return {"written": 0, "candidates": 0, "cancelled": False}

    candidates = find_backfill_candidates(feature_id=feature_id)

    if not candidates:
        print("[backfill-event] No candidates. All completed features have audit events.")
        return {"written": 0, "candidates": 0, "cancelled": False}

    print(f"[backfill-event] {len(candidates)} candidate(s) missing feature_completed events:\n")
    effective_root = str(find_project_root())

    preview_events = []
    for c in candidates:
        ts = c["completed_at"] if c["completed_at"] != "unknown" else _iso_now()
        preview_events.append((c, ts))
        print(f"  Feature {c['feature_id']}: {c['feature_name']}")
        print(f"    → feature_completed  backfilled=true  timestamp={ts}\n")

    if not yes:
        answer = input(
            f"Write {len(preview_events)} backfill event(s) to audit.log? [y/N] "
        ).strip().lower()
        if answer != "y":
            print("[backfill-event] Cancelled.")
            return {"written": 0, "candidates": len(candidates), "cancelled": True}

    written = 0
    for c, ts in preview_events:
        try:
            event = {
                "id": audit_log.generate_audit_id(project_root=effective_root),
                "tx_id": audit_log.generate_tx_id(),
                "timestamp": ts,
                "event_type": "feature_completed",
                "feature_id": c["feature_id"],
                "backfilled": True,
                "backfill_reason": "reconciled from existing progress state",
                "details": {"feature_name": c["feature_name"]},
            }
            audit_log.append_audit_record(event, project_root=effective_root)
            written += 1
            print(f"[backfill-event] Written: F{c['feature_id']} feature_completed")
        except Exception as e:
            print(f"[backfill-event] ERROR: F{c['feature_id']}: {e}")

    print(f"[backfill-event] Done. {written}/{len(candidates)} written.")
    return {"written": written, "candidates": len(candidates), "cancelled": False}


def cmd_install_git_hooks() -> Dict[str, Any]:
    """将 post-merge hook 安装到当前项目的 git hooks 目录。

    使用 `git rev-parse --git-path hooks` 获取 hooks 路径，
    正确支持 worktree（.git 是文件而非目录的场景）。
    """
    import stat

    repo_root = find_project_root()

    # 通过 git 查询 hooks 路径：worktree 下 .git 是文件，不是目录
    # git rev-parse --git-path hooks 在两种情况下均返回正确路径
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            capture_output=True, text=True, timeout=10,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            msg = f"git rev-parse --git-path hooks failed: {result.stderr.strip()}"
            print(f"[install-git-hooks] ERROR: {msg}")
            return {"installed": False, "hook_path": None, "error": msg}

        hooks_path = result.stdout.strip()
        git_hooks_dir = Path(hooks_path)
        if not git_hooks_dir.is_absolute():
            git_hooks_dir = repo_root / git_hooks_dir
        git_hooks_dir.mkdir(exist_ok=True, parents=True)
    except FileNotFoundError:
        msg = "git not found in PATH"
        print(f"[install-git-hooks] ERROR: {msg}")
        return {"installed": False, "hook_path": None, "error": msg}
    except Exception as e:
        msg = f"Failed to resolve git hooks directory: {e}"
        print(f"[install-git-hooks] ERROR: {msg}")
        return {"installed": False, "hook_path": None, "error": msg}

    hooks_to_install = [
        ("post_merge_hook.sh", "post-merge"),
        (os.path.join("..", "pre-commit"), "pre-commit"),
    ]

    installed = []
    for src_rel, hook_name in hooks_to_install:
        source = Path(__file__).parent / src_rel
        source = source.resolve()
        if not source.exists():
            msg = f"Hook source not found: {source}"
            print(f"[install-git-hooks] ERROR: {msg}")
            return {"installed": False, "hook_path": None, "error": msg, "installed_hooks": installed}

        target = git_hooks_dir / hook_name
        target.write_text(source.read_text())
        current_mode = target.stat().st_mode
        target.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"[install-git-hooks] Installed: {target}")
        installed.append(str(target))

    return {"installed": True, "hook_path": installed[0], "error": None, "installed_hooks": installed}


def _store_evaluator_result(feature_id: int, result: Any) -> None:
    """PR-3: persist evaluator assessment into quality_gates.evaluator."""
    with progress_transaction():
        data = load_progress_json()
        if data is None:
            raise ValueError("progress.json not found")
        feat = next((f for f in data.get("features", []) if f.get("id") == feature_id), None)
        if feat is None:
            raise ValueError(f"feature {feature_id} not found")
        feat.setdefault("quality_gates", {})
        feat["quality_gates"]["evaluator"] = result.to_quality_gate_payload()

        current_root = find_project_root()
        main_root = _resolve_main_repo_path(current_root)
        if main_root.resolve() != current_root.resolve():
            with progress_transaction(project_root=main_root):
                main_data, err = _load_progress_payload_at_root(main_root)
                if main_data is not None:
                    main_feat = next((f for f in main_data.get("features", []) if f.get("id") == feature_id), None)
                    if main_feat is not None:
                        main_feat.setdefault("quality_gates", {})
                        main_feat["quality_gates"]["evaluator"] = result.to_quality_gate_payload()
                        _save_progress_payload_at_root(main_root, main_data)
                    else:
                        logger.warning("Feature %s not found in main repo tracker at %s", feature_id, main_root)
                else:
                    logger.warning("Could not load main repo tracker at %s: %s", main_root, err)

                save_progress_json(data)
        else:
            save_progress_json(data)
        _append_audit_event(
            event_type="evaluator_assessment",
            feature_id=feature_id,
            details={"status": result.status, "score": result.score},
        )


def _emit(data: Dict[str, Any], as_json: bool) -> None:
    import evaluator_gateway
    return evaluator_gateway._emit(data, as_json)
_emit.is_wrapper = True


def reconcile_evaluator(
    feature_id: Optional[int] = None,
    output_json: bool = False,
) -> int:
    import evaluator_gateway
    return evaluator_gateway.reconcile_evaluator(
        feature_id=feature_id,
        output_json=output_json,
        progress_dir=get_progress_dir(),
        load_progress_json_fn=load_progress_json,
        store_evaluator_result_fn=_store_evaluator_result,
        append_audit_event_fn=_append_audit_event,
        evaluator_gate_mod=evaluator_gate_mod,
        emit_fn=_emit,
    )
reconcile_evaluator.is_wrapper = True


def save_progress_json(
    data: Dict[str, Any],
    touch_updated_at: bool = True,
    progress_dir: Optional[Path] = None,
) -> None:
    """Save data to progress.json file with optional updated_at touch and migration."""
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    with progress_transaction():
        return state_io.save_progress_json(
            progress_dir=dir_path,
            data=data,
            touch_updated_at=touch_updated_at,
            apply_schema_defaults=_apply_schema_defaults,
            now_fn=_iso_now,
        )


def load_progress_md(progress_dir: Optional[Path] = None) -> Optional[str]:
    """Deprecated: progress.md is no longer maintained."""
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.load_progress_md(progress_dir=dir_path)


def save_progress_md(content: str, progress_dir: Optional[Path] = None) -> None:
    """Deprecated: remove stale progress.md instead of writing it."""
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.save_progress_md(progress_dir=dir_path, content=content)


def _slugify(text: Optional[str], fallback: str = "project") -> str:
    """Create a filesystem-safe slug from free-form text."""
    if not text:
        return fallback
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:48] if slug else fallback


def _load_progress_history() -> List[Dict[str, Any]]:
    """Load archived progress metadata from progress_history.json."""
    history_path = get_progress_dir() / PROGRESS_HISTORY_JSON
    if not history_path.exists():
        return []
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_progress_history(entries: List[Dict[str, Any]]) -> None:
    """Persist archived progress metadata."""
    with progress_transaction():
        progress_dir = get_progress_dir()
        progress_dir.mkdir(parents=True, exist_ok=True)
        history_path = progress_dir / PROGRESS_HISTORY_JSON
        payload = json.dumps(
            entries[-PROGRESS_ARCHIVE_MAX_ENTRIES :], indent=2, ensure_ascii=False
        )
        _atomic_write_text(history_path, payload)


def _make_archive_id(project_name: str, reason: Optional[str] = None) -> str:
    """Build a unique archive identifier."""
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    archive_id = f"{timestamp}-{_slugify(project_name)}"
    reason_slug = _slugify(reason, fallback="") if reason else ""
    if reason_slug:
        archive_id = f"{archive_id}-{reason_slug}"
    return archive_id


def _resolve_unique_archive_id(
    base_archive_id: str,
    archive_dir: Path,
    history: List[Dict[str, Any]],
) -> str:
    """Ensure archive IDs remain unique across history and on-disk artifacts."""
    existing_ids = {
        str(entry.get("archive_id")).strip()
        for entry in history
        if isinstance(entry, dict) and entry.get("archive_id")
    }

    candidate = base_archive_id
    suffix = 2
    while candidate in existing_ids or any(archive_dir.glob(f"{candidate}.*")):
        candidate = f"{base_archive_id}-{suffix}"
        suffix += 1
    return candidate


def _copy_archive_artifact(
    source_path: Path,
    archive_dir: Path,
    archive_id: str,
    *,
    kind: str,
    suffix: str,
) -> Optional[Dict[str, str]]:
    """Copy one state artifact into archive storage using standardized naming."""
    if not source_path.exists():
        return None

    archive_name = f"{archive_id}.{suffix}"
    archive_path = archive_dir / archive_name
    shutil.copy2(source_path, archive_path)

    return {
        "kind": kind,
        "source_path": rel_progress_path(source_path.name),
        "archive_path": f"{PROGRESS_ARCHIVE_DIR}/{archive_name}",
    }


def archive_current_progress(reason: str) -> Optional[Dict[str, Any]]:
    """
    Archive the current active progress files before destructive operations.

    Returns metadata for the created archive entry, or None when no active
    progress files exist.
    """
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if not json_path.exists():
        return None

    active_data = load_progress_json() if json_path.exists() else {}
    if not isinstance(active_data, dict):
        active_data = {}

    project_name = active_data.get("project_name", "unknown-project")
    archive_dir = progress_dir / PROGRESS_ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    history = _load_progress_history()
    base_archive_id = _make_archive_id(project_name, reason=reason)
    archive_id = _resolve_unique_archive_id(base_archive_id, archive_dir, history)

    archived_artifacts: List[Dict[str, str]] = []

    for source_path, kind, suffix in (
        (json_path, "progress_json", "progress.json"),
        (progress_dir / STATUS_SUMMARY_FILE, "status_summary_v1", "status-summary.v1.json"),
        (
            progress_dir / STATUS_SUMMARY_LEGACY_FILE,
            "status_summary_legacy",
            "status-summary.legacy.json",
        ),
    ):
        artifact = _copy_archive_artifact(
            source_path,
            archive_dir,
            archive_id,
            kind=kind,
            suffix=suffix,
        )
        if artifact:
            archived_artifacts.append(artifact)

    artifact_by_kind = {
        item["kind"]: item["archive_path"]
        for item in archived_artifacts
        if isinstance(item, dict) and isinstance(item.get("kind"), str)
    }

    features = active_data.get("features", [])
    if not isinstance(features, list):
        features = []
    completed_features = sum(1 for f in features if isinstance(f, dict) and f.get("completed"))

    entry: Dict[str, Any] = {
        "archive_id": archive_id,
        "archived_at": _iso_now(),
        "reason": reason,
        "project_name": project_name,
        "total_features": len(features),
        "completed_features": completed_features,
        "current_feature_id": active_data.get("current_feature_id"),
        "progress_json": artifact_by_kind.get("progress_json"),
        "status_summary_v1": artifact_by_kind.get("status_summary_v1"),
        "status_summary_legacy": artifact_by_kind.get("status_summary_legacy"),
        "archived_artifacts": archived_artifacts,
    }

    history.append(entry)
    _save_progress_history(history)
    return entry


def _reset_active_progress(data: Dict[str, Any]) -> None:
    """Clear active progress state after all features are completed.

    Attempts to record ``project_completed`` as a best-effort audit boundary;
    failure does NOT block clearing active state.  Callers that also archive
    the completed run (e.g. ``cmd_done``) provide a complementary boundary in
    ``progress_history.json``.

    Args:
        data: The in-memory progress dict (mutated in place and saved to disk).
    """
    # 1. Best-effort: write audit boundary event (reconcile uses this as a
    #    cycle marker; when absent, backfill across cycle boundaries may
    #    misattribute events if feature IDs are reused).
    try:
        record_feature_state_event(
            event_type="project_completed",
            feature_id=None,
            feature_name=None,
        )
    except Exception as exc:
        print(
            f"[DONE] WARNING: Failed to write project_completed audit event. "
            f"State will still be cleared; completed-run archive, when present, "
            f"preserves the active snapshot. Reconcile may not see an audit boundary. "
            f"Error: {exc}"
        )

    # 2. Clear tracked collections.
    data["features"] = []
    data["bugs"] = []
    data["updates"] = []
    data["retrospectives"] = []

    # 3. Clear current IDs and workflow state.
    data["current_feature_id"] = None
    data["current_bug_id"] = None
    data.pop("workflow_state", None)

    # 4. Reset runtime_context work fields (preserve structure, clear work).
    runtime_context = data.get("runtime_context")
    if isinstance(runtime_context, dict):
        runtime_context.update({
            "current_feature_id": None,
            "workflow_phase": None,
            "current_task": None,
            "total_tasks": None,
            "next_action": None,
        })

    # 5. Update timestamp.
    data["updated_at"] = _iso_now()

    # 6. Save cleared state and remove stale progress.md.
    save_progress_json(data)
    save_progress_md("")

    print("Active progress cleared — project state is now 0/0.")


# _is_project_fully_completed is imported from completion_flow


def list_archives(limit: int = 20) -> bool:
    """List archived progress snapshots."""
    history = _load_progress_history()
    if not history:
        print("No progress archives found.")
        return True

    safe_limit = max(1, limit)
    print(f"\n## Progress Archives (latest {safe_limit})")
    for entry in list(reversed(history))[:safe_limit]:
        archive_id = entry.get("archive_id", "unknown")
        project_name = entry.get("project_name", "Unknown Project")
        reason = entry.get("reason", "unknown")
        archived_at = entry.get("archived_at", "unknown")
        completed = entry.get("completed_features", 0)
        total = entry.get("total_features", 0)
        print(
            f"- [{archive_id}] {project_name} | reason={reason} | "
            f"progress={completed}/{total} | archived_at={archived_at}"
        )
    return True


def restore_archive(archive_id: str, force: bool = False) -> bool:
    """Restore an archived progress snapshot into active progress files."""
    history = _load_progress_history()
    target = next((entry for entry in history if entry.get("archive_id") == archive_id), None)
    if not target:
        print(f"Archive '{archive_id}' not found.")
        return False

    progress_dir = get_progress_dir()
    active_json = progress_dir / PROGRESS_JSON
    has_active = active_json.exists()

    if has_active and not force:
        print("Active progress tracking exists. Use --force to overwrite current progress files.")
        return False

    if has_active and force:
        archive_current_progress(reason=f"pre_restore:{archive_id}")

    json_rel = target.get("progress_json")
    if not json_rel:
        print(f"Archive '{archive_id}' does not contain progress.json snapshot.")
        return False

    source_json = progress_dir / json_rel
    if not source_json.exists():
        print(f"Archived progress.json not found: {source_json}")
        return False

    progress_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_json, active_json)
    save_progress_md("")

    print(f"Restored archive: {archive_id}")
    return True


def determine_complexity_bucket(score: int) -> str:
    """Map a 0-100 complexity score to simple/standard/complex buckets."""
    if score <= 37:
        return "simple"
    if score <= 62:
        return "standard"
    return "complex"


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


import git_utils
from git_utils import RUNTIME_CONTEXT_COMPARE_KEYS
import worktree_handler
import route_sync
import workspace_entropy


def _normalize_context_path(value: Optional[str]) -> Optional[str]:
    return git_utils._normalize_context_path(value)


def collect_git_context() -> Dict[str, Any]:
    return git_utils.collect_git_context(project_root=find_project_root())
collect_git_context.is_wrapper = True


def build_runtime_context(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    return git_utils.build_runtime_context(
        data=data,
        source=source,
        project_root=find_project_root(),
        now_str=_iso_now(),
        collect_git_context_fn=collect_git_context,
    )


def build_execution_context(source: str) -> Dict[str, Any]:
    return git_utils.build_execution_context(
        source=source,
        project_root=find_project_root(),
        now_str=_iso_now(),
        collect_git_context_fn=collect_git_context,
    )


def _runtime_context_fingerprint(ctx: Optional[Dict[str, Any]]) -> Tuple[Any, ...]:
    return git_utils._runtime_context_fingerprint(ctx)


def _update_runtime_context(data: Dict[str, Any], source: str, force: bool = False) -> bool:
    return git_utils._update_runtime_context(
        data=data,
        source=source,
        project_root=find_project_root(),
        now_str=_iso_now(),
        force=force,
        collect_git_context_fn=collect_git_context,
    )


def _update_execution_context(workflow_state: Dict[str, Any], source: str) -> None:
    return git_utils._update_execution_context(
        workflow_state=workflow_state,
        source=source,
        project_root=find_project_root(),
        now_str=_iso_now(),
        collect_git_context_fn=collect_git_context,
    )


def compare_contexts(
    expected: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    return git_utils.compare_contexts(expected, current)


def _format_context_summary(context: Optional[Dict[str, Any]]) -> str:
    return git_utils._format_context_summary(context)


def _latest_checkpoint_entry(checkpoints: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the most recent checkpoint entry (append semantics => last entry)."""
    if not isinstance(checkpoints, dict):
        return None
    entries = checkpoints.get("entries")
    if not isinstance(entries, list) or not entries:
        return None
    last = entries[-1]
    return last if isinstance(last, dict) else None


def _latest_checkpoint_entry_for_feature(
    checkpoints: Optional[Dict[str, Any]], feature_id: Optional[int]
) -> Optional[Dict[str, Any]]:
    """Return the most recent checkpoint entry for the given feature."""
    if feature_id is None or not isinstance(checkpoints, dict):
        return None
    entries = checkpoints.get("entries")
    if not isinstance(entries, list) or not entries:
        return None
    for entry in reversed(entries):
        if isinstance(entry, dict) and entry.get("feature_id") == feature_id:
            return entry
    return None


def _build_checkpoint_context(entry: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Adapt a checkpoint entry to the context comparison shape."""
    if not isinstance(entry, dict):
        return None
    return {
        "workspace_mode": entry.get("workspace_mode"),
        "worktree_path": entry.get("worktree_path"),
        "project_root": entry.get("worktree_path"),
        "git_dir": None,
        "branch": entry.get("branch"),
        "upstream": entry.get("upstream"),
    }


def load_checkpoints(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load checkpoints from docs/progress-tracker/state/checkpoints.json."""
    import state_io
    checkpoints_path = path or (get_progress_dir() / CHECKPOINTS_JSON)
    return state_io.load_checkpoints_from_file(checkpoints_path)
load_checkpoints.is_wrapper = True


def save_checkpoints(data: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Save checkpoints to docs/progress-tracker/state/checkpoints.json."""
    with progress_transaction():
        progress_dir = get_progress_dir()
        progress_dir.mkdir(parents=True, exist_ok=True)
        checkpoints_path = path or (progress_dir / CHECKPOINTS_JSON)
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        _atomic_write_text(checkpoints_path, payload)


def _read_json_dict(path: Path) -> Optional[Dict[str, Any]]:
    from summary_projector import _read_json_dict as _impl
    return _impl(path)
_read_json_dict.is_wrapper = True


def _status_source_snapshot(path: Path, rel_path: str) -> Dict[str, Any]:
    from summary_projector import _status_source_snapshot as _impl
    return _impl(path, rel_path)
_status_source_snapshot.is_wrapper = True


def _status_summary_source_fingerprint(target_root: Path) -> Dict[str, Any]:
    from summary_projector import _status_summary_source_fingerprint as _impl
    return _impl(target_root)
_status_summary_source_fingerprint.is_wrapper = True


def _load_progress_data_for_summary(progress_path: Path) -> Dict[str, Any]:
    from summary_projector import _load_progress_data_for_summary as _impl
    return _impl(progress_path, apply_schema_defaults_fn=_apply_schema_defaults)
_load_progress_data_for_summary.is_wrapper = True


def _format_relative_time_for_summary(iso_timestamp: Optional[str]) -> str:
    from summary_projector import _format_relative_time_for_summary as _impl
    return _impl(iso_timestamp)
_format_relative_time_for_summary.is_wrapper = True


def _normalize_feature_stage_for_summary(feature: Dict[str, Any]) -> str:
    from summary_projector import _normalize_feature_stage_for_summary as _impl
    return _impl(feature)
_normalize_feature_stage_for_summary.is_wrapper = True


def _stage_label_for_summary(stage: Optional[str]) -> Optional[str]:
    from summary_projector import _stage_label_for_summary as _impl
    return _impl(stage)
_stage_label_for_summary.is_wrapper = True


def _determine_next_action_for_summary(
    features: List[Dict[str, Any]], progress_data: Dict[str, Any]
) -> Dict[str, Any]:
    from summary_projector import _determine_next_action_for_summary as _impl
    return _impl(features, progress_data)
_determine_next_action_for_summary.is_wrapper = True


def _check_plan_health_for_summary(
    progress_data: Dict[str, Any], target_root: Path
) -> Dict[str, Any]:
    from summary_projector import _check_plan_health_for_summary as _impl
    return _impl(
        progress_data,
        target_root,
        validate_plan_path_fn=validate_plan_path,
        validate_plan_document_fn=validate_plan_document,
    )
_check_plan_health_for_summary.is_wrapper = True


def _check_risk_blocker_for_summary(progress_data: Dict[str, Any]) -> Dict[str, Any]:
    from summary_projector import _check_risk_blocker_for_summary as _impl
    return _impl(progress_data)
_check_risk_blocker_for_summary.is_wrapper = True


def _load_recent_snapshot_for_summary(
    checkpoints_data: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    from summary_projector import _load_recent_snapshot_for_summary as _impl
    return _impl(checkpoints_data)
_load_recent_snapshot_for_summary.is_wrapper = True


def _build_status_summary_core(
    progress_data: Dict[str, Any],
    checkpoints_data: Dict[str, Any],
    target_root: Path,
) -> Dict[str, Any]:
    from summary_projector import _build_status_summary_core as _impl
    return _impl(
        progress_data,
        checkpoints_data,
        target_root,
        validate_plan_path_fn=validate_plan_path,
        validate_plan_document_fn=validate_plan_document,
    )
_build_status_summary_core.is_wrapper = True


def _extract_projection_source_fingerprint(
    projection: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    from summary_projector import _extract_projection_source_fingerprint as _impl
    return _impl(projection)
_extract_projection_source_fingerprint.is_wrapper = True


def _projection_has_required_core_fields(projection: Dict[str, Any]) -> bool:
    from summary_projector import _projection_has_required_core_fields as _impl
    return _impl(projection)
_projection_has_required_core_fields.is_wrapper = True


def _projection_needs_rebuild(
    projection: Optional[Dict[str, Any]],
    current_inputs: Dict[str, Any],
) -> bool:
    from summary_projector import _projection_needs_rebuild as _impl
    return _impl(projection, current_inputs)
_projection_needs_rebuild.is_wrapper = True


def _legacy_summary_migration_info(legacy_path: Path) -> Optional[Dict[str, Any]]:
    from summary_projector import _legacy_summary_migration_info as _impl
    return _impl(legacy_path)
_legacy_summary_migration_info.is_wrapper = True


def _resolve_status_summary_target_root(project_root: Optional[str]) -> Path:
    from summary_projector import _resolve_status_summary_target_root as _impl
    return _impl(project_root)
_resolve_status_summary_target_root.is_wrapper = True


def get_status_summary_projection_path(project_root: Optional[str] = None) -> Path:
    """Return status summary projection path for the resolved target root."""
    from summary_projector import get_status_summary_projection_path as _impl
    return _impl(project_root)
get_status_summary_projection_path.is_wrapper = True


def _build_status_summary_projection(
    target_root: Path,
    current_inputs: Dict[str, Any],
    migration_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from summary_projector import _build_status_summary_projection as _impl
    return _impl(
        target_root,
        current_inputs,
        apply_schema_defaults_fn=_apply_schema_defaults,
        load_checkpoints_fn=load_checkpoints,
        validate_plan_path_fn=validate_plan_path,
        validate_plan_document_fn=validate_plan_document,
        migration_info=migration_info,
    )
_build_status_summary_projection.is_wrapper = True


def load_status_summary_projection(
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load shared status summary projection with drift detection and self-healing.

    The projection is persisted at docs/progress-tracker/state/status_summary.v1.json
    and rebuilt automatically when source files drift, projection is missing/corrupt,
    or schema/core fields mismatch.
    """
    from summary_projector import load_status_summary_projection as _impl
    return _impl(
        project_root,
        apply_schema_defaults_fn=_apply_schema_defaults,
        load_checkpoints_fn=load_checkpoints,
        validate_plan_path_fn=validate_plan_path,
        validate_plan_document_fn=validate_plan_document,
    )
load_status_summary_projection.is_wrapper = True


def auto_checkpoint() -> bool:
    """Create a lightweight checkpoint snapshot every 30 minutes of active work."""
    data = load_progress_json()
    if not data:
        return True

    current_feature_id = data.get("current_feature_id")
    if current_feature_id is None:
        return True

    checkpoints = load_checkpoints()
    now = datetime.now().astimezone()
    last_checkpoint = _parse_iso_timestamp(checkpoints.get("last_checkpoint_at"))

    if last_checkpoint and (now - last_checkpoint).total_seconds() < CHECKPOINT_INTERVAL_SECONDS:
        return True

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == current_feature_id), None)
    workflow_state = data.get("workflow_state", {})
    git_context = collect_git_context()

    checkpoint_entry = {
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "feature_id": current_feature_id,
        "feature_name": feature.get("name", "Unknown") if feature else "Unknown",
        "phase": workflow_state.get("phase", "unknown"),
        "plan_path": workflow_state.get("plan_path"),
        "current_task": workflow_state.get("current_task"),
        "total_tasks": workflow_state.get("total_tasks"),
        "next_action": workflow_state.get("next_action"),
        "workspace_mode": git_context.get("workspace_mode"),
        "worktree_path": git_context.get("worktree_path"),
        "branch": git_context.get("branch"),
        "upstream": git_context.get("upstream"),
        "reason": "auto_interval",
    }

    entries = checkpoints.get("entries", [])
    entries.append(checkpoint_entry)
    max_entries = checkpoints.get("max_entries", CHECKPOINT_MAX_ENTRIES)
    if len(entries) > max_entries:
        entries = entries[-max_entries:]

    save_checkpoints(
        {
            "last_checkpoint_at": checkpoint_entry["timestamp"],
            "max_entries": max_entries,
            "entries": entries,
        }
    )

    print(f"Auto-checkpoint saved for feature {current_feature_id}")
    return True


def _cmd_wf_auto_driver() -> bool:
    """
    wf-auto-driver 子命令：在文件锁内计算并写回 pending_action。

    流程（原子）：
    1. 读取 progress.json
    2. 检查 current_feature_id 和 workflow_state
    3. compute_next_action(phase, context)
    4. 写回 workflow_state.pending_action

    幂等：相同 phase 重复调用结果不变。
    """
    try:
        import importlib.util
        _scripts_dir = Path(__file__).parent
        spec = importlib.util.spec_from_file_location(
            "wf_state_machine", _scripts_dir / "wf_state_machine.py"
        )
        _wf_sm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_wf_sm)
        compute_next_action = _wf_sm.compute_next_action
    except Exception:
        return True  # fail-open：模块不存在时静默退出

    data = load_progress_json()
    if not data:
        return True

    current_id = data.get("current_feature_id")
    if current_id is None:
        return True

    workflow_state = data.get("workflow_state")
    if not workflow_state or not isinstance(workflow_state, dict):
        return True

    phase = workflow_state.get("phase")
    context = {
        "completed_tasks": workflow_state.get("completed_tasks") or [],
        "total_tasks": workflow_state.get("total_tasks") or 0,
    }

    pending_action = compute_next_action(phase, context)
    if pending_action is None:
        return True

    # 在锁内原子写回
    from lifecycle_state_machine import acquire_lock
    state_dir = get_progress_dir()
    lock_path = state_dir / "progress.lock"
    progress_path = state_dir / "progress.json"

    with acquire_lock(lock_path):
        fresh = load_progress_json()
        if not fresh:
            return True
        wf = fresh.get("workflow_state")
        if not wf or not isinstance(wf, dict):
            return True
        wf["pending_action"] = pending_action
        _atomic_write_text(progress_path, json.dumps(fresh, indent=2, ensure_ascii=False))

    return True


def init_tracking(project_name, features=None, force=False, confirm_destroy=False):
    """
    Initialize progress tracking for a project.

    Args:
        project_name: Name of the project to track
        features: Optional list of feature dicts with keys: name, test_steps
        force: Force re-initialization even if tracking exists
        confirm_destroy: Required when force=True and completed features exist
    """
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if json_path.exists() and not force:
        existing = load_progress_json()
        if existing:
            print(
                f"Progress tracking already exists for project: {existing.get('project_name', 'Unknown')}"
            )
            print(f"Location: {progress_dir}")
            print("Use --force to re-initialize")
            return False

    archived_entry = None
    existing_parent_root: Optional[str] = None
    if force:
        existing = load_progress_json()
        if isinstance(existing, dict):
            if not confirm_destroy:
                raw_features = existing.get("features")
                feature_list = raw_features if isinstance(raw_features, list) else []
                completed_count = sum(
                    1 for f in feature_list
                    if isinstance(f, dict) and bool(f.get("completed", False))
                )
                if completed_count > 0:
                    project = existing.get("project_name", "unknown")
                    print(
                        f"ERROR: {completed_count} completed feature(s) detected in "
                        f"'{project}'. Refusing to overwrite real project data.\n"
                        "Pass confirm_destroy=True (API) or --confirm-destroy (CLI) to proceed."
                    )
                    return False
            raw = existing.get("parent_project_root")
            if isinstance(raw, str) and raw.strip():
                existing_parent_root = raw.strip()
        archived_entry = archive_current_progress(reason="reinitialize")

    # Detect parent tracker role: if the target root has a plugins/ directory,
    # this is a monorepo root that will act as a mixed-host parent.
    target_root = find_project_root()
    is_parent_root = (target_root / "plugins").is_dir()

    # Create initial progress structure
    now = datetime.now().isoformat() + "Z"
    data = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "project_name": project_name,
        "created_at": now,
        "updated_at": now,
        "features": features or [],
        "current_feature_id": None,
        "settings": {"auto_state_commit": True},
    }
    if existing_parent_root:
        data["parent_project_root"] = existing_parent_root

    # Parent tracker initialization (CONSTRAINT-002, CONSTRAINT-003)
    if is_parent_root:
        data["tracker_role"] = "parent"
        data["project_code"] = ROOT_ROUTE_CODE
        data["routing_queue"] = [ROOT_ROUTE_CODE]

    save_progress_json(data)
    save_progress_md("")

    # Parent discovery: auto-discover child plugins after parent data is saved
    discovered_count = 0
    if is_parent_root:
        try:
            repo_root = _resolve_repo_root(target_root)
            discover_result = _auto_discover_child_plugins(target_root, repo_root, data)
            discovered_count = len(discover_result.get("added_codes", []))
            if discovered_count > 0:
                # Re-save with discovered children
                save_progress_json(data)
        except Exception as exc:
            logger.warning(f"Child discovery during init failed: {exc}")

    print(f"Initialized progress tracking for: {project_name}")
    print(f"Location: {progress_dir}")
    if is_parent_root:
        print(f"Role: parent (mixed-host monorepo root)")
        print(f"Project code: {ROOT_ROUTE_CODE}")
    if archived_entry:
        print(
            "Archived previous progress as "
            f"{archived_entry.get('archive_id')} "
            f"(reason={archived_entry.get('reason')})"
        )
    if features:
        print(f"Added {len(features)} features")
    _notify_parent_sync()
    return True


def _make_status_command_services():
    """Build a StatusCommandServices bundle wiring progress_manager callbacks."""
    from status_commands import StatusCommandServices  # type: ignore[import-untyped]
    return StatusCommandServices(
        load_progress_json_fn=load_progress_json,
        find_project_root_fn=find_project_root,
        load_checkpoints_fn=load_checkpoints,
        apply_schema_defaults_fn=_apply_schema_defaults,
        validate_plan_path_fn=validate_plan_path,
        validate_plan_document_fn=validate_plan_document,
        analyze_reconcile_state_fn=analyze_reconcile_state,
        load_progress_history_fn=_load_progress_history,
        collect_git_context_fn=collect_git_context,
    )


def _build_status_handoff_block(
    data: Dict[str, Any],
    completed: int,
    total: int,
    project_root: str,
) -> Optional[str]:
    from status_commands import _build_status_handoff_block as _impl  # type: ignore[import-untyped]
    return _impl(
        data, completed, total, project_root,
        services=_make_status_command_services(),
    )
_build_status_handoff_block.is_wrapper = True


def _build_done_handoff_block(data: Dict[str, Any], project_root: str) -> Optional[str]:
    return completion_flow._build_done_handoff_block(data, project_root, _make_completion_flow_services())
_build_done_handoff_block.is_wrapper = True


def _build_project_completion_summary(data: Dict[str, Any], project_root: str) -> str:
    return completion_flow._build_project_completion_summary(data, project_root)
_build_project_completion_summary.is_wrapper = True


def _display_root_dashboard(
    data: Dict[str, Any],
    project_root: Path,
    repo_root: Path,
    output_json: bool = False,
) -> bool:
    from status_commands import _display_root_dashboard as _impl  # type: ignore[import-untyped]
    return _impl(
        data, project_root, repo_root,
        services=_make_status_command_services(),
        output_json=output_json,
    )
_display_root_dashboard.is_wrapper = True


def _get_stale_bugs(data: dict, now: datetime) -> List[dict]:
    from status_commands import _get_stale_bugs as _impl  # type: ignore[import-untyped]
    return _impl(data, now)
_get_stale_bugs.is_wrapper = True


def status(output_json: bool = False) -> bool:
    """Display current progress status."""
    from status_commands import status as _impl  # type: ignore[import-untyped]
    return _impl(services=_make_status_command_services(), output_json=output_json)
status.is_wrapper = True


def _run_git(args: List[str], cwd: Optional[str] = None, timeout: int = 5) -> Tuple[int, str, str]:
    return git_utils._run_git(args, cwd, timeout)
_run_git.is_wrapper = True


def _get_dirty_state_files(project_root: Optional[Path] = None) -> List[Path]:
    root = project_root if project_root is not None else find_project_root()
    return git_utils._get_dirty_state_files(project_root=root)


def _git_commit_state(
    state_files: List[Path], msg: str, project_root: Optional[Path] = None
) -> Optional[str]:
    root = project_root if project_root is not None else find_project_root()
    return git_utils._git_commit_state(state_files, msg, project_root=root)


def _auto_state_commit(ref: str, event: str) -> Optional[str]:
    return git_utils._auto_state_commit(
        ref=ref,
        event=event,
        project_root=find_project_root(),
        progress_dir=get_progress_dir(),
        apply_schema_defaults=_apply_schema_defaults,
    )


def _parse_worktree_list_output(output: str) -> List[Dict[str, str]]:
    return worktree_handler._parse_worktree_list_output(output)
_parse_worktree_list_output.is_wrapper = True


def _extract_branch_name_from_worktree_ref(ref: Optional[str]) -> Optional[str]:
    return worktree_handler._extract_branch_name_from_worktree_ref(ref)
_extract_branch_name_from_worktree_ref.is_wrapper = True


def _count_branch_commits_behind(
    branch: str,
    target_branch: str,
    project_root: Path,
) -> Optional[int]:
    return worktree_handler._count_branch_commits_behind(branch, target_branch, project_root=project_root)
_count_branch_commits_behind.is_wrapper = True


def _find_existing_worktree_candidates_for_feature(
    *,
    repo_root: Path,
    tracker_project_root: Path,
    current_worktree: Path,
    current_feature_id: Optional[int],
) -> List[Dict[str, Any]]:
    return worktree_handler._find_existing_worktree_candidates_for_feature(
        repo_root=repo_root,
        tracker_project_root=tracker_project_root,
        current_worktree=current_worktree,
        current_feature_id=current_feature_id,
    )
_find_existing_worktree_candidates_for_feature.is_wrapper = True


def _detect_default_branch(project_root: Optional[Path] = None) -> Optional[str]:
    root = project_root if project_root is not None else find_project_root()
    return git_utils._detect_default_branch(project_root=root)
_detect_default_branch.is_wrapper = True


def _git_squash_close_task(
    task_id: str,
    branch: str,
    project_root: Optional[Path] = None,
    base_branch: Optional[str] = None,
    task_name: Optional[str] = None,
) -> Tuple[bool, str]:
    root = project_root if project_root is not None else find_project_root()
    return git_utils._git_squash_close_task(
        task_id=task_id,
        branch=branch,
        project_root=root,
        base_branch=base_branch,
        task_name=task_name,
    )


def _local_and_origin_ref_candidates(ref: str) -> Tuple[str, ...]:
    return worktree_handler._local_and_origin_ref_candidates(ref)
_local_and_origin_ref_candidates.is_wrapper = True


def _is_branch_merged_into(branch: str, target: str) -> bool:
    return worktree_handler._is_branch_merged_into(branch, target, project_root=find_project_root())
_is_branch_merged_into.is_wrapper = True


def analyze_git_sync_risks() -> Dict[str, Any]:
    return git_utils.analyze_git_sync_risks(project_root=find_project_root())


def git_sync_check() -> bool:
    return git_utils.git_sync_check(project_root=find_project_root())


def analyze_git_auto_preflight() -> Dict[str, Any]:
    """
    Produce the canonical git-auto preflight report and tri-state decision.
    """
    git_context = collect_git_context()
    sync_report = analyze_git_sync_risks()

    project_root_raw = (
        git_context.get("project_root")
        or sync_report.get("project_root")
        or str(find_project_root())
    )
    project_root = Path(project_root_raw).resolve()
    tracker_project_root = find_project_root().resolve()
    current_worktree_raw = git_context.get("worktree_path") or project_root_raw
    current_worktree = Path(current_worktree_raw).resolve()
    default_branch = _detect_default_branch(project_root)

    branch = git_context.get("branch") or sync_report.get("branch")
    workspace_mode = git_context.get("workspace_mode") or "unknown"
    issues: List[Dict[str, Any]] = sync_report.get("issues", [])
    issue_ids = {issue.get("id") for issue in issues}
    status = sync_report.get("status", "ok")

    decision = "ALLOW_IN_PLACE"
    reason_codes: List[str] = []

    delegate_issue_ids = {
        "detached_head",
        "operation_in_progress",
        "branch_diverged",
        "branch_checked_out_elsewhere",
        "branch_behind_default",
    }

    default_branch_candidates = {candidate for candidate in (default_branch, "main", "master") if candidate}
    on_default_branch = branch in default_branch_candidates
    existing_worktree_candidates: List[Dict[str, Any]] = []

    if (
        workspace_mode == "worktree"
        and branch
        and default_branch
        and branch not in default_branch_candidates
    ):
        behind_default = _count_branch_commits_behind(
            branch=branch,
            target_branch=default_branch,
            project_root=project_root,
        )
        if behind_default is not None and behind_default > 0:
            issues.append(
                {
                    "id": "branch_behind_default",
                    "level": "warning",
                    "message": (
                        f"Worktree branch '{branch}' is behind default branch "
                        f"'{default_branch}' by {behind_default} commit(s)."
                    ),
                    "recommendation": (
                        f"Rebase before continuing: git fetch origin && git rebase {default_branch}"
                    ),
                    "behind_count": behind_default,
                }
            )
            issue_ids.add("branch_behind_default")
            if status == "ok":
                status = "warning"

    triggered_delegate_ids = sorted(
        issue_id
        for issue_id in issue_ids
        if issue_id in delegate_issue_ids
    )

    if triggered_delegate_ids:
        decision = "DELEGATE_GIT_AUTO"
        reason_codes.extend(triggered_delegate_ids)
    elif status == "critical":
        decision = "DELEGATE_GIT_AUTO"
        reason_codes.append("critical_sync_risk")
    elif on_default_branch and workspace_mode != "worktree":
        current_feature_id: Optional[int] = None
        progress_data = load_progress_json()
        if isinstance(progress_data, dict):
            raw_feature_id = progress_data.get("current_feature_id")
            if isinstance(raw_feature_id, int):
                current_feature_id = raw_feature_id

        existing_worktree_candidates = _find_existing_worktree_candidates_for_feature(
            repo_root=project_root,
            tracker_project_root=tracker_project_root,
            current_worktree=current_worktree,
            current_feature_id=current_feature_id,
        )
        decision = "REQUIRE_WORKTREE"
        reason_codes.append("default_branch_feature_work")
        if existing_worktree_candidates:
            reason_codes.append("existing_worktree_found")
        if "dirty_worktree" in issue_ids:
            reason_codes.append("dirty_on_default_branch")
    else:
        reason_codes.append("no_blocking_workspace_risk")

    return {
        "status": status,
        "workspace_mode": workspace_mode,
        "branch": branch,
        "issues": issues,
        "decision": decision,
        "reason_codes": reason_codes,
        "default_branch": default_branch,
        "project_root": str(project_root),
        "existing_worktree_candidates": existing_worktree_candidates,
    }


def git_auto_preflight(output_json: bool = False) -> bool:
    """
    Emit preflight information for git-auto consumers.
    """
    report = analyze_git_auto_preflight()

    if output_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return True

    print("[Progress Tracker][Git Auto Preflight]")
    print(f"Repository: {report.get('project_root')}")
    print(f"Branch: {report.get('branch') or 'detached'}")
    print(f"Default branch: {report.get('default_branch') or 'unknown'}")
    print(f"Workspace mode: {report.get('workspace_mode')}")
    print(f"Status: {report.get('status')}")
    print(f"Decision: {report.get('decision')}")

    if report.get("issues"):
        print("Issues:")
        for issue in report["issues"]:
            print(f"- [{issue.get('level')}] {issue.get('id')}: {issue.get('message')}")

    reason_codes = report.get("reason_codes") or []
    if reason_codes:
        print("Reason codes:")
        for code in reason_codes:
            print(f"  - {code}")

    return True


def sync_runtime_context(source: str = "manual", quiet: bool = False, force: bool = False) -> bool:
    """
    Persist current runtime_context snapshot without touching semantic updated_at.

    Intended for SessionStart hooks and manual troubleshooting. This command is
    intentionally non-blocking when no progress tracking exists.
    """
    allowed_sources = {"session_start", "manual"}
    if source not in allowed_sources:
        if not quiet:
            print(f"Error: Invalid runtime context source '{source}'. Allowed: {sorted(allowed_sources)}")
        return False

    data = load_progress_json()
    if not data:
        if not quiet:
            print("No progress tracking found; runtime context sync skipped.")
        return True

    changed = _update_runtime_context(data, source=source, force=force)
    if not changed:
        if not quiet:
            print("Runtime context unchanged.")
        return True

    save_progress_json(data, touch_updated_at=False)

    if not quiet:
        ctx = data.get("runtime_context", {})
        print(f"Runtime context synced: {_format_context_summary(ctx)}")

    return True


def _check_other_worktrees_for_incomplete_work(current_worktree: str) -> List[Dict[str, Any]]:
    """
    Check other worktrees for incomplete progress work.

    Args:
        current_worktree: Path to the current worktree/root

    Returns:
        List of worktrees with incomplete work, each containing:
        - worktree_path: Path to the worktree
        - project_name: Name of the project
        - current_feature_id: ID of the current feature (if any)
        - incomplete_count: Number of incomplete features
        - total_features: Total number of features
    """
    other_worktrees = []

    # Get list of all worktrees
    exit_code, stdout, _ = _run_git(["worktree", "list", "--porcelain"], timeout=10)
    if exit_code != 0:
        return other_worktrees

    # Parse worktree paths
    worktree_paths = []
    for line in stdout.strip().split('\n'):
        if line.startswith('worktree '):
            path = line[9:].strip()  # Remove 'worktree ' prefix
            worktree_paths.append(path)

    # Check each worktree for progress files
    for wt_path in worktree_paths:
        # Skip current worktree
        if Path(wt_path).resolve() == Path(current_worktree).resolve():
            continue

        # Check if progress.json exists in the new docs/progress-tracker layout
        progress_file = Path(wt_path) / "docs" / "progress-tracker" / "state" / PROGRESS_JSON
        if not progress_file.exists():
            continue

        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            features = data.get("features", [])
            incomplete = [
                f
                for f in features
                if isinstance(f, dict) and not f.get("completed", False)
            ]
            actionable = [f for f in incomplete if not _is_feature_deferred(f)]
            deferred = [f for f in incomplete if _is_feature_deferred(f)]

            if actionable:
                other_worktrees.append({
                    "worktree_path": wt_path,
                    "project_name": data.get("project_name", "Unknown"),
                    "current_feature_id": data.get("current_feature_id"),
                    "incomplete_count": len(actionable),
                    "deferred_count": len(deferred),
                    "total_features": len(features),
                })
        except (json.JSONDecodeError, IOError):
            # Skip worktrees with corrupted or unreadable progress files
            continue

    return other_worktrees


def check(output_json: bool = False):
    """
    Check if progress tracking exists and has incomplete features.
    Returns exit code 0 if tracking is complete or doesn't exist, 1 if incomplete.

    Outputs JSON-formatted recovery information when incomplete work is detected.
    Also checks other worktrees for incomplete work and provides informative messages.

    Args:
        output_json: If True, emit only machine-readable JSON output without text messages.
    """
    # Check for incomplete work in other worktrees
    current_root = str(find_project_root())
    other_worktrees_with_work = _check_other_worktrees_for_incomplete_work(current_root)

    # Check current worktree for incomplete work
    data = load_progress_json()
    if not data:
        return 0  # No tracking = nothing to recover

    reconcile_report = analyze_reconcile_state(data)
    features = data.get("features", [])
    incomplete = [
        f
        for f in features
        if isinstance(f, dict) and not f.get("completed", False)
    ]
    actionable_incomplete = [f for f in incomplete if not _is_feature_deferred(f)]
    deferred_incomplete = [f for f in incomplete if _is_feature_deferred(f)]

    if incomplete:
        current_id = data.get("current_feature_id")

        if not actionable_incomplete and current_id is None:
            print(
                json.dumps(
                    {
                        "status": "deferred_only",
                        "project_name": data.get("project_name", "Unknown"),
                        "deferred_count": len(deferred_incomplete),
                        "total_features": len(features),
                        "recommendation": "resume_deferred_features",
                        "drift_diagnosis": reconcile_report.get("diagnosis"),
                        "drift_recommended_next_step": reconcile_report.get(
                            "recommended_next_step"
                        ),
                        "message": (
                            "All pending features are deferred. "
                            "Use `prog resume --all` or `prog resume --defer-group <group>` "
                            "when you want to continue."
                        ),
                    }
                )
            )
            return 0

        # First, show info about other worktrees with incomplete work (if any)
        # This is informational only - doesn't block current worktree recovery
        if other_worktrees_with_work:
            wt_list = []
            for wt in other_worktrees_with_work[:3]:  # Show at most 3 worktrees
                wt_info = (
                    f"{wt['worktree_path']} "
                    f"({wt['project_name']}: actionable={wt['incomplete_count']}, "
                    f"deferred={wt.get('deferred_count', 0)})"
                )
                wt_list.append(wt_info)

            info_msg = f"[Progress Tracker] ℹ️ 注意：其他 worktree 中也有未完成的工作\n"
            info_msg += f"其他 worktree: {'; '.join(wt_list)}\n"
            info_msg += f"如需切换，使用: cd <worktree_path>\n"

            if not output_json:
                print(json.dumps({
                    "status": "info_other_worktrees",
                    "message": info_msg,
                    "other_worktrees": other_worktrees_with_work[:3],
                    "drift_diagnosis": reconcile_report.get("diagnosis"),
                    "drift_recommended_next_step": reconcile_report.get(
                        "recommended_next_step"
                    ),
                }))

        # Then proceed with current worktree recovery
        project_name = data.get("project_name", "Unknown")
        total = len(features)
        completed = sum(1 for f in features if isinstance(f, dict) and f.get("completed", False))
        workflow_state = data.get("workflow_state", {})

        # If there's a feature in progress, provide detailed recovery info
        if current_id is not None:
            feature = next((f for f in features if f.get("id") == current_id), None)
            if feature:
                if _is_feature_deferred(feature):
                    print(
                        json.dumps(
                            {
                                "status": "needs_manual_review",
                                "feature_id": current_id,
                                "feature_name": feature.get("name", "Unknown"),
                                "reason": "current_feature_deferred",
                                "recommendation": "clear_or_resume_current_feature",
                                "message": (
                                    "Current feature is marked deferred. "
                                    "Run `prog resume --all` (or by group), or clear current feature state."
                                ),
                            }
                        )
                    )
                    return 1

                phase = workflow_state.get("phase", "unknown")
                plan_path = workflow_state.get("plan_path", "")
                completed_tasks = workflow_state.get("completed_tasks", [])
                total_tasks = workflow_state.get("total_tasks", 0)
                checkpoints = load_checkpoints()
                latest_checkpoint = _latest_checkpoint_entry(checkpoints)
                latest_feature_checkpoint = _latest_checkpoint_entry_for_feature(checkpoints, current_id)
                latest_checkpoint_context = _build_checkpoint_context(latest_checkpoint)
                latest_feature_checkpoint_context = _build_checkpoint_context(latest_feature_checkpoint)
                execution_context = workflow_state.get("execution_context")
                expected_context = execution_context
                if not isinstance(expected_context, dict) or not (
                    expected_context.get("worktree_path") or expected_context.get("branch")
                ):
                    expected_context = latest_feature_checkpoint_context

                # Build a live context snapshot for comparison without persisting it.
                current_context = build_runtime_context(data, source="manual")
                context_hint = compare_contexts(expected_context, current_context)
                if (
                    context_hint.get("status") == "unknown"
                    and latest_feature_checkpoint_context
                    and latest_feature_checkpoint_context is not expected_context
                ):
                    # Fallback compare if execution_context existed but was incomplete.
                    context_hint = compare_contexts(latest_feature_checkpoint_context, current_context)

                # Determine recovery recommendation
                recommendation = determine_recovery_action(
                    phase, feature, completed_tasks, total_tasks, plan_path=plan_path
                )
                plan_validation = validate_plan_path(
                    plan_path,
                    require_exists=phase in [
                        "planning:draft", "planning:approved",
                        "planning_complete", "execution", "execution_complete",
                    ],
                )

                # Build a user-friendly recovery message
                recovery_message = f"[Progress Tracker] 恢复功能开发: {feature.get('name', 'Unknown')}\n"
                recovery_message += f"阶段: {phase}\n"
                if plan_path:
                    recovery_message += f"Plan 文档: {plan_path}\n"

                # Add worktree switch hint if context mismatch
                if context_hint.get("status") in ("mismatch", "path_mismatch"):
                    expected_path = context_hint.get("expected_worktree_path")
                    if expected_path and expected_path != context_hint.get("current_worktree_path"):
                        recovery_message += f"\n⚠️ 当前会话不在上次执行的工作目录中\n"
                        recovery_message += f"上次执行位置: {expected_path}\n"
                        recovery_message += f"当前位置: {context_hint.get('current_worktree_path')}\n"
                        recovery_message += f"\n💡 切换到正确的工作目录:\n"
                        recovery_message += f"   cd {expected_path}\n"

                recovery_info = {
                    "status": "incomplete",
                    "feature_id": current_id,
                    "feature_name": feature.get("name", "Unknown"),
                    "phase": phase,
                    "plan_path": plan_path,
                    "plan_path_valid": plan_validation["valid"],
                    "plan_path_error": plan_validation["error"],
                    "completed_tasks": completed_tasks,
                    "total_tasks": total_tasks,
                    "recommendation": recommendation,
                    "context_hint": context_hint,
                    "drift": reconcile_report,
                    "recovery_message": recovery_message,
                    "last_checkpoint_hint": (
                        {
                            "timestamp": latest_checkpoint.get("timestamp"),
                            "feature_id": latest_checkpoint.get("feature_id"),
                            "feature_name": latest_checkpoint.get("feature_name"),
                            "phase": latest_checkpoint.get("phase"),
                            "current_task": latest_checkpoint.get("current_task"),
                            "total_tasks": latest_checkpoint.get("total_tasks"),
                            "next_action": latest_checkpoint.get("next_action"),
                            "branch": latest_checkpoint.get("branch"),
                            "worktree_path": latest_checkpoint.get("worktree_path"),
                        }
                        if latest_checkpoint
                        else None
                    ),
                }

                print(json.dumps(recovery_info))
                return 1

        # General incomplete status (no specific feature in progress)
        result = {
            "status": "incomplete",
            "project_name": project_name,
            "completed": completed,
            "total": total,
            "actionable_count": len(actionable_incomplete),
            "deferred_count": len(deferred_incomplete),
            "drift_diagnosis": reconcile_report.get("diagnosis"),
            "drift_recommended_next_step": reconcile_report.get("recommended_next_step"),
        }

        if not output_json:
            print(f"[Progress Tracker] Unfinished project detected: {project_name}")
            print(f"Progress: {completed}/{total} completed")
            if reconcile_report.get("diagnosis") != "in_sync":
                print(
                    "[Progress Tracker] Reality check: "
                    f"{reconcile_report.get('diagnosis')} -> "
                    f"{reconcile_report.get('recommended_next_step')}"
                )
            if actionable_incomplete:
                print("Use '/prog' to view status or '/prog-next' to continue")
            else:
                print("Only deferred pending features remain. Use `prog resume --all` to continue.")
        else:
            print(json.dumps(result))

        return 1 if actionable_incomplete else 0

    return 0


def determine_recovery_action(
    phase, feature, completed_tasks, total_tasks, plan_path: Optional[str] = None
):
    """Determine the recommended recovery action based on workflow state.

    Delegates to compute_next_action() as the canonical phase→action mapping,
    then applies recovery-specific refinements (plan validation, progress %).
    """
    # Phase groups that require a valid plan for recovery.
    # NOTE: planning:clarifying is intentionally excluded — at this stage the
    # plan may not exist yet (clarifying happens before draft), so validating
    # it would produce false-positive recreate_plan actions.
    plan_required_phases = [
        "planning:draft", "planning:approved", "planning:review",
        "planning_complete", "execution", "execution_complete",
    ]
    if phase in plan_required_phases:
        plan_validation = validate_plan_path(plan_path, require_exists=True)
        if not plan_validation["valid"]:
            return "recreate_plan"

    # execution phase: finer-grained resume strategy based on progress
    if phase == "execution" and total_tasks > 0:
        progress = len(completed_tasks) / total_tasks
        if progress >= 0.8:
            return "auto_resume"
        else:
            return "manual_resume"

    # Delegate to canonical FSM for all other phases
    if compute_next_action is not None:
        context = {"completed_tasks": completed_tasks, "total_tasks": total_tasks}
        base_action = compute_next_action(phase, context)
        if base_action:
            return base_action
    else:
        logging.warning(
            "wf_state_machine not available, falling back to manual_review "
            "for phase=%s", phase
        )

    return "manual_review"


def set_current(feature_id):
    """Set the current feature being worked on."""
    is_wrapper = True
    from feature_commands import set_current_command, FeatureCommandsServices
    return set_current_command(feature_id, FeatureCommandsServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        update_runtime_context_fn=_update_runtime_context,
        auto_state_commit_fn=_auto_state_commit,
        notify_parent_sync_fn=_notify_parent_sync,
    ))


def set_development_stage(stage: str, feature_id: Optional[int] = None) -> bool:
    """Set development_stage for the target feature (defaults to current feature)."""
    is_wrapper = True
    from feature_commands import set_development_stage_command, FeatureCommandsServices
    return set_development_stage_command(stage, FeatureCommandsServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        update_runtime_context_fn=_update_runtime_context,
        auto_state_commit_fn=_auto_state_commit,
        notify_parent_sync_fn=_notify_parent_sync,
    ), feature_id=feature_id)


def _work_item_selector_services():
    from work_item_selector import WorkItemSelectorServices
    return WorkItemSelectorServices(
        load_progress_json_fn=load_progress_json,
        is_feature_deferred_fn=_is_feature_deferred,
        parse_iso_timestamp_fn=_parse_iso_timestamp,
        now_fn=lambda: datetime.now(tz=timezone.utc),
        warn_fn=logger.warning,
        resolve_linked_project_root_fn=_resolve_linked_project_root,
        load_progress_payload_at_root_fn=_load_progress_payload_at_root,
        stale_after_hours=DEFAULT_LINKED_STATUS_STALE_HOURS,
        root_route_code=ROOT_ROUTE_CODE,
    )


def get_next_feature():
    """Get the next incomplete feature."""
    from work_item_selector import get_next_feature as _impl
    return _impl(_work_item_selector_services())
get_next_feature.is_wrapper = True


def _get_dispatched_child_feature(
    routing_queue: List[str],
    active_routes: List[Any],
    linked_projects: List[Any],
    project_root: Path,
    repo_root: Path,
    parent_data: Optional[Dict[str, Any]] = None,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
) -> Optional[Dict[str, Any]]:
    """Scan routing_queue and return the first dispatchable feature, or None."""
    from work_item_selector import get_dispatched_child_feature as _impl
    return _impl(
        routing_queue,
        active_routes,
        linked_projects,
        project_root,
        repo_root,
        svc=_work_item_selector_services(),
        parent_data=parent_data,
        stale_after_hours=stale_after_hours,
    )
_get_dispatched_child_feature.is_wrapper = True


def _select_next_work_item(
    data: Dict[str, Any],
    project_root: Path,
    repo_root: Path,
) -> Optional[Dict[str, Any]]:
    """Unified work-item selector with priority ordering."""
    from work_item_selector import select_next_work_item as _impl
    return _impl(data, project_root, repo_root, _work_item_selector_services())
_select_next_work_item.is_wrapper = True


def _next_feature_command_services():
    from next_feature_commands import NextFeatureCommandServices
    return NextFeatureCommandServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        find_project_root_fn=find_project_root,
        detect_default_branch_fn=_detect_default_branch,
        run_git_fn=_run_git,
        update_runtime_context_fn=_update_runtime_context,
        collect_linked_project_statuses_fn=collect_linked_project_statuses,
        analyze_reconcile_state_fn=analyze_reconcile_state,
        evaluate_planning_readiness_fn=readiness_validator._evaluate_planning_readiness,
        select_next_work_item_fn=_select_next_work_item,
        get_next_feature_fn=get_next_feature,
        iso_now_fn=_iso_now,
        debug_fn=logger.debug,
        finish_pending_state=FINISH_PENDING_STATE,
        linked_snapshot_schema_version=LINKED_SNAPSHOT_SCHEMA_VERSION,
        root_route_code=ROOT_ROUTE_CODE,
        repo_root=_REPO_ROOT,
        entropy_preflight_fn=workspace_entropy.run_safe_entropy_preflight,
    )


def next_feature(output_json: bool = False, ack_planning_risk: bool = False) -> bool:
    """Print the next actionable feature (skipping completed/deferred)."""
    from next_feature_commands import next_feature_command
    return next_feature_command(
        output_json=output_json,
        ack_planning_risk=ack_planning_risk,
        svc=_next_feature_command_services(),
    )
next_feature.is_wrapper = True


def set_feature_ai_metrics(
    feature_id: int,
    complexity_score: int,
    selected_model: str,
    workflow_path: str,
    confidence: str = "medium",
    bucket_override: str | None = None,
) -> bool:
    """Set lightweight AI metrics for a feature."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    valid_models = {"haiku", "sonnet", "opus"}
    if selected_model not in valid_models:
        print(f"Invalid model '{selected_model}'. Must be one of: {sorted(valid_models)}")
        return False

    valid_confidences = {"high", "medium", "low"}
    if confidence not in valid_confidences:
        print(f"Invalid confidence '{confidence}'. Must be one of: {sorted(valid_confidences)}")
        return False

    valid_buckets = {"simple", "standard", "complex", None}
    if bucket_override not in valid_buckets:
        print(f"Invalid bucket_override '{bucket_override}'. Must be simple/standard/complex or None")
        return False

    if complexity_score < 0 or complexity_score > 100:
        print("Invalid complexity score. Must be in range 0-100")
        return False

    now_iso = datetime.now().isoformat() + "Z"
    ai_metrics = feature.get("ai_metrics", {})
    if not isinstance(ai_metrics, dict):
        ai_metrics = {}

    raw_bucket = determine_complexity_bucket(complexity_score)
    routed_bucket = bucket_override if bucket_override else raw_bucket

    ai_metrics.update(
        {
            "complexity_score": complexity_score,
            "complexity_bucket": routed_bucket,
            "selected_model": selected_model,
            "workflow_path": workflow_path,
            "scoring_v2": {
                "score": complexity_score,
                "raw_score_bucket": raw_bucket,
                "routed_bucket": routed_bucket,
                "confidence": confidence,
            },
        }
    )
    if not ai_metrics.get("started_at"):
        ai_metrics["started_at"] = now_iso

    feature["ai_metrics"] = ai_metrics
    save_progress_json(data)

    save_progress_md("")

    print(
        f"AI metrics updated for feature {feature_id}: "
        f"{ai_metrics['complexity_bucket']}, model={selected_model}"
    )
    return True


def _make_completion_flow_services() -> "completion_flow.CompletionFlowServices":
    """Build a CompletionFlowServices instance wired to facade functions."""
    return completion_flow.CompletionFlowServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        find_project_root_fn=find_project_root,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        record_sprint_artifact_fn=record_sprint_artifact,
        require_sprint_contract_fn=require_sprint_contract,
        notify_parent_sync_fn=_notify_parent_sync,
        repo_root=_REPO_ROOT,
        record_feature_state_event_fn=record_feature_state_event,
        update_runtime_context_fn=_update_runtime_context,
        auto_state_commit_fn=_auto_state_commit,
        archive_current_progress_fn=archive_current_progress,
        reset_active_progress_fn=_reset_active_progress,
        archive_feature_docs_fn=archive_feature_docs,
        get_next_feature_fn=get_next_feature,
        validate_plan_document_fn=validate_plan_document,
        collect_git_context_fn=collect_git_context,
        get_head_commit_fn=_get_head_commit,
        analyze_reconcile_state_fn=analyze_reconcile_state,
    )


def complete_feature_ai_metrics(feature_id: int) -> bool:
    return completion_flow.complete_feature_ai_metrics(feature_id, _make_completion_flow_services())
complete_feature_ai_metrics.is_wrapper = True


def _is_immutable_protected(file_path: Path, project_root: Path) -> bool:
    """Return True if file_path is a canonically protected file that must never be archived.

    Uses normalized relative-path matching (not basename) to avoid false positives
    from unrelated files that happen to share the same name.
    """
    try:
        rel = str(file_path.relative_to(project_root)).replace("\\", "/")
        return rel in _IMMUTABLE_PROTECTED_RELPATHS
    except ValueError:
        return False


def archive_feature_docs(feature_id: int, feature_name: str = None) -> Dict[str, Any]:
    import doc_generator
    return doc_generator.archive_feature_docs(
        feature_id,
        feature_name,
        find_project_root_fn=find_project_root,
        load_progress_json_fn=load_progress_json,
        is_immutable_protected_fn=_is_immutable_protected,
    )
archive_feature_docs.is_wrapper = True



def save_archive_record(feature_id: int, archive_result: Dict[str, Any]) -> None:
    return completion_flow.save_archive_record(feature_id, archive_result, _make_completion_flow_services())
save_archive_record.is_wrapper = True


AcceptanceTestResult = completion_flow.AcceptanceTestResult


def _clear_feature_finish_pending(feature: Dict[str, Any]) -> None:
    return completion_flow._clear_feature_finish_pending(feature)
_clear_feature_finish_pending.is_wrapper = True


def _is_executable_test_step(step: str) -> bool:
    return completion_flow._is_executable_test_step(step)
_is_executable_test_step.is_wrapper = True


def _extract_test_step_command(step: str) -> Optional[str]:
    return completion_flow._extract_test_step_command(step)
_extract_test_step_command.is_wrapper = True


def _extract_relative_path_candidates_from_command(command: str) -> List[str]:
    return completion_flow._extract_relative_path_candidates_from_command(command)
_extract_relative_path_candidates_from_command.is_wrapper = True


def _resolve_acceptance_command_cwd(
    command: str,
    project_root: Path,
    repo_root: Optional[Path],
) -> Path:
    return completion_flow._resolve_acceptance_command_cwd(command, project_root, repo_root)
_resolve_acceptance_command_cwd.is_wrapper = True


def _run_acceptance_tests(feature: Dict[str, Any], run_all: bool = False):
    return completion_flow._run_acceptance_tests(feature, _make_completion_flow_services(), run_all=run_all)
_run_acceptance_tests.is_wrapper = True


def _cleanup_old_done_reports(report_dir: Path, feature_id: int, keep_latest: int = 5) -> None:
    return completion_flow._cleanup_old_done_reports(report_dir, feature_id, keep_latest)
_cleanup_old_done_reports.is_wrapper = True


def _save_done_test_report(feature_id: int, feature_name: str, results, success: bool) -> Optional[Path]:
    return completion_flow._save_done_test_report(feature_id, feature_name, results, success, _make_completion_flow_services())
_save_done_test_report.is_wrapper = True


def _format_failure_reason(results) -> str:
    return completion_flow._format_failure_reason(results)
_format_failure_reason.is_wrapper = True


def _validate_done_preconditions(data: Dict[str, Any]):
    return completion_flow._validate_done_preconditions(data, _make_completion_flow_services())
_validate_done_preconditions.is_wrapper = True


def _validate_completion_reconcile(data: Dict[str, Any], feature_id: int):
    return completion_flow._validate_completion_reconcile(data, feature_id, _make_completion_flow_services())
_validate_completion_reconcile.is_wrapper = True


def _validate_completion_plan_document(data: Dict[str, Any], feature_id: int):
    return completion_flow._validate_completion_plan_document(data, feature_id, _make_completion_flow_services())
_validate_completion_plan_document.is_wrapper = True


def _finalize_completion_state_in_memory(data: Dict[str, Any], feature_id: int, commit_hash: Optional[str] = None):
    return completion_flow._finalize_completion_state_in_memory(data, feature_id, _make_completion_flow_services(), commit_hash=commit_hash)
_finalize_completion_state_in_memory.is_wrapper = True


def _record_feature_completed_event(feature_id: int, feature_name: str, commit_hash: str = "") -> None:
    return completion_flow._record_feature_completed_event(feature_id, feature_name, _make_completion_flow_services(), commit_hash=commit_hash)
_record_feature_completed_event.is_wrapper = True


def _append_capability_memory(feature: Dict[str, Any], commit_hash: str) -> None:
    return completion_flow._append_capability_memory(feature, commit_hash, _make_completion_flow_services())
_append_capability_memory.is_wrapper = True


def _is_worktree_dirty(worktree_path: Optional[str]) -> bool:
    return worktree_handler._is_worktree_dirty(worktree_path, project_root=find_project_root())
_is_worktree_dirty.is_wrapper = True


def _resolve_upstream(branch: str) -> tuple:
    return git_utils._resolve_upstream(branch, project_root=find_project_root())


def _remove_worktree(worktree_path: str) -> bool:
    return git_utils._remove_worktree(worktree_path, project_root=find_project_root())


def _delete_local_branch(branch: str) -> bool:
    return git_utils._delete_local_branch(branch, project_root=find_project_root())


def _delete_remote_branch(remote: str, remote_branch: str) -> bool:
    return git_utils._delete_remote_branch(remote, remote_branch, project_root=find_project_root())


def _run_post_done_cleanup(ctx: dict, skip: bool = False) -> None:
    return completion_flow._run_post_done_cleanup(ctx, _make_completion_flow_services(), skip=skip)
_run_post_done_cleanup.is_wrapper = True


def _get_head_commit() -> Optional[str]:
    return git_utils._get_head_commit(project_root=find_project_root())


def _close_current_task(output_json: bool = False) -> int:
    """Main dispatch for `prog next --done`. Returns RC 0/1/2."""
    data = load_progress_json()
    if not data:
        msg = "No progress tracking found"
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": None, "message": msg}))
        else:
            print(f"Error: {msg}")
        return 1

    current_task_id = data.get("current_task_id")
    if not current_task_id:
        msg = "No active task. Run `prog next` to select a task first."
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": None, "message": msg}))
        else:
            print(f"Error: {msg}\nRepair: run `prog next` to activate a task.")
        return 1

    tasks = data.get("tasks") or []
    task = next((t for t in tasks if isinstance(t, dict) and t.get("id") == current_task_id), None)

    if task is None:
        msg = f"Task {current_task_id} not found — clearing stale current_task_id."
        data["current_task_id"] = None
        save_progress_json(data)
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": current_task_id, "message": msg}))
        else:
            print(f"Error: {msg}")
        return 1

    if task.get("status") == "completed":
        msg = f"Task {current_task_id} is already completed."
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": current_task_id, "message": msg}))
        else:
            print(f"Error: {msg}\nRepair: run `prog next` to select the next task.")
        return 1

    parent_fid = task.get("parent_feature_id")
    if parent_fid is None:
        return _close_standalone_task(task, data, output_json=output_json)
    else:
        return _close_feature_bound_task(task, data, output_json=output_json)


def _close_standalone_task(task: dict, data: dict, output_json: bool = False) -> int:
    """Close a standalone task via git squash-merge. Atomic: git first, state second."""
    task_id = task["id"]
    branch = f"task/{task_id}"
    project_root = find_project_root()

    ok, value = _git_squash_close_task(
        task_id=task_id,
        branch=branch,
        project_root=project_root,
        task_name=task.get("description") or task.get("name"),
    )
    if not ok:
        msg = f"Git squash-merge failed: {value}"
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": task_id, "message": msg}))
        else:
            print(f"Error: {msg}")
        return 1

    # Git succeeded — now update business state
    task["status"] = "completed"
    data["current_task_id"] = None
    data["updated_at"] = _iso_now()
    save_progress_json(data)

    msg = f"Task {task_id} closed. Squash commit: {value}"
    if output_json:
        print(json.dumps({"status": "ok", "closed_task_id": task_id, "message": msg}))
    else:
        print(f"[DONE] {msg}")
    return 0


def _close_feature_bound_task(task: dict, data: dict, output_json: bool = False) -> int:
    """Close a feature-bound task: mark complete, no git ops, no feature auto-close."""
    task_id = task["id"]
    task["status"] = "completed"
    data["current_task_id"] = None
    data["updated_at"] = _iso_now()
    save_progress_json(data)

    msg = f"Task {task_id} marked complete. Parent feature not auto-closed."
    if output_json:
        print(json.dumps({"status": "ok", "closed_task_id": task_id, "message": msg}))
    else:
        print(f"[DONE] {msg}")
    return 0


def _run_done_preflight(data: Dict[str, Any]):
    return completion_flow._run_done_preflight(data, _make_completion_flow_services())
_run_done_preflight.is_wrapper = True


def _print_preflight_report(results: list, feature_id, feature_name: str) -> None:
    return completion_flow._print_preflight_report(results, feature_id, feature_name)
_print_preflight_report.is_wrapper = True


def cmd_done(commit_hash=None, run_all: bool = False, skip_archive: bool = False,
             no_cleanup: bool = False, check_only: bool = False) -> int:
    return completion_flow.cmd_done(
        _make_completion_flow_services(),
        commit_hash=commit_hash,
        run_all=run_all,
        skip_archive=skip_archive,
        no_cleanup=no_cleanup,
        check_only=check_only,
    )
cmd_done.is_wrapper = True


def _collect_ship_signals(feature: dict) -> dict:
    import evaluator_gateway
    return evaluator_gateway._collect_ship_signals(feature)
_collect_ship_signals.is_wrapper = True


def cmd_ship_check(feature_id: int, *, coverage_min: float = 0.8) -> int:
    """Run unified pre-archive ship gate (PR-5)."""
    if not SHIP_CHECK_AVAILABLE:
        print("ship_check module not available", file=sys.stderr)
        return 9

    data = load_progress_json()
    if not data:
        print("No progress tracking found", file=sys.stderr)
        return 1

    feat = next((f for f in data.get("features", []) if f.get("id") == feature_id), None)
    if feat is None:
        print(f"feature {feature_id} not found", file=sys.stderr)
        return 3

    inputs = _collect_ship_signals(feat)
    result = _run_ship_check(
        feature_id=feature_id,
        project_root=Path.cwd(),
        inputs=inputs,
        thresholds={"coverage_min": coverage_min},
    )

    with progress_transaction():
        data2 = load_progress_json()
        if data2:
            feat2 = next((f for f in data2.get("features", []) if f.get("id") == feature_id), None)
            if feat2 is not None:
                feat2.setdefault("quality_gates", {})["ship_check"] = result.to_quality_gate_payload()
                save_progress_json(data2)
                save_progress_md("")

    if result.status == "fail":
        for f in result.failures:
            print(f"[{f.check_id}] {f.detail}", file=sys.stderr)
        return 8
    print(f"[SHIP-CHECK] Feature {feature_id}: pass")
    return 0


def cmd_set_finish_state(feature_id: int, status: str, reason: Optional[str] = None) -> int:
    """Resolve explicit finish_pending state for a feature."""
    if status not in VALID_FINISH_STATES:
        print(
            f"Invalid status: {status}. "
            f"Expected one of: {', '.join(VALID_FINISH_STATES)}",
            file=sys.stderr,
        )
        return 2

    data = load_progress_json()
    if not data:
        print("No progress tracking found", file=sys.stderr)
        return 1

    features = data.get("features", [])
    feature = next((item for item in features if item.get("id") == feature_id), None)
    if feature is None:
        print(f"Feature ID {feature_id} not found", file=sys.stderr)
        return 3

    current_status = feature.get("integration_status")
    if current_status != FINISH_PENDING_STATE:
        print(
            f"Feature {feature_id} is not in finish_pending (current: {current_status})",
            file=sys.stderr,
        )
        return 4

    normalized_reason = _normalize_optional_string(reason)
    feature["integration_status"] = status
    _clear_feature_finish_pending(feature)
    feature["finish_state_resolved_at"] = _iso_now()
    if normalized_reason is None:
        feature.pop("finish_state_resolved_reason", None)
    else:
        feature["finish_state_resolved_reason"] = normalized_reason

    save_progress_json(data)
    save_progress_md("")

    _append_audit_event(
        event_type="set_finish_state",
        feature_id=feature_id,
        details={
            "from_status": FINISH_PENDING_STATE,
            "to_status": status,
            "reason": normalized_reason,
        },
    )

    print(f"Feature {feature_id} finish state resolved: {status}")
    return 0


def cmd_review_pass(feature_id: int, lane: str, evidence: Optional[str] = None) -> int:
    """Mark one review lane as passed for a feature.

    Exit codes:
      0 — lane marked passed
      1 — no tracking / review_router unavailable
      3 — feature not found
      4 — feature has no required review lanes
      5 — lane not in required lanes
    """
    if not REVIEW_ROUTER_AVAILABLE:
        print("[REVIEW] review_router not available", file=sys.stderr)
        return 1

    data = load_progress_json()
    if not data:
        print("[REVIEW] No progress tracking found", file=sys.stderr)
        return 1

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if feature is None:
        print(f"[REVIEW] Feature {feature_id} not found", file=sys.stderr)
        return 3

    reviews = feature.get("quality_gates", {}).get("reviews", {})
    required = reviews.get("required", [])
    if not required:
        print(f"[REVIEW] Feature {feature_id} has no required review lanes", file=sys.stderr)
        return 4

    if lane not in required:
        print(
            f"[REVIEW] Lane '{lane}' is not in required lanes {required}",
            file=sys.stderr,
        )
        return 5

    _mark_review_passed(feature, lane)
    pending = _get_pending_lanes(feature)

    normalized_evidence = _normalize_optional_string(evidence)
    if normalized_evidence:
        quality_gates = feature.setdefault("quality_gates", {})
        lane_evidence = quality_gates.setdefault("review_evidence", {})
        lane_evidence[lane] = {
            "evidence": normalized_evidence,
            "recorded_at": _iso_now(),
        }

    save_progress_json(data)
    save_progress_md("")

    print(f"[REVIEW] Lane '{lane}' marked passed for feature {feature_id}")
    if pending:
        print(f"[REVIEW] Remaining pending: {pending}")
    else:
        print("[REVIEW] All required lanes passed. /prog done will no longer be blocked by review gate.")
    return 0


def cmd_set_sprint_contract(
    feature_id: int, scope: str, done_criteria: list, test_plan: list
) -> int:
    """Set or update the sprint contract for a feature.

    Exit codes:
      0 -- sprint contract set successfully
      1 -- no progress tracking found
      3 -- feature not found
    """
    data = load_progress_json()
    if not data:
        print("No progress tracking found", file=sys.stderr)
        return 1

    features = data.get("features", [])
    feature = next((item for item in features if item.get("id") == feature_id), None)
    if feature is None:
        print(f"Feature ID {feature_id} not found", file=sys.stderr)
        return 3

    existing_contract = feature.get("sprint_contract") or {}

    normalized_scope = scope.strip()
    normalized_done_criteria = [
        item.strip() for item in done_criteria if item and item.strip()
    ]
    normalized_test_plan = [
        item.strip() for item in test_plan if item and item.strip()
    ]

    feature["sprint_contract"] = {
        "scope": normalized_scope,
        "done_criteria": normalized_done_criteria,
        "test_plan": normalized_test_plan,
        "accepted_by": existing_contract.get("accepted_by"),
        "accepted_at": existing_contract.get("accepted_at"),
    }

    save_progress_json(data)
    save_progress_md("")

    _append_audit_event(
        event_type="set_sprint_contract",
        feature_id=feature_id,
        details={
            "scope": normalized_scope,
            "done_criteria_count": len(normalized_done_criteria),
            "test_plan_count": len(normalized_test_plan),
        },
    )

    print(f"Sprint contract set for feature {feature_id}")
    return 0


def complete_feature(feature_id, commit_hash=None, skip_archive=False):
    return completion_flow.complete_feature(feature_id, _make_completion_flow_services(), commit_hash=commit_hash, skip_archive=skip_archive)
complete_feature.is_wrapper = True


def undo_last_feature():
    """Undo the last completed feature, reverting git commit if recorded."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    completed_features = [f for f in features if f.get("completed", False)]

    if not completed_features:
        print("No completed features to undo.")
        return False

    # Sort by completed_at desc, then id desc
    def sort_key(f):
        # Use a default very old date for features without completed_at
        date_str = f.get("completed_at", "1970-01-01T00:00:00Z")
        return (date_str, f.get("id", 0))

    last_feature = sorted(completed_features, key=sort_key, reverse=True)[0]
    commit_hash = last_feature.get("commit_hash")

    print(
        f"Undoing feature: {last_feature.get('name', 'Unknown')} (ID: {last_feature.get('id')})"
    )

    # Attempt git revert if hash exists
    if commit_hash:
        print(f"Attempting to revert commit {commit_hash}...")

        # Validate commit hash format before using it
        if GIT_VALIDATOR_AVAILABLE:
            if not validate_commit_hash(commit_hash):
                print(f"Error: Invalid commit hash format: {commit_hash}")
                print("Commit hash must be 7-40 hexadecimal characters.")
                print("To protect your repo, progress undo has been aborted.")
                return False
        else:
            # Basic validation fallback
            if not re.match(r'^[0-9a-f]{7,40}$', commit_hash):
                print(f"Error: Invalid commit hash format: {commit_hash}")
                return False

        try:
            # Check for working directory changes first using secure validator
            if GIT_VALIDATOR_AVAILABLE:
                if not is_working_directory_clean(str(find_project_root())):
                    print(
                        "Error: Working directory is not clean. Commit or stash changes before undoing."
                    )
                    return False

                # Execute git revert with validation
                exit_code, stdout, stderr = safe_git_command(
                    ['git', 'revert', '--no-edit', commit_hash],
                    timeout=30
                )
                if exit_code != 0:
                    print(f"Error reverting commit: {stderr}")
                    print("To protect your repo, progress undo has been aborted.")
                    return False
            else:
                # Fallback to subprocess if validator not available
                status = subprocess.check_output(
                    ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
                )
                if status:
                    print(
                        "Error: Working directory is not clean. Commit or stash changes before undoing."
                    )
                    return False

                subprocess.check_call(
                    ["git", "revert", "--no-edit", commit_hash],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

            print(f"Successfully reverted commit {commit_hash}")
        except (GitCommandError, subprocess.CalledProcessError) as e:
            print(f"Error reverting commit: {e}")
            print("To protect your repo, progress undo has been aborted.")
            return False
    else:
        print("No commit hash recorded for this feature. Skipping git revert.")

    # Update state
    last_feature["completed"] = False
    if "completed_at" in last_feature:
        del last_feature["completed_at"]
    if "commit_hash" in last_feature:
        del last_feature["commit_hash"]

    # If nothing is currently in progress, we could optionally set this as current
    # But for safety, we'll leave current_feature_id as None or whatever it was

    save_progress_json(data)

    # Event sourcing: append feature_undone to audit.log
    record_feature_state_event(
        event_type="feature_undone",
        feature_id=last_feature.get("id"),
        feature_name=last_feature.get("name"),
    )

    save_progress_md("")

    print("Progress tracking updated.")
    return True


def _format_feature_owners(feature: Dict[str, Any]) -> Optional[str]:
    import doc_generator
    return doc_generator._format_feature_owners(feature)
_format_feature_owners.is_wrapper = True


def _make_work_item_commands_services():
    import work_item_commands

    return work_item_commands.WorkItemCommandsServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        update_runtime_context_fn=_update_runtime_context,
        notify_parent_sync_fn=_notify_parent_sync,
        add_bug_internal_fn=_add_bug_internal,
        find_project_root_fn=find_project_root,
    )


def add_update(
    category: str,
    summary: str,
    details: Optional[str] = None,
    feature_id: Optional[int] = None,
    bug_id: Optional[str] = None,
    role: Optional[str] = None,
    owner: Optional[str] = None,
    source: str = "prog_update",
    next_action: Optional[str] = None,
    refs: Optional[List[str]] = None,
) -> bool:
    import work_item_commands

    return work_item_commands.add_update_command(
        category,
        summary,
        svc=_make_work_item_commands_services(),
        details=details,
        feature_id=feature_id,
        bug_id=bug_id,
        role=role,
        owner=owner,
        source=source,
        next_action=next_action,
        refs=refs,
    )
add_update.is_wrapper = True


def list_updates(limit: int = 0) -> bool:
    import work_item_commands

    return work_item_commands.list_updates_command(
        limit,
        svc=_make_work_item_commands_services(),
    )
list_updates.is_wrapper = True


def add_retro(
    feature_id: int,
    summary: str,
    root_cause: str,
    action_items: Optional[List[str]] = None,
) -> bool:
    import work_item_commands

    return work_item_commands.add_retro_command(
        feature_id,
        summary,
        root_cause,
        svc=_make_work_item_commands_services(),
        action_items=action_items,
    )
add_retro.is_wrapper = True


def set_feature_owner(feature_id: int, role: str, owner: Optional[str]) -> bool:
    import work_item_commands

    return work_item_commands.set_feature_owner_command(
        feature_id,
        role,
        owner,
        svc=_make_work_item_commands_services(),
    )
set_feature_owner.is_wrapper = True


def add_feature(name, test_steps, workflow_profile=None):
    import work_item_commands

    return work_item_commands.add_feature_command(
        name,
        test_steps,
        svc=_make_work_item_commands_services(),
        workflow_profile=workflow_profile,
    )
add_feature.is_wrapper = True


def update_feature(feature_id, name, test_steps=None):
    import work_item_commands

    return work_item_commands.update_feature_command(
        feature_id,
        name,
        svc=_make_work_item_commands_services(),
        test_steps=test_steps,
    )
update_feature.is_wrapper = True


def defer_features(
    feature_id: Optional[int],
    all_pending: bool,
    reason: str,
    defer_group: Optional[str] = None,
) -> bool:
    import work_item_commands

    return work_item_commands.defer_features_command(
        feature_id,
        all_pending,
        reason,
        svc=_make_work_item_commands_services(),
        defer_group=defer_group,
    )
defer_features.is_wrapper = True


def resume_deferred_features(defer_group: Optional[str], resume_all: bool) -> bool:
    import work_item_commands

    return work_item_commands.resume_deferred_features_command(
        defer_group,
        resume_all,
        svc=_make_work_item_commands_services(),
    )
resume_deferred_features.is_wrapper = True


def get_next_bug_id():
    """
    Generate the next bug ID with retry logic for concurrency safety.

    Uses a retry mechanism to handle potential race conditions in
    concurrent scenarios. Falls back to timestamp-based ID if
    collisions are detected.

    Returns:
        str: Next bug ID in format BUG-XXX
    """
    max_retries = 3
    for attempt in range(max_retries):
        data = load_progress_json()
        if not data:
            return "BUG-001"

        bugs = data.get("bugs", [])
        if not bugs:
            return "BUG-001"

        # Extract numeric part and find max
        max_id = 0
        for bug in bugs:
            bug_id = bug.get("id", "BUG-000")
            # Extract number from BUG-XXX format
            try:
                num = int(bug_id.split("-")[1])
                max_id = max(max_id, num)
            except (IndexError, ValueError):
                logger.warning(f"Invalid bug ID format: {bug_id}")
                pass

        new_id = f"BUG-{max_id + 1:03d}"

        # Verify ID doesn't exist (race condition check)
        if not any(b.get("id") == new_id for b in bugs):
            return new_id

        # Retry if collision detected
        if attempt < max_retries - 1:
            logger.warning(f"Bug ID collision detected for {new_id}, retrying...")
            continue

    # Fallback: use timestamp to guarantee uniqueness
    timestamp_suffix = int(datetime.now().timestamp() % 1000)
    fallback_id = f"BUG-{timestamp_suffix:03d}"
    logger.warning(f"Using timestamp-based bug ID: {fallback_id}")
    return fallback_id


def _add_bug_internal(
    description: str,
    status: str = "pending_investigation",
    priority: str = "medium",
    category: str = "bug",
    scheduled_position: Optional[str] = None,
    verification_results: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    import bug_tracker
    return bug_tracker._add_bug_internal(
        description=description,
        status=status,
        priority=priority,
        category=category,
        scheduled_position=scheduled_position,
        verification_results=verification_results,
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        get_next_bug_id_fn=get_next_bug_id,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
    )
_add_bug_internal.is_wrapper = True


def add_bug(
    description: str,
    status: str = "pending_investigation",
    priority: str = "medium",
    category: str = "bug",
    scheduled_position: Optional[str] = None,
    verification_results: Optional[str] = None,
) -> bool:
    import bug_tracker
    return bug_tracker.add_bug(
        description=description,
        status=status,
        priority=priority,
        category=category,
        scheduled_position=scheduled_position,
        verification_results=verification_results,
        add_bug_internal_fn=_add_bug_internal,
    )
add_bug.is_wrapper = True


def add_task_item(
    description: str,
    details: str = "",
    refs: Optional[List[str]] = None,
    next_action: str = "",
    priority: str = "P1",
    workflow_profile: str = WORKFLOW_PROFILE_DEFAULT,
    parent_feature_id: Optional[int] = None,
) -> Optional[str]:
    import work_item_commands

    return work_item_commands.add_task_item_command(
        description,
        svc=_make_work_item_commands_services(),
        details=details,
        refs=refs,
        next_action=next_action,
        priority=priority,
        workflow_profile=workflow_profile,
        parent_feature_id=parent_feature_id,
    )
add_task_item.is_wrapper = True


def smart_intake(
    candidate_json: str,
    commit: Optional[str] = None,
    workflow_profile: str = WORKFLOW_PROFILE_DEFAULT,
) -> bool:
    import work_item_commands

    return work_item_commands.smart_intake_command(
        candidate_json,
        svc=_make_work_item_commands_services(),
        commit=commit,
        workflow_profile=workflow_profile,
    )
smart_intake.is_wrapper = True


def update_bug(
    bug_id: str,
    status: Optional[str] = None,
    root_cause: Optional[str] = None,
    fix_summary: Optional[str] = None,
) -> bool:
    import bug_tracker
    return bug_tracker.update_bug(
        bug_id=bug_id,
        status=status,
        root_cause=root_cause,
        fix_summary=fix_summary,
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        auto_state_commit_fn=_auto_state_commit,
    )
update_bug.is_wrapper = True


def list_bugs() -> bool:
    import bug_tracker
    return bug_tracker.list_bugs(
        load_progress_json_fn=load_progress_json,
    )
list_bugs.is_wrapper = True


def remove_bug(bug_id: str):
    """Remove a bug from tracking (use for false positives)."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found.")
        return False

    bugs = data.get("bugs", [])
    if not bugs:
        print(f"No bugs found. Bug {bug_id} does not exist.")
        return False

    bug = next((b for b in bugs if b.get("id") == bug_id), None)
    if not bug:
        print(f"Bug {bug_id} not found.")
        return False

    print(f"Removing bug: {bug_id}")
    print(f"Description: {bug.get('description', 'No description')}")

    # Remove bug
    data["bugs"] = [b for b in bugs if b.get("id") != bug_id]

    # Clear current bug if this was it
    if data.get("current_bug_id") == bug_id:
        data["current_bug_id"] = None

    save_progress_json(data)
    save_progress_md("")

    print(f"Bug {bug_id} removed from tracking.")
    return True


def reset_tracking(force=False, remove_active=False):
    """Reset active progress tracking files (thin shim; logic in admin_ops)."""
    import admin_ops

    progress_dir = get_progress_dir()
    tracked_files = [
        progress_dir / PROGRESS_JSON,
        progress_dir / PROGRESS_MD,  # legacy cleanup only; no longer generated/tracked
        progress_dir / CHECKPOINTS_JSON,
    ]
    return admin_ops.reset_tracking(
        force=force,
        remove_active=remove_active,
        progress_dir=progress_dir,
        tracked_files=tracked_files,
        summary_file=progress_dir / STATUS_SUMMARY_FILE,
        legacy_summary_file=progress_dir / STATUS_SUMMARY_LEGACY_FILE,
        schema_version=CURRENT_SCHEMA_VERSION,
        root_route_code=ROOT_ROUTE_CODE,
        logger=logger,
        input_fn=input,
        load_progress_json=load_progress_json,
        save_progress_json=save_progress_json,
        save_progress_md=save_progress_md,
        save_checkpoints=save_checkpoints,
        generate_progress_md=generate_progress_md,
        archive_current_progress=archive_current_progress,
        record_reset_event=lambda: record_feature_state_event(
            event_type="tracker_reset",
            feature_id=None,
            feature_name=None,
        ),
        find_project_root=find_project_root,
        resolve_repo_root=_resolve_repo_root,
        auto_discover_child_plugins=_auto_discover_child_plugins,
        load_status_summary_projection=load_status_summary_projection,
    )


reset_tracking.is_wrapper = True


def set_workflow_state(phase=None, plan_path=None, next_action=None):
    """Set workflow state for current feature."""
    import workflow_commands

    return workflow_commands.set_workflow_state_command(
        phase=phase,
        plan_path=plan_path,
        next_action=next_action,
        svc=_make_workflow_commands_services(),
    )
set_workflow_state.is_wrapper = True


def update_workflow_task(task_id, status):
    """Update task completion status in workflow_state."""
    import workflow_commands

    return workflow_commands.update_workflow_task_command(
        task_id, status, svc=_make_workflow_commands_services()
    )
update_workflow_task.is_wrapper = True


def clear_workflow_state():
    """Clear workflow state from progress tracking."""
    import workflow_commands

    return workflow_commands.clear_workflow_state_command(
        svc=_make_workflow_commands_services()
    )
clear_workflow_state.is_wrapper = True


def health_check():
    """Perform health check and return JSON metrics (0 healthy, 1 degraded)."""
    import workflow_commands

    return workflow_commands.health_check_command(
        svc=_make_workflow_commands_services()
    )
health_check.is_wrapper = True


def validate_plan(plan_path: Optional[str] = None):
    """Validate workflow plan path and minimum plan document structure."""
    import workflow_commands

    return workflow_commands.validate_plan_command(
        plan_path, svc=_make_workflow_commands_services()
    )
validate_plan.is_wrapper = True


def generate_direct_tdd_note() -> bool:
    import doc_generator
    return doc_generator.generate_direct_tdd_note(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        find_project_root_fn=find_project_root,
        validate_plan_document_fn=validate_plan_document,
        set_workflow_state_fn=set_workflow_state,
        validate_plan_path_fn=validate_plan_path,
    )
generate_direct_tdd_note.is_wrapper = True


def generate_progress_md(data: Dict[str, Any]) -> str:
    """Deprecated: progress.md generation is disabled."""
    return ""
generate_progress_md.is_wrapper = True


def _scope_hint(path: Path, repo_root: Path) -> str:
    """Render a path as repo-relative when possible for CLI guidance."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _extract_command_tail(argv: Sequence[str], command: str) -> List[str]:
    """Extract command + args tail from argv for retry hints."""
    try:
        index = list(argv).index(command)
    except ValueError:
        return [command]
    return list(argv[index:])


def _discover_parent_route_bindings_for_child(
    child_project_root: Path,
    repo_root: Path,
) -> List[Dict[str, Any]]:
    import route_commands
    return route_commands._discover_parent_route_bindings_for_child(
        child_project_root, repo_root,
        resolve_main_repo_path_fn=_resolve_main_repo_path,
    )
_discover_parent_route_bindings_for_child.is_wrapper = True


def _print_route_preflight_block(
    *,
    reason: str,
    command: str,
    argv: Sequence[str],
    child_project_root: Path,
    repo_root: Path,
    child_code: Optional[str],
    parent_project_root: Optional[Path],
) -> None:
    import route_commands
    return route_commands._print_route_preflight_block(
        reason=reason,
        command=command,
        argv=argv,
        child_project_root=child_project_root,
        repo_root=repo_root,
        child_code=child_code,
        parent_project_root=parent_project_root,
        extract_command_tail_fn=_extract_command_tail,
        scope_hint_fn=_scope_hint,
    )
_print_route_preflight_block.is_wrapper = True


def enforce_route_preflight(command: str, argv: Sequence[str]) -> bool:
    import route_commands
    return route_commands.enforce_route_preflight(
        command,
        argv,
        project_root=find_project_root(),
        repo_root=Path(_REPO_ROOT or find_project_root()),
        load_progress_json_fn=load_progress_json,
        resolve_main_repo_path_fn=_resolve_main_repo_path,
        extract_command_tail_fn=_extract_command_tail,
        scope_hint_fn=_scope_hint,
    )
enforce_route_preflight.is_wrapper = True


def check_worktree_branch_consistency(command: str) -> bool:
    import worktree_handler
    return worktree_handler.check_worktree_branch_consistency(
        command,
        load_progress_json_fn=load_progress_json,
        collect_git_context_fn=collect_git_context,
        compare_contexts_fn=compare_contexts,
        find_project_root_fn=find_project_root,
        detect_default_branch_fn=_detect_default_branch,
    )
check_worktree_branch_consistency.is_wrapper = True



def _suggest_command(unknown: str, valid_commands: List[str]) -> Optional[str]:
    """Return best suggestion for an unknown command, or None if no good match.

    Priority:
    1. Ghost-command alias table (always shown when matched).
    2. Levenshtein edit-distance <= 2 to closest valid command.
    """
    if unknown in _GHOST_COMMAND_ALIASES:
        return _GHOST_COMMAND_ALIASES[unknown]

    def _edit_distance(a: str, b: str) -> int:
        m, n = len(a), len(b)
        dp = list(range(n + 1))
        for i in range(1, m + 1):
            prev = dp[0]
            dp[0] = i
            for j in range(1, n + 1):
                temp = dp[j]
                if a[i - 1] == b[j - 1]:
                    dp[j] = prev
                else:
                    dp[j] = 1 + min(prev, dp[j], dp[j - 1])
                prev = temp
        return dp[n]

    best, best_dist = None, 3  # threshold: distance must be <= 2
    for cmd in valid_commands:
        d = _edit_distance(unknown, cmd)
        if d < best_dist:
            best, best_dist = cmd, d
    return best  # None if nothing within threshold


class _ProgressArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that provides ghost-command and edit-distance
    'Did you mean?' suggestions on unknown *subcommand* errors.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._registered_commands: List[str] = []

    def register_commands(self, commands: List[str]) -> None:
        """Called in main() after all subparsers are added."""
        self._registered_commands = list(commands)

    def error(self, message: str) -> None:
        import re
        if "argument command: invalid choice:" in message:
            match = re.search(r"invalid choice: '([^']+)'", message)
            if match:
                unknown = match.group(1)
                suggestion = _suggest_command(unknown, self._registered_commands)
                self.print_usage(sys.stderr)
                if suggestion:
                    sys.stderr.write(f"{self.prog}: error: unknown command '{unknown}'\n")
                    sys.stderr.write(f"Did you mean: '{suggestion}'?\n")
                    sys.stderr.write(f"Run: {self.prog} {suggestion.split()[0]} --help\n")
                else:
                    sys.stderr.write(f"{self.prog}: error: {message}\n")
                sys.exit(2)
        super().error(message)


if SPRINT_LEDGER_AVAILABLE:
    import sprint_ledger
    sprint_ledger.register_callbacks(
        progress_transaction_fn=progress_transaction,
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        find_project_root_fn=find_project_root,
    )


def entropy_check(output_json: bool = False) -> int:
    return workspace_entropy.entropy_check_command(output_json=output_json)


entropy_check.is_wrapper = True


def entropy_fix(*, safe: bool = False, apply: bool = False, output_json: bool = False) -> int:
    return workspace_entropy.entropy_fix_command(
        safe=safe,
        apply=apply,
        output_json=output_json,
    )


entropy_fix.is_wrapper = True


def main():
    parser = _ProgressArgumentParser(description="Progress Tracker Manager")
    parser.add_argument(
        "--project-root",
        help=(
            "Target project root. Required in monorepo root contexts, e.g. "
            "'plugins/note-organizer'."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize progress tracking")
    init_parser.add_argument("project_name", help="Name of the project")
    init_parser.add_argument(
        "--force", action="store_true", help="Force re-initialization"
    )
    init_parser.add_argument(
        "--confirm-destroy",
        action="store_true",
        dest="confirm_destroy",
        help="Required when --force is used and the project has completed features.",
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Show progress status")
    status_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output only",
    )

    # Check command
    check_parser = subparsers.add_parser("check", help="Check for incomplete progress")
    check_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output only",
    )
    reconcile_parser = subparsers.add_parser(
        "reconcile", help="Diagnose tracker drift and suggest the next safe action"
    )
    reconcile_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    next_feature_parser = subparsers.add_parser(
        "next-feature", help="Show next actionable feature (skips deferred features)"
    )
    next_feature_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    next_feature_parser.add_argument(
        "--ack-planning-risk",
        action="store_true",
        dest="ack_planning_risk",
        help="Acknowledge planning preflight warnings and continue selection",
    )

    # PT-F13: ``next`` alias for ``next-feature`` (unified work-item selection).
    next_alias_parser = subparsers.add_parser(
        "next",
        help="Alias for next-feature (unified work-item selection)",
    )
    next_alias_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    next_alias_parser.add_argument(
        "--ack-planning-risk",
        action="store_true",
        dest="ack_planning_risk",
        help="Acknowledge planning preflight warnings and continue selection",
    )
    next_alias_parser.add_argument(
        "--done",
        action="store_true",
        dest="done",
        help="Close the current active task (prog next --done)",
    )

    # PT-F14: `add-task` direct task creation CLI.
    add_task_parser = subparsers.add_parser(
        "add-task",
        help="Create a new task item",
    )
    add_task_parser.add_argument(
        "--description", required=True, help="Task description"
    )
    add_task_parser.add_argument(
        "--feature-id", type=int, dest="feature_id", default=None,
        help="Bind to parent feature ID (mutually exclusive with --workflow-profile quick_task)",
    )
    add_task_parser.add_argument(
        "--workflow-profile",
        choices=sorted(WORKFLOW_PROFILE_VALUES),
        default=WORKFLOW_PROFILE_DEFAULT,
        dest="workflow_profile",
        help="Workflow profile",
    )
    add_task_parser.add_argument(
        "--priority", choices=["P0", "P1", "P2"], default="P1",
        help="Task priority",
    )
    add_task_parser.add_argument(
        "--details", default="", help="Extended details",
    )

    # PT-F13: ``smart`` deterministic work-item intake executor.
    smart_parser = subparsers.add_parser(
        "smart",
        help="Deterministic work-item intake executor (preview or commit)",
    )
    smart_parser.add_argument(
        "--candidate-json",
        required=True,
        help="JSON string with type, confidence, and profile fields",
    )
    smart_parser.add_argument(
        "--commit",
        choices=["bug", "feature", "task", "update"],
        help="Commit the candidate to the specified work-item type",
    )
    smart_parser.add_argument(
        "--workflow-profile",
        choices=sorted(WORKFLOW_PROFILE_VALUES),
        default=WORKFLOW_PROFILE_DEFAULT,
        help="workflow_profile for task commits",
    )

    # Archive history commands
    archives_parser = subparsers.add_parser(
        "list-archives", help="List archived progress snapshots"
    )
    archives_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum number of archives to display"
    )
    restore_parser = subparsers.add_parser(
        "restore-archive", help="Restore archived progress snapshot"
    )
    restore_parser.add_argument("archive_id", help="Archive ID to restore")
    restore_parser.add_argument(
        "--force", action="store_true", help="Overwrite current active progress files"
    )

    # Set current command
    current_parser = subparsers.add_parser("set-current", help="Set current feature")
    current_parser.add_argument("feature_id", type=int, help="Feature ID")

    # Validate readiness command (read-only)
    validate_readiness_parser = subparsers.add_parser(
        "validate-readiness",
        help="Validate feature readiness contract for starting work",
    )
    validate_readiness_parser.add_argument("feature_id", type=int, help="Feature ID")

    validate_planning_parser = subparsers.add_parser(
        "validate-planning",
        help="Validate SPM planning preflight contract using updates+refs",
    )
    validate_planning_parser.add_argument(
        "--feature-id",
        type=int,
        required=True,
        help="Feature ID to evaluate planning readiness for",
    )
    validate_planning_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )

    # Fix readiness command (mutating)
    fix_readiness_parser = subparsers.add_parser(
        "fix-readiness",
        help="Apply structured fixes to feature readiness contract fields",
    )
    fix_readiness_parser.add_argument("feature_id", type=int, help="Feature ID")
    fix_readiness_parser.add_argument(
        "--add-requirement",
        dest="add_requirement",
        help="Requirement ID to add (for example REQ-006)",
    )
    fix_readiness_parser.add_argument(
        "--set-why",
        dest="set_why",
        help="Set change_spec.why",
    )
    fix_readiness_parser.add_argument(
        "--add-acceptance",
        dest="add_acceptance",
        help="Acceptance scenario to append",
    )

    # Set development stage command
    stage_parser = subparsers.add_parser(
        "set-development-stage",
        help="Set development stage for current feature (or a specific feature)",
    )
    stage_parser.add_argument("stage", choices=DEVELOPMENT_STAGES, help="Target stage")
    stage_parser.add_argument("--feature-id", type=int, help="Feature ID (defaults to current)")

    # Complete command
    complete_parser = subparsers.add_parser("complete", help="Mark feature as complete")
    complete_parser.add_argument("feature_id", type=int, help="Feature ID")
    complete_parser.add_argument("--commit", help="Git commit hash")
    complete_parser.add_argument("--skip-archive", action="store_true",
                               help="Skip document archiving")
    complete_parser.add_argument(
        "--unsafe-legacy",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    done_parser = subparsers.add_parser(
        "done",
        help="Complete current feature with acceptance test gatekeeping",
    )
    done_parser.add_argument("--commit", help="Git commit hash (default: HEAD)")
    done_parser.add_argument(
        "--run-all",
        action="store_true",
        help="Run all acceptance tests even if one fails",
    )
    done_parser.add_argument(
        "--skip-archive",
        action="store_true",
        help="Skip document archiving",
    )
    done_parser.add_argument(
        "--no-cleanup",
        action="store_true",
        dest="no_cleanup",
        help="Skip automatic post-done cleanup of worktree and feature branch",
    )
    done_parser.add_argument(
        "--check", action="store_true",
        help="Run all validation gates (acceptance included) without persisting state",
    )
    set_finish_state_parser = subparsers.add_parser(
        "set-finish-state",
        help="Resolve explicit finish_pending integration status for a feature",
    )
    set_finish_state_parser.add_argument(
        "--feature-id",
        type=int,
        required=True,
        help="Feature ID in finish_pending state",
    )
    set_finish_state_parser.add_argument(
        "--status",
        required=True,
        choices=VALID_FINISH_STATES,
        help="Target integration status",
    )
    set_finish_state_parser.add_argument(
        "--reason",
        help="Optional reason for resolution",
    )
    review_pass_parser = subparsers.add_parser(
        "review-pass",
        help="Mark a review lane as passed for a feature",
    )
    review_pass_parser.add_argument(
        "--feature-id",
        type=int,
        required=True,
        help="Feature ID",
    )
    review_pass_parser.add_argument(
        "--lane",
        required=True,
        help="Review lane to mark passed (eng, qa, docs, design, devex)",
    )
    review_pass_parser.add_argument(
        "--evidence",
        help="Optional lane-specific evidence artifact path or summary",
    )

    # Add feature command
    add_parser = subparsers.add_parser("add-feature", help="Add a new feature")
    add_parser.add_argument("name", help="Feature name")
    add_parser.add_argument("test_steps", nargs="+", help="Test steps for the feature")

    # Update feature command
    update_parser = subparsers.add_parser("update-feature", help="Update an existing feature")
    update_parser.add_argument("feature_id", type=int, help="Feature ID")
    update_parser.add_argument("name", help="Updated feature name")
    update_parser.add_argument(
        "test_steps", nargs="*", help="Updated test steps (optional)"
    )

    # Set sprint contract command
    sprint_contract_parser = subparsers.add_parser(
        "set-sprint-contract", help="Set sprint contract fields for a feature"
    )
    sprint_contract_parser.add_argument(
        "--feature-id", type=int, required=True, help="Feature ID"
    )
    sprint_contract_parser.add_argument(
        "--scope", required=True, help="Scope description for the sprint contract"
    )
    sprint_contract_parser.add_argument(
        "--done-criteria",
        nargs="+",
        required=True,
        help="One or more done criteria items",
    )
    sprint_contract_parser.add_argument(
        "--test-plan",
        nargs="+",
        required=True,
        help="One or more test plan items",
    )

    # Defer command
    defer_parser = subparsers.add_parser(
        "defer", help="Defer one feature or all pending features"
    )
    defer_target_group = defer_parser.add_mutually_exclusive_group(required=True)
    defer_target_group.add_argument(
        "--all-pending", action="store_true", help="Defer all pending (not completed) features"
    )
    defer_target_group.add_argument("--feature-id", type=int, help="Feature ID to defer")
    defer_parser.add_argument("--reason", required=True, help="Reason for deferring")
    defer_parser.add_argument(
        "--defer-group", help="Optional defer group identifier for later resume"
    )

    # Resume command
    resume_parser = subparsers.add_parser(
        "resume", help="Resume deferred features (all or by defer group)"
    )
    resume_target_group = resume_parser.add_mutually_exclusive_group(required=True)
    resume_target_group.add_argument("--all", action="store_true", help="Resume all deferred features")
    resume_target_group.add_argument("--defer-group", help="Resume deferred features in this group")

    # Structured updates commands
    add_update_parser = subparsers.add_parser(
        "add-update", help="Append a structured progress update entry"
    )
    add_update_parser.add_argument("--category", required=True, help="Update category")
    add_update_parser.add_argument("--summary", required=True, help="Short summary")
    add_update_parser.add_argument("--details", help="Additional details")
    add_update_parser.add_argument("--feature-id", type=int, help="Related feature ID")
    add_update_parser.add_argument("--bug-id", help="Related bug ID")
    add_update_parser.add_argument("--role", help="Role: architecture|coding|testing")
    add_update_parser.add_argument("--owner", help="Owner for the role")
    add_update_parser.add_argument(
        "--source",
        default="prog_update",
        help="Source: prog_update|spm_meeting|spm_assign|spm_planning|manual",
    )
    add_update_parser.add_argument("--next-action", help="Suggested next action")
    add_update_parser.add_argument(
        "--ref",
        action="append",
        dest="refs",
        default=[],
        help="Reference token (repeatable)",
    )

    list_updates_parser = subparsers.add_parser("list-updates", help="List recent updates")
    list_updates_parser.add_argument("--limit", type=int, default=0, help="Max updates (0=all)")

    set_owner_parser = subparsers.add_parser(
        "set-feature-owner", help="Assign feature owner for a role"
    )
    set_owner_parser.add_argument("feature_id", type=int, help="Feature ID")
    set_owner_parser.add_argument("role", help="Role: architecture|coding|testing")
    set_owner_parser.add_argument("owner", help="Owner name (use 'none' to clear)")

    # Undo command
    subparsers.add_parser("undo", help="Undo last completed feature")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset progress tracking")
    reset_parser.add_argument(
        "--force", action="store_true", help="Force reset without confirmation"
    )
    reset_parser.add_argument(
        "--remove-active", action="store_true",
        help="Completely remove active progress tracking files instead of recreating an empty baseline"
    )

    # Set workflow state command
    workflow_parser = subparsers.add_parser(
        "set-workflow-state", help="Set workflow state for current feature"
    )
    workflow_parser.add_argument("--phase", help="Workflow phase")
    workflow_parser.add_argument("--plan-path", help="Path to plan file")
    workflow_parser.add_argument("--next-action", help="Next action to take")

    # Update workflow task command
    task_parser = subparsers.add_parser(
        "update-workflow-task", help="Update task completion status"
    )
    task_parser.add_argument("task_id", type=int, help="Task ID")
    task_parser.add_argument("status", choices=["completed"], help="Task status")

    # Clear workflow state command
    subparsers.add_parser("clear-workflow-state", help="Clear workflow state")

    # Health check command
    subparsers.add_parser("health", help="Perform health check and return metrics")
    subparsers.add_parser(
        "git-sync-check",
        help="Run non-blocking Git sync preflight and print risk warnings",
    )
    preflight_parser = subparsers.add_parser(
        "git-auto-preflight",
        help="Run git-auto preflight and emit tri-state workspace decision",
    )
    preflight_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )

    entropy_check_parser = subparsers.add_parser(
        "entropy-check", help="Inspect workspace entropy and emit cleanup decisions"
    )
    entropy_check_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )

    entropy_fix_parser = subparsers.add_parser(
        "entropy-fix", help="Apply safe workspace entropy cleanup actions"
    )
    entropy_fix_parser.add_argument("--safe", action="store_true", help="Apply only green (safe) actions")
    entropy_fix_parser.add_argument("--apply", action="store_true", help="Also apply yellow (quarantine) actions")
    entropy_fix_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )

    # Feature AI metrics commands
    ai_metrics_parser = subparsers.add_parser(
        "set-feature-ai-metrics", help="Set AI metrics for a feature"
    )
    ai_metrics_parser.add_argument("feature_id", type=int, help="Feature ID")
    ai_metrics_parser.add_argument(
        "--complexity-score", type=int, required=True, help="Must be in range 0-100"
    )
    ai_metrics_parser.add_argument(
        "--selected-model", choices=["haiku", "sonnet", "opus"], required=True, help="Model used"
    )
    ai_metrics_parser.add_argument(
        "--workflow-path", required=True,
        choices=["direct_tdd", "plan_execute", "full_design_plan_execute"],
        help="Workflow path used for implementation"
    )
    ai_metrics_parser.add_argument(
        "--confidence",
        choices=["high", "medium", "low"],
        default="medium",
        help="Confidence level of complexity assessment (high/medium/low)"
    )
    ai_metrics_parser.add_argument(
        "--bucket-override",
        choices=["simple", "standard", "complex"],
        default=None,
        help="Override routed bucket when confidence upgrade or force rules apply"
    )

    complete_ai_metrics_parser = subparsers.add_parser(
        "complete-feature-ai-metrics", help="Finalize AI metrics duration for feature"
    )
    complete_ai_metrics_parser.add_argument("feature_id", type=int, help="Feature ID")

    # Auto-checkpoint command
    subparsers.add_parser("auto-checkpoint", help="Create checkpoint snapshot if interval elapsed")

    # wf-auto-driver command
    subparsers.add_parser("wf-auto-driver", help="Compute and write back pending_action to workflow_state")

    # reconcile-evaluator command
    reconcile_evaluator_parser = subparsers.add_parser(
        "reconcile-evaluator",
        help="Backfill evaluator results for completed features missing evaluation",
    )
    reconcile_evaluator_parser.add_argument(
        "--feature-id",
        type=int,
        default=None,
        dest="feature_id",
        help="Backfill a specific feature by ID (default: scan all completed features)",
    )
    reconcile_evaluator_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )

    sync_linked_parser = subparsers.add_parser(
        "sync-linked", help="Refresh linked project snapshots into linked_snapshot"
    )
    sync_linked_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    sync_linked_parser.add_argument(
        "--stale-after-hours",
        type=int,
        default=DEFAULT_LINKED_STATUS_STALE_HOURS,
        help="Staleness threshold in hours for linked snapshots",
    )
    sync_linked_parser.add_argument(
        "--repair-routes",
        action="store_true",
        dest="repair_routes",
        help="Rebuild active_routes from child current_feature_id (skips completed/deferred)",
    )
    link_project_parser = subparsers.add_parser(
        "link-project",
        help=(
            "Register child tracker into linked_projects/routing_queue. "
            "Use global --project-root for child path."
        ),
    )
    link_project_parser.add_argument(
        "--code",
        required=True,
        help="Project code token for route coordination (e.g. NO, APP2)",
    )
    link_project_parser.add_argument(
        "--label",
        help="Optional display label for linked project entry",
    )
    link_project_parser.add_argument(
        "--parent-root",
        help=(
            "Optional parent tracker root when invoking from monorepo root. "
            "Defaults to current working project."
        ),
    )
    link_project_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    discover_children_parser = subparsers.add_parser(
        "discover-children",
        help="Auto-discover and register child trackers under a parent.",
    )
    discover_children_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    route_status_parser = subparsers.add_parser(
        "route-status",
        help="Display routing_queue, active_routes, and conflict summary.",
    )
    route_status_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    prioritize_parser = subparsers.add_parser(
        "prioritize",
        help="Move a queue entry to the front of routing_queue.",
    )
    prioritize_parser.add_argument(
        "code",
        help="Queue code to prioritize (e.g. PT, ROOT)",
    )
    prioritize_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    set_queue_parser = subparsers.add_parser(
        "set-queue",
        help="Replace routing_queue with an ordered list of codes.",
    )
    set_queue_parser.add_argument(
        "codes",
        nargs="+",
        help="Ordered list of queue codes (e.g. PT ROOT NO)",
    )
    set_queue_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow dropping existing queue codes",
    )
    set_queue_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    route_select_parser = subparsers.add_parser(
        "route-select",
        help="Upsert active_routes entry for a project code (unique key).",
    )
    route_select_parser.add_argument(
        "--project",
        required=True,
        help="Project code token to select (e.g. NO, APP2)",
    )
    route_select_parser.add_argument(
        "--feature-ref",
        dest="feature_ref",
        help="Feature reference within the project (e.g. NO-F3). Omit to preserve existing.",
    )
    route_select_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    runtime_sync_parser = subparsers.add_parser(
        "sync-runtime-context",
        help="Record current session/worktree context without changing semantic progress timestamps",
    )
    runtime_sync_parser.add_argument(
        "--source",
        choices=["session_start", "manual"],
        default="manual",
        help="Source of runtime context sync",
    )
    runtime_sync_parser.add_argument(
        "--quiet", action="store_true", help="Suppress non-essential output"
    )
    runtime_sync_parser.add_argument(
        "--force", action="store_true", help="Write even when context fingerprint is unchanged"
    )

    # Plan validation command
    validate_plan_parser = subparsers.add_parser(
        "validate-plan", help="Validate plan path and required plan sections"
    )
    validate_plan_parser.add_argument(
        "--plan-path",
        help="Plan path to validate (defaults to workflow_state.plan_path)",
    )

    # Direct TDD execution note generation
    subparsers.add_parser(
        "generate-direct-tdd-note",
        help="Generate lightweight execution note for direct_tdd features",
    )

    # Add bug command
    bug_parser = subparsers.add_parser("add-bug", help="Add a new bug")
    bug_parser.add_argument("--description", required=True, help="Bug description")
    bug_parser.add_argument("--status", default="pending_investigation",
                           choices=["pending_investigation", "investigating", "confirmed", "fixing", "fixed", "false_positive"],
                           help="Bug status")
    bug_parser.add_argument("--priority", default="medium",
                           choices=["high", "medium", "low"],
                           help="Bug priority")
    bug_parser.add_argument("--category", default="bug",
                           choices=["bug", "technical_debt"],
                           help="Bug category")
    bug_parser.add_argument("--scheduled-position", help="Scheduling position (e.g., 'before:3', 'after:2', 'last')")
    bug_parser.add_argument("--verification-results", help="JSON string of verification results")

    # Update bug command
    update_bug_parser = subparsers.add_parser("update-bug", help="Update bug status or information")
    update_bug_parser.add_argument("--bug-id", required=True, help="Bug ID (e.g., BUG-001)")
    update_bug_parser.add_argument("--status",
                                  choices=["pending_investigation", "investigating", "confirmed", "fixing", "fixed", "false_positive"],
                                  help="New status")
    update_bug_parser.add_argument("--root-cause", help="Root cause description")
    update_bug_parser.add_argument("--fix-summary", help="Summary of fix applied")

    # List bugs command
    subparsers.add_parser("list-bugs", help="List all bugs")

    # Remove bug command
    remove_bug_parser = subparsers.add_parser("remove-bug", help="Remove a bug")
    remove_bug_parser.add_argument("bug_id", help="Bug ID to remove")

    # ship-check command (PR-5)
    ship_check_parser = subparsers.add_parser("ship-check", help="Run unified pre-archive ship gate")
    ship_check_parser.add_argument("--feature-id", type=int, required=True)
    ship_check_parser.add_argument("--coverage-min", type=float, default=0.8)

    # reconcile-state command (F0: Event Sourcing)
    rs_parser = subparsers.add_parser(
        "reconcile-state",
        help="Detect and fix progress.json drift by replaying audit.log events"
    )
    rs_parser.add_argument("--check", action="store_true",
                           help="Detect-only, no file modification")
    rs_parser.add_argument("--auto-commit", action="store_true",
                           help="Auto git-commit after fixing")

    # backfill-event command (F0: Event Sourcing)
    bf_parser = subparsers.add_parser(
        "backfill-event",
        help="Backfill missing feature_completed events for completed features"
    )
    bf_parser.add_argument("--feature-id", type=int, default=None,
                           help="Only backfill this feature ID")
    bf_parser.add_argument("--yes", "-y", action="store_true",
                           help="Skip confirmation prompt")

    # install-git-hooks command (F0: Event Sourcing)
    subparsers.add_parser("install-git-hooks",
                          help="Install post-merge hook for auto reconcile-state")

    # PT-F14: register valid subcommand names for ghost-command suggestions.
    parser.register_commands(list(subparsers.choices.keys()))

    args = parser.parse_args()

    scope_project_root = args.project_root
    if args.command == "link-project":
        scope_project_root = args.parent_root

    if not configure_project_scope(scope_project_root):
        return False

    def _dispatch_command() -> Any:
        if args.command == "init":
            return init_tracking(
                args.project_name,
                force=args.force,
                confirm_destroy=getattr(args, "confirm_destroy", False),
            )
        if args.command == "status":
            return status(output_json=args.output_json)
        if args.command == "check":
            return check(output_json=args.output_json)
        if args.command == "reconcile":
            return reconcile(output_json=args.output_json)
        if args.command == "reconcile-state":
            check_mode = getattr(args, "check", False)
            if not check_mode:
                # 修复模式走 mutating 保护链路
                if not enforce_route_preflight("reconcile-state", sys.argv):
                    return 1
                try:
                    with progress_transaction():
                        r = cmd_reconcile_state(
                            check_only=False,
                            auto_commit=getattr(args, "auto_commit", False),
                        )
                except TimeoutError:
                    print("[reconcile-state] ERROR: Could not acquire progress lock")
                    sys.exit(1)
            else:
                r = cmd_reconcile_state(check_only=True)
            # 退出码：修复后 drift 已消除应返回 0；仅检测到 drift 但未修复才返回 1
            if r["fixed"]:
                sys.exit(0)
            else:
                sys.exit(0 if not r["drift"] else 1)
        if args.command == "backfill-event":
            r = cmd_backfill_event(
                feature_id=getattr(args, "feature_id", None),
                yes=getattr(args, "yes", False),
            )
            sys.exit(0 if r["written"] >= 0 else 1)
        if args.command == "install-git-hooks":
            r = cmd_install_git_hooks()
            sys.exit(0 if r["installed"] else 1)
        if args.command == "reconcile-evaluator":
            return reconcile_evaluator(
                feature_id=args.feature_id,
                output_json=args.output_json,
            )
        if args.command in ("next-feature", "next"):
            return next_feature(
                output_json=args.output_json,
                ack_planning_risk=args.ack_planning_risk,
            )
        if args.command == "list-archives":
            return list_archives(limit=args.limit)
        if args.command == "restore-archive":
            return restore_archive(args.archive_id, force=args.force)
        if args.command == "set-current":
            return set_current(args.feature_id)
        if args.command == "validate-readiness":
            return validate_readiness_command(args.feature_id)
        if args.command == "validate-planning":
            return validate_planning_command(
                args.feature_id,
                output_json=args.output_json,
            )
        if args.command == "fix-readiness":
            return fix_readiness_command(
                args.feature_id,
                add_requirement=args.add_requirement,
                set_why=args.set_why,
                add_acceptance=args.add_acceptance,
            )
        if args.command == "set-development-stage":
            return set_development_stage(args.stage, feature_id=args.feature_id)
        if args.command == "complete":
            if getattr(args, "unsafe_legacy", False):
                return complete_feature(
                    args.feature_id,
                    commit_hash=args.commit,
                    skip_archive=args.skip_archive,
                )

            data = load_progress_json()
            if not data:
                print("[ERROR] No progress tracking found", file=sys.stderr)
                return 4

            current_id = data.get("current_feature_id")
            if args.feature_id != current_id:
                print(
                    f"[ERROR] Feature ID mismatch: complete was given {args.feature_id}, "
                    f"but current_feature_id is {current_id or 'None'}. "
                    f"Use 'prog done' or 'prog set-current {args.feature_id}' first.",
                    file=sys.stderr,
                )
                return 12

            print(
                "[NOTICE] Redirecting 'prog complete' through 'prog done' gatekeeping.",
                file=sys.stderr,
            )
            return cmd_done(
                commit_hash=args.commit,
                run_all=False,
                skip_archive=args.skip_archive,
            )
        if args.command == "done":
            return cmd_done(
                commit_hash=args.commit,
                run_all=args.run_all,
                skip_archive=args.skip_archive,
                no_cleanup=args.no_cleanup,
                check_only=args.check,
            )
        if args.command == "set-finish-state":
            return cmd_set_finish_state(
                feature_id=args.feature_id,
                status=args.status,
                reason=args.reason,
            )
        if args.command == "review-pass":
            return cmd_review_pass(args.feature_id, args.lane, evidence=args.evidence)
        if args.command == "add-feature":
            return add_feature(args.name, args.test_steps, workflow_profile=WORKFLOW_PROFILE_DEFAULT)
        if args.command == "update-feature":
            return update_feature(
                args.feature_id, args.name, args.test_steps if args.test_steps else None
            )
        if args.command == "set-sprint-contract":
            return cmd_set_sprint_contract(
                feature_id=args.feature_id,
                scope=args.scope,
                done_criteria=args.done_criteria,
                test_plan=args.test_plan,
            )
        if args.command == "defer":
            return defer_features(
                feature_id=args.feature_id,
                all_pending=args.all_pending,
                reason=args.reason,
                defer_group=args.defer_group,
            )
        if args.command == "resume":
            return resume_deferred_features(
                defer_group=args.defer_group,
                resume_all=args.all,
            )
        if args.command == "add-update":
            return add_update(
                category=args.category,
                summary=args.summary,
                details=args.details,
                feature_id=args.feature_id,
                bug_id=args.bug_id,
                role=args.role,
                owner=args.owner,
                source=args.source,
                next_action=args.next_action,
                refs=args.refs,
            )
        if args.command == "list-updates":
            if args.limit < 0:
                print("Error: --limit must be 0 (all) or a positive integer", file=sys.stderr)
                return 2
            return list_updates(limit=args.limit)
        if args.command == "set-feature-owner":
            return set_feature_owner(args.feature_id, args.role, args.owner)
        if args.command == "undo":
            return undo_last_feature()
        if args.command == "reset":
            return reset_tracking(force=args.force, remove_active=args.remove_active)
        if args.command == "set-workflow-state":
            return set_workflow_state(
                phase=args.phase,
                plan_path=_normalize_plan_path_cli_arg(args.plan_path),
                next_action=args.next_action,
            )
        if args.command == "update-workflow-task":
            return update_workflow_task(args.task_id, args.status)
        if args.command == "clear-workflow-state":
            return clear_workflow_state()
        if args.command == "health":
            return health_check()
        if args.command == "git-sync-check":
            return git_sync_check()
        if args.command == "git-auto-preflight":
            return git_auto_preflight(output_json=args.output_json)
        if args.command == "entropy-check":
            return entropy_check(output_json=getattr(args, "output_json", False))
        if args.command == "entropy-fix":
            return entropy_fix(
                safe=getattr(args, "safe", False),
                apply=getattr(args, "apply", False),
                output_json=getattr(args, "output_json", False),
            )
        if args.command == "set-feature-ai-metrics":
            return set_feature_ai_metrics(
                args.feature_id,
                args.complexity_score,
                args.selected_model,
                args.workflow_path,
                confidence=args.confidence,
                bucket_override=args.bucket_override,
            )
        if args.command == "complete-feature-ai-metrics":
            return complete_feature_ai_metrics(args.feature_id)
        if args.command == "auto-checkpoint":
            return auto_checkpoint()
        if args.command == "wf-auto-driver":
            return _cmd_wf_auto_driver()
        if args.command == "sync-linked":
            return sync_linked(
                output_json=args.output_json,
                stale_after_hours=args.stale_after_hours,
                repair_routes=getattr(args, "repair_routes", False),
            )
        if args.command == "link-project":
            return link_project(
                child_project_root=args.project_root,
                code=args.code,
                label=args.label,
                output_json=args.output_json,
            )
        if args.command == "discover-children":
            return discover_children(output_json=args.output_json)
        if args.command == "route-status":
            return route_status(output_json=args.output_json)
        if args.command == "prioritize":
            return prioritize_route(code=args.code, output_json=args.output_json)
        if args.command == "set-queue":
            return set_routing_queue(
                codes=args.codes,
                force=args.force,
                output_json=args.output_json,
            )
        if args.command == "route-select":
            return route_select(
                args.project,
                feature_ref=args.feature_ref,
                output_json=args.output_json,
            )
        if args.command == "sync-runtime-context":
            return sync_runtime_context(source=args.source, quiet=args.quiet, force=args.force)
        if args.command == "validate-plan":
            return validate_plan(plan_path=_normalize_plan_path_cli_arg(args.plan_path))
        if args.command == "generate-direct-tdd-note":
            return generate_direct_tdd_note()
        if args.command == "add-bug":
            try:
                return add_bug(
                    description=args.description,
                    status=args.status,
                    priority=args.priority,
                    category=args.category,
                    scheduled_position=args.scheduled_position,
                    verification_results=args.verification_results
                )
            except ValueError as e:
                print(f"Error: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error adding bug: {e}")
                print(f"Error: Failed to add bug - {e}")
                return False
        if args.command == "add-task":
            # Mutual exclusion: --feature-id + quick_task profile
            if args.feature_id is not None and args.workflow_profile == "quick_task":
                print("Error: --feature-id and --workflow-profile quick_task are mutually exclusive")
                return 2
            task_id = add_task_item(
                description=args.description,
                details=args.details,
                priority=args.priority,
                workflow_profile=args.workflow_profile,
                parent_feature_id=args.feature_id,
            )
            return 0 if task_id is not None else 1
        if args.command == "update-bug":
            return update_bug(
                bug_id=args.bug_id,
                status=args.status,
                root_cause=args.root_cause,
                fix_summary=args.fix_summary
            )
        if args.command == "list-bugs":
            return list_bugs()
        if args.command == "remove-bug":
            return remove_bug(args.bug_id)
        if args.command == "ship-check":
            return cmd_ship_check(args.feature_id, coverage_min=args.coverage_min)
        parser.print_help()
        return 1

    # F21: fail-closed scope consistency check for next-feature, next, and done
    # next --done is a task close, not a feature selection — skip branch check.
    if args.command in {"next-feature", "next", "done"} and not getattr(args, "done", False):
        if not check_worktree_branch_consistency(args.command):
            return 1

    # PT-F13: `smart` is dual-mode (preview vs commit). It is intentionally
    # NOT in MUTATING_COMMANDS to keep preview as a zero-side-effect path.
    # Only the --commit branch runs preflight + progress_transaction().
    if args.command == "smart":
        if args.commit:
            if not enforce_route_preflight("smart", sys.argv):
                return 1
            try:
                with progress_transaction():
                    return smart_intake(
                        candidate_json=args.candidate_json,
                        commit=args.commit,
                        workflow_profile=args.workflow_profile,
                    )
            except TimeoutError as exc:
                print(f"Error: {exc}")
                return False
        return smart_intake(
            candidate_json=args.candidate_json,
            commit=None,
            workflow_profile=args.workflow_profile,
        )

    # PT-F14: `next --done` closes the current task. Like `done`, it bypasses
    # the outer progress_transaction() lock to avoid BUG-002 class deadlocks.
    if args.command == "next" and getattr(args, "done", False):
        return _close_current_task(output_json=getattr(args, "output_json", False))

    if args.command in MUTATING_COMMANDS:
        if not enforce_route_preflight(args.command, sys.argv):
            return 1
        # `done` and the `complete` → cmd_done redirect path may execute nested
        # `prog` mutating commands from acceptance steps. Holding an outer process
        # lock here deadlocks those subprocess invocations (BUG-002).
        # `complete --unsafe-legacy` calls complete_feature() which has no
        # internal locking, so it still needs the outer transaction guard.
        if args.command == "done" or (
            args.command == "complete" and not getattr(args, "unsafe_legacy", False)
        ):
            return _dispatch_command()
        try:
            with progress_transaction():
                return _dispatch_command()
        except TimeoutError as exc:
            print(f"Error: {exc}")
            return False

    return _dispatch_command()


if __name__ == "__main__":
    result = main()
    if isinstance(result, bool):
        sys.exit(0 if result else 1)
    if isinstance(result, int):
        sys.exit(result)
    sys.exit(0 if result else 1)
