#!/usr/bin/env python3
"""Unit tests for SPM -> PROG bridge execution behavior."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import prog_bridge


def test_run_prog_success(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(prog_bridge, "resolve_prog_command", lambda: ["prog"])
    completed = subprocess.CompletedProcess(["prog", "status"], 0, "ok", "")

    with patch("prog_bridge.subprocess.run", return_value=completed) as run_mock:
        result = prog_bridge.run_prog(["status"], cwd=tmp_path)

    assert result["ok"] is True
    assert "prog status" in result["command"]
    run_mock.assert_called_once()


def test_run_prog_graceful_degradation_when_prog_missing(monkeypatch) -> None:
    monkeypatch.setattr(prog_bridge, "resolve_prog_command", lambda: None)

    result = prog_bridge.run_prog(["status"])

    assert result["ok"] is False
    assert result["error"] == "prog_not_found"


def test_run_prog_nonzero_exit_captures_stderr(monkeypatch) -> None:
    monkeypatch.setattr(prog_bridge, "resolve_prog_command", lambda: ["prog"])
    completed = subprocess.CompletedProcess(["prog", "status"], 1, "", "boom")

    with patch("prog_bridge.subprocess.run", return_value=completed):
        result = prog_bridge.run_prog(["status"])

    assert result["ok"] is False
    assert result["error"] == "prog_failed"
    assert result["stderr"] == "boom"


def test_sync_assignment_executes_owner_then_assignment_update(monkeypatch) -> None:
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return {"ok": True, "command": "x", "stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(prog_bridge, "run_prog", fake_run)

    result = prog_bridge.sync_assignment(
        feature_id=3,
        role="coding",
        owner="alice",
        summary="Assign coding owner",
        details="beta assignment",
    )

    assert result["ok"] is True
    assert calls[0][:2] == ["set-feature-owner", "3"]
    assert calls[1][0] == "add-update"
    assert "--category" in calls[1]
    assert "assignment" in calls[1]


def test_sync_planning_update_emits_planning_source_and_refs(monkeypatch) -> None:
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return {"ok": True, "command": "x", "stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(prog_bridge, "run_prog", fake_run)

    result = prog_bridge.sync_planning_update(
        stage="office_hours",
        summary="Planning kickoff complete",
        doc_path="docs/product-contracts/2026-04-09-office-hours.md",
        refs=["custom:token"],
    )

    assert result["ok"] is True
    argv = calls[0]
    assert argv[0] == "add-update"
    assert "--source" in argv
    assert "spm_planning" in argv
    assert "planning:office_hours" in argv
    assert "doc:docs/product-contracts/2026-04-09-office-hours.md" in argv
    assert "custom:token" in argv


def test_sync_planning_update_rejects_unknown_stage() -> None:
    result = prog_bridge.sync_planning_update(
        stage="unknown",
        summary="Invalid stage",
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_planning_stage"
