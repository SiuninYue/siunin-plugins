"""
BUG-002 regression tests: lock-exemption scope for `prog complete`.

Two contracts:
  1. `prog complete` (cmd_done redirect path) must NOT hold the outer lock —
     acceptance-test subprocesses need to acquire it (BUG-002).
  2. `prog complete --unsafe-legacy` (complete_feature path) MUST hold the
     outer lock — complete_feature() has no internal locking and does
     multiple load-mutate-save cycles that need serialisation (PR review).

Deadlock path (BUG-002, before original fix):
    main()
      └─ MUTATING_COMMANDS: "complete" → with progress_transaction()
           └─ _dispatch_command() → cmd_done()
                └─ _run_acceptance_tests()
                     └─ subprocess.run("prog set-workflow-state ...")
                          └─ new process: progress_transaction()
                               └─ fcntl.LOCK_EX|LOCK_NB → BLOCKED (parent holds) → RC=9

Race condition (before PR-review fix):
    main()
      └─ "complete" in {"done","complete"} → lock SKIPPED
           └─ _dispatch_command() → complete_feature()  (--unsafe-legacy)
                └─ save_progress_json()  \
                └─ load_progress_json()   > no locking → concurrent writes interleave
                └─ save_archive_record() /
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager as pm


def _make_progress_data(current_id: int = 1) -> dict:
    return {
        "schema_version": "2.1",
        "project_name": "bug-002-test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Feature 1",
                "test_steps": [],
                "completed": False,
                "development_stage": "developing",
                "lifecycle_state": "implementing",
            }
        ],
        "current_feature_id": current_id,
    }


@pytest.fixture()
def complete_scope(project_scope):
    """Minimal isolated state: feature 1 in-progress, set as current."""
    state_dir = project_scope["state_dir"]
    (state_dir / "progress.json").write_text(json.dumps(_make_progress_data()))
    return project_scope


def test_complete_does_not_hold_lock_when_calling_cmd_done(complete_scope, monkeypatch):
    """
    `prog complete 1` must invoke cmd_done() with _PROGRESS_LOCK_DEPTH == 0.

    Before the fix: complete is in MUTATING_COMMANDS but not in the 'done'
    lock-exemption branch, so _dispatch_command() runs inside
    progress_transaction() → _PROGRESS_LOCK_DEPTH == 1 when cmd_done is entered
    → subprocess prog commands in acceptance tests deadlock (BUG-002).

    After the fix: complete joins the exemption → depth == 0.
    """
    root = complete_scope["root"]
    lock_depth_at_cmd_done: list[int] = []

    def tracking_cmd_done(**kwargs):
        lock_depth_at_cmd_done.append(pm._PROGRESS_LOCK_DEPTH)
        return 0

    def mock_configure_project_scope(project_root_arg=None):
        pm._PROJECT_ROOT_OVERRIDE = root
        pm._STORAGE_READY_ROOT = None
        return True

    monkeypatch.setattr(pm, "cmd_done", tracking_cmd_done)
    monkeypatch.setattr(pm, "enforce_route_preflight", lambda *a, **kw: True)
    monkeypatch.setattr(pm, "configure_project_scope", mock_configure_project_scope)
    monkeypatch.setattr(sys, "argv", ["prog", "complete", "1"])

    pm.main()

    assert lock_depth_at_cmd_done, (
        "cmd_done was never called — feature_id/current_id mismatch or early exit in test setup"
    )
    assert lock_depth_at_cmd_done[0] == 0, (
        f"BUG-002: cmd_done was entered with _PROGRESS_LOCK_DEPTH={lock_depth_at_cmd_done[0]}, "
        "expected 0. 'prog complete' must NOT hold the outer progress lock when dispatching "
        "to cmd_done — acceptance-test subprocesses will deadlock trying to acquire the same lock."
    )


def test_complete_unsafe_legacy_holds_progress_lock(complete_scope, monkeypatch):
    """
    `prog complete 1 --unsafe-legacy` must call complete_feature() with
    _PROGRESS_LOCK_DEPTH >= 1.

    complete_feature() has no internal progress_transaction() and performs
    multiple load-mutate-save cycles. Without the outer lock, concurrent
    mutating prog invocations can interleave writes and corrupt tracker state.

    The lock exemption introduced for BUG-002 must NOT apply to this path.
    """
    root = complete_scope["root"]
    lock_depth_at_complete_feature: list[int] = []

    def tracking_complete_feature(feature_id, **kwargs):
        lock_depth_at_complete_feature.append(pm._PROGRESS_LOCK_DEPTH)
        return 0

    def mock_configure_project_scope(project_root_arg=None):
        pm._PROJECT_ROOT_OVERRIDE = root
        pm._STORAGE_READY_ROOT = None
        return True

    monkeypatch.setattr(pm, "complete_feature", tracking_complete_feature)
    monkeypatch.setattr(pm, "enforce_route_preflight", lambda *a, **kw: True)
    monkeypatch.setattr(pm, "configure_project_scope", mock_configure_project_scope)
    monkeypatch.setattr(sys, "argv", ["prog", "complete", "1", "--unsafe-legacy"])

    pm.main()

    assert lock_depth_at_complete_feature, (
        "complete_feature was never called — check test setup"
    )
    assert lock_depth_at_complete_feature[0] >= 1, (
        f"complete --unsafe-legacy must hold outer progress lock (depth >= 1) when calling "
        f"complete_feature, got _PROGRESS_LOCK_DEPTH={lock_depth_at_complete_feature[0]}. "
        "complete_feature has no internal locking — the outer transaction is its only guard."
    )
