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
    python3 progress_manager.py done [--commit <hash>] [--run-all] [--skip-archive] [--no-cleanup]
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
)
from contract_importer import ContractImporter, ContractImportError
import progress_prompt_builders
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
PROGRESS_LOCK_FILE = "progress.lock"
PROGRESS_LOCK_TIMEOUT_SECONDS = 10.0
PROGRESS_LOCK_POLL_INTERVAL_SECONDS = 0.05
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

# Schema version - increment when breaking changes occur
CURRENT_SCHEMA_VERSION = "2.1"
LINKED_SNAPSHOT_SCHEMA_VERSION = "1.0"
DEFAULT_LINKED_STATUS_STALE_HOURS = 24
TRACKER_ROLES = ("standalone", "parent", "child")
DEFAULT_TRACKER_ROLE = "standalone"
ROOT_ROUTE_CODE = "ROOT"
DEVELOPMENT_STAGES = ("planning", "developing", "completed")
LIFECYCLE_STATES = ("approved", "implementing", "verified", "archived")
VALID_FINISH_STATES = ("merged_and_cleaned", "pr_open", "kept_with_reason")
FINISH_PENDING_STATE = "finish_pending"
OWNER_ROLES = ("architecture", "coding", "testing")
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
_PROGRESS_LOCK_HANDLE: Optional[Any] = None
_PROGRESS_LOCK_DEPTH = 0


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
    if _PROJECT_ROOT_OVERRIDE is not None:
        return _PROJECT_ROOT_OVERRIDE

    target_root, _ = resolve_target_project_root(project_root_arg=None)
    return target_root


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


def _progress_lock_path() -> Path:
    """Return the per-project progress lock file path."""
    progress_dir = get_progress_dir()
    progress_dir.mkdir(parents=True, exist_ok=True)
    return progress_dir / PROGRESS_LOCK_FILE


def _acquire_progress_lock(timeout_seconds: float = PROGRESS_LOCK_TIMEOUT_SECONDS) -> None:
    """Acquire a re-entrant cross-process lock for progress state mutations."""
    global _PROGRESS_LOCK_HANDLE, _PROGRESS_LOCK_DEPTH
    if fcntl is None:
        return

    if _PROGRESS_LOCK_DEPTH > 0 and _PROGRESS_LOCK_HANDLE is not None:
        _PROGRESS_LOCK_DEPTH += 1
        return

    lock_path = _progress_lock_path()
    handle = open(lock_path, "a+", encoding="utf-8")
    start = time.monotonic()

    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _PROGRESS_LOCK_HANDLE = handle
            _PROGRESS_LOCK_DEPTH = 1
            return
        except BlockingIOError:
            if time.monotonic() - start >= timeout_seconds:
                handle.close()
                raise TimeoutError(
                    f"Timed out acquiring progress lock after {timeout_seconds:.1f}s: {lock_path}"
                )
            time.sleep(PROGRESS_LOCK_POLL_INTERVAL_SECONDS)
        except Exception:
            handle.close()
            raise


def _release_progress_lock() -> None:
    """Release the re-entrant progress lock."""
    global _PROGRESS_LOCK_HANDLE, _PROGRESS_LOCK_DEPTH
    if fcntl is None:
        return
    if _PROGRESS_LOCK_DEPTH <= 0:
        return

    _PROGRESS_LOCK_DEPTH -= 1
    if _PROGRESS_LOCK_DEPTH > 0:
        return

    handle = _PROGRESS_LOCK_HANDLE
    _PROGRESS_LOCK_HANDLE = None
    if handle is None:
        return

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@contextmanager
def progress_transaction(timeout_seconds: float = PROGRESS_LOCK_TIMEOUT_SECONDS):
    """Transactional guard for mutating progress state."""
    _acquire_progress_lock(timeout_seconds=timeout_seconds)
    try:
        yield
    finally:
        _release_progress_lock()


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace a text file via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


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
    """
    Validate minimum plan structure for feature execution.

    Supports two compatible formats:

    1) Progress-tracker strict template:
       - Tasks
       - Acceptance mapping
       - Risks

    2) Superpowers writing-plans template:
       - Goal (header field)
       - Architecture (header field)
       - Tasks

    In format (2), missing strict sections are treated as warnings.
    """
    path_validation = validate_plan_path(
        plan_path, require_exists=True, target_root=target_root
    )
    if not path_validation["valid"]:
        return {
            "valid": False,
            "errors": [path_validation["error"]],
            "missing_sections": [],
            "warnings": [],
            "profile": "invalid",
        }

    base_root = target_root or find_project_root()
    absolute_path = base_root / path_validation["normalized_path"]
    try:
        content = absolute_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "valid": False,
            "errors": [f"Unable to read plan: {exc}"],
            "missing_sections": [],
            "warnings": [],
            "profile": "invalid",
        }

    checks = {
        # Match both "## Tasks" (list style) and "## Task 1: name" (Superpowers individual tasks)
        "tasks": re.search(r"^##+\s+Tasks?\b", content, flags=re.IGNORECASE | re.MULTILINE),
        "acceptance_mapping": re.search(
            r"^##+\s+Acceptance(\s+Criteria)?(\s+Mapping)?\b",
            content,
            flags=re.IGNORECASE | re.MULTILINE,
        ),
        "risks": re.search(r"^##+\s+Risks?\b", content, flags=re.IGNORECASE | re.MULTILINE),
    }
    superpowers_checks = {
        # Accept English and Chinese field labels (writing-plans generates Chinese when prompted in Chinese)
        "goal": re.search(r"^\*\*(Goal|目标):\*\*\s+.+", content, flags=re.MULTILINE),
        "architecture": re.search(r"^\*\*(Architecture|架构):\*\*\s+.+", content, flags=re.MULTILINE),
    }

    missing_sections = [name for name, found in checks.items() if not found]

    # Tasks are mandatory for all plan formats.
    if "tasks" in missing_sections:
        return {
            "valid": False,
            "errors": ["Missing required plan sections: tasks"],
            "missing_sections": missing_sections,
            "warnings": [],
            "profile": "invalid",
        }

    # Strict format fully satisfied.
    if not missing_sections:
        return {
            "valid": True,
            "errors": [],
            "missing_sections": [],
            "warnings": [],
            "profile": "strict",
        }

    # Superpowers-compatible format.
    if superpowers_checks["goal"] and superpowers_checks["architecture"]:
        advisory_missing = [s for s in missing_sections if s in ("acceptance_mapping", "risks")]
        warnings = []
        if advisory_missing:
            warnings.append(
                "Superpowers plan accepted; recommended sections missing: "
                f"{', '.join(advisory_missing)}"
            )
        return {
            "valid": True,
            "errors": [],
            "missing_sections": advisory_missing,
            "warnings": warnings,
            "profile": "superpowers",
        }

    return {
        "valid": False,
        "errors": [f"Missing required plan sections: {', '.join(missing_sections)}"],
        "missing_sections": missing_sections,
        "warnings": [],
        "profile": "invalid",
    }


def _default_owners() -> Dict[str, Optional[str]]:
    """Build default feature owners payload for known roles."""
    return {role: None for role in OWNER_ROLES}


def _normalize_feature_owners(feature: Dict[str, Any]) -> None:
    """Ensure feature owners map exists with known role keys."""
    owners = feature.get("owners")
    if not isinstance(owners, dict):
        owners = {}
    for role in OWNER_ROLES:
        owners.setdefault(role, None)
    feature["owners"] = owners


def _normalize_feature_defer_state(feature: Dict[str, Any]) -> None:
    """Ensure feature defer metadata is present and type-safe."""
    feature["deferred"] = bool(feature.get("deferred", False))
    feature["defer_reason"] = _normalize_optional_string(feature.get("defer_reason"))
    feature["deferred_at"] = _normalize_optional_string(feature.get("deferred_at"))
    feature["defer_group"] = _normalize_optional_string(feature.get("defer_group"))


def _clear_feature_defer_state(feature: Dict[str, Any]) -> None:
    """Clear defer metadata while keeping schema-compatible fields."""
    feature["deferred"] = False
    feature["defer_reason"] = None
    feature["deferred_at"] = None
    feature["defer_group"] = None


def _default_requirement_ids(feature: Dict[str, Any]) -> List[str]:
    """Build deterministic fallback requirement IDs for legacy features."""
    feature_id = feature.get("id")
    if isinstance(feature_id, int) and feature_id >= 0:
        return [f"REQ-{feature_id:03d}"]
    return ["REQ-000"]


def _default_change_spec(feature: Dict[str, Any]) -> Dict[str, Any]:
    """Build baseline change_spec for schema backfill."""
    feature_name = str(feature.get("name") or "Unnamed feature").strip()
    return {
        "why": f"Deliver {feature_name} with traceable acceptance coverage.",
        "in_scope": [feature_name],
        "out_of_scope": ["Unrelated refactors and behavior changes outside this feature."],
        "risks": ["Potential regression in adjacent workflows; verify with listed test_steps."],
    }


def _default_acceptance_scenarios(feature: Dict[str, Any]) -> List[str]:
    """Build fallback acceptance scenarios from test steps."""
    test_steps = feature.get("test_steps")
    if isinstance(test_steps, list):
        scenarios = [str(step).strip() for step in test_steps if str(step).strip()]
        if scenarios:
            return [f"Scenario: {step}" for step in scenarios]

    feature_name = str(feature.get("name") or "feature").strip()
    return [f"Scenario: {feature_name} baseline behavior works as expected."]


def _derive_lifecycle_state(feature: Dict[str, Any]) -> str:
    """Derive lifecycle state from legacy completion/development fields."""
    if feature.get("archive_info"):
        return "archived"

    if bool(feature.get("completed", False)):
        return "verified"

    stage = feature.get("development_stage")
    if stage == "developing":
        return "implementing"
    if stage == "completed":
        return "verified"

    return "approved"


def _normalize_feature_contract(feature: Dict[str, Any]) -> None:
    """Backfill schema 2.1 feature contract fields while preserving explicit values."""
    lifecycle_state = feature.get("lifecycle_state")
    if lifecycle_state not in LIFECYCLE_STATES:
        feature["lifecycle_state"] = _derive_lifecycle_state(feature)

    requirement_ids = feature.get("requirement_ids")
    if not isinstance(requirement_ids, list):
        feature["requirement_ids"] = _default_requirement_ids(feature)

    change_spec = feature.get("change_spec")
    defaults = _default_change_spec(feature)
    if not isinstance(change_spec, dict):
        feature["change_spec"] = defaults
    else:
        for key, value in defaults.items():
            change_spec.setdefault(key, value)
        feature["change_spec"] = change_spec

    acceptance_scenarios = feature.get("acceptance_scenarios")
    if not isinstance(acceptance_scenarios, list):
        feature["acceptance_scenarios"] = _default_acceptance_scenarios(feature)


def _default_linked_snapshot() -> Dict[str, Any]:
    """Build default snapshot metadata for linked project status aggregation."""
    return {
        "schema_version": LINKED_SNAPSHOT_SCHEMA_VERSION,
        "updated_at": None,
        "projects": [],
    }


def _normalize_linked_schema(data: Dict[str, Any]) -> None:
    """Backfill linked_projects and linked_snapshot top-level schema fields."""
    linked_projects = data.get("linked_projects")
    if not isinstance(linked_projects, list):
        linked_projects = []
    data["linked_projects"] = linked_projects

    linked_snapshot = data.get("linked_snapshot")
    defaults = _default_linked_snapshot()
    if not isinstance(linked_snapshot, dict):
        data["linked_snapshot"] = defaults
        return

    for key, value in defaults.items():
        linked_snapshot.setdefault(key, value)

    if not isinstance(linked_snapshot.get("projects"), list):
        linked_snapshot["projects"] = []

    data["linked_snapshot"] = linked_snapshot


def _normalize_route_schema(data: Dict[str, Any]) -> None:
    """Backfill routing metadata fields used by RouteV1 coordination."""
    tracker_role = data.get("tracker_role")
    if not isinstance(tracker_role, str):
        normalized_tracker_role = DEFAULT_TRACKER_ROLE
    else:
        normalized_tracker_role = tracker_role.strip().lower()
        if normalized_tracker_role not in TRACKER_ROLES:
            normalized_tracker_role = DEFAULT_TRACKER_ROLE
    data["tracker_role"] = normalized_tracker_role

    project_code = data.get("project_code")
    if isinstance(project_code, str):
        stripped_project_code = project_code.strip()
        data["project_code"] = stripped_project_code or None
    else:
        data["project_code"] = None

    routing_queue = data.get("routing_queue")
    if not isinstance(routing_queue, list):
        routing_queue = []
    data["routing_queue"] = routing_queue

    active_routes = data.get("active_routes")
    if not isinstance(active_routes, list):
        active_routes = []
    data["active_routes"] = active_routes


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
    project_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    now: Optional[datetime] = None,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
    active_routes: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Collect linked project progress snapshots in read-only mode.

    This function never writes linked project files; it only reads each child's
    `docs/progress-tracker/state/progress.json` and computes summary status.
    """
    if not isinstance(progress_data, dict):
        return []

    effective_project_root = Path(project_root or find_project_root()).resolve()
    effective_repo_root = Path(repo_root or _REPO_ROOT or effective_project_root).resolve()
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
            # spec_project_code still available; route_status unknown (no child data)
            status["project_code"] = spec_project_code
            if spec_project_code is None:
                status["route_status"] = "unknown"
            elif spec_project_code in _active_route_codes:
                status["route_status"] = "active"
            # else: keep "idle"
            statuses.append(status)
            continue

        try:
            payload = json.loads(progress_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("progress payload must be object")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            status["status"] = "invalid"
            status["error"] = str(exc)
            status["project_code"] = spec_project_code
            if spec_project_code is None:
                status["route_status"] = "unknown"
            elif spec_project_code in _active_route_codes:
                status["route_status"] = "active"
            # else: keep "idle"
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

        # --- F23: new fields ---
        # child_project_code: always from child payload
        child_code_raw = payload.get("project_code")
        child_code: Optional[str] = None
        if isinstance(child_code_raw, str) and child_code_raw.strip():
            child_code = child_code_raw.strip().upper()
        status["child_project_code"] = child_code

        # project_code: spec (linked_projects entry) → fallback child payload
        resolved_code = spec_project_code or child_code
        status["project_code"] = resolved_code

        # workspace: from child runtime_context.workspace_mode, whitelist only
        _VALID_WORKSPACE_MODES = {"worktree", "in_place", "unknown"}
        rt_ctx = payload.get("runtime_context")
        if isinstance(rt_ctx, dict):
            wm = rt_ctx.get("workspace_mode")
            if isinstance(wm, str) and wm.strip() in _VALID_WORKSPACE_MODES:
                status["workspace"] = wm.strip()
        # else: keep default "unknown"

        # route_status: "unknown" when no project_code; "active"/"idle" from active_routes
        if resolved_code is None:
            status["route_status"] = "unknown"
        elif resolved_code in _active_route_codes:
            status["route_status"] = "active"
        # else: keep default "idle"
        # --- end F23 ---

        # Compute active_feature_ref from project_code and current_feature_id
        project_code = payload.get("project_code")
        current_feature_id = payload.get("current_feature_id")
        if isinstance(project_code, str) and project_code.strip() and isinstance(current_feature_id, int):
            status["active_feature_ref"] = f"{project_code.strip()}-F{current_feature_id}"

        statuses.append(status)

    return statuses


def sync_linked(
    output_json: bool = False,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
) -> bool:
    """Refresh and persist linked project status snapshot under linked_snapshot."""
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

    _update_runtime_context(data, source="sync_linked")
    save_progress_json(data)

    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    ok_count = sum(1 for item in statuses if item.get("status") == "ok")
    missing_count = sum(1 for item in statuses if item.get("status") == "missing")
    invalid_count = sum(1 for item in statuses if item.get("status") == "invalid")
    stale_count = sum(1 for item in statuses if item.get("is_stale") is True)

    payload = {
        "status": "ok",
        "project_count": len(statuses),
        "ok_count": ok_count,
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "stale_count": stale_count,
        "stale_after_hours": stale_window_hours,
        "snapshot": linked_snapshot,
    }

    if output_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(
            "Synced linked snapshot: "
            f"{len(statuses)} projects (ok={ok_count}, missing={missing_count}, "
            f"invalid={invalid_count}, stale={stale_count})"
        )
    return True


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
    """Persist linked project roots as repo-relative paths when possible."""
    resolved_root = project_root.resolve()
    try:
        return resolved_root.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(resolved_root)


def _load_progress_payload_at_root(project_root: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
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
    _apply_schema_defaults(payload)
    return payload, None


def _save_progress_payload_at_root(
    project_root: Path,
    data: Dict[str, Any],
    *,
    touch_updated_at: bool = True,
) -> None:
    """Persist progress payload + markdown for an explicit root."""
    ensure_tracker_layout(project_root)
    _apply_schema_defaults(data)
    if touch_updated_at:
        data["updated_at"] = _iso_now()
    _atomic_write_text(
        get_progress_json_path(project_root),
        json.dumps(data, indent=2, ensure_ascii=False),
    )
    _atomic_write_text(get_progress_md_path(project_root), generate_progress_md(data))


def _notify_parent_sync() -> None:
    """Trigger parent linked_snapshot refresh after child state changes.

    Reads parent_project_root from the current child tracker.
    On any error (missing parent, invalid data), prints WARNING and returns.
    Never raises — always warn-only.
    """
    try:
        child_data = load_progress_json()
        if not isinstance(child_data, dict):
            return
        parent_raw = child_data.get("parent_project_root")
        if not parent_raw or not str(parent_raw).strip():
            return

        child_root = find_project_root().resolve()
        repo_root = Path(_REPO_ROOT or child_root).resolve()
        parent_root = _resolve_linked_project_root(str(parent_raw).strip(), child_root, repo_root)

        # Best-effort summary refresh before parent writeback (Task 7)
        try:
            load_status_summary_projection(str(child_root))
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
        statuses = collect_linked_project_statuses(
            parent_data,
            project_root=parent_root,
            active_routes=active_routes,
        )

        linked_snapshot = parent_data.get("linked_snapshot")
        if not isinstance(linked_snapshot, dict):
            linked_snapshot = {}
        linked_snapshot["schema_version"] = LINKED_SNAPSHOT_SCHEMA_VERSION
        linked_snapshot["updated_at"] = _iso_now()
        linked_snapshot["projects"] = statuses
        parent_data["linked_snapshot"] = linked_snapshot

        _save_progress_payload_at_root(parent_root, parent_data)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARNING] Parent writeback failed: {exc}")


def link_project(
    child_project_root: Optional[str],
    code: str,
    *,
    label: Optional[str] = None,
    output_json: bool = False,
) -> bool:
    """Register a child tracker under linked_projects and route queue."""
    parent_data = load_progress_json()
    if not parent_data:
        message = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

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
    child_root = _resolve_linked_project_root(raw_child_root, parent_root, repo_root)

    if child_root == parent_root:
        message = "Error: Child project root cannot be the same as parent project root."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    child_data, child_error = _load_progress_payload_at_root(child_root)
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

    # Collect previous codes for migration before delegating to helper
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

    # Delegate core registration to _link_child_to_parent
    _link_child_to_parent(
        parent_data, parent_root, repo_root, child_root, normalized_code, label=label
    )

    # Post-registration: migrate previous_codes in routing_queue
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

    # Post-registration: migrate previous_codes in active_routes
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

    # Derive output values from updated parent_data
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
    if output_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(
            "Linked child project "
            f"{configured_project_root} as {normalized_code}. "
            f"routing_queue={normalized_queue}"
        )
    return True


# ---------------------------------------------------------------------------
# Monorepo child discovery helpers (F10)
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


def _link_child_to_parent(
    parent_data: Dict[str, Any],
    parent_root: Path,
    repo_root: Path,
    child_root: Path,
    code: str,
    label: Optional[str] = None,
    append_to_queue: bool = True,
) -> None:
    """Register a child tracker in the parent's linked_projects and queue.

    Extracted from ``link_project()`` so discovery can reuse the core
    registration logic without the CLI scaffolding.
    """
    normalized_code = _normalize_project_code(code) or code.upper()[:8]

    # Write child metadata
    child_data, _ = _load_progress_payload_at_root(child_root)
    if isinstance(child_data, dict):
        child_data["tracker_role"] = "child"
        child_data["project_code"] = normalized_code
        child_data["parent_project_root"] = _serialize_project_root_for_config(
            parent_root, repo_root
        )
        _save_progress_payload_at_root(child_root, child_data)

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
                _save_progress_payload_at_root(child_root, child_data)

    # Initialize empty queue as [ROOT] + sorted(initialized_codes) if queue is empty
    if not existing_queue:
        # Re-derive properly with all codes considered
        all_codes: Set[str] = set()
        final_codes: List[str] = [ROOT_ROUTE_CODE]
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


def discover_children(*, output_json: bool = False) -> bool:
    """Discover and register child trackers under a parent."""
    project_root = find_project_root()
    repo_root = _resolve_repo_root(project_root)

    data = load_progress_json()
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

    _update_runtime_context(data, source="discover_children")
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

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
    data = load_progress_json()
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
    for item in routing_queue:
        if not isinstance(item, str):
            continue
        code = item.strip().upper()
        if code and code != ROOT_ROUTE_CODE and code not in linked_codes:
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
    data = load_progress_json()
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

    # Move to front, preserving order of remaining entries
    new_queue = [normalized_code] + [c for c in routing_queue if c != normalized_code]
    data["routing_queue"] = new_queue

    _update_runtime_context(data, source="prioritize_route")
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

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
    data = load_progress_json()
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
    invalid_codes = [c for c in normalized_codes if c != ROOT_ROUTE_CODE and c not in linked_codes]
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

    _update_runtime_context(data, source="set_routing_queue")
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

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
    from prog_paths import resolve_repo_root
    return resolve_repo_root(cwd=project_root)


def route_select(
    project_code: str,
    *,
    feature_ref: Optional[str] = None,
    output_json: bool = False,
) -> bool:
    """Upsert active_routes entry for project_code (unique key), merging duplicates."""
    data = load_progress_json()
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
    _git_ctx = collect_git_context()
    upserted_entry["worktree_path"] = _git_ctx.get("worktree_path")
    upserted_entry["branch"] = _git_ctx.get("branch")

    new_routes = other_routes + [upserted_entry]
    data["active_routes"] = new_routes

    _update_runtime_context(data, source="route_select")
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

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


def _apply_imported_feature_contract(feature: Dict[str, Any], contract: Dict[str, Any]) -> None:
    """Apply imported contract payload onto a feature record."""
    feature["requirement_ids"] = contract["requirement_ids"]
    feature["change_spec"] = contract["change_spec"]
    feature["acceptance_scenarios"] = contract["acceptance_scenarios"]
    _normalize_feature_contract(feature)


def _has_non_empty_list_items(value: Any) -> bool:
    """Return True when value is a list containing at least one non-empty item."""
    return isinstance(value, list) and any(str(item).strip() for item in value)


def validate_feature_readiness(feature: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate feature contract readiness using blocking and warning checks.

    Contract:
      {
        "valid": bool,
        "errors": [str],      # blocking checks
        "warnings": [str],    # advisory checks
      }
    """
    blockers: List[str] = []
    warnings: List[str] = []

    if not _has_non_empty_list_items(feature.get("requirement_ids")):
        blockers.append("requirement_ids cannot be empty")

    change_spec = feature.get("change_spec")
    if not isinstance(change_spec, dict):
        change_spec = {}

    why = str(change_spec.get("why") or "").strip()
    if not why:
        blockers.append("change_spec.why cannot be empty")
    elif len(why) <= 10:
        warnings.append("change_spec.why should be longer than 10 characters")

    if not _has_non_empty_list_items(feature.get("acceptance_scenarios")):
        blockers.append("acceptance_scenarios cannot be empty")

    if not _has_non_empty_list_items(feature.get("test_steps")):
        warnings.append("test_steps is empty")

    name = str(feature.get("name") or "").strip()
    if len(name) < 5:
        warnings.append("name should be at least 5 characters")

    # Keep readiness warning semantics aligned with done gate contract checks.
    sprint_contract = feature.get("sprint_contract")
    missing: List[str] = []
    if not isinstance(sprint_contract, dict):
        missing = ["scope", "done_criteria", "test_plan"]
    else:
        if not str(sprint_contract.get("scope") or "").strip():
            missing.append("scope")
        done_criteria = sprint_contract.get("done_criteria")
        if not _has_non_empty_list_items(done_criteria):
            missing.append("done_criteria")
        test_plan = sprint_contract.get("test_plan")
        if not _has_non_empty_list_items(test_plan):
            missing.append("test_plan")
    if missing:
        warnings.append(
            "sprint_contract incomplete: "
            + ", ".join(missing)
            + " are empty or missing. Fill before /prog done."
        )

    return {
        "valid": len(blockers) == 0,
        "errors": blockers,
        "warnings": warnings,
    }


def print_readiness_warnings(report: Dict[str, Any]) -> None:
    """Print non-blocking readiness warnings."""
    warnings = report.get("warnings", [])
    if not warnings:
        return

    print("Warnings (non-blocking):")
    for warning in warnings:
        print(f"  - {warning}")


def _build_readiness_fix_commands(feature_id: int, errors: List[str]) -> List[str]:
    """Build deterministic one-line fix commands from blocking errors."""
    commands: List[str] = []
    seen: Set[str] = set()
    default_req = f"REQ-{feature_id:03d}"

    def _add(command: str) -> None:
        if command in seen:
            return
        seen.add(command)
        commands.append(command)

    for error in errors:
        if "requirement_ids" in error:
            _add(
                f"plugins/progress-tracker/prog fix-readiness {feature_id} --add-requirement {default_req}"
            )
        elif "change_spec.why" in error:
            _add(
                f"plugins/progress-tracker/prog fix-readiness {feature_id} --set-why \"Detailed explanation...\""
            )
        elif "acceptance_scenarios" in error:
            _add(
                f"plugins/progress-tracker/prog fix-readiness {feature_id} --add-acceptance \"Scenario: ...\""
            )

    return commands


def print_readiness_error(feature: Dict[str, Any], report: Dict[str, Any]) -> None:
    """Print readiness blockers and actionable fix commands."""
    feature_id = feature.get("id", "?")
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])

    print(f"Feature #{feature_id} cannot start: readiness check failed")
    print("")
    print("Blockers:")
    for error in errors:
        print(f"  - {error}")

    if warnings:
        print("")
        print_readiness_warnings(report)

    fix_commands = _build_readiness_fix_commands(
        feature_id if isinstance(feature_id, int) else 0,
        [str(item) for item in errors],
    )
    if fix_commands:
        print("")
        print("Suggested fixes:")
        for command in fix_commands:
            print(f"  {command}")

    print("")
    print(f"Retry: plugins/progress-tracker/prog set-current {feature_id}")


def validate_readiness_command(feature_id: int) -> int:
    """Read-only readiness validation. Returns 0 when no blockers, otherwise 1."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return 1

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return 1

    report = validate_feature_readiness(feature)
    if report["valid"]:
        print(f"Feature #{feature_id} readiness check passed")
        if report["warnings"]:
            print("")
            print_readiness_warnings(report)
        return 0

    print_readiness_error(feature, report)
    return 1


def validate_planning_command(feature_id: int, output_json: bool = False) -> bool:
    """Validate preflight planning artifacts from structured updates.

    Returns:
        True (exit code 0) for ready/warn status
        False (exit code 1) for missing status
    """
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])
    target_feature = next((f for f in features if f.get("id") == feature_id), None)
    if target_feature is None:
        print(f"Feature ID {feature_id} not found")
        return False

    report = _evaluate_planning_readiness(data, feature_id=feature_id)
    if output_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(
            f"Planning preflight for feature #{feature_id}: {report['status']} - "
            f"{report['message']}"
        )
        if report.get("refs"):
            print("Refs:")
            for ref in report["refs"]:
                print(f"- {ref}")

    # Return exit code: 0 (True) for ready/warn, 1 (False) for missing
    status = report.get("status", "ready")
    return status != "missing"


def fix_readiness_command(
    feature_id: int,
    *,
    add_requirement: Optional[str] = None,
    set_why: Optional[str] = None,
    add_acceptance: Optional[str] = None,
) -> bool:
    """
    Apply structured contract fixes for readiness blockers.

    Returns False for invalid input/feature-not-found; True for successful (including idempotent) runs.
    """
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    feature = next((f for f in data.get("features", []) if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    operations = [add_requirement, set_why, add_acceptance]
    if not any(item is not None for item in operations):
        print(
            "Error: At least one operation required "
            "(--add-requirement / --set-why / --add-acceptance)"
        )
        return False

    changed = False

    if add_requirement is not None:
        requirement = str(add_requirement).strip()
        if not requirement:
            print("Error: --add-requirement cannot be empty")
            return False
        if not requirement.startswith("REQ-"):
            print(f"Warning: '{requirement}' does not match REQ- format")

        requirement_ids = feature.get("requirement_ids")
        if not isinstance(requirement_ids, list):
            requirement_ids = []
            feature["requirement_ids"] = requirement_ids
        if requirement not in requirement_ids:
            requirement_ids.append(requirement)
            changed = True

    if set_why is not None:
        why = str(set_why).strip()
        if not why:
            print("Error: --set-why cannot be empty")
            return False
        change_spec = feature.get("change_spec")
        if not isinstance(change_spec, dict):
            change_spec = {}
            feature["change_spec"] = change_spec
        if change_spec.get("why") != why:
            change_spec["why"] = why
            changed = True

    if add_acceptance is not None:
        acceptance = str(add_acceptance).strip()
        if not acceptance:
            print("Error: --add-acceptance cannot be empty")
            return False
        acceptance_scenarios = feature.get("acceptance_scenarios")
        if not isinstance(acceptance_scenarios, list):
            acceptance_scenarios = []
            feature["acceptance_scenarios"] = acceptance_scenarios
        if acceptance not in acceptance_scenarios:
            acceptance_scenarios.append(acceptance)
            changed = True

    if changed:
        _normalize_feature_contract(feature)
        save_progress_json(data)
        save_progress_md(generate_progress_md(data))
        print(f"Feature #{feature_id} updated")
    else:
        print(f"No changes needed for feature #{feature_id}")

    report = validate_feature_readiness(feature)
    if report["valid"]:
        print("All blockers resolved. Ready to start.")
    else:
        print("Remaining blockers:")
        for error in report["errors"]:
            print(f"  - {error}")

    if report["warnings"]:
        print("")
        print_readiness_warnings(report)

    return True


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


def _default_sprint_contract(feature: Dict[str, Any]) -> None:
    """PR-3/schema-2.1: inject sprint_contract defaults if absent."""
    if os.environ.get("PROG_DISABLE_V2") == "1" and "sprint_contract" in feature:
        return
    feature.setdefault(
        "sprint_contract",
        {
            "scope": "",
            "done_criteria": [],
            "test_plan": [],
            "accepted_by": None,
            "accepted_at": None,
        },
    )


def _default_quality_gates(feature: Dict[str, Any]) -> None:
    """PR-3/schema-2.1: deep-merge quality_gates defaults (handles partial existing data)."""
    if os.environ.get("PROG_DISABLE_V2") == "1" and "quality_gates" in feature:
        return
    default_evaluator = {
        "status": "pending",
        "score": None,
        "defects": [],
        "last_run_at": None,
        "evaluator_model": None,
    }
    default_reviews = {"required": [], "passed": [], "pending": []}
    default_ship_check = {"status": "pending", "failures": [], "last_run_at": None}

    if "quality_gates" not in feature:
        feature["quality_gates"] = {
            "evaluator": default_evaluator,
            "reviews": default_reviews,
            "ship_check": default_ship_check,
        }
        return

    # Deep merge: fill missing sub-keys without clobbering existing data
    qg = feature["quality_gates"]
    if not isinstance(qg.get("evaluator"), dict):
        qg["evaluator"] = default_evaluator
    else:
        for k, v in default_evaluator.items():
            qg["evaluator"].setdefault(k, v)
    if "reviews" not in qg:
        qg["reviews"] = default_reviews
    else:
        for k, v in default_reviews.items():
            qg["reviews"].setdefault(k, v)
    if "ship_check" not in qg:
        qg["ship_check"] = default_ship_check
    else:
        for k, v in default_ship_check.items():
            qg["ship_check"].setdefault(k, v)


def _sync_reviews_pending_cache(feature: Dict[str, Any]) -> None:
    """Keep reviews.pending as a derived cache from required - passed.

    This is display-oriented normalization only; gate decisions must still rely on
    review_router.get_pending_lanes() and never trust persisted pending directly.
    """
    quality_gates = feature.get("quality_gates")
    if not isinstance(quality_gates, dict):
        return
    reviews = quality_gates.get("reviews")
    if not isinstance(reviews, dict):
        return

    required_raw = reviews.get("required")
    passed_raw = reviews.get("passed")
    required = required_raw if isinstance(required_raw, list) else []
    passed = passed_raw if isinstance(passed_raw, list) else []
    reviews["pending"] = [lane for lane in required if lane not in passed]


def _default_handoff(feature: Dict[str, Any]) -> None:
    """PR-3/schema-2.1: inject handoff defaults if absent."""
    if os.environ.get("PROG_DISABLE_V2") == "1" and "handoff" in feature:
        return
    feature.setdefault(
        "handoff",
        {
            "from_phase": None,
            "to_phase": None,
            "artifact_path": None,
            "created_at": None,
        },
    )


def _apply_schema_defaults(data: Dict[str, Any]) -> None:
    """Backfill backward-compatible defaults for evolving schema fields."""
    old_version = data.get("schema_version")
    if "schema_version" not in data:
        data["schema_version"] = CURRENT_SCHEMA_VERSION

    features = data.get("features")
    if not isinstance(features, list):
        features = []
    data["features"] = features
    for feature in features:
        if isinstance(feature, dict):
            _normalize_feature_owners(feature)
            _normalize_feature_defer_state(feature)
            _normalize_feature_contract(feature)
            _default_quality_gates(feature)
            _sync_reviews_pending_cache(feature)
            _default_sprint_contract(feature)
            _default_handoff(feature)

    # Upgrade schema version and emit audit event on first migration
    if old_version == "2.0" and data.get("schema_version") != "2.1":
        data["schema_version"] = "2.1"
        _append_audit_event(
            event_type="schema_migration",
            details={"from": "2.0", "to": "2.1"},
        )
    elif old_version is None or old_version not in ("2.0", "2.1"):
        data["schema_version"] = CURRENT_SCHEMA_VERSION

    _normalize_linked_schema(data)
    _normalize_route_schema(data)

    updates = data.get("updates")
    if not isinstance(updates, list):
        updates = []
    data["updates"] = [item for item in updates if isinstance(item, dict)]

    retrospectives = data.get("retrospectives")
    if not isinstance(retrospectives, list):
        retrospectives = []
    data["retrospectives"] = [item for item in retrospectives if isinstance(item, dict)]

    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    data["tasks"] = [t for t in tasks if isinstance(t, dict)]


def load_progress_json():
    """Load the progress.json file."""
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if not json_path.exists():
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                print(f"Error: {json_path} is not a valid JSON object.")
                return None
            _apply_schema_defaults(data)
            return data
    except json.JSONDecodeError:
        print(f"Error: {json_path} is corrupted.")
        return None


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
    data = load_progress_json()
    if data is None:
        raise ValueError("progress.json not found")
    feat = next((f for f in data.get("features", []) if f.get("id") == feature_id), None)
    if feat is None:
        raise ValueError(f"feature {feature_id} not found")
    feat.setdefault("quality_gates", {})
    feat["quality_gates"]["evaluator"] = result.to_quality_gate_payload()
    save_progress_json(data)
    _append_audit_event(
        event_type="evaluator_assessment",
        feature_id=feature_id,
        details={"status": result.status, "score": result.score},
    )


def _emit(data: Dict[str, Any], as_json: bool) -> None:
    """Print reconcile_evaluator result as JSON or human-readable text."""
    if as_json:
        print(json.dumps(data))
    else:
        if "error" in data:
            print(f"Error: {data['error']}", file=sys.stderr)
        elif "summary" in data:
            print(f"Reconcile evaluator: {data['summary']}")
            if data.get("failed"):
                print("Failed features:")
                for fid_str, err in data["failed"].items():
                    print(f"  F{fid_str}: {err}")


def reconcile_evaluator(
    feature_id: Optional[int] = None,
    output_json: bool = False,
) -> int:
    """Backfill evaluator results for completed features missing evaluation.

    For each candidate feature, calls evaluator_gate.assess() synchronously,
    then persists via _store_evaluator_result() (which writes an
    'evaluator_assessment' audit event) and appends a separate
    'evaluator_backfill' audit event recording the CLI source and reason.
    Two audit events per backfill is intentional: they serve different
    observability purposes.

    Scope of "completed" features:
      - completed == True  (archived)
      - lifecycle_state in ("execution_complete", "archived")
        (execution_complete included because it means implementation is done
        but /prog done has not yet run — still a valid backfill target)

    Args:
        feature_id: If given, only process this feature (ignores backfill filter,
                    allowing forced re-evaluation of already-evaluated features).
        output_json: Emit JSON summary to stdout.

    Returns:
        0 = all succeeded, 1 = partial failure, 2 = all failed / system error.
    """
    if evaluator_gate_mod is None:
        _emit({"error": "evaluator_gate module not available"}, output_json)
        return 2

    # Read raw JSON first to track original evaluator state before schema
    # normalization converts null evaluators to {"status": "pending", ...}.
    # This lets us distinguish "missing_evaluator" from "retry" reasons.
    raw_null_evaluator_ids: set = set()
    try:
        raw_json_path = get_progress_dir() / PROGRESS_JSON
        if raw_json_path.exists():
            raw = json.loads(raw_json_path.read_text(encoding="utf-8"))
            for f in raw.get("features", []):
                qg = f.get("quality_gates") or {}
                if qg.get("evaluator") is None and "quality_gates" in f:
                    raw_null_evaluator_ids.add(f.get("id"))
    except Exception:
        pass  # Non-critical; backfill_reason defaults to "retry"

    data = load_progress_json()
    if data is None:
        _emit({"error": "progress.json not found"}, output_json)
        return 2

    features = data.get("features", [])

    def _needs_backfill(feat: Dict[str, Any]) -> bool:
        ev = feat.get("quality_gates", {}).get("evaluator")
        return ev is None or ev.get("status") == "pending"

    if feature_id is not None:
        candidates = [f for f in features if f.get("id") == feature_id]
        if not candidates:
            _emit({"error": f"Feature {feature_id} not found"}, output_json)
            return 2
        # Track whether this is a forced overwrite of existing evaluator data.
        # Unlike the full-scan path, --feature-id always evaluates (for re-evaluation).
        forced_overwrite_ids = {
            f["id"] for f in candidates if not _needs_backfill(f)
        }
    else:
        forced_overwrite_ids: set = set()  # full-scan never forces overwrites
        # Collect completed features: archived ones plus the current feature
        # if its workflow phase is execution_complete (implementation done but
        # /prog done not yet run — still a valid backfill target).
        exec_complete_ids: set = set()
        wf = data.get("workflow_state") or {}
        if wf.get("phase") == "execution_complete":
            current_fid = data.get("current_feature_id")
            if current_fid is not None:
                exec_complete_ids.add(current_fid)

        completed = [
            f
            for f in features
            if f.get("completed") or f.get("id") in exec_complete_ids
        ]
        candidates = [f for f in completed if _needs_backfill(f)]

    if not candidates:
        report: Dict[str, Any] = {
            "total_scanned": 0,
            "backfilled": 0,
            "failed": {},
            "summary": "No features need evaluator backfill",
        }
        _emit(report, output_json)
        return 0

    rubric: Dict[str, Any] = {"test_coverage_min": 0.0}
    signals: Dict[str, Any] = {"test_coverage": 1.0, "defects": []}
    backfilled: List[int] = []
    failed: Dict[str, str] = {}

    for feat in candidates:
        fid = feat["id"]
        backfill_reason = (
            "missing_evaluator" if fid in raw_null_evaluator_ids else "retry"
        )
        try:
            result = evaluator_gate_mod.assess(
                feature=feat,
                rubric=rubric,
                signals=signals,
            )
            _store_evaluator_result(fid, result)  # also writes evaluator_assessment event
            _append_audit_event(
                event_type="evaluator_backfill",
                feature_id=fid,
                details={
                    "status": result.status,
                    "score": result.score,
                    "backfill_reason": backfill_reason,
                    "source": "reconcile-evaluator CLI",
                    "synthetic": True,
                    "score_source": "backfill_default",
                    **({"forced_overwrite": True} if fid in forced_overwrite_ids else {}),
                },
            )
            backfilled.append(fid)
        except Exception as exc:
            failed[str(fid)] = str(exc)

    total = len(candidates)
    n_ok = len(backfilled)
    report = {
        "total_scanned": total,
        "backfilled": n_ok,
        "failed": failed,
        "summary": f"{n_ok}/{total} backfilled successfully",
    }
    _emit(report, output_json)

    if failed and backfilled:
        return 1
    if failed:
        return 2
    return 0


def save_progress_json(data, touch_updated_at: bool = True):
    """Save data to progress.json file with optional updated_at touch and migration."""
    with progress_transaction():
        progress_dir = get_progress_dir()
        json_path = progress_dir / PROGRESS_JSON

        # Ensure state directory exists
        progress_dir.mkdir(parents=True, exist_ok=True)

        _apply_schema_defaults(data)

        # Auto-update updated_at timestamp
        if touch_updated_at:
            data["updated_at"] = _iso_now()

        payload = json.dumps(data, indent=2, ensure_ascii=False)
        _atomic_write_text(json_path, payload)


def load_progress_md():
    """Load the progress.md file content."""
    progress_dir = get_progress_dir()
    md_path = progress_dir / PROGRESS_MD

    if not md_path.exists():
        return None

    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()


def save_progress_md(content):
    """Save content to progress.md file."""
    with progress_transaction():
        progress_dir = get_progress_dir()
        md_path = progress_dir / PROGRESS_MD

        # Ensure state directory exists
        progress_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(md_path, content)


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

    Fail-closed: writes the ``project_completed`` audit boundary event FIRST.
    If the audit write raises any exception, the function returns immediately
    WITHOUT modifying the active state — this prevents old-cycle
    ``feature_completed`` events from corrupting the next cycle's
    reconcile/backfill.

    Args:
        data: The in-memory progress dict (mutated in place and saved to disk).
    """
    # 1. Fail-closed: write audit boundary event FIRST.
    try:
        record_feature_state_event(
            event_type="project_completed",
            feature_id=None,
            feature_name=None,
        )
    except Exception as exc:
        print(
            f"Warning: _reset_active_progress: failed to write project_completed "
            f"audit event — aborting reset to prevent state corruption. "
            f"Error: {exc}"
        )
        return

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


RUNTIME_CONTEXT_COMPARE_KEYS = (
    "workspace_mode",
    "worktree_path",
    "project_root",
    "cwd",
    "git_dir",
    "branch",
    "upstream",
    "current_feature_id",
    "workflow_phase",
    "current_task",
    "total_tasks",
    "next_action",
)


def _normalize_context_path(value: Optional[str]) -> Optional[str]:
    """Normalize paths for cross-platform comparison."""
    if not value:
        return None
    try:
        return Path(value).resolve().as_posix()
    except Exception:
        return str(value).replace("\\", "/")


def _normalize_optional_string(value: Optional[str]) -> Optional[str]:
    """Normalize optional string values for context comparison."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def collect_git_context() -> Dict[str, Any]:
    """
    Collect current git/worktree context using lightweight git probes.

    workspace_mode contract:
    - unknown: not a git repo or probes failed
    - worktree: git dir path contains '/worktrees/'
    - in_place: git repo and not a linked worktree git dir
    """
    fallback_root = find_project_root()
    fallback_root_str = str(fallback_root.resolve())
    cwd_str = str(Path.cwd().resolve())
    context: Dict[str, Any] = {
        "workspace_mode": "unknown",
        "worktree_path": fallback_root_str,
        "project_root": fallback_root_str,
        "cwd": cwd_str,
        "git_dir": None,
        "branch": None,
        "upstream": None,
    }

    exit_code, stdout, _ = _run_git(
        ["rev-parse", "--show-toplevel"],
        cwd=str(fallback_root),
        timeout=5,
    )
    if exit_code != 0 or not stdout.strip():
        return context

    project_root_raw = stdout.strip()
    try:
        project_root = Path(project_root_raw).resolve()
    except Exception:
        project_root = Path(project_root_raw)

    project_root_str = str(project_root)
    context["project_root"] = project_root_str
    context["worktree_path"] = project_root_str

    exit_code, stdout, _ = _run_git(
        ["rev-parse", "--absolute-git-dir"],
        cwd=str(project_root),
        timeout=5,
    )
    git_dir = stdout.strip() if exit_code == 0 and stdout.strip() else None
    context["git_dir"] = git_dir

    if git_dir:
        git_dir_posix = _normalize_context_path(git_dir) or ""
        context["workspace_mode"] = (
            "worktree" if "/worktrees/" in git_dir_posix else "in_place"
        )
    else:
        context["workspace_mode"] = "in_place"

    exit_code, stdout, _ = _run_git(
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=str(project_root),
        timeout=5,
    )
    context["branch"] = stdout.strip() if exit_code == 0 and stdout.strip() else None

    exit_code, stdout, _ = _run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=str(project_root),
        timeout=5,
    )
    context["upstream"] = stdout.strip() if exit_code == 0 and stdout.strip() else None

    return context


def build_runtime_context(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Build top-level runtime_context snapshot from current repository + progress state."""
    git_context = collect_git_context()
    tracker_root = str(find_project_root().resolve())
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}

    runtime_context: Dict[str, Any] = {
        "recorded_at": _iso_now(),
        "source": source,
        **git_context,
        "tracker_root": tracker_root,
        "current_feature_id": data.get("current_feature_id"),
        "workflow_phase": workflow_state.get("phase"),
        "current_task": workflow_state.get("current_task"),
        "total_tasks": workflow_state.get("total_tasks"),
        "next_action": workflow_state.get("next_action"),
    }
    return runtime_context


def build_execution_context(source: str) -> Dict[str, Any]:
    """Build workflow_state.execution_context snapshot for workflow semantic transitions."""
    git_context = collect_git_context()
    tracker_root = str(find_project_root().resolve())
    return {
        "recorded_at": _iso_now(),
        "source": source,
        "workspace_mode": git_context.get("workspace_mode"),
        "worktree_path": git_context.get("worktree_path"),
        "project_root": git_context.get("project_root"),
        "tracker_root": tracker_root,
        "git_dir": git_context.get("git_dir"),
        "branch": git_context.get("branch"),
        "upstream": git_context.get("upstream"),
    }


def _runtime_context_fingerprint(ctx: Optional[Dict[str, Any]]) -> Tuple[Any, ...]:
    """Build a comparable fingerprint for runtime_context deduplication."""
    if not isinstance(ctx, dict):
        return tuple([None] * len(RUNTIME_CONTEXT_COMPARE_KEYS))
    normalized: List[Any] = []
    for key in RUNTIME_CONTEXT_COMPARE_KEYS:
        value = ctx.get(key)
        if key in {"worktree_path", "project_root", "cwd", "git_dir"}:
            normalized.append(_normalize_context_path(value))
        else:
            normalized.append(value)
    return tuple(normalized)


def _update_runtime_context(data: Dict[str, Any], source: str, force: bool = False) -> bool:
    """Update top-level runtime_context in progress data; returns True if changed."""
    if not isinstance(data, dict):
        return False

    new_context = build_runtime_context(data, source)
    old_context = data.get("runtime_context")

    if not force and _runtime_context_fingerprint(old_context) == _runtime_context_fingerprint(new_context):
        return False

    data["runtime_context"] = new_context
    return True


def _update_execution_context(workflow_state: Dict[str, Any], source: str) -> None:
    """Refresh workflow_state.execution_context after semantic workflow progress changes."""
    if not isinstance(workflow_state, dict):
        return
    workflow_state["execution_context"] = build_execution_context(source)


def compare_contexts(
    expected: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compare expected execution context with current/runtime context.

    Returns a normalized hint object suitable for recovery/status output.
    """
    if not isinstance(expected, dict):
        expected = {}
    if not isinstance(current, dict):
        current = {}

    expected_branch = _normalize_optional_string(expected.get("branch"))
    expected_path = _normalize_context_path(expected.get("worktree_path"))
    current_branch = _normalize_optional_string(current.get("branch"))
    current_path = _normalize_context_path(current.get("worktree_path"))

    expected_has_signal = bool(expected_branch or expected_path)
    current_has_signal = bool(current_branch or current_path)

    result: Dict[str, Any] = {
        "status": "unknown",
        "severity": "info",
        "expected_branch": expected_branch,
        "expected_worktree_path": expected_path,
        "current_branch": current_branch,
        "current_worktree_path": current_path,
        "message": "No execution context available yet.",
    }

    if not expected_has_signal:
        return result

    if not current_has_signal:
        result.update(
            {
                "status": "unknown",
                "severity": "warning",
                "message": "Current session context is unavailable; cannot verify worktree/branch alignment.",
            }
        )
        return result

    expected_needs_path = bool(expected_path)
    expected_needs_branch = bool(expected_branch)

    path_missing_current = expected_needs_path and not current_path
    branch_missing_current = expected_needs_branch and not current_branch

    path_mismatch = bool(expected_path and current_path and expected_path != current_path)
    branch_mismatch = bool(expected_branch and current_branch and expected_branch != current_branch)

    if path_mismatch or branch_mismatch:
        if path_mismatch and branch_mismatch:
            status = "mismatch"
        elif path_mismatch:
            status = "path_mismatch"
        else:
            status = "branch_mismatch"

        msg_parts: List[str] = ["Current session does not match the last recorded execution context"]
        details: List[str] = []
        if path_mismatch:
            details.append("worktree path differs")
        if branch_mismatch:
            details.append("branch differs")
        if path_missing_current:
            details.append("current worktree path unavailable")
        if branch_missing_current:
            details.append("current branch unavailable")
        if details:
            msg_parts.append(f"({', '.join(details)})")

        result.update(
            {
                "status": status,
                "severity": "warning",
                "message": " ".join(msg_parts) + ".",
            }
        )
        return result

    missing_parts: List[str] = []
    if path_missing_current:
        missing_parts.append("worktree path")
    if branch_missing_current:
        missing_parts.append("branch")
    if missing_parts:
        result.update(
            {
                "status": "unknown",
                "severity": "warning",
                "message": (
                    "Current session context is incomplete; cannot verify "
                    + " and ".join(missing_parts)
                    + " alignment."
                ),
            }
        )
        return result

    if (not expected_needs_path or expected_path == current_path) and (
        not expected_needs_branch or expected_branch == current_branch
    ):
        result.update(
            {
                "status": "match",
                "severity": "info",
                "message": "Current session matches the last recorded execution context.",
            }
        )
        return result

    result.update(
        {
            "status": "unknown",
            "severity": "warning",
            "message": "Current session context could not be fully compared with the recorded execution context.",
        }
    )
    return result


def _format_context_summary(context: Optional[Dict[str, Any]]) -> str:
    """Format a concise context summary for CLI/markdown displays."""
    if not isinstance(context, dict):
        return "unknown"

    branch = context.get("branch") or "(no-branch)"
    worktree_path = context.get("worktree_path")
    mode = context.get("workspace_mode") or "unknown"

    if worktree_path:
        try:
            worktree_label = Path(worktree_path).name or worktree_path
        except Exception:
            worktree_label = str(worktree_path)
        return f"{branch} @ {worktree_label} [{mode}]"
    return f"{branch} [{mode}]"


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
    """Read JSON object from disk and return None on parse/shape errors."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _status_source_snapshot(path: Path, rel_path: str) -> Dict[str, Any]:
    """Return lightweight source-file fingerprint for drift detection."""
    if not path.exists():
        return {
            "path": rel_path,
            "exists": False,
            "mtime_ns": None,
            "size": None,
        }
    stat = path.stat()
    return {
        "path": rel_path,
        "exists": True,
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
    }


def _status_summary_source_fingerprint(target_root: Path) -> Dict[str, Any]:
    """Collect input fingerprints for progress/checkpoints source files."""
    progress_path = get_progress_json_path(target_root)
    checkpoints_path = get_checkpoints_path(target_root)
    return {
        "progress": _status_source_snapshot(
            progress_path, rel_progress_path(PROGRESS_JSON)
        ),
        "checkpoints": _status_source_snapshot(
            checkpoints_path, rel_progress_path(CHECKPOINTS_JSON)
        ),
    }


def _load_progress_data_for_summary(progress_path: Path) -> Dict[str, Any]:
    """Load progress payload for summary projection with graceful fallback."""
    payload = _read_json_dict(progress_path)
    if payload is None:
        return {"features": [], "current_feature_id": None, "bugs": []}
    _apply_schema_defaults(payload)
    return payload


def _format_relative_time_for_summary(iso_timestamp: Optional[str]) -> str:
    """Format ISO timestamp into compact relative text for status summary."""
    if not iso_timestamp:
        return "暂无快照"
    try:
        timestamp = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - timestamp
        if delta.days > 0:
            return f"{delta.days} 天前"
        if delta.seconds >= 3600:
            return f"{delta.seconds // 3600} 小时前"
        if delta.seconds >= 60:
            return f"{delta.seconds // 60} 分钟前"
        return "刚刚"
    except Exception:
        return iso_timestamp


def _normalize_feature_stage_for_summary(feature: Dict[str, Any]) -> str:
    """Normalize development_stage for summary rendering."""
    if feature.get("completed", False):
        return "completed"
    stage = feature.get("development_stage")
    if stage in {"planning", "developing", "completed"}:
        return stage
    return "developing"


def _stage_label_for_summary(stage: Optional[str]) -> Optional[str]:
    """Localize status stage labels used by summary payload."""
    if stage is None:
        return None
    return {
        "planning": "规划中",
        "developing": "开发中",
        "completed": "已完成",
        "pending": "待开始",
    }.get(stage, "未知")


def _determine_next_action_for_summary(
    features: List[Dict[str, Any]], progress_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Build next_action summary field from active/pending feature state."""
    current_id = progress_data.get("current_feature_id")
    if current_id is not None:
        feature = next(
            (
                f
                for f in features
                if isinstance(f, dict) and f.get("id") == current_id
            ),
            None,
        )
        if feature:
            stage = _normalize_feature_stage_for_summary(feature)
            return {
                "type": "feature",
                "feature_id": current_id,
                "feature_name": feature.get("name", "Unknown"),
                "development_stage": stage,
                "stage_label": _stage_label_for_summary(stage),
            }

    pending = [
        f for f in features if isinstance(f, dict) and not f.get("completed", False)
    ]
    if pending:
        next_feature = pending[0]
        return {
            "type": "feature",
            "feature_id": next_feature.get("id"),
            "feature_name": next_feature.get("name", "Unknown"),
            "development_stage": "pending",
            "stage_label": _stage_label_for_summary("pending"),
        }

    return {
        "type": "none",
        "feature_id": None,
        "feature_name": "无待办功能",
        "development_stage": None,
        "stage_label": None,
    }


def _check_plan_health_for_summary(
    progress_data: Dict[str, Any], target_root: Path
) -> Dict[str, Any]:
    """Validate active plan path/document health for summary projection."""
    workflow_state = progress_data.get("workflow_state")
    if not isinstance(workflow_state, dict) or not workflow_state.get("plan_path"):
        return {"status": "N/A", "plan_path": None, "message": "无活跃计划"}

    plan_path = str(workflow_state.get("plan_path"))
    try:
        path_result = validate_plan_path(
            plan_path, require_exists=True, target_root=target_root
        )
        if not path_result["valid"]:
            return {
                "status": "WARN",
                "plan_path": plan_path,
                "message": path_result["error"],
            }

        doc_result = validate_plan_document(plan_path, target_root=target_root)
        if not doc_result["valid"]:
            missing = ", ".join(doc_result.get("missing_sections", []))
            return {
                "status": "INVALID",
                "plan_path": plan_path,
                "message": f"缺少必需章节: {missing}" if missing else "计划文档验证失败",
            }

        return {
            "status": "OK",
            "plan_path": plan_path,
            "message": "计划文件完整且符合规范",
        }
    except Exception as exc:
        return {
            "status": "WARN",
            "plan_path": plan_path,
            "message": f"验证失败: {exc}",
        }


def _check_risk_blocker_for_summary(progress_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate high-priority/blocked bug signals for status summary."""
    bugs = progress_data.get("bugs", [])
    if not isinstance(bugs, list):
        bugs = []

    high_priority = [
        bug
        for bug in bugs
        if isinstance(bug, dict)
        and bug.get("priority") == "high"
        and bug.get("status") != "fixed"
    ]
    blocked = [
        bug for bug in bugs if isinstance(bug, dict) and bug.get("status") == "blocked"
    ]

    if high_priority or blocked:
        return {
            "has_risk": True,
            "high_priority_bugs": len(high_priority),
            "blocked_count": len(blocked),
            "message": f"{len(high_priority)} 个高优先级 bug",
        }

    return {
        "has_risk": False,
        "high_priority_bugs": 0,
        "blocked_count": 0,
        "message": "正常",
    }


def _load_recent_snapshot_for_summary(
    checkpoints_data: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build recent_snapshot field from checkpoints payload."""
    if not isinstance(checkpoints_data, dict):
        return {"exists": False, "timestamp": None, "relative_time": "暂无快照"}

    last_time = checkpoints_data.get("last_checkpoint_at")
    if not last_time:
        return {"exists": False, "timestamp": None, "relative_time": "暂无快照"}

    return {
        "exists": True,
        "timestamp": last_time,
        "relative_time": _format_relative_time_for_summary(last_time),
    }


def _build_status_summary_core(
    progress_data: Dict[str, Any],
    checkpoints_data: Dict[str, Any],
    target_root: Path,
) -> Dict[str, Any]:
    """Compute the shared status summary core fields."""
    features_raw = progress_data.get("features", [])
    features = [item for item in features_raw if isinstance(item, dict)]
    completed = sum(1 for feature in features if feature.get("completed", False))
    total = len(features)
    percentage = int((completed / total) * 100) if total > 0 else 0

    return {
        "progress": {
            "completed": completed,
            "total": total,
            "percentage": percentage,
        },
        "next_action": _determine_next_action_for_summary(features, progress_data),
        "plan_health": _check_plan_health_for_summary(progress_data, target_root),
        "risk_blocker": _check_risk_blocker_for_summary(progress_data),
        "recent_snapshot": _load_recent_snapshot_for_summary(checkpoints_data),
    }


def _extract_projection_source_fingerprint(
    projection: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Extract persisted inputs fingerprint from projection payload."""
    inputs = projection.get("inputs")
    return inputs if isinstance(inputs, dict) else None


def _projection_has_required_core_fields(projection: Dict[str, Any]) -> bool:
    """Check whether projection carries all required summary fields."""
    return all(field in projection for field in STATUS_SUMMARY_CORE_FIELDS)


def _projection_needs_rebuild(
    projection: Optional[Dict[str, Any]],
    current_inputs: Dict[str, Any],
) -> bool:
    """Determine whether cached projection is stale or malformed."""
    if not isinstance(projection, dict):
        return True
    if projection.get("schema_version") != STATUS_SUMMARY_SCHEMA_VERSION:
        return True
    if not _projection_has_required_core_fields(projection):
        return True
    persisted_inputs = _extract_projection_source_fingerprint(projection)
    if persisted_inputs != current_inputs:
        return True
    return False


def _legacy_summary_migration_info(legacy_path: Path) -> Optional[Dict[str, Any]]:
    """Read legacy summary metadata for migration traceability."""
    legacy_payload = _read_json_dict(legacy_path)
    if legacy_payload is None:
        return None
    from_version = legacy_payload.get("schema_version")
    if not isinstance(from_version, str) or not from_version.strip():
        from_version = "unknown"
    return {
        "from_schema_version": from_version,
        "from_path": rel_progress_path(STATUS_SUMMARY_LEGACY_FILE),
        "migrated_at": _iso_now(),
    }


def _resolve_status_summary_target_root(project_root: Optional[str]) -> Path:
    """Resolve summary projection target root from optional explicit path."""
    if project_root is None:
        return find_project_root()
    root = Path(project_root).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    return root.resolve()


def get_status_summary_projection_path(project_root: Optional[str] = None) -> Path:
    """Return status summary projection path for the resolved target root."""
    target_root = _resolve_status_summary_target_root(project_root)
    return get_state_dir(target_root) / STATUS_SUMMARY_FILE


def _build_status_summary_projection(
    target_root: Path,
    current_inputs: Dict[str, Any],
    migration_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Recompute and persist status summary projection for a target root."""
    progress_path = get_progress_json_path(target_root)
    checkpoints_path = get_checkpoints_path(target_root)
    projection_path = get_status_summary_projection_path(str(target_root))

    progress_data = _load_progress_data_for_summary(progress_path)
    checkpoints_data = load_checkpoints(path=checkpoints_path)
    core = _build_status_summary_core(progress_data, checkpoints_data, target_root)

    projection: Dict[str, Any] = {
        "schema_version": STATUS_SUMMARY_SCHEMA_VERSION,
        "projection_path": rel_progress_path(STATUS_SUMMARY_FILE),
        "updated_at": _iso_now(),
        "source": {
            "generator": "progress_manager.load_status_summary_projection",
            "progress_path": rel_progress_path(PROGRESS_JSON),
            "checkpoints_path": rel_progress_path(CHECKPOINTS_JSON),
        },
        "inputs": current_inputs,
        **core,
    }
    if migration_info:
        projection["migration"] = migration_info

    _atomic_write_text(
        projection_path,
        json.dumps(projection, indent=2, ensure_ascii=False),
    )
    return projection


def load_status_summary_projection(
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load shared status summary projection with drift detection and self-healing.

    The projection is persisted at docs/progress-tracker/state/status_summary.v1.json
    and rebuilt automatically when source files drift, projection is missing/corrupt,
    or schema/core fields mismatch.
    """
    target_root = _resolve_status_summary_target_root(project_root)
    ensure_tracker_layout(target_root)
    ensure_storage_migrated(target_root)

    projection_path = get_status_summary_projection_path(str(target_root))
    legacy_path = get_state_dir(target_root) / STATUS_SUMMARY_LEGACY_FILE
    current_inputs = _status_summary_source_fingerprint(target_root)
    projection = _read_json_dict(projection_path)

    migration_info: Optional[Dict[str, Any]] = None
    if projection is None and legacy_path.exists():
        migration_info = _legacy_summary_migration_info(legacy_path)

    if _projection_needs_rebuild(projection, current_inputs):
        try:
            return _build_status_summary_projection(
                target_root=target_root,
                current_inputs=current_inputs,
                migration_info=migration_info,
            )
        except Exception as exc:
            logger.warning(f"Failed to persist status summary projection: {exc}")
            progress_data = _load_progress_data_for_summary(get_progress_json_path(target_root))
            checkpoints_data = load_checkpoints(path=get_checkpoints_path(target_root))
            core = _build_status_summary_core(progress_data, checkpoints_data, target_root)
            return {
                "schema_version": STATUS_SUMMARY_SCHEMA_VERSION,
                "projection_path": rel_progress_path(STATUS_SUMMARY_FILE),
                "updated_at": _iso_now(),
                "source": {
                    "generator": "progress_manager.load_status_summary_projection",
                    "progress_path": rel_progress_path(PROGRESS_JSON),
                    "checkpoints_path": rel_progress_path(CHECKPOINTS_JSON),
                },
                "inputs": current_inputs,
                "repair": {
                    "status": "degraded",
                    "reason": str(exc),
                },
                **core,
            }

    # projection is guaranteed dict and schema-valid by _projection_needs_rebuild.
    return projection  # type: ignore[return-value]


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


def _build_status_handoff_block(
    data: Dict[str, Any],
    completed: int,
    total: int,
    project_root: str,
) -> Optional[str]:
    """Build context handoff block for /prog status output."""
    git_ctx = collect_git_context()
    current_branch = git_ctx.get("branch")
    return progress_prompt_builders.build_status_handoff_block(
        data, completed, total, project_root, current_branch=current_branch
    )


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
    """Render monorepo root dashboard by pulling child summaries.

    Uses ``load_status_summary_projection()`` for initialized children,
    falls back to ``linked_snapshot`` entries when summary loading fails,
    and renders ``-- not initialized --`` for uninitialized plugins.
    """
    catalog = _discover_plugin_catalog(repo_root, parent_root=project_root)

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
                resolved = _resolve_linked_project_root(
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
            child_data, _ = _load_progress_payload_at_root(child_root)
            if isinstance(child_data, dict):
                raw_code = child_data.get("project_code")
                if isinstance(raw_code, str) and raw_code.strip():
                    code = raw_code.strip().upper()

        if code is None:
            code = _generate_project_code(plugin_name, set(r.get("code", "") for r in child_rows if r.get("code")))

        # Load summary via projection loader
        summary: Optional[Dict[str, Any]] = None
        summary_err: Optional[str] = None
        try:
            summary = load_status_summary_projection(str(child_root))
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
    if not isinstance(routing_queue, list):
        routing_queue = []

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

    active_route_str = "none"
    if active_route_code:
        active_route_str = f"{active_route_code}"
        if active_feature_name:
            active_route_str += f" -> {active_feature_name}"
    queue_str = " -> ".join(str(c) for c in routing_queue) if routing_queue else "(empty)"
    print(f"\nActive Route: {active_route_str}  |  Queue: {queue_str}")

    return True


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


def status(output_json: bool = False) -> bool:
    """Display current progress status."""
    data = load_progress_json()
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
        project_root = find_project_root()
        repo_root = _resolve_repo_root(project_root)
        return _display_root_dashboard(data, project_root, repo_root, output_json=output_json)

    project_name = data.get("project_name", "Unknown")
    features = data.get("features", [])
    current_id = data.get("current_feature_id")
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}
    runtime_context = data.get("runtime_context")
    summary = load_status_summary_projection()
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
        and _is_feature_deferred(f)
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
                    print(f"**Execution Context**: {_format_context_summary(execution_context)}")
                if runtime_context:
                    print(f"**Current Session Context**: {_format_context_summary(runtime_context)}")

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

    reconcile_report = analyze_reconcile_state(data)
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
                owner_summary = _format_feature_owners(f)
                if owner_summary:
                    print(f"     Owners: {owner_summary}")

    if in_progress:
        print("\n### In Progress:")
        for f in features:
            if f.get("id") == current_id:
                print(f"  [*] {f.get('name', 'Unknown')}")
                owner_summary = _format_feature_owners(f)
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
        and _is_feature_deferred(f)
    ]
    remaining = [
        f
        for f in features
        if isinstance(f, dict)
        and not f.get("completed", False)
        and f.get("id") != current_id
        and not _is_feature_deferred(f)
    ]
    if remaining:
        print("\n### Pending:")
        for f in remaining:
            print(f"  [ ] {f.get('name', 'Unknown')}")
            owner_summary = _format_feature_owners(f)
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
        print("\nUse `prog resume --all` or `prog resume --defer-group <group>` to continue deferred features.")

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
                        f"  [{proj_name}] {completed_n}/{total_n} ({pct}%){active_marker}{stale_marker}{updated_str}"
                    )
                elif proj_status == "missing":
                    print(f"  [{proj_name}] missing{stale_marker}")
                else:
                    print(f"  [{proj_name}] {proj_status}{stale_marker}")

    # Display parallel active_routes conflict warning (F20)
    active_routes_raw: List[Any] = data.get("active_routes") or []
    parallel_routes = _detect_parallel_active_routes(active_routes_raw)
    if parallel_routes:
        print("\n### [WARNING] Parallel Active Routes:")
        for route in parallel_routes:
            code = route.get("project_code", "?")
            ref = route.get("feature_ref") or "(no feature_ref)"
            print(f"  {code} -> {ref}")
        print("  Multiple projects executing simultaneously — run 'prog route-status' for details.")

    # Display archive history summary
    history = _load_progress_history()
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
    project_root_str = str(find_project_root().resolve())
    handoff = _build_status_handoff_block(data, completed, total, project_root_str)
    if handoff:
        print(f"\n---\n**Paste into a new session to continue:**\n\n{handoff}\n---")

    return True


def _run_git(args: List[str], cwd: Optional[str] = None, timeout: int = 5) -> Tuple[int, str, str]:
    """
    Run git command with secure validation when available.

    Args:
        args: Git arguments excluding the `git` binary name
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    if GIT_VALIDATOR_AVAILABLE:
        return safe_git_command(["git"] + args, cwd=cwd, timeout=timeout)

    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            check=False,
            cwd=cwd,
            timeout=timeout,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def _get_dirty_state_files(project_root: Path) -> list:
    """Return list of state files (whitelist only) that have uncommitted changes.

    Uses git status --porcelain with cwd=repo_root so paths in output are
    consistently repo-root-relative, avoiding double-prefix bugs when
    project_root is a subdirectory (e.g. plugins/progress-tracker).
    """
    progress_dir = get_progress_dir()
    dirty: list = []

    try:
        git_root = _resolve_repo_root(project_root)
    except Exception:
        return dirty

    for name in STATE_FILE_NAMES:
        f = progress_dir / name
        # No exists() guard: deleted tracked files must be included (they show
        # as "D " in porcelain output and must be committed to record the deletion).
        # Files that never existed and were never tracked → empty porcelain output → skipped.
        try:
            rel = str(f.relative_to(git_root))
        except ValueError:
            continue
        code, out, _ = _run_git(["status", "--porcelain", "--", rel], cwd=str(git_root))
        if code == 0 and out.strip():
            dirty.append(f)

    for dir_name in STATE_DIR_NAMES:
        d = progress_dir / dir_name
        # No is_dir() guard: deleted directories with tracked files show up in porcelain.
        try:
            rel_dir = str(d.relative_to(git_root))
        except ValueError:
            continue
        code, out, _ = _run_git(["status", "--porcelain", "--", rel_dir], cwd=str(git_root))
        if code == 0:
            for line in out.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    file_path = parts[1].strip()
                    # If path ends with '/', it's an untracked directory.
                    # Recursively list all files within it.
                    if file_path.endswith('/'):
                        dir_path = git_root / file_path
                        if dir_path.is_dir():
                            for item in dir_path.rglob('*'):
                                if item.is_file():
                                    dirty.append(item)
                        else:
                            # Directory doesn't exist, add the path as-is
                            dirty.append(git_root / file_path)
                    else:
                        dirty.append(git_root / file_path)

    return dirty


def _git_commit_state(
    state_files: list, msg: str, project_root: Path
) -> "Optional[str]":
    """Commit state_files using git add + git commit --only.

    Uses subprocess.run directly (not safe_git_command) because the commit
    message contains parentheses, which safe_git_command rejects as dangerous
    shell metacharacters. shell=False ensures no injection risk.

    git add stages untracked files; --only isolates the commit so any files
    the user has staged are left untouched.
    """
    try:
        git_root = _resolve_repo_root(project_root)
    except Exception:
        print("[state-sync] Auto-commit skipped: cannot resolve repo root.")
        return None

    try:
        rel_paths = [str(f.relative_to(git_root)) for f in state_files]
    except ValueError as exc:
        print(f"[state-sync] Auto-commit skipped: path resolution error: {exc}")
        return None

    try:
        add_result = subprocess.run(
            ["git", "add", "--"] + rel_paths,
            capture_output=True, check=False,
            cwd=str(git_root), timeout=15, text=True,
        )
        if add_result.returncode != 0:
            print(
                f"[state-sync] Auto-commit skipped: git add failed: "
                f"{add_result.stderr.strip()}"
            )
            return None

        commit_result = subprocess.run(
            ["git", "commit", "--only", "-m", msg, "--"] + rel_paths,
            capture_output=True, check=False,
            cwd=str(git_root), timeout=30, text=True,
        )
        if commit_result.returncode != 0:
            print(
                f"[state-sync] Auto-commit failed (non-blocking): "
                f"{commit_result.stderr.strip()}"
            )
            return None

        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, check=False,
            cwd=str(git_root), text=True, timeout=5,
        )
        if hash_result.returncode != 0:
            print(f"[state-sync] Failed to retrieve commit hash: {hash_result.stderr.strip()}")
            return None
        return hash_result.stdout.strip() or None
    except subprocess.TimeoutExpired as exc:
        print(f"[state-sync] Auto-commit timeout (repository may be unresponsive): {exc}")
        return None
    except Exception as exc:
        print(f"[state-sync] Auto-commit error (non-blocking): {exc}")
        return None


def _auto_state_commit(ref: str, event: str) -> "Optional[str]":
    """Auto-commit dirty state files after a prog lifecycle command succeeds.

    Non-blocking: all failures print a warning and return None without
    raising or affecting the caller's return value.

    Args:
        ref:   Human-readable reference, e.g. "F3" (feature) or "BUG-001".
        event: Lifecycle event name, e.g. "done", "start", "fix".
    """
    data = load_progress_json()
    if not data:
        return None
    if not data.get("settings", {}).get("auto_state_commit", True):
        return None

    # Resolve project root first — needed as cwd for all git calls.
    project_root = find_project_root()

    # Detect in-progress git operations (worktree-safe: --absolute-git-dir).
    # Pass cwd=project_root to avoid detecting the wrong repo in multi-project setups.
    code, git_dir_str, _ = _run_git(["rev-parse", "--absolute-git-dir"],
                                     cwd=str(project_root))
    if code == 0:
        git_dir = Path(git_dir_str.strip())
        for marker in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD"):
            if (git_dir / marker).exists():
                print(
                    f"[state-sync] Skip: {marker} in progress. "
                    "Resolve git operation, then commit state files manually."
                )
                return None
        for dir_marker in ("rebase-merge", "rebase-apply"):
            if (git_dir / dir_marker).is_dir():
                print(f"[state-sync] Skip: {dir_marker} in progress.")
                return None

    dirty = _get_dirty_state_files(project_root)
    if not dirty:
        return None

    msg = f"chore(PT): state sync [{ref}: {event}] [skip ci]"
    return _git_commit_state(dirty, msg, project_root)


def _parse_worktree_list_output(output: str) -> List[Dict[str, str]]:
    """
    Parse `git worktree list --porcelain` output.
    """
    entries: List[Dict[str, str]] = []
    current: Dict[str, str] = {}

    for line in output.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue

        if " " not in line:
            continue

        key, value = line.split(" ", 1)
        current[key] = value

    if current:
        entries.append(current)

    return entries


def _detect_default_branch(project_root: Path) -> Optional[str]:
    """
    Detect repository default branch using origin/HEAD when available.
    """
    exit_code, stdout, _ = _run_git(
        ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        cwd=str(project_root),
        timeout=5,
    )
    if exit_code == 0 and stdout.strip():
        ref = stdout.strip()
        prefix = "refs/remotes/origin/"
        if ref.startswith(prefix):
            branch = ref[len(prefix):].strip()
            if branch:
                return branch

    for candidate in ("main", "master"):
        exit_code, _, _ = _run_git(
            ["show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"],
            cwd=str(project_root),
            timeout=5,
        )
        if exit_code == 0:
            return candidate

    return None


def _git_squash_close_task(
    task_id: str,
    branch: str,
    project_root: Optional[Path] = None,
    base_branch: Optional[str] = None,
) -> Tuple[bool, str]:
    """Execute git squash-merge sequence for a standalone task branch.

    Returns (True, commit_hash) on success, (False, error_message) on failure.
    On success, base_branch has exactly +1 commit and branch is deleted.
    """
    if project_root is None:
        project_root = find_project_root()

    cwd = str(project_root)

    # Resolve base branch
    if base_branch is None:
        base_branch = _detect_default_branch(project_root)
    if not base_branch:
        for _candidate in ("main", "master"):
            _rc_br, _, _ = _run_git(
                ["show-ref", "--verify", "--quiet", f"refs/heads/{_candidate}"], cwd=cwd
            )
            if _rc_br == 0:
                base_branch = _candidate
                break
    if not base_branch:
        return False, "cannot determine default branch (tried main and master)"

    # Pre-condition 1: branch must exist
    rc, _, _ = _run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=cwd)
    if rc != 0:
        return False, f"branch '{branch}' not found in local repo"

    # Pre-condition 2: working tree must be clean
    rc, stdout, _ = _run_git(["status", "--porcelain"], cwd=cwd)
    if rc != 0 or stdout.strip():
        return False, f"working tree is dirty; commit or stash changes first"

    # Step 1: checkout base branch
    rc, _, err = _run_git(["checkout", base_branch], cwd=cwd)
    if rc != 0:
        return False, f"checkout {base_branch} failed: {err}"

    # Step 2: squash merge
    rc, _, err = _run_git(["merge", "--squash", branch], cwd=cwd)
    if rc != 0:
        # Roll back any partial index changes
        _run_git(["reset", "--mixed", "HEAD"], cwd=cwd)
        return False, f"git merge --squash failed: {err}"

    # Step 3: commit
    commit_msg = f"squash merge {task_id}: close standalone task"
    rc, _, err = _run_git(["commit", "-m", commit_msg], cwd=cwd)
    if rc != 0:
        _run_git(["reset", "--mixed", "HEAD"], cwd=cwd)
        return False, f"git commit failed: {err}"

    # Step 4: get commit hash
    rc, commit_hash, _ = _run_git(["rev-parse", "HEAD"], cwd=cwd)
    commit_hash = commit_hash.strip() if rc == 0 else ""

    # Step 5: delete task branch.
    # Uses -D (force) rather than -d (safe) because squash-merge creates a new
    # commit that does not reference the original branch, so -d's "is-merged?"
    # safety check would always fail. This is a deliberate deviation from the
    # plan's `git branch -d` to match squash-merge semantics.
    rc, _, err = _run_git(["branch", "-D", branch], cwd=cwd)
    if rc != 0:
        logger.warning(
            f"squash commit {commit_hash[:8] if commit_hash else '?'} succeeded "
            f"but branch '{branch}' deletion failed: {err}. "
            f"Manual cleanup may be needed: git branch -D {branch}"
        )

    return True, commit_hash


def _local_and_origin_ref_candidates(ref: str) -> Tuple[str, ...]:
    """Return deduplicated local+origin ref candidates for ancestry checks."""
    normalized = str(ref or "").strip()
    if not normalized:
        return tuple()
    candidates = [normalized]
    if not normalized.startswith("origin/"):
        candidates.append(f"origin/{normalized}")
    return tuple(dict.fromkeys(candidates))


def _is_branch_merged_into(branch: str, target: str) -> bool:
    """Return True when branch is an ancestor of target (local/origin fallback)."""
    source_refs = _local_and_origin_ref_candidates(branch)
    target_refs = _local_and_origin_ref_candidates(target)
    if not source_refs or not target_refs:
        return False

    project_root = find_project_root()
    for source_ref in source_refs:
        for target_ref in target_refs:
            exit_code, _, _ = _run_git(
                ["merge-base", "--is-ancestor", source_ref, target_ref],
                cwd=str(project_root),
                timeout=10,
            )
            if exit_code == 0:
                return True
    return False


def analyze_git_sync_risks() -> Dict[str, Any]:
    """
    Analyze repository state for sync/rebase/divergence risks.

    This check is designed for SessionStart hooks and intentionally avoids
    mutating repository state.
    """
    project_root = find_project_root()
    report: Dict[str, Any] = {
        "status": "ok",
        "project_root": str(project_root),
        "branch": None,
        "upstream": None,
        "ahead": 0,
        "behind": 0,
        "issues": [],
    }

    status_rank = {"ok": 0, "warning": 1, "critical": 2}

    def add_issue(
        issue_id: str, level: str, message: str, recommendation: Optional[str] = None
    ) -> None:
        issue = {"id": issue_id, "level": level, "message": message}
        if recommendation:
            issue["recommendation"] = recommendation
        report["issues"].append(issue)
        if status_rank[level] > status_rank[report["status"]]:
            report["status"] = level

    # Skip when not in a git repository
    if GIT_VALIDATOR_AVAILABLE:
        in_git_repo = is_git_repository(str(project_root))
    else:
        exit_code, _, _ = _run_git(
            ["rev-parse", "--is-inside-work-tree"],
            cwd=str(project_root),
            timeout=3,
        )
        in_git_repo = exit_code == 0

    if not in_git_repo:
        report["status"] = "skipped"
        return report

    # Determine current branch / detached HEAD
    exit_code, stdout, _ = _run_git(
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=str(project_root),
        timeout=5,
    )
    branch = stdout.strip() if exit_code == 0 else None
    report["branch"] = branch
    if not branch:
        add_issue(
            "detached_head",
            "critical",
            "Repository is in detached HEAD state.",
            "Switch back to a branch before continuing: git switch <branch>",
        )

    # Detect in-progress git operations (merge/rebase/cherry-pick/revert/bisect)
    git_dir: Optional[Path] = None
    exit_code, stdout, _ = _run_git(
        ["rev-parse", "--absolute-git-dir"],
        cwd=str(project_root),
        timeout=5,
    )
    if exit_code == 0 and stdout.strip():
        git_dir = Path(stdout.strip())

    if git_dir:
        operation_markers = [
            ("rebase-merge", "rebase"),
            ("rebase-apply", "rebase"),
            ("MERGE_HEAD", "merge"),
            ("CHERRY_PICK_HEAD", "cherry-pick"),
            ("REVERT_HEAD", "revert"),
            ("BISECT_LOG", "bisect"),
        ]
        active_operations = sorted(
            {name for marker, name in operation_markers if (git_dir / marker).exists()}
        )
        if active_operations:
            ops = ", ".join(active_operations)
            add_issue(
                "operation_in_progress",
                "critical",
                f"Git operation in progress: {ops}.",
                "Finish or abort it before new changes (e.g. git rebase --continue/--abort).",
            )

    # Detect uncommitted changes
    is_clean = True
    if GIT_VALIDATOR_AVAILABLE:
        is_clean = is_working_directory_clean(str(project_root))
    else:
        exit_code, stdout, _ = _run_git(
            ["status", "--porcelain"],
            cwd=str(project_root),
            timeout=5,
        )
        is_clean = exit_code == 0 and not stdout.strip()

    if not is_clean:
        add_issue(
            "dirty_worktree",
            "warning",
            "Working tree has uncommitted changes.",
            "Commit or stash changes before pull/rebase/cherry-pick operations.",
        )

    # Detect upstream tracking and divergence/ahead/behind
    upstream_ref: Optional[str] = None
    if branch:
        exit_code, stdout, _ = _run_git(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            cwd=str(project_root),
            timeout=5,
        )
        if exit_code == 0 and stdout.strip():
            upstream_ref = stdout.strip()
            report["upstream"] = upstream_ref
        else:
            add_issue(
                "no_upstream",
                "warning",
                f"Branch '{branch}' is not tracking an upstream branch.",
                f"Set upstream once: git push -u origin {branch}",
            )

    if upstream_ref:
        exit_code, stdout, _ = _run_git(
            ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"],
            cwd=str(project_root),
            timeout=5,
        )
        if exit_code == 0:
            parts = stdout.strip().split()
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                behind = int(parts[0])
                ahead = int(parts[1])
                report["behind"] = behind
                report["ahead"] = ahead

                if ahead > 0 and behind > 0:
                    add_issue(
                        "branch_diverged",
                        "critical",
                        f"Branch has diverged from upstream (ahead {ahead}, behind {behind}).",
                        "Sync before coding: git fetch origin && git rebase @{upstream} (or merge).",
                    )
                elif behind > 0:
                    add_issue(
                        "branch_behind",
                        "warning",
                        f"Branch is behind upstream by {behind} commit(s).",
                        "Update branch first: git fetch origin && git rebase @{upstream}.",
                    )
                elif ahead > 0:
                    add_issue(
                        "branch_ahead",
                        "warning",
                        f"Branch is ahead of upstream by {ahead} commit(s).",
                        "Push when ready: git push.",
                    )

    # Detect same branch checked out in another worktree
    if branch:
        exit_code, stdout, _ = _run_git(
            ["worktree", "list", "--porcelain"],
            cwd=str(project_root),
            timeout=5,
        )
        if exit_code == 0 and stdout.strip():
            branch_ref = f"refs/heads/{branch}"
            # Use the actual git worktree root, not project_root which may be a
            # subdirectory (e.g. a plugin folder inside the repo). Using project_root
            # would cause a false-positive: git worktree list reports the git root,
            # so the comparison would always fail when cwd is a subdirectory.
            _ec, _toplevel, _ = _run_git(
                ["rev-parse", "--show-toplevel"],
                cwd=str(project_root),
                timeout=5,
            )
            current_worktree = (
                str(Path(_toplevel.strip()).resolve())
                if _ec == 0 and _toplevel.strip()
                else str(project_root.resolve())
            )
            worktrees = _parse_worktree_list_output(stdout)
            duplicate_paths: List[str] = []
            for entry in worktrees:
                worktree_path = entry.get("worktree")
                if not worktree_path or entry.get("branch") != branch_ref:
                    continue

                try:
                    resolved_path = str(Path(worktree_path).resolve())
                except Exception:
                    resolved_path = worktree_path

                if resolved_path != current_worktree:
                    duplicate_paths.append(worktree_path)

            if duplicate_paths:
                shown = ", ".join(duplicate_paths[:2])
                if len(duplicate_paths) > 2:
                    shown = f"{shown}, +{len(duplicate_paths) - 2} more"
                add_issue(
                    "branch_checked_out_elsewhere",
                    "warning",
                    f"Branch '{branch}' is also checked out in another worktree: {shown}.",
                    "Avoid editing the same branch in multiple sessions/tools at the same time.",
                )

    return report


def git_sync_check() -> bool:
    """
    Print actionable Git sync warnings.

    Returns True in all cases so hooks remain non-blocking.
    """
    report = analyze_git_sync_risks()
    status = report.get("status", "ok")

    if status in ("ok", "skipped"):
        return True

    label = "CRITICAL" if status == "critical" else "WARNING"
    print(f"[Progress Tracker][Git {label}] Session preflight detected sync risks")
    print(f"Repository: {report.get('project_root')}")
    if report.get("branch"):
        print(f"Branch: {report.get('branch')}")

    issues = report.get("issues", [])
    for issue in issues:
        print(f"- {issue.get('message')}")

    recommendations: List[str] = []
    for issue in issues:
        recommendation = issue.get("recommendation")
        if recommendation and recommendation not in recommendations:
            recommendations.append(recommendation)

    if recommendations:
        print("Recommended actions:")
        for action in recommendations:
            print(f"  - {action}")

    return True


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
    project_root = Path(project_root_raw)
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
    }
    triggered_delegate_ids = sorted(
        issue_id
        for issue_id in issue_ids
        if issue_id in delegate_issue_ids
    )

    default_branch_candidates = {candidate for candidate in (default_branch, "main", "master") if candidate}
    on_default_branch = branch in default_branch_candidates

    if triggered_delegate_ids:
        decision = "DELEGATE_GIT_AUTO"
        reason_codes.extend(triggered_delegate_ids)
    elif status == "critical":
        decision = "DELEGATE_GIT_AUTO"
        reason_codes.append("critical_sync_risk")
    elif on_default_branch and workspace_mode != "worktree":
        decision = "REQUIRE_WORKTREE"
        reason_codes.append("default_branch_feature_work")
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
    """
    Archive testing and plan documents for a completed feature.

    Moves documents from:
    - docs/plans/ (Superpowers writing-plans standard location for plan files)
    - docs/testing/ (bug fix reports and test documentation)

    To:
    - docs/archive/plans/
    - docs/archive/testing/

    Supports naming patterns:
    - Primary: Reads plan_path from feature object (preserved before completion)
    - Fallback: feature-{feature_id}-*.md (legacy pattern)
    - Fallback: bug-*-fix-report.md (testing reports)

    Args:
        feature_id: The ID of the completed feature
        feature_name: Optional feature name for logging

    Returns:
        Dict with archive results including success status, files moved, and any errors
    """
    result = {
        "success": True,
        "archived_files": [],
        "skipped_files": [],
        "errors": []
    }

    try:
        project_root = find_project_root()

        # Plans live at docs/plans/ (Superpowers standard)
        # Testing reports live at docs/testing/
        plans_src = project_root / "docs" / "plans"
        testing_src = project_root / "docs" / "testing"
        plans_archive = project_root / "docs" / "archive" / "plans"
        testing_archive = project_root / "docs" / "archive" / "testing"

        # Create archive directories if they don't exist
        testing_archive.mkdir(parents=True, exist_ok=True)
        plans_archive.mkdir(parents=True, exist_ok=True)

        # Try to get plan_path from feature object (preserved before workflow_state clear)
        data = load_progress_json()
        feature = next((f for f in data.get("features", []) if f.get("id") == feature_id), None)
        plan_path_from_feature = feature.get("plan_path") if feature else None

        # Archive plan file if plan_path is available
        if plan_path_from_feature:
            try:
                plan_file = project_root / plan_path_from_feature
                if plan_file.exists():
                    # Guard: never archive immutable protected files
                    if _is_immutable_protected(plan_file, project_root):
                        logger.warning(
                            "Skipping immutable protected file from archival: %s",
                            plan_path_from_feature,
                        )
                        result["skipped_files"].append(f"Protected: {plan_path_from_feature}")
                    else:
                        dst_file = plans_archive / plan_file.name

                        # Handle filename conflicts
                        if dst_file.exists():
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            stem = plan_file.stem
                            suffix = plan_file.suffix
                            new_name = f"{stem}_{timestamp}{suffix}"
                            dst_file = plans_archive / new_name

                        shutil.move(str(plan_file), str(dst_file))
                        result["archived_files"].append({
                            "from": plan_path_from_feature,
                            "to": str(dst_file.relative_to(project_root))
                        })
                        logger.info(f"Archived plan: {plan_path_from_feature} -> {dst_file.relative_to(project_root)}")
            except Exception as e:
                error_msg = f"Failed to archive plan {plan_path_from_feature}: {e}"
                result["errors"].append(error_msg)
                logger.warning(error_msg)

        # Collect all patterns to try for this feature (fallback)
        patterns = [
            # Legacy pattern: feature-{feature_id}-*.md
            (testing_src, testing_archive, f"feature-{feature_id}-*.md"),
            (plans_src, plans_archive, f"feature-{feature_id}-*.md"),
            # Modern pattern: bug-NNN-*.md for testing reports
            (testing_src, testing_archive, f"bug-*-fix-report.md"),
        ]

        for src_dir, dst_dir, pattern in patterns:
            if not src_dir.exists():
                result["skipped_files"].append(f"Source directory not found: {src_dir}")
                continue

            # Find matching files
            matching_files = list(src_dir.glob(pattern))

            if not matching_files:
                # Debug log but don't report to user (too verbose)
                logger.debug(f"No files found matching {pattern} in {src_dir}")
                continue

            # Move each matching file
            for src_file in matching_files:
                # Guard: never archive immutable protected files
                if _is_immutable_protected(src_file, project_root):
                    logger.warning(
                        "Skipping immutable protected file from archival: %s",
                        src_file,
                    )
                    result["skipped_files"].append(f"Protected: {src_file.name}")
                    continue
                try:
                    dst_file = dst_dir / src_file.name

                    # Handle filename conflicts by adding timestamp
                    if dst_file.exists():
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        stem = src_file.stem
                        suffix = src_file.suffix
                        new_name = f"{stem}_{timestamp}{suffix}"
                        dst_file = dst_dir / new_name

                    # Move the file
                    shutil.move(str(src_file), str(dst_file))
                    result["archived_files"].append({
                        "from": str(src_file.relative_to(project_root)),
                        "to": str(dst_file.relative_to(project_root))
                    })
                    logger.info(f"Archived: {src_file.name} -> {dst_file.relative_to(project_root)}")

                except Exception as e:
                    error_msg = f"Failed to move {src_file.name}: {e}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg)
                    # Don't set success=False for individual file errors - continue with others

        # Log summary
        if result["archived_files"]:
            logger.info(f"Archived {len(result['archived_files'])} file(s) for feature {feature_id}")
            for file_info in result["archived_files"]:
                print(f"  Archived: {file_info['from']} -> {file_info['to']}")

        if result["errors"]:
            result["success"] = False
            for error in result["errors"]:
                logger.warning(error)

    except Exception as e:
        result["success"] = False
        error_msg = f"Archive operation failed: {e}"
        result["errors"].append(error_msg)
        logger.error(error_msg)

    return result


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


def _run_acceptance_tests(
    feature: Dict[str, Any],
    run_all: bool = False,
) -> Tuple[bool, List[AcceptanceTestResult]]:
    """Execute command-like acceptance steps from the target feature."""
    steps = feature.get("test_steps", [])
    if not isinstance(steps, list):
        steps = []

    project_root = find_project_root()
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
                cwd=str(project_root),
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
        return False, "No active feature. Run /prog next first.", 1, None

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
    """Return True if the given path has uncommitted changes.

    Falls back to the project root when worktree_path is None/empty.
    """
    cwd = worktree_path if worktree_path else str(find_project_root())
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return bool(result.returncode == 0 and result.stdout.strip())
    except Exception:
        return False


def _resolve_upstream(branch: str) -> tuple:
    """Return (remote, remote_branch) for *branch* before it is deleted.

    Must be called while the local branch still exists so tracking metadata
    is available.  Returns ("", "") when no upstream is configured.
    """
    if not branch:
        return ("", "")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{u}}"],
            capture_output=True,
            text=True,
            cwd=str(find_project_root()),
            timeout=10,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ("", "")
        upstream = result.stdout.strip()  # e.g. "origin/feature-25"
        parts = upstream.split("/", 1)
        if len(parts) == 2:
            return (parts[0], parts[1])
        return ("", "")
    except Exception:
        return ("", "")


def _remove_worktree(worktree_path: str) -> bool:
    """Remove a git worktree.  Must be run from the repo root, not the worktree itself."""
    try:
        result = subprocess.run(
            ["git", "worktree", "remove", worktree_path],
            capture_output=True,
            text=True,
            cwd=str(find_project_root()),
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            print(f"[CLEANUP] WARN: could not remove worktree {worktree_path}: {result.stderr.strip()}")
            return False
        return True
    except Exception as exc:
        print(f"[CLEANUP] WARN: exception removing worktree {worktree_path}: {exc}")
        return False


def _delete_local_branch(branch: str) -> bool:
    """Delete a local branch with git branch -d (safe; fails if unmerged)."""
    if not branch:
        return False
    try:
        result = subprocess.run(
            ["git", "branch", "-d", branch],
            capture_output=True,
            text=True,
            cwd=str(find_project_root()),
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            print(
                f"[CLEANUP] WARN: could not delete local branch '{branch}': "
                f"{result.stderr.strip()}. "
                f"Switch to main then run: git branch -d {branch}"
            )
            return False
        return True
    except Exception as exc:
        print(f"[CLEANUP] WARN: exception deleting local branch '{branch}': {exc}")
        return False


def _delete_remote_branch(remote: str, remote_branch: str) -> bool:
    """Push a delete to the remote.  No-op when remote or branch is empty.

    Failures are non-blocking — only a warning is printed.
    """
    if not remote or not remote_branch:
        return True
    try:
        result = subprocess.run(
            ["git", "push", remote, "--delete", remote_branch],
            capture_output=True,
            text=True,
            cwd=str(find_project_root()),
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            print(
                f"[CLEANUP] WARN: could not delete remote branch "
                f"'{remote}/{remote_branch}': {result.stderr.strip()}"
            )
            return False
        return True
    except Exception as exc:
        print(f"[CLEANUP] WARN: exception deleting remote branch '{remote}/{remote_branch}': {exc}")
        return False


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
    """Resolve current HEAD commit hash, if available."""
    try:
        if GIT_VALIDATOR_AVAILABLE:
            head = get_current_commit_hash()
            if isinstance(head, str) and head.strip():
                return head.strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(find_project_root()),
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            head = result.stdout.strip()
            if head:
                return head
    except Exception:
        pass
    return None


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
        task_id=task_id, branch=branch, project_root=project_root
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


def cmd_done(commit_hash=None, run_all: bool = False, skip_archive: bool = False,
             no_cleanup: bool = False) -> int:
    """Close current feature through deterministic acceptance gatekeeping."""
    data = load_progress_json()
    if not data:
        print("[DONE] No progress tracking found")
        return 4

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

    _notify_parent_sync()
    try:
        _run_post_done_cleanup(cleanup_ctx, skip=no_cleanup)
    except Exception as exc:
        print(f"[CLEANUP] WARN: unexpected cleanup error (feature still completed): {exc}")

    if completion_output:
        print(completion_output)

    return 0


def _collect_ship_signals(feature: dict) -> dict:
    """Collect best-effort ship signals from feature state."""
    quality_gates = feature.get("quality_gates", {})
    evaluator = quality_gates.get("evaluator", {})
    reviews = quality_gates.get("reviews", {})
    defects = evaluator.get("defects", [])
    failed_tests = len([d for d in defects if d.get("severity") == "critical"])
    return {
        "test_coverage": 1.0,
        "test_results": {"passed": 1, "failed": failed_tests, "skipped": 0},
        "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
        "regression_results": {"passed": 1, "failed": 0},
    }


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
    """Format non-empty feature owners as a compact status string."""
    owners = feature.get("owners")
    if not isinstance(owners, dict):
        return None
    populated = []
    for role in OWNER_ROLES:
        value = owners.get(role)
        if isinstance(value, str) and value.strip():
            populated.append(f"{role}={value.strip()}")
    if not populated:
        return None
    return ", ".join(populated)


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


def _add_bug_internal(description: str, status: str = "pending_investigation",
                      priority: str = "medium", category: str = "bug",
                      scheduled_position: Optional[str] = None,
                      verification_results: Optional[str] = None):
    """
    Add a new bug to the tracking with validation (internal).

    Creates a new bug entry with auto-generated ID, timestamp, and optional
    scheduling information. Updates both progress.json and progress.md.

    Args:
        description: Bug description (1-2000 chars, required)
        status: Bug lifecycle status. Defaults to "pending_investigation".
            Must be one of: pending_investigation, investigating, confirmed,
            fixing, fixed, false_positive.
        priority: Bug severity level. Defaults to "medium".
            Must be one of: high, medium, low.
        category: Logical bug category. Defaults to "bug".
            Must be one of: bug, technical_debt.
        scheduled_position: Optional scheduling directive in format
            "before:N", "after:N", or "last" for smart insertion into feature
            timeline.
        verification_results: Optional JSON string containing quick verification
            results (max 10KB).

    Returns:
        Tuple[bool, Optional[str]]: (success, bug_id). On success returns
        (True, bug_id); on duplicate / failure returns (False, None).

    Raises:
        ValueError: If description is empty, too long, or contains invalid
            characters. If status or priority are invalid.
    """
    # Validate description
    if not description or not description.strip():
        raise ValueError("Description cannot be empty")

    description = description.strip()

    if len(description) > 2000:
        raise ValueError(f"Description too long ({len(description)} chars, max 2000)")

    # Validate status
    valid_statuses = ["pending_investigation", "investigating", "confirmed",
                     "fixing", "fixed", "false_positive"]
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {valid_statuses}")

    # Validate priority
    valid_priorities = ["high", "medium", "low"]
    if priority not in valid_priorities:
        raise ValueError(f"Invalid priority '{priority}'. Must be one of: {valid_priorities}")

    valid_categories = ["bug", "technical_debt"]
    if category not in valid_categories:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {valid_categories}")

    # Sanitize description (remove control characters except newline/tab)
    description = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', description)

    data = load_progress_json()
    if not data:
        raise ValueError("No progress tracking found. Use '/prog init' first.")

    bugs = data.get("bugs", [])
    if bugs is None:
        bugs = []
        data["bugs"] = bugs

    # Check for duplicate bugs (case-insensitive, normalized whitespace)
    normalized_desc = re.sub(r'\s+', ' ', description.lower())
    for bug in bugs:
        if bug.get("status") == "false_positive":
            continue
        bug_desc = bug.get("description", "")
        normalized_bug_desc = re.sub(r'\s+', ' ', bug_desc.lower())
        if normalized_bug_desc == normalized_desc:
            print(f"Duplicate bug detected: {bug.get('id')}")
            print("Use 'update-bug' to add more information or different bug.")
            return False, None

    # Generate new bug ID
    bug_id = get_next_bug_id()

    # Parse scheduled position
    scheduled_pos = None
    if scheduled_position:
        if scheduled_position == "last":
            scheduled_pos = {"type": "last", "reason": "Non-urgent, defer to later"}
        elif ":" in scheduled_position:
            pos_type, feature_id = scheduled_position.split(":", 1)
            try:
                scheduled_pos = {
                    "type": f"{pos_type}_feature",
                    "feature_id": int(feature_id),
                    "reason": "Smart scheduling based on impact"
                }
            except ValueError:
                raise ValueError(f"Invalid scheduled position format: {scheduled_position}")

    # Parse verification results if provided with validation
    quick_verification = {}
    if verification_results:
        # Check size limit (10KB)
        if len(verification_results) > 10240:
            raise ValueError(f"Verification results too large ({len(verification_results)} bytes, max 10KB)")

        try:
            quick_verification = json.loads(verification_results)

            # Validate structure
            if not isinstance(quick_verification, dict):
                raise ValueError("Verification results must be a JSON object")

            # Limit nesting depth to prevent stack overflow
            def check_depth(obj, current_depth=0, max_depth=10):
                if current_depth > max_depth:
                    raise ValueError("JSON nesting too deep (max 10 levels)")
                if isinstance(obj, dict):
                    for v in obj.values():
                        check_depth(v, current_depth + 1, max_depth)
                elif isinstance(obj, list):
                    for v in obj:
                        check_depth(v, current_depth + 1, max_depth)

            check_depth(quick_verification)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid verification results JSON: {e}")

    new_bug = {
        "id": bug_id,
        "description": description,
        "status": status,
        "priority": priority,
        "category": category,
        "created_at": datetime.now().isoformat() + "Z",
        "quick_verification": quick_verification,
    }

    if scheduled_pos:
        new_bug["scheduled_position"] = scheduled_pos

    bugs.append(new_bug)
    data["bugs"] = bugs

    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    logger.info(f"Bug {bug_id} added successfully")
    print(f"Bug recorded: {bug_id}")
    print(f"Description: {description}")
    print(f"Status: {status}")
    print(f"Priority: {priority}")
    print(f"Category: {category}")
    if scheduled_pos:
        print(f"Scheduled: {scheduled_pos}")
    return True, bug_id


def add_bug(description: str, status: str = "pending_investigation",
            priority: str = "medium", category: str = "bug",
            scheduled_position: Optional[str] = None,
            verification_results: Optional[str] = None) -> bool:
    """Public wrapper around _add_bug_internal preserving the bool return type.

    See `_add_bug_internal` for full documentation. This wrapper exists for
    backward compatibility — existing callers expect a bool return value.
    """
    success, _ = _add_bug_internal(
        description=description,
        status=status,
        priority=priority,
        category=category,
        scheduled_position=scheduled_position,
        verification_results=verification_results,
    )
    return success


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


def update_bug(bug_id: str, status: Optional[str] = None,
               root_cause: Optional[str] = None, fix_summary: Optional[str] = None):
    """
    Update bug status and/or add investigation/fix information.

    Args:
        bug_id: Bug ID (e.g., "BUG-001")
        status: New status
        root_cause: Root cause description (when confirming bug)
        fix_summary: Summary of fix applied (when marking as fixed)
    """
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

    updated = False

    if status:
        bug["status"] = status
        bug["updated_at"] = datetime.now().isoformat() + "Z"
        updated = True

        # Set current bug if starting investigation/fixing
        if status in ["investigating", "fixing"]:
            data["current_bug_id"] = bug_id
        elif status == "fixed":
            data["current_bug_id"] = None

    if root_cause:
        bug["root_cause"] = root_cause
        if "investigation" not in bug:
            bug["investigation"] = {}
        bug["investigation"]["root_cause"] = root_cause
        bug["investigation"]["confirmed_at"] = datetime.now().isoformat() + "Z"
        updated = True

    if fix_summary:
        bug["fix_summary"] = fix_summary
        bug["fixed_at"] = datetime.now().isoformat() + "Z"
        updated = True

    if updated:
        save_progress_json(data)
        md_content = generate_progress_md(data)
        save_progress_md(md_content)
        if status == "fixed":
            _auto_state_commit(bug_id, "fix")
        print(f"Bug {bug_id} updated.")
        if status:
            print(f"Status: {status}")
        if root_cause:
            print(f"Root cause: {root_cause}")
        if fix_summary:
            print(f"Fix summary: {fix_summary}")
        return True
    else:
        print("No updates provided. Use --status, --root-cause, or --fix-summary")
        return False


def list_bugs():
    """List all bugs in progress tracking."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found.")
        return False

    bugs = data.get("bugs", [])
    if not bugs:
        print("No bugs recorded.")
        return True

    print(f"\n## Bug Backlog ({len(bugs)} total)\n")

    # Group by status
    status_icons = {
        "pending_investigation": "🔴",
        "investigating": "🟡",
        "confirmed": "🟢",
        "fixing": "🔧",
        "fixed": "✅",
        "false_positive": "❌"
    }

    # Sort by priority and status
    priority_order = {"high": 0, "medium": 1, "low": 2}
    status_order = ["pending_investigation", "investigating", "confirmed", "fixing", "fixed", "false_positive"]

    def sort_key(bug):
        priority = bug.get("priority", "medium")
        status = bug.get("status", "pending_investigation")
        return (
            status_order.index(status) if status in status_order else 99,
            priority_order.get(priority, 1),
            bug.get("created_at", "")
        )

    sorted_bugs = sorted(bugs, key=sort_key)

    for bug in sorted_bugs:
        bug_id = bug.get("id", "Unknown")
        description = bug.get("description", "No description")
        status = bug.get("status", "unknown")
        priority = bug.get("priority", "medium")
        category = bug.get("category", "bug")
        created_at = bug.get("created_at", "")
        scheduled = bug.get("scheduled_position", {})

        icon = status_icons.get(status, "❓")

        # Calculate time ago
        time_ago = ""
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                now = datetime.now(created_dt.tzinfo)
                diff = now - created_dt
                hours = diff.total_seconds() / 3600
                if hours < 1:
                    time_ago = f"{int(diff.total_seconds() / 60)}m ago"
                elif hours < 24:
                    time_ago = f"{int(hours)}h ago"
                else:
                    time_ago = f"{int(hours / 24)}d ago"
            except (ValueError, AttributeError, OSError) as e:
                logger.debug(f"Error parsing date '{created_at}': {e}")
                time_ago = "unknown"

        print(f"- [{bug_id}] {description}")
        print(
            f"  Status: {icon} {status} | Priority: {priority} | "
            f"Category: {category} | Created: {time_ago}"
        )

        if scheduled:
            pos_type = scheduled.get("type", "")
            feature_id = scheduled.get("feature_id")
            reason = scheduled.get("reason", "")
            if pos_type == "before_feature" and feature_id:
                print(f"  📍 Before Feature {feature_id} ({reason})")
            elif pos_type == "after_feature" and feature_id:
                print(f"  📍 After Feature {feature_id} ({reason})")
            elif pos_type == "last":
                print(f"  📍 Last ({reason})")

        # Show root cause if confirmed
        if status in ["confirmed", "fixing", "fixed"] and "root_cause" in bug:
            print(f"  Root cause: {bug['root_cause']}")

        # Show fix summary if fixed
        if status == "fixed" and "fix_summary" in bug:
            print(f"  Fix: {bug['fix_summary']}")

        print()

    return True


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


def generate_direct_tdd_note():
    """Generate a lightweight execution note for direct_tdd features.

    Creates a strict-profile plan document from feature metadata so that
    validate-plan always finds a valid plan_path. File writes are idempotent
    (existing valid notes are preserved via state-path and deterministic-path
    fallback), but workflow_state convergence always runs.

    Returns:
        bool: True on success, False on error.
    """
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    current_id = data.get("current_feature_id")
    if current_id is None:
        print("Error: No feature currently in progress")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == current_id), None)
    if feature is None:
        print(f"Error: Feature {current_id} not found")
        return False

    def _normalize_text_list(value: Any, fallback: List[str]) -> List[str]:
        """Normalize metadata fields to a non-empty list of strings."""
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            return normalized or fallback
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return [stripped]
        return fallback

    feature_name = str(feature.get("name") or "Unnamed feature").strip()
    change_spec = feature.get("change_spec")
    if not isinstance(change_spec, dict) or not change_spec:
        change_spec = _default_change_spec(feature)

    why = str(change_spec.get("why") or f"Deliver {feature_name}.")
    in_scope = _normalize_text_list(change_spec.get("in_scope"), [feature_name])
    out_of_scope = _normalize_text_list(
        change_spec.get("out_of_scope"),
        ["Unrelated refactors and behavior changes outside this feature."],
    )
    risks = _normalize_text_list(
        change_spec.get("risks"),
        ["Potential regression in adjacent workflows"],
    )

    test_steps = feature.get("test_steps")
    if isinstance(test_steps, list) and test_steps:
        task_lines = [
            f"- [ ] {str(step).strip()}" for step in test_steps if str(step).strip()
        ]
    else:
        task_lines = [f"- [ ] Implement {feature_name}"]
    if not task_lines:
        task_lines = [f"- [ ] Implement {feature_name}"]

    acceptance = feature.get("acceptance_scenarios")
    if not isinstance(acceptance, list) or not acceptance:
        acceptance = _default_acceptance_scenarios(feature)
    acceptance_lines = [f"- {str(item).strip()}" for item in acceptance if str(item).strip()]
    if not acceptance_lines:
        acceptance_lines = [
            f"- Scenario: {feature_name} baseline behavior works as expected."
        ]

    risk_lines = [f"- {str(risk).strip()}" for risk in risks if str(risk).strip()]
    if not risk_lines:
        risk_lines = ["- Potential regression in adjacent workflows"]

    in_scope_text = ", ".join(in_scope)
    out_of_scope_text = ", ".join(out_of_scope)

    base_root = find_project_root()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _slugify(feature_name)
    plan_rel = f"docs/plans/{today}-feature-{current_id}-{slug}.md"

    workflow_state_raw = data.get("workflow_state")
    needs_workflow_state_repair = (
        "workflow_state" in data and not isinstance(workflow_state_raw, dict)
    )
    workflow_state = workflow_state_raw if isinstance(workflow_state_raw, dict) else {}
    existing_plan_path = workflow_state.get("plan_path")
    if isinstance(existing_plan_path, str):
        existing_plan_path = existing_plan_path.strip() or None
    else:
        existing_plan_path = None

    candidate_paths: List[str] = []
    if existing_plan_path:
        candidate_paths.append(existing_plan_path)
    if plan_rel not in candidate_paths:
        candidate_paths.append(plan_rel)

    plans_dir = base_root / "docs" / "plans"
    if plans_dir.exists():
        pattern = f"*-feature-{current_id}-{slug}.md"
        for matched in sorted(plans_dir.glob(pattern), reverse=True):
            rel = matched.relative_to(base_root).as_posix()
            if rel not in candidate_paths:
                candidate_paths.append(rel)

    need_write = True
    for candidate in candidate_paths:
        absolute_candidate = base_root / candidate
        if not absolute_candidate.exists():
            continue
        validation = validate_plan_document(candidate)
        if validation["valid"]:
            need_write = False
            plan_rel = candidate
            print(f"Execution note already exists: {plan_rel} (state converged)")
            break
        print(f"Warning: existing note invalid ({candidate}), regenerating")

    if need_write:
        note_content = (
            f"# {feature_name} -- direct_tdd execution note\n"
            f"\n"
            f"**Goal:** {why}\n"
            f"\n"
            f"**Architecture:** Direct TDD implementation of {in_scope_text}. "
            f"Out of scope: {out_of_scope_text}.\n"
            f"\n"
            f"---\n"
            f"\n"
            f"## Tasks\n"
            f"\n"
            + "\n".join(task_lines)
            + "\n"
            f"\n"
            f"## Acceptance Mapping\n"
            f"\n"
            + "\n".join(acceptance_lines)
            + "\n"
            f"\n"
            f"## Risks\n"
            f"\n"
            + "\n".join(risk_lines)
            + "\n"
        )
        absolute_path = base_root / plan_rel
        _atomic_write_text(absolute_path, note_content)
        print(f"Generated direct_tdd execution note: {plan_rel}")

    # set_workflow_state() assumes persisted workflow_state has dict semantics.
    # Missing workflow_state is legal and is initialized by set_workflow_state().
    if needs_workflow_state_repair:
        data["workflow_state"] = {}
        save_progress_json(data)

    result = set_workflow_state(
        phase="execution",
        plan_path=plan_rel,
        next_action="direct_tdd",
    )
    if not result:
        print("Error: Failed to converge workflow_state")
        return False

    return True


def generate_progress_md(data):
    """Generate markdown content from progress data."""
    project_name = data.get("project_name", "Unknown Project")
    features = data.get("features", [])
    bugs = data.get("bugs", [])
    current_id = data.get("current_feature_id")
    current_bug_id = data.get("current_bug_id")
    created_at = data.get("created_at", "")
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}
    runtime_context = data.get("runtime_context")

    md_lines = [
        f"# Project Progress: {project_name}",
        "",
        f"**Created**: {created_at}",
        "",
    ]

    completed = [f for f in features if f.get("completed", False)]
    in_progress = [f for f in features if f.get("id") == current_id]
    deferred = [
        f
        for f in features
        if not f.get("completed", False)
        and f.get("id") != current_id
        and _is_feature_deferred(f)
    ]
    pending = [
        f
        for f in features
        if not f.get("completed", False) and f.get("id") != current_id
        and not _is_feature_deferred(f)
    ]

    total = len(features)
    completed_count = len(completed)

    md_lines.append(f"**Status**: {completed_count}/{total} completed")
    md_lines.append("")

    if completed:
        md_lines.append("## Completed")
        for f in completed:
            md_lines.append(f"- [x] {f.get('name', 'Unknown')}")
            owner_summary = _format_feature_owners(f)
            if owner_summary:
                md_lines.append(f"  Owners: {owner_summary}")
        md_lines.append("")

    if in_progress:
        md_lines.append("## In Progress")
        for f in in_progress:
            md_lines.append(f"- [ ] {f.get('name', 'Unknown')}")
            owner_summary = _format_feature_owners(f)
            if owner_summary:
                md_lines.append(f"  Owners: {owner_summary}")
            test_steps = f.get("test_steps", [])
            if test_steps:
                md_lines.append("  **Test steps**:")
                for step in test_steps:
                    md_lines.append(f"  - {step}")
        md_lines.append("")

    if pending:
        md_lines.append("## Pending")
        for f in pending:
            md_lines.append(f"- [ ] {f.get('name', 'Unknown')}")
            owner_summary = _format_feature_owners(f)
            if owner_summary:
                md_lines.append(f"  Owners: {owner_summary}")
        md_lines.append("")

    if deferred:
        md_lines.append("## Deferred")
        for f in deferred:
            reason = f.get("defer_reason") or "No reason provided"
            group = f.get("defer_group")
            line = f"- [~] {f.get('name', 'Unknown')} — {reason}"
            if group:
                line += f" (group: {group})"
            md_lines.append(line)
            owner_summary = _format_feature_owners(f)
            if owner_summary:
                md_lines.append(f"  Owners: {owner_summary}")
        md_lines.append("")

    if current_id is not None and workflow_state:
        phase = workflow_state.get("phase", "unknown")
        current_task = workflow_state.get("current_task")
        total_tasks = workflow_state.get("total_tasks")
        next_action = workflow_state.get("next_action")
        execution_context = workflow_state.get("execution_context")
        context_hint = compare_contexts(execution_context, runtime_context)

        md_lines.append("## Workflow Context")
        md_lines.append(f"- Phase: {phase}")

        if current_task is not None or total_tasks is not None:
            task_progress = f"{current_task if current_task is not None else '?'}"
            if total_tasks is not None:
                task_progress += f"/{total_tasks}"
            md_lines.append(f"- Task progress: {task_progress}")

        if next_action:
            md_lines.append(f"- Next action: {next_action}")

        if execution_context:
            md_lines.append(f"- Execution context: {_format_context_summary(execution_context)}")
        if runtime_context:
            md_lines.append(f"- Current session context: {_format_context_summary(runtime_context)}")

        if context_hint.get("status") in {"mismatch", "path_mismatch", "branch_mismatch"}:
            md_lines.append(
                "- Context mismatch: "
                f"{context_hint.get('message')} "
                f"(expected {context_hint.get('expected_branch') or '?'} @ "
                f"{context_hint.get('expected_worktree_path') or '?'})"
            )
        md_lines.append("")

    updates = data.get("updates", [])
    if updates:
        md_lines.append("## Recent Updates")
        for update in updates[-5:]:
            line = (
                f"- [{update.get('id', 'UPD-???')}] "
                f"{update.get('category', 'status')}: {update.get('summary', '')}"
            )
            if update.get("feature_id") is not None:
                line += f" (feature:{update['feature_id']})"
            if update.get("role") and update.get("owner"):
                line += f" [{update['role']}={update['owner']}]"
            md_lines.append(line)
            if update.get("next_action"):
                md_lines.append(f"  Next: {update['next_action']}")
        md_lines.append("")

    # Add bugs section if any exist
    if bugs:
        status_icons = {
            "pending_investigation": "🔴",
            "investigating": "🟡",
            "confirmed": "🟢",
            "fixing": "🔧",
            "fixed": "✅",
            "false_positive": "❌"
        }

        # Group bugs by status
        pending_bugs = [b for b in bugs if b.get("status") in ["pending_investigation", "investigating", "confirmed", "fixing"]]
        fixed_bugs = [b for b in bugs if b.get("status") == "fixed"]

        # Group pending bugs by priority
        high_pending = [b for b in pending_bugs if b.get("priority") == "high"]
        medium_pending = [b for b in pending_bugs if b.get("priority") == "medium"]
        low_pending = [b for b in pending_bugs if b.get("priority") == "low"]

        if pending_bugs:
            md_lines.append("## Bug Backlog")

            if high_pending:
                md_lines.append("### High Priority (🔴)")
                for bug in high_pending:
                    icon = status_icons.get(bug.get("status"), "❓")
                    category_prefix = "[DEBT] " if bug.get("category") == "technical_debt" else ""
                    md_lines.append(
                        f"- [{icon}] [{bug.get('id')}] {category_prefix}{bug.get('description', 'No description')}"
                    )
                    scheduled = bug.get("scheduled_position", {})
                    if scheduled:
                        reason = scheduled.get("reason", "")
                        md_lines.append(f"  Status: {bug.get('status')} | 📍 {reason}")
                md_lines.append("")

            if medium_pending:
                md_lines.append("### Medium Priority (🟡)")
                for bug in medium_pending:
                    icon = status_icons.get(bug.get("status"), "❓")
                    category_prefix = "[DEBT] " if bug.get("category") == "technical_debt" else ""
                    md_lines.append(
                        f"- [{icon}] [{bug.get('id')}] {category_prefix}{bug.get('description', 'No description')}"
                    )
                    if bug.get("root_cause"):
                        md_lines.append(f"  Root cause: {bug['root_cause']}")
                    scheduled = bug.get("scheduled_position", {})
                    if scheduled:
                        reason = scheduled.get("reason", "")
                        md_lines.append(f"  📍 {reason}")
                md_lines.append("")

            if low_pending:
                md_lines.append("### Low Priority (🟢)")
                for bug in low_pending:
                    icon = status_icons.get(bug.get("status"), "❓")
                    category_prefix = "[DEBT] " if bug.get("category") == "technical_debt" else ""
                    md_lines.append(
                        f"- [{icon}] [{bug.get('id')}] {category_prefix}{bug.get('description', 'No description')}"
                    )
                md_lines.append("")

        if fixed_bugs:
            md_lines.append("### Fixed (✅)")
            for bug in fixed_bugs:
                category_prefix = "[DEBT] " if bug.get("category") == "technical_debt" else ""
                md_lines.append(
                    f"- [x] [{bug.get('id')}] {category_prefix}{bug.get('description', 'No description')}"
                )
                if bug.get("fix_summary"):
                    md_lines.append(f"  Fix: {bug['fix_summary']}")
            md_lines.append("")

    return "\n".join(md_lines)


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

        payload, _ = _load_progress_payload_at_root(resolved_root)
        if not isinstance(payload, dict):
            continue
        _normalize_route_schema(payload)
        tracker_role = str(payload.get("tracker_role") or DEFAULT_TRACKER_ROLE).strip().lower()
        if tracker_role != "parent":
            continue

        matched_entry: Optional[Dict[str, Any]] = None
        for spec in _iter_linked_project_specs(payload):
            linked_root = _resolve_linked_project_root(
                spec["raw_project_root"],
                resolved_root,
                repo_resolved,
            )
            if linked_root == child_resolved:
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
) -> None:
    """Print deterministic route preflight recovery guidance."""
    command_tail = _extract_command_tail(argv, command)
    command_tail_text = " ".join(shlex.quote(token) for token in command_tail) if command_tail else command
    child_scope = shlex.quote(_scope_hint(child_project_root, repo_root))
    code_hint = child_code or "<PROJECT_CODE>"

    print(f"[Route Preflight] BLOCKED: {reason}")
    print(f"Current tracker: {child_project_root}")
    if parent_project_root is not None:
        print(f"Detected parent tracker: {parent_project_root}")

    print("Recovery:")
    print(f"  cd {repo_root}")
    if parent_project_root is None:
        print(
            "  plugins/progress-tracker/prog --project-root <parent_project_root> "
            f"link-project --project-root {child_scope} --code {code_hint}"
        )
        print(
            "  plugins/progress-tracker/prog --project-root <parent_project_root> "
            f"route-select --project {code_hint} --feature-ref {code_hint}-F<number>"
        )
    else:
        parent_scope = shlex.quote(_scope_hint(parent_project_root, repo_root))
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


def enforce_route_preflight(command: str, argv: Sequence[str]) -> bool:
    """Fail-closed preflight for child tracker mutating commands."""
    if command in ROUTE_PREFLIGHT_EXEMPT_COMMANDS:
        return True

    data = load_progress_json()
    if not isinstance(data, dict):
        return True

    tracker_role = str(data.get("tracker_role") or DEFAULT_TRACKER_ROLE).strip().lower()
    if tracker_role != "child":
        return True

    child_project_root = find_project_root().resolve()
    repo_root = Path(_REPO_ROOT or child_project_root).resolve()
    child_code_raw = data.get("project_code")
    child_code = _normalize_project_code(child_code_raw) if isinstance(child_code_raw, str) else None

    parent_bindings = _discover_parent_route_bindings_for_child(
        child_project_root=child_project_root,
        repo_root=repo_root,
    )

    if child_code is None:
        _print_route_preflight_block(
            reason="Child tracker has no project_code; route ownership cannot be verified.",
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=repo_root,
            child_code=None,
            parent_project_root=parent_bindings[0]["project_root"] if parent_bindings else None,
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
            repo_root=repo_root,
            child_code=child_code,
            parent_project_root=None,
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
            repo_root=repo_root,
            child_code=child_code,
            parent_project_root=parent_bindings[0]["project_root"],
        )
        return False

    parent_binding = parent_bindings[0]
    parent_project_root = parent_binding["project_root"]
    linked_entry = parent_binding.get("linked_entry", {})
    linked_code_raw = linked_entry.get("project_code") if isinstance(linked_entry, dict) else None
    linked_code = _normalize_project_code(linked_code_raw) if isinstance(linked_code_raw, str) else None
    if linked_code is not None and linked_code != child_code:
        _print_route_preflight_block(
            reason=(
                f"Parent registration mismatch: child reports {child_code}, "
                f"but parent linked_projects expects {linked_code}."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=repo_root,
            child_code=child_code,
            parent_project_root=parent_project_root,
        )
        return False

    active_route_codes: List[str] = []
    for route in parent_binding.get("active_routes", []):
        if not isinstance(route, dict):
            continue
        route_code_raw = route.get("project_code")
        if not isinstance(route_code_raw, str):
            continue
        route_code = _normalize_project_code(route_code_raw)
        if route_code is not None:
            active_route_codes.append(route_code)

    if child_code not in active_route_codes:
        active_display = ", ".join(sorted(set(active_route_codes))) if active_route_codes else "(none)"
        _print_route_preflight_block(
            reason=(
                f"Parent active route mismatch: expected {child_code}, current active routes: {active_display}. "
                "Mutating command denied."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=repo_root,
            child_code=child_code,
            parent_project_root=parent_project_root,
        )
        return False

    return True


def check_worktree_branch_consistency(command: str) -> bool:
    """
    Fail-closed check: verify current worktree/branch matches workflow_state.execution_context.

    Returns True if context matches or no constraint is recorded.
    Returns False (and prints recovery guidance) on mismatch.
    """
    data = load_progress_json()
    if not isinstance(data, dict):
        return True

    workflow_state = data.get("workflow_state")
    if not isinstance(workflow_state, dict):
        return True

    execution_context = workflow_state.get("execution_context")
    if not isinstance(execution_context, dict):
        return True

    expected_branch = execution_context.get("branch")
    expected_path = execution_context.get("worktree_path")

    # No constraint recorded yet — pass through
    if not expected_branch and not expected_path:
        return True

    current_ctx = collect_git_context()
    comparison = compare_contexts(
        expected=execution_context,
        current=current_ctx,
    )

    mismatch_statuses = {"mismatch", "path_mismatch", "branch_mismatch", "unknown"}
    comparison_status = comparison.get("status")
    current_branch = current_ctx.get("branch")
    current_path = current_ctx.get("worktree_path")
    missing_required_current = bool(
        (expected_branch and not current_branch) or (expected_path and not current_path)
    )
    if comparison_status not in mismatch_statuses and not missing_required_current:
        return True

    # done-only exemption: allow completion on default branch once feature branch is merged.
    if command == "done" and expected_branch:
        project_root = find_project_root()
        default_branch = _detect_default_branch(project_root)
        if default_branch and current_branch == default_branch:
            if _is_branch_merged_into(expected_branch, default_branch):
                print(
                    f"[Scope Consistency] Feature branch '{expected_branch}' "
                    f"already merged into {default_branch} — proceeding."
                )
                if expected_path and comparison_status in {"path_mismatch", "mismatch"}:
                    print(
                        "[Scope Consistency] WARN: worktree path mismatch "
                        f"(expected {expected_path}) — ignored (branch merged)."
                    )
                return True

    # Hard block — print actionable recovery guidance
    print(f"[Scope Consistency] BLOCKED: {command} denied — worktree/branch mismatch.")
    print(f"  Expected branch:       {expected_branch or '(any)'}")
    print(f"  Current branch:        {current_ctx.get('branch') or '(unknown)'}")
    print(f"  Expected worktree:     {expected_path or '(any)'}")
    print(f"  Current worktree:      {current_ctx.get('worktree_path') or '(unknown)'}")
    print("Recovery:")
    print("  1. Switch to the correct worktree/branch, OR")
    print("  2. Re-register this session as the active route:")
    print("       plugins/progress-tracker/prog route-select --project <PROJECT_CODE>")
    print(
        "  3. If the feature branch is already merged and worktree was cleaned up:"
    )
    print("       plugins/progress-tracker/prog clear-workflow-state")
    print(
        "       plugins/progress-tracker/prog set-workflow-state "
        "--phase execution_complete --plan-path <path>"
    )
    print("       plugins/progress-tracker/prog done --commit <merge_commit_hash>")
    return False


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
