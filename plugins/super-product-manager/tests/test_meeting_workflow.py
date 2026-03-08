#!/usr/bin/env python3
"""Tests for SPM meeting workflow artifact writing and sync behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import meeting_workflow


def test_create_meeting_record_writes_artifacts_and_sync(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        meeting_workflow.prog_bridge,
        "sync_meeting",
        lambda **kwargs: {"ok": True, "command": "prog add-update", "stdout": "", "stderr": ""},
    )

    result = meeting_workflow.create_meeting_record(
        topic="Beta Kickoff",
        summary="Scope aligned",
        decisions=["Enable beta bridge"],
        action_items=["Create integration tests", "Draft release note"],
        refs=["docs/plans/2026-03-09-spm-prog-beta-design.md"],
        project_root=tmp_path,
    )

    assert result["ok"] is True
    assert Path(result["meeting_file"]).exists()
    action_items_path = Path(result["action_items_file"])
    assert action_items_path.exists()

    payload = json.loads(action_items_path.read_text(encoding="utf-8"))
    assert len(payload) == 2
    assert result["sync_errors"] == []


def test_assign_feature_owner_propagates_sync_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        meeting_workflow.prog_bridge,
        "sync_assignment",
        lambda **kwargs: {"ok": False, "error": "prog_failed", "stderr": "bad"},
    )

    result = meeting_workflow.assign_feature_owner(
        feature_id=2,
        role="testing",
        owner="qa-bot",
        note="Need test owner",
        project_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["sync_errors"]


def test_followup_sync_failure_does_not_block_action_item_update(monkeypatch, tmp_path: Path) -> None:
    meetings_dir = tmp_path / "docs" / "meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)
    items = [
        {
            "id": "A-20260309-01",
            "topic": "kickoff",
            "summary": "Initial",
            "status": "open",
            "created_at": "2026-03-09T00:00:00Z",
            "updated_at": "2026-03-09T00:00:00Z",
        }
    ]
    (meetings_dir / "action-items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        meeting_workflow.prog_bridge,
        "sync_followup",
        lambda **kwargs: {"ok": False, "error": "prog_failed", "stderr": "sync down"},
    )

    result = meeting_workflow.followup_action_item(
        action_id="A-20260309-01",
        status="blocked",
        note="Blocked by staging env",
        feature_id=2,
        project_root=tmp_path,
    )

    payload = json.loads((meetings_dir / "action-items.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert payload[0]["status"] == "blocked"
    assert payload[0]["summary"] == "Blocked by staging env"
    assert result["sync_errors"]
