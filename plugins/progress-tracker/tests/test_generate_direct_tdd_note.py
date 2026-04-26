"""Tests for generate_direct_tdd_note() command."""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


def _make_feature(
    feature_id=1,
    name="Test Feature",
    test_steps=None,
    change_spec=None,
    acceptance_scenarios=None,
    ai_metrics=None,
):
    """Build a minimal feature dict."""
    feature = {
        "id": feature_id,
        "name": name,
        "test_steps": test_steps or ["Write unit test", "Verify output"],
        "completed": False,
    }
    if change_spec is not None:
        feature["change_spec"] = change_spec
    if acceptance_scenarios is not None:
        feature["acceptance_scenarios"] = acceptance_scenarios
    if ai_metrics is not None:
        feature["ai_metrics"] = ai_metrics
    return feature


def _write_progress(state_dir, features, current_id=None, workflow_state=None):
    """Write progress.json with given features."""
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": features,
        "current_feature_id": current_id,
    }
    if workflow_state is not None:
        data["workflow_state"] = workflow_state
    path = state_dir / "progress.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture()
def project_env(tmp_path):
    """Set up an isolated project environment with state dir and plans dir."""
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    plans_dir = tmp_path / "docs" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
    progress_manager._STORAGE_READY_ROOT = None

    yield {"root": tmp_path, "state_dir": state_dir, "plans_dir": plans_dir}

    progress_manager._PROJECT_ROOT_OVERRIDE = None
    progress_manager._STORAGE_READY_ROOT = None


class TestGenerateDirectTddNote:
    def test_creates_note_from_metadata(self, project_env):
        """Creates file and converges workflow state from feature metadata."""
        feature = _make_feature(
            feature_id=5,
            name="Widget Parser",
            test_steps=["Parse widget input", "Handle empty input"],
            change_spec={
                "why": "Enable widget parsing for pipeline.",
                "in_scope": ["Widget parsing"],
                "out_of_scope": ["Logging changes"],
                "risks": ["May break legacy format"],
            },
            acceptance_scenarios=["Scenario: parses valid widget"],
        )
        _write_progress(project_env["state_dir"], [feature], current_id=5)

        result = progress_manager.generate_direct_tdd_note()
        assert result is True

        data = progress_manager.load_progress_json()
        workflow_state = data["workflow_state"]
        assert workflow_state["phase"] == "execution"
        assert workflow_state["next_action"] == "direct_tdd"
        assert workflow_state["plan_path"].startswith("docs/plans/")
        assert "widget-parser" in workflow_state["plan_path"]

        note_path = project_env["root"] / workflow_state["plan_path"]
        assert note_path.exists()
        content = note_path.read_text(encoding="utf-8")
        assert "**Goal:**" in content
        assert "**Architecture:**" in content
        assert "## Tasks" in content
        assert "## Acceptance Mapping" in content
        assert "## Risks" in content
        assert "- [ ] Parse widget input" in content
        assert "- [ ] Handle empty input" in content

    def test_passes_validate_plan_document(self, project_env):
        """Generated note passes validate_plan_document() strict profile."""
        feature = _make_feature(feature_id=1, name="Strict Check")
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        progress_manager.generate_direct_tdd_note()

        data = progress_manager.load_progress_json()
        plan_path = data["workflow_state"]["plan_path"]
        result = progress_manager.validate_plan_document(plan_path)
        assert result["valid"] is True
        assert result["profile"] == "strict"

    def test_idempotent_file_preserved_state_converged(self, project_env):
        """Reuses an existing valid note and still converges workflow_state."""
        feature = _make_feature(feature_id=1, name="Idempotent Test")
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        progress_manager.generate_direct_tdd_note()
        data = progress_manager.load_progress_json()
        plan_path = data["workflow_state"]["plan_path"]
        note_file = project_env["root"] / plan_path

        first_content = note_file.read_text(encoding="utf-8")
        note_file.write_text(
            first_content + "\n<!-- sentinel-preserve -->\n",
            encoding="utf-8",
        )
        digest_first = hashlib.sha256(note_file.read_bytes()).hexdigest()

        data["workflow_state"] = {}
        (project_env["state_dir"] / "progress.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = progress_manager.generate_direct_tdd_note()
        assert result is True

        digest_second = hashlib.sha256(note_file.read_bytes()).hexdigest()
        assert digest_first == digest_second

        data = progress_manager.load_progress_json()
        workflow_state = data["workflow_state"]
        assert workflow_state["phase"] == "execution"
        assert workflow_state["next_action"] == "direct_tdd"
        assert workflow_state["plan_path"] == plan_path

    def test_regenerates_when_plan_invalid(self, project_env):
        """Regenerates when stored plan_path points to an invalid file."""
        feature = _make_feature(feature_id=1, name="Regen Test")
        _write_progress(
            project_env["state_dir"],
            [feature],
            current_id=1,
            workflow_state={
                "plan_path": "docs/plans/bad-note.md",
                "phase": "execution",
            },
        )
        bad_plan = project_env["root"] / "docs" / "plans" / "bad-note.md"
        bad_plan.write_text("# Bad Plan\n\nNo tasks here.\n", encoding="utf-8")

        result = progress_manager.generate_direct_tdd_note()
        assert result is True

        data = progress_manager.load_progress_json()
        workflow_state = data["workflow_state"]
        new_plan = project_env["root"] / workflow_state["plan_path"]
        assert new_plan.exists()
        content = new_plan.read_text(encoding="utf-8")
        assert "## Tasks" in content

    def test_state_converged_when_note_preexists(self, project_env):
        """Existing valid note still gets phase and next_action convergence."""
        feature = _make_feature(feature_id=1, name="Preexist Test")
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        progress_manager.generate_direct_tdd_note()
        data = progress_manager.load_progress_json()
        plan_path = data["workflow_state"]["plan_path"]

        data["workflow_state"] = {"plan_path": plan_path}
        (project_env["state_dir"] / "progress.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = progress_manager.generate_direct_tdd_note()
        assert result is True

        data = progress_manager.load_progress_json()
        workflow_state = data["workflow_state"]
        assert workflow_state["phase"] == "execution"
        assert workflow_state["next_action"] == "direct_tdd"
        assert workflow_state["plan_path"] == plan_path

    def test_no_current_feature(self, project_env):
        """Returns False when no feature is active."""
        _write_progress(project_env["state_dir"], [], current_id=None)

        result = progress_manager.generate_direct_tdd_note()
        assert result is False

    def test_defaults_when_missing_metadata(self, project_env):
        """Uses default metadata builders for missing fields."""
        feature = _make_feature(
            feature_id=1,
            name="Defaults Feature",
            test_steps=["Run smoke test"],
        )
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        result = progress_manager.generate_direct_tdd_note()
        assert result is True

        data = progress_manager.load_progress_json()
        note_path = project_env["root"] / data["workflow_state"]["plan_path"]
        content = note_path.read_text(encoding="utf-8")
        assert "Deliver Defaults Feature" in content
        assert "- [ ] Run smoke test" in content

    def test_handles_non_dict_workflow_state(self, project_env):
        """Malformed workflow_state is repaired and replaced by converged state."""
        feature = _make_feature(feature_id=1, name="Bad WS Type")
        _write_progress(
            project_env["state_dir"],
            [feature],
            current_id=1,
            workflow_state="not-a-dict",
        )

        result = progress_manager.generate_direct_tdd_note()
        assert result is True
        data = progress_manager.load_progress_json()
        assert isinstance(data["workflow_state"], dict)
        assert data["workflow_state"]["phase"] == "execution"
        assert data["workflow_state"]["next_action"] == "direct_tdd"

    def test_missing_workflow_state_is_not_pre_repaired(self, project_env, monkeypatch):
        """Missing workflow_state is legal and only gets the convergence write."""
        feature = _make_feature(feature_id=1, name="Missing WS")
        _write_progress(project_env["state_dir"], [feature], current_id=1)
        original_save = progress_manager.save_progress_json
        save_calls = []

        def counted_save(data):
            save_calls.append(data.get("workflow_state"))
            return original_save(data)

        monkeypatch.setattr(progress_manager, "save_progress_json", counted_save)

        result = progress_manager.generate_direct_tdd_note()
        assert result is True
        assert len(save_calls) == 1
        assert save_calls[0]["phase"] == "execution"

    def test_normalizes_string_change_spec_fields(self, project_env):
        """String change_spec list fields become single-item lists."""
        feature = _make_feature(
            feature_id=1,
            name="Normalize Fields",
            change_spec={
                "why": "Normalize metadata types.",
                "in_scope": "API contract update",
                "out_of_scope": "No migration changes",
                "risks": "Potential integration mismatch",
            },
            acceptance_scenarios=["Scenario: contract remains backward compatible"],
        )
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        result = progress_manager.generate_direct_tdd_note()
        assert result is True
        data = progress_manager.load_progress_json()
        note_path = project_env["root"] / data["workflow_state"]["plan_path"]
        content = note_path.read_text(encoding="utf-8")
        assert "Direct TDD implementation of API contract update." in content
        assert "Out of scope: No migration changes." in content
        assert "- Potential integration mismatch" in content

    def test_cli_dispatch(self, project_env):
        """Verify argparse registration and dispatch work end-to-end."""
        feature = _make_feature(feature_id=1, name="CLI Test")
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        test_argv = ["progress_manager.py", "generate-direct-tdd-note"]
        with patch.object(sys, "argv", test_argv), patch.object(
            progress_manager, "configure_project_scope"
        ):
            result = progress_manager.main()

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "execution"
        assert data["workflow_state"]["next_action"] == "direct_tdd"

    def test_set_workflow_state_rejects_before_file_write(self, project_env):
        """Documents the required write-before-set-workflow-state ordering."""
        feature = _make_feature(feature_id=1, name="Order Test")
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        nonexistent_plan = "docs/plans/2026-01-01-feature-1-order-test.md"
        result = progress_manager.set_workflow_state(
            phase="execution",
            plan_path=nonexistent_plan,
        )
        assert result is False

    def test_already_in_execution_phase(self, project_env):
        """Already-execution features still converge successfully."""
        feature = _make_feature(feature_id=1, name="Already Exec")
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        progress_manager.generate_direct_tdd_note()
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "execution"

        result = progress_manager.generate_direct_tdd_note()
        assert result is True
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["phase"] == "execution"
        assert data["workflow_state"]["next_action"] == "direct_tdd"

    def test_already_in_execution_without_valid_plan_regenerates(self, project_env):
        """Regenerates note when execution state points to a missing plan."""
        feature = _make_feature(feature_id=1, name="Missing Plan")
        _write_progress(
            project_env["state_dir"],
            [feature],
            current_id=1,
            workflow_state={
                "phase": "execution",
                "plan_path": "docs/plans/gone.md",
                "next_action": "direct_tdd",
            },
        )

        result = progress_manager.generate_direct_tdd_note()
        assert result is True

        data = progress_manager.load_progress_json()
        workflow_state = data["workflow_state"]
        new_note = project_env["root"] / workflow_state["plan_path"]
        assert new_note.exists()
        content = new_note.read_text(encoding="utf-8")
        assert "## Tasks" in content

    def test_full_phase_transition(self, project_env):
        """Verifies direct_tdd then verify_and_complete next_action transition."""
        feature = _make_feature(feature_id=1, name="Transition Test")
        _write_progress(project_env["state_dir"], [feature], current_id=1)

        progress_manager.generate_direct_tdd_note()
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["next_action"] == "direct_tdd"
        assert data["workflow_state"]["phase"] == "execution"

        progress_manager.set_workflow_state(
            phase="execution_complete",
            next_action="verify_and_complete",
        )
        data = progress_manager.load_progress_json()
        assert data["workflow_state"]["next_action"] == "verify_and_complete"
        assert data["workflow_state"]["phase"] == "execution_complete"

    def test_direct_tdd_bypass_still_works(self, project_env):
        """validate_plan() still accepts legacy direct_tdd state without plan_path."""
        feature = _make_feature(
            feature_id=1,
            name="Bypass Test",
            ai_metrics={"workflow_path": "direct_tdd"},
        )
        _write_progress(
            project_env["state_dir"],
            [feature],
            current_id=1,
            workflow_state={},
        )

        result = progress_manager.validate_plan()
        assert result is True
