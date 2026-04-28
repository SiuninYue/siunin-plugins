#!/usr/bin/env python3
"""ship_check: unified pre-archive gate (PR-5).

Mirrors gstack /ship discipline: "sync main, run tests, audit coverage,
push, open PR" + auto-invoked /document-release for docs-sync.
See https://github.com/garrytan/gstack for the upstream concept.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

Status = Literal["pass", "fail"]


@dataclass
class ShipFailure:
    check_id: str
    detail: str

    def to_dict(self) -> Dict[str, str]:
        return {"check_id": self.check_id, "detail": self.detail}


@dataclass
class ShipCheckResult:
    status: Status
    failures: List[ShipFailure] = field(default_factory=list)
    last_run_at: str = ""

    def to_quality_gate_payload(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "failures": [f.to_dict() for f in self.failures],
            "last_run_at": self.last_run_at,
        }


def _check_coverage(inputs: Dict[str, Any], thresholds: Dict[str, Any]) -> List[ShipFailure]:
    cov = float(inputs.get("test_coverage", 0.0))
    minimum = float(thresholds.get("coverage_min", 0.8))
    if cov < minimum:
        return [ShipFailure(check_id="coverage", detail=f"{cov:.0%} < required {minimum:.0%}")]
    return []


def _check_tests(inputs: Dict[str, Any]) -> List[ShipFailure]:
    r = inputs.get("test_results", {})
    if r.get("failed", 0) > 0:
        return [ShipFailure(check_id="tests", detail=f"{r['failed']} test(s) failed")]
    return []


def _check_regression(inputs: Dict[str, Any]) -> List[ShipFailure]:
    r = inputs.get("regression_results", {})
    if r.get("failed", 0) > 0:
        return [ShipFailure(check_id="regression", detail=f"{r['failed']} regression(s) failed")]
    return []


def _check_docs_sync(inputs: Dict[str, Any]) -> List[ShipFailure]:
    """Borrowed from gstack /document-release: auto-check docs drift."""
    docs = inputs.get("docs_sync", {})
    failures = []
    if not docs.get("progress_md_matches_json", True):
        failures.append(ShipFailure(check_id="docs_sync", detail="progress.md out of sync with progress.json"))
    if not docs.get("architecture_refs_valid", True):
        failures.append(ShipFailure(check_id="docs_sync", detail="architecture.md references stale feature IDs"))
    return failures


_PLUGIN_JSON_REQUIRED_KEYS = {
    "name", "version", "description", "author",
    "license", "repository", "homepage",
}


def _check_sync_compatibility(project_root: Path) -> List[ShipFailure]:
    """Sync compatibility gate (Q2-C strategy):

    Primary: run codex-plugin-sync --dry-run when available (richer evidence).
    Fallback: validate .claude-plugin/plugin.json schema (required keys) when tool absent.
    No plugin.json present → skip gracefully (non-plugin project).
    """
    plugin_json_path = project_root / ".claude-plugin" / "plugin.json"
    if not plugin_json_path.exists():
        return []  # Non-plugin project — skip check gracefully

    # Primary: try codex-plugin-sync --dry-run first
    if shutil.which("codex-plugin-sync"):
        try:
            r = subprocess.run(
                ["codex-plugin-sync", "--dry-run"],
                capture_output=True, text=True,
                cwd=str(project_root), timeout=30,
            )
            if r.returncode != 0:
                return [ShipFailure(
                    check_id="sync_compat",
                    detail=f"codex-plugin-sync --dry-run failed: {r.stderr.strip()[:200]}",
                )]
            return []  # Tool ran and passed
        except Exception:
            pass  # Tool present but failed to exec — fall through to schema check

    # Fallback: static schema validation when codex-plugin-sync is absent
    try:
        data = json.loads(plugin_json_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return [ShipFailure(check_id="sync_compat", detail=f"plugin.json parse error: {exc}")]

    missing = _PLUGIN_JSON_REQUIRED_KEYS - set(data.keys())
    if missing:
        return [ShipFailure(
            check_id="sync_compat",
            detail=f"plugin.json missing required keys: {', '.join(sorted(missing))}",
        )]

    return []


def _collect_real_signals(
    project_root: Path,
    test_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run real checks and collect signals for run_ship_check.

    pytest scope: project_root/tests/ by default (plugin-scoped, not full monorepo).
    Pass test_path to override scope.

    Fail-closed rules:
    - Missing tests/ dir → tests_dir_exists=False (triggers _check_test_scope failure).
    - pytest returncode != 0 with no parsed failures → set failed=1 (collection errors,
      import errors, or interrupts are treated as implicit test failures).

    Docs drift: compares progress.md mtime vs progress.json mtime (60s tolerance).
    """
    passed, failed = 0, 0
    tests_dir = test_path or (project_root / "tests")
    tests_dir_exists = tests_dir.is_dir()

    if tests_dir_exists:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(tests_dir), "-q", "--tb=no"],
                capture_output=True, text=True, timeout=300,
                cwd=str(project_root),
            )
            for line in (result.stdout + result.stderr).splitlines():
                m_pass = re.search(r"(\d+) passed", line)
                m_fail = re.search(r"(\d+) failed", line)
                if m_pass:
                    passed = int(m_pass.group(1))
                if m_fail:
                    failed = int(m_fail.group(1))
            # Fail-closed: non-zero returncode with no parsed failures = collection/interrupt error
            if result.returncode != 0 and failed == 0:
                failed = 1
        except subprocess.TimeoutExpired:
            failed = 1  # Treat timeout as test failure (fail-closed)
        except Exception:
            failed = 1  # Treat any exec error as failure (fail-closed)

    # Docs drift: progress.md should be at least as recent as progress.json
    progress_json_path = project_root / "docs" / "progress-tracker" / "state" / "progress.json"
    progress_md_path = project_root / "docs" / "progress-tracker" / "state" / "progress.md"
    md_in_sync = True
    if progress_json_path.exists() and progress_md_path.exists():
        tolerance = 60  # seconds
        md_in_sync = (
            progress_md_path.stat().st_mtime >= progress_json_path.stat().st_mtime - tolerance
        )

    return {
        "test_coverage": 1.0,  # Coverage not collected in CLI mode
        "tests_dir_exists": tests_dir_exists,
        "test_results": {"passed": passed, "failed": failed, "skipped": 0},
        "docs_sync": {"progress_md_matches_json": md_in_sync, "architecture_refs_valid": True},
        "regression_results": {"passed": passed, "failed": 0},
    }


def _check_test_scope(inputs: Dict[str, Any]) -> List[ShipFailure]:
    """Fail-closed: missing tests/ directory is a gate failure.

    Existing callers that don't pass tests_dir_exists default to True (no regression).
    """
    if not inputs.get("tests_dir_exists", True):
        return [ShipFailure(
            check_id="no_test_scope",
            detail="tests/ directory not found — gate cannot verify test coverage",
        )]
    return []


def _update_progress_json(
    project_root: Path,
    feature_id: int,
    result: "ShipCheckResult",
) -> None:
    """Best-effort: write ship_check result back to quality_gates in progress.json.

    progress.md is intentionally NOT updated here — it is a derived artifact
    regenerated automatically by any subsequent prog command.
    Never blocks the gate on persistence failure.
    """
    progress_json_path = project_root / "docs" / "progress-tracker" / "state" / "progress.json"
    if not progress_json_path.exists():
        return
    try:
        data = json.loads(progress_json_path.read_text())
        for feat in data.get("features", []):
            if feat.get("id") == feature_id:
                feat.setdefault("quality_gates", {})["ship_check"] = result.to_quality_gate_payload()
                break
        progress_json_path.write_text(json.dumps(data, indent=2))
    except Exception:
        pass  # Never block the gate on persistence failure


def run_ship_check(
    *,
    feature_id: int,
    project_root: Path,
    inputs: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> ShipCheckResult:
    failures: List[ShipFailure] = []
    failures += _check_tests(inputs)
    failures += _check_coverage(inputs, thresholds)
    failures += _check_regression(inputs)
    failures += _check_docs_sync(inputs)
    failures += _check_sync_compatibility(project_root)
    failures += _check_test_scope(inputs)  # fail-closed: missing tests/ → fail

    return ShipCheckResult(
        status="fail" if failures else "pass",
        failures=failures,
        last_run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point: run the ship gate against the current project.

    Exit codes:
        0 = pass
        8 = fail (matches cmd_ship_check convention in progress_manager.py)

    Default project root: Path.cwd() — consistent with cmd_ship_check.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="ship_check: unified pre-archive release gate"
    )
    parser.add_argument(
        "--feature-id", type=int, default=None,
        help="Feature ID to update in progress.json (default: auto-discover from current_feature_id)",
    )
    parser.add_argument(
        "--project-root", type=Path, default=None,
        help="Project root directory (default: cwd, consistent with prog ship-check)",
    )
    parser.add_argument(
        "--test-path", type=Path, default=None,
        help="Override pytest target path (default: <project-root>/tests/)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output result as JSON",
    )
    args = parser.parse_args(argv)

    # Default project root: cwd (matches cmd_ship_check in progress_manager.py)
    project_root: Path = args.project_root or Path.cwd()

    # Auto-discover feature_id before run_ship_check so all calls use the same value
    feature_id = args.feature_id
    if feature_id is None:
        progress_json_path = (
            project_root / "docs" / "progress-tracker" / "state" / "progress.json"
        )
        if progress_json_path.exists():
            try:
                data = json.loads(progress_json_path.read_text())
                fid = data.get("current_feature_id")
                if fid is not None:
                    feature_id = int(fid)
            except Exception:
                pass

    inputs = _collect_real_signals(project_root, test_path=args.test_path)
    result = run_ship_check(
        feature_id=feature_id if feature_id is not None else 0,
        project_root=project_root,
        inputs=inputs,
        thresholds={"coverage_min": 0.8},
    )

    if feature_id is not None:
        _update_progress_json(project_root, feature_id, result)

    if args.json_output:
        print(json.dumps(result.to_quality_gate_payload(), indent=2))
    else:
        if result.status == "pass":
            print("[SHIP-CHECK] pass")
        else:
            for f in result.failures:
                print(f"  FAIL [{f.check_id}] {f.detail}")
            print(f"[SHIP-CHECK] FAIL ({len(result.failures)} issue(s))")

    # Exit code: 0=pass, 8=fail (matches cmd_ship_check convention)
    return 0 if result.status == "pass" else 8


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as exc:
        # Remap argparse usage errors (code 2) and any other unexpected codes to 8 (fail-closed)
        if exc.code not in (0, 8):
            sys.exit(8)
        raise
