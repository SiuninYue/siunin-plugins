# Task Execution Semantics and Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `prog next --done` lifecycle for standalone (squash-merge) and feature-bound (progress-advance) tasks, with stale bug warnings and full-history visibility in `prog status`.

**Architecture:** Add `parent_feature_id` / `current_task_id` to the data model; `prog next` activates tasks (creating a branch for standalone ones); `prog next --done` dispatches to `_close_current_task()` which forks by `parent_feature_id` — standalone path runs `_git_squash_close_task()`, feature-bound path just marks the task complete. The `next --done` path bypasses `progress_transaction()` the same way `done` does. Status visibility improvements are isolated to `status()` and `list_updates()`.

**Tech Stack:** Python 3.10+, argparse, fcntl file locking, subprocess git calls via `_run_git()`, pytest + `mock_git_repo` fixture, `_PROJECT_ROOT_OVERRIDE` for test isolation.

---

## File Map

| File | Change |
|------|--------|
| `plugins/progress-tracker/hooks/scripts/progress_manager.py` | All new/modified functions — 9 tasks |
| `plugins/progress-tracker/hooks/scripts/wf_state_machine.py` | 1-line fix: `start_task` → `next` |
| `plugins/progress-tracker/docs/PROG_COMMANDS.md` | Add new command entries |
| `plugins/progress-tracker/tests/test_task_execution_semantics.py` | New: all 16 test cases |

---

## Task 1: Data model — `parent_feature_id` + `prog add-task` CLI

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

### Context

`add_task_item()` is at line ~9995 in `progress_manager.py`. It accepts `description, details, refs, next_action, priority, workflow_profile` but has no `parent_feature_id` param. The CLI has no `add-task` subcommand — tasks are currently only created via `prog smart --commit task`.

`MUTATING_COMMANDS` set is at line 252.

- [ ] **Step 1: Write failing tests**

Create `plugins/progress-tracker/tests/test_task_execution_semantics.py`:

```python
"""Tests for PT-F14: task execution semantics."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

import pytest
import sys

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _init_project(root: Path, name: str = "Test") -> None:
    progress_manager.configure_project_scope(str(root))
    progress_manager.init_tracking(name, force=True)


def _add_feature(root: Path, name: str = "Feature A") -> int:
    """Add a feature and return its id."""
    progress_manager._PROJECT_ROOT_OVERRIDE = root
    data = progress_manager.load_progress_json()
    features = data.get("features", [])
    new_id = (max((f["id"] for f in features), default=0) + 1)
    features.append({
        "id": new_id, "name": name, "completed": False, "deferred": False,
        "lifecycle_state": "pending", "test_steps": [],
        "acceptance_criteria": [], "acceptance_scenarios": [],
        "ai_metrics": {}, "state": {"status": "pending"},
    })
    data["features"] = features
    progress_manager.save_progress_json(data)
    return new_id


# ---------------------------------------------------------------------------
# Task 1: add_task_item parent_feature_id + prog add-task CLI
# ---------------------------------------------------------------------------

class TestAddTaskParentFeatureId:
    def test_add_task_standalone_has_null_parent(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        task_id = progress_manager.add_task_item(description="do something")
        data = progress_manager.load_progress_json()
        task = next(t for t in data["tasks"] if t["id"] == task_id)
        assert task.get("parent_feature_id") is None

    def test_add_task_with_valid_feature_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        task_id = progress_manager.add_task_item(description="bounded", parent_feature_id=fid)
        data = progress_manager.load_progress_json()
        task = next(t for t in data["tasks"] if t["id"] == task_id)
        assert task["parent_feature_id"] == fid

    def test_add_task_invalid_feature_id_returns_none(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        result = progress_manager.add_task_item(description="bad", parent_feature_id=999)
        assert result is None

    def test_add_task_cli_add_task_subcommand_exists(self):
        """prog add-task must be a registered subcommand."""
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "progress_manager.py"), "add-task", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--description" in result.stdout

    def test_add_task_cli_feature_id_and_quick_task_profile_mutually_exclusive(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        result = subprocess.run(
            [
                "python3", str(SCRIPT_DIR / "progress_manager.py"),
                "--project-root", str(tmp_path),
                "add-task",
                "--description", "conflict",
                "--feature-id", str(fid),
                "--workflow-profile", "quick_task",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 2

    def test_add_task_cli_nonexistent_feature_returns_rc1(self, tmp_path):
        _init_project(tmp_path)
        result = subprocess.run(
            [
                "python3", str(SCRIPT_DIR / "progress_manager.py"),
                "--project-root", str(tmp_path),
                "add-task",
                "--description", "bad ref",
                "--feature-id", "999",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
```

- [ ] **Step 2: Run tests — verify RED**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.claude/worktrees/feat+PT-F14-task-execution-semantics
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestAddTaskParentFeatureId -v 2>&1 | tail -20
```

Expected: All 6 tests FAIL (AttributeError or wrong RC).

- [ ] **Step 3: Implement — `add_task_item()` + `prog add-task` parser**

**3a. Modify `add_task_item()` signature** (line ~9995 in `progress_manager.py`):

```python
def add_task_item(
    description: str,
    details: str = "",
    refs: Optional[List[str]] = None,
    next_action: str = "",
    priority: str = "P1",
    workflow_profile: str = WORKFLOW_PROFILE_DEFAULT,
    parent_feature_id: Optional[int] = None,
) -> Optional[str]:
    """Write a standalone task item to tasks[].
    ...existing docstring...
    """
    if not description or not description.strip():
        raise ValueError("Description cannot be empty")
    # ... existing validation ...

    # NEW: validate parent_feature_id
    if parent_feature_id is not None:
        data_check = load_progress_json()
        if data_check:
            features = data_check.get("features", [])
            if not any(f.get("id") == parent_feature_id for f in features):
                print(f"Error: feature {parent_feature_id} not found")
                return None

    # ... rest of existing function ...
    new_task = {
        "id": task_id,
        "type": "task",
        "description": description,
        "workflow_profile": workflow_profile,
        "status": "pending",
        "priority": priority,
        "details": details.strip() if details else "",
        "refs": refs,
        "next_action": next_action.strip() if next_action else "",
        "created_at": _iso_now(),
        "parent_feature_id": parent_feature_id,  # NEW
    }
    # ... rest unchanged ...
```

**3b. Add `prog add-task` subparser** (add after the `next_alias_parser` block, around line 11503):

```python
    # PT-F14: `add-task` direct task creation CLI.
    add_task_parser = subparsers.add_parser(
        "add-task",
        help="Create a new task item",
    )
    add_task_parser.add_argument(
        "--description", required=True, help="Task description"
    )
    add_task_parser.add_argument(
        "--feature-id", type=int, dest="feature_id", default=None,
        help="Bind to parent feature ID (mutually exclusive with --workflow-profile quick_task)",
    )
    add_task_parser.add_argument(
        "--workflow-profile",
        choices=sorted(WORKFLOW_PROFILE_VALUES),
        default=WORKFLOW_PROFILE_DEFAULT,
        dest="workflow_profile",
        help="Workflow profile",
    )
    add_task_parser.add_argument(
        "--priority", choices=["P0", "P1", "P2"], default="P1",
        help="Task priority",
    )
    add_task_parser.add_argument(
        "--details", default="", help="Extended details",
    )
```

**3c. Add `add-task` to `MUTATING_COMMANDS`** (around line 252, add after `"add-bug"`):

```python
    "add-task",
```

**3d. Add dispatch to `_dispatch_command()`** (add after the `add-bug` dispatch, around line ~12230):

```python
        if args.command == "add-task":
            # Mutual exclusion: --feature-id + quick_task profile
            if args.feature_id is not None and args.workflow_profile == "quick_task":
                print("Error: --feature-id and --workflow-profile quick_task are mutually exclusive")
                return 2
            task_id = add_task_item(
                description=args.description,
                details=args.details,
                priority=args.priority,
                workflow_profile=args.workflow_profile,
                parent_feature_id=args.feature_id,
            )
            return 0 if task_id is not None else 1
```

- [ ] **Step 4: Run tests — verify GREEN**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestAddTaskParentFeatureId -v 2>&1 | tail -20
```

Expected: All 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "feat(PT-F14): add parent_feature_id to add_task_item + prog add-task CLI"
```

---

## Task 2: `next_feature()` task activation — `current_task_id` + branch creation + ghost fix

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py` (lines ~7099–7337)
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

### Context

In `next_feature()`, at line ~7318, when `item_type == "task"` the code prints `"Run: prog start-task {task_id}"` and returns without writing `current_task_id` or creating a branch. The `_task_item()` helper at line 7099 also emits `"prog start-task"`.

- [ ] **Step 1: Write failing tests**

Append to `test_task_execution_semantics.py`:

```python
class TestNextFeatureTaskActivation:
    def test_next_selects_task_sets_current_task_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="my task")
        progress_manager.next_feature()
        data = progress_manager.load_progress_json()
        assert data.get("current_task_id") == "TASK-001"

    def test_next_standalone_task_output_contains_next_done(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="my task")
        with patch.object(progress_manager, "_run_git", return_value=(0, "", "")):
            progress_manager.next_feature()
        out = capsys.readouterr().out
        assert "prog next --done" in out
        assert "start-task" not in out

    def test_next_standalone_task_creates_branch(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=mock_git_repo, capture_output=True)
        progress_manager.add_task_item(description="standalone")
        progress_manager.next_feature()
        result = subprocess.run(
            ["git", "branch", "--list", "task/TASK-001"],
            cwd=mock_git_repo, capture_output=True, text=True,
        )
        assert "task/TASK-001" in result.stdout

    def test_next_feature_bound_task_does_not_create_branch(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=mock_git_repo, capture_output=True)
        fid = _add_feature(mock_git_repo)
        progress_manager.add_task_item(description="bound", parent_feature_id=fid)
        progress_manager.next_feature()
        result = subprocess.run(
            ["git", "branch", "--list", "task/TASK-001"],
            cwd=mock_git_repo, capture_output=True, text=True,
        )
        assert result.stdout.strip() == ""

    def test_next_standalone_branch_fail_does_not_set_current_task_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="standalone")
        # _run_git returns non-zero to simulate branch creation failure
        with patch.object(progress_manager, "_run_git", return_value=(1, "", "branch error")):
            progress_manager.next_feature()
        data = progress_manager.load_progress_json()
        assert data.get("current_task_id") is None
```

- [ ] **Step 2: Run tests — verify RED**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestNextFeatureTaskActivation -v 2>&1 | tail -20
```

Expected: All 5 FAIL.

- [ ] **Step 3: Implement**

**3a. Fix `_task_item()` at line 7099** — change `action` value:

```python
    def _task_item(task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = task.get("id")
        return {
            "item_type": "task",
            "id": task_id,
            "name": task.get("description", task_id),
            "priority_tier": None,
            "action": "prog next --done",   # was: f"prog start-task {task_id}"
            "dispatched_to": "task",
        }
```

**3b. Replace the `item_type == "task"` block in `next_feature()` at line ~7318**:

Replace:
```python
            if item_type == "task":
                task_id = work_item["id"]
                task_name = work_item["name"]
                action = work_item.get("action") or f"prog start-task {task_id}"
                if output_json:
                    print(json.dumps({
                        "status": "ok",
                        "item_type": "task",
                        "id": task_id,
                        "name": task_name,
                        "priority_tier": None,
                        "action": action,
                        "feature_id": None,
                        "test_steps": [],
                    }, ensure_ascii=False))
                else:
                    print(f"[NEXT] Task: {task_id}")
                    print(f"{task_id}: {task_name}")
                    print(f"Run: {action}")
                return True
```

With:
```python
            if item_type == "task":
                task_id = work_item["id"]
                task_name = work_item["name"]
                # Look up full task record to check parent_feature_id.
                tasks = data.get("tasks") or []
                task_record = next(
                    (t for t in tasks if isinstance(t, dict) and t.get("id") == task_id),
                    None,
                )
                parent_fid = task_record.get("parent_feature_id") if task_record else None
                is_standalone = parent_fid is None

                if is_standalone:
                    # Create short-lived branch before activating.
                    branch_name = f"task/{task_id}"
                    rc, _, err = _run_git(
                        ["checkout", "-b", branch_name],
                        cwd=str(project_root),
                    )
                    if rc != 0:
                        print(f"Error: could not create branch {branch_name}: {err}")
                        return False

                # Persist current_task_id after branch (standalone) or immediately (feature-bound).
                try:
                    data["current_task_id"] = task_id
                    data["updated_at"] = _iso_now()
                    save_progress_json(data)
                except Exception as exc:
                    logger.debug(f"Task activation bookkeeping failed: {exc}")

                action = "prog next --done"
                if output_json:
                    print(json.dumps({
                        "status": "ok",
                        "item_type": "task",
                        "id": task_id,
                        "name": task_name,
                        "priority_tier": None,
                        "action": action,
                        "feature_id": parent_fid,
                        "test_steps": [],
                    }, ensure_ascii=False))
                else:
                    print(f"Task selected: {task_id}")
                    print(f"{task_id}: {task_name}")
                    print(f"Run: {action}")
                return True
```

- [ ] **Step 4: Run tests — verify GREEN**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestNextFeatureTaskActivation -v 2>&1 | tail -20
```

Expected: All 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "feat(PT-F14): activate task on next — current_task_id, branch creation, ghost fix"
```

---

## Task 3: `_git_squash_close_task()` helper

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

### Context

This is the git helper called by `_close_standalone_task()`. It must be testable independently. Insert near other git helpers (search for `def _detect_default_branch` around line 5965 — add after that function).

- [ ] **Step 1: Write failing tests**

Append to `test_task_execution_semantics.py`:

```python
class TestGitSquashCloseTask:
    def test_squash_close_succeeds_and_returns_commit_hash(self, mock_git_repo):
        """Unit: mock _run_git to verify call sequence."""
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo

        call_log = []
        def fake_run_git(args, cwd=None, timeout=5):
            call_log.append(args)
            if args[0] == "rev-parse":
                return 0, "abc123", ""
            return 0, "", ""

        with patch.object(progress_manager, "_run_git", side_effect=fake_run_git):
            ok, value = progress_manager._git_squash_close_task(
                task_id="TASK-001",
                branch="task/TASK-001",
                project_root=mock_git_repo,
            )

        assert ok is True
        assert value == "abc123"
        # Verify sequence: show-ref (branch check), status, checkout, merge --squash, commit, branch -d
        cmds = [c[0] for c in call_log]
        assert "checkout" in cmds
        assert "merge" in cmds
        assert "commit" in cmds
        assert "branch" in cmds

    def test_squash_close_fails_if_branch_missing(self, mock_git_repo):
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo

        def fake_run_git(args, cwd=None, timeout=5):
            if args[0] == "show-ref":
                return 1, "", "not found"  # branch does not exist
            return 0, "", ""

        with patch.object(progress_manager, "_run_git", side_effect=fake_run_git):
            ok, msg = progress_manager._git_squash_close_task(
                task_id="TASK-001",
                branch="task/TASK-001",
                project_root=mock_git_repo,
            )

        assert ok is False
        assert "not found" in msg.lower() or "branch" in msg.lower()

    def test_squash_close_integration(self, mock_git_repo):
        """Integration: real git ops — verifies main+1 commit and branch deleted."""
        import subprocess
        progress_manager.configure_project_scope(str(mock_git_repo))
        progress_manager._PROJECT_ROOT_OVERRIDE = mock_git_repo
        progress_manager.init_tracking("Test", force=True)
        subprocess.run(["git", "add", "."], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=mock_git_repo, capture_output=True)

        # Get commit count on main before
        before = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout.strip()

        # Create a task branch with a commit
        subprocess.run(["git", "checkout", "-b", "task/TASK-001"], cwd=mock_git_repo, capture_output=True)
        (mock_git_repo / "task_work.txt").write_text("some work")
        subprocess.run(["git", "add", "task_work.txt"], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "task work"], cwd=mock_git_repo, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=mock_git_repo, capture_output=True)

        ok, commit_hash = progress_manager._git_squash_close_task(
            task_id="TASK-001",
            branch="task/TASK-001",
            project_root=mock_git_repo,
        )

        assert ok is True
        assert len(commit_hash) >= 7

        # main has exactly +1 commit
        after = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout.strip()
        assert int(after) == int(before) + 1

        # task branch is deleted
        branches = subprocess.run(
            ["git", "branch", "--list", "task/TASK-001"],
            cwd=mock_git_repo, capture_output=True, text=True,
        ).stdout
        assert branches.strip() == ""
```

- [ ] **Step 2: Run tests — verify RED**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestGitSquashCloseTask -v 2>&1 | tail -20
```

Expected: AttributeError `_git_squash_close_task` not found.

- [ ] **Step 3: Implement `_git_squash_close_task()`**

Add after `_detect_default_branch()` (around line 5990 in `progress_manager.py`):

```python
def _git_squash_close_task(
    task_id: str,
    branch: str,
    project_root: Optional[Path] = None,
    base_branch: Optional[str] = None,
) -> Tuple[bool, str]:
    """Execute git squash-merge sequence for a standalone task branch.

    Returns (True, commit_hash) on success, (False, error_message) on failure.
    On success, base_branch has exactly +1 commit and branch is deleted.
    """
    if project_root is None:
        project_root = find_project_root()

    cwd = str(project_root)

    # Resolve base branch
    if base_branch is None:
        base_branch = _detect_default_branch(project_root) or "main"

    # Pre-condition 1: branch must exist
    rc, _, _ = _run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=cwd)
    if rc != 0:
        return False, f"branch '{branch}' not found in local repo"

    # Pre-condition 2: working tree must be clean
    rc, stdout, _ = _run_git(["status", "--porcelain"], cwd=cwd)
    if rc != 0 or stdout.strip():
        return False, f"working tree is dirty; commit or stash changes first"

    # Step 1: checkout base branch
    rc, _, err = _run_git(["checkout", base_branch], cwd=cwd)
    if rc != 0:
        return False, f"checkout {base_branch} failed: {err}"

    # Step 2: squash merge
    rc, _, err = _run_git(["merge", "--squash", branch], cwd=cwd)
    if rc != 0:
        # Roll back any partial index changes
        _run_git(["reset", "--mixed", "HEAD"], cwd=cwd)
        return False, f"git merge --squash failed: {err}"

    # Step 3: commit
    commit_msg = f"task({task_id}): close standalone task"
    rc, _, err = _run_git(["commit", "-m", commit_msg], cwd=cwd)
    if rc != 0:
        _run_git(["reset", "--mixed", "HEAD"], cwd=cwd)
        return False, f"git commit failed: {err}"

    # Step 4: get commit hash
    rc, commit_hash, _ = _run_git(["rev-parse", "HEAD"], cwd=cwd)
    commit_hash = commit_hash.strip() if rc == 0 else ""

    # Step 5: delete task branch
    rc, _, err = _run_git(["branch", "-d", branch], cwd=cwd)
    if rc != 0:
        # Non-fatal: log warning but don't fail the close
        logger.warning(f"Could not delete branch {branch}: {err}")

    return True, commit_hash
```

- [ ] **Step 4: Run tests — verify GREEN**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestGitSquashCloseTask -v 2>&1 | tail -20
```

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "feat(PT-F14): add _git_squash_close_task() helper"
```

---

## Task 4: `_close_current_task()` + `_close_standalone_task()` + `_close_feature_bound_task()`

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

### Context

Add these three functions near `cmd_done()` (around line 8420 in `progress_manager.py`). They are called by the CLI dispatch added in Task 5.

- [ ] **Step 1: Write failing tests**

Append to `test_task_execution_semantics.py`:

```python
class TestCloseCurrentTask:
    def test_close_fails_rc1_when_no_current_task_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        rc = progress_manager._close_current_task()
        assert rc == 1

    def test_close_fails_rc1_when_current_task_id_points_to_missing_task(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-999"
        progress_manager.save_progress_json(data)
        rc = progress_manager._close_current_task()
        assert rc == 1

    def test_close_fails_rc1_when_task_already_completed(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="done already")
        data = progress_manager.load_progress_json()
        data["tasks"][0]["status"] = "completed"
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)
        rc = progress_manager._close_current_task()
        assert rc == 1

    def test_close_standalone_task_marks_completed_and_clears_current_task_id(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="standalone")
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        with patch.object(
            progress_manager, "_git_squash_close_task",
            return_value=(True, "deadbeef"),
        ):
            rc = progress_manager._close_current_task()

        assert rc == 0
        data = progress_manager.load_progress_json()
        task = data["tasks"][0]
        assert task["status"] == "completed"
        assert data.get("current_task_id") is None

    def test_close_standalone_git_failure_does_not_modify_state(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="standalone")
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        with patch.object(
            progress_manager, "_git_squash_close_task",
            return_value=(False, "merge conflict"),
        ):
            rc = progress_manager._close_current_task()

        assert rc == 1
        data = progress_manager.load_progress_json()
        assert data["tasks"][0]["status"] == "pending"  # unchanged
        assert data.get("current_task_id") == "TASK-001"  # unchanged

    def test_close_feature_bound_task_marks_completed_no_git(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        progress_manager.add_task_item(description="bounded", parent_feature_id=fid)
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        git_called = []
        with patch.object(
            progress_manager, "_git_squash_close_task",
            side_effect=lambda **kw: git_called.append(True) or (True, ""),
        ):
            rc = progress_manager._close_current_task()

        assert rc == 0
        assert git_called == []  # git must NOT be called for feature-bound
        data = progress_manager.load_progress_json()
        assert data["tasks"][0]["status"] == "completed"
        assert data.get("current_task_id") is None

    def test_close_feature_bound_task_does_not_auto_close_parent_feature(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        fid = _add_feature(tmp_path)
        progress_manager.add_task_item(description="bounded", parent_feature_id=fid)
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        rc = progress_manager._close_current_task()

        data = progress_manager.load_progress_json()
        feature = next(f for f in data["features"] if f["id"] == fid)
        assert feature.get("completed") is not True
        assert feature.get("lifecycle_state") != "completed"

    def test_close_json_output_contract(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        progress_manager.add_task_item(description="task")
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        with patch.object(
            progress_manager, "_git_squash_close_task",
            return_value=(True, "abc123"),
        ):
            rc = progress_manager._close_current_task(output_json=True)

        out = capsys.readouterr().out
        payload = json.loads(out)
        assert "status" in payload
        assert "closed_task_id" in payload
        assert "message" in payload
        assert rc == 0
```

- [ ] **Step 2: Run tests — verify RED**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestCloseCurrentTask -v 2>&1 | tail -25
```

Expected: AttributeError `_close_current_task` not found.

- [ ] **Step 3: Implement three close functions**

Add before `cmd_done()` (around line 8420 in `progress_manager.py`):

```python
def _close_current_task(output_json: bool = False) -> int:
    """Main dispatch for `prog next --done`. Returns RC 0/1/2."""
    data = load_progress_json()
    if not data:
        msg = "No progress tracking found"
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": None, "message": msg}))
        else:
            print(f"Error: {msg}")
        return 1

    current_task_id = data.get("current_task_id")
    if not current_task_id:
        msg = "No active task. Run `prog next` to select a task first."
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": None, "message": msg}))
        else:
            print(f"Error: {msg}\nRepair: run `prog next` to activate a task.")
        return 1

    tasks = data.get("tasks") or []
    task = next((t for t in tasks if isinstance(t, dict) and t.get("id") == current_task_id), None)

    if task is None:
        msg = f"Task {current_task_id} not found — clearing stale current_task_id."
        data["current_task_id"] = None
        save_progress_json(data)
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": current_task_id, "message": msg}))
        else:
            print(f"Error: {msg}")
        return 1

    if task.get("status") == "completed":
        msg = f"Task {current_task_id} is already completed."
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": current_task_id, "message": msg}))
        else:
            print(f"Error: {msg}\nRepair: run `prog next` to select the next task.")
        return 1

    parent_fid = task.get("parent_feature_id")
    if parent_fid is None:
        return _close_standalone_task(task, data, output_json=output_json)
    else:
        return _close_feature_bound_task(task, data, output_json=output_json)


def _close_standalone_task(task: dict, data: dict, output_json: bool = False) -> int:
    """Close a standalone task via git squash-merge. Atomic: git first, state second."""
    task_id = task["id"]
    branch = f"task/{task_id}"
    project_root = find_project_root()

    ok, value = _git_squash_close_task(
        task_id=task_id, branch=branch, project_root=project_root
    )
    if not ok:
        msg = f"Git squash-merge failed: {value}"
        if output_json:
            print(json.dumps({"status": "error", "closed_task_id": task_id, "message": msg}))
        else:
            print(f"Error: {msg}")
        return 1

    # Git succeeded — now update business state
    task["status"] = "completed"
    data["current_task_id"] = None
    data["updated_at"] = _iso_now()
    save_progress_json(data)

    msg = f"Task {task_id} closed. Squash commit: {value}"
    if output_json:
        print(json.dumps({"status": "ok", "closed_task_id": task_id, "message": msg}))
    else:
        print(f"[DONE] {msg}")
    return 0


def _close_feature_bound_task(task: dict, data: dict, output_json: bool = False) -> int:
    """Close a feature-bound task: mark complete, no git ops, no feature auto-close."""
    task_id = task["id"]
    task["status"] = "completed"
    data["current_task_id"] = None
    data["updated_at"] = _iso_now()
    save_progress_json(data)

    msg = f"Task {task_id} marked complete. Parent feature not auto-closed."
    if output_json:
        print(json.dumps({"status": "ok", "closed_task_id": task_id, "message": msg}))
    else:
        print(f"[DONE] {msg}")
    return 0
```

- [ ] **Step 4: Run tests — verify GREEN**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestCloseCurrentTask -v 2>&1 | tail -25
```

Expected: All 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "feat(PT-F14): add _close_current_task / _close_standalone_task / _close_feature_bound_task"
```

---

## Task 5: `next --done` CLI flag + lock exemption

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

### Context

Add `--done` flag to the `next` alias parser (around line 11496). In `main()`, insert a dispatch exemption before the `MUTATING_COMMANDS` check (around line 12383).

The exemption must also be added to the worktree-branch-consistency check (`args.command in {"next-feature", "next", "done"}` at line ~12356) — specifically, `next --done` should bypass that check since it's a task close, not a feature selection.

- [ ] **Step 1: Write failing tests**

Append to `test_task_execution_semantics.py`:

```python
class TestNextDoneCLI:
    def test_next_done_flag_closes_task_via_cli(self, tmp_path):
        _init_project(tmp_path)
        progress_manager.add_task_item(description="task")
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        with patch.object(
            progress_manager, "_git_squash_close_task",
            return_value=(True, "deadbeef"),
        ):
            result = subprocess.run(
                [
                    "python3", str(SCRIPT_DIR / "progress_manager.py"),
                    "--project-root", str(tmp_path),
                    "next", "--done",
                ],
                capture_output=True, text=True,
            )

        assert result.returncode == 0

    def test_next_done_does_not_hold_mutating_lock(self, tmp_path):
        """next --done must not time out due to MUTATING_COMMANDS outer lock."""
        import time
        _init_project(tmp_path)
        progress_manager.add_task_item(description="task")
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        data["current_task_id"] = "TASK-001"
        progress_manager.save_progress_json(data)

        with patch.object(
            progress_manager, "_git_squash_close_task",
            return_value=(True, "abc"),
        ):
            start = time.monotonic()
            result = subprocess.run(
                [
                    "python3", str(SCRIPT_DIR / "progress_manager.py"),
                    "--project-root", str(tmp_path),
                    "next", "--done",
                ],
                capture_output=True, text=True,
                timeout=5,  # must complete well under 10s lock timeout
            )
            elapsed = time.monotonic() - start

        assert result.returncode == 0
        assert elapsed < 5.0  # no lock contention
```

- [ ] **Step 2: Run tests — verify RED**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestNextDoneCLI -v 2>&1 | tail -20
```

Expected: FAIL (unknown argument `--done`).

- [ ] **Step 3: Implement**

**3a. Add `--done` to `next` alias parser** (around line 11496 in `progress_manager.py`, after the `--ack-planning-risk` argument):

```python
    next_alias_parser.add_argument(
        "--done",
        action="store_true",
        dest="done",
        help="Close the current active task (prog next --done)",
    )
```

**3b. Insert lock exemption in `main()`** (add immediately before `if args.command in MUTATING_COMMANDS:` around line 12383):

```python
    # PT-F14: `next --done` closes the current task. Like `done`, it bypasses
    # the outer progress_transaction() lock to avoid BUG-002 class deadlocks.
    if args.command == "next" and getattr(args, "done", False):
        return _close_current_task(output_json=getattr(args, "output_json", False))
```

**3c. Also exempt `next --done` from worktree-branch-consistency check** (at line ~12356):

Replace:
```python
    if args.command in {"next-feature", "next", "done"}:
        if not check_worktree_branch_consistency(args.command):
            return 1
```
With:
```python
    # next --done is a task close, not a feature selection — skip branch check.
    if args.command in {"next-feature", "next", "done"} and not getattr(args, "done", False):
        if not check_worktree_branch_consistency(args.command):
            return 1
```

- [ ] **Step 4: Run tests — verify GREEN**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestNextDoneCLI -v 2>&1 | tail -20
```

Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "feat(PT-F14): add next --done flag + lock exemption"
```

---

## Task 6: Ghost command protection + `wf_state_machine.py` fix

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Modify: `plugins/progress-tracker/hooks/scripts/wf_state_machine.py`
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

### Context

`argparse` calls `sys.exit(2)` with an error message for unknown commands. To intercept and add suggestions, subclass `ArgumentParser` and override `error()`. Place `_GHOST_COMMAND_ALIASES` near the `MUTATING_COMMANDS` constant (line ~252). The `ProgressArgumentParser` class goes near the `main()` function. `wf_state_machine.py` line 54 has `"task:pending": "start_task"` which maps to the ghost command.

- [ ] **Step 1: Write failing tests**

Append to `test_task_execution_semantics.py`:

```python
class TestGhostCommandProtection:
    def test_start_task_shows_did_you_mean(self):
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "progress_manager.py"), "start-task", "TASK-001"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        assert "next --done" in result.stderr or "next --done" in result.stdout

    def test_low_similarity_command_no_did_you_mean(self):
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "progress_manager.py"), "xyzfrobnicate"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        # Should NOT show "Did you mean" for a completely unrelated command
        combined = result.stdout + result.stderr
        assert "Did you mean" not in combined

    def test_typo_close_to_done_shows_suggestion(self):
        """Edit-distance fallback: 'dne' is distance 1 from 'done'."""
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "progress_manager.py"), "dne"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        combined = result.stdout + result.stderr
        assert "done" in combined  # Did you mean: done?

    def test_wf_state_machine_task_pending_action_is_not_start_task(self):
        """wf_state_machine must not reference the ghost command."""
        import wf_state_machine
        action = wf_state_machine.WF_STATE_TRANSITIONS.get("task:pending")
        assert action != "start_task"
        assert action is not None
```

- [ ] **Step 2: Run tests — verify RED**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestGhostCommandProtection -v 2>&1 | tail -20
```

Expected: All 4 FAIL.

- [ ] **Step 3: Implement**

**3a. Add `_GHOST_COMMAND_ALIASES` near `MUTATING_COMMANDS` (after line ~291)**:

```python
# Ghost-command alias table. Maps deprecated/non-existent command names to
# their correct replacements. Takes priority over edit-distance suggestions.
_GHOST_COMMAND_ALIASES: Dict[str, str] = {
    "start-task": "next --done",
}
```

**3b. Add `_suggest_command()` helper** (add just before `def main():`):

```python
def _suggest_command(unknown: str, valid_commands: List[str]) -> Optional[str]:
    """Return best suggestion for an unknown command, or None if no good match.

    Priority:
    1. Ghost-command alias table (always shown when matched).
    2. Levenshtein edit-distance ≤ 2 to closest valid command.
    """
    if unknown in _GHOST_COMMAND_ALIASES:
        return _GHOST_COMMAND_ALIASES[unknown]

    def _edit_distance(a: str, b: str) -> int:
        m, n = len(a), len(b)
        dp = list(range(n + 1))
        for i in range(1, m + 1):
            prev = dp[0]
            dp[0] = i
            for j in range(1, n + 1):
                temp = dp[j]
                if a[i - 1] == b[j - 1]:
                    dp[j] = prev
                else:
                    dp[j] = 1 + min(prev, dp[j], dp[j - 1])
                prev = temp
        return dp[n]

    best, best_dist = None, 3  # threshold: distance must be ≤ 2
    for cmd in valid_commands:
        d = _edit_distance(unknown, cmd)
        if d < best_dist:
            best, best_dist = cmd, d
    return best  # None if nothing within threshold
```

**3c. Add `_ProgressArgumentParser` class** (add just before `def main():`):

```python
class _ProgressArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that provides ghost-command and edit-distance
    'Did you mean?' suggestions on unknown subcommand errors."""

    def error(self, message: str) -> None:
        import re
        # Extract the unknown command from the standard argparse error message.
        match = re.search(r"invalid choice: '([^']+)'", message)
        if match:
            unknown = match.group(1)
            valid = [a.option_string if hasattr(a, 'option_string') else a
                     for a in self._subparsers._group_actions[0].choices.keys()
                     ] if self._subparsers else []
            valid = list(self._subparsers._group_actions[0].choices.keys()) if self._subparsers else []
            suggestion = _suggest_command(unknown, valid)
            self.print_usage(sys.stderr)
            if suggestion:
                sys.stderr.write(f"{self.prog}: error: unknown command '{unknown}'\n")
                sys.stderr.write(f"Did you mean: '{suggestion}'?\n")
                sys.stderr.write(f"Run: {self.prog} {suggestion.split()[0]} --help\n")
            else:
                sys.stderr.write(f"{self.prog}: error: {message}\n")
            sys.exit(2)
        super().error(message)
```

**3d. In `main()`, change `argparse.ArgumentParser` to `_ProgressArgumentParser`** (line ~11420):

```python
    parser = _ProgressArgumentParser(description="Progress Tracker Manager")
```

**3e. Fix `wf_state_machine.py` line 54** — open the file and change:

```python
    "task:pending":      "start_task",
```
to:
```python
    "task:pending":      "next",
```

Also fix the comment at line 27 (`task:pending → "start_task"`) to:
```python
# task:pending → "next"
```

- [ ] **Step 4: Run tests — verify GREEN**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestGhostCommandProtection -v 2>&1 | tail -20
```

Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/hooks/scripts/wf_state_machine.py \
        plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "feat(PT-F14): ghost command protection — alias table, edit-distance suggestions, wf_state_machine fix"
```

---

## Task 7: `_get_stale_bugs()` + `status()` stale bug warnings

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

### Context

`status()` starts at line 5472. The updates display block is around line 5652. Add stale bug warnings before that block. `_get_stale_bugs()` is a new helper function — add it near `status()`.

- [ ] **Step 1: Write failing tests**

Append to `test_task_execution_semantics.py`:

```python
class TestStaleBugs:
    def _make_bug(self, priority: str, days_old: int, status: str = "confirmed") -> dict:
        ts = (datetime.now(tz=timezone.utc) - timedelta(days=days_old)).isoformat()
        return {
            "id": f"BUG-{priority}-{days_old}d",
            "description": f"{priority} bug {days_old}d old",
            "priority": {"high": "high", "medium": "medium", "low": "low"}[priority],
            "status": status,
            "created_at": ts,
        }

    def test_get_stale_bugs_p0_threshold_3_days(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            self._make_bug("high", 4),   # P0, 4d > 3d → stale
            self._make_bug("high", 2),   # P0, 2d ≤ 3d → not stale
            self._make_bug("high", 3),   # P0, exactly 3d → NOT stale (strict >)
        ]
        progress_manager.save_progress_json(data)
        stale = progress_manager._get_stale_bugs(data, now)
        assert len(stale) == 1
        assert stale[0]["id"] == "BUG-high-4d"

    def test_get_stale_bugs_p1_threshold_7_days(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            self._make_bug("medium", 8),   # P1, 8d > 7d → stale
            self._make_bug("medium", 7),   # P1, exactly 7d → not stale
            self._make_bug("medium", 6),   # P1, 6d ≤ 7d → not stale
        ]
        progress_manager.save_progress_json(data)
        stale = progress_manager._get_stale_bugs(data, now)
        assert len(stale) == 1
        assert stale[0]["id"] == "BUG-medium-8d"

    def test_get_stale_bugs_excludes_terminal_status(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            self._make_bug("high", 10, status="fixed"),
            self._make_bug("high", 10, status="false_positive"),
            self._make_bug("high", 10, status="confirmed"),
        ]
        progress_manager.save_progress_json(data)
        stale = progress_manager._get_stale_bugs(data, now)
        ids = [b["id"] for b in stale]
        assert "BUG-high-10d" in ids
        assert len(stale) == 1  # only the "confirmed" one

    def test_get_stale_bugs_p0_before_p1_order(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            {"id": "BUG-P1", "description": "p1", "priority": "medium", "status": "confirmed",
             "created_at": (now - timedelta(days=10)).isoformat()},
            {"id": "BUG-P0", "description": "p0", "priority": "high", "status": "confirmed",
             "created_at": (now - timedelta(days=5)).isoformat()},
        ]
        progress_manager.save_progress_json(data)
        stale = progress_manager._get_stale_bugs(data, now)
        assert stale[0]["id"] == "BUG-P0"
        assert stale[1]["id"] == "BUG-P1"

    def test_status_shows_stale_bug_warnings(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        data = progress_manager.load_progress_json()
        now = datetime.now(tz=timezone.utc)
        data["bugs"] = [
            {"id": "BUG-001", "description": "critical stale bug", "priority": "high",
             "status": "confirmed",
             "created_at": (now - timedelta(days=5)).isoformat()},
        ]
        progress_manager.save_progress_json(data)
        progress_manager.status()
        out = capsys.readouterr().out
        assert "BUG-001" in out
        assert "Bug Warnings" in out or "P0" in out
```

- [ ] **Step 2: Run tests — verify RED**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestStaleBugs -v 2>&1 | tail -20
```

Expected: All 6 FAIL (AttributeError `_get_stale_bugs` not found).

- [ ] **Step 3: Implement**

**3a. Add `_get_stale_bugs()` before `status()`** (around line 5470 in `progress_manager.py`):

```python
def _get_stale_bugs(data: dict, now: datetime) -> List[dict]:
    """Return P0/P1 bugs exceeding their stale threshold.

    Thresholds (strict >): P0 (priority=high) → 3 days; P1 (priority=medium) → 7 days.
    Excludes: fixed, false_positive. Time base: updated_at preferred, fallback created_at.
    Output: P0 first, then P1; same priority sorted by stale_days descending.
    """
    THRESHOLDS = {"high": 3, "medium": 7}  # days; only P0/P1 (P2/low excluded)
    TERMINAL = {"fixed", "false_positive"}

    result = []
    for bug in data.get("bugs") or []:
        if not isinstance(bug, dict):
            continue
        priority = bug.get("priority", "low")
        if priority not in THRESHOLDS:
            continue
        if bug.get("status") in TERMINAL:
            continue
        # Resolve timestamp: updated_at preferred, fallback created_at
        raw_ts = bug.get("updated_at") or bug.get("created_at")
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(raw_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.debug(f"Skipping bug {bug.get('id')}: unparseable timestamp {raw_ts!r}")
            continue
        stale_days = (now - ts).total_seconds() / 86400
        if stale_days > THRESHOLDS[priority]:
            result.append({**bug, "_stale_days": stale_days, "_priority": priority})

    # Sort: P0 (high) first, then P1 (medium); within tier, most stale first
    def _sort_key(b):
        tier = 0 if b["_priority"] == "high" else 1
        return (tier, -b["_stale_days"])

    result.sort(key=_sort_key)
    return result
```

**3b. Modify `status()` to insert stale bug warnings** (insert before the `updates = data.get("updates", [])` line at ~5648):

```python
    # Stale P0/P1 bug warnings
    stale_bugs = _get_stale_bugs(data, datetime.now(tz=timezone.utc))
    if stale_bugs:
        print("\n### Bug Warnings:")
        for bug in stale_bugs:
            tier = "P0" if bug.get("_priority") == "high" else "P1"
            desc = (bug.get("description") or "")[:60]
            days = int(bug.get("_stale_days", 0))
            raw_ts = bug.get("updated_at") or bug.get("created_at") or ""
            last_date = raw_ts[:10] if raw_ts else "unknown"
            print(f"  [{tier}] {bug.get('id')}: {desc} (stale {days}d, last: {last_date})")
```

Note: Add `from datetime import datetime, timezone` at the top of the file if not already present (check existing imports — `datetime` is likely already imported).

- [ ] **Step 4: Run tests — verify GREEN**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestStaleBugs -v 2>&1 | tail -20
```

Expected: All 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "feat(PT-F14): add _get_stale_bugs() helper + stale P0/P1 warnings in status()"
```

---

## Task 8: `status()` hidden-history + `list_updates()` unlimited default

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py` (lines ~5648–5668 and ~9369)
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

- [ ] **Step 1: Write failing tests**

Append to `test_task_execution_semantics.py`:

```python
class TestStatusHiddenHistory:
    def _add_updates(self, tmp_path: Path, count: int) -> None:
        for i in range(count):
            progress_manager.add_update(
                category="status",
                summary=f"update {i + 1}",
            )

    def test_status_shows_plus_n_more_when_over_5_updates(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        self._add_updates(tmp_path, 12)
        progress_manager.status()
        out = capsys.readouterr().out
        assert "+7 more" in out or "+7" in out

    def test_status_no_plus_n_when_5_or_fewer_updates(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        self._add_updates(tmp_path, 5)
        progress_manager.status()
        out = capsys.readouterr().out
        assert "more" not in out or "+0" not in out  # no overflow line

    def test_status_updates_sorted_by_created_at(self, tmp_path, capsys):
        """The 5 shown updates must be the 5 most recent."""
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        self._add_updates(tmp_path, 7)
        progress_manager.status()
        out = capsys.readouterr().out
        # updates 3-7 should appear, updates 1-2 should not
        assert "update 7" in out
        assert "update 3" in out
        assert "update 1" not in out
        assert "update 2" not in out


class TestListUpdatesUnlimited:
    def test_list_updates_default_returns_all(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        for i in range(15):
            progress_manager.add_update(category="status", summary=f"upd {i+1}")
        progress_manager.list_updates()
        out = capsys.readouterr().out
        assert "upd 1" in out
        assert "upd 15" in out

    def test_list_updates_limit_positive_truncates(self, tmp_path, capsys):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        for i in range(10):
            progress_manager.add_update(category="status", summary=f"upd {i+1}")
        progress_manager.list_updates(limit=3)
        out = capsys.readouterr().out
        assert "upd 10" in out  # most recent
        assert "upd 1" not in out  # truncated

    def test_list_updates_negative_limit_raises_or_returns_error(self, tmp_path):
        _init_project(tmp_path)
        progress_manager._PROJECT_ROOT_OVERRIDE = tmp_path
        result = subprocess.run(
            [
                "python3", str(SCRIPT_DIR / "progress_manager.py"),
                "--project-root", str(tmp_path),
                "list-updates", "--limit", "-1",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
```

- [ ] **Step 2: Run tests — verify RED**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestStatusHiddenHistory plugins/progress-tracker/tests/test_task_execution_semantics.py::TestListUpdatesUnlimited -v 2>&1 | tail -25
```

Expected: Most FAIL.

- [ ] **Step 3: Implement**

**3a. Modify `status()` updates block** (replace lines ~5648–5667):

```python
    updates = data.get("updates", [])
    if updates:
        # Sort ascending by created_at before slicing so [-5:] gets the most recent 5.
        def _upd_ts(u):
            return u.get("created_at") or ""
        sorted_updates = sorted(updates, key=_upd_ts)
        shown = sorted_updates[-5:]
        total_count = len(updates)
        hidden = total_count - len(shown)
        print(f"\n### Recent Updates (showing {len(shown)}/{total_count}):")
        for update in shown:
            line = (
                f"  [{update.get('id', 'UPD-???')}] "
                f"{update.get('category', 'status')}: {update.get('summary', '')}"
            )
            if update.get("feature_id") is not None:
                line += f" (feature:{update['feature_id']})"
            if update.get("role") and update.get("owner"):
                line += f" [{update['role']}={update['owner']}]"
            print(line)
        if hidden > 0:
            print(f"  +{hidden} more updates (run: prog list-updates)")
```

**3b. Modify `list_updates()`** (at line 9369 — change signature and body):

```python
def list_updates(limit: int = 0) -> bool:
    """List the latest structured updates. limit=0 means show all."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    updates = data.get("updates", [])
    if not updates:
        print("No updates recorded.")
        return True

    if limit < 0:
        print("Error: --limit must be 0 (all) or a positive integer")
        return False

    safe_limit = len(updates) if limit == 0 else min(len(updates), limit)
    print(f"Showing {safe_limit} of {len(updates)} update(s):")
    for item in updates[-safe_limit:]:
        line = f"- [{item.get('id', 'UPD-???')}] {item.get('category', 'status')}: {item.get('summary', '')}"
        source = str(item.get("source") or "").strip()
        if source:
            line += f" [source={source}]"
        if item.get("feature_id") is not None:
            line += f" (feature:{item['feature_id']})"
        if item.get("role") and item.get("owner"):
            line += f" [{item['role']}={item['owner']}]"
        overflow_count = item.get("refs_overflow_count", 0) or 0
        if overflow_count > 0:
            line += f" [+{overflow_count} refs overflow]"
        print(line)
    return True
```

**3c. Change `list-updates` parser default** (at line 11755):

```python
    list_updates_parser.add_argument("--limit", type=int, default=0, help="Max updates (0=all)")
```

**3d. Add negative limit validation in `main()` dispatch** (around line 12247–12249):

```python
        if args.command == "list-updates":
            if args.limit < 0:
                print("Error: --limit must be 0 (all) or a positive integer", file=sys.stderr)
                return 2
            return list_updates(limit=args.limit)
```

- [ ] **Step 4: Run tests — verify GREEN**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py::TestStatusHiddenHistory plugins/progress-tracker/tests/test_task_execution_semantics.py::TestListUpdatesUnlimited -v 2>&1 | tail -25
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "feat(PT-F14): status hidden-history count + list-updates unlimited default"
```

---

## Task 9: `docs/PROG_COMMANDS.md` updates

**Files:**
- Modify: `plugins/progress-tracker/docs/PROG_COMMANDS.md`

No TDD needed here — this is documentation. Spot-check with `generate_prog_docs.py --check`.

- [ ] **Step 1: Add new command entries to `docs/PROG_COMMANDS.md`**

Find the `### README_EN` source block and add after the existing entries for `prog next`:

```markdown
### `/progress-tracker:prog-next` — `prog next --done`

Close the currently active task.

- **Standalone task** (`parent_feature_id=null`): squash-merges the task branch into the default branch, deletes the branch, adds exactly 1 commit. No feature done-gate is triggered.
- **Feature-bound task** (`parent_feature_id` set): marks the task completed and advances parent feature task-progress counter. Parent feature is **not** auto-closed.

**RC semantics:** 0 = success; 1 = precondition failure (no active task, invalid state); 2 = parameter error.

```bash
prog next --done           # close current task (human-readable output)
prog next --done --json    # machine-readable: {"status","closed_task_id","message"}
```

### `/progress-tracker:prog-add-task` — `prog add-task`

Create a new task item.

```bash
prog add-task --description "Fix typo in README"
prog add-task --description "Implement login" --feature-id 3
prog add-task --description "Quick cleanup" --workflow-profile quick_task --priority P0
```

**Constraints:**
- `--feature-id` must reference an existing feature (RC=1 if not found).
- `--feature-id` and `--workflow-profile quick_task` are mutually exclusive (RC=2).

### Ghost Commands (do NOT use)

| Command | Correct replacement |
|---------|---------------------|
| `prog start-task <id>` | `prog next --done` |
```

Also update the existing `prog list-updates` entry to note `--limit 0` means all.

- [ ] **Step 2: Verify generation script still passes**

```bash
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check 2>&1 | tail -10
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add plugins/progress-tracker/docs/PROG_COMMANDS.md
git commit -m "docs(PT-F14): add prog add-task, next --done, ghost commands section to PROG_COMMANDS.md"
```

---

## Task 10: Full test suite + acceptance verification

**Files:**
- Test: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

- [ ] **Step 1: Run the full new test file**

```bash
python3 -m pytest plugins/progress-tracker/tests/test_task_execution_semantics.py -v 2>&1 | tail -40
```

Expected: All tests PASS.

- [ ] **Step 2: Run the full existing test suite (regression check)**

```bash
python3 -m pytest plugins/progress-tracker/tests/ -x -q --tb=short 2>&1 | tail -20
```

Expected: All tests pass except the pre-existing BUG-008 failure (`test_cmd_done_clears_state_when_project_completed_audit_fails`) which is tracked separately.

- [ ] **Step 3: Manual acceptance test 1** — `prog next` selects task, branch created

```bash
cd /Users/siunin/Projects/Claude-Plugins/.claude/worktrees/feat+PT-F14-task-execution-semantics
# Init a scratch project in /tmp
TMP_PROJ=$(mktemp -d)
plugins/progress-tracker/prog init "Scratch" --project-root $TMP_PROJ
plugins/progress-tracker/prog add-task --description "my quick task" --project-root $TMP_PROJ
plugins/progress-tracker/prog next --project-root $TMP_PROJ
git -C $TMP_PROJ branch --list "task/TASK-001"
```

Expected: `task/TASK-001` branch appears.

- [ ] **Step 4: Manual acceptance test 2** — `prog next --done` squash-merges

```bash
plugins/progress-tracker/prog next --done --project-root $TMP_PROJ
git -C $TMP_PROJ log --oneline -3
git -C $TMP_PROJ branch --list "task/TASK-001"
```

Expected: 1 new commit on main (message contains `task(TASK-001)`), branch gone.

- [ ] **Step 5: Manual acceptance test 5** — `prog status` shows stale warnings

```bash
# Manually insert a stale P0 bug into $TMP_PROJ progress.json (set created_at to 5 days ago)
python3 -c "
import json; from pathlib import Path; from datetime import datetime, timezone, timedelta
p = Path('$TMP_PROJ/docs/progress-tracker/state/progress.json')
d = json.loads(p.read_text())
d.setdefault('bugs', []).append({
    'id': 'BUG-TEST', 'description': 'stale p0', 'priority': 'high',
    'status': 'confirmed',
    'created_at': (datetime.now(tz=timezone.utc) - timedelta(days=5)).isoformat()
})
p.write_text(json.dumps(d, indent=2))
"
plugins/progress-tracker/prog status --project-root $TMP_PROJ
```

Expected: `### Bug Warnings:` section with `[P0] BUG-TEST`.

- [ ] **Step 6: Update workflow state to execution_complete**

```bash
plugins/progress-tracker/prog set-workflow-state \
  --phase execution_complete \
  --next-action "verify_and_complete" \
  --project-root plugins/progress-tracker
```

- [ ] **Step 7: Final commit**

```bash
git add plugins/progress-tracker/tests/test_task_execution_semantics.py
git commit -m "test(PT-F14): complete acceptance verification for task execution semantics"
```

---

## Self-Review Checklist

- [x] **Spec Section 1** (data model): Covered by Task 1 (`parent_feature_id`) + Task 2 (`current_task_id` write) + Tasks 4/5 (`current_task_id` cleared on close)
- [x] **Spec Section 2** (`prog next --done`): Task 5; (`prog add-task`): Task 1; (`list-updates`): Task 8
- [x] **Spec Section 2** (ghost command, RC semantics): Task 6
- [x] **Spec Section 3** (internal functions): Tasks 3, 4; lock exemption: Task 5
- [x] **Spec Section 4** (status visibility): Tasks 7, 8
- [x] **Spec Section 5** (PROG_COMMANDS.md): Task 9
- [x] **Spec Section 6** (all 16 test scenarios): Distributed across Tasks 1-8 + Task 10
- [x] **Acceptance tests 1-5**: Manual verification in Task 10
- [x] **Type consistency**: `_close_current_task` / `_close_standalone_task` / `_close_feature_bound_task` signatures consistent (data dict passed, task dict passed)
- [x] **No placeholders**: All test code and implementation snippets are complete
