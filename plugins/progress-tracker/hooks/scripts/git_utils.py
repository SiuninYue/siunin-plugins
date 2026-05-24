"""
git_utils.py — Git operations and runtime/execution context helpers.

Extracted from progress_manager.py (F18 modularisation, Task 3).

This module contains pure-ish git helpers: subprocess-based git invocation,
working-tree probes, auto state commits, sync-risk analysis, worktree/branch
cleanup primitives, and the squash-close sequence for standalone tasks.

Design notes
------------
- We avoid importing ``progress_manager`` at module load to prevent circular
  imports (pm.py imports from this module).  Helpers that need pm-level
  functions (``find_project_root``, ``get_progress_dir``, ``_resolve_repo_root``,
  ``load_progress_json``, ``save_progress_json``, ``_iso_now``, ``STATE_FILE_NAMES``,
  ``STATE_DIR_NAMES``, ``_parse_worktree_list_output``) use lazy imports inside
  function bodies.
- Runtime/execution context helpers live in ``git_context.py``.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Optional secure git wrapper.  Import locally so the module is independent
# of progress_manager's import graph.
try:
    from git_validator import (
        safe_git_command,
        is_git_repository,
        is_working_directory_clean,
        get_current_commit_hash,
    )
    GIT_VALIDATOR_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    GIT_VALIDATOR_AVAILABLE = False

from pm_runtime import get_progress_manager_module
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level git invocation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# State-file auto-commit helpers
# ---------------------------------------------------------------------------


def _get_dirty_state_files(project_root: Path) -> list:
    """Return list of state files (whitelist only) that have uncommitted changes.

    Uses git status --porcelain with cwd=repo_root so paths in output are
    consistently repo-root-relative, avoiding double-prefix bugs when
    project_root is a subdirectory (e.g. plugins/progress-tracker).
    """
    # Lazy lookup avoids circular imports and binds to CLI __main__ when needed.
    _pm = get_progress_manager_module()
    progress_dir = _pm.get_progress_dir()
    dirty: list = []

    try:
        git_root = _pm._resolve_repo_root(project_root)
    except Exception:
        return dirty

    for name in _pm.STATE_FILE_NAMES:
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

    for dir_name in _pm.STATE_DIR_NAMES:
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
    _pm = get_progress_manager_module()

    try:
        git_root = _pm._resolve_repo_root(project_root)
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
    _pm = get_progress_manager_module()

    data = _pm.load_progress_json()
    if not data:
        return None
    if not data.get("settings", {}).get("auto_state_commit", True):
        return None

    # Resolve project root first — needed as cwd for all git calls.
    project_root = _pm.find_project_root()

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


# ---------------------------------------------------------------------------
# Default-branch detection and squash-close sequence
# ---------------------------------------------------------------------------


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
    task_name: Optional[str] = None,
) -> Tuple[bool, str]:
    """Execute git squash-merge sequence for a standalone task branch.

    Returns (True, commit_hash) on success, (False, error_message) on failure.
    On success, base_branch has exactly +1 commit and branch is deleted.
    """
    # Late-binding via the progress_manager namespace lets tests
    # ``patch("progress_manager._run_git", ...)`` / ``_detect_default_branch``
    # affect the call graph even though both helpers physically live here.
    _pm = get_progress_manager_module()

    if project_root is None:
        project_root = _pm.find_project_root()

    cwd = str(project_root)

    # Resolve base branch
    if base_branch is None:
        base_branch = _pm._detect_default_branch(project_root)
    if not base_branch:
        for _candidate in ("main", "master"):
            _rc_br, _, _ = _pm._run_git(
                ["show-ref", "--verify", "--quiet", f"refs/heads/{_candidate}"], cwd=cwd
            )
            if _rc_br == 0:
                base_branch = _candidate
                break
    if not base_branch:
        return False, "cannot determine default branch (tried main and master)"

    # Pre-condition 1: branch must exist
    rc, _, _ = _pm._run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=cwd)
    if rc != 0:
        return False, f"branch '{branch}' not found in local repo"

    # Pre-condition 2: working tree must be clean
    rc, stdout, _ = _pm._run_git(["status", "--porcelain"], cwd=cwd)
    if rc != 0 or stdout.strip():
        return False, f"working tree is dirty; commit or stash changes first"

    # Step 1: checkout base branch
    rc, _, err = _pm._run_git(["checkout", base_branch], cwd=cwd)
    if rc != 0:
        return False, f"checkout {base_branch} failed: {err}"

    # Step 2: squash merge
    rc, _, err = _pm._run_git(["merge", "--squash", branch], cwd=cwd)
    if rc != 0:
        # Hard-reset to clean index + worktree (safe: pre-condition 2
        # guarantees a clean working tree at entry), then return to the
        # task branch so the user isn't stranded on the base branch.
        _pm._run_git(["reset", "--hard", "HEAD"], cwd=cwd)
        _pm._run_git(["checkout", branch], cwd=cwd)
        return False, f"git merge --squash failed: {err}"

    # Step 3: commit
    description = task_name.strip() if task_name else "close standalone task"
    commit_msg = f"task({task_id}): {description}"
    rc, _, err = _pm._run_git(["commit", "-m", commit_msg], cwd=cwd)
    if rc != 0:
        _pm._run_git(["reset", "--hard", "HEAD"], cwd=cwd)
        _pm._run_git(["checkout", branch], cwd=cwd)
        return False, f"git commit failed: {err}"

    # Step 4: get commit hash
    rc, commit_hash, _ = _pm._run_git(["rev-parse", "HEAD"], cwd=cwd)
    commit_hash = commit_hash.strip() if rc == 0 else ""

    # Step 5: delete task branch.
    # Uses -D (force) rather than -d (safe) because squash-merge creates a new
    # commit that does not reference the original branch, so -d's "is-merged?"
    # safety check would always fail. This is a deliberate deviation from the
    # plan's `git branch -d` to match squash-merge semantics.
    rc, _, err = _pm._run_git(["branch", "-D", branch], cwd=cwd)
    if rc != 0:
        logger.warning(
            f"squash commit {commit_hash[:8] if commit_hash else '?'} succeeded "
            f"but branch '{branch}' deletion failed: {err}. "
            f"Manual cleanup may be needed: git branch -D {branch}"
        )

    return True, commit_hash


# ---------------------------------------------------------------------------
# Sync-risk analysis
# ---------------------------------------------------------------------------


def analyze_git_sync_risks() -> Dict[str, Any]:
    """
    Analyze repository state for sync/rebase/divergence risks.

    This check is designed for SessionStart hooks and intentionally avoids
    mutating repository state.
    """
    _pm = get_progress_manager_module()

    project_root = _pm.find_project_root()
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
            worktrees = _pm._parse_worktree_list_output(stdout)
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


# ---------------------------------------------------------------------------
# Worktree / branch cleanup primitives
# ---------------------------------------------------------------------------


def _resolve_upstream(branch: str) -> tuple:
    """Return (remote, remote_branch) for *branch* before it is deleted.

    Must be called while the local branch still exists so tracking metadata
    is available.  Returns ("", "") when no upstream is configured.
    """
    _pm = get_progress_manager_module()

    if not branch:
        return ("", "")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{u}}"],
            capture_output=True,
            text=True,
            cwd=str(_pm.find_project_root()),
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
    _pm = get_progress_manager_module()

    try:
        result = subprocess.run(
            ["git", "worktree", "remove", worktree_path],
            capture_output=True,
            text=True,
            cwd=str(_pm.find_project_root()),
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
    _pm = get_progress_manager_module()

    if not branch:
        return False
    try:
        result = subprocess.run(
            ["git", "branch", "-d", branch],
            capture_output=True,
            text=True,
            cwd=str(_pm.find_project_root()),
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
    _pm = get_progress_manager_module()

    if not remote or not remote_branch:
        return True
    try:
        result = subprocess.run(
            ["git", "push", remote, "--delete", remote_branch],
            capture_output=True,
            text=True,
            cwd=str(_pm.find_project_root()),
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


def _get_head_commit() -> Optional[str]:
    """Resolve current HEAD commit hash, if available."""
    _pm = get_progress_manager_module()

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
            cwd=str(_pm.find_project_root()),
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
