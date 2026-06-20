"""
git_utils.py — Git and worktree operational helpers.

Extracted from progress_manager.py (F18 modularisation).
"""
import os
import re
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from prog_paths import (
    resolve_repo_root as _resolve_repo_root,
    get_state_dir,
)
from state_io import (
    load_progress_json,
    _normalize_optional_string,
    compare_contexts,
    _normalize_context_path,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROGRESS_JSON = "progress.json"
CHECKPOINTS_JSON = "checkpoints.json"
PROGRESS_HISTORY_JSON = "progress_history.json"

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
# Git Validator Import Fallback
# ---------------------------------------------------------------------------

try:
    from git_validator import (
        safe_git_command,
        validate_commit_hash,
        GitCommandError,
        is_git_repository,
        get_git_root,
        is_working_directory_clean,
        get_current_commit_hash,
    )
    GIT_VALIDATOR_AVAILABLE = True
except ImportError:
    GIT_VALIDATOR_AVAILABLE = False
    GitCommandError = subprocess.CalledProcessError


# ---------------------------------------------------------------------------
# Base Git functions
# ---------------------------------------------------------------------------

def _run_git(args: List[str], cwd: Optional[str] = None, timeout: int = 5) -> Tuple[int, str, str]:
    """Run git command with secure validation when available."""
    import sys
    pm = sys.modules.get("progress_manager")
    if pm is not None and hasattr(pm, "_run_git"):
        pm_func = pm._run_git
        if getattr(pm_func, "is_wrapper", None) is not True:
            return pm_func(args, cwd=cwd, timeout=timeout)

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


def _get_dirty_state_files(project_root: Path) -> List[Path]:
    """Return list of state files (whitelist only) that have uncommitted changes."""
    progress_dir = get_state_dir(project_root)
    dirty: List[Path] = []

    try:
        git_root = _resolve_repo_root(project_root)
    except Exception:
        return dirty

    for name in STATE_FILE_NAMES:
        f = progress_dir / name
        try:
            rel = str(f.relative_to(git_root))
        except ValueError:
            continue
        code, out, _ = _run_git(["status", "--porcelain", "--", rel], cwd=str(git_root))
        if code == 0 and out.strip():
            dirty.append(f)

    for dir_name in STATE_DIR_NAMES:
        d = progress_dir / dir_name
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
                    if file_path.endswith('/'):
                        dir_path = git_root / file_path
                        if dir_path.is_dir():
                            for item in dir_path.rglob('*'):
                                if item.is_file():
                                    dirty.append(item)
                        else:
                            dirty.append(git_root / file_path)
                    else:
                        dirty.append(git_root / file_path)

    return dirty


def _git_commit_state(
    state_files: List[Path], msg: str, project_root: Path
) -> Optional[str]:
    """Commit state_files using git add + git commit --only."""
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


def _auto_state_commit(
    ref: str,
    event: str,
    project_root: Path,
    progress_dir: Path,
    apply_schema_defaults: Callable[[Dict[str, Any]], None],
) -> Optional[str]:
    """Auto-commit dirty state files after a prog lifecycle command succeeds."""
    data = load_progress_json(progress_dir, apply_schema_defaults=apply_schema_defaults)
    if not data:
        return None
    if not data.get("settings", {}).get("auto_state_commit", True):
        return None

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


def _detect_default_branch(project_root: Path) -> Optional[str]:
    """Detect repository default branch using origin/HEAD when available."""
    import sys
    pm = sys.modules.get("progress_manager")
    if pm is not None and hasattr(pm, "_detect_default_branch"):
        pm_func = pm._detect_default_branch
        if getattr(pm_func, "is_wrapper", None) is not True:
            return pm_func(project_root)

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
    project_root: Path,
    base_branch: Optional[str] = None,
    task_name: Optional[str] = None,
) -> Tuple[bool, str]:
    """Execute git squash-merge sequence for a standalone task branch."""
    cwd = str(project_root)

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

    rc, _, _ = _run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=cwd)
    if rc != 0:
        return False, f"branch '{branch}' not found in local repo"

    rc, stdout, _ = _run_git(["status", "--porcelain"], cwd=cwd)
    if rc != 0 or stdout.strip():
        return False, f"working tree is dirty; commit or stash changes first"

    rc, _, err = _run_git(["checkout", base_branch], cwd=cwd)
    if rc != 0:
        return False, f"checkout {base_branch} failed: {err}"

    rc, _, err = _run_git(["merge", "--squash", branch], cwd=cwd)
    if rc != 0:
        _run_git(["reset", "--hard", "HEAD"], cwd=cwd)
        _run_git(["checkout", branch], cwd=cwd)
        return False, f"git merge --squash failed: {err}"

    description = task_name.strip() if task_name else "close standalone task"
    commit_msg = f"task({task_id}): {description}"
    rc, _, err = _run_git(["commit", "-m", commit_msg], cwd=cwd)
    if rc != 0:
        _run_git(["reset", "--hard", "HEAD"], cwd=cwd)
        _run_git(["checkout", branch], cwd=cwd)
        return False, f"git commit failed: {err}"

    rc, commit_hash, _ = _run_git(["rev-parse", "HEAD"], cwd=cwd)
    commit_hash = commit_hash.strip() if rc == 0 else ""

    rc, _, err = _run_git(["branch", "-D", branch], cwd=cwd)
    if rc != 0:
        logger.warning(
            f"squash commit {commit_hash[:8] if commit_hash else '?'} succeeded "
            f"but branch '{branch}' deletion failed: {err}. "
            f"Manual cleanup may be needed: git branch -D {branch}"
        )

    return True, commit_hash




# ---------------------------------------------------------------------------
# Context tracking and comparison
# ---------------------------------------------------------------------------



def collect_git_context(project_root: Path) -> Dict[str, Any]:
    """Collect current git/worktree context using lightweight git probes."""
    project_root_str = str(project_root.resolve())
    cwd_str = str(Path.cwd().resolve())
    context: Dict[str, Any] = {
        "workspace_mode": "unknown",
        "worktree_path": project_root_str,
        "project_root": project_root_str,
        "cwd": cwd_str,
        "git_dir": None,
        "branch": None,
        "upstream": None,
    }

    exit_code, stdout, _ = _run_git(
        ["rev-parse", "--show-toplevel"],
        cwd=str(project_root),
        timeout=5,
    )
    if exit_code != 0 or not stdout.strip():
        return context

    toplevel_raw = stdout.strip()
    try:
        toplevel = Path(toplevel_raw).resolve()
    except Exception:
        toplevel = Path(toplevel_raw)

    toplevel_str = str(toplevel)
    context["project_root"] = toplevel_str
    context["worktree_path"] = toplevel_str

    exit_code, stdout, _ = _run_git(
        ["rev-parse", "--absolute-git-dir"],
        cwd=str(toplevel),
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
        cwd=str(toplevel),
        timeout=5,
    )
    context["branch"] = stdout.strip() if exit_code == 0 and stdout.strip() else None

    exit_code, stdout, _ = _run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=str(toplevel),
        timeout=5,
    )
    context["upstream"] = stdout.strip() if exit_code == 0 and stdout.strip() else None

    return context


def build_runtime_context(
    data: Dict[str, Any],
    source: str,
    project_root: Path,
    now_str: str,
    collect_git_context_fn: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build top-level runtime_context snapshot from current repository + progress state."""
    git_context = (
        collect_git_context_fn()
        if collect_git_context_fn is not None
        else collect_git_context(project_root)
    )
    tracker_root = str(project_root.resolve())
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}

    runtime_context: Dict[str, Any] = {
        "recorded_at": now_str,
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


def build_execution_context(
    source: str,
    project_root: Path,
    now_str: str,
    collect_git_context_fn: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build workflow_state.execution_context snapshot for workflow semantic transitions."""
    git_context = (
        collect_git_context_fn()
        if collect_git_context_fn is not None
        else collect_git_context(project_root)
    )
    tracker_root = str(project_root.resolve())
    return {
        "recorded_at": now_str,
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


def _update_runtime_context(
    data: Dict[str, Any],
    source: str,
    project_root: Path,
    now_str: str,
    force: bool = False,
    collect_git_context_fn: Optional[Callable[[], Dict[str, Any]]] = None,
) -> bool:
    """Update top-level runtime_context in progress data; returns True if changed."""
    if not isinstance(data, dict):
        return False

    new_context = build_runtime_context(
        data,
        source,
        project_root,
        now_str,
        collect_git_context_fn=collect_git_context_fn,
    )
    old_context = data.get("runtime_context")

    if not force and _runtime_context_fingerprint(old_context) == _runtime_context_fingerprint(new_context):
        return False

    data["runtime_context"] = new_context
    return True


def _update_execution_context(
    workflow_state: Dict[str, Any],
    source: str,
    project_root: Path,
    now_str: str,
    collect_git_context_fn: Optional[Callable[[], Dict[str, Any]]] = None,
) -> None:
    """Refresh workflow_state.execution_context after semantic workflow progress changes."""
    if not isinstance(workflow_state, dict):
        return
    workflow_state["execution_context"] = build_execution_context(
        source,
        project_root,
        now_str,
        collect_git_context_fn=collect_git_context_fn,
    )




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


# ---------------------------------------------------------------------------
# Sync checking and risk analysis
# ---------------------------------------------------------------------------

def _parse_worktree_list_output(output: str) -> List[Dict[str, str]]:
    """Parse `git worktree list --porcelain` output."""
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

        parts = line.split(None, 1)
        if len(parts) == 2:
            key, val = parts[0], parts[1].strip()
            current[key] = val

    if current:
        entries.append(current)

    return entries


def analyze_git_sync_risks(project_root: Path) -> Dict[str, Any]:
    """Analyze repository state for sync/rebase/divergence risks."""
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

    exit_code, stdout, _ = _run_git(
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=str(project_root),
        timeout=5,
    )
    branch = stdout.strip() if exit_code == 0 and stdout.strip() else None
    report["branch"] = branch
    if not branch:
        add_issue(
            "detached_head",
            "critical",
            "Repository is in detached HEAD state.",
            "Switch back to a branch before continuing: git switch <branch>",
        )

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

    if branch:
        exit_code, stdout, _ = _run_git(
            ["worktree", "list", "--porcelain"],
            cwd=str(project_root),
            timeout=5,
        )
        if exit_code == 0 and stdout.strip():
            branch_ref = f"refs/heads/{branch}"
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


def git_sync_check(project_root: Path) -> bool:
    """Print actionable Git sync warnings."""
    report = analyze_git_sync_risks(project_root)
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


# ---------------------------------------------------------------------------
# Cleanup helper functions
# ---------------------------------------------------------------------------

def _resolve_upstream(branch: str, project_root: Path) -> Tuple[str, str]:
    """Return (remote, remote_branch) for *branch* before it is deleted."""
    if not branch:
        return ("", "")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{u}}"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=10,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ("", "")
        upstream = result.stdout.strip()
        parts = upstream.split("/", 1)
        if len(parts) == 2:
            return (parts[0], parts[1])
        return ("", "")
    except Exception:
        return ("", "")


def _remove_worktree(worktree_path: str, project_root: Path) -> bool:
    """Remove a git worktree."""
    try:
        result = subprocess.run(
            ["git", "worktree", "remove", worktree_path],
            capture_output=True,
            text=True,
            cwd=str(project_root),
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


def _delete_local_branch(branch: str, project_root: Path) -> bool:
    """Delete a local branch with git branch -d."""
    if not branch:
        return False
    try:
        result = subprocess.run(
            ["git", "branch", "-d", branch],
            capture_output=True,
            text=True,
            cwd=str(project_root),
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


def _delete_remote_branch(remote: str, remote_branch: str, project_root: Path) -> bool:
    """Push a delete to the remote."""
    if not remote or not remote_branch:
        return True
    try:
        result = subprocess.run(
            ["git", "push", remote, "--delete", remote_branch],
            capture_output=True,
            text=True,
            cwd=str(project_root),
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


def _get_head_commit(project_root: Path) -> Optional[str]:
    """Resolve current HEAD commit hash, if available."""
    try:
        if GIT_VALIDATOR_AVAILABLE:
            head = get_current_commit_hash()
            return head if head else None
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            cwd=str(project_root),
            timeout=5,
            check=False,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None
