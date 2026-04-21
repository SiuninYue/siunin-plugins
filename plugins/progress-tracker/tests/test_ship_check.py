#!/usr/bin/env python3
"""ship_check contract tests (PR-5, inspired by gstack /ship + /document-release)."""

import pytest

from ship_check import run_ship_check, ShipCheckResult, ShipFailure


def test_ship_check_passes_when_all_subchecks_clean(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.92,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 20, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "pass"
    assert result.failures == []


def test_ship_check_fails_when_coverage_below_threshold(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.6,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 20, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "fail"
    assert any(f.check_id == "coverage" for f in result.failures)


def test_ship_check_fails_when_regression_broken(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.9,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 19, "failed": 1},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "fail"
    assert any(f.check_id == "regression" for f in result.failures)


def test_ship_check_fails_when_docs_drift_detected(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.9,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": False, "architecture_refs_valid": True},
            "regression_results": {"passed": 20, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "fail"
    assert any(f.check_id == "docs_sync" for f in result.failures)


def test_ship_check_result_serializes_to_quality_gates_schema(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.9,
            "test_results": {"passed": 10, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 10, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    payload = result.to_quality_gate_payload()
    assert set(payload.keys()) == {"status", "failures", "last_run_at"}


def test_ship_check_cli_returns_nonzero_on_failure(tmp_path, monkeypatch):
    import subprocess, sys, json
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    progress_manager = Path(__file__).parent.parent / "hooks" / "scripts" / "progress_manager.py"
    subprocess.run([sys.executable, str(progress_manager), "init", "Ship Test"], cwd=tmp_path)
    subprocess.run([sys.executable, str(progress_manager), "add-feature", "F1", "echo"], cwd=tmp_path)
    # force pending ship_check state via direct edit
    state = tmp_path / "docs" / "progress-tracker" / "state" / "progress.json"
    data = json.loads(state.read_text())
    data["features"][0]["quality_gates"]["ship_check"] = {
        "status": "fail",
        "failures": [{"check_id": "coverage", "detail": "59%"}],
        "last_run_at": "2026-04-08T00:00:00Z",
    }
    state.write_text(json.dumps(data, indent=2))
    result = subprocess.run(
        [sys.executable, str(progress_manager), "ship-check", "--feature-id", "1"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode != 0
