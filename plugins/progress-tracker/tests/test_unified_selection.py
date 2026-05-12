#!/usr/bin/env python3
"""
RED-phase tests for PT-F13 unified work-item selection.

PT-F13 introduces ``_select_next_work_item()`` which replaces the parent
``routing_queue``-only dispatch inside ``next_feature()``. The new selector
must honor a single global priority order:

    P0 bug  >  P1 bug  >  standalone task  >  feature_task  >  P2 bug

routing_queue scanning rules:
    * ``BUG-<N>``       → lookup in ``bugs[]``; skip if ``status`` in
                          {fixed, false_positive} or if the BUG id is already
                          present in ``active_routes`` (status != done/cancelled).
    * ``ROOT``          → return first root-level pending feature.
    * ``<other-code>``  → child project dispatch (existing behavior).

Fallback when routing_queue produces nothing:
    1. Scan ``tasks[]`` for the first pending task.
    2. Otherwise delegate to ``get_next_feature()``.

priority → tier mapping for bugs:
    * high   → P0
    * medium → P1
    * low    → P2

These tests intentionally fail before ``_select_next_work_item`` is wired
into ``next_feature()``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# Path to the progress_manager.py script (subprocess CLI entry point)
PROGRESS_MANAGER = os.path.join(
    os.path.dirname(__file__),
    "..",
    "hooks",
    "scripts",
    "progress_manager.py",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_prog(*args, cwd):
    """Invoke progress_manager.py as a subprocess.

    Returns the CompletedProcess instance (always with text=True).
    """
    return subprocess.run(
        [sys.executable, PROGRESS_MANAGER, *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=30,
        input="",
    )


def _init_project(cwd, name="UnifiedSelectionTest"):
    """Initialize a fresh progress-tracker project inside cwd."""
    subprocess.run(["git", "init"], cwd=str(cwd), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(cwd),
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(cwd),
        capture_output=True,
        check=True,
    )
    result = _run_prog("init", name, "--force", cwd=cwd)
    assert result.returncode == 0, f"init failed: {result.stderr}"


def _progress_path(cwd):
    return Path(cwd) / "docs" / "progress-tracker" / "state" / "progress.json"


def _patch_progress(cwd, patches: dict):
    """Merge ``patches`` into progress.json (top-level dict update)."""
    path = _progress_path(cwd)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(patches)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _next_output(cwd):
    """Invoke ``prog next-feature`` and return combined stdout+stderr.

    The CLI alias ``next`` may not exist yet; F13's contract says the
    selection logic must be exercised through ``next-feature`` regardless.
    """
    result = _run_prog("next-feature", cwd=cwd)
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, f"next-feature non-zero exit: {output}"
    return output, result


# ---------------------------------------------------------------------------
# Per-test isolation fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def parent_workspace(tmp_path):
    """Fresh tmp dir + initialized parent-mode progress-tracker project."""
    _init_project(tmp_path)
    # Force parent mode and clear state so each test starts from a clean slate.
    _patch_progress(tmp_path, {
        "tracker_role": "parent",
        "features": [],
        "tasks": [],
        "bugs": [],
        "routing_queue": [],
        "active_routes": [],
        "linked_projects": [],
    })
    yield tmp_path


# ---------------------------------------------------------------------------
# Common fixture data
# ---------------------------------------------------------------------------


def _bug(bug_id, priority="high", status="pending_investigation",
         description=None):
    return {
        "id": bug_id,
        "description": description or f"bug {bug_id}",
        "status": status,
        "priority": priority,
    }


def _task(task_id, description="standalone task work",
          status="pending", priority="P1"):
    return {
        "id": task_id,
        "description": description,
        "status": status,
        "priority": priority,
    }


def _feature(fid, name="root feature"):
    return {
        "id": fid,
        "name": name,
        "completed": False,
        "test_steps": [],
    }


def _linked_project(code, project_root):
    return {
        "project_code": code,
        "project_root": str(project_root),
        "label": code,
    }


# ---------------------------------------------------------------------------
# 1. P0 bug ranks above a child-project feature in the queue
# ---------------------------------------------------------------------------


def test_p0_bug_above_feature_in_queue(parent_workspace, tmp_path_factory):
    """``BUG-001`` (P0) should be selected before child project ``PT``."""
    # Create a sibling child project so "PT" is a known linked project with
    # at least one pending feature.
    child_root = tmp_path_factory.mktemp("child_pt")
    _init_project(child_root, name="PT")
    # Give the child a pending feature so the dispatch path *would* succeed.
    _patch_progress(child_root, {
        "features": [_feature(1, name="child feature one")],
    })

    _patch_progress(parent_workspace, {
        "routing_queue": ["BUG-001", "PT"],
        "bugs": [_bug("BUG-001", priority="high")],
        "linked_projects": [_linked_project("PT", child_root)],
    })

    output, _ = _next_output(parent_workspace)
    assert "BUG-001" in output, (
        f"expected BUG-001 to win over PT feature, got:\n{output}"
    )
    # Sanity: child feature name must not be the primary surface item.
    assert "child feature one" not in output, (
        f"P0 bug should preempt child feature dispatch, got:\n{output}"
    )


# ---------------------------------------------------------------------------
# 2. P1 bug ranks above a standalone task
# ---------------------------------------------------------------------------


def test_p1_bug_above_standalone_task(parent_workspace):
    """``BUG-002`` (P1 / priority=medium) should win over a pending task."""
    _patch_progress(parent_workspace, {
        "routing_queue": ["BUG-002", "TASK-001"],
        "bugs": [_bug("BUG-002", priority="medium",
                      description="medium priority bug")],
        "tasks": [_task("TASK-001",
                        description="cleanup standalone task")],
    })

    output, _ = _next_output(parent_workspace)
    assert "BUG-002" in output, (
        f"expected BUG-002 to outrank TASK-001, got:\n{output}"
    )
    # The selector must recognize BUG-* entries directly, not treat them
    # as unknown linked-project codes (which would emit a [WARN] line).
    assert "not found in linked_projects" not in output, (
        f"BUG-* codes should be resolved via bugs[], not treated as "
        f"unknown project codes, got:\n{output}"
    )
    assert "cleanup standalone task" not in output, (
        f"P1 bug must preempt task surface, got:\n{output}"
    )


# ---------------------------------------------------------------------------
# 3. Standalone task ranks above feature_task
# ---------------------------------------------------------------------------


def test_standalone_task_above_feature_task(parent_workspace):
    """With no bugs, a pending task should outrank a feature."""
    _patch_progress(parent_workspace, {
        "routing_queue": [],
        "tasks": [_task("TASK-010",
                        description="standalone refactor work")],
        "features": [_feature(1, name="legacy feature work")],
    })

    output, _ = _next_output(parent_workspace)
    assert "standalone refactor work" in output, (
        f"expected standalone task to surface, got:\n{output}"
    )
    assert "legacy feature work" not in output, (
        f"task should preempt feature, got:\n{output}"
    )


# ---------------------------------------------------------------------------
# 4. Bug with status=fixed must be skipped
# ---------------------------------------------------------------------------


def test_fixed_bug_skipped(parent_workspace):
    """A BUG entry whose status is ``fixed`` must not be selected."""
    _patch_progress(parent_workspace, {
        "routing_queue": ["BUG-003"],
        "bugs": [_bug("BUG-003", priority="high", status="fixed",
                      description="already-fixed bug")],
    })

    output, _ = _next_output(parent_workspace)
    assert "BUG-003" not in output, (
        f"fixed bug must be skipped, got:\n{output}"
    )
    assert "not found in linked_projects" not in output, (
        f"selector emitted 'not found in linked_projects' warning for BUG id, "
        f"meaning it was treated as project_code instead of bug:\n{output}"
    )


# ---------------------------------------------------------------------------
# 5. Active-route conflict skips the bug
# ---------------------------------------------------------------------------


def test_active_route_conflict_skipped(parent_workspace):
    """BUG present in active_routes (active) must be skipped by selector."""
    _patch_progress(parent_workspace, {
        "routing_queue": ["BUG-004"],
        "bugs": [_bug("BUG-004", priority="high",
                      description="bug already being worked")],
        "active_routes": [{
            "project_code": "BUG-004",
            "status": "active",
        }],
    })

    output, _ = _next_output(parent_workspace)
    assert "BUG-004" not in output, (
        f"BUG-004 is in active_routes; selector must skip it, got:\n{output}"
    )
    assert "not found in linked_projects" not in output, (
        f"selector emitted 'not found in linked_projects' warning for BUG id, "
        f"meaning it was treated as project_code instead of bug:\n{output}"
    )


# ---------------------------------------------------------------------------
# 6. Mixed queue: P0 bug ranks above ROOT and child codes
# ---------------------------------------------------------------------------


def test_routing_queue_mixed_codes_and_bugs(parent_workspace, tmp_path_factory):
    """In a mixed queue, the P0 bug must surface before ROOT or PT."""
    child_root = tmp_path_factory.mktemp("child_pt_mixed")
    _init_project(child_root, name="PT")
    _patch_progress(child_root, {
        "features": [_feature(1, name="child PT feature")],
    })

    _patch_progress(parent_workspace, {
        "routing_queue": ["BUG-005", "ROOT", "PT"],
        "bugs": [_bug("BUG-005", priority="high",
                      description="high priority crash")],
        "features": [_feature(1, name="root level feature")],
        "linked_projects": [_linked_project("PT", child_root)],
    })

    output, _ = _next_output(parent_workspace)
    assert "BUG-005" in output, (
        f"P0 bug must outrank ROOT/PT items, got:\n{output}"
    )
    # The selector should not have advanced to the ROOT feature or the
    # PT child feature when a P0 bug is available.
    assert "root level feature" not in output, (
        f"ROOT feature should not surface when P0 bug is available, "
        f"got:\n{output}"
    )
    assert "child PT feature" not in output, (
        f"child PT feature should not surface when P0 bug is available, "
        f"got:\n{output}"
    )


# ---------------------------------------------------------------------------
# 7. Fallback to tasks[] when routing_queue has no actionable items
# ---------------------------------------------------------------------------


def test_fallback_to_tasks_when_queue_empty(parent_workspace):
    """Empty routing_queue must fall back to pending tasks[]."""
    _patch_progress(parent_workspace, {
        "routing_queue": [],
        "tasks": [_task("TASK-020",
                        description="fallback task description")],
        "features": [],
    })

    output, _ = _next_output(parent_workspace)
    assert "fallback task description" in output, (
        f"selector should fall back to tasks[], got:\n{output}"
    )


# ---------------------------------------------------------------------------
# 8. Fallback to features[] when both routing_queue and tasks[] are empty
# ---------------------------------------------------------------------------


def test_fallback_to_feature_when_tasks_empty(parent_workspace):
    """Empty routing_queue + empty tasks[] must surface a pending feature.

    F13 also exposes ``prog next`` as a new alias for ``next-feature`` so
    that the unified selector has a single canonical entry point. This
    test exercises the new alias to confirm both surfaces work.
    """
    _patch_progress(parent_workspace, {
        "routing_queue": [],
        "tasks": [],
        "features": [_feature(1, name="ultimate fallback feature")],
    })

    # F13 contract: ``prog next`` is the new canonical alias.
    result = _run_prog("next", cwd=parent_workspace)
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, (
        f"`prog next` alias must exist and exit 0, got "
        f"returncode={result.returncode}, output:\n{output}"
    )
    assert "ultimate fallback feature" in output, (
        f"selector should fall back to get_next_feature(), got:\n{output}"
    )
