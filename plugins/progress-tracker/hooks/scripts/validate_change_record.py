#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import traceback
from pathlib import Path

class ContractError(Exception):
    pass

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

def get_staged_files(repo_root):
    out = run_git_command(["diff", "--cached", "--name-only"], cwd=repo_root)
    if not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]

def get_git_file_content(repo_root, rev_path):
    try:
        return run_git_command(["show", rev_path], cwd=repo_root)
    except subprocess.CalledProcessError as e:
        if e.returncode == 128:
            return None
        print(f"Warning: git show {rev_path} failed with exit code {e.returncode}. Stderr: {e.stderr}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: git show {rev_path} failed with error: {e}", file=sys.stderr)
        return None

def validate_change_id_format(change_id):
    pattern = r"^\d{8}-[a-z0-9\-]+-[0-9a-fA-F]{4}$"
    return bool(re.match(pattern, change_id))

def main():
    try:
        _main_impl()
        sys.exit(0)
    except ContractError as ce:
        print(f"Validation Error: {ce}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("Validator crashed internally!", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

def _main_impl():
    parser = argparse.ArgumentParser(description="Validate PT change records")
    parser.add_argument("--project-root", type=str, help="Path to project root")
    args = parser.parse_args()

    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        project_root = Path(__file__).resolve().parents[2]

    try:
        repo_root_str = run_git_command(["rev-parse", "--show-toplevel"], cwd=project_root)
        repo_root = Path(repo_root_str).resolve()
    except Exception as e:
        raise RuntimeError(f"Failed to find git repository root: {e}")

    try:
        project_rel_to_repo = project_root.relative_to(repo_root)
    except ValueError as e:
        raise RuntimeError(f"Project root {project_root} is not under git repo root {repo_root}: {e}")

    high_risk_list_file = project_root / "docs" / "changes" / "high_risk_scripts.txt"
    if not high_risk_list_file.exists():
        raise ContractError(f"Missing high_risk_scripts.txt at {high_risk_list_file}")

    high_risk_rel_paths = set()
    with open(high_risk_list_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                high_risk_rel_paths.add(line)

    staged_repo_paths = get_staged_files(repo_root)
    staged_project_paths = []
    for p in staged_repo_paths:
        try:
            rel_to_proj = Path(p).relative_to(project_rel_to_repo)
            staged_project_paths.append(str(rel_to_proj))
        except ValueError:
            continue

    staged_high_risk = [p for p in staged_project_paths if p in high_risk_rel_paths]

    index_jsonl_proj_path = "docs/changes/index.jsonl"
    index_jsonl_repo_path = f"{project_rel_to_repo}/{index_jsonl_proj_path}"
    
    staged_index_content = get_git_file_content(repo_root, f":{index_jsonl_repo_path}")
    if staged_index_content is None:
        local_file = project_root / index_jsonl_proj_path
        if local_file.exists():
            staged_index_content = local_file.read_text(encoding="utf-8")
        else:
            staged_index_content = ""

    head_index_content = get_git_file_content(repo_root, f"HEAD:{index_jsonl_repo_path}")
    head_change_ids = set()
    if head_index_content:
        for line in head_index_content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "change_id" in data:
                    head_change_ids.add(data["change_id"])
            except json.JSONDecodeError:
                pass

    lines = staged_index_content.splitlines()
    seen_change_ids = set()
    newly_added_rows = []

    required_fields = {
        "change_id", "date", "component", "summary", "root_cause",
        "fixes", "touched_files", "test_command", "test_result",
        "rollback_strategy", "record_path"
    }

    for idx, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ContractError(f"index.jsonl line {idx}: Invalid JSON: {e}")

        missing = required_fields - set(row.keys())
        if missing:
            raise ContractError(f"index.jsonl line {idx}: Missing required fields: {sorted(list(missing))}")

        change_id = row["change_id"]
        if change_id in seen_change_ids:
            raise ContractError(f"index.jsonl line {idx}: Duplicate change_id: {change_id}")
        seen_change_ids.add(change_id)

        record_path_val = row["record_path"]
        if not record_path_val.startswith("docs/changes/") or not record_path_val.endswith(".md"):
            raise ContractError(
                f"index.jsonl line {idx}: record_path '{record_path_val}' must be project-root-relative path in the form 'docs/changes/<file>.md'"
            )
        
        detail_file = project_root / record_path_val
        if not detail_file.exists():
            raise ContractError(f"index.jsonl line {idx}: Detail record file does not exist at '{record_path_val}'")
        try:
            detail_file.read_text(encoding="utf-8")
        except Exception as e:
            raise ContractError(f"index.jsonl line {idx}: Detail record file at '{record_path_val}' is unreadable: {e}")

        if change_id not in head_change_ids:
            newly_added_rows.append(row)

    for row in newly_added_rows:
        cid = row["change_id"]
        if not validate_change_id_format(cid):
            raise ContractError(
                f"Newly added change_id '{cid}' must match YYYYMMDD-<slug>-<4hex> format (e.g. 20260616-workspace-entropy-a7d2)"
            )

    if staged_high_risk and not newly_added_rows:
        raise ContractError(
            f"Staged changes contain high-risk files:\n"
            f"  " + "\n  ".join(staged_high_risk) + "\n"
            f"But no newly added change records were found in index.jsonl."
        )

    print("Change record validation passed successfully.")

if __name__ == "__main__":
    main()
