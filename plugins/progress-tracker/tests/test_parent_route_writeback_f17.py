"""F17 RED-phase tests: parent active_routes writeback on set_current / cmd_done.

These tests describe the F17 feature contract:

1. When a child plugin calls ``set_current(feature_id)``, the parent
   ``progress.json`` must auto-upsert an entry into ``active_routes`` for the
   child's ``project_code`` and the selected ``feature_ref``.
2. When the child plugin calls ``cmd_done()`` (or the underlying clear hook),
   the parent ``active_routes`` entry for that child must be removed.
3. When the parent already has a different project active in ``active_routes``,
   ``set_current`` must still succeed but emit a ``WARNING`` describing the
   parallel routes.
4. When the child is properly registered in ``linked_projects`` but
   ``active_routes`` is empty (bootstrap), ``set_current`` must succeed and
   emit a bootstrap/warn message rather than being blocked.

All tests are expected to FAIL on the pre-F17 codebase (RED phase).

Run only this file with:
    PYTHONPATH=hooks/scripts pytest tests/test_parent_route_writeback_f17.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

# Make ``progress_manager`` importable (conftest already does this, but we
# guard against direct invocations).
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager  # type: ignore[import]  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_progress(root: Path, payload: dict) -> None:
    """Write progress.json to ``<root>/docs/progress-tracker/state/``."""
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _read_progress(root: Path) -> dict:
    return json.loads(
        (root / "docs" / "progress-tracker" / "state" / "progress.json").read_text(
            encoding="utf-8"
        )
    )


def _git_init(repo_root: Path) -> None:
    """Initialise a minimal git repo so progress_manager can resolve REPO_ROOT."""
    subprocess.run(
        ["git", "init"], cwd=repo_root, capture_output=True, check=False
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )


def _activate_child(child_root: Path, repo_root: Path) -> None:
    """Point progress_manager at the child project (used inside a test body)."""
    progress_manager._PROJECT_ROOT_OVERRIDE = child_root
    progress_manager._STORAGE_READY_ROOT = None
    progress_manager._REPO_ROOT = str(repo_root)


def _build_parent_payload(
    *,
    linked_code: str = "PT",
    linked_root: str = "plugins/child-pt",
    active_routes: list | None = None,
) -> dict:
    if active_routes is None:
        active_routes = []
    return {
        "project_name": "Parent",
        "tracker_role": "parent",
        "project_code": "ROOT",
        "created_at": "2026-01-01T00:00:00Z",
        "features": [],
        "current_feature_id": None,
        "linked_projects": [
            {
                "project_root": linked_root,
                "project_code": linked_code,
                "label": linked_code,
            }
        ],
        "linked_snapshot": {"projects": []},
        "active_routes": list(active_routes),
        "routing_queue": [linked_code],
    }


def _build_child_payload(
    *,
    project_code: str = "PT",
    parent_root_rel: str = "plugins/progress-tracker",
    features: list | None = None,
    current_feature_id=None,
) -> dict:
    if features is None:
        features = [
            {
                "id": 14,
                "name": "Feature 14",
                "completed": False,
                "test_steps": ["run pytest"],
                "lifecycle_state": "approved",
                "deferred": False,
            }
        ]
    return {
        "project_name": "Child PT",
        "tracker_role": "child",
        "project_code": project_code,
        "created_at": "2026-01-01T00:00:00Z",
        "parent_project_root": parent_root_rel,
        "features": features,
        "current_feature_id": current_feature_id,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_set_current_upserts_parent_active_routes(temp_dir):
    """T1.1: child set_current should upsert parent active_routes entry."""
    repo_root = temp_dir / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_init(repo_root)

    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "child-pt"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    _write_progress(parent_root, _build_parent_payload())
    _write_progress(child_root, _build_child_payload())

    original_cwd = os.getcwd()
    try:
        os.chdir(child_root)
        _activate_child(child_root, repo_root)
        result = progress_manager.set_current(14)
    finally:
        os.chdir(original_cwd)
        progress_manager._PROJECT_ROOT_OVERRIDE = None
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None

    assert result is True, "set_current should succeed for a valid feature"

    parent_data = _read_progress(parent_root)
    active_routes = parent_data.get("active_routes") or []
    pt_routes = [
        r for r in active_routes
        if isinstance(r, dict) and r.get("project_code") == "PT"
    ]
    assert pt_routes, (
        "Parent active_routes should contain a PT entry after child set_current. "
        f"Current active_routes={active_routes}"
    )
    feature_ref = str(pt_routes[0].get("feature_ref") or "")
    assert "PT-F14" in feature_ref, (
        f"Expected feature_ref to include 'PT-F14', got {feature_ref!r}"
    )


def test_cmd_done_removes_parent_active_route(temp_dir):
    """T1.2: notifying the parent with 'clear' should remove the child route."""
    repo_root = temp_dir / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_init(repo_root)

    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "child-pt"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    parent_payload = _build_parent_payload(
        active_routes=[
            {
                "project_code": "PT",
                "feature_ref": "PT-F14",
                "assigned_at": "2026-01-01T00:00:00Z",
            }
        ]
    )
    _write_progress(parent_root, parent_payload)

    child_payload = _build_child_payload(current_feature_id=14)
    # Mark the feature as completed so the clear path is logically consistent
    child_payload["features"][0]["completed"] = True
    child_payload["features"][0]["completed_at"] = "2026-01-02T00:00:00Z"
    _write_progress(child_root, child_payload)

    original_cwd = os.getcwd()
    try:
        os.chdir(child_root)
        _activate_child(child_root, repo_root)
        # F17 will introduce a clear action on _notify_parent_sync.
        # On the pre-F17 codebase this call raises TypeError because the
        # function currently takes no arguments — that is the RED state.
        progress_manager._notify_parent_sync("clear")
    finally:
        os.chdir(original_cwd)
        progress_manager._PROJECT_ROOT_OVERRIDE = None
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None

    parent_data = _read_progress(parent_root)
    active_routes = parent_data.get("active_routes") or []
    pt_routes = [
        r for r in active_routes
        if isinstance(r, dict) and r.get("project_code") == "PT"
    ]
    assert not pt_routes, (
        "Parent active_routes should no longer contain a PT entry after clear. "
        f"Current active_routes={active_routes}"
    )


def test_set_current_warns_on_parallel_routes(temp_dir, capsys):
    """T1.3: set_current must succeed but warn when another route is active."""
    repo_root = temp_dir / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_init(repo_root)

    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "child-pt"
    other_child_root = repo_root / "plugins" / "child-no"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)
    other_child_root.mkdir(parents=True, exist_ok=True)

    parent_payload = _build_parent_payload(
        active_routes=[
            {
                "project_code": "NO",
                "feature_ref": "NO-F1",
                "assigned_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    # Register both PT and NO so PT is a known linked project.
    parent_payload["linked_projects"] = [
        {
            "project_root": "plugins/child-pt",
            "project_code": "PT",
            "label": "PT",
        },
        {
            "project_root": "plugins/child-no",
            "project_code": "NO",
            "label": "NO",
        },
    ]
    parent_payload["routing_queue"] = ["PT", "NO"]
    _write_progress(parent_root, parent_payload)
    _write_progress(child_root, _build_child_payload())

    original_cwd = os.getcwd()
    try:
        os.chdir(child_root)
        _activate_child(child_root, repo_root)
        result = progress_manager.set_current(14)
    finally:
        os.chdir(original_cwd)
        progress_manager._PROJECT_ROOT_OVERRIDE = None
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None

    assert result is True, (
        "set_current should still succeed even when other routes are active "
        "(it must only warn, not block)."
    )

    captured = capsys.readouterr().out
    # Filter out the unrelated sprint_contract incompleteness notice that
    # ``set_current`` already prints in every test scenario.
    relevant = "\n".join(
        line for line in captured.splitlines()
        if "sprint_contract" not in line.lower()
    )
    has_warning_marker = "[WARNING]" in relevant or "WARNING:" in relevant
    mentions_parallel = (
        "parallel" in relevant.lower()
        or "another" in relevant.lower()
        or "other route" in relevant.lower()
        or "active route" in relevant.lower()
    )
    assert has_warning_marker and mentions_parallel, (
        "Expected a [WARNING]/WARNING: line describing parallel active routes "
        f"in stdout. Got (filtered):\n{relevant}\n\nFull stdout:\n{captured}"
    )


def test_set_current_bootstrap_warn_when_active_routes_absent(temp_dir, capsys):
    """T1.4: bootstrap exception — empty active_routes must not block set_current.

    enforce_route_preflight (called via main()) must allow set-current through
    when the child is properly registered in linked_projects but active_routes is
    empty, and must emit a bootstrap [WARNING].
    """
    repo_root = temp_dir / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_init(repo_root)

    parent_root = repo_root / "plugins" / "progress-tracker"
    child_root = repo_root / "plugins" / "child-pt"
    parent_root.mkdir(parents=True, exist_ok=True)
    child_root.mkdir(parents=True, exist_ok=True)

    # Parent has PT linked but no active routes — the bootstrap scenario.
    _write_progress(parent_root, _build_parent_payload(active_routes=[]))
    _write_progress(child_root, _build_child_payload())

    original_cwd = os.getcwd()
    try:
        os.chdir(repo_root)
        # Go through main() so that enforce_route_preflight is invoked.
        with patch(
            "sys.argv",
            [
                "progress_manager.py",
                "--project-root",
                "plugins/child-pt",
                "set-current",
                "14",
            ],
        ):
            result = progress_manager.main()
    finally:
        os.chdir(original_cwd)
        progress_manager._PROJECT_ROOT_OVERRIDE = None
        progress_manager._STORAGE_READY_ROOT = None
        progress_manager._REPO_ROOT = None

    assert result is True, (
        "set_current must succeed in the bootstrap scenario where parent "
        "linked_projects already contains the child but active_routes is empty."
    )

    captured = capsys.readouterr().out
    relevant_lines = [
        line for line in captured.splitlines()
        if "sprint_contract" not in line.lower()
    ]
    relevant = "\n".join(relevant_lines).lower()
    assert "bootstrap" in relevant or (
        "[warning]" in relevant and "active_route" in relevant
    ), (
        "Expected a [WARNING] bootstrap notice in stdout. "
        f"Got (filtered):\n{relevant}\n\nFull stdout:\n{captured}"
    )
