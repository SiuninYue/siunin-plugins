#!/usr/bin/env python3
"""
Progress Manager - Core state management for Progress Tracker plugin.

This script handles initialization, status checking, and state updates for
feature-based progress tracking.

Usage:
    python3 progress_manager.py init [--force] <project_name>
    python3 progress_manager.py status
    python3 progress_manager.py check
    python3 progress_manager.py list-archives [--limit <n>]
    python3 progress_manager.py restore-archive <archive_id> [--force]
    python3 progress_manager.py git-sync-check
    python3 progress_manager.py git-auto-preflight [--json]
    python3 progress_manager.py set-current <feature_id>
    python3 progress_manager.py set-development-stage <planning|developing|completed> [--feature-id <id>]
    python3 progress_manager.py complete <feature_id>
    python3 progress_manager.py set-feature-ai-metrics <feature_id> --complexity-score <score> --selected-model <model> --workflow-path <path>
    python3 progress_manager.py complete-feature-ai-metrics <feature_id>
    python3 progress_manager.py auto-checkpoint
    python3 progress_manager.py validate-plan [--plan-path <path>]
    python3 progress_manager.py add-feature <name> <test_steps...>
    python3 progress_manager.py update-feature <feature_id> <name> [test_steps...]
    python3 progress_manager.py reset
"""

import argparse
import json
import os
import re
import sys
import subprocess
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

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
    resolve_target_project_root,
)

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
PLAN_PATH_PREFIX = "docs/plans/"
PLAN_PATH_PREFIX_LEGACY = "docs/progress-tracker/plans/"
# Both paths are accepted: docs/plans/ (Superpowers writing-plans standard)
# and docs/progress-tracker/plans/ (legacy format for backward compatibility)
VALID_PLAN_PREFIXES = (PLAN_PATH_PREFIX, PLAN_PATH_PREFIX_LEGACY)
PROGRESS_ARCHIVE_MAX_ENTRIES = 200

# Schema version - increment when breaking changes occur
CURRENT_SCHEMA_VERSION = "2.0"
DEVELOPMENT_STAGES = ("planning", "developing", "completed")

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


def validate_plan_path(
    plan_path: Optional[str], require_exists: bool = False
) -> Dict[str, Optional[str]]:
    """
    Validate workflow plan path shape and optional existence.

    Accepted formats:
    - docs/plans/<YYYY-MM-DD-name>.md  (Superpowers writing-plans standard)
    - docs/progress-tracker/plans/<name>.md  (legacy format)
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
            "error": f"plan_path must be under '{PLAN_PATH_PREFIX}' (or legacy '{PLAN_PATH_PREFIX_LEGACY}')",
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
        absolute_path = find_project_root() / normalized
        if not absolute_path.exists():
            return {
                "valid": False,
                "normalized_path": None,
                "error": f"plan_path does not exist: {normalized}",
            }

    return {"valid": True, "normalized_path": normalized, "error": None}


def validate_plan_document(plan_path: str) -> Dict[str, Any]:
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
    path_validation = validate_plan_path(plan_path, require_exists=True)
    if not path_validation["valid"]:
        return {
            "valid": False,
            "errors": [path_validation["error"]],
            "missing_sections": [],
            "warnings": [],
            "profile": "invalid",
        }

    absolute_path = find_project_root() / path_validation["normalized_path"]
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


def load_progress_json():
    """Load the progress.json file."""
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if not json_path.exists():
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error: {json_path} is corrupted.")
        return None


def _iso_now() -> str:
    """Return current local timestamp with trailing Z for compatibility."""
    return datetime.now().isoformat() + "Z"


def save_progress_json(data, touch_updated_at: bool = True):
    """Save data to progress.json file with optional updated_at touch and migration."""
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    # Ensure state directory exists
    progress_dir.mkdir(parents=True, exist_ok=True)

    # Auto-update updated_at timestamp
    if touch_updated_at:
        data["updated_at"] = _iso_now()

    # Ensure schema_version exists (migrate old files)
    if "schema_version" not in data:
        data["schema_version"] = CURRENT_SCHEMA_VERSION
        logger.info(f"Migrated to schema version {CURRENT_SCHEMA_VERSION}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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
    progress_dir = get_progress_dir()
    md_path = progress_dir / PROGRESS_MD

    # Ensure state directory exists
    progress_dir.mkdir(parents=True, exist_ok=True)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


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
    progress_dir = get_progress_dir()
    progress_dir.mkdir(parents=True, exist_ok=True)
    history_path = progress_dir / PROGRESS_HISTORY_JSON
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(entries[-PROGRESS_ARCHIVE_MAX_ENTRIES :], f, indent=2, ensure_ascii=False)


def _make_archive_id(project_name: str) -> str:
    """Build a unique archive identifier."""
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    return f"{timestamp}-{_slugify(project_name)}"


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
    archive_id = _make_archive_id(project_name)
    archive_dir = progress_dir / PROGRESS_ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_json_rel = None
    archive_md_rel = None

    if json_path.exists():
        archive_json_name = f"{archive_id}.progress.json"
        shutil.copy2(json_path, archive_dir / archive_json_name)
        archive_json_rel = f"{PROGRESS_ARCHIVE_DIR}/{archive_json_name}"

    if md_path.exists():
        archive_md_name = f"{archive_id}.progress.md"
        shutil.copy2(md_path, archive_dir / archive_md_name)
        archive_md_rel = f"{PROGRESS_ARCHIVE_DIR}/{archive_md_name}"

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
        "progress_json": archive_json_rel,
        "progress_md": archive_md_rel,
    }

    history = _load_progress_history()
    history.append(entry)
    _save_progress_history(history)
    return entry


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
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}

    runtime_context: Dict[str, Any] = {
        "recorded_at": _iso_now(),
        "source": source,
        **git_context,
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
    return {
        "recorded_at": _iso_now(),
        "source": source,
        "workspace_mode": git_context.get("workspace_mode"),
        "worktree_path": git_context.get("worktree_path"),
        "project_root": git_context.get("project_root"),
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
    progress_dir = get_progress_dir()
    progress_dir.mkdir(parents=True, exist_ok=True)
    checkpoints_path = path or (progress_dir / CHECKPOINTS_JSON)
    with open(checkpoints_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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

    # Calculate statistics
    total = len(features)
    completed = sum(1 for f in features if f.get("completed", False))
    in_progress = current_id is not None

    print(f"\n## Project: {project_name}")
    print(
        f"**Status**: {completed}/{total} completed ({completed * 100 // total if total > 0 else 0}%)"
    )

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

    # Display features
    if completed > 0:
        print("\n### Completed:")
        for f in features:
            if f.get("completed", False):
                print(f"  [x] {f.get('name', 'Unknown')}")

    if in_progress:
        print("\n### In Progress:")
        for f in features:
            if f.get("id") == current_id:
                print(f"  [*] {f.get('name', 'Unknown')}")
                test_steps = f.get("test_steps", [])
                if test_steps:
                    print("     Test steps:")
                    for step in test_steps:
                        print(f"       - {step}")

    remaining = [
        f
        for f in features
        if not f.get("completed", False) and f.get("id") != current_id
    ]
    if remaining:
        print("\n### Pending:")
        for f in remaining:
            print(f"  [ ] {f.get('name', 'Unknown')}")

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
            current_worktree = str(project_root.resolve())
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
            incomplete = [f for f in features if not f.get("completed", False)]

            if incomplete:
                other_worktrees.append({
                    "worktree_path": wt_path,
                    "project_name": data.get("project_name", "Unknown"),
                    "current_feature_id": data.get("current_feature_id"),
                    "incomplete_count": len(incomplete),
                    "total_features": len(features),
                })
        except (json.JSONDecodeError, IOError):
            # Skip worktrees with corrupted or unreadable progress files
            continue

    return other_worktrees


def check():
    """
    Check if progress tracking exists and has incomplete features.
    Returns exit code 0 if tracking is complete or doesn't exist, 1 if incomplete.

    Outputs JSON-formatted recovery information when incomplete work is detected.
    Also checks other worktrees for incomplete work and provides informative messages.
    """
    # Check for incomplete work in other worktrees
    current_root = str(find_project_root())
    other_worktrees_with_work = _check_other_worktrees_for_incomplete_work(current_root)

    # Check current worktree for incomplete work
    data = load_progress_json()
    if not data:
        return 0  # No tracking = nothing to recover

    features = data.get("features", [])
    incomplete = [f for f in features if not f.get("completed", False)]

    if incomplete:
        # First, show info about other worktrees with incomplete work (if any)
        # This is informational only - doesn't block current worktree recovery
        if other_worktrees_with_work:
            wt_list = []
            for wt in other_worktrees_with_work[:3]:  # Show at most 3 worktrees
                wt_info = f"{wt['worktree_path']} ({wt['project_name']}: {wt['total_features'] - wt['incomplete_count']}/{wt['total_features']} 完成)"
                wt_list.append(wt_info)

            info_msg = f"[Progress Tracker] ℹ️ 注意：其他 worktree 中也有未完成的工作\n"
            info_msg += f"其他 worktree: {'; '.join(wt_list)}\n"
            info_msg += f"如需切换，使用: cd <worktree_path>\n"

            print(json.dumps({
                "status": "info_other_worktrees",
                "message": info_msg,
                "other_worktrees": other_worktrees_with_work[:3],
            }))

        # Then proceed with current worktree recovery
        project_name = data.get("project_name", "Unknown")
        total = len(features)
        completed = total - len(incomplete)
        current_id = data.get("current_feature_id")
        workflow_state = data.get("workflow_state", {})

        # If there's a feature in progress, provide detailed recovery info
        if current_id:
            feature = next((f for f in features if f.get("id") == current_id), None)
            if feature:
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
                    require_exists=phase in ["planning_complete", "execution", "execution_complete"],
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
        print(f"[Progress Tracker] Unfinished project detected: {project_name}")
        print(f"Progress: {completed}/{total} completed")
        print(f"Use '/prog' to view status or '/prog-next' to continue")
        return 1

    return 0


def determine_recovery_action(
    phase, feature, completed_tasks, total_tasks, plan_path: Optional[str] = None
):
    """Determine the recommended recovery action based on workflow state."""
    if phase in ["planning_complete", "execution", "execution_complete"]:
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

    data["current_feature_id"] = feature_id

    # Selecting a feature for work always starts in planning stage.
    # /prog-start will explicitly transition planning -> developing.
    if not feature.get("completed", False):
        feature["development_stage"] = "planning"
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

    feature["development_stage"] = stage
    if stage == "developing" and not feature.get("started_at"):
        feature["started_at"] = _iso_now()

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
        if not feature.get("completed", False):
            return feature

    return None


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
    - Legacy: feature-{feature_id}-*.md
    - Current: YYYY-MM-DD-description.md

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

        # Collect all patterns to try for this feature
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

        save_progress_json(data)
        logger.info(f"Archive record saved for feature {feature_id}")

    except Exception as e:
        logger.error(f"Failed to save archive record: {e}")


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
    feature["completed_at"] = _iso_now()
    if commit_hash:
        feature["commit_hash"] = commit_hash

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
    }

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

    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Updated feature {feature_id}: {normalized_name}")
    if test_steps:
        print(f"Updated test steps ({len(test_steps)} step(s))")
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
    pending = [
        f
        for f in features
        if not f.get("completed", False) and f.get("id") != current_id
    ]

    total = len(features)
    completed_count = len(completed)

    md_lines.append(f"**Status**: {completed_count}/{total} completed")
    md_lines.append("")

    if completed:
        md_lines.append("## Completed")
        for f in completed:
            md_lines.append(f"- [x] {f.get('name', 'Unknown')}")
        md_lines.append("")

    if in_progress:
        md_lines.append("## In Progress")
        for f in in_progress:
            md_lines.append(f"- [ ] {f.get('name', 'Unknown')}")
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
    subparsers.add_parser("check", help="Check for incomplete progress")

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

    if not configure_project_scope(args.project_root):
        return False

    if args.command == "init":
        return init_tracking(args.project_name, force=args.force)
    elif args.command == "status":
        return status()
    elif args.command == "check":
        return check()
    elif args.command == "list-archives":
        return list_archives(limit=args.limit)
    elif args.command == "restore-archive":
        return restore_archive(args.archive_id, force=args.force)
    elif args.command == "set-current":
        return set_current(args.feature_id)
    elif args.command == "set-development-stage":
        return set_development_stage(args.stage, feature_id=args.feature_id)
    elif args.command == "complete":
        return complete_feature(
            args.feature_id,
            commit_hash=args.commit,
            skip_archive=args.skip_archive
        )
    elif args.command == "add-feature":
        return add_feature(args.name, args.test_steps)
    elif args.command == "update-feature":
        return update_feature(
            args.feature_id, args.name, args.test_steps if args.test_steps else None
        )
    elif args.command == "undo":
        return undo_last_feature()
    elif args.command == "reset":
        return reset_tracking(force=args.force)
    elif args.command == "set-workflow-state":
        return set_workflow_state(
            phase=args.phase, plan_path=args.plan_path, next_action=args.next_action
        )
    elif args.command == "update-workflow-task":
        return update_workflow_task(args.task_id, args.status)
    elif args.command == "clear-workflow-state":
        return clear_workflow_state()
    elif args.command == "health":
        return health_check()
    elif args.command == "git-sync-check":
        return git_sync_check()
    elif args.command == "git-auto-preflight":
        return git_auto_preflight(output_json=args.output_json)
    elif args.command == "set-feature-ai-metrics":
        return set_feature_ai_metrics(
            args.feature_id,
            args.complexity_score,
            args.selected_model,
            args.workflow_path,
        )
    elif args.command == "complete-feature-ai-metrics":
        return complete_feature_ai_metrics(args.feature_id)
    elif args.command == "auto-checkpoint":
        return auto_checkpoint()
    elif args.command == "sync-runtime-context":
        return sync_runtime_context(source=args.source, quiet=args.quiet, force=args.force)
    elif args.command == "validate-plan":
        return validate_plan(plan_path=args.plan_path)
    elif args.command == "add-bug":
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
    elif args.command == "update-bug":
        return update_bug(
            bug_id=args.bug_id,
            status=args.status,
            root_cause=args.root_cause,
            fix_summary=args.fix_summary
        )
    elif args.command == "list-bugs":
        return list_bugs()
    elif args.command == "remove-bug":
        return remove_bug(args.bug_id)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    result = main()
    if isinstance(result, bool):
        sys.exit(0 if result else 1)
    if isinstance(result, int):
        sys.exit(result)
    sys.exit(0 if result else 1)
