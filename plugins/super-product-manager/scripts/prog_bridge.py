#!/usr/bin/env python3
"""Bridge helpers for syncing SPM workflow outputs into PROG via CLI."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

OWNER_ROLES = ("architecture", "coding", "testing")
UPDATE_CATEGORIES = ("status", "decision", "risk", "handoff", "assignment", "meeting")
UPDATE_SOURCES = ("prog_update", "spm_meeting", "spm_assign", "manual")


def _local_prog_path() -> Path:
    return Path(__file__).resolve().parents[2] / "progress-tracker" / "prog"


def resolve_prog_command() -> Optional[List[str]]:
    """Resolve the command prefix used to invoke the PROG CLI."""
    env_prog = os.environ.get("PROG_CLI")
    if env_prog:
        env_path = Path(env_prog).expanduser()
        if env_path.exists():
            return [str(env_path)] if os.access(env_path, os.X_OK) else ["bash", str(env_path)]

    local_prog = _local_prog_path()
    if local_prog.exists():
        return [str(local_prog)] if os.access(local_prog, os.X_OK) else ["bash", str(local_prog)]

    which_prog = shutil.which("prog")
    if which_prog:
        return [which_prog]

    return None


def _command_string(parts: List[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def run_prog(args: List[str], cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Run PROG command and return structured execution result."""
    prog_cmd = resolve_prog_command()
    if not prog_cmd:
        return {
            "ok": False,
            "error": "prog_not_found",
            "command": "",
            "stderr": "Unable to resolve 'prog' CLI. Set PROG_CLI or install progress-tracker.",
        }

    command = [*prog_cmd, *args]
    cwd_str = str(cwd) if cwd else None

    try:
        proc = subprocess.run(
            command,
            cwd=cwd_str,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive path
        return {
            "ok": False,
            "error": "prog_exec_error",
            "command": _command_string(command),
            "stderr": str(exc),
        }

    return {
        "ok": proc.returncode == 0,
        "error": None if proc.returncode == 0 else "prog_failed",
        "returncode": proc.returncode,
        "command": _command_string(command),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def sync_update(
    *,
    category: str,
    summary: str,
    details: Optional[str] = None,
    feature_id: Optional[int] = None,
    bug_id: Optional[str] = None,
    role: Optional[str] = None,
    owner: Optional[str] = None,
    source: str = "spm_meeting",
    next_action: Optional[str] = None,
    refs: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append a structured update into PROG using add-update."""
    normalized_category = category.strip().lower()
    if normalized_category not in UPDATE_CATEGORIES:
        return {
            "ok": False,
            "error": "invalid_category",
            "stderr": f"Unsupported category: {category}",
            "command": "",
        }

    normalized_source = source.strip().lower()
    if normalized_source not in UPDATE_SOURCES:
        return {
            "ok": False,
            "error": "invalid_source",
            "stderr": f"Unsupported source: {source}",
            "command": "",
        }

    normalized_role = role.strip().lower() if isinstance(role, str) else None
    if normalized_role and normalized_role not in OWNER_ROLES:
        return {
            "ok": False,
            "error": "invalid_role",
            "stderr": f"Unsupported role: {role}",
            "command": "",
        }

    argv = [
        "add-update",
        "--category",
        normalized_category,
        "--summary",
        summary,
        "--source",
        normalized_source,
    ]

    if details:
        argv.extend(["--details", details])
    if feature_id is not None:
        argv.extend(["--feature-id", str(feature_id)])
    if bug_id:
        argv.extend(["--bug-id", bug_id])
    if normalized_role:
        argv.extend(["--role", normalized_role])
    if owner:
        argv.extend(["--owner", owner])
    if next_action:
        argv.extend(["--next-action", next_action])
    for ref in refs or []:
        argv.extend(["--ref", ref])

    return run_prog(argv, cwd=cwd)


def assign_feature_owner(
    *,
    feature_id: int,
    role: str,
    owner: str,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    """Set role owner for a feature through PROG CLI."""
    normalized_role = role.strip().lower()
    if normalized_role not in OWNER_ROLES:
        return {
            "ok": False,
            "error": "invalid_role",
            "stderr": f"Unsupported role: {role}",
            "command": "",
        }

    return run_prog(["set-feature-owner", str(feature_id), normalized_role, owner], cwd=cwd)


def sync_assignment(
    *,
    feature_id: int,
    role: str,
    owner: str,
    summary: str,
    details: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    """Sync role assignment as owner mutation plus assignment update."""
    owner_result = assign_feature_owner(
        feature_id=feature_id,
        role=role,
        owner=owner,
        cwd=cwd,
    )
    update_result = sync_update(
        category="assignment",
        summary=summary,
        details=details,
        feature_id=feature_id,
        role=role,
        owner=owner,
        source="spm_assign",
        cwd=cwd,
    )
    return {
        "ok": owner_result.get("ok") and update_result.get("ok"),
        "owner_result": owner_result,
        "update_result": update_result,
    }


def sync_meeting(
    *,
    summary: str,
    details: Optional[str] = None,
    feature_id: Optional[int] = None,
    refs: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    """Sync meeting summary into PROG updates stream."""
    return sync_update(
        category="meeting",
        summary=summary,
        details=details,
        feature_id=feature_id,
        source="spm_meeting",
        refs=refs,
        cwd=cwd,
    )


def sync_followup(
    *,
    summary: str,
    details: Optional[str] = None,
    category: str = "status",
    feature_id: Optional[int] = None,
    next_action: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    """Sync follow-up status/handoff update into PROG."""
    return sync_update(
        category=category,
        summary=summary,
        details=details,
        feature_id=feature_id,
        source="spm_meeting",
        next_action=next_action,
        cwd=cwd,
    )
