#!/usr/bin/env python3
"""sprint_ledger contract tests."""

import json
from pathlib import Path

import pytest

import progress_manager
from sprint_ledger import (
    SprintLedgerError,
    list_sprint_records,
    mark_handoff,
    read_latest,
    record,
    require_sprint_contract,
)


def _init_single_feature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert progress_manager.init_tracking("Sprint Ledger Test", force=True) is True
    assert progress_manager.add_feature("F1", ["step 1"]) is True


def test_record_writes_append_only_jsonl(tmp_path):
    ledger_path = tmp_path / "docs" / "progress-tracker" / "state" / "sprint_ledger.jsonl"
    record(
        feature_id=1,
        phase="plan",
        artifact_path="docs/plans/f1-plan.md",
        metadata={"author": "planner"},
        ledger_path=ledger_path,
    )
    record(
        feature_id=1,
        phase="implementation",
        artifact_path="hooks/scripts/progress_manager.py",
        metadata={"commit": "abc123"},
        ledger_path=ledger_path,
    )

    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["phase"] == "plan"
    assert second["phase"] == "implementation"


def test_list_sprint_records_filters_by_feature(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    record(feature_id=1, phase="plan", artifact_path="a.md", ledger_path=ledger_path)
    record(feature_id=2, phase="plan", artifact_path="b.md", ledger_path=ledger_path)
    record(feature_id=1, phase="implementation", artifact_path="c.md", ledger_path=ledger_path)

    records = list_sprint_records(feature_id=1, ledger_path=ledger_path)
    assert len(records) == 2
    assert all(item.feature_id == 1 for item in records)


def test_read_latest_returns_most_recent_phase_record(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    record(feature_id=1, phase="plan", artifact_path="a.md", ledger_path=ledger_path)
    record(feature_id=1, phase="plan", artifact_path="a2.md", ledger_path=ledger_path)

    latest = read_latest(feature_id=1, phase="plan", ledger_path=ledger_path)
    assert latest is not None
    assert latest.artifact_path == "a2.md"


def test_record_rejects_unknown_phase(tmp_path):
    with pytest.raises(SprintLedgerError):
        record(feature_id=1, phase="bogus", artifact_path="x", ledger_path=tmp_path / "l.jsonl")


def test_handoff_field_is_updated_when_phase_transitions(tmp_path, monkeypatch):
    _init_single_feature(tmp_path, monkeypatch)

    mark_handoff(
        feature_id=1,
        from_phase="plan",
        to_phase="implementation",
        artifact_path="docs/plans/f1-plan.md",
    )

    data = progress_manager.load_progress_json()
    assert data is not None
    feature = data["features"][0]
    assert feature["handoff"]["from_phase"] == "plan"
    assert feature["handoff"]["to_phase"] == "implementation"
    assert feature["handoff"]["artifact_path"] == "docs/plans/f1-plan.md"
    assert feature["handoff"]["created_at"]

    handoff_record = read_latest(feature_id=1, phase="handoff")
    assert handoff_record is not None
    assert handoff_record.artifact_path == "docs/plans/f1-plan.md"
    assert handoff_record.metadata == {"from": "plan", "to": "implementation"}


def test_sprint_contract_done_criteria_required_before_phase_execution(tmp_path, monkeypatch):
    _init_single_feature(tmp_path, monkeypatch)

    data = progress_manager.load_progress_json()
    assert data is not None
    feature = data["features"][0]

    # default schema 2.1 sprint contract is intentionally empty -> should fail
    with pytest.raises(SprintLedgerError):
        require_sprint_contract(feature)

    feature["sprint_contract"] = {
        "scope": "auth middleware rewrite",
        "done_criteria": ["tests pass", "docs updated"],
        "test_plan": ["unit + integration"],
        "accepted_by": "user",
        "accepted_at": "2026-04-22T00:00:00Z",
    }
    require_sprint_contract(feature)
