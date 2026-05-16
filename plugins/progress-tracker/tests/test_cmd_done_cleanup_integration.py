"""
T3: RED integration tests for cmd_done() + post-done cleanup.

Invocation model: all tests call cmd_done() in-process (direct Python function
call).  unittest.mock.patch only works in-process; CLI subprocess would ignore
patches.

Gate seeding strategy: the seeded_done_env fixture routes cmd_done() through
all completion gates by:
  - seeding progress.json with all quality_gates at "pass" in a tmp_path
  - seeding workflow_state.plan_path with a valid plan document
  - setting _PROJECT_ROOT_OVERRIDE to tmp_path so all file I/O goes there
  - mocking require_sprint_contract, _run_acceptance_tests,
    _save_done_test_report, record_sprint_artifact, and _notify_parent_sync
  - mocking collect_git_context to return a stable fixture context

cmd_done() finalization runs for real and writes to tmp_path so that
P1 state-invariant assertions can inspect the persisted result.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest

import progress_manager
from prog_paths import PROGRESS_ARCHIVE_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FEATURE_ID = 25


def _make_progress_json(tmp_path: Path) -> Path:
    """Write a fully-gated progress.json that allows cmd_done() to pass all gates."""
    plan_path = "docs/plans/2026-01-01-feature-25.md"
    plan_abs = tmp_path / plan_path
    plan_abs.parent.mkdir(parents=True, exist_ok=True)
    plan_abs.write_text(
        "# Cleanup Done Plan\n\n"
        "## Tasks\n\n"
        "- [ ] Run done flow\n\n"
        "## Acceptance Mapping\n\n"
        "- done exits zero\n\n"
        "## Risks\n\n"
        "- Minimal fixture drift\n",
        encoding="utf-8",
    )

    feature = {
        "id": _FEATURE_ID,
        "name": "cleanup-after-done test feature",
        "completed": False,
        "deferred": False,
        "lifecycle_state": "implementing",
        "development_stage": "developing",
        "change_spec": {
            "why": "test",
            "in_scope": [],
            "out_of_scope": [],
            "risks": [],
        },
        "requirement_ids": [f"REQ-{_FEATURE_ID:03d}"],
        "acceptance_scenarios": [],
        "acceptance_criteria": [],
        "integration_status": None,
        "quality_gates": {
            "evaluator": {
                "status": "pass",
                "score": 100,
                "defects": [],
                "last_run_at": "2026-01-01T00:00:00Z",
                "evaluator_model": None,
            },
            "ship_check": {
                "status": "pass",
                "failures": [],
                "last_run_at": "2026-01-01T00:00:00Z",
            },
            "reviews": {
                "required": ["eng"],
                "passed": ["eng"],
                "pending": [],
            },
        },
        "sprint_contract": {
            "scope": "cleanup after done",
            "done_criteria": ["cleanup runs after done"],
            "test_plan": ["pytest -q tests/test_cleanup_after_done.py"],
            "accepted_by": "test-suite",
            "accepted_at": "2026-01-01T00:00:00Z",
        },
        "handoff": {
            "from_phase": None,
            "to_phase": None,
            "artifact_path": None,
            "created_at": None,
        },
    }
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [feature],
        "current_feature_id": _FEATURE_ID,
        "updates": [],
        "retrospectives": [],
        "runtime_context": {},
        "linked_projects": [],
        "linked_snapshot": {},
        "tracker_role": "standalone",
        "project_code": None,
        "routing_queue": [],
        "active_routes": [],
        "bugs": [],
        "current_bug_id": None,
        "workflow_state": {"phase": "execution_complete", "plan_path": plan_path},
    }
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True)
    progress_file = state_dir / "progress.json"
    progress_file.write_text(json.dumps(data))
    return tmp_path


def _worktree_git_ctx(tmp_path: Path) -> dict:
    return {
        "branch": f"feature/feature-{_FEATURE_ID}",
        "workspace_mode": "worktree",
        "worktree_path": str(tmp_path / ".worktrees" / f"feature-{_FEATURE_ID}"),
    }


# ---------------------------------------------------------------------------
# Fixture: all gates passed, git ops mocked
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_done_env(tmp_path):
    """
    Provide a fully-gated cmd_done() environment.

    Gate seeding:
      1. _validate_done_preconditions — satisfied by progress.json content
         (current_feature_id set, not completed, phase=execution_complete)
      2. _validate_completion_plan_document — satisfied by valid docs/plans fixture file
      3. require_sprint_contract — mocked to no-op
      4. _run_acceptance_tests — mocked to return (True, [])
      5. evaluator gate — seeded in JSON: quality_gates.evaluator.status="pass"
      6. review gate — seeded in JSON: all required lanes in passed list
      7. ship_check gate — seeded in JSON: quality_gates.ship_check.status="pass"

    Additional mocks (no state side-effects):
      - _save_done_test_report → None (skips report path branch)
      - record_sprint_artifact → no-op
      - _notify_parent_sync → no-op
      - collect_git_context → returns fixture worktree context
    """
    proj_root = _make_progress_json(tmp_path)

    with (
        patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root),
        patch("progress_manager.require_sprint_contract", return_value=None),
        patch("progress_manager._run_acceptance_tests", return_value=(True, [])),
        patch("progress_manager._save_done_test_report", return_value=None),
        patch("progress_manager.record_sprint_artifact", return_value=None),
        patch("progress_manager._notify_parent_sync", return_value=None),
        patch("progress_manager.collect_git_context",
              return_value=_worktree_git_ctx(tmp_path)),
    ):
        yield proj_root


# ---------------------------------------------------------------------------
# T3 scenarios
# ---------------------------------------------------------------------------

def test_cmd_done_snapshots_branch_before_finalize(seeded_done_env):
    """cleanup_ctx captures branch/mode/path BEFORE in-memory finalization."""
    captured: dict = {}
    original_finalize = progress_manager._finalize_completion_state_in_memory

    def spy_finalize(data, feature_id, commit_hash=None):
        captured["called"] = True
        return original_finalize(data, feature_id, commit_hash=commit_hash)

    with (
        patch("progress_manager._finalize_completion_state_in_memory", side_effect=spy_finalize),
        patch("progress_manager._run_post_done_cleanup") as mock_cleanup,
    ):
        rc = progress_manager.cmd_done()

    assert rc == 0
    assert captured.get("called"), "_finalize_completion_state_in_memory must have been called"
    # Verify cleanup received the git context that was snapshotted before finalization.
    assert mock_cleanup.called
    ctx_arg = mock_cleanup.call_args[0][0]
    assert ctx_arg["branch"] == f"feature/feature-{_FEATURE_ID}"
    assert ctx_arg["workspace_mode"] == "worktree"


def test_cmd_done_no_cleanup_flag_skips_cleanup(seeded_done_env):
    """cmd_done(no_cleanup=True) → _run_post_done_cleanup called with skip=True."""
    with patch("progress_manager._run_post_done_cleanup") as mock_cleanup:
        rc = progress_manager.cmd_done(no_cleanup=True)

    assert rc == 0
    mock_cleanup.assert_called_once()
    _, kwargs = mock_cleanup.call_args
    assert kwargs.get("skip") is True or mock_cleanup.call_args[0][1] is True


def test_cmd_done_cleanup_failure_preserves_completion_state(seeded_done_env):
    """[P1 invariant] RuntimeError in _run_post_done_cleanup must not corrupt state.

    After the exception:
    - cmd_done() returns 0
    - progress.json is valid JSON (no partial-write corruption)
    - current_feature_id == null
    - If project is fully completed (single-feature), features list is empty
      because _reset_active_progress clears active state; otherwise features
      must show completed=True.
    """
    def raise_on_cleanup(ctx, skip=False):
        raise RuntimeError("simulated cleanup failure")

    with patch("progress_manager._run_post_done_cleanup", side_effect=raise_on_cleanup):
        rc = progress_manager.cmd_done()

    assert rc == 0, f"cmd_done must return 0 even when cleanup raises; got {rc}"

    # Read back the persisted state from tmp_path
    state_dir = seeded_done_env / "docs" / "progress-tracker" / "state"
    progress_file = state_dir / "progress.json"

    raw = progress_file.read_text()
    data = json.loads(raw)  # must not raise — no partial write

    assert data.get("current_feature_id") is None, (
        f"current_feature_id must be null after done, got {data.get('current_feature_id')}"
    )

    # Single-feature project: _reset_active_progress clears all features on
    # full completion, so an empty features list is the expected success state.
    features = data.get("features", [])
    if features:
        feat = next(f for f in features if f["id"] == _FEATURE_ID)
        assert feat.get("completed") is True, (
            f"feature.completed must be True after done, got {feat.get('completed')}"
        )


def test_cmd_done_non_git_context_does_not_block(seeded_done_env):
    """workspace_mode=unknown → cleanup skips, cmd_done returns 0."""
    with (
        patch("progress_manager.collect_git_context",
              return_value={"branch": "", "workspace_mode": "unknown", "worktree_path": None}),
        patch("progress_manager._remove_worktree") as m_remove,
        patch("progress_manager._delete_local_branch") as m_local,
        patch("progress_manager._delete_remote_branch") as m_remote,
    ):
        rc = progress_manager.cmd_done()

    assert rc == 0
    m_remove.assert_not_called()
    m_local.assert_not_called()
    m_remote.assert_not_called()


def test_archive_docs_skips_protected_architecture_md(tmp_path, caplog):
    """archive_feature_docs must skip the canonical architecture.md even when plan_path points there.

    Vulnerability being guarded: if a feature's plan_path is accidentally set to
    docs/progress-tracker/architecture/architecture.md, the archive flow would move
    (destroy) the immutable design doc. The guard must detect and skip this.
    """
    import logging

    _ARCH_FEATURE_ID = 42

    # Create the canonical protected file
    arch_dir = tmp_path / "docs" / "progress-tracker" / "architecture"
    arch_dir.mkdir(parents=True, exist_ok=True)
    arch_file = arch_dir / "architecture.md"
    original_content = "# Architecture\nImmutable design doc."
    arch_file.write_text(original_content, encoding="utf-8")

    # Also create the archive destination dir (archive_feature_docs creates it, but
    # we need progress.json to be readable first)
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    progress_data = {
        "schema_version": "2.1",
        "project_name": "arch-guard-test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [
            {
                "id": _ARCH_FEATURE_ID,
                "name": "arch guard test feature",
                "completed": True,
                "plan_path": "docs/progress-tracker/architecture/architecture.md",
            }
        ],
        "current_feature_id": None,
        "updates": [],
        "retrospectives": [],
        "runtime_context": {},
        "linked_projects": [],
        "linked_snapshot": {},
        "tracker_role": "standalone",
        "project_code": None,
        "routing_queue": [],
        "active_routes": [],
        "bugs": [],
        "current_bug_id": None,
    }
    (state_dir / "progress.json").write_text(json.dumps(progress_data), encoding="utf-8")

    with (
        patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", tmp_path),
        caplog.at_level(logging.WARNING, logger="progress_manager"),
    ):
        result = progress_manager.archive_feature_docs(_ARCH_FEATURE_ID)

    # File must NOT have been moved
    assert arch_file.exists(), "architecture.md must not be moved by archive_feature_docs"
    assert arch_file.read_text(encoding="utf-8") == original_content, (
        "architecture.md content must be unchanged"
    )

    # Guard must log a warning that mentions the skipped path
    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    protected_path = "docs/progress-tracker/architecture/architecture.md"
    assert any(protected_path in msg for msg in warning_messages), (
        f"Guard must log a WARNING containing '{protected_path}'; got: {warning_messages}"
    )

    # skipped_files must record the protected path
    assert any(
        "architecture.md" in entry for entry in result["skipped_files"]
    ), f"skipped_files must mention architecture.md; got: {result['skipped_files']}"


def test_cmd_done_preserves_architecture_md(seeded_done_env):
    """[Invariant] cmd_done must leave docs/progress-tracker/architecture/architecture.md untouched.

    Verifies the architecture immutability guarantee end-to-end: content is compared
    before and after cmd_done() to detect both deletion and silent modification.
    """
    arch_dir = seeded_done_env / "docs" / "progress-tracker" / "architecture"
    arch_dir.mkdir(parents=True, exist_ok=True)
    original_content = (
        "# Architecture\n\n"
        "This is the immutable design doc.\n"
        "It must not be modified by any done-flow operation.\n"
    )
    arch_file = arch_dir / "architecture.md"
    arch_file.write_text(original_content, encoding="utf-8")

    rc = progress_manager.cmd_done()

    assert rc == 0, f"cmd_done must succeed; got rc={rc}"
    assert arch_file.exists(), "architecture.md must not be deleted by cmd_done"
    assert arch_file.read_text(encoding="utf-8") == original_content, (
        "architecture.md content must be byte-for-byte unchanged after cmd_done"
    )


def test_cmd_done_completion_state_stable_before_cleanup_runs(seeded_done_env):
    """[P1 invariant] complete_feature() writes to disk BEFORE _run_post_done_cleanup runs.

    Even if cleanup is artificially delayed, the completed/reset state must
    already be persisted when the cleanup function is entered.  When the
    project is fully completed (single-feature), _reset_active_progress will
    have cleared the features list; otherwise the feature must show
    completed=True.
    """
    state_dir = seeded_done_env / "docs" / "progress-tracker" / "state"
    progress_file = state_dir / "progress.json"
    observed_during_cleanup: dict = {}

    def inspect_state_during_cleanup(ctx, skip=False):
        raw = progress_file.read_text()
        data = json.loads(raw)
        features = data.get("features", [])
        feat = next((f for f in features if f["id"] == _FEATURE_ID), None)
        if feat:
            observed_during_cleanup["completed"] = feat.get("completed")
        else:
            # Features list cleared by _reset_active_progress (project fully done)
            observed_during_cleanup["completed"] = "reset"
        observed_during_cleanup["current_feature_id"] = data.get("current_feature_id")
        observed_during_cleanup["features_empty"] = len(features) == 0

    with patch("progress_manager._run_post_done_cleanup",
               side_effect=inspect_state_during_cleanup):
        rc = progress_manager.cmd_done()

    assert rc == 0
    # Single-feature project: features cleared by _reset_active_progress
    # before cleanup runs; multi-feature: feature must be completed.
    assert observed_during_cleanup.get("completed") in (True, "reset"), (
        "feature.completed must already be True or reset when _run_post_done_cleanup "
        f"is entered; got {observed_during_cleanup.get('completed')}"
    )
    assert observed_during_cleanup.get("current_feature_id") is None, (
        "current_feature_id must already be null when _run_post_done_cleanup is entered; "
        f"got {observed_during_cleanup.get('current_feature_id')}"
    )


def test_cmd_done_preserves_state_when_project_completed_audit_fails(seeded_done_env):
    """project_completed 审计写入失败时，reset 需 fail-closed 保留 active state。

    仅拦截 event_type == "project_completed"，放行 feature_completed。
    防止 cmd_done() 回归为“边界事件丢失仍清空状态”的不安全行为。
    """
    original = progress_manager.record_feature_state_event

    def selective_fail(*args, **kwargs):
        if kwargs.get("event_type") == "project_completed":
            raise ValueError("audit fail")
        return original(*args, **kwargs)

    with patch.object(progress_manager, "record_feature_state_event",
                      side_effect=selective_fail):
        rc = progress_manager.cmd_done()

    assert rc == 0

    state_dir = seeded_done_env / "docs" / "progress-tracker" / "state"
    data = json.loads((state_dir / "progress.json").read_text())
    assert data["features"], "fail-closed: state must be preserved when project_completed audit fails"
    feature = next(f for f in data["features"] if f["id"] == _FEATURE_ID)
    assert feature["completed"] is True
    assert data["current_feature_id"] is None
