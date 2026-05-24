"""
worktree_handler.py — Worktree path/ref parsing and ancestry helpers.

Extracted from progress_manager.py (F18 modularisation).

Contains pure-ish helpers that:
- Parse ``git worktree list --porcelain`` output
- Normalise worktree porcelain branch refs
- Probe branch ancestry / commits-behind
- Locate other worktrees that already track the same active feature
- Detect dirty worktrees

Higher-level orchestration helpers (``analyze_git_auto_preflight``,
``_check_other_worktrees_for_incomplete_work``, ``check_worktree_branch_consistency``)
remain in progress_manager.py because tests patch them or their dependencies
directly on that module.

Dependencies on progress_manager (``find_project_root``, ``_is_feature_deferred``,
``PROGRESS_JSON``) use lazy imports to avoid circular-import issues.
"""
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from git_utils import _run_git
from pm_runtime import get_progress_manager_module


# ---------------------------------------------------------------------------
# git worktree porcelain parsing
# ---------------------------------------------------------------------------


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


def _extract_branch_name_from_worktree_ref(ref: Optional[str]) -> Optional[str]:
    """Normalize a worktree porcelain branch ref to a branch name."""
    if not isinstance(ref, str):
        return None
    normalized = ref.strip()
    if not normalized:
        return None
    prefix = "refs/heads/"
    if normalized.startswith(prefix):
        return normalized[len(prefix):]
    return normalized


# ---------------------------------------------------------------------------
# Branch ancestry / commits-behind probes
# ---------------------------------------------------------------------------


def _local_and_origin_ref_candidates(ref: str) -> Tuple[str, ...]:
    """Return deduplicated local+origin ref candidates for ancestry checks."""
    normalized = str(ref or "").strip()
    if not normalized:
        return tuple()
    candidates = [normalized]
    if not normalized.startswith("origin/"):
        candidates.append(f"origin/{normalized}")
    return tuple(dict.fromkeys(candidates))


def _count_branch_commits_behind(
    branch: str,
    target_branch: str,
    project_root: Path,
) -> Optional[int]:
    """
    Count commits that `branch` is behind `target_branch`.

    Returns None when refs are unavailable or probe fails.
    """
    source_refs = _local_and_origin_ref_candidates(branch)
    target_refs = _local_and_origin_ref_candidates(target_branch)
    if not source_refs or not target_refs:
        return None

    for source_ref in source_refs:
        for target_ref in target_refs:
            exit_code, stdout, _ = _run_git(
                ["rev-list", "--count", f"{source_ref}..{target_ref}"],
                cwd=str(project_root),
                timeout=8,
            )
            if exit_code != 0:
                continue
            count_text = stdout.strip()
            if count_text.isdigit():
                return int(count_text)

    return None


def _is_branch_merged_into(branch: str, target: str) -> bool:
    """Return True when branch is an ancestor of target (local/origin fallback)."""
    source_refs = _local_and_origin_ref_candidates(branch)
    target_refs = _local_and_origin_ref_candidates(target)
    if not source_refs or not target_refs:
        return False

    # Lazy import so that ``patch.object(progress_manager, "_run_git", ...)``
    # in tests is honoured: callers patch the symbol on progress_manager, so we
    # dispatch through that module rather than the locally-bound git_utils ref.
    _pm = get_progress_manager_module()

    project_root = _pm.find_project_root()
    run_git = getattr(_pm, "_run_git", _run_git)
    for source_ref in source_refs:
        for target_ref in target_refs:
            exit_code, _, _ = run_git(
                ["merge-base", "--is-ancestor", source_ref, target_ref],
                cwd=str(project_root),
                timeout=10,
            )
            if exit_code == 0:
                return True
    return False


# ---------------------------------------------------------------------------
# Worktree discovery / status helpers
# ---------------------------------------------------------------------------


def _find_existing_worktree_candidates_for_feature(
    *,
    repo_root: Path,
    tracker_project_root: Path,
    current_worktree: Path,
    current_feature_id: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Find other worktrees that already track the same active feature id.

    The lookup preserves project scope by resolving tracker_project_root relative
    to repo_root, then probing the same relative path in each linked worktree.
    """
    if current_feature_id is None:
        return []

    try:
        project_rel = tracker_project_root.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return []

    exit_code, stdout, _ = _run_git(
        ["worktree", "list", "--porcelain"],
        cwd=str(repo_root),
        timeout=10,
    )
    if exit_code != 0 or not stdout.strip():
        return []

    # Lazy lookup — these symbols live on progress_manager (constant + helper).
    _pm = get_progress_manager_module()

    candidates: List[Dict[str, Any]] = []
    for entry in _parse_worktree_list_output(stdout):
        worktree_path_raw = entry.get("worktree")
        if not worktree_path_raw:
            continue

        worktree_path = Path(worktree_path_raw)
        try:
            resolved_worktree = worktree_path.resolve()
        except Exception:
            resolved_worktree = worktree_path

        if resolved_worktree == current_worktree.resolve():
            continue

        candidate_project_root = (
            resolved_worktree if project_rel == Path(".") else resolved_worktree / project_rel
        )
        progress_file = (
            candidate_project_root
            / "docs"
            / "progress-tracker"
            / "state"
            / _pm.PROGRESS_JSON
        )
        if not progress_file.exists():
            continue

        try:
            with open(progress_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue

        if data.get("current_feature_id") != current_feature_id:
            continue

        matching_feature: Optional[Dict[str, Any]] = None
        features = data.get("features")
        if isinstance(features, list):
            for feature in features:
                if isinstance(feature, dict) and feature.get("id") == current_feature_id:
                    matching_feature = feature
                    break

        if isinstance(matching_feature, dict):
            if matching_feature.get("completed", False):
                continue
            if _pm._is_feature_deferred(matching_feature):
                continue

        candidates.append(
            {
                "worktree_path": str(resolved_worktree),
                "project_root": str(candidate_project_root),
                "branch": _extract_branch_name_from_worktree_ref(entry.get("branch")),
                "current_feature_id": current_feature_id,
            }
        )

    candidates.sort(key=lambda item: str(item.get("worktree_path") or ""))
    return candidates


def _is_worktree_dirty(worktree_path: Optional[str]) -> bool:
    """Return True if the given path has uncommitted changes.

    Falls back to the project root when worktree_path is None/empty.
    """
    # Lazy lookup to avoid circular dependency with progress_manager.
    _pm = get_progress_manager_module()

    cwd = worktree_path if worktree_path else str(_pm.find_project_root())
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
