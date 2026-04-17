#!/usr/bin/env python3
"""Schema 2.0 -> 2.1 migration contract."""

import json
import os
from pathlib import Path

import pytest

from progress_manager import (
    _apply_schema_defaults,
    CURRENT_SCHEMA_VERSION,
    load_progress_json,
    save_progress_json,
)


def test_schema_default_is_2_1():
    assert CURRENT_SCHEMA_VERSION == "2.1"


def test_legacy_2_0_progress_json_backfills_all_new_fields():
    data = {
        "schema_version": "2.0",
        "features": [
            {
                "id": 1,
                "name": "legacy feature",
                "lifecycle_state": "approved",
                "development_stage": "planning",
            }
        ],
    }
    _apply_schema_defaults(data)
    assert data["schema_version"] == "2.1"
    feat = data["features"][0]
    assert "sprint_contract" in feat
    assert feat["sprint_contract"]["done_criteria"] == []
    assert "quality_gates" in feat
    assert feat["quality_gates"]["evaluator"]["status"] == "pending"
    assert feat["quality_gates"]["evaluator"]["evaluator_model"] is None
    assert feat["quality_gates"]["reviews"]["required"] == []
    assert feat["quality_gates"]["ship_check"]["status"] == "pending"
    assert "handoff" in feat
    assert feat["handoff"]["from_phase"] is None


def test_prog_disable_v2_env_var_preserves_existing_fields(monkeypatch):
    monkeypatch.setenv("PROG_DISABLE_V2", "1")
    data = {
        "schema_version": "2.0",
        "features": [
            {
                "id": 1,
                "name": "x",
                "lifecycle_state": "approved",
                "quality_gates": {
                    "evaluator": {
                        "status": "pass",
                        "score": 95,
                        "defects": [],
                        "last_run_at": "2026-04-08T00:00:00Z",
                        "evaluator_model": "claude-sonnet-4-6",
                    },
                    "reviews": {"required": ["eng"], "passed": ["eng"], "pending": []},
                    "ship_check": {"status": "pass", "failures": [], "last_run_at": None},
                },
            }
        ],
    }
    _apply_schema_defaults(data)
    # existing fields must not be clobbered even when migrating
    assert data["features"][0]["quality_gates"]["evaluator"]["status"] == "pass"
    assert data["features"][0]["quality_gates"]["reviews"]["required"] == ["eng"]
    assert data["features"][0]["quality_gates"]["evaluator"]["evaluator_model"] == "claude-sonnet-4-6"


def test_partial_quality_gates_gets_missing_subkeys_filled():
    """Robustness: partial quality_gates (e.g., manually edited) must be deep-merged."""
    data = {
        "schema_version": "2.0",
        "features": [
            {
                "id": 1,
                "name": "partially edited",
                "lifecycle_state": "approved",
                "quality_gates": {
                    "evaluator": {"status": "retry"},
                    # reviews and ship_check missing
                },
            }
        ],
    }
    _apply_schema_defaults(data)
    feat = data["features"][0]
    # existing evaluator.status must be preserved
    assert feat["quality_gates"]["evaluator"]["status"] == "retry"
    # missing subkeys must be filled with defaults
    assert "score" in feat["quality_gates"]["evaluator"]
    assert "defects" in feat["quality_gates"]["evaluator"]
    assert "evaluator_model" in feat["quality_gates"]["evaluator"]
    # missing top-level gates must be added
    assert "reviews" in feat["quality_gates"]
    assert "ship_check" in feat["quality_gates"]


def test_round_trip_preserves_unknown_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = tmp_path / "docs" / "progress-tracker" / "state"
    state.mkdir(parents=True)
    (state / "progress.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "features": [{"id": 1, "name": "x", "experimental_field": "keep me"}],
            }
        )
    )
    data = load_progress_json()
    assert data["features"][0]["experimental_field"] == "keep me"
    save_progress_json(data)
    reloaded = json.loads((state / "progress.json").read_text())
    assert reloaded["features"][0]["experimental_field"] == "keep me"
    assert reloaded["schema_version"] == "2.1"


def test_audit_log_records_schema_migration_event(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = tmp_path / "docs" / "progress-tracker" / "state"
    state.mkdir(parents=True)
    (state / "progress.json").write_text(
        json.dumps({"schema_version": "2.0", "features": []})
    )
    load_progress_json()
    audit = state / "audit.log"
    assert audit.exists()
    lines = audit.read_text().strip().splitlines()
    assert any("schema_migration" in line for line in lines)
