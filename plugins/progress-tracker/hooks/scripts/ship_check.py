#!/usr/bin/env python3
"""ship_check: unified pre-archive gate (PR-5).

Mirrors gstack /ship discipline: "sync main, run tests, audit coverage,
push, open PR" + auto-invoked /document-release for docs-sync.
See https://github.com/garrytan/gstack for the upstream concept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

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

    return ShipCheckResult(
        status="fail" if failures else "pass",
        failures=failures,
        last_run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
