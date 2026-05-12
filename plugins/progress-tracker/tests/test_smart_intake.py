#!/usr/bin/env python3
"""
RED-phase tests for PT-F13 unified intake (`prog smart`).

`prog smart` is a deterministic executor — it accepts an already-classified
candidate JSON and either previews (no --commit) or commits (with --commit).

Contract under test:
    prog smart --candidate-json '<json>'                      # preview, no mutation
    prog smart --candidate-json '<json>' --commit bug         # writes bugs[]
    prog smart --candidate-json '<json>' --commit feature     # writes features[]
    prog smart --candidate-json '<json>' --commit task        # writes tasks[]
    prog smart --candidate-json '<json>' --commit update      # writes updates[]

These tests intentionally fail before the `smart` subcommand is implemented.
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


def _init_project(cwd, name="SmartIntakeTest"):
    """Initialize a fresh progress-tracker project inside cwd."""
    # init expects an existing git repo for some operations
    subprocess.run(["git", "init"], cwd=str(cwd), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(cwd),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(cwd),
        capture_output=True,
    )
    result = _run_prog("init", name, "--force", cwd=cwd)
    assert result.returncode == 0, f"init failed: {result.stderr}"


def _progress_path(cwd):
    return Path(cwd) / "docs" / "progress-tracker" / "state" / "progress.json"


def _load_progress(cwd):
    return json.loads(_progress_path(cwd).read_text(encoding="utf-8"))


def _bug_profile(description="crash on startup", priority="P0",
                 confidence=0.92):
    return {
        "type": "bug",
        "confidence": confidence,
        "profile": {
            "description": description,
            "priority": priority,
            "details": "",
            "refs": [],
            "next_action": "",
        },
    }


def _feature_profile(description="add export to csv", confidence=0.9):
    return {
        "type": "feature",
        "confidence": confidence,
        "profile": {
            "description": description,
            "priority": "P1",
            "details": "",
            "refs": [],
            "next_action": "",
        },
    }


def _task_profile(description="refactor parser module", confidence=0.9,
                  extra_profile=None):
    profile = {
        "description": description,
        "priority": "P2",
        "details": "",
        "refs": [],
        "next_action": "",
    }
    if extra_profile:
        profile.update(extra_profile)
    return {
        "type": "task",
        "confidence": confidence,
        "profile": profile,
    }


def _update_profile(description="status sync at 2026-05-11",
                    confidence=0.9, extra_profile=None):
    profile = {
        "description": description,
        "priority": "P3",
        "details": "",
        "refs": [],
        "next_action": "",
    }
    if extra_profile:
        profile.update(extra_profile)
    return {
        "type": "update",
        "confidence": confidence,
        "profile": profile,
    }


# ---------------------------------------------------------------------------
# Per-test isolation fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def smart_workspace(tmp_path):
    """Fresh tmp directory + initialized progress-tracker project per test."""
    _init_project(tmp_path)
    yield tmp_path


# ---------------------------------------------------------------------------
# 1. Preview (no --commit) must not mutate progress.json
# ---------------------------------------------------------------------------


def test_smart_preview_no_mutation(smart_workspace):
    """High-confidence candidate without --commit produces no state change."""
    before = _load_progress(smart_workspace)
    bugs_before = len(before.get("bugs", []) or [])
    tasks_before = len(before.get("tasks", []) or [])

    candidate = json.dumps(_bug_profile(confidence=0.92))
    result = _run_prog("smart", "--candidate-json", candidate,
                       cwd=smart_workspace)
    assert result.returncode == 0, (
        f"smart preview failed: {result.stderr or result.stdout}"
    )

    after = _load_progress(smart_workspace)
    assert len(after.get("bugs", []) or []) == bugs_before
    assert len(after.get("tasks", []) or []) == tasks_before


# ---------------------------------------------------------------------------
# 2. Ambiguous (low-confidence) candidate must not mutate and must prompt
# ---------------------------------------------------------------------------


def test_smart_ambiguous_no_mutation(smart_workspace):
    """Low-confidence candidate emits clarifying questions and no mutation."""
    before_raw = _progress_path(smart_workspace).read_text(encoding="utf-8")

    candidate = json.dumps(
        _bug_profile(description="something weird happened",
                     priority="P1", confidence=0.45)
    )
    result = _run_prog("smart", "--candidate-json", candidate,
                       cwd=smart_workspace)

    # CLI should exit 0 and emit a structured clarifying prompt (not crash).
    assert result.returncode == 0, (
        f"smart ambiguous preview should exit 0 with clarifying prompt, "
        f"got returncode={result.returncode}, stderr={result.stderr!r}"
    )
    combined_out = (result.stdout or "") + (result.stderr or "")
    combined_lower = combined_out.lower()
    assert (
        "needs_clarification" in combined_lower
        or "clarif" in combined_lower
        or "请补充" in combined_out
        or "请确认" in combined_out
    ), f"expected clarifying prompt, got:\n{combined_out}"

    after_raw = _progress_path(smart_workspace).read_text(encoding="utf-8")
    assert after_raw == before_raw, "progress.json was modified by ambiguous preview"


# ---------------------------------------------------------------------------
# 3. Commit bug → bugs[] grows
# ---------------------------------------------------------------------------


def test_smart_commit_bug_writes_bugs(smart_workspace):
    """`smart --commit bug` appends one bug whose description matches profile."""
    before = _load_progress(smart_workspace)
    bugs_before = len(before.get("bugs", []) or [])

    candidate = json.dumps(_bug_profile(description="crash on startup",
                                        priority="P0"))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "bug",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit bug failed: {result.stderr or result.stdout}"
    )

    after = _load_progress(smart_workspace)
    bugs = after.get("bugs", []) or []
    assert len(bugs) == bugs_before + 1, (
        f"expected bugs len {bugs_before + 1}, got {len(bugs)}"
    )
    assert any(
        "crash on startup" in (b.get("description") or "") for b in bugs
    ), f"new bug description not found in {[b.get('description') for b in bugs]}"


# ---------------------------------------------------------------------------
# 4. Commit bug with profile.priority="P0" → routing_queue contains BUG-* entry
# ---------------------------------------------------------------------------


def test_smart_commit_bug_routing_queue(smart_workspace):
    """High-priority bug commit produces a BUG- entry in routing_queue."""
    candidate = json.dumps(_bug_profile(description="db connection drops",
                                        priority="P0"))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "bug",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit bug failed: {result.stderr or result.stdout}"
    )

    after = _load_progress(smart_workspace)
    queue = after.get("routing_queue", []) or []
    # routing_queue entries may be strings or objects; flatten to strings.
    flat = []
    for item in queue:
        if isinstance(item, str):
            flat.append(item)
        elif isinstance(item, dict):
            code = item.get("code") or item.get("id") or ""
            flat.append(str(code))
    assert any(s.startswith("BUG-") for s in flat), (
        f"expected a BUG-* entry in routing_queue, got: {flat}"
    )


# ---------------------------------------------------------------------------
# 5. Commit task → tasks[] grows with workflow_profile field
# ---------------------------------------------------------------------------


def test_smart_commit_task_writes_tasks(smart_workspace):
    """`smart --commit task` appends one task with a workflow_profile field."""
    before = _load_progress(smart_workspace)
    tasks_before = len(before.get("tasks", []) or [])

    candidate = json.dumps(_task_profile(description="refactor parser module"))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "task",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit task failed: {result.stderr or result.stdout}"
    )

    after = _load_progress(smart_workspace)
    tasks = after.get("tasks", []) or []
    assert len(tasks) == tasks_before + 1, (
        f"expected tasks len {tasks_before + 1}, got {len(tasks)}"
    )
    new_task = tasks[-1]
    assert "workflow_profile" in new_task, (
        f"new task missing workflow_profile field: {new_task!r}"
    )


# ---------------------------------------------------------------------------
# 6. Commit feature → features[] grows
# ---------------------------------------------------------------------------


def test_smart_commit_feature_writes_features(smart_workspace):
    """`smart --commit feature` appends one feature."""
    before = _load_progress(smart_workspace)
    features_before = len(before.get("features", []) or [])

    candidate = json.dumps(_feature_profile(description="add export to csv"))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "feature",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit feature failed: {result.stderr or result.stdout}"
    )

    after = _load_progress(smart_workspace)
    features = after.get("features", []) or []
    assert len(features) == features_before + 1, (
        f"expected features len {features_before + 1}, got {len(features)}"
    )


# ---------------------------------------------------------------------------
# 7. Commit update → updates[] grows (delegates to add_update)
# ---------------------------------------------------------------------------


def test_smart_commit_update_calls_add_update(smart_workspace):
    """`smart --commit update` appends one update entry."""
    before = _load_progress(smart_workspace)
    updates_before = len(before.get("updates", []) or [])

    candidate = json.dumps(_update_profile(description="weekly status sync"))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "update",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit update failed: {result.stderr or result.stdout}"
    )

    after = _load_progress(smart_workspace)
    updates = after.get("updates", []) or []
    assert len(updates) == updates_before + 1, (
        f"expected updates len {updates_before + 1}, got {len(updates)}"
    )


# ---------------------------------------------------------------------------
# 8. workflow_profile defaults to "standard_task" when not provided
# ---------------------------------------------------------------------------


def test_workflow_profile_default(smart_workspace):
    """Task commit without --workflow-profile uses 'standard_task'."""
    candidate = json.dumps(_task_profile(description="cleanup obsolete code"))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "task",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit task failed: {result.stderr or result.stdout}"
    )

    after = _load_progress(smart_workspace)
    tasks = after.get("tasks", []) or []
    assert tasks, "tasks[] should not be empty after commit task"
    assert tasks[-1].get("workflow_profile") == "standard_task", (
        f"expected workflow_profile='standard_task', got "
        f"{tasks[-1].get('workflow_profile')!r}"
    )


# ---------------------------------------------------------------------------
# 9. UPDATE_CATEGORIES validation:
#    - missing category   → defaults to "status"
#    - valid category     → preserved
#    - invalid category   → fallback to "status"
# ---------------------------------------------------------------------------


def test_smart_commit_update_default_category(smart_workspace):
    """No category field in profile → defaults to 'status'."""
    candidate = json.dumps(_update_profile(
        description="update without category"))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "update",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit update (no category) failed: "
        f"{result.stderr or result.stdout}"
    )
    updates = _load_progress(smart_workspace).get("updates", []) or []
    assert updates, "updates[] should grow"
    assert updates[-1].get("category") == "status", (
        f"expected category 'status', got "
        f"{updates[-1].get('category')!r}"
    )


def test_smart_commit_update_valid_explicit_category(smart_workspace):
    """Valid explicit category 'meeting' is preserved."""
    candidate = json.dumps(_update_profile(
        description="meeting notes 2026-05-11",
        extra_profile={"category": "meeting"},
    ))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "update",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit update (meeting) failed: "
        f"{result.stderr or result.stdout}"
    )
    updates = _load_progress(smart_workspace).get("updates", []) or []
    assert updates, "updates[] should grow"
    assert updates[-1].get("category") == "meeting", (
        f"expected category 'meeting', got "
        f"{updates[-1].get('category')!r}"
    )


def test_smart_commit_update_invalid_category_fallback(smart_workspace):
    """Invalid category 'progress' falls back to 'status'."""
    candidate = json.dumps(_update_profile(
        description="should fallback to status",
        extra_profile={"category": "progress"},
    ))
    result = _run_prog(
        "smart",
        "--candidate-json", candidate,
        "--commit", "update",
        cwd=smart_workspace,
    )
    assert result.returncode == 0, (
        f"smart commit update (invalid category) failed: "
        f"{result.stderr or result.stdout}"
    )
    updates = _load_progress(smart_workspace).get("updates", []) or []
    assert updates, "updates[] should grow"
    assert updates[-1].get("category") == "status", (
        f"invalid 'progress' should fallback to 'status', "
        f"got {updates[-1].get('category')!r}"
    )
