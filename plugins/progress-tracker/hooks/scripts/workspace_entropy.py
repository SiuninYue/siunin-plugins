"""Workspace entropy reporting and dirty-change classification.

Standalone submodule under hooks/scripts/. Must NOT import progress_manager
(no reverse dependency). May import from git_utils, worktree_handler,
audit_log, state_io, and stdlib.
"""

import json
import subprocess
import sys
from pathlib import Path

TRACKER_STATE_PREFIXES = (
    "docs/progress-tracker/state/",
    "plugins/progress-tracker/docs/progress-tracker/state/",
    "plugins/note-organizer/docs/progress-tracker/state/",
    "plugins/super-product-manager/docs/progress-tracker/state/",
)


def _porcelain_path(line: str) -> str:
    return line[3:].strip()


def classify_dirty_entries(entries: list[str]) -> dict[str, list[str]]:
    result = {"auto_commit": [], "quarantine": [], "block": []}
    for entry in entries:
        if len(entry) < 4:
            continue
        status = entry[:2]
        path = _porcelain_path(entry)
        if not path:
            continue
        if "D" in status and not path.startswith(TRACKER_STATE_PREFIXES):
            result["block"].append(path)
        elif path.startswith(TRACKER_STATE_PREFIXES):
            result["auto_commit"].append(path)
        else:
            result["quarantine"].append(path)
    return result


PROTECTED_BRANCHES = {"main", "master", "develop", "dev"}


def classify_branches(
    branches: list[dict[str, object]], *, default_branch: str
) -> dict[str, list[str]]:
    report = {"delete_local": [], "review": [], "keep": []}
    protected = set(PROTECTED_BRANCHES)
    protected.add(default_branch)
    for branch in branches:
        name = str(branch.get("name") or "")
        if not name:
            continue
        if (
            name not in protected
            and branch.get("merged") is True
            and branch.get("is_current") is not True
            and branch.get("has_worktree") is not True
        ):
            report["delete_local"].append(name)
        elif branch.get("merged") is False and name not in protected:
            report["review"].append(name)
        else:
            report["keep"].append(name)
    return report


def _get_git_status_entries(project_root: Path) -> list[str]:
    """Return raw git status --porcelain lines."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _get_local_branches(project_root: Path, default_branch: str) -> list[dict]:
    """Collect local branches with merged/current/worktree metadata."""
    # Get all local branches
    result = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []

    # Get current branch
    current_result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    current_branch = current_result.stdout.strip() if current_result.returncode == 0 else ""

    # Get worktree branches
    wt_result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    worktree_branches: set[str] = set()
    for line in (wt_result.stdout.splitlines() if wt_result.returncode == 0 else []):
        if line.startswith("branch refs/heads/"):
            worktree_branches.add(line[len("branch refs/heads/"):].strip())

    branches = []
    for name in result.stdout.splitlines():
        name = name.strip()
        if not name:
            continue
        # Check if merged into default branch
        merge_check = subprocess.run(
            ["git", "merge-base", "--is-ancestor", name, default_branch],
            cwd=str(project_root),
            capture_output=True,
            check=False,
        )
        merged = merge_check.returncode == 0
        branches.append({
            "name": name,
            "is_current": name == current_branch,
            "merged": merged,
            "has_worktree": name in worktree_branches,
        })
    return branches


def _detect_default_branch(project_root: Path) -> str:
    """Detect default branch (main/master fallback)."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        ref = result.stdout.strip()
        if ref.startswith("origin/"):
            return ref[len("origin/"):]
    # Fallback: check if main exists, else master
    for candidate in ("main", "master"):
        check = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"],
            cwd=str(project_root),
            capture_output=True,
            check=False,
        )
        if check.returncode == 0:
            return candidate
    return "main"


def build_entropy_report(project_root: Path) -> dict:
    """Build a full entropy report for the workspace."""
    default_branch = _detect_default_branch(project_root)
    entries = _get_git_status_entries(project_root)
    dirty_changes = classify_dirty_entries(entries)

    branches = _get_local_branches(project_root, default_branch)
    branch_report = classify_branches(branches, default_branch=default_branch)

    # Determine overall status
    if dirty_changes["block"]:
        decision = "block"
    elif dirty_changes["auto_commit"] or dirty_changes["quarantine"] or branch_report["delete_local"]:
        decision = "safe_fix_available"
    else:
        decision = "ok"

    return {
        "status": "ok",
        "decision": decision,
        "dirty_changes": dirty_changes,
        "branches": branch_report,
        "routes": {"repair": [], "block": []},
        "worktrees": {"prune": False, "block": []},
    }


class EntropyPreflightResult:
    """Result from run_safe_entropy_preflight."""

    def __init__(self, report: dict) -> None:
        self.report = report
        self.has_red_blocks = bool(report.get("dirty_changes", {}).get("block"))

    def to_block_payload(self) -> dict:
        return {
            "status": "blocked",
            "reason": "workspace_entropy_red",
            "block": self.report.get("dirty_changes", {}).get("block", []),
            "message": "Workspace entropy check found destructive pending changes. Resolve before continuing.",
            "recommended_next_step": "Run `prog entropy-fix --safe` to see safe actions, or resolve manually.",
        }


def run_safe_entropy_preflight(project_root: Path) -> EntropyPreflightResult:
    """Run entropy check and return result. Does NOT mutate workspace."""
    report = build_entropy_report(project_root)
    return EntropyPreflightResult(report)


def entropy_check_command(output_json: bool = False) -> int:
    """Inspect workspace entropy without mutation."""
    try:
        project_root = Path.cwd()
        report = build_entropy_report(project_root)
        if output_json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(f"Entropy decision: {report['decision']}")
            if report["dirty_changes"]["block"]:
                print(f"  BLOCK: {report['dirty_changes']['block']}")
            if report["dirty_changes"]["auto_commit"]:
                print(f"  Auto-commit: {report['dirty_changes']['auto_commit']}")
            if report["dirty_changes"]["quarantine"]:
                print(f"  Quarantine: {report['dirty_changes']['quarantine']}")
            if report["branches"]["delete_local"]:
                print(f"  Delete branches: {report['branches']['delete_local']}")
        return 0
    except Exception as exc:
        print(f"entropy-check error: {exc}", file=sys.stderr)
        return 1


def entropy_fix_command(*, safe: bool = False, apply: bool = False, output_json: bool = False) -> int:
    """Apply workspace entropy cleanup actions."""
    try:
        project_root = Path.cwd()
        report = build_entropy_report(project_root)
        actions_taken: list[str] = []

        if report["dirty_changes"]["block"]:
            # Red: always block
            result = {
                "status": "blocked",
                "reason": "workspace_entropy_red",
                "block": report["dirty_changes"]["block"],
                "actions": [],
            }
            if output_json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(f"BLOCKED: red entropy detected: {report['dirty_changes']['block']}")
            return 1

        # Green: delete merged branches (--apply enables the same green actions for now;
        # yellow quarantine actions are reserved for a future iteration)
        if safe or apply:
            for branch in report["branches"]["delete_local"]:
                rc = subprocess.run(
                    ["git", "branch", "-d", branch],
                    cwd=str(project_root),
                    capture_output=True,
                    check=False,
                )
                if rc.returncode == 0:
                    actions_taken.append(f"deleted_branch:{branch}")

        result = {
            "status": "ok",
            "decision": report["decision"],
            "actions": actions_taken,
            "summary": {
                "category": "status",
                "source": "prog_update",
                "summary": "Workspace entropy safe-fix applied",
                "refs": ["entropy:safe_fix", "command:entropy-fix"],
            },
            "dirty_changes": report["dirty_changes"],
            "branches": report["branches"],
        }
        if output_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            if actions_taken:
                print(f"Applied {len(actions_taken)} green action(s): {actions_taken}")
            else:
                print("No green actions to apply.")
        return 0
    except Exception as exc:
        print(f"entropy-fix error: {exc}", file=sys.stderr)
        return 1
