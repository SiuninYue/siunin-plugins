"""E2E test fixtures and helpers for SPM-PROG planning handoff integration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def project_root() -> Path:
    """Return the monorepo root directory."""
    return Path(__file__).resolve().parents[5]


def spm_scripts_dir() -> Path:
    """Return super-product-manager scripts directory."""
    return project_root() / "plugins" / "super-product-manager" / "scripts"


def prog_cli_path() -> Path:
    """Return progress-tracker prog CLI path."""
    return project_root() / "plugins" / "progress-tracker" / "prog"


def run_python_script(script_path: Path, args: List[str]) -> Dict[str, Any]:
    """Run a Python script and return parsed JSON output."""
    cmd = ["python3", str(script_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_root()),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "stderr": "Command timed out after 30s"}

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "invalid_json",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }


def run_prog_cli(args: List[str]) -> Dict[str, Any]:
    """Run PROG CLI command and return parsed result."""
    prog_path = prog_cli_path()
    if not prog_path.exists():
        return {"ok": False, "error": "prog_not_found", "path": str(prog_path)}

    cmd = [str(prog_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_root()),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "stderr": "Command timed out after 30s"}

    # Try JSON output first
    if "--json" in args:
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def minimal_planning_workflow_result() -> Dict[str, Any]:
    """Return minimal expected structure from planning workflow calls."""
    return {
        "ok": True,
        "artifact_file": str,  # Path to created artifact
        "sync": {
            "ok": True,
        },
        "sync_errors": list,
    }


def validate_planning_result_schema() -> Dict[str, Any]:
    """Return expected schema from validate-planning --json."""
    return {
        "ok": True,
        "status": str,  # "ready" | "warn" | "missing"
        "change_type": str,
        "required": list,
        "missing": list,
        "optional_missing": list,
        "refs": list,
        "message": str,
        "schema_version": str,
    }


def next_feature_result_schema() -> Dict[str, Any]:
    """Return expected schema from next-feature --json."""
    return {
        "status": str,  # "ok" | "blocked" | "none"
        "feature_id": int,
        "feature_name": str,
    }


class TempFeatureContext:
    """Context manager for creating and cleaning up a temporary feature for E2E testing."""

    def __init__(self, prog_cli_args: List[str] = ["--project-root", "plugins/super-product-manager"]):
        self.prog_cli_args = prog_cli_args
        self.feature_id: Optional[int] = None

    def __enter__(self) -> "TempFeatureContext":
        # Create a temporary feature via PROG CLI
        # Using add-feature command if available, otherwise manual JSON edit
        # For now, we'll use an existing feature ID for testing
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Cleanup: remove test updates if any
        pass
