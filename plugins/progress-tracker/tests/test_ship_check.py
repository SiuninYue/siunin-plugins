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


def test_ship_check_ignores_legacy_progress_md_drift(tmp_path):
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
    assert result.status == "pass"
    assert result.failures == []


def test_ship_check_fails_when_architecture_refs_stale(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.9,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"architecture_refs_valid": False},
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


def test_ship_check_cli_overwrites_stale_failure_with_fresh_pass(tmp_path, monkeypatch):
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
    assert result.returncode == 0
    assert "[SHIP-CHECK] Feature 1: pass" in result.stdout

    updated = json.loads(state.read_text())
    assert updated["features"][0]["quality_gates"]["ship_check"]["status"] == "pass"


def test_ship_check_cli_returns_zero_and_persists_result_on_success(tmp_path, monkeypatch):
    import subprocess, sys, json
    from pathlib import Path

    monkeypatch.chdir(tmp_path)
    progress_manager = Path(__file__).parent.parent / "hooks" / "scripts" / "progress_manager.py"
    subprocess.run([sys.executable, str(progress_manager), "init", "Ship Test"], cwd=tmp_path, check=True)
    subprocess.run([sys.executable, str(progress_manager), "add-feature", "F1", "echo"], cwd=tmp_path, check=True)

    state = tmp_path / "docs" / "progress-tracker" / "state" / "progress.json"
    result = subprocess.run(
        [sys.executable, str(progress_manager), "ship-check", "--feature-id", "1"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "[SHIP-CHECK] Feature 1: pass" in result.stdout

    data = json.loads(state.read_text())
    ship_check = data["features"][0]["quality_gates"]["ship_check"]
    assert ship_check["status"] == "pass"
    assert ship_check["failures"] == []


# ── Task 1: sync compatibility ────────────────────────────────────────────────

def test_check_sync_compat_passes_with_valid_plugin_json(tmp_path):
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"name":"x","version":"1.0","description":"d","author":{"name":"a"},'
        '"license":"MIT","repository":"https://g","homepage":"https://g"}'
    )
    from ship_check import _check_sync_compatibility
    assert _check_sync_compatibility(tmp_path) == []


def test_check_sync_compat_fails_with_missing_keys(tmp_path):
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text('{"name":"x"}')
    from ship_check import _check_sync_compatibility
    failures = _check_sync_compatibility(tmp_path)
    assert len(failures) == 1
    assert failures[0].check_id == "sync_compat"
    assert "missing" in failures[0].detail


# ── Task 3: real signal collection ───────────────────────────────────────────

def test_collect_real_signals_runs_pytest_and_returns_counts(tmp_path):
    """_collect_real_signals runs pytest in tests/ and parses pass/fail counts."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_trivial.py").write_text("def test_ok(): assert 1 + 1 == 2\n")

    from ship_check import _collect_real_signals
    signals = _collect_real_signals(tmp_path)

    assert signals["tests_dir_exists"] is True
    assert signals["test_results"]["passed"] >= 1
    assert signals["test_results"]["failed"] == 0


def test_collect_real_signals_no_tests_dir_signals_missing_scope(tmp_path):
    """_collect_real_signals sets tests_dir_exists=False when tests/ is absent (fail-closed)."""
    from ship_check import _collect_real_signals
    signals = _collect_real_signals(tmp_path)
    assert signals["tests_dir_exists"] is False


def test_run_ship_check_fails_with_no_test_scope_when_tests_dir_missing(tmp_path):
    """End-to-end: run_ship_check returns fail with check_id='no_test_scope' when tests/ absent."""
    from ship_check import run_ship_check
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 1.0,
            "tests_dir_exists": False,
            "test_results": {"passed": 0, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 0, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "fail"
    assert any(f.check_id == "no_test_scope" for f in result.failures)


def test_update_progress_json_writes_ship_check_result(tmp_path, monkeypatch):
    """_update_progress_json writes gate result into progress.json quality_gates."""
    import json as _json
    import subprocess as _sp
    import sys as _sys
    from pathlib import Path

    # Set up minimal progress.json with feature id=1
    monkeypatch.chdir(tmp_path)
    progress_manager = Path(__file__).parent.parent / "hooks" / "scripts" / "progress_manager.py"
    _sp.run([_sys.executable, str(progress_manager), "init", "Test"], cwd=tmp_path, check=True)
    _sp.run([_sys.executable, str(progress_manager), "add-feature", "F1", "echo"], cwd=tmp_path, check=True)

    from ship_check import _update_progress_json, ShipCheckResult, ShipFailure

    result = ShipCheckResult(
        status="fail",
        failures=[ShipFailure(check_id="coverage", detail="59% < 80%")],
        last_run_at="2026-04-28T00:00:00Z",
    )
    _update_progress_json(tmp_path, 1, result)

    state = tmp_path / "docs" / "progress-tracker" / "state" / "progress.json"
    data = _json.loads(state.read_text())
    sc = data["features"][0]["quality_gates"]["ship_check"]
    assert sc["status"] == "fail"
    assert sc["failures"][0]["check_id"] == "coverage"


# ── Task 4: CLI entry point ───────────────────────────────────────────────────

def test_ship_check_cli_exits_0_on_clean_project(tmp_path):
    """python3 ship_check.py exits 0 when all checks pass."""
    import subprocess, sys
    from pathlib import Path

    # Minimal project: plugin.json + trivial test
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"name":"x","version":"1.0","description":"d","author":{"name":"a"},'
        '"license":"MIT","repository":"https://g","homepage":"https://g"}'
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_trivial.py").write_text("def test_ok(): assert True\n")

    ship_check_script = Path(__file__).parent.parent / "hooks" / "scripts" / "ship_check.py"
    result = subprocess.run(
        [sys.executable, str(ship_check_script), "--project-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pass" in result.stdout.lower()


def test_ship_check_cli_exits_8_on_missing_plugin_keys(tmp_path):
    """python3 ship_check.py exits 8 when plugin.json is missing required keys."""
    import subprocess, sys
    from pathlib import Path

    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text('{"name":"broken"}')

    ship_check_script = Path(__file__).parent.parent / "hooks" / "scripts" / "ship_check.py"
    result = subprocess.run(
        [sys.executable, str(ship_check_script), "--project-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 8, f"Expected 8, got {result.returncode}"
    assert "FAIL" in result.stdout or "FAIL" in result.stderr


def test_ship_check_cli_resolves_relative_test_path_against_project_root(tmp_path):
    """Relative --test-path should resolve from --project-root, not shell cwd."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"name":"x","version":"1.0","description":"d","author":{"name":"a"},'
        '"license":"MIT","repository":"https://g","homepage":"https://g"}'
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_trivial.py").write_text("def test_ok(): assert True\n")

    ship_check_script = Path(__file__).parent.parent / "hooks" / "scripts" / "ship_check.py"
    result = subprocess.run(
        [
            sys.executable,
            str(ship_check_script),
            "--project-root",
            os.path.basename(str(tmp_path)),
            "--test-path",
            "tests",
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_path.parent),
    )
    assert result.returncode == 0, result.stdout + result.stderr
