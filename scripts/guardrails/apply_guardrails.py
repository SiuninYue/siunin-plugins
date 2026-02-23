#!/usr/bin/env python3
"""Apply and rollback Git/GitHub guardrails across personal repositories."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

SCRIPT_VERSION = "1.0.0"
WORKFLOW_FILE_PATH = ".github/workflows/required-check.yml"
SCAN_ROOT = Path("/Users/siunin/Projects")

ROOT_DIR = Path(__file__).resolve().parents[2]
OPS_DIR = ROOT_DIR / "docs" / "ops"
TEMPLATE_PATH = Path(__file__).resolve().parent / "required-check.yml.tpl"
PROTECTION_PAYLOAD_PATH = Path(__file__).resolve().parent / "protection_payload.json"

GLOBAL_FILE_PATHS = [
    Path("/Users/siunin/.gitconfig"),
    Path("/Users/siunin/.config/gh/config.yml"),
    Path("/Users/siunin/.codex/AGENTS.md"),
]

TARGET_GIT_CONFIG = {
    "pull.rebase": "true",
    "pull.ff": "only",
    "rebase.autostash": "true",
    "rebase.updaterefs": "true",
    "rerere.enabled": "true",
    "fetch.prune": "true",
    "merge.conflictstyle": "zdiff3",
    "push.autosetupremote": "true",
}

SSH_INSTEADOF_KEY = "url.git@github.com:.insteadOf"
SSH_INSTEADOF_VALUE = "https://github.com/"

GH_SECTION = """## GH Command Execution

- For this environment, any command starting with `gh` must run with escalated permissions by default.
- Do not attempt `gh` commands in sandbox first.
- Reason: sandbox sessions may fail to access macOS keychain credentials even when host `gh auth` is valid.
"""

GIT_TRANSPORT_SECTION = """## Git Transport

- Default to SSH transport for Git remotes when configuring repositories.
- Prefer `git@github.com:<owner>/<repo>.git` over HTTPS for `origin` when requested.
"""


@dataclass
class CmdResult:
    returncode: int
    stdout: str
    stderr: str


class GuardrailsError(Exception):
    """Fatal error for command orchestration."""


class PartialFailure(Exception):
    """Non-fatal failure for a single target."""


class GuardrailsRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.timestamp = utc_timestamp()
        self.report: dict[str, Any] = {
            "metadata": {
                "timestamp_utc": self.timestamp,
                "script_version": SCRIPT_VERSION,
                "mode": args.mode,
                "owner": args.owner,
                "rewrite_remotes": bool(getattr(args, "rewrite_remotes", False)),
                "cwd": str(Path.cwd()),
            },
            "summary": {},
            "global_changes": {
                "git_config": [],
                "gh_config": [],
                "agents_file": {},
            },
            "repo_results": [],
            "local_remote_results": [],
            "errors": [],
            "retry_hints": [],
        }
        self.backup: dict[str, Any] = {
            "metadata": {
                "timestamp_utc": self.timestamp,
                "script_version": SCRIPT_VERSION,
                "mode": args.mode,
                "owner": args.owner,
                "rewrite_remotes": bool(getattr(args, "rewrite_remotes", False)),
            },
            "global_file_snapshots": {},
            "global_git_values_before": {},
            "gh_config_before": {},
            "repo_protection_before": [],
            "workflow_file_before": [],
            "local_remote_before": [],
        }

    def run(self) -> int:
        if self.args.mode == "rollback":
            return self.run_rollback()
        return self.run_governance()

    def run_governance(self) -> int:
        ensure_ops_dir()
        self.preflight_checks(require_scopes=True)

        protection_target = load_json_file(PROTECTION_PAYLOAD_PATH)
        workflow_template = TEMPLATE_PATH.read_text(encoding="utf-8")

        # Snapshot global state before any change.
        self.capture_global_backups()

        repos = self.discover_target_repos(self.args.owner)
        repo_states = self.collect_repo_states(repos)
        local_remotes = self.scan_local_remotes(self.args.owner, {r["full_name"] for r in repos})

        self.backup["repo_protection_before"] = [
            {
                "repo": state["repo"],
                "default_branch": state["default_branch"],
                "protection": state.get("protection_before"),
            }
            for state in repo_states
        ]
        self.backup["workflow_file_before"] = [
            {
                "repo": state["repo"],
                "default_branch": state["default_branch"],
                "workflow": state.get("workflow_before"),
            }
            for state in repo_states
        ]
        self.backup["local_remote_before"] = [
            {
                "path": entry["path"],
                "repo": entry.get("repo"),
                "origin_before": entry.get("origin_before"),
            }
            for entry in local_remotes
            if entry.get("repo")
        ]

        backup_path = OPS_DIR / f"guardrails-backup-{self.timestamp}.json"
        write_json_file(backup_path, self.backup)
        self.report["backup_file"] = str(backup_path)

        if self.args.mode == "apply":
            self.apply_global_settings()
        else:
            self.plan_global_settings_changes()

        for state in repo_states:
            self.process_repo_state(state, workflow_template, protection_target)

        self.process_local_remotes(local_remotes)

        report_path = OPS_DIR / f"guardrails-report-{self.timestamp}.json"
        self.finalize_report(repos, repo_states, local_remotes, report_path)
        write_json_file(report_path, self.report)

        print(f"Report written: {report_path}")
        print(f"Backup written: {backup_path}")

        if self.report["errors"]:
            return 2
        return 0

    def run_rollback(self) -> int:
        ensure_ops_dir()
        backup_file = Path(self.args.backup_file)
        if not backup_file.exists():
            raise GuardrailsError(f"Backup file not found: {backup_file}")

        backup_data = load_json_file(backup_file)
        self.backup = backup_data
        owner = backup_data.get("metadata", {}).get("owner")
        if owner:
            self.report["metadata"]["owner"] = owner

        self.preflight_checks(require_scopes=True)

        self.restore_global_files(backup_data)
        self.restore_global_git_values(backup_data)
        self.restore_local_remotes(backup_data)
        self.restore_repo_workflows(backup_data)
        self.restore_repo_protections(backup_data)

        report_path = OPS_DIR / f"guardrails-report-{self.timestamp}.json"
        self.finalize_report([], [], [], report_path)
        write_json_file(report_path, self.report)
        print(f"Report written: {report_path}")

        if self.report["errors"]:
            return 2
        return 0

    def preflight_checks(self, require_scopes: bool) -> None:
        result = run_cmd(["gh", "auth", "status", "-h", "github.com"], check=False)
        combined = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode != 0:
            raise GuardrailsError(
                "gh auth status failed. Please run `gh auth login` first.\n" + combined
            )

        if require_scopes:
            lower = combined.lower()
            if "repo" not in lower or "workflow" not in lower:
                raise GuardrailsError(
                    "gh auth is missing required scopes. Need: repo, workflow.\n" + combined
                )

    def capture_global_backups(self) -> None:
        for path in GLOBAL_FILE_PATHS:
            self.backup["global_file_snapshots"][str(path)] = snapshot_file(path)

        for key in TARGET_GIT_CONFIG:
            self.backup["global_git_values_before"][key] = git_config_get(key)
        self.backup["global_git_values_before"][SSH_INSTEADOF_KEY] = git_config_get_all(SSH_INSTEADOF_KEY)
        self.backup["gh_config_before"]["git_protocol"] = gh_config_get("git_protocol")

    def discover_target_repos(self, owner: str) -> list[dict[str, Any]]:
        cmd = [
            "gh",
            "api",
            "--paginate",
            "/user/repos?per_page=100",
            "--jq",
            ".[] | @base64",
        ]
        result = run_cmd(cmd)
        repos: list[dict[str, Any]] = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            encoded = line
            if encoded.startswith('"') and encoded.endswith('"'):
                encoded = json.loads(encoded)
            try:
                decoded = base64.b64decode(encoded).decode("utf-8")
                repo = json.loads(decoded)
            except Exception as exc:  # pragma: no cover - defensive parsing
                self.add_error("repo_discovery", "N/A", f"Failed to parse repo line: {exc}")
                continue

            if repo.get("archived") or repo.get("fork"):
                continue
            owner_login = ((repo.get("owner") or {}).get("login") or "").lower()
            if owner_login != owner.lower():
                continue

            repos.append(
                {
                    "full_name": repo["full_name"],
                    "name": repo["name"],
                    "default_branch": repo["default_branch"],
                }
            )

        repos.sort(key=lambda item: item["full_name"].lower())
        return repos

    def collect_repo_states(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        states: list[dict[str, Any]] = []
        for repo in repos:
            slug = repo["full_name"]
            default_branch = repo["default_branch"]
            state: dict[str, Any] = {
                "repo": slug,
                "default_branch": default_branch,
                "protection_before": None,
                "workflow_before": {
                    "exists": False,
                    "sha": None,
                    "content": None,
                },
                "open_prs": {
                    "count": 0,
                    "sample": [],
                },
                "errors": [],
            }

            try:
                state["protection_before"] = self.get_branch_protection(slug, default_branch)
            except Exception as exc:
                message = f"Failed to read branch protection: {exc}"
                state["errors"].append(message)
                self.add_error("repo_state", slug, message)

            try:
                workflow_info = self.get_workflow_file(slug, default_branch)
                state["workflow_before"] = workflow_info
            except Exception as exc:
                message = f"Failed to read required-check workflow: {exc}"
                state["errors"].append(message)
                self.add_error("repo_state", slug, message)

            try:
                prs = self.get_open_prs(slug)
                state["open_prs"] = prs
            except Exception as exc:
                message = f"Failed to read open PRs: {exc}"
                state["errors"].append(message)
                self.add_error("repo_state", slug, message)

            states.append(state)

        return states

    def process_repo_state(
        self,
        state: dict[str, Any],
        workflow_template: str,
        protection_target: dict[str, Any],
    ) -> None:
        slug = state["repo"]
        branch = state["default_branch"]

        repo_result: dict[str, Any] = {
            "repo": slug,
            "default_branch": branch,
            "workflow": {},
            "protection": {},
            "open_prs": state["open_prs"],
            "errors": list(state["errors"]),
        }

        desired_workflow = render_workflow(workflow_template, branch)
        workflow_before = state["workflow_before"]
        workflow_changed = False
        protection_changed = False

        try:
            workflow_result = self.apply_or_plan_workflow(slug, branch, workflow_before, desired_workflow)
            repo_result["workflow"] = workflow_result
            workflow_changed = workflow_result.get("changed", False)
        except Exception as exc:
            message = f"Workflow operation failed: {exc}"
            repo_result["workflow"] = {
                "status": "failed",
                "changed": False,
                "reason": message,
            }
            repo_result["errors"].append(message)
            self.add_error("workflow", slug, message)

        try:
            protection_result = self.apply_or_plan_protection(
                slug,
                branch,
                state.get("protection_before"),
                protection_target,
            )
            repo_result["protection"] = protection_result
            protection_changed = protection_result.get("changed", False)
        except Exception as exc:
            message = f"Protection operation failed: {exc}"
            repo_result["protection"] = {
                "status": "failed",
                "changed": False,
                "reason": message,
            }
            repo_result["errors"].append(message)
            self.add_error("protection", slug, message)

        repo_result["changed"] = workflow_changed or protection_changed
        self.report["repo_results"].append(repo_result)

    def get_branch_protection(self, repo: str, branch: str) -> dict[str, Any] | None:
        path = f"/repos/{repo}/branches/{quote(branch, safe='')}/protection"
        response = gh_api(path, method="GET", expect_404=True)
        return response

    def get_workflow_file(self, repo: str, branch: str) -> dict[str, Any]:
        ref = quote(branch, safe="")
        path = f"/repos/{repo}/contents/{WORKFLOW_FILE_PATH}?ref={ref}"
        response = gh_api(path, method="GET", expect_404=True)
        if response is None:
            return {"exists": False, "sha": None, "content": None}

        encoded = (response.get("content") or "").replace("\n", "")
        decoded = base64.b64decode(encoded).decode("utf-8") if encoded else ""
        return {
            "exists": True,
            "sha": response.get("sha"),
            "content": decoded,
        }

    def get_open_prs(self, repo: str) -> dict[str, Any]:
        response = gh_api(f"/repos/{repo}/pulls?state=open&per_page=100", method="GET")
        pulls = response if isinstance(response, list) else []
        sample = []
        for pr in pulls[:5]:
            sample.append({"number": pr.get("number"), "title": pr.get("title")})

        return {
            "count": len(pulls),
            "sample": sample,
            "truncated": len(pulls) > len(sample),
        }

    def apply_or_plan_workflow(
        self,
        repo: str,
        branch: str,
        before: dict[str, Any],
        desired_content: str,
    ) -> dict[str, Any]:
        before_exists = bool(before.get("exists"))
        before_content = normalize_text(before.get("content")) if before_exists else None
        desired_norm = normalize_text(desired_content)

        if before_exists and before_content == desired_norm:
            return {
                "status": "unchanged",
                "changed": False,
                "reason": "required-check workflow already matches template",
            }

        if self.args.mode != "apply":
            return {
                "status": "would_update" if before_exists else "would_create",
                "changed": True,
                "reason": "dry-run only",
            }

        payload = {
            "message": f"chore: enforce required-check workflow on {branch}",
            "content": base64.b64encode(desired_norm.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if before_exists and before.get("sha"):
            payload["sha"] = before["sha"]

        gh_api(f"/repos/{repo}/contents/{WORKFLOW_FILE_PATH}", method="PUT", data=payload)

        after = self.get_workflow_file(repo, branch)
        if not after.get("exists") or normalize_text(after.get("content")) != desired_norm:
            raise PartialFailure("workflow update verification failed")

        return {
            "status": "updated" if before_exists else "created",
            "changed": True,
            "reason": "workflow file synchronized",
        }

    def apply_or_plan_protection(
        self,
        repo: str,
        branch: str,
        before_raw: dict[str, Any] | None,
        target_payload: dict[str, Any],
    ) -> dict[str, Any]:
        current_norm = normalize_protection(before_raw)
        target_norm = normalize_target_protection(target_payload)

        if current_norm == target_norm:
            return {
                "status": "unchanged",
                "changed": False,
                "reason": "branch protection already matches target",
            }

        if self.args.mode != "apply":
            return {
                "status": "would_update",
                "changed": True,
                "reason": "dry-run only",
                "diff": {
                    "current": current_norm,
                    "target": target_norm,
                },
            }

        gh_api(
            f"/repos/{repo}/branches/{quote(branch, safe='')}/protection",
            method="PUT",
            data=target_payload,
        )

        after_raw = self.get_branch_protection(repo, branch)
        if normalize_protection(after_raw) != target_norm:
            raise PartialFailure("branch protection verification failed")

        return {
            "status": "updated",
            "changed": True,
            "reason": "branch protection synchronized",
        }

    def plan_global_settings_changes(self) -> None:
        git_changes = []
        for key, target in TARGET_GIT_CONFIG.items():
            current = git_config_get(key)
            git_changes.append(
                {
                    "key": key,
                    "before": current,
                    "after": target,
                    "changed": current != target,
                    "status": "would_update" if current != target else "unchanged",
                }
            )

        instead_values = git_config_get_all(SSH_INSTEADOF_KEY)
        missing_instead = SSH_INSTEADOF_VALUE not in instead_values
        git_changes.append(
            {
                "key": SSH_INSTEADOF_KEY,
                "before": instead_values,
                "after": [*sorted(set(instead_values + [SSH_INSTEADOF_VALUE]))],
                "changed": missing_instead,
                "status": "would_add" if missing_instead else "unchanged",
            }
        )

        gh_current = gh_config_get("git_protocol")
        gh_change = {
            "key": "git_protocol",
            "before": gh_current,
            "after": "ssh",
            "changed": gh_current != "ssh",
            "status": "would_update" if gh_current != "ssh" else "unchanged",
        }

        agents_path = Path("/Users/siunin/.codex/AGENTS.md")
        before = read_text_if_exists(agents_path)
        after = ensure_agents_rules(before)
        agents_change = {
            "path": str(agents_path),
            "changed": normalize_text(before) != normalize_text(after),
            "status": "would_update" if normalize_text(before) != normalize_text(after) else "unchanged",
        }

        self.report["global_changes"]["git_config"] = git_changes
        self.report["global_changes"]["gh_config"] = [gh_change]
        self.report["global_changes"]["agents_file"] = agents_change

    def apply_global_settings(self) -> None:
        git_changes = []
        for key, target in TARGET_GIT_CONFIG.items():
            current = git_config_get(key)
            changed = current != target
            status = "unchanged"
            try:
                if changed:
                    run_cmd(["git", "config", "--global", key, target])
                    status = "updated"
                git_changes.append(
                    {
                        "key": key,
                        "before": current,
                        "after": target,
                        "changed": changed,
                        "status": status,
                    }
                )
            except Exception as exc:
                message = f"Failed to set git config {key}: {exc}"
                git_changes.append(
                    {
                        "key": key,
                        "before": current,
                        "after": target,
                        "changed": False,
                        "status": "failed",
                        "reason": message,
                    }
                )
                self.add_error("global_git", key, message)

        before_values = git_config_get_all(SSH_INSTEADOF_KEY)
        changed_instead = SSH_INSTEADOF_VALUE not in before_values
        try:
            if changed_instead:
                run_cmd(["git", "config", "--global", "--add", SSH_INSTEADOF_KEY, SSH_INSTEADOF_VALUE])
            after_values = git_config_get_all(SSH_INSTEADOF_KEY)
            git_changes.append(
                {
                    "key": SSH_INSTEADOF_KEY,
                    "before": before_values,
                    "after": after_values,
                    "changed": changed_instead,
                    "status": "updated" if changed_instead else "unchanged",
                }
            )
        except Exception as exc:
            message = f"Failed to set git config {SSH_INSTEADOF_KEY}: {exc}"
            git_changes.append(
                {
                    "key": SSH_INSTEADOF_KEY,
                    "before": before_values,
                    "after": before_values,
                    "changed": False,
                    "status": "failed",
                    "reason": message,
                }
            )
            self.add_error("global_git", SSH_INSTEADOF_KEY, message)

        gh_changes = []
        gh_before = gh_config_get("git_protocol")
        try:
            if gh_before != "ssh":
                run_cmd(["gh", "config", "set", "git_protocol", "ssh"])
            gh_after = gh_config_get("git_protocol")
            gh_changes.append(
                {
                    "key": "git_protocol",
                    "before": gh_before,
                    "after": gh_after,
                    "changed": gh_before != gh_after,
                    "status": "updated" if gh_before != gh_after else "unchanged",
                }
            )
        except Exception as exc:
            message = f"Failed to set gh git_protocol: {exc}"
            gh_changes.append(
                {
                    "key": "git_protocol",
                    "before": gh_before,
                    "after": gh_before,
                    "changed": False,
                    "status": "failed",
                    "reason": message,
                }
            )
            self.add_error("global_gh", "git_protocol", message)

        agents_path = Path("/Users/siunin/.codex/AGENTS.md")
        agents_before = read_text_if_exists(agents_path)
        agents_after = ensure_agents_rules(agents_before)
        agents_changed = normalize_text(agents_before) != normalize_text(agents_after)

        try:
            if agents_changed:
                write_text_file(agents_path, agents_after)
            agents_status = {
                "path": str(agents_path),
                "changed": agents_changed,
                "status": "updated" if agents_changed else "unchanged",
            }
        except Exception as exc:
            message = f"Failed to update AGENTS.md: {exc}"
            agents_status = {
                "path": str(agents_path),
                "changed": False,
                "status": "failed",
                "reason": message,
            }
            self.add_error("global_agents", str(agents_path), message)

        self.report["global_changes"]["git_config"] = git_changes
        self.report["global_changes"]["gh_config"] = gh_changes
        self.report["global_changes"]["agents_file"] = agents_status

    def scan_local_remotes(self, owner: str, target_repos: set[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for repo_dir in iter_git_repos(SCAN_ROOT):
            origin = git_remote_get_origin(repo_dir)
            if origin is None:
                continue

            parsed = parse_github_repo_from_url(origin)
            entry: dict[str, Any] = {
                "path": str(repo_dir),
                "origin_before": origin,
                "origin_after": origin,
                "repo": None,
                "status": "skipped_not_target",
                "changed": False,
            }

            if parsed is None:
                results.append(entry)
                continue

            parsed_owner, parsed_repo = parsed
            slug = f"{parsed_owner}/{parsed_repo}"
            entry["repo"] = slug

            if parsed_owner.lower() != owner.lower() or slug not in target_repos:
                entry["status"] = "skipped_not_target"
                results.append(entry)
                continue

            if is_ssh_origin(origin, parsed_owner, parsed_repo):
                entry["status"] = "skipped_already_ssh"
                results.append(entry)
                continue

            # Only https target repos reach this point.
            if self.args.mode == "apply" and bool(self.args.rewrite_remotes):
                ssh_url = build_ssh_origin(parsed_owner, parsed_repo)
                try:
                    run_cmd(["git", "-C", str(repo_dir), "remote", "set-url", "origin", ssh_url])
                    entry["origin_after"] = ssh_url
                    entry["status"] = "updated_to_ssh"
                    entry["changed"] = True
                except Exception as exc:
                    message = f"Failed to rewrite remote: {exc}"
                    entry["status"] = "failed"
                    entry["reason"] = message
                    self.add_error("local_remote", str(repo_dir), message)
            else:
                entry["status"] = "non_compliant_unmodified"

            results.append(entry)

        return results

    def process_local_remotes(self, local_remotes: list[dict[str, Any]]) -> None:
        self.report["local_remote_results"] = local_remotes

    def restore_global_files(self, backup_data: dict[str, Any]) -> None:
        snapshots = backup_data.get("global_file_snapshots") or {}
        for path_str, snapshot in snapshots.items():
            path = Path(path_str)
            try:
                restore_snapshot_file(path, snapshot)
            except Exception as exc:
                self.add_error("rollback_global_file", path_str, str(exc))

    def restore_global_git_values(self, backup_data: dict[str, Any]) -> None:
        values = backup_data.get("global_git_values_before") or {}
        for key, value in values.items():
            try:
                if key == SSH_INSTEADOF_KEY:
                    run_cmd(["git", "config", "--global", "--unset-all", SSH_INSTEADOF_KEY], check=False)
                    if isinstance(value, list):
                        for item in value:
                            run_cmd(["git", "config", "--global", "--add", SSH_INSTEADOF_KEY, str(item)])
                    continue

                if value is None:
                    run_cmd(["git", "config", "--global", "--unset", key], check=False)
                else:
                    run_cmd(["git", "config", "--global", key, str(value)])
            except Exception as exc:
                self.add_error("rollback_global_git", key, str(exc))

    def restore_local_remotes(self, backup_data: dict[str, Any]) -> None:
        entries = backup_data.get("local_remote_before") or []
        for entry in entries:
            path = entry.get("path")
            origin_before = entry.get("origin_before")
            if not path or not origin_before:
                continue
            try:
                run_cmd(["git", "-C", path, "remote", "set-url", "origin", origin_before])
            except Exception as exc:
                self.add_error("rollback_local_remote", path, str(exc))

    def restore_repo_workflows(self, backup_data: dict[str, Any]) -> None:
        entries = backup_data.get("workflow_file_before") or []
        for entry in entries:
            repo = entry.get("repo")
            branch = entry.get("default_branch")
            workflow = entry.get("workflow") or {}
            if not repo or not branch:
                continue
            try:
                self.restore_single_workflow(repo, branch, workflow)
            except Exception as exc:
                self.add_error("rollback_workflow", repo, str(exc))

    def restore_single_workflow(self, repo: str, branch: str, workflow_before: dict[str, Any]) -> None:
        exists_before = bool(workflow_before.get("exists"))
        current = self.get_workflow_file(repo, branch)
        current_exists = bool(current.get("exists"))

        if not exists_before:
            if not current_exists:
                return
            payload = {
                "message": "chore: rollback required-check workflow removal",
                "sha": current.get("sha"),
                "branch": branch,
            }
            gh_api(f"/repos/{repo}/contents/{WORKFLOW_FILE_PATH}", method="DELETE", data=payload)
            return

        desired_content = normalize_text(workflow_before.get("content"))
        payload = {
            "message": "chore: rollback required-check workflow",
            "content": base64.b64encode(desired_content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if current_exists and current.get("sha"):
            payload["sha"] = current["sha"]
        gh_api(f"/repos/{repo}/contents/{WORKFLOW_FILE_PATH}", method="PUT", data=payload)

    def restore_repo_protections(self, backup_data: dict[str, Any]) -> None:
        entries = backup_data.get("repo_protection_before") or []
        for entry in entries:
            repo = entry.get("repo")
            branch = entry.get("default_branch")
            protection_before = entry.get("protection")
            if not repo or not branch:
                continue

            endpoint = f"/repos/{repo}/branches/{quote(branch, safe='')}/protection"
            try:
                if protection_before is None:
                    gh_api(endpoint, method="DELETE", expect_404=True)
                else:
                    payload = protection_raw_to_payload(protection_before)
                    gh_api(endpoint, method="PUT", data=payload)
            except Exception as exc:
                self.add_error("rollback_protection", repo, str(exc))

    def finalize_report(
        self,
        repos: list[dict[str, Any]],
        repo_states: list[dict[str, Any]],
        local_remotes: list[dict[str, Any]],
        report_path: Path,
    ) -> None:
        repo_changed = 0
        repo_failed = 0
        repo_skipped = 0
        repo_success = 0
        for result in self.report["repo_results"]:
            if result.get("changed"):
                repo_changed += 1
            has_failure = bool(result.get("errors"))
            if has_failure:
                repo_failed += 1
                continue

            workflow_status = (result.get("workflow") or {}).get("status")
            protection_status = (result.get("protection") or {}).get("status")
            if workflow_status == "unchanged" and protection_status == "unchanged":
                repo_skipped += 1
            else:
                repo_success += 1

        local_changed = sum(1 for item in local_remotes if item.get("changed"))
        local_non_compliant = sum(1 for item in local_remotes if item.get("status") == "non_compliant_unmodified")
        local_failed = sum(1 for item in local_remotes if item.get("status") == "failed")
        local_skipped = sum(
            1 for item in local_remotes if item.get("status") in {"skipped_not_target", "skipped_already_ssh"}
        )
        local_success = sum(1 for item in local_remotes if item.get("status") == "updated_to_ssh")

        global_changed_count = 0
        global_failed_count = 0
        global_skipped_count = 0
        for item in self.report["global_changes"].get("git_config", []):
            if item.get("changed"):
                global_changed_count += 1
            if item.get("status") == "failed":
                global_failed_count += 1
            if item.get("status") == "unchanged":
                global_skipped_count += 1
        for item in self.report["global_changes"].get("gh_config", []):
            if item.get("changed"):
                global_changed_count += 1
            if item.get("status") == "failed":
                global_failed_count += 1
            if item.get("status") == "unchanged":
                global_skipped_count += 1
        if self.report["global_changes"].get("agents_file", {}).get("changed"):
            global_changed_count += 1
        if self.report["global_changes"].get("agents_file", {}).get("status") == "failed":
            global_failed_count += 1
        if self.report["global_changes"].get("agents_file", {}).get("status") == "unchanged":
            global_skipped_count += 1

        self.report["summary"] = {
            "report_file": str(report_path),
            "repos_total": len(repos) if repos else len(repo_states),
            "repos_changed": repo_changed,
            "repos_success": repo_success,
            "repos_skipped": repo_skipped,
            "repos_failed": repo_failed,
            "local_remotes_total": len(local_remotes),
            "local_remotes_changed": local_changed,
            "local_remotes_success": local_success,
            "local_remotes_skipped": local_skipped,
            "local_remotes_non_compliant": local_non_compliant,
            "local_remotes_failed": local_failed,
            "global_items_changed": global_changed_count,
            "global_items_skipped": global_skipped_count,
            "global_items_failed": global_failed_count,
            "errors_total": len(self.report["errors"]),
        }

        self.report["retry_hints"] = build_retry_hints(self.report["errors"])

    def add_error(self, scope: str, target: str, message: str) -> None:
        self.report["errors"].append(
            {
                "scope": scope,
                "target": target,
                "message": message,
            }
        )


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_ops_dir() -> None:
    OPS_DIR.mkdir(parents=True, exist_ok=True)


def run_cmd(cmd: list[str], check: bool = True, input_text: str | None = None) -> CmdResult:
    proc = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    result = CmdResult(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
    if check and proc.returncode != 0:
        raise GuardrailsError(format_cmd_error(cmd, result))
    return result


def format_cmd_error(cmd: list[str], result: CmdResult) -> str:
    parts = [f"Command failed ({result.returncode}): {' '.join(cmd)}"]
    if result.stdout:
        parts.append(f"stdout: {result.stdout}")
    if result.stderr:
        parts.append(f"stderr: {result.stderr}")
    return "\n".join(parts)


def gh_api(
    path: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    expect_404: bool = False,
) -> Any:
    cmd = ["gh", "api", path]
    if method and method.upper() != "GET":
        cmd.extend(["-X", method.upper()])

    input_text = None
    if data is not None:
        cmd.extend(["--input", "-"])
        input_text = json.dumps(data)

    result = run_cmd(cmd, check=False, input_text=input_text)

    if result.returncode != 0:
        message = format_cmd_error(cmd, result)
        if expect_404 and ("HTTP 404" in message or "404 Not Found" in message):
            return None
        raise GuardrailsError(message)

    if not result.stdout:
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def snapshot_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "content": None,
        }
    return {
        "exists": True,
        "content": path.read_text(encoding="utf-8"),
    }


def restore_snapshot_file(path: Path, snapshot: dict[str, Any]) -> None:
    exists = bool(snapshot.get("exists"))
    content = snapshot.get("content")
    if exists:
        if content is None:
            raise GuardrailsError(f"Snapshot for {path} is missing content")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")
    else:
        if path.exists():
            path.unlink()


def read_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def normalize_text(content: str | None) -> str | None:
    if content is None:
        return None
    value = content.replace("\r\n", "\n")
    value = value.rstrip("\n") + "\n"
    return value


def render_workflow(template: str, default_branch: str) -> str:
    return template.replace("{{ default_branch }}", default_branch)


def normalize_protection(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None

    checks = raw.get("required_status_checks")
    review = raw.get("required_pull_request_reviews")

    return {
        "required_status_checks": {
            "strict": bool((checks or {}).get("strict", False)),
            "contexts": sorted(status_check_contexts(checks)),
        },
        "enforce_admins": bool((raw.get("enforce_admins") or {}).get("enabled", False)),
        "required_pull_request_reviews": {
            "required_approving_review_count": int((review or {}).get("required_approving_review_count") or 0),
            "dismiss_stale_reviews": bool((review or {}).get("dismiss_stale_reviews", False)),
            "require_last_push_approval": bool((review or {}).get("require_last_push_approval", False)),
        },
        "required_linear_history": bool((raw.get("required_linear_history") or {}).get("enabled", False)),
        "required_conversation_resolution": bool(
            (raw.get("required_conversation_resolution") or {}).get("enabled", False)
        ),
        "allow_force_pushes": bool((raw.get("allow_force_pushes") or {}).get("enabled", False)),
        "allow_deletions": bool((raw.get("allow_deletions") or {}).get("enabled", False)),
    }


def normalize_target_protection(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("required_status_checks") or {}
    review = payload.get("required_pull_request_reviews") or {}
    return {
        "required_status_checks": {
            "strict": bool(checks.get("strict", False)),
            "contexts": sorted(checks.get("contexts") or []),
        },
        "enforce_admins": bool(payload.get("enforce_admins", False)),
        "required_pull_request_reviews": {
            "required_approving_review_count": int(review.get("required_approving_review_count") or 0),
            "dismiss_stale_reviews": bool(review.get("dismiss_stale_reviews", False)),
            "require_last_push_approval": bool(review.get("require_last_push_approval", False)),
        },
        "required_linear_history": bool(payload.get("required_linear_history", False)),
        "required_conversation_resolution": bool(payload.get("required_conversation_resolution", False)),
        "allow_force_pushes": bool(payload.get("allow_force_pushes", False)),
        "allow_deletions": bool(payload.get("allow_deletions", False)),
    }


def status_check_contexts(checks: dict[str, Any] | None) -> list[str]:
    if not checks:
        return []

    contexts = checks.get("contexts")
    if isinstance(contexts, list):
        return [str(ctx) for ctx in contexts]

    output: list[str] = []
    for item in checks.get("checks") or []:
        context = item.get("context")
        if context:
            output.append(str(context))
    return output


def protection_raw_to_payload(raw: dict[str, Any]) -> dict[str, Any]:
    checks = raw.get("required_status_checks")
    review = raw.get("required_pull_request_reviews")

    restrictions_raw = raw.get("restrictions")
    restrictions: dict[str, Any] | None
    if restrictions_raw is None:
        restrictions = None
    else:
        restrictions = {
            "users": [user.get("login") for user in restrictions_raw.get("users") or [] if user.get("login")],
            "teams": [team.get("slug") for team in restrictions_raw.get("teams") or [] if team.get("slug")],
            "apps": [
                app.get("slug") or app.get("name")
                for app in restrictions_raw.get("apps") or []
                if app.get("slug") or app.get("name")
            ],
        }

    payload: dict[str, Any] = {
        "required_status_checks": None
        if checks is None
        else {
            "strict": bool(checks.get("strict", False)),
            "contexts": sorted(status_check_contexts(checks)),
        },
        "enforce_admins": bool((raw.get("enforce_admins") or {}).get("enabled", False)),
        "required_pull_request_reviews": None
        if review is None
        else {
            "dismiss_stale_reviews": bool(review.get("dismiss_stale_reviews", False)),
            "require_code_owner_reviews": bool(review.get("require_code_owner_reviews", False)),
            "required_approving_review_count": int(review.get("required_approving_review_count") or 0),
            "require_last_push_approval": bool(review.get("require_last_push_approval", False)),
        },
        "restrictions": restrictions,
        "required_linear_history": bool((raw.get("required_linear_history") or {}).get("enabled", False)),
        "allow_force_pushes": bool((raw.get("allow_force_pushes") or {}).get("enabled", False)),
        "allow_deletions": bool((raw.get("allow_deletions") or {}).get("enabled", False)),
        "block_creations": bool((raw.get("block_creations") or {}).get("enabled", False)),
        "required_conversation_resolution": bool(
            (raw.get("required_conversation_resolution") or {}).get("enabled", False)
        ),
        "lock_branch": bool((raw.get("lock_branch") or {}).get("enabled", False)),
        "allow_fork_syncing": bool((raw.get("allow_fork_syncing") or {}).get("enabled", False)),
    }

    return payload


def ensure_agents_rules(existing: str | None) -> str:
    base = (existing or "").strip()

    # Remove existing targeted sections before injecting canonical ones.
    for heading in ("GH Command Execution", "Git Transport"):
        pattern = rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)"
        base = re.sub(pattern, "", base)

    base = base.strip()
    if base.startswith("# Global Agent Rules"):
        lines = base.splitlines()
        base = "\n".join(lines[1:]).strip()

    parts = ["# Global Agent Rules", "", GH_SECTION.strip(), "", GIT_TRANSPORT_SECTION.strip()]
    if base:
        parts.extend(["", base])

    return "\n".join(parts).rstrip() + "\n"


def git_config_get(key: str) -> str | None:
    result = run_cmd(["git", "config", "--global", "--get", key], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def git_config_get_all(key: str) -> list[str]:
    result = run_cmd(["git", "config", "--global", "--get-all", key], check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def gh_config_get(key: str) -> str | None:
    result = run_cmd(["gh", "config", "get", key], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def iter_git_repos(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, _filenames in os.walk(root):
        if ".git" in dirnames:
            yield Path(dirpath)
            dirnames[:] = []


def git_remote_get_origin(repo_path: Path) -> str | None:
    result = run_cmd(["git", "-C", str(repo_path), "remote", "get-url", "origin"], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def parse_github_repo_from_url(url: str) -> tuple[str, str] | None:
    https_match = re.match(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if https_match:
        return https_match.group(1), https_match.group(2)

    ssh_match = re.match(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)

    ssh_uri_match = re.match(r"^ssh://git@github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if ssh_uri_match:
        return ssh_uri_match.group(1), ssh_uri_match.group(2)

    return None


def is_ssh_origin(url: str, owner: str, repo: str) -> bool:
    ssh_urls = {
        f"git@github.com:{owner}/{repo}.git",
        f"git@github.com:{owner}/{repo}",
        f"ssh://git@github.com/{owner}/{repo}.git",
        f"ssh://git@github.com/{owner}/{repo}",
    }
    return url in ssh_urls


def build_ssh_origin(owner: str, repo: str) -> str:
    return f"git@github.com:{owner}/{repo}.git"


def build_retry_hints(errors: list[dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    for err in errors:
        message = (err.get("message") or "").lower()
        if "scope" in message and ("repo" in message or "workflow" in message):
            hint = "Verify gh token scopes include `repo` and `workflow` and re-run."
        elif "403" in message or "admin" in message:
            hint = "Check repository admin permissions for this account and retry affected repos."
        elif "404" in message:
            hint = "Verify repository/default branch still exists and re-run for that target."
        else:
            hint = "Retry the operation for failed targets after resolving the reported error."

        if hint not in hints:
            hints.append(hint)
    return hints


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply or rollback global Git/GH guardrails")
    parser.add_argument("--owner", help="GitHub owner login (required for dry-run/apply)")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["dry-run", "apply", "rollback"],
        help="Execution mode",
    )
    parser.add_argument(
        "--backup-file",
        help="Backup JSON file path (required for rollback)",
    )
    parser.add_argument(
        "--rewrite-remotes",
        action="store_true",
        help="Rewrite HTTPS origin URLs to SSH for local target repos (apply mode only)",
    )

    args = parser.parse_args(argv)

    if args.mode in {"dry-run", "apply"} and not args.owner:
        parser.error("--owner is required for dry-run/apply")
    if args.mode == "rollback" and not args.backup_file:
        parser.error("--backup-file is required for rollback")
    if args.mode != "apply" and args.rewrite_remotes:
        parser.error("--rewrite-remotes is only valid for --mode apply")

    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    runner = GuardrailsRunner(args)
    try:
        return runner.run()
    except GuardrailsError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
