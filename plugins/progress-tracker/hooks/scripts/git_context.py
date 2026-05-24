"""
git_context.py - Git runtime/execution context helpers.

Extracted from git_utils.py during F18 modularisation to keep each module under
its readability budget while preserving progress_manager re-export names.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from git_utils import _run_git
from pm_runtime import get_progress_manager_module

# ---------------------------------------------------------------------------
# Context normalisation helpers (used by both pm.py and this module)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Runtime / execution context builders
# ---------------------------------------------------------------------------


def collect_git_context() -> Dict[str, Any]:
    """
    Collect current git/worktree context using lightweight git probes.

    workspace_mode contract:
    - unknown: not a git repo or probes failed
    - worktree: git dir path contains '/worktrees/'
    - in_place: git repo and not a linked worktree git dir
    """
    _pm = get_progress_manager_module()
    fallback_root = _pm.find_project_root()
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
    _pm = get_progress_manager_module()  # late binding so test patches on pm namespace are honoured

    git_context = _pm.collect_git_context()
    tracker_root = str(_pm.find_project_root().resolve())
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}

    runtime_context: Dict[str, Any] = {
        "recorded_at": _pm._iso_now(),
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
    _pm = get_progress_manager_module()  # late binding so test patches on pm namespace are honoured

    git_context = _pm.collect_git_context()
    tracker_root = str(_pm.find_project_root().resolve())
    return {
        "recorded_at": _pm._iso_now(),
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

