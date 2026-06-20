"""
RED-phase tests for the feature_commands module (F22).

These tests describe the target behaviour of
`hooks/scripts/feature_commands.py`, which extracts `set_current` and
`set_development_stage` out of `progress_manager.py` into a dedicated module.

All side effects are injected via `FeatureCommandsServices` (a dataclass of
callables). Tests mock every service field with `unittest.mock.MagicMock`, and
mock the readiness validator + `_is_deferred` helpers so the tests are isolated
from those modules' real behaviour.

The module does not exist yet, so importing it MUST fail (RED phase).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make hooks/scripts importable (same convention as conftest.py).
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Import under test. This will raise ModuleNotFoundError until the module is
# created — that is the expected RED state.
import feature_commands  # noqa: E402
from feature_commands import (  # noqa: E402
    FeatureCommandsServices,
    set_current_command,
    set_development_stage_command,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_services():
    """Build a FeatureCommandsServices with every field as a MagicMock."""
    return FeatureCommandsServices(
        load_progress_json_fn=MagicMock(),
        save_progress_json_fn=MagicMock(),
        generate_progress_md_fn=MagicMock(return_value="# progress md"),
        save_progress_md_fn=MagicMock(),
        update_runtime_context_fn=MagicMock(return_value=True),
        auto_state_commit_fn=MagicMock(return_value="abc123"),
        notify_parent_sync_fn=MagicMock(),
    )


def _data_with_feature(feature, current_feature_id=None):
    return {
        "schema_version": "2.1",
        "project_name": "test",
        "features": [feature],
        "current_feature_id": current_feature_id,
    }


def _valid_readiness():
    return {"valid": True, "warnings": []}


def _invalid_readiness():
    return {"valid": False, "warnings": [], "errors": ["missing test_steps"]}


@pytest.fixture
def patch_readiness_valid():
    """Patch readiness validator so features always pass with no warnings."""
    with patch.object(
        feature_commands, "validate_feature_readiness",
        return_value=_valid_readiness(),
    ) as v, patch.object(
        feature_commands, "print_readiness_error",
    ) as err, patch.object(
        feature_commands, "print_readiness_warnings",
    ) as warn:
        yield {"validate": v, "error": err, "warn": warn}


@pytest.fixture
def patch_not_deferred():
    """Patch the deferred check so features are treated as active."""
    with patch.object(
        feature_commands, "_is_deferred", return_value=False,
    ) as m:
        yield m


# ===========================================================================
# set_current tests
# ===========================================================================

def test_set_current_success(patch_readiness_valid, patch_not_deferred):
    """Valid, non-deferred feature passing readiness -> full success path."""
    feature = {"id": 1, "name": "Feature 1", "test_steps": ["s1"], "completed": False}
    data = _data_with_feature(feature, current_feature_id=None)

    svc = _make_services()
    svc.load_progress_json_fn.return_value = data

    with patch.object(feature_commands, "REVIEW_ROUTER_AVAILABLE", True), \
         patch.object(feature_commands, "_initialize_reviews") as mock_init_reviews:
        result = set_current_command(1, svc)

    assert result is True

    # reviews initialized via _initialize_reviews (REVIEW_ROUTER_AVAILABLE branch).
    mock_init_reviews.assert_called_once_with(feature)

    # Stage / lifecycle transition.
    assert feature["development_stage"] == "developing"
    assert feature["lifecycle_state"] == "implementing"

    # started_at recorded.
    assert feature.get("started_at")

    # workflow_state initialized for a newly switched feature.
    assert data["workflow_state"]["phase"] == "planning"

    # Runtime context updated with the correct source.
    svc.update_runtime_context_fn.assert_called_once_with(data, "set_current")

    # Persistence happened exactly once.
    svc.save_progress_json_fn.assert_called_once_with(data)

    # Deprecated progress.md cleanup hook runs without generating markdown.
    svc.generate_progress_md_fn.assert_not_called()
    svc.save_progress_md_fn.assert_called_once_with("")

    # Auto commit + parent notification.
    svc.auto_state_commit_fn.assert_called_once_with("F1", "start")
    svc.notify_parent_sync_fn.assert_called_once_with("activate")


def test_set_current_feature_not_found(patch_readiness_valid, patch_not_deferred):
    """Unknown feature id -> False and no persistence/commit/notify side effects."""
    feature = {"id": 1, "name": "Feature 1", "completed": False}
    data = _data_with_feature(feature)

    svc = _make_services()
    svc.load_progress_json_fn.return_value = data

    result = set_current_command(999, svc)

    assert result is False
    svc.save_progress_json_fn.assert_not_called()
    svc.auto_state_commit_fn.assert_not_called()
    svc.notify_parent_sync_fn.assert_not_called()


def test_set_current_deferred_blocked(patch_readiness_valid):
    """Deferred feature -> blocked, returns False, no state change/persistence."""
    feature = {
        "id": 1, "name": "Feature 1", "completed": False,
        "deferred": True, "defer_reason": "blocked on upstream",
    }
    data = _data_with_feature(feature)

    svc = _make_services()
    svc.load_progress_json_fn.return_value = data

    with patch.object(feature_commands, "_is_deferred", return_value=True):
        result = set_current_command(1, svc)

    assert result is False
    # No transition applied.
    assert "development_stage" not in feature
    assert "lifecycle_state" not in feature
    svc.save_progress_json_fn.assert_not_called()
    svc.auto_state_commit_fn.assert_not_called()
    svc.notify_parent_sync_fn.assert_not_called()


def test_set_current_readiness_blocked(patch_not_deferred):
    """Invalid readiness -> print_readiness_error called, returns False, no save."""
    feature = {"id": 1, "name": "Feature 1", "completed": False}
    data = _data_with_feature(feature)

    svc = _make_services()
    svc.load_progress_json_fn.return_value = data

    with patch.object(
        feature_commands, "validate_feature_readiness",
        return_value=_invalid_readiness(),
    ), patch.object(
        feature_commands, "print_readiness_error",
    ) as err:
        result = set_current_command(1, svc)

    assert result is False
    err.assert_called_once()
    svc.save_progress_json_fn.assert_not_called()
    svc.auto_state_commit_fn.assert_not_called()
    svc.notify_parent_sync_fn.assert_not_called()


# ===========================================================================
# set_development_stage tests
# ===========================================================================

def test_set_development_stage_to_developing(patch_readiness_valid):
    """developing on the current feature -> implementing + started_at + save."""
    feature = {"id": 2, "name": "Feature 2", "test_steps": ["s"], "completed": False}
    data = _data_with_feature(feature, current_feature_id=2)

    svc = _make_services()
    svc.load_progress_json_fn.return_value = data

    result = set_development_stage_command("developing", svc)

    assert result is True
    assert feature["development_stage"] == "developing"
    assert feature["lifecycle_state"] == "implementing"
    assert feature.get("started_at")

    svc.save_progress_json_fn.assert_called_once_with(data)
    svc.update_runtime_context_fn.assert_called_once()
    svc.generate_progress_md_fn.assert_not_called()
    svc.save_progress_md_fn.assert_called_once_with("")


def test_set_development_stage_planning_and_completed(patch_readiness_valid):
    """planning -> approved; completed -> verified. Each saves + updates context."""
    # planning
    feature_p = {"id": 1, "name": "F", "completed": False}
    data_p = _data_with_feature(feature_p, current_feature_id=1)
    svc_p = _make_services()
    svc_p.load_progress_json_fn.return_value = data_p

    result_p = set_development_stage_command("planning", svc_p)

    assert result_p is True
    assert feature_p["development_stage"] == "planning"
    assert feature_p["lifecycle_state"] == "approved"
    svc_p.save_progress_json_fn.assert_called_once_with(data_p)
    svc_p.update_runtime_context_fn.assert_called_once()

    # completed
    feature_c = {"id": 1, "name": "F", "completed": False}
    data_c = _data_with_feature(feature_c, current_feature_id=1)
    svc_c = _make_services()
    svc_c.load_progress_json_fn.return_value = data_c

    result_c = set_development_stage_command("completed", svc_c)

    assert result_c is True
    assert feature_c["development_stage"] == "completed"
    assert feature_c["lifecycle_state"] == "verified"
    svc_c.save_progress_json_fn.assert_called_once_with(data_c)
    svc_c.update_runtime_context_fn.assert_called_once()


def test_set_development_stage_invalid_cases():
    """Unknown stage -> False without loading; no current/feature_id -> False."""
    # Unknown stage: must short-circuit before loading progress.
    svc1 = _make_services()
    result_unknown = set_development_stage_command("bogus-stage", svc1)
    assert result_unknown is False
    svc1.load_progress_json_fn.assert_not_called()

    # No current_feature_id and no feature_id argument -> False.
    feature = {"id": 1, "name": "F", "completed": False}
    data = _data_with_feature(feature, current_feature_id=None)
    svc2 = _make_services()
    svc2.load_progress_json_fn.return_value = data

    result_no_target = set_development_stage_command("planning", svc2)
    assert result_no_target is False
    svc2.save_progress_json_fn.assert_not_called()
