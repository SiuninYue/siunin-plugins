"""Readiness validation and remediation command tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


@pytest.fixture
def temp_dir(tmp_path):
    """Run each test in an isolated directory."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)


def test_validate_feature_readiness_all_pass():
    feature = {
        "id": 6,
        "name": "Feature Six",
        "test_steps": ["run tests"],
        "requirement_ids": ["REQ-006"],
        "change_spec": {"why": "Implement robust readiness checks before feature start."},
        "acceptance_scenarios": ["Scenario: feature start succeeds with complete contract."],
        "sprint_contract": {
            "scope": "Implement readiness checks",
            "done_criteria": ["all blockers validated"],
            "test_plan": ["run unit tests"],
        },
    }

    report = progress_manager.validate_feature_readiness(feature)

    assert report["valid"] is True
    assert report["errors"] == []
    assert report["warnings"] == []


def test_validate_feature_readiness_blockers():
    feature = {
        "id": 6,
        "name": "Feature Six",
        "test_steps": ["run tests"],
        "requirement_ids": [],
        "change_spec": {"why": "   "},
        "acceptance_scenarios": [],
    }

    report = progress_manager.validate_feature_readiness(feature)

    assert report["valid"] is False
    assert "requirement_ids cannot be empty" in report["errors"]
    assert "change_spec.why cannot be empty" in report["errors"]
    assert "acceptance_scenarios cannot be empty" in report["errors"]


def test_validate_feature_readiness_warnings():
    feature = {
        "id": 6,
        "name": "abc",
        "test_steps": [],
        "requirement_ids": ["REQ-006"],
        "change_spec": {"why": "short why"},
        "acceptance_scenarios": ["Scenario: baseline works."],
        "sprint_contract": {
            "scope": "s",
            "done_criteria": ["ok"],
            "test_plan": ["ok"],
        },
    }

    report = progress_manager.validate_feature_readiness(feature)

    assert report["valid"] is True
    assert report["errors"] == []
    assert "change_spec.why should be longer than 10 characters" in report["warnings"]
    assert "test_steps is empty" in report["warnings"]
    assert "name should be at least 5 characters" in report["warnings"]


def test_warns_empty_sprint_all_fields():
    feature = {
        "id": 6,
        "name": "Feature Six",
        "test_steps": ["run tests"],
        "requirement_ids": ["REQ-006"],
        "change_spec": {"why": "Detailed reason text for readiness contract."},
        "acceptance_scenarios": ["Scenario: baseline works."],
        "sprint_contract": {
            "scope": "",
            "done_criteria": [],
            "test_plan": [],
        },
    }
    report = progress_manager.validate_feature_readiness(feature)
    assert report["valid"] is True
    sprint_warnings = [w for w in report["warnings"] if "sprint_contract incomplete" in w]
    assert len(sprint_warnings) == 1
    assert "scope" in sprint_warnings[0]
    assert "done_criteria" in sprint_warnings[0]
    assert "test_plan" in sprint_warnings[0]


def test_warns_missing_sprint_key():
    feature = {
        "id": 6,
        "name": "Feature Six",
        "test_steps": ["run tests"],
        "requirement_ids": ["REQ-006"],
        "change_spec": {"why": "Detailed reason text for readiness contract."},
        "acceptance_scenarios": ["Scenario: baseline works."],
    }
    report = progress_manager.validate_feature_readiness(feature)
    assert report["valid"] is True
    sprint_warnings = [w for w in report["warnings"] if "sprint_contract incomplete" in w]
    assert len(sprint_warnings) == 1
    assert "scope" in sprint_warnings[0]
    assert "done_criteria" in sprint_warnings[0]
    assert "test_plan" in sprint_warnings[0]


def test_warns_empty_scope_only():
    feature = {
        "id": 6,
        "name": "Feature Six",
        "test_steps": ["run tests"],
        "requirement_ids": ["REQ-006"],
        "change_spec": {"why": "Detailed reason text for readiness contract."},
        "acceptance_scenarios": ["Scenario: baseline works."],
        "sprint_contract": {
            "scope": "",
            "done_criteria": ["ok"],
            "test_plan": ["ok"],
        },
    }
    report = progress_manager.validate_feature_readiness(feature)
    assert report["valid"] is True
    sprint_warnings = [w for w in report["warnings"] if "sprint_contract incomplete" in w]
    assert len(sprint_warnings) == 1
    assert "scope" in sprint_warnings[0]
    assert "done_criteria" not in sprint_warnings[0]
    assert "test_plan" not in sprint_warnings[0]


def test_no_warn_sprint_complete():
    feature = {
        "id": 6,
        "name": "Feature Six",
        "test_steps": ["run tests"],
        "requirement_ids": ["REQ-006"],
        "change_spec": {"why": "Detailed reason text for readiness contract."},
        "acceptance_scenarios": ["Scenario: baseline works."],
        "sprint_contract": {
            "scope": "Scope is complete.",
            "done_criteria": ["done"],
            "test_plan": ["tests"],
        },
    }
    report = progress_manager.validate_feature_readiness(feature)
    assert report["valid"] is True
    assert all("sprint_contract incomplete" not in w for w in report["warnings"])


def test_set_current_blocked_by_readiness(temp_dir):
    progress_manager.init_tracking("Readiness", force=True)
    progress_manager.add_feature("Feature Six", ["step 1"])

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = []
    feature["change_spec"] = {"why": ""}
    feature["acceptance_scenarios"] = []
    progress_manager.save_progress_json(data)

    assert progress_manager.set_current(1) is False


def test_set_current_does_not_modify_state_on_blocker(temp_dir):
    progress_manager.init_tracking("Readiness", force=True)
    progress_manager.add_feature("Feature Six", ["step 1"])

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = []
    feature["change_spec"] = {"why": ""}
    feature["acceptance_scenarios"] = []
    data["current_feature_id"] = None
    progress_manager.save_progress_json(data)

    assert progress_manager.set_current(1) is False

    refreshed = progress_manager.load_progress_json()
    blocked_feature = refreshed["features"][0]
    assert refreshed["current_feature_id"] is None
    assert blocked_feature.get("development_stage") != "developing"
    assert not blocked_feature.get("started_at")


def test_validate_readiness_command_exit_codes(temp_dir):
    progress_manager.init_tracking("Readiness", force=True)
    progress_manager.add_feature("Feature Six", ["step 1"])

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = []
    feature["change_spec"] = {"why": ""}
    feature["acceptance_scenarios"] = []
    progress_manager.save_progress_json(data)

    assert progress_manager.validate_readiness_command(1) == 1

    feature["requirement_ids"] = ["REQ-001"]
    feature["change_spec"] = {"why": "Detailed readiness reason text."}
    feature["acceptance_scenarios"] = ["Scenario: start works"]
    data["features"][0] = feature
    progress_manager.save_progress_json(data)

    assert progress_manager.validate_readiness_command(1) == 0


def test_fix_readiness_command(temp_dir):
    progress_manager.init_tracking("Readiness", force=True)
    progress_manager.add_feature("Feature Six", ["step 1"])

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = []
    feature["change_spec"] = {"why": ""}
    feature["acceptance_scenarios"] = []
    progress_manager.save_progress_json(data)

    assert progress_manager.fix_readiness_command(1, add_requirement="REQ-006") is True
    assert progress_manager.fix_readiness_command(
        1,
        set_why="Implement readiness validator for feature start.",
    ) is True
    assert progress_manager.fix_readiness_command(
        1,
        add_acceptance="Scenario: feature starts when blockers are resolved.",
    ) is True

    updated = progress_manager.load_progress_json()["features"][0]
    report = progress_manager.validate_feature_readiness(updated)
    assert report["valid"] is True
    assert "REQ-006" in updated["requirement_ids"]
    assert updated["change_spec"]["why"] == "Implement readiness validator for feature start."
    assert "Scenario: feature starts when blockers are resolved." in updated["acceptance_scenarios"]


def test_readiness_cmd_exit_zero_with_sprint_warn(temp_dir, capsys):
    progress_manager.init_tracking("Readiness", force=True)
    progress_manager.add_feature("Feature Six", ["step 1"])

    data = progress_manager.load_progress_json()
    feature = data["features"][0]
    feature["requirement_ids"] = ["REQ-001"]
    feature["change_spec"] = {"why": "Detailed readiness reason text."}
    feature["acceptance_scenarios"] = ["Scenario: start works"]
    feature["sprint_contract"] = {
        "scope": "",
        "done_criteria": [],
        "test_plan": [],
    }
    progress_manager.save_progress_json(data)

    assert progress_manager.validate_readiness_command(1) == 0
    captured = capsys.readouterr()
    assert "sprint_contract incomplete" in captured.out
