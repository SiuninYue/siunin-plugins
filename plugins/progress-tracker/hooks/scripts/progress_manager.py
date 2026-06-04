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
from typing import Optional, List, Dict, Any, Tuple, Set, Sequence

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
    get_progress_md_path,
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
import progress_prompt_builders
import readiness_validator
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
    PROGRESS_MD,
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
# Superpowers writing-plans standard: docs/plans/ and docs/superpowers/plans/
PLAN_PATH_PREFIX = "docs/plans/"
SUPERPOWERS_PLAN_PATH_PREFIX = "docs/superpowers/plans/"
VALID_PLAN_PREFIXES = (PLAN_PATH_PREFIX, SUPERPOWERS_PLAN_PATH_PREFIX)
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
FINISH_PENDING_STATE = "finish_pending"
# Canonical relative paths (from project root) that must never be moved or deleted
# by archive_feature_docs or any other done-flow mutation.
_IMMUTABLE_PROTECTED_RELPATHS: frozenset[str] = frozenset({
    "docs/progress-tracker/architecture/architecture.md",
})
WORK_ITEM_TAXONOMY = frozenset([
    "epic", "feature", "task", "bug", "spike", "risk", "decision", "update"
])

WORKFLOW_PROFILE_VALUES = frozenset([
    "quick_task", "standard_task", "feature_delivery", "hotfix"
])
WORKFLOW_PROFILE_DEFAULT = "standard_task"

UPDATE_CATEGORIES = ("status", "decision", "risk", "handoff", "assignment", "meeting")
UPDATE_SOURCES = ("prog_update", "spm_meeting", "spm_assign", "spm_planning", "manual")
UPDATE_REFS_INLINE_LIMIT = 12
PLANNING_SOURCE = "spm_planning"
PLANNING_REQUIRED_REFS = ("office_hours", "ceo_review")
PLANNING_OPTIONAL_REFS = ("design_review", "devex_review")
PLANNING_ARTIFACT_DIRS = ("docs/product-contracts", "docs/product-reviews")
PLANNING_MESSAGE_KEYS = {
    "gate_disabled": "planning.gate_disabled",
    "missing": "planning.missing",
    "optional_missing": "planning.optional_missing",
    "ready": "planning.ready",
}
PLANNING_SCHEMA_VERSION = "1.0"
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
) -> Dict[str, Optional[str]]:
    """
    Validate workflow plan path shape and optional existence.

    Accepted formats:
    - docs/plans/<YYYY-MM-DD-name>.md
    - docs/superpowers/plans/<YYYY-MM-DD-name>.md  (writing-plans skill)
    """
    if plan_path is None:
        return {"valid": True, "normalized_path": None, "error": None}

    normalized = plan_path.strip().replace("\\", "/")
    if normalized == "":
        return {"valid": True, "normalized_path": "", "error": None}

    if Path(normalized).is_absolute():
        return {
            "valid": False,
            "normalized_path": None,
            "error": "plan_path must be relative (absolute paths are not allowed)",
        }

    if not any(normalized.startswith(prefix) for prefix in VALID_PLAN_PREFIXES):
        return {
            "valid": False,
            "normalized_path": None,
            "error": (
                f"plan_path must be under '{PLAN_PATH_PREFIX}' or "
                f"'{SUPERPOWERS_PLAN_PATH_PREFIX}' ending with .md"
            ),
        }

    if not normalized.endswith(".md"):
        return {
            "valid": False,
            "normalized_path": None,
            "error": "plan_path must end with .md",
        }

    if ".." in Path(normalized).parts:
        return {
            "valid": False,
            "normalized_path": None,
            "error": "plan_path cannot contain '..' segments",
        }

    if require_exists:
        base_root = (target_root or find_project_root()).resolve()
        absolute_path = base_root / normalized
        if not absolute_path.exists():
            # Walk up to git root to find plan files written by writing-plans
            # skill at the repo/worktree root level (e.g. docs/superpowers/plans/).
            found = False
            try:
                git_root = _resolve_repo_root(base_root).resolve()
            except Exception:
                git_root = None
            cursor = base_root
            while True:
                cursor = cursor.parent
                if (cursor / normalized).exists():
                    found = True
                    break
                # Stop after checking git root (or filesystem root).
                if (git_root is not None and cursor == git_root) or cursor == cursor.parent:
                    break
            if not found:
                return {
                    "valid": False,
                    "normalized_path": None,
                    "error": f"plan_path does not exist: {normalized}",
                }

    return {"valid": True, "normalized_path": normalized, "error": None}


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

    md_content = generate_progress_md(data)
    save_progress_md(md_content)

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
        _atomic_write_text(get_progress_md_path(project_root), generate_progress_md(data))


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
        save_progress_md(generate_progress_md(parent_data))

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


def _apply_imported_feature_contract(feature: Dict[str, Any], contract: Dict[str, Any]) -> None:
    """Apply imported contract payload onto a feature record."""
    feature["requirement_ids"] = contract["requirement_ids"]
    feature["change_spec"] = contract["change_spec"]
    feature["acceptance_scenarios"] = contract["acceptance_scenarios"]
    _normalize_feature_contract(feature)


def _make_readiness_validator_services() -> ReadinessValidatorServices:
    """Build the injected-services bundle for readiness_validator commands."""
    return ReadinessValidatorServices(
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        generate_progress_md_fn=generate_progress_md,
        save_progress_md_fn=save_progress_md,
        evaluate_planning_readiness_fn=_evaluate_planning_readiness,
    )


def validate_feature_readiness(feature: Dict[str, Any]) -> Dict[str, Any]:
    return readiness_validator.validate_feature_readiness(feature)
validate_feature_readiness.is_wrapper = True


def print_readiness_warnings(report: Dict[str, Any]) -> None:
    return readiness_validator.print_readiness_warnings(report)
print_readiness_warnings.is_wrapper = True


def _build_readiness_fix_commands(feature_id: int, errors: List[str]) -> List[str]:
    return readiness_validator._build_readiness_fix_commands(feature_id, errors)


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


def _collect_feature_artifact_evidence(
    feature_id: Optional[int], workflow_state: Dict[str, Any]
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

    project_root = find_project_root()
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
    exit_code, stdout, _ = _run_git(
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


def analyze_reconcile_state(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Analyze tracker drift vs implementation evidence and return stable diagnostics."""
    if data is None:
        data = load_progress_json()

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
        latest_feature_checkpoint = _latest_checkpoint_entry_for_feature(
            load_checkpoints(), current_id if isinstance(current_id, int) else None
        )
        expected_context = _build_checkpoint_context(latest_feature_checkpoint) or {}

    current_context = build_runtime_context(data, source="manual")
    context_hint = compare_contexts(expected_context, current_context)

    project_root = find_project_root()
    normalized_project_root = _normalize_context_path(str(project_root))
    execution_project_root = _normalize_context_path(execution_context.get("project_root"))
    runtime_project_root = _normalize_context_path(runtime_context.get("project_root"))
    execution_tracker_root = _normalize_context_path(execution_context.get("tracker_root"))
    runtime_tracker_root = _normalize_context_path(runtime_context.get("tracker_root"))

    feature_artifacts = _collect_feature_artifact_evidence(
        feature_id=current_id if isinstance(current_id, int) else None,
        workflow_state=workflow_state,
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


def reconcile(output_json: bool = False) -> bool:
    """Print reconcile diagnostics and suggested next step."""
    data = load_progress_json()
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

    report = analyze_reconcile_state(data)
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


def cmd_reconcile_state(
    check_only: bool = False,
    auto_commit: bool = False,
) -> Dict[str, Any]:
    """通过 audit.log 事件回放检测并修复 progress.json 的 drift。

    不接受 project_root 参数：使用 find_project_root() 与其余 progress_manager
    命令保持一致。测试通过 _PROJECT_ROOT_OVERRIDE 注入。

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
    effective_root = str(find_project_root())
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
    data = load_progress_json()
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

    save_progress_json(data)
    result["fixed"] = True
    print(f"[reconcile-state] Fixed {len(diff_items)} feature(s) in progress.json")
    print("[reconcile-state] NOTE: Not committed. Run 'git commit' manually, or use --auto-commit.")

    # 6. 可选 auto-commit
    if auto_commit:
        try:
            import subprocess
            progress_json_path = get_progress_dir() / PROGRESS_JSON
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
    """Load the progress.md file content."""
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.load_progress_md(progress_dir=dir_path)


def save_progress_md(content: str, progress_dir: Optional[Path] = None) -> None:
    """Save content to progress.md file."""
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
    md_path = progress_dir / PROGRESS_MD

    if not json_path.exists() and not md_path.exists():
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
        (md_path, "progress_md", "progress.md"),
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
        "progress_md": artifact_by_kind.get("progress_md"),
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

    # 6. Save and regenerate.
    save_progress_json(data)
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print("Active progress cleared — project state is now 0/0.")


def _is_project_fully_completed(data: Dict[str, Any]) -> bool:
    """Return True when all tracked features are completed."""
    features = data.get("features", [])
    if not isinstance(features, list):
        return False
    feature_items = [item for item in features if isinstance(item, dict)]
    if not feature_items:
        return False
    return all(bool(item.get("completed")) for item in feature_items)


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
    active_md = progress_dir / PROGRESS_MD
    has_active = active_json.exists() or active_md.exists()

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

    md_rel = target.get("progress_md")
    if md_rel:
        source_md = progress_dir / md_rel
        if source_md.exists():
            shutil.copy2(source_md, active_md)
        else:
            restored_data = load_progress_json()
            if restored_data:
                save_progress_md(generate_progress_md(restored_data))
    else:
        restored_data = load_progress_json()
        if restored_data:
            save_progress_md(generate_progress_md(restored_data))

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
    checkpoints_path = path or (get_progress_dir() / CHECKPOINTS_JSON)
    if not checkpoints_path.exists():
        return {
            "last_checkpoint_at": None,
            "max_entries": CHECKPOINT_MAX_ENTRIES,
            "entries": [],
        }

    try:
        with open(checkpoints_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning(f"Corrupted checkpoints file: {checkpoints_path}. Reinitializing.")
        return {
            "last_checkpoint_at": None,
            "max_entries": CHECKPOINT_MAX_ENTRIES,
            "entries": [],
        }

    if not isinstance(data, dict):
        return {
            "last_checkpoint_at": None,
            "max_entries": CHECKPOINT_MAX_ENTRIES,
            "entries": [],
        }

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        entries = []

    max_entries = data.get("max_entries", CHECKPOINT_MAX_ENTRIES)
    if not isinstance(max_entries, int) or max_entries <= 0:
        max_entries = CHECKPOINT_MAX_ENTRIES

    return {
        "last_checkpoint_at": data.get("last_checkpoint_at"),
        "max_entries": max_entries,
        "entries": entries,
    }


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

    # Create initial progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

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
                save_progress_md(generate_progress_md(data))
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


def _build_done_handoff_block(
    data: Dict[str, Any],
    project_root: str,
) -> Optional[str]:
    """Build the post-completion handoff block for `/prog done`."""
    next_feature = get_next_feature()
    return progress_prompt_builders.build_done_handoff_block(data, next_feature, project_root)


def _build_project_completion_summary(
    data: Dict[str, Any],
    project_root: str,
) -> str:
    """Build a concise summary when no more pending features remain."""
    return progress_prompt_builders.build_project_completion_summary(data, project_root)


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
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)

    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    if _is_feature_deferred(feature):
        defer_reason = feature.get("defer_reason") or "Deferred feature"
        print(
            f"Feature ID {feature_id} is deferred and cannot be set as current: {defer_reason}. "
            "Run `prog resume` first."
        )
        return False

    if not feature.get("completed", False):
        readiness_report = validate_feature_readiness(feature)
        if not readiness_report["valid"]:
            print_readiness_error(feature, readiness_report)
            return False
        if readiness_report["warnings"]:
            print_readiness_warnings(readiness_report)
            print("")

    previous_current_id = data.get("current_feature_id")
    data["current_feature_id"] = feature_id

    # Selecting a feature for work should immediately enter active development.
    # This keeps `/prog-next` as a one-step start action.
    if not feature.get("completed", False):
        feature["development_stage"] = "developing"
        feature["lifecycle_state"] = "implementing"
        if not feature.get("started_at"):
            feature["started_at"] = _iso_now()

    if previous_current_id != feature_id:
        data.pop("workflow_state", None)
        # Defensive init: even if skill is interrupted before calling
        # set-workflow-state, the feature has a resumable workflow phase.
        if not feature.get("completed", False):
            data["workflow_state"] = {"phase": "planning", "updated_at": _iso_now()}

    # F-11: initialize review lanes when starting a new feature (idempotent)
    if not feature.get("completed", False) and REVIEW_ROUTER_AVAILABLE:
        _initialize_reviews(feature)

    _update_runtime_context(data, source="set_current")
    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    _auto_state_commit(f"F{feature_id}", "start")

    # F17: notify parent tracker to upsert active_routes for this child feature
    if not feature.get("completed", False):
        _notify_parent_sync("activate")

    print(f"Set current feature: {feature.get('name', 'Unknown')}")
    return True


def set_development_stage(stage: str, feature_id: Optional[int] = None) -> bool:
    """Set development_stage for the target feature (defaults to current feature)."""
    if stage not in DEVELOPMENT_STAGES:
        print(f"Invalid development_stage '{stage}'. Must be one of: {DEVELOPMENT_STAGES}")
        return False

    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    target_feature_id = feature_id if feature_id is not None else data.get("current_feature_id")
    if target_feature_id is None:
        print("Error: No active feature. Run '/prog-next' first or pass --feature-id.")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == target_feature_id), None)
    if not feature:
        print(f"Feature ID {target_feature_id} not found")
        return False

    if stage == "developing" and not feature.get("completed", False):
        readiness_report = validate_feature_readiness(feature)
        if not readiness_report["valid"]:
            print_readiness_error(feature, readiness_report)
            return False
        if readiness_report["warnings"]:
            print_readiness_warnings(readiness_report)
            print("")

    feature["development_stage"] = stage
    if stage == "developing" and not feature.get("started_at"):
        feature["started_at"] = _iso_now()
    if stage == "developing":
        feature["lifecycle_state"] = "implementing"
    elif stage == "planning" and not feature.get("completed", False):
        feature["lifecycle_state"] = "approved"
    elif stage == "completed":
        feature["lifecycle_state"] = "verified"

    _update_runtime_context(data, source="set_development_stage")
    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(
        f"Feature #{target_feature_id} stage set to '{stage}': "
        f"{feature.get('name', 'Unknown')}"
    )
    return True


def get_next_feature():
    """Get the next incomplete feature."""
    data = load_progress_json()
    if not data:
        return None

    features = data.get("features", [])
    for feature in features:
        if not feature.get("completed", False) and not _is_feature_deferred(feature):
            return feature

    return None


def _get_dispatched_child_feature(
    routing_queue: List[str],
    active_routes: List[Any],
    linked_projects: List[Any],
    project_root: Path,
    repo_root: Path,
    parent_data: Optional[Dict[str, Any]] = None,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
) -> Optional[Dict[str, Any]]:
    """Scan routing_queue and return the first dispatchable feature, or None.

    Supports ``ROOT_ROUTE_CODE`` for root-level features and child project
    codes for child dispatch.  Emits warnings for unknown non-ROOT codes.
    """
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
            ts = _parse_iso_timestamp(assigned_at)
            if ts is not None:
                now = datetime.now(tz=timezone.utc)
                age_hours = (now - ts).total_seconds() / 3600
                if age_hours > stale_after_hours:
                    is_stale = True
        if not is_stale:
            code = route.get("project_code")
            if code:
                conflicted.add(code)

    # Scan routing_queue for the first dispatchable entry
    for position, code in enumerate(routing_queue, start=1):
        # ROOT: return root-level pending feature
        if code == ROOT_ROUTE_CODE:
            if not isinstance(parent_data, dict):
                continue
            root_features = parent_data.get("features", [])
            if not isinstance(root_features, list):
                continue
            for f in root_features:
                if not isinstance(f, dict):
                    continue
                if not f.get("completed", False) and not _is_feature_deferred(f):
                    return {
                        "dispatched_to": "root",
                        "child_project_code": ROOT_ROUTE_CODE,
                        "child_project_root": str(project_root),
                        "next_feature_id": f.get("id"),
                        "next_feature_name": f.get("name"),
                        "action_required": "prog next",
                        "position": position,
                    }
            continue

        # Unknown non-ROOT code: warn and skip (CONSTRAINT-008)
        if code not in lp_lookup:
            print(f"[WARN] Code \"{code}\" not found in linked_projects, skipping")
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
        child_root = _resolve_linked_project_root(raw_project_root, project_root, repo_root)
        child_data, error = _load_progress_payload_at_root(child_root)
        if error or not child_data:
            continue
        feature = None
        for f in child_data.get("features", []):
            if not isinstance(f, dict):
                continue
            if not f.get("completed", False) and not _is_feature_deferred(f):
                feature = f
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


def _select_next_work_item(
    data: Dict[str, Any],
    project_root: Path,
    repo_root: Path,
) -> Optional[Dict[str, Any]]:
    """Unified work-item selector with priority ordering.

    Priority order:
        P0 bug > P1 bug > standalone task > feature_task (child/root) > P2 bug

    routing_queue scanning:
        ``BUG-<N>``    -> resolved via ``bugs[]``; skipped if status is
                          ``fixed`` / ``false_positive`` or if the same id is
                          present in non-terminal ``active_routes``.
        ``ROOT``       -> root-level pending feature (existing behavior).
        ``<other>``    -> child project dispatch (existing behavior).

    Fallback when routing_queue produces nothing:
        1. Scan ``tasks[]`` for the first pending task.
        2. Otherwise delegate to ``get_next_feature()``.

    Note: P2 (low-priority) bugs are intentionally subordinate to child/root
    feature dispatch. When routing_queue contains both a dispatchable child
    project code and a P2 bug, the child feature is selected first. P2 bugs
    are selected only when no P0/P1 bugs, tasks, or dispatchable child/root
    features remain.

    Returns ``None`` if nothing actionable is found.
    """
    # ------------------------------------------------------------------
    # Step 1: active_route conflict set for BUG-* entries.
    # Stale routes (assigned_at older than DEFAULT_LINKED_STATUS_STALE_HOURS)
    # are treated as non-conflicting, matching the behavior of
    # _get_dispatched_child_feature() for child project codes.
    # ------------------------------------------------------------------
    active_bug_ids: set = set()
    for route in data.get("active_routes") or []:
        if not isinstance(route, dict):
            continue
        status = route.get("status")
        if status in ("done", "cancelled"):
            continue
        # Stale route -> not a conflict (align with _get_dispatched_child_feature)
        assigned_at = route.get("assigned_at")
        if assigned_at:
            ts = _parse_iso_timestamp(assigned_at)
            if ts is not None:
                age_hours = (datetime.now(tz=timezone.utc) - ts).total_seconds() / 3600
                if age_hours > DEFAULT_LINKED_STATUS_STALE_HOURS:
                    continue
        code = route.get("project_code", "")
        if isinstance(code, str) and code.startswith("BUG-"):
            active_bug_ids.add(code)

    # ------------------------------------------------------------------
    # Step 2: bucket routing_queue entries by priority tier.
    # ------------------------------------------------------------------
    bugs_map: Dict[str, Dict[str, Any]] = {
        b["id"]: b
        for b in (data.get("bugs") or [])
        if isinstance(b, dict) and isinstance(b.get("id"), str)
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
    # P0 bugs
    for bug_id, bug in p0_bugs:
        return _bug_item(bug_id, bug, "P0")

    # P1 bugs
    for bug_id, bug in p1_bugs:
        return _bug_item(bug_id, bug, "P1")

    # Standalone tasks (tasks[] scan) before child/root dispatch.
    for task in data.get("tasks") or []:
        if isinstance(task, dict) and task.get("status") == "pending":
            return _task_item(task)

    # Non-bug routing_queue entries (ROOT / child project codes).
    if other_entries:
        active_routes = data.get("active_routes") or []
        linked_projects = data.get("linked_projects") or []
        dispatch_result = _get_dispatched_child_feature(
            other_entries,
            active_routes,
            linked_projects,
            project_root,
            repo_root,
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

    # P2 bugs (lowest priority).
    for bug_id, bug in p2_bugs:
        return _bug_item(bug_id, bug, "P2")

    # ------------------------------------------------------------------
    # Step 4: tasks[] fallback (only when routing_queue exhausted with no
    # actionable bug/child entry). Tasks were already attempted above, but
    # re-check defensively in case routing_queue was empty entirely.
    # ------------------------------------------------------------------
    for task in data.get("tasks") or []:
        if isinstance(task, dict) and task.get("status") == "pending":
            return _task_item(task)

    # ------------------------------------------------------------------
    # Step 5: feature fallback via get_next_feature().
    # ------------------------------------------------------------------
    feature = get_next_feature()
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


def next_feature(output_json: bool = False, ack_planning_risk: bool = False) -> bool:
    """Print the next actionable feature (skipping completed/deferred)."""
    data = load_progress_json()
    if data:
        features = data.get("features", [])
        pending_finish_feature = next(
            (
                feature
                for feature in features
                if isinstance(feature, dict)
                and feature.get("integration_status") == FINISH_PENDING_STATE
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

        reconcile_report = analyze_reconcile_state(data)
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
        # Determine whether routing_queue has any non-bug entries; if it is
        # composed entirely of BUG-* entries (all of which may be filtered),
        # the "no actionable in queue" error is suppressed.
        rq_has_non_bug = any(
            isinstance(e, str) and not e.startswith("BUG-")
            for e in rq
        )
        try:
            project_root = find_project_root()
            repo_root = _REPO_ROOT or project_root
            work_item = _select_next_work_item(data, project_root, repo_root)
        except Exception as exc:
            logger.debug(f"Parent dispatch failed: {exc}")
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
                # Register bug in active_routes so /prog reflects it.
                try:
                    ar_list = data.get("active_routes")
                    if not isinstance(ar_list, list):
                        ar_list = []
                    ar_list = [
                        r for r in ar_list
                        if not (isinstance(r, dict) and r.get("project_code") == bug_id)
                    ]
                    ar_list.append({
                        "project_code": bug_id,
                        "feature_ref": bug_id,
                        "feature_name": bug_name,
                        "assigned_at": _iso_now(),
                        "status": "active",
                    })
                    data["active_routes"] = ar_list
                    _update_runtime_context(data, source="next_dispatch")
                    save_progress_json(data)
                    md_content = generate_progress_md(data)
                    save_progress_md(md_content)
                except Exception as exc:
                    logger.debug(f"Bug dispatch bookkeeping failed: {exc}")
                return True

            if item_type == "task":
                task_id = work_item["id"]
                task_name = work_item["name"]
                # Look up full task record to check parent_feature_id.
                tasks = data.get("tasks") or []
                task_record = next(
                    (t for t in tasks if isinstance(t, dict) and t.get("id") == task_id),
                    None,
                )
                parent_fid = task_record.get("parent_feature_id") if task_record else None
                is_standalone = parent_fid is None

                original_branch = None
                if is_standalone:
                    # Create short-lived branch before activating.
                    branch_name = f"task/{task_id}"
                    git_dir = project_root / ".git"
                    if git_dir.exists():
                        rc_orig, orig_out, _ = _run_git(
                            ["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(project_root)
                        )
                        if rc_orig == 0:
                            original_branch = orig_out.strip()
                        # Branch from the default branch, not current HEAD,
                        # to avoid carrying unrelated changes into the squash merge.
                        task_base = _detect_default_branch(project_root) or "main"
                        rc_verify, _, _ = _run_git(
                            ["rev-parse", "--verify", "--quiet", task_base],
                            cwd=str(project_root),
                        )
                        if rc_verify == 0:
                            rc, _, err = _run_git(
                                ["checkout", "-b", branch_name, task_base],
                                cwd=str(project_root),
                            )
                        else:
                            rc, _, err = _run_git(
                                ["checkout", "-b", branch_name],
                                cwd=str(project_root),
                            )
                        if rc != 0:
                            print(f"Error: could not create branch {branch_name}: {err}")
                            return False

                # Persist current_task_id after branch (standalone) or immediately (feature-bound).
                try:
                    data["current_task_id"] = task_id
                    data["updated_at"] = _iso_now()
                    save_progress_json(data)
                except Exception as exc:
                    # Roll back branch creation for standalone tasks.
                    if is_standalone and original_branch:
                        _run_git(["checkout", original_branch], cwd=str(project_root))
                        _run_git(["branch", "-D", branch_name], cwd=str(project_root))
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
                    if code == ROOT_ROUTE_CODE:
                        print(f"[NEXT] Root-level feature (routing_queue position {pos}):")
                    else:
                        print(f"[NEXT] Dispatching to [{code}] (routing_queue position {pos}):")
                    print(f"F{fid}: {fname}")
                    print(f"Run: {action}")
                # Register dispatch in active_routes + refresh linked_snapshot
                # so /prog reflects that this child is now active.
                if code and code != ROOT_ROUTE_CODE:
                    try:
                        ar_list = data.get("active_routes")
                        if not isinstance(ar_list, list):
                            ar_list = []
                        ar_list = [
                            r for r in ar_list
                            if not (isinstance(r, dict) and r.get("project_code") == code)
                        ]
                        ar_list.append({
                            "project_code": code,
                            "feature_ref": f"F{fid}",
                            "feature_name": fname,
                            "assigned_at": _iso_now(),
                            "status": "active",
                        })
                        data["active_routes"] = ar_list
                        statuses = collect_linked_project_statuses(
                            data, project_root=project_root, repo_root=repo_root,
                            active_routes=ar_list,
                        )
                        linked_snapshot = data.get("linked_snapshot")
                        if not isinstance(linked_snapshot, dict):
                            linked_snapshot = {}
                        linked_snapshot["schema_version"] = LINKED_SNAPSHOT_SCHEMA_VERSION
                        linked_snapshot["updated_at"] = _iso_now()
                        linked_snapshot["projects"] = statuses
                        data["linked_snapshot"] = linked_snapshot
                        _update_runtime_context(data, source="next_dispatch")
                        save_progress_json(data)
                        md_content = generate_progress_md(data)
                        save_progress_md(md_content)
                    except Exception as exc:
                        logger.debug(f"Child dispatch bookkeeping failed: {exc}")
                return True

            # item_type == "feature": fall through to the legacy feature
            # rendering path below so planning preflight still runs.

        # No work item from unified selector. If routing_queue contained
        # non-bug entries that could not be dispatched, surface the legacy
        # "no actionable in queue" error (returncode 1).
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

        # If routing_queue contained only BUG-* entries that were all
        # filtered (fixed / false_positive / active_route conflict) and
        # nothing else is actionable, treat this as a successful no-op
        # (exit 0) rather than an error: the queue was reviewed and the
        # user has nothing to do.
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
            (t for t in tasks if isinstance(t, dict) and t.get("status") == "pending"),
            None,
        )
        if pending_task is not None:
            task_id = pending_task.get("id")
            task_name = pending_task.get("description", task_id)
            parent_fid = pending_task.get("parent_feature_id")
            is_standalone = parent_fid is None

            original_branch = None
            if is_standalone:
                project_root = find_project_root()
                branch_name = f"task/{task_id}"
                # Only attempt branch creation inside a git repo.
                git_dir = project_root / ".git"
                if git_dir.exists():
                    rc_orig, orig_out, _ = _run_git(
                        ["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(project_root)
                    )
                    if rc_orig == 0:
                        original_branch = orig_out.strip()
                    # Branch from the default branch, not current HEAD,
                    # to avoid carrying unrelated changes into the squash merge.
                    task_base = _detect_default_branch(project_root) or "main"
                    rc_verify, _, _ = _run_git(
                        ["rev-parse", "--verify", "--quiet", task_base],
                        cwd=str(project_root),
                    )
                    if rc_verify == 0:
                        rc, _, err = _run_git(
                            ["checkout", "-b", branch_name, task_base],
                            cwd=str(project_root),
                        )
                    else:
                        rc, _, err = _run_git(
                            ["checkout", "-b", branch_name],
                            cwd=str(project_root),
                        )
                    if rc != 0:
                        print(f"Error: could not create branch {branch_name}: {err}")
                        return False

            # Persist current_task_id.
            try:
                data["current_task_id"] = task_id
                data["updated_at"] = _iso_now()
                save_progress_json(data)
            except Exception as exc:
                # Roll back branch creation for standalone tasks.
                if is_standalone and original_branch:
                    _run_git(["checkout", original_branch], cwd=str(project_root))
                    _run_git(["branch", "-D", branch_name], cwd=str(project_root))
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

    feature = get_next_feature()
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

    planning_report = _evaluate_planning_readiness(data, feature_id=feature.get("id"))
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

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(
        f"AI metrics updated for feature {feature_id}: "
        f"{ai_metrics['complexity_bucket']}, model={selected_model}"
    )
    return True


def complete_feature_ai_metrics(feature_id: int) -> bool:
    """Mark AI metrics completion timestamp and duration for a feature."""
    data = load_progress_json()
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

    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"AI metrics finalized for feature {feature_id}: duration={duration_seconds}s")
    return True


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
    """
    Save archive record to progress.json for traceability.

    Args:
        feature_id: The ID of the completed feature
        archive_result: The result dict from archive_feature_docs()
    """
    try:
        data = load_progress_json()
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

        save_progress_json(data)
        logger.info(f"Archive record saved for feature {feature_id}")

    except Exception as e:
        logger.error(f"Failed to save archive record: {e}")


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


def _clear_feature_finish_pending(feature: Dict[str, Any]) -> None:
    """Clear transient finish-pending metadata on a feature object."""
    feature.pop("finish_pending_reason", None)
    feature.pop("last_done_attempt_at", None)


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
            normalized = normalized[len(prefix) :].strip()
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


def _run_acceptance_tests(
    feature: Dict[str, Any],
    run_all: bool = False,
) -> Tuple[bool, List[AcceptanceTestResult]]:
    """Execute command-like acceptance steps from the target feature."""
    steps = feature.get("test_steps", [])
    if not isinstance(steps, list):
        steps = []

    project_root = find_project_root().resolve()
    repo_root: Optional[Path]
    if _REPO_ROOT:
        repo_root = Path(_REPO_ROOT).resolve()
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
) -> Optional[Path]:
    """Persist acceptance execution report for `/prog done` attempts."""
    try:
        state_dir = get_state_dir(find_project_root())
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
) -> Tuple[bool, str, int, Optional[Dict[str, Any]]]:
    """Validate deterministic gate checks before `/prog done` execution."""
    current_id = data.get("current_feature_id")
    if current_id is None:
        tracker_role = str(data.get("tracker_role") or DEFAULT_TRACKER_ROLE)
        project_code = data.get("project_code")
        scope_hint = find_project_root()
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
    data: Dict[str, Any], feature_id: int
) -> Tuple[bool, str, int]:
    """Block completion when reconcile reports state drift that needs repair."""
    reconcile_report = analyze_reconcile_state(data)
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
    data: Dict[str, Any], feature_id: int
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

    validation = validate_plan_document(plan_path)
    if not validation.get("valid"):
        errors = validation.get("errors", [])
        if not errors:
            return False, "plan document validation failed", 11
        return False, "; ".join(str(item) for item in errors), 11

    return True, "", 0


def _finalize_completion_state_in_memory(
    data: Dict[str, Any], feature_id: int, commit_hash: Optional[str] = None
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
    _update_runtime_context(data, source="finalize")

    return data, True


def _record_feature_completed_event(
    feature_id: int, feature_name: str, commit_hash: str = ""
) -> None:
    """Append feature_completed audit event for a real state transition only."""
    record_feature_state_event(
        event_type="feature_completed",
        feature_id=feature_id,
        feature_name=feature_name,
        extra_details={"commit_hash": commit_hash} if commit_hash else None,
    )


def _append_capability_memory(feature: Dict[str, Any], commit_hash: str) -> None:
    """Best-effort project memory append using project_memory module API."""
    try:
        import project_memory
        project_root = find_project_root()
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

    if _is_worktree_dirty(worktree_path if workspace_mode == "worktree" else None):
        print("[CLEANUP] WARN: dirty worktree, skipping cleanup")
        return

    # Cache upstream info BEFORE deleting the local branch —
    # tracking metadata disappears once the branch is removed.
    remote, remote_branch = _resolve_upstream(branch)

    if workspace_mode == "worktree":
        _remove_worktree(worktree_path)
        _delete_local_branch(branch)
        _delete_remote_branch(remote, remote_branch)

    elif workspace_mode == "in_place":
        _delete_local_branch(branch)
        _delete_remote_branch(remote, remote_branch)


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


def _run_done_preflight(data: Dict[str, Any]) -> Tuple[bool, list]:
    """Batch-validate all completion gates and return (all_passed, results)."""
    results: list = []

    # --- Gate 1: Preconditions ---
    valid, reason, code, feature = _validate_done_preconditions(data)
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
    valid, reason, code = _validate_completion_reconcile(data, feature_id)
    results.append({"gate": 2, "name": "Reconcile State", "passed": valid,
                    "reason": reason, "exit_code": code})

    # --- Gate 3: Plan Document ---
    valid, reason, code = _validate_completion_plan_document(data, feature_id)
    results.append({"gate": 3, "name": "Plan Document", "passed": valid,
                    "reason": reason, "exit_code": code})

    # --- Gate 4: Sprint Ledger ---
    if not SPRINT_LEDGER_AVAILABLE:
        results.append({"gate": 4, "name": "Sprint Ledger", "passed": False,
                        "reason": "sprint_ledger module unavailable", "exit_code": 9})
    else:
        try:
            require_sprint_contract(feature)
            results.append({"gate": 4, "name": "Sprint Ledger", "passed": True,
                            "reason": "", "exit_code": 0})
        except SprintLedgerError as exc:
            results.append({"gate": 4, "name": "Sprint Ledger", "passed": False,
                            "reason": str(exc), "exit_code": 9})

    # --- Gate 5: Acceptance Tests ---
    all_passed, test_results = _run_acceptance_tests(feature, run_all=True)
    if not all_passed:
        passed_n = sum(1 for r in test_results if r.success)
        reason = f"{passed_n}/{len(test_results)} passed"
    else:
        reason = "all passed"
    results.append({"gate": 5, "name": "Acceptance Tests", "passed": all_passed,
                    "reason": reason, "exit_code": 3 if not all_passed else 0})

    # Reload after acceptance, matching cmd_done line 9088-9094
    refreshed = load_progress_json()
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
        print(f"  [{icon}] Gate {r['gate']}: {r['name']}")
        if r["reason"]:
            print(f"       {r['reason']}")

    print("=" * 60)
    if failed_n:
        print("[PREFLIGHT] RESULT: BLOCKED — fix FAILED gates above"
              " before running `prog done`")
    else:
        print("[PREFLIGHT] RESULT: READY — all gates passed."
              " Run `prog done` to complete.")


def cmd_done(commit_hash=None, run_all: bool = False, skip_archive: bool = False,
             no_cleanup: bool = False, check_only: bool = False) -> int:
    """Close current feature through deterministic acceptance gatekeeping."""
    data = load_progress_json()
    if not data:
        print("[DONE] No progress tracking found")
        return 4

    if check_only:
        all_passed, results = _run_done_preflight(data)
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

    valid, reason, code, feature = _validate_done_preconditions(data)
    if not valid:
        print(f"[DONE] BLOCKED: {reason}")
        return code

    assert feature is not None  # preconditions guarantee feature presence
    feature_id = int(feature.get("id"))
    feature_name = feature.get("name", f"Feature {feature_id}")

    valid, reason, code = _validate_completion_reconcile(data, feature_id)
    if not valid:
        print(f"[DONE] BLOCKED: {reason}", file=sys.stderr)
        return code

    valid, reason, code = _validate_completion_plan_document(data, feature_id)
    if not valid:
        print(f"[DONE] BLOCKED: plan document validation failed: {reason}", file=sys.stderr)
        return code

    if not SPRINT_LEDGER_AVAILABLE:
        print("[DONE] BLOCKED: sprint_ledger module unavailable.", file=sys.stderr)
        return 9

    try:
        require_sprint_contract(feature)
    except SprintLedgerError as exc:
        print(f"[DONE] BLOCKED: {exc}", file=sys.stderr)
        return 9

    print(f"[DONE] Running acceptance tests for Feature {feature_id}: {feature_name}")

    all_passed, results = _run_acceptance_tests(feature, run_all=run_all)
    report_path = _save_done_test_report(
        feature_id=feature_id,
        feature_name=feature_name,
        results=results,
        success=all_passed,
    )
    if report_path:
        try:
            artifact_path = str(report_path.relative_to(find_project_root()))
        except ValueError:
            artifact_path = str(report_path)
        try:
            passed_count = sum(1 for result in results if result.success)
            record_sprint_artifact(
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
        refreshed = load_progress_json()
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
                save_progress_json(refreshed)

        passed_count = sum(1 for result in results if result.success)
        total_count = len(results)
        print(f"[DONE] Acceptance failed ({passed_count}/{total_count} passed)")
        if report_path:
            try:
                relative_report = report_path.relative_to(find_project_root())
            except ValueError:
                relative_report = report_path
            print(f"[DONE] Report: {relative_report}")
        return 3

    print("[DONE] Acceptance passed")

    gate_feat = None
    refreshed_for_gate = load_progress_json()
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

    # F-11: review gate — all required review lanes must be passed before archiving.
    if REVIEW_ROUTER_AVAILABLE:
        reviews_payload = gate_feat.setdefault("quality_gates", {}).setdefault(
            "reviews",
            {"required": [], "passed": [], "pending": []},
        )
        if not reviews_payload.get("required"):
            _initialize_reviews(gate_feat)
            save_progress_json(refreshed_for_gate)
            save_progress_md(generate_progress_md(refreshed_for_gate))
        pending_lanes = _get_pending_lanes(gate_feat)
        if pending_lanes:
            print(
                f"[DONE] BLOCKED: pending reviews: {pending_lanes}. "
                "Run: prog review-pass --feature-id <id> --lane <lane>",
                file=sys.stderr,
            )
            return 7

    # PR-5: ship_check gate — must pass before archiving.
    ship_payload = gate_feat.get("quality_gates", {}).get("ship_check", {})
    ship_status = ship_payload.get("status")
    if ship_status != "pass":
        print(
            f"[DONE] BLOCKED: ship_check not passed (status={ship_status!r}). "
            f"Run `prog ship-check --feature-id {feature_id}` first.",
            file=sys.stderr,
        )
        return 8

    # Snapshot git context before finalize clears workflow_state.
    git_ctx = collect_git_context()
    cleanup_ctx = {
        "branch": git_ctx.get("branch", ""),
        "workspace_mode": git_ctx.get("workspace_mode", "unknown"),
        "worktree_path": git_ctx.get("worktree_path"),
    }

    resolved_commit = commit_hash or _get_head_commit()
    data_for_finalize = load_progress_json()
    if not data_for_finalize:
        print("[DONE] Failed to load progress state before finalization", file=sys.stderr)
        return 4

    data_final, did_transition = _finalize_completion_state_in_memory(
        data_for_finalize, feature_id, commit_hash=resolved_commit
    )
    if not did_transition:
        print(f"[DONE] Feature {feature_id} already completed; no-op.")
        return 0

    save_progress_json(data_final)
    save_progress_md(generate_progress_md(data_final))

    _record_feature_completed_event(feature_id, feature_name, resolved_commit or "")

    if not skip_archive:
        try:
            archive_result = archive_feature_docs(feature_id, feature_name)
            if archive_result.get("archived_files"):
                print(f"Archived {len(archive_result['archived_files'])} file(s)")
            if archive_result.get("errors"):
                print("Warning: Some files could not be archived (feature still marked complete)")
            data_post_archive = load_progress_json()
            if data_post_archive:
                save_archive_record(feature_id, archive_result)
        except Exception as exc:
            logger.error(f"Archive failed but feature completed: {exc}")
            print("Warning: Document archiving failed but feature is marked complete")

    data_for_memory = load_progress_json()
    if data_for_memory:
        feat_for_memory = next(
            (f for f in data_for_memory.get("features", []) if f.get("id") == feature_id),
            None,
        )
        if feat_for_memory is not None:
            _append_capability_memory(feat_for_memory, resolved_commit or "")

    data_final_check = load_progress_json()
    if data_final_check and _is_project_fully_completed(data_final_check):
        try:
            archive_current_progress(reason="completed")
        except Exception as exc:
            logger.error(f"Completed-run archive failed: {exc}")
            print("Warning: Completed-run archive failed, but active state will still be cleared.")
        data_post_reset = load_progress_json()
        if data_post_reset:
            _reset_active_progress(data_post_reset)

    _auto_state_commit(f"F{feature_id}", "done")

    print(f"[DONE] Feature {feature_id} completed")
    if resolved_commit:
        print(f"[DONE] Commit: {resolved_commit}")
    if report_path:
        try:
            relative_report = report_path.relative_to(find_project_root())
        except ValueError:
            relative_report = report_path
        print(f"[DONE] Report: {relative_report}")

    refreshed = load_progress_json()
    completion_output = None
    if refreshed:
        project_root_str = str(find_project_root().resolve())
        completion_output = _build_done_handoff_block(refreshed, project_root_str)
        if completion_output is None:
            completion_output = _build_project_completion_summary(refreshed, project_root_str)

    _notify_parent_sync("clear")
    try:
        _run_post_done_cleanup(cleanup_ctx, skip=no_cleanup)
    except Exception as exc:
        print(f"[CLEANUP] WARN: unexpected cleanup error (feature still completed): {exc}")

    if completion_output:
        print(completion_output)

    return 0


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
                save_progress_md(generate_progress_md(data2))

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
    save_progress_md(generate_progress_md(data))

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
    save_progress_md(generate_progress_md(data))

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
    save_progress_md(generate_progress_md(data))

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
    """Mark a feature as completed."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)

    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    valid, reason, _ = _validate_completion_reconcile(data, feature_id)
    if not valid:
        print(f"Cannot complete feature: {reason}")
        return False

    resolved_commit = commit_hash or ""
    data, did_transition = _finalize_completion_state_in_memory(
        data,
        feature_id,
        commit_hash=resolved_commit if resolved_commit else None,
    )
    if not did_transition:
        return True

    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

    _record_feature_completed_event(
        feature_id,
        feature.get("name", f"Feature {feature_id}"),
        resolved_commit,
    )

    print(f"Completed feature: {feature.get('name', 'Unknown')}")
    if commit_hash:
        print(f"Recorded commit: {commit_hash}")

    # Archive documents (non-blocking)
    if not skip_archive:
        try:
            feature_name = feature.get("name", f"Feature {feature_id}")
            print(f"\nArchiving documents for {feature_name}...")
            archive_result = archive_feature_docs(feature_id, feature_name)

            if archive_result["archived_files"]:
                print(f"Archived {len(archive_result['archived_files'])} file(s)")

            # Save archive record regardless of individual file errors.
            refreshed = load_progress_json()
            if refreshed:
                save_archive_record(feature_id, archive_result)

            if archive_result["errors"]:
                print(f"Warning: Some files could not be archived (feature still marked complete)")

        except Exception as e:
            # Archive failures should not prevent feature completion
            logger.error(f"Archive failed but feature completed: {e}")
            print(f"Warning: Document archiving failed but feature is marked complete")

        refreshed = load_progress_json()
        if refreshed and _is_project_fully_completed(refreshed):
            try:
                completed_archive = archive_current_progress(reason="completed")
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

    refreshed = load_progress_json()
    if refreshed:
        feat_for_memory = next((f for f in refreshed.get("features", []) if f.get("id") == feature_id), None)
        if feat_for_memory:
            _append_capability_memory(feat_for_memory, resolved_commit)

    # ── Outside if not skip_archive — always runs ──
    refreshed = load_progress_json()
    if refreshed and _is_project_fully_completed(refreshed):
        _reset_active_progress(refreshed)

    return True


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

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print("Progress tracking updated.")
    return True


def _next_update_id(updates: List[Dict[str, Any]]) -> str:
    """Generate the next UPD-XXX identifier."""
    max_num = 0
    for item in updates:
        update_id = str(item.get("id", ""))
        match = re.match(r"^UPD-(\d+)$", update_id)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"UPD-{max_num + 1:03d}"


def _format_feature_owners(feature: Dict[str, Any]) -> Optional[str]:
    import doc_generator
    return doc_generator._format_feature_owners(feature)
_format_feature_owners.is_wrapper = True


def _normalize_ref_tokens(refs: Optional[List[str]]) -> List[str]:
    """Normalize and deduplicate ref tokens while preserving encounter order."""
    normalized: List[str] = []
    seen: Set[str] = set()
    for raw in refs or []:
        if not isinstance(raw, str):
            continue
        token = raw.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _collect_auto_update_refs(feature: Dict[str, Any]) -> List[str]:
    """Collect deterministic auto refs from a feature contract payload."""
    refs: List[str] = []
    for req_id in feature.get("requirement_ids", []):
        if isinstance(req_id, str) and req_id.strip():
            refs.append(f"req:{req_id.strip()}")

    change_spec = feature.get("change_spec")
    if isinstance(change_spec, dict):
        change_id = change_spec.get("change_id")
        if isinstance(change_id, str) and change_id.strip():
            refs.append(f"change:{change_id.strip()}")

    normalized = _normalize_ref_tokens(refs)
    normalized.sort()
    return normalized


def _compact_update_refs(refs: List[str]) -> Tuple[List[str], List[str]]:
    """Split refs into inline and overflow buckets without dropping data."""
    if len(refs) <= UPDATE_REFS_INLINE_LIMIT:
        return refs, []
    return refs[:UPDATE_REFS_INLINE_LIMIT], refs[UPDATE_REFS_INLINE_LIMIT:]


def _collect_update_refs(update_item: Dict[str, Any]) -> List[str]:
    """Collect refs and overflow refs from one update item."""
    refs: List[str] = []
    inline_refs = update_item.get("refs")
    if isinstance(inline_refs, list):
        refs.extend([ref for ref in inline_refs if isinstance(ref, str)])
    overflow_refs = update_item.get("refs_overflow")
    if isinstance(overflow_refs, list):
        refs.extend([ref for ref in overflow_refs if isinstance(ref, str)])
    return _normalize_ref_tokens(refs)


def _planning_gate_enabled(data: Dict[str, Any]) -> bool:
    """Return whether preflight planning gate should be evaluated for this project."""
    updates = data.get("updates", [])
    if isinstance(updates, list):
        for item in updates:
            if not isinstance(item, dict):
                continue
            if str(item.get("source") or "").strip().lower() == PLANNING_SOURCE:
                return True

    project_root = find_project_root()
    for rel_path in PLANNING_ARTIFACT_DIRS:
        if (project_root / rel_path).exists():
            return True
    return False


def _evaluate_planning_readiness(
    data: Dict[str, Any],
    feature_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Evaluate preflight planning readiness from updates + refs without schema changes.

    Contract:
      {
        "ok": true,
        "status": "ready|warn|missing",
        "required": ["office_hours", "ceo_review"],
        "missing": [...],
        "optional_missing": [...],
        "refs": ["doc:..."],
        "message": "..."
      }
    """
    required = list(PLANNING_REQUIRED_REFS)
    optional = list(PLANNING_OPTIONAL_REFS)

    planning_refs: List[str] = []
    updates = data.get("updates", [])
    if isinstance(updates, list):
        for item in updates:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip().lower()
            if source != PLANNING_SOURCE:
                continue
            item_feature_id = item.get("feature_id")
            if feature_id is not None and item_feature_id not in (None, feature_id):
                continue
            planning_refs.extend(_collect_update_refs(item))

    normalized_planning_refs = set(_normalize_ref_tokens(planning_refs))
    doc_refs = sorted([ref for ref in normalized_planning_refs if ref.startswith("doc:")])

    if not _planning_gate_enabled(data):
        return {
            "ok": True,
            "status": "ready",
            "required": required,
            "missing": [],
            "optional_missing": [],
            "refs": doc_refs,
            "message": PLANNING_MESSAGE_KEYS["gate_disabled"],
            "schema_version": PLANNING_SCHEMA_VERSION,
        }

    missing = [name for name in required if f"planning:{name}" not in normalized_planning_refs]
    optional_missing = [
        name for name in optional if f"planning:{name}" not in normalized_planning_refs
    ]

    if missing:
        status = "missing"
        message = PLANNING_MESSAGE_KEYS["missing"]
    elif optional_missing:
        status = "warn"
        message = PLANNING_MESSAGE_KEYS["optional_missing"]
    else:
        status = "ready"
        message = PLANNING_MESSAGE_KEYS["ready"]

    return {
        "ok": True,
        "status": status,
        "required": required,
        "missing": missing,
        "optional_missing": optional_missing,
        "refs": doc_refs,
        "message": message,
        "schema_version": PLANNING_SCHEMA_VERSION,
    }


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
    """Append a structured update entry into progress.json."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    normalized_category = (category or "").strip().lower()
    if normalized_category not in UPDATE_CATEGORIES:
        print(
            "Error: Invalid category "
            f"'{category}'. Allowed: {', '.join(UPDATE_CATEGORIES)}"
        )
        return False

    normalized_summary = (summary or "").strip()
    if not normalized_summary:
        print("Error: summary cannot be empty")
        return False

    normalized_role = None
    if role:
        normalized_role = role.strip().lower()
        if normalized_role not in OWNER_ROLES:
            print(f"Error: Invalid role '{role}'. Allowed: {', '.join(OWNER_ROLES)}")
            return False

    normalized_owner = owner.strip() if isinstance(owner, str) else owner
    if normalized_owner and not normalized_role:
        print("Error: owner requires role")
        return False

    normalized_source = (source or "").strip().lower()
    if normalized_source not in UPDATE_SOURCES:
        print(
            "Error: Invalid source "
            f"'{source}'. Allowed: {', '.join(UPDATE_SOURCES)}"
        )
        return False

    target_feature: Optional[Dict[str, Any]] = None
    if feature_id is not None:
        features = data.get("features", [])
        target_feature = next((f for f in features if f.get("id") == feature_id), None)
        if target_feature is None:
            print(f"Error: Feature ID {feature_id} not found")
            return False

    # Manual refs are authoritative when explicitly provided.
    normalized_manual_refs = _normalize_ref_tokens(refs)
    selected_refs = normalized_manual_refs
    if feature_id is not None and not normalized_manual_refs and target_feature is not None:
        selected_refs = _collect_auto_update_refs(target_feature)

    refs_inline, refs_overflow = _compact_update_refs(selected_refs)

    updates = data.setdefault("updates", [])
    created_at = _iso_now()
    update_item = {
        "id": _next_update_id(updates),
        "created_at": created_at,
        "category": normalized_category,
        "summary": normalized_summary,
        "details": details.strip() if isinstance(details, str) and details.strip() else None,
        "feature_id": feature_id,
        "bug_id": bug_id.strip() if isinstance(bug_id, str) and bug_id.strip() else None,
        "role": normalized_role,
        "owner": normalized_owner if normalized_owner else None,
        "source": normalized_source,
        "next_action": (
            next_action.strip()
            if isinstance(next_action, str) and next_action.strip()
            else None
        ),
        "refs": refs_inline,
    }
    if refs_overflow:
        update_item["refs_overflow"] = refs_overflow
        update_item["refs_overflow_count"] = len(refs_overflow)
    updates.append(update_item)

    save_progress_json(data)
    save_progress_md(generate_progress_md(data))
    print(f"Added update {update_item['id']}: {update_item['category']} - {update_item['summary']}")
    return True


def list_updates(limit: int = 0) -> bool:
    """List the latest structured updates. limit=0 means show all."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    updates = data.get("updates", [])
    if not updates:
        print("No updates recorded.")
        return True

    if limit < 0:
        print("Error: --limit must be 0 (all) or a positive integer")
        return False

    safe_limit = len(updates) if limit == 0 else min(len(updates), limit)
    print(f"Showing {safe_limit} of {len(updates)} update(s):")
    for item in updates[-safe_limit:]:
        line = f"- [{item.get('id', 'UPD-???')}] {item.get('category', 'status')}: {item.get('summary', '')}"
        source = str(item.get("source") or "").strip()
        if source:
            line += f" [source={source}]"
        if item.get("feature_id") is not None:
            line += f" (feature:{item['feature_id']})"
        if item.get("role") and item.get("owner"):
            line += f" [{item['role']}={item['owner']}]"
        overflow_count = item.get("refs_overflow_count", 0) or 0
        if overflow_count > 0:
            line += f" [+{overflow_count} refs overflow]"
        print(line)
    return True


def add_retro(
    feature_id: int,
    summary: str,
    root_cause: str,
    action_items: Optional[List[str]] = None,
) -> bool:
    """Add a retrospective entry for a feature."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])
    if not any(f.get("id") == feature_id for f in features):
        print(f"Error: Feature ID {feature_id} not found")
        return False

    normalized_summary = (summary or "").strip()
    if not normalized_summary:
        print("Error: summary cannot be empty")
        return False

    normalized_root_cause = (root_cause or "").strip()
    if not normalized_root_cause:
        print("Error: root_cause cannot be empty")
        return False

    retrospectives = data.setdefault("retrospectives", [])
    retro_id = f"RETRO-{feature_id}-{len(retrospectives) + 1:03d}"
    created_at = _iso_now()

    retro_item = {
        "id": retro_id,
        "created_at": created_at,
        "feature_id": feature_id,
        "summary": normalized_summary,
        "root_cause": normalized_root_cause,
        "action_items": [
            item.strip() if isinstance(item, str) else item
            for item in (action_items or [])
            if isinstance(item, str) and item.strip()
        ],
    }

    retrospectives.append(retro_item)
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))
    print(f"Added retrospective {retro_id}: {normalized_summary}")
    return True


def set_feature_owner(feature_id: int, role: str, owner: str) -> bool:
    """Set feature owner for a specific role."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    normalized_role = (role or "").strip().lower()
    if normalized_role not in OWNER_ROLES:
        print(f"Error: Invalid role '{role}'. Allowed: {', '.join(OWNER_ROLES)}")
        return False

    normalized_owner = (owner or "").strip()
    owner_value = None if normalized_owner.lower() in {"", "-", "none", "null"} else normalized_owner

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    _normalize_feature_owners(feature)
    feature["owners"][normalized_role] = owner_value

    save_progress_json(data)
    save_progress_md(generate_progress_md(data))
    assigned = owner_value if owner_value is not None else "None"
    print(f"Set owner: feature {feature_id} {normalized_role} -> {assigned}")
    return True


def add_feature(name, test_steps, workflow_profile=None):
    """Add a new feature to the tracking."""
    if workflow_profile is None:
        workflow_profile = WORKFLOW_PROFILE_DEFAULT
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])

    # Generate new ID
    max_id = max([f.get("id", 0) for f in features], default=0)
    new_id = max_id + 1

    new_feature = {
        "id": new_id,
        "name": name,
        "test_steps": test_steps,
        "workflow_profile": workflow_profile,
        "completed": False,
        "deferred": False,
        "defer_reason": None,
        "deferred_at": None,
        "defer_group": None,
        "owners": _default_owners(),
    }
    _normalize_feature_contract(new_feature)

    try:
        imported_contract = import_contract_for_feature(new_id)
    except ContractImportError as exc:
        print(f"Error: Failed to import contract for feature {new_id}: {exc}")
        return False
    if imported_contract:
        _apply_imported_feature_contract(new_feature, imported_contract)

    features.append(new_feature)
    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Added feature: {name} (ID: {new_id})")
    _notify_parent_sync()
    return True


def update_feature(feature_id, name, test_steps=None):
    """Update an existing feature's name and optional test steps."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)

    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    normalized_name = name.strip()
    if not normalized_name:
        print("Feature name cannot be empty")
        return False

    feature["name"] = normalized_name
    if test_steps:
        feature["test_steps"] = test_steps
    _normalize_feature_contract(feature)

    try:
        imported_contract = import_contract_for_feature(feature_id)
    except ContractImportError as exc:
        print(f"Error: Failed to import contract for feature {feature_id}: {exc}")
        return False
    if imported_contract:
        _apply_imported_feature_contract(feature, imported_contract)

    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Updated feature {feature_id}: {normalized_name}")
    if test_steps:
        print(f"Updated test steps ({len(test_steps)} step(s))")
    return True


def defer_features(
    feature_id: Optional[int],
    all_pending: bool,
    reason: str,
    defer_group: Optional[str] = None,
) -> bool:
    """Defer one feature or all pending features without losing tracker state."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    normalized_reason = _normalize_optional_string(reason)
    if not normalized_reason:
        print("Error: --reason is required and cannot be empty.")
        return False

    normalized_group = _normalize_optional_string(defer_group)
    features = data.get("features", [])
    targets: List[Dict[str, Any]] = []

    if all_pending:
        targets = [
            f
            for f in features
            if isinstance(f, dict) and not f.get("completed", False)
        ]
        if not targets:
            print("No pending features to defer.")
            return False
    else:
        if feature_id is None:
            print("Error: --feature-id is required when --all-pending is not set.")
            return False
        feature = next((f for f in features if f.get("id") == feature_id), None)
        if not feature:
            print(f"Feature ID {feature_id} not found")
            return False
        if feature.get("completed", False):
            print(f"Feature ID {feature_id} is already completed and cannot be deferred.")
            return False
        targets = [feature]

    now = _iso_now()
    target_ids = {f.get("id") for f in targets}
    for feature in targets:
        feature["deferred"] = True
        feature["defer_reason"] = normalized_reason
        feature["deferred_at"] = now
        feature["defer_group"] = normalized_group

    cleared_active = False
    if data.get("current_feature_id") in target_ids:
        data["current_feature_id"] = None
        if "workflow_state" in data:
            del data["workflow_state"]
        cleared_active = True

    _update_runtime_context(data, source="defer")
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

    print(f"Deferred {len(targets)} feature(s).")
    print(f"Reason: {normalized_reason}")
    if normalized_group:
        print(f"Group: {normalized_group}")
    if cleared_active:
        print("Cleared active feature and workflow_state because the active feature was deferred.")
    return True


def resume_deferred_features(defer_group: Optional[str], resume_all: bool) -> bool:
    """Resume deferred features by group or resume all deferred features."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    normalized_group = _normalize_optional_string(defer_group)
    features = data.get("features", [])
    targets: List[Dict[str, Any]] = []

    for feature in features:
        if not isinstance(feature, dict):
            continue
        if feature.get("completed", False):
            continue
        if not _is_feature_deferred(feature):
            continue
        if not resume_all and feature.get("defer_group") != normalized_group:
            continue
        targets.append(feature)

    if not targets:
        if resume_all:
            print("No deferred pending features to resume.")
        else:
            print(f"No deferred pending features found for group: {normalized_group}")
        return False

    for feature in targets:
        _clear_feature_defer_state(feature)

    _update_runtime_context(data, source="resume")
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

    print(f"Resumed {len(targets)} deferred feature(s).")
    if not resume_all:
        print(f"Group: {normalized_group}")
    return True


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


def _push_bug_to_routing_queue(data: Dict[str, Any], bug_id: str, priority: str) -> None:
    """Insert bug_id into routing_queue at the position matching its priority tier.

    Priority tier mapping (bug.priority field -> tier weight):
        high   -> P0 (weight 0, inserted before P1/P2 bugs and all other entries)
        medium -> P1 (weight 1, inserted before P2 bugs, after P0)
        low    -> P2 (weight 2, appended after all P0/P1 bugs)

    routing_queue entries can be:
        - Project codes (e.g. "PT", "ROOT") -> weight 1.5 (between P1 and P2)
        - Bug IDs ("BUG-*") -> weight depends on their priority in bugs[]
        - Task IDs ("TASK-*") -> weight 1.5 (same as project codes for ordering purposes)

    Idempotent: if bug_id is already in routing_queue, this is a no-op.

    Args:
        data: The loaded progress.json dict (will be mutated in-place).
        bug_id: The bug ID to insert (e.g. "BUG-001").
        priority: The bug's priority string ("high", "medium", "low").
    """
    queue = data.setdefault("routing_queue", [])
    if not isinstance(queue, list):
        queue = []
        data["routing_queue"] = queue

    # Idempotent: bail out if already present
    if bug_id in queue:
        return

    # Map bug priority to tier weight
    priority_to_weight = {"high": 0.0, "medium": 1.0, "low": 2.0}
    new_weight = priority_to_weight.get(priority, 1.0)

    # Build lookup from existing bug IDs to their priorities (for queue items
    # that are BUG-* entries — we need to know their tier weight).
    bug_priority_map: Dict[str, str] = {}
    for bug in data.get("bugs") or []:
        if isinstance(bug, dict):
            bid = bug.get("id")
            bprio = bug.get("priority")
            if isinstance(bid, str) and isinstance(bprio, str):
                bug_priority_map[bid] = bprio

    def _entry_weight(entry: str) -> float:
        # BUG-* entries draw their weight from bugs[]; if the bug is missing
        # from bugs[] for any reason, treat it as medium (1.0) as a safe default.
        if isinstance(entry, str) and entry.startswith("BUG-"):
            prio = bug_priority_map.get(entry, "medium")
            return priority_to_weight.get(prio, 1.0)
        # Project codes / TASK-* / ROOT / anything else: weight 1.5
        return 1.5

    # Find first existing entry whose weight is >= new_weight; insert before it.
    insert_idx = len(queue)
    for idx, entry in enumerate(queue):
        if _entry_weight(entry) >= new_weight:
            insert_idx = idx
            break

    queue.insert(insert_idx, bug_id)


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
    """Write a standalone task item to tasks[].

    Returns the new task ID on success, None on failure.
    Priority values: P0, P1, P2.
    workflow_profile must be one of WORKFLOW_PROFILE_VALUES.

    Note: Callers that invoke this outside the CLI MUST hold a progress_transaction()
    lock to avoid concurrent write races. The CLI wires mutating commands through
    MUTATING_COMMANDS + progress_transaction() automatically.
    """
    if not description or not description.strip():
        raise ValueError("Description cannot be empty")

    description = description.strip()

    if len(description) > 2000:
        raise ValueError(f"Description too long ({len(description)} chars, max 2000)")

    valid_priorities = ["P0", "P1", "P2"]
    if priority not in valid_priorities:
        raise ValueError(f"Invalid priority '{priority}'. Must be one of: {valid_priorities}")

    if workflow_profile not in WORKFLOW_PROFILE_VALUES:
        raise ValueError(
            f"Invalid workflow_profile '{workflow_profile}'. "
            f"Allowed: {sorted(WORKFLOW_PROFILE_VALUES)}"
        )

    # Sanitize control characters (preserve newline/tab)
    description = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', description)
    if details:
        details = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', details)

    # Defensive copy of refs to avoid aliasing mutation
    refs = list(refs) if refs else []

    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return None

    # Validate parent_feature_id if provided (single load, no TOCTOU window).
    if parent_feature_id is not None:
        features = data.get("features", [])
        if not any(f.get("id") == parent_feature_id for f in features):
            print(f"Error: feature {parent_feature_id} not found")
            return None

    tasks = data.setdefault("tasks", [])

    # Generate task ID
    existing_ids = [t.get("id", "") for t in tasks if isinstance(t, dict)]
    n = len(tasks) + 1
    while f"TASK-{n:03d}" in existing_ids:
        n += 1
    task_id = f"TASK-{n:03d}"

    new_task = {
        "id": task_id,
        "type": "task",
        "description": description,
        "workflow_profile": workflow_profile,
        "status": "pending",
        "priority": priority,
        "details": details.strip() if details else "",
        "refs": refs,
        "next_action": next_action.strip() if next_action else "",
        "created_at": _iso_now(),
        "parent_feature_id": parent_feature_id,
    }

    tasks.append(new_task)
    data["tasks"] = tasks

    save_progress_json(data)
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Task recorded: {task_id}")
    print(f"Description: {description}")
    print(f"workflow_profile: {workflow_profile}")
    return task_id


# Priority mapping for smart_intake: P0/P1/P2 → high/medium/low (add_bug priority)
_SMART_INTAKE_PRIORITY_MAP = {"P0": "high", "P1": "medium", "P2": "low"}


def smart_intake(
    candidate_json: str,
    commit: Optional[str] = None,
    workflow_profile: str = WORKFLOW_PROFILE_DEFAULT,
) -> bool:
    """Deterministic work-item intake executor.

    Preview mode (commit=None):
        Parse candidate_json, display type/confidence/profile fields.
        If confidence < 0.6: print one clarification prompt, no JSON write.
        Always returns True (success) on valid candidate, never mutates progress.json.

    Commit mode (commit="bug"|"feature"|"task"|"update"):
        Must be called inside progress_transaction() by the caller (CLI dispatch).
        Routes to the appropriate write function based on commit type.
        Returns True on success, False on failure.

    Args:
        candidate_json: JSON string with type, confidence, and profile fields.
        commit: Commit target work-item type, or None for preview.
        workflow_profile: Used only when commit="task". Ignored for all other
            commit types and in preview mode.
    """
    # Parse and validate candidate_json
    try:
        candidate = json.loads(candidate_json)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"Error: invalid candidate JSON: {e}")
        return False

    if not isinstance(candidate, dict):
        print("Error: candidate JSON must be an object")
        return False

    item_type = candidate.get("type", "")
    try:
        confidence = float(candidate.get("confidence", 0.0))
    except (TypeError, ValueError):
        print("Error: confidence must be a number")
        return False

    profile = candidate.get("profile", {})
    if not isinstance(profile, dict):
        print("Error: profile must be an object")
        return False

    description = (profile.get("description") or "").strip()

    if not description:
        print("Error: profile.description is required")
        return False

    if item_type not in WORK_ITEM_TAXONOMY:
        print(
            f"Error: invalid type '{item_type}'. "
            f"Must be one of: {sorted(WORK_ITEM_TAXONOMY)}"
        )
        return False

    # Preview branch: zero mutation
    if not commit:
        print("[候选工作项]")
        print(f"  type:        {item_type}")
        print(f"  confidence:  {confidence:.2f}")
        print("  profile:")
        print(f"    description: {description}")
        for key in ("priority", "details", "refs", "next_action"):
            val = profile.get(key)
            if val:
                print(f"    {key}: {val}")

        if confidence < 0.6:
            print()
            print(
                "needs_clarification: 请补充信息 — 这条记录更接近 bug、"
                "feature、task 还是 update？"
            )
            print("  → 确认后用 --commit <type> 重新提交")
            return True

        print()
        print(f"→ 使用 --commit {item_type} 写入，或指定其他类型")
        return True

    # Commit branch: caller must hold progress_transaction() lock
    if commit == "bug":
        priority_str = profile.get("priority", "P1")
        bug_priority = _SMART_INTAKE_PRIORITY_MAP.get(priority_str, "medium")
        try:
            success, bug_id = _add_bug_internal(
                description=description,
                priority=bug_priority,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return False
        if success and bug_id:
            data = load_progress_json()
            _push_bug_to_routing_queue(data, bug_id, bug_priority)
            save_progress_json(data)
            md_content = generate_progress_md(data)
            save_progress_md(md_content)
        return success

    if commit == "task":
        raw_priority = profile.get("priority", "P1")
        if raw_priority not in ("P0", "P1", "P2"):
            raw_priority = "P1"
        task_id = add_task_item(
            description=description,
            details=profile.get("details", "") or "",
            refs=profile.get("refs") or [],
            next_action=profile.get("next_action", "") or "",
            priority=raw_priority,
            workflow_profile=workflow_profile,
        )
        return task_id is not None

    if commit == "feature":
        result = add_feature(
            name=description,
            test_steps=[],
            workflow_profile=workflow_profile,
        )
        # add_feature returns bool; treat None as False defensively.
        return bool(result)

    if commit == "update":
        raw_category = profile.get("category", "status")
        category = raw_category if raw_category in UPDATE_CATEGORIES else "status"
        return add_update(
            category=category,
            summary=description,
            details=profile.get("details") or None,
            next_action=profile.get("next_action") or None,
            refs=profile.get("refs") or None,
        )

    print(f"Error: unknown commit type '{commit}'")
    return False


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
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Bug {bug_id} removed from tracking.")
    return True


def reset_tracking(force=False):
    """Reset active progress tracking files while preserving archive/history."""
    progress_dir = get_progress_dir()
    tracked_files = [
        progress_dir / PROGRESS_JSON,
        progress_dir / PROGRESS_MD,
        progress_dir / CHECKPOINTS_JSON,
    ]
    if not progress_dir.exists() or not any(path.exists() for path in tracked_files):
        print("No progress tracking found to reset.")
        return True

    if not force:
        confirm = input(
            f"Are you sure you want to reset active progress files at {progress_dir}? (y/N): "
        )
        if confirm.lower() != "y":
            print("Reset cancelled.")
            return False

    try:
        archived_entry = archive_current_progress(reason="reset")

        # Event sourcing: append tracker_reset global event to audit.log
        # Must be before files are deleted, so audit_log can still write
        record_feature_state_event(
            event_type="tracker_reset",
            feature_id=None,
            feature_name=None,
        )

        removed = []
        for path in tracked_files:
            if path.exists():
                path.unlink()
                removed.append(path.name)

        if not removed:
            print("No active progress files found to reset.")
            return True

        print(f"Progress tracking reset successfully. Removed: {', '.join(removed)}")
        if archived_entry:
            print(
                "Archived previous progress as "
                f"{archived_entry.get('archive_id')} "
                f"(reason={archived_entry.get('reason')})"
            )
        return True
    except Exception as e:
        print(f"Error resetting progress tracking: {e}")
        return False


def set_workflow_state(phase=None, plan_path=None, next_action=None):
    """Set workflow state for current feature."""
    data = load_progress_json()
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
    plan_validation = validate_plan_path(
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
    _update_execution_context(workflow_state, source="set_workflow_state")

    data["workflow_state"] = workflow_state
    _update_runtime_context(data, source="set_workflow_state")
    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Workflow state updated: phase={phase or workflow_state.get('phase')}")
    return True


def update_workflow_task(task_id, status):
    """Update task completion status in workflow_state."""
    data = load_progress_json()
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
    _update_execution_context(workflow_state, source="update_workflow_task")

    data["workflow_state"] = workflow_state
    _update_runtime_context(data, source="update_workflow_task")
    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    total = workflow_state.get("total_tasks", 0)
    print(f"Task {task_id}/{total} marked as {status}")
    return True


def clear_workflow_state():
    """Clear workflow state from progress tracking."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    if "workflow_state" in data:
        del data["workflow_state"]
        save_progress_json(data)

        # Update progress.md
        md_content = generate_progress_md(data)
        save_progress_md(md_content)

        print("Workflow state cleared")
        return True

    print("No workflow state to clear")
    return True


def health_check():
    """
    Perform health check and return JSON metrics.

    This command is used to monitor the health of the progress tracker
    and provide recommendations for timeout settings.

    Returns:
        int: 0 if healthy, 1 if degraded

    Output:
        JSON with status, response_time_ms, and recommended_timeout
    """
    import time
    start = time.time()

    # Load progress to check data integrity
    try:
        data = load_progress_json()
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


def validate_plan(plan_path: Optional[str] = None):
    """Validate workflow plan path and minimum plan document structure."""
    data = load_progress_json()
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

    plan_result = validate_plan_document(resolved_plan_path)
    if not plan_result["valid"]:
        print("Plan validation failed:")
        for err in plan_result["errors"]:
            print(f"- {err}")
        return False

    print(f"Plan validation passed: {resolved_plan_path}")
    for warning in plan_result.get("warnings", []):
        print(f"Plan validation warning: {warning}")
    return True


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
    import doc_generator
    return doc_generator.generate_progress_md(data)
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
            return reset_tracking(force=args.force)
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
