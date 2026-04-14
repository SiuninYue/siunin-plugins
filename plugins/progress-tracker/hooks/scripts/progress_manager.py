#!/usr/bin/env python3
"""
Progress Manager - Core state management for Progress Tracker plugin.

This script handles initialization, status checking, and state updates for
feature-based progress tracking.

Usage:
    python3 progress_manager.py init [--force] <project_name>
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
    python3 progress_manager.py done [--commit <hash>] [--run-all] [--skip-archive]
    python3 progress_manager.py set-feature-ai-metrics <feature_id> --complexity-score <score> --selected-model <model> --workflow-path <path>
    python3 progress_manager.py complete-feature-ai-metrics <feature_id>
    python3 progress_manager.py auto-checkpoint
    python3 progress_manager.py sync-linked [--json] [--stale-after-hours <hours>]
    python3 progress_manager.py link-project --project-root <path> --code <CODE> [--parent-root <path>] [--json]
    python3 progress_manager.py validate-plan [--plan-path <path>]
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
from typing import Optional, List, Dict, Any, Tuple, Set

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

from prog_paths import (
    PROGRESS_ARCHIVE_DIR,
    PROGRESS_HISTORY_JSON,
    ProjectRootResolutionError,
    ensure_storage_migrated,
    ensure_tracker_layout,
    get_checkpoints_path,
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
# Superpowers writing-plans standard: docs/plans/
PLAN_PATH_PREFIX = "docs/plans/"
VALID_PLAN_PREFIXES = (PLAN_PATH_PREFIX,)
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
CURRENT_SCHEMA_VERSION = "2.0"
LINKED_SNAPSHOT_SCHEMA_VERSION = "1.0"
DEFAULT_LINKED_STATUS_STALE_HOURS = 24
TRACKER_ROLES = ("standalone", "parent", "child")
DEFAULT_TRACKER_ROLE = "standalone"
DEVELOPMENT_STAGES = ("planning", "developing", "completed")
LIFECYCLE_STATES = ("approved", "implementing", "verified", "archived")
OWNER_ROLES = ("architecture", "coding", "testing")
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
    "update-bug",
    "remove-bug",
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

    Accepted format:
    - docs/plans/<YYYY-MM-DD-name>.md  (Superpowers writing-plans standard)
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
            "error": f"plan_path must be under '{PLAN_PATH_PREFIX}'",
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
        base_root = target_root or find_project_root()
        absolute_path = base_root / normalized
        if not absolute_path.exists():
            return {
                "valid": False,
                "normalized_path": None,
                "error": f"plan_path does not exist: {normalized}",
            }

    return {"valid": True, "normalized_path": normalized, "error": None}


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

    statuses: List[Dict[str, Any]] = []
    for spec in _iter_linked_project_specs(progress_data):
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
        }

        if not progress_path.exists():
            statuses.append(status)
            continue

        try:
            payload = json.loads(progress_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("progress payload must be object")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            status["status"] = "invalid"
            status["error"] = str(exc)
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

    child_data["tracker_role"] = "child"
    child_data["project_code"] = normalized_code
    _save_progress_payload_at_root(child_root, child_data)

    child_name = child_data.get("project_name")
    inferred_label = (
        child_name.strip()
        if isinstance(child_name, str) and child_name.strip()
        else child_root.name
    )
    normalized_label = (
        label.strip() if isinstance(label, str) and label.strip() else inferred_label
    )
    configured_project_root = _serialize_project_root_for_config(child_root, repo_root)

    linked_projects = parent_data.get("linked_projects")
    if not isinstance(linked_projects, list):
        linked_projects = []

    previous_codes: Set[str] = set()
    deduped_projects: List[Any] = []
    target_written = False
    for entry in linked_projects:
        entry_root_raw: Optional[str]
        entry_code_raw: Optional[str]
        if isinstance(entry, dict):
            raw_value = entry.get("project_root") or entry.get("path") or entry.get("root")
            entry_root_raw = str(raw_value).strip() if raw_value is not None else None
            entry_code_raw = entry.get("project_code")
        elif isinstance(entry, str):
            entry_root_raw = entry.strip()
            entry_code_raw = None
        else:
            deduped_projects.append(entry)
            continue

        entry_root = (
            _resolve_linked_project_root(entry_root_raw, parent_root, repo_root)
            if entry_root_raw
            else None
        )
        entry_code = (
            str(entry_code_raw).strip().upper()
            if isinstance(entry_code_raw, str) and entry_code_raw.strip()
            else None
        )

        if entry_code and entry_root == child_root and entry_code != normalized_code:
            previous_codes.add(entry_code)

        matches_target = (entry_root == child_root) or (entry_code == normalized_code)
        if matches_target:
            if target_written:
                continue
            base_entry = entry if isinstance(entry, dict) else {}
            updated_entry = dict(base_entry)
            updated_entry["project_root"] = configured_project_root
            updated_entry["project_code"] = normalized_code
            updated_entry["label"] = normalized_label
            deduped_projects.append(updated_entry)
            target_written = True
            continue

        deduped_projects.append(entry)

    if not target_written:
        deduped_projects.append(
            {
                "project_root": configured_project_root,
                "project_code": normalized_code,
                "label": normalized_label,
            }
        )

    parent_data["linked_projects"] = deduped_projects
    parent_data["tracker_role"] = "parent"

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
        if token == normalized_code:
            continue
        if token in seen_queue_codes:
            continue
        seen_queue_codes.add(token)
        normalized_queue.append(token)
    normalized_queue.append(normalized_code)
    parent_data["routing_queue"] = normalized_queue

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

    # Type B: routing_queue code not in linked_projects
    for item in routing_queue:
        if not isinstance(item, str):
            continue
        code = item.strip().upper()
        if code and code not in linked_codes:
            conflicts.append(
                {"type": "B", "code": code, "message": f"{code} in routing_queue but not in linked_projects"}
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

    new_routes = other_routes + [upserted_entry]
    data["active_routes"] = new_routes

    _update_runtime_context(data, source="route_select")
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

    action = "updated" if existing_entry is not None else "inserted"
    if output_json:
        print(
            json.dumps(
                {"status": "ok", "project_code": normalized_code, "active_routes": new_routes},
                ensure_ascii=False,
            )
        )
    else:
        ref_display = final_ref or "(empty)"
        print(f"route-select: {action} {normalized_code} -> {ref_display}")
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
    """Return whether a feature is currently deferred."""
    return bool(feature.get("deferred", False))


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
    recommended_next_step = "/prog next" if not current_id else "resume implementation"
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
    """Map a 0-40 complexity score to simple/standard/complex buckets."""
    if score <= 15:
        return "simple"
    if score <= 25:
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
        next_feature = min(pending, key=lambda item: item.get("id", float("inf")))
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
    if not current_feature_id:
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


def init_tracking(project_name, features=None, force=False):
    """
    Initialize progress tracking for a project.

    Args:
        project_name: Name of the project to track
        features: Optional list of feature dicts with keys: name, test_steps
        force: Force re-initialization even if tracking exists
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
    if force:
        archived_entry = archive_current_progress(reason="reinitialize")

    # Create initial progress structure
    now = datetime.now().isoformat() + "Z"
    data = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "project_name": project_name,
        "created_at": now,
        "updated_at": now,
        "features": features or [],
        "current_feature_id": None,
    }

    save_progress_json(data)

    # Create initial progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Initialized progress tracking for: {project_name}")
    print(f"Location: {progress_dir}")
    if archived_entry:
        print(
            "Archived previous progress as "
            f"{archived_entry.get('archive_id')} "
            f"(reason={archived_entry.get('reason')})"
        )
    if features:
        print(f"Added {len(features)} features")
    return True


def status():
    """Display current progress status."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use '/prog init' to start tracking.")
        return False

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

    if current_id:
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

    updates = data.get("updates", [])
    if updates:
        print("\n### Recent Updates:")
        for update in updates[-5:]:
            line = (
                f"  [{update.get('id', 'UPD-???')}] "
                f"{update.get('category', 'status')}: {update.get('summary', '')}"
            )
            if update.get("feature_id") is not None:
                line += f" (feature:{update['feature_id']})"
            if update.get("role") and update.get("owner"):
                line += f" [{update['role']}={update['owner']}]"
            print(line)

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
                updated = proj.get("updated_at")
                updated_str = (
                    f" | {_format_relative_time_for_summary(updated)}" if updated else ""
                )
                if proj_status == "ok":
                    print(
                        f"  [{proj_name}] {completed_n}/{total_n} ({pct}%){stale_marker}{updated_str}"
                    )
                elif proj_status == "missing":
                    print(f"  [{proj_name}] missing{stale_marker}")
                else:
                    print(f"  [{proj_name}] {proj_status}{stale_marker}")

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
    elif on_default_branch and "dirty_worktree" in issue_ids:
        decision = "REQUIRE_WORKTREE"
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

        if not actionable_incomplete and not current_id:
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
        if current_id:
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
    """Determine the recommended recovery action based on workflow state."""
    if phase in ["planning:draft", "planning:approved",
                 "planning_complete", "execution", "execution_complete"]:
        plan_validation = validate_plan_path(plan_path, require_exists=True)
        if not plan_validation["valid"]:
            return "recreate_plan"

    if phase == "execution_complete":
        return "run_prog_done"
    elif phase == "execution" and total_tasks > 0:
        progress = len(completed_tasks) / total_tasks if total_tasks > 0 else 0
        if progress >= 0.8:
            return "auto_resume"
        else:
            return "manual_resume"
    elif phase == "planning:approved":
        return "execute_approved_plan"
    elif phase == "planning:draft":
        return "resume_planning_draft"
    elif phase == "planning:clarifying":
        return "restart_from_planning"
    elif phase in ["planning", "design_complete", "design"]:
        return "restart_from_planning"
    else:
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
    # This keeps `/prog-next` as a one-step start action instead of requiring
    # an additional `/prog-start` transition.
    if not feature.get("completed", False):
        feature["development_stage"] = "developing"
        feature["lifecycle_state"] = "implementing"
        if not feature.get("started_at"):
            feature["started_at"] = _iso_now()

    if previous_current_id != feature_id:
        data.pop("workflow_state", None)

    _update_runtime_context(data, source="set_current")
    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

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


def next_feature(output_json: bool = False, ack_planning_risk: bool = False) -> bool:
    """Print the next actionable feature (skipping completed/deferred)."""
    data = load_progress_json()
    if data:
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


def set_feature_ai_metrics(feature_id: int, complexity_score: int,
                           selected_model: str, workflow_path: str) -> bool:
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

    if complexity_score < 0 or complexity_score > 40:
        print("Invalid complexity score. Must be in range 0-40")
        return False

    now_iso = datetime.now().isoformat() + "Z"
    ai_metrics = feature.get("ai_metrics", {})
    if not isinstance(ai_metrics, dict):
        ai_metrics = {}

    ai_metrics.update(
        {
            "complexity_score": complexity_score,
            "complexity_bucket": determine_complexity_bucket(complexity_score),
            "selected_model": selected_model,
            "workflow_path": workflow_path,
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
    normalized = step.strip()
    if not normalized:
        return False
    if normalized.startswith("DoD:"):
        return False
    if normalized.startswith("#") or normalized.startswith("//"):
        return False

    try:
        tokens = shlex.split(normalized, posix=True)
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
        if not _is_executable_test_step(raw_step):
            print(f"[DONE][SKIP] {raw_step}")
            continue

        command = raw_step.strip()
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


def cmd_done(commit_hash=None, run_all: bool = False, skip_archive: bool = False) -> int:
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
    print(f"[DONE] Running acceptance tests for Feature {feature_id}: {feature_name}")

    all_passed, results = _run_acceptance_tests(feature, run_all=run_all)
    report_path = _save_done_test_report(
        feature_id=feature_id,
        feature_name=feature_name,
        results=results,
        success=all_passed,
    )

    if not all_passed:
        refreshed = load_progress_json()
        if refreshed:
            current_feature = next(
                (item for item in refreshed.get("features", []) if item.get("id") == feature_id),
                None,
            )
            if current_feature:
                current_feature["finish_pending_reason"] = _format_failure_reason(results)
                current_feature["last_done_attempt_at"] = _iso_now()
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
    resolved_commit = commit_hash or _get_head_commit()
    success = complete_feature(
        feature_id=feature_id,
        commit_hash=resolved_commit,
        skip_archive=skip_archive,
    )
    if not success:
        print("[DONE] Failed to complete feature after acceptance checks")
        return 4

    print(f"[DONE] Feature {feature_id} completed")
    if resolved_commit:
        print(f"[DONE] Commit: {resolved_commit}")
    if report_path:
        try:
            relative_report = report_path.relative_to(find_project_root())
        except ValueError:
            relative_report = report_path
        print(f"[DONE] Report: {relative_report}")
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

    reconcile_report = analyze_reconcile_state(data)
    diagnosis = reconcile_report.get("diagnosis")
    if diagnosis in {"scope_mismatch", "context_mismatch"}:
        print(
            "Cannot complete feature due to reconcile gate: "
            f"{diagnosis}. Suggested next step: {reconcile_report.get('recommended_next_step')}"
        )
        return False

    if diagnosis == "needs_manual_review":
        current_id = data.get("current_feature_id")
        if current_id == feature_id:
            suggested = reconcile_report.get("recommended_next_step")
            if suggested in {"repair workflow_state", "clear invalid current_feature_id"}:
                print(
                    "Cannot complete feature until tracker state is repaired. "
                    f"Suggested next step: {suggested}"
                )
                return False

    # Finalize AI metrics before marking feature complete.
    complete_feature_ai_metrics(feature_id)
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False
    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    feature["completed"] = True
    feature["development_stage"] = "completed"
    feature["lifecycle_state"] = "verified"
    feature["completed_at"] = _iso_now()
    _clear_feature_defer_state(feature)
    _clear_feature_finish_pending(feature)
    if commit_hash:
        feature["commit_hash"] = commit_hash

    # Preserve plan_path for archiving before clearing workflow_state
    plan_path = data.get("workflow_state", {}).get("plan_path")
    if plan_path:
        feature["plan_path"] = plan_path

    data["current_feature_id"] = None
    _update_runtime_context(data, source="complete_feature")

    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

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

            # Save archive record regardless of individual file errors
            save_archive_record(feature_id, archive_result)

            if archive_result["errors"]:
                print(f"Warning: Some files could not be archived (feature still marked complete)")

        except Exception as e:
            # Archive failures should not prevent feature completion
            logger.error(f"Archive failed but feature completed: {e}")
            print(f"Warning: Document archiving failed but feature is marked complete")

        refreshed = load_progress_json()
        if refreshed and _is_project_fully_completed(refreshed):
            completed_archive = archive_current_progress(reason="completed")
            if completed_archive:
                print(
                    "Archived completed run as "
                    f"{completed_archive.get('archive_id')} "
                    f"(reason={completed_archive.get('reason')})"
                )

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


def list_updates(limit: int = 10) -> bool:
    """List the latest structured updates."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    updates = data.get("updates", [])
    if not updates:
        print("No updates recorded.")
        return True

    safe_limit = max(1, limit)
    print(f"Showing latest {min(safe_limit, len(updates))} update(s):")
    for item in updates[-safe_limit:]:
        line = f"- [{item.get('id', 'UPD-???')}] {item.get('category', 'status')}: {item.get('summary', '')}"
        source = str(item.get("source") or "").strip()
        if source:
            line += f" [source={source}]"
        if item.get("feature_id") is not None:
            line += f" (feature:{item['feature_id']})"
        if item.get("role") and item.get("owner"):
            line += f" [{item['role']}={item['owner']}]"
        overflow_count = item.get("refs_overflow_count")
        if not isinstance(overflow_count, int) or overflow_count < 0:
            overflow_refs = item.get("refs_overflow")
            if isinstance(overflow_refs, list):
                overflow_count = len(
                    [
                        ref
                        for ref in overflow_refs
                        if isinstance(ref, str) and ref.strip()
                    ]
                )
            else:
                overflow_count = 0
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


def add_feature(name, test_steps):
    """Add a new feature to the tracking."""
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


def add_bug(description: str, status: str = "pending_investigation",
            priority: str = "medium", category: str = "bug",
            scheduled_position: Optional[str] = None,
            verification_results: Optional[str] = None):
    """
    Add a new bug to the tracking with validation.

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
        bool: True if bug was successfully added, False if duplicate detected
        or validation failed.

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
            return False

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
    return True


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

    if not data.get("current_feature_id"):
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

    if current_id and workflow_state:
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


def main():
    parser = argparse.ArgumentParser(description="Progress Tracker Manager")
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

    # Status command
    subparsers.add_parser("status", help="Show progress status")

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
    list_updates_parser.add_argument("--limit", type=int, default=10, help="Max updates to show")

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
        "--complexity-score", type=int, required=True, help="Complexity score (0-40)"
    )
    ai_metrics_parser.add_argument(
        "--selected-model", choices=["haiku", "sonnet", "opus"], required=True, help="Model used"
    )
    ai_metrics_parser.add_argument(
        "--workflow-path", required=True,
        choices=["direct_tdd", "plan_execute", "full_design_plan_execute"],
        help="Workflow path used for implementation"
    )

    complete_ai_metrics_parser = subparsers.add_parser(
        "complete-feature-ai-metrics", help="Finalize AI metrics duration for feature"
    )
    complete_ai_metrics_parser.add_argument("feature_id", type=int, help="Feature ID")

    # Auto-checkpoint command
    subparsers.add_parser("auto-checkpoint", help="Create checkpoint snapshot if interval elapsed")
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

    args = parser.parse_args()

    scope_project_root = args.project_root
    if args.command == "link-project":
        scope_project_root = args.parent_root

    if not configure_project_scope(scope_project_root):
        return False

    def _dispatch_command() -> Any:
        if args.command == "init":
            return init_tracking(args.project_name, force=args.force)
        if args.command == "status":
            return status()
        if args.command == "check":
            return check(output_json=args.output_json)
        if args.command == "reconcile":
            return reconcile(output_json=args.output_json)
        if args.command == "next-feature":
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
            return complete_feature(
                args.feature_id,
                commit_hash=args.commit,
                skip_archive=args.skip_archive
            )
        if args.command == "done":
            return cmd_done(
                commit_hash=args.commit,
                run_all=args.run_all,
                skip_archive=args.skip_archive,
            )
        if args.command == "add-feature":
            return add_feature(args.name, args.test_steps)
        if args.command == "update-feature":
            return update_feature(
                args.feature_id, args.name, args.test_steps if args.test_steps else None
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
            return list_updates(limit=args.limit)
        if args.command == "set-feature-owner":
            return set_feature_owner(args.feature_id, args.role, args.owner)
        if args.command == "undo":
            return undo_last_feature()
        if args.command == "reset":
            return reset_tracking(force=args.force)
        if args.command == "set-workflow-state":
            return set_workflow_state(
                phase=args.phase, plan_path=args.plan_path, next_action=args.next_action
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
            )
        if args.command == "complete-feature-ai-metrics":
            return complete_feature_ai_metrics(args.feature_id)
        if args.command == "auto-checkpoint":
            return auto_checkpoint()
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
        if args.command == "route-status":
            return route_status(output_json=args.output_json)
        if args.command == "route-select":
            return route_select(
                args.project,
                feature_ref=args.feature_ref,
                output_json=args.output_json,
            )
        if args.command == "sync-runtime-context":
            return sync_runtime_context(source=args.source, quiet=args.quiet, force=args.force)
        if args.command == "validate-plan":
            return validate_plan(plan_path=args.plan_path)
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
        parser.print_help()
        return 1

    if args.command in MUTATING_COMMANDS:
        # `done` may execute nested `prog` mutating commands from acceptance steps.
        # Holding an outer process lock here can deadlock those nested invocations.
        if args.command == "done":
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
