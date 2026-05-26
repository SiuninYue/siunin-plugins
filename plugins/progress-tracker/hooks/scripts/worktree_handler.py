"""
worktree_handler.py — Worktree operational and inspection helpers.

Extracted from progress_manager.py (F18 modularisation).
"""
import json
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import git_utils
from git_utils import _run_git

PROGRESS_JSON = "progress.json"


def _is_feature_deferred(feature: Dict[str, Any]) -> bool:
    """Helper to check if a feature is deferred."""
    return bool(feature.get("deferred", False))


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


def _find_existing_worktree_candidates_for_feature(
    *,
    repo_root: Path,
    tracker_project_root: Path,
    current_worktree: Path,
    current_feature_id: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Find other worktrees that already track the same active feature id.
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
            / PROGRESS_JSON
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
            if _is_feature_deferred(matching_feature):
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


def _is_branch_merged_into(branch: str, target: str, project_root: Path) -> bool:
    """Return True when branch is an ancestor of target (local/origin fallback)."""
    import sys
    pm = sys.modules.get("progress_manager")
    if pm is not None and hasattr(pm, "_is_branch_merged_into"):
        pm_func = pm._is_branch_merged_into
        if getattr(pm_func, "is_wrapper", None) is not True:
            return pm_func(branch, target)

    source_refs = _local_and_origin_ref_candidates(branch)
    target_refs = _local_and_origin_ref_candidates(target)
    if not source_refs or not target_refs:
        return False

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


def _is_worktree_dirty(worktree_path: Optional[str], project_root: Path) -> bool:
    """Return True if the given path has uncommitted changes."""
    import sys
    pm = sys.modules.get("progress_manager")
    if pm is not None and hasattr(pm, "_is_worktree_dirty"):
        pm_func = pm._is_worktree_dirty
        if getattr(pm_func, "is_wrapper", None) is not True:
            return pm_func(worktree_path)

    cwd = worktree_path if worktree_path else str(project_root)
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


def check_worktree_branch_consistency(
    command: str,
    *,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    collect_git_context_fn: Callable[[], Dict[str, Any]],
    compare_contexts_fn: Callable[..., Dict[str, Any]],
    find_project_root_fn: Callable[[], Path],
    detect_default_branch_fn: Callable[[Path], Optional[str]],
) -> bool:
    """
    Fail-closed check: verify current worktree/branch matches workflow_state.execution_context.

    Returns True if context matches or no constraint is recorded.
    Returns False (and prints recovery guidance) on mismatch.
    """
    data = load_progress_json_fn()
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

    current_ctx = collect_git_context_fn()
    comparison = compare_contexts_fn(
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
        project_root = find_project_root_fn()
        default_branch = detect_default_branch_fn(project_root)
        if default_branch and current_branch == default_branch:
            if _is_branch_merged_into(expected_branch, default_branch, project_root):
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

