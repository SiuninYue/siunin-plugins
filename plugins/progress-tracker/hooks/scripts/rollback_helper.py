#!/usr/bin/env python3
import argparse
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Optional

def run_git_command(args, cwd=None):
    import os
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    try:
        res = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            check=True
        )
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise e


def run_cli_command(args, cwd=None):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to run command {' '.join(map(str, args))}: {e}")

def find_commit_sha(change_id, project_root):
    # Find repo root
    try:
        repo_root_str = run_git_command(["rev-parse", "--show-toplevel"], cwd=project_root)
        repo_root = Path(repo_root_str).resolve()
        project_rel = project_root.relative_to(repo_root)
    except Exception as e:
        raise RuntimeError(f"Failed to find git repository: {e}")

    index_path = project_rel / "docs" / "changes" / "index.jsonl"
    
    # We use -S to find the exact change_id addition.
    # Diff filter A limits it to added commit.
    query = f'"change_id": "{change_id}"'
    args = [
        "log", 
        "--all",
        f"-S{query}", 
        "--pretty=format:%H", 
        "--", 
        str(index_path)
    ]
    
    try:
        out = run_git_command(args, cwd=repo_root)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git log failed: {e.stderr}")

    candidate_shas = [line.strip() for line in out.splitlines() if line.strip()]
    if not candidate_shas:
        raise ValueError(f"No commit found introducing change_id '{change_id}' in index.jsonl")

    # Filter shas to only commits that ADDED (not modified/removed) the change_id line
    added_shas = []
    for sha in candidate_shas:
        try:
            diff_out = run_git_command(["show", sha, "--", str(index_path)], cwd=repo_root)
            has_plus = False
            has_minus = False
            for line in diff_out.splitlines():
                if query in line:
                    if line.startswith("+") and not line.startswith("+++"):
                        has_plus = True
                    elif line.startswith("-") and not line.startswith("---"):
                        has_minus = True
            if has_plus and not has_minus:
                added_shas.append(sha)
        except Exception:
            added_shas.append(sha)

    if not added_shas:
        added_shas = candidate_shas

    # Deterministic sort by commit ordering (newest first in git history)
    try:
        rev_list_str = run_git_command(["rev-list", "--all"], cwd=repo_root)
        rev_list = [line.strip() for line in rev_list_str.splitlines() if line.strip()]
        added_shas.sort(key=lambda s: rev_list.index(s) if s in rev_list else len(rev_list))
    except Exception:
        pass

    if len(added_shas) > 1:
        print(f"Warning: Multiple commits found introducing change_id '{change_id}' (cherry-picks or squash merges):", file=sys.stderr)
        for s in added_shas:
            print(f"  - {s}", file=sys.stderr)
        print(f"Selecting the most recent one: {added_shas[0]}", file=sys.stderr)

    return added_shas[0], added_shas

def check_archive_available(project_root):
    # Check if we have any valid archived checkpoints/snapshots in the progress_archive directory
    archive_dir = project_root / "docs" / "progress-tracker" / "state" / "progress_archive"
    if not archive_dir.exists() or not archive_dir.is_dir():
        return False
    try:
        archives = list(archive_dir.glob("*.progress.json"))
        return len(archives) > 0
    except Exception:
        return False


def find_latest_archive_id(project_root) -> Optional[str]:
    archive_dir = project_root / "docs" / "progress-tracker" / "state" / "progress_archive"
    if not archive_dir.exists() or not archive_dir.is_dir():
        return None

    archives = sorted(archive_dir.glob("*.progress.json"), key=lambda path: path.name, reverse=True)
    if not archives:
        return None

    latest_name = archives[0].name
    return latest_name[: -len(".progress.json")]


def run_prog_command(project_root: Path, *prog_args: str):
    prog_path = project_root / "prog"
    if not prog_path.exists():
        raise RuntimeError(f"prog entrypoint not found at {prog_path}")

    return run_cli_command(
        [str(prog_path), "--project-root", str(project_root), *prog_args],
        cwd=project_root,
    )


def print_command_output(result) -> None:
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)


def run_reconcile_check(project_root: Path) -> bool:
    result = run_prog_command(project_root, "reconcile-state", "--check")
    print_command_output(result)
    return result.returncode == 0


def run_restore_archive(project_root: Path, archive_id: str) -> bool:
    result = run_prog_command(project_root, "restore-archive", archive_id, "--force")
    print_command_output(result)
    return result.returncode == 0


def run_git_revert(project_root: Path, sha: str) -> bool:
    repo_root = Path(run_git_command(["rev-parse", "--show-toplevel"], cwd=project_root))
    status = run_git_command(["status", "--porcelain"], cwd=repo_root)
    if status:
        raise RuntimeError("Working directory is not clean. Commit or stash changes before rollback.")

    result = run_cli_command(
        ["git", "revert", "--no-edit", sha],
        cwd=repo_root,
    )
    print_command_output(result)
    if result.returncode != 0:
        abort_result = run_cli_command(
            ["git", "revert", "--abort"],
            cwd=repo_root,
        )
        if abort_result.returncode != 0:
            print_command_output(abort_result)
    return result.returncode == 0

def run_rollback(change_id, project_root, mock_archive_available=None, mock_reconcile_pass=None):
    project_root = Path(project_root).resolve()
    print(f"Starting rollback SOP for change_id: {change_id}")
    
    # 1. Locate Commit SHA
    try:
        sha, all_shas = find_commit_sha(change_id, project_root)
        print(f"[Lookup] Located target commit SHA: {sha}")
    except Exception as e:
        print(f"[Lookup] Failed to locate commit: {e}", file=sys.stderr)
        sys.exit(2)

    # 2. Determine Route (A or B)
    archive_avail = check_archive_available(project_root) if mock_archive_available is None else mock_archive_available

    if archive_avail:
        archive_id = find_latest_archive_id(project_root)
        if not archive_id:
            print("[Route A] Archive directory exists but no valid archive ID was found. Falling back to Route B.", file=sys.stderr)
            archive_avail = False
        else:
            print("[Route A] Archive is available. Attempting restore-archive + reconcile check...")
            print(f"[Route A] Restoring checkpoint: {archive_id}")
            if not run_restore_archive(project_root, archive_id):
                print("[Route A] restore-archive failed. Falling back to Route B.", file=sys.stderr)
                archive_avail = False

    if archive_avail:
        reconcile_ok = run_reconcile_check(project_root) if mock_reconcile_pass is None else mock_reconcile_pass
        if reconcile_ok:
            print("[Route A] Reconcile-state --check PASSED. Rollback Route A completed successfully.")
            return True
        else:
            print("[Route A] Reconcile check failed. Falling back to Route C.", file=sys.stderr)
            # Route C
            trigger_route_c()
            sys.exit(1)
    else:
        print("[Route B] Archive NOT available. Attempting git revert + reconcile check...")
        print(f"[Route B] Command: git revert --no-edit {sha}")
        if not run_git_revert(project_root, sha):
            print("[Route B] git revert failed.", file=sys.stderr)
            sys.exit(2)

        reconcile_ok = run_reconcile_check(project_root) if mock_reconcile_pass is None else mock_reconcile_pass
        if reconcile_ok:
            print("[Route B] Reconcile-state --check PASSED.")
            print("[Route B] MANUAL CONFIRMATION REQUIRED: Please manually verify the state is correct.")
            return True
        else:
            print("[Route B] Reconcile check failed. Falling back to Route C.", file=sys.stderr)
            # Route C
            trigger_route_c()
            sys.exit(1)

def trigger_route_c():
    print("\n==================================================", file=sys.stderr)
    print("[Route C] EMERGENCY: Reconcile check failed after rollback attempt!", file=sys.stderr)
    print("Please run the following diagnostic commands to troubleshoot:\n", file=sys.stderr)
    print("  python3 plugins/progress-tracker/hooks/scripts/progress_manager.py reconcile --json", file=sys.stderr)
    print("  git status && git worktree list", file=sys.stderr)
    print("  bash scripts/check_pm_boundary.sh", file=sys.stderr)
    print("==================================================\n", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="PT Rollback SOP Helper")
    parser.add_argument("command", choices=["find-sha", "rollback"])
    parser.add_argument("change_id")
    parser.add_argument("--project-root", type=str, help="Path to project root")
    args = parser.parse_args()

    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        project_root = Path(__file__).resolve().parents[2]

    try:
        if args.command == "find-sha":
            sha, all_shas = find_commit_sha(args.change_id, project_root)
            print(sha)
        elif args.command == "rollback":
            run_rollback(args.change_id, project_root)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
