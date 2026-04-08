#!/usr/bin/env python3
"""Tests for SPM planning workflow artifacts and PROG sync behavior."""

from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import planning_workflow


def test_run_office_hours_writes_artifact_and_sync(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        planning_workflow.prog_bridge,
        "sync_planning_update",
        lambda **kwargs: {"ok": True, "command": "prog add-update", "stdout": "", "stderr": ""},
    )

    result = planning_workflow.run_office_hours(
        topic="Harness Alignment",
        goals=["Align planner ownership to SPM"],
        scope=["Planner-only output"],
        acceptance=["Contract includes goals/scope/acceptance/risks"],
        risks=["Ambiguous gate ownership"],
        project_root=tmp_path,
    )

    artifact = Path(result["artifact_file"])
    assert result["ok"] is True
    assert artifact.exists()
    content = artifact.read_text(encoding="utf-8")
    assert "## Goals" in content
    assert "## Scope" in content
    assert result["sync_errors"] == []


def test_run_design_review_generates_lane_suggestions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        planning_workflow.prog_bridge,
        "sync_planning_update",
        lambda **kwargs: {"ok": True, "command": "prog add-update", "stdout": "", "stderr": ""},
    )

    result = planning_workflow.run_design_review(
        topic="Editor UX",
        score=8,
        strengths=["Clear hierarchy"],
        issues=["Spacing inconsistency"],
        recommendation="Fix spacing scale",
        change_categories=["frontend", "ci"],
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["lane_suggestion"]["design"] is True
    assert result["lane_suggestion"]["devex"] is True


def test_run_devex_review_sync_failure_keeps_artifact(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        planning_workflow.prog_bridge,
        "sync_planning_update",
        lambda **kwargs: {"ok": False, "error": "prog_failed", "stderr": "sync down"},
    )

    result = planning_workflow.run_devex_review(
        topic="Build Loop",
        score=6,
        frictions=["Slow local setup"],
        improvements=["Add setup script"],
        recommendation="Automate bootstrap",
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert Path(result["artifact_file"]).exists()
    assert result["sync_errors"]
