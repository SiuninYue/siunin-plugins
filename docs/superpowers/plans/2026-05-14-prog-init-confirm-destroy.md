# `prog init --force` Confirm-Destroy Protection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent `prog init --force` from silently destroying real project data by requiring an explicit `--confirm-destroy` flag when completed features are detected.

**Architecture:** Add a `confirm_destroy=False` parameter to `init_tracking()`. Inside the `force` branch — before `archive_current_progress()` — count completed features using the `completed` boolean field. If `completed_count > 0` and `confirm_destroy=False`, print an error and return `False`. Wire the matching `--confirm-destroy` CLI flag through the subparser and dispatch. Fix test isolation by asserting `configure_project_scope` return values (Rule A) and adding `confirm_destroy=True` to the one test that reinitializes over completed data (Rule B).

**Tech Stack:** Python 3, pytest, `plugins/progress-tracker/hooks/scripts/progress_manager.py`

**Spec:** `docs/superpowers/specs/2026-05-14-prog-init-force-confirm-destroy-design.md`

**Run tests from:** `/Users/siunin/Projects/Claude-Plugins` (repo root), using `python3 -m pytest plugins/progress-tracker/tests/<file> -v`

---

### Task 1: Write 7 failing tests

**Files:**
- Create: `plugins/progress-tracker/tests/test_init_confirm_destroy.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for prog init --force confirm-destroy protection (spec: 2026-05-14)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import sys

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


def _mark_feature_completed(temp_dir: Path, feature_index: int = 0) -> None:
    """Write completed=True onto a feature in the current project's progress.json."""
    json_path = (
        temp_dir / "docs" / "progress-tracker" / "state" / "progress.json"
    )
    data = json.loads(json_path.read_text())
    data["features"][feature_index]["completed"] = True
    json_path.write_text(json.dumps(data))


class TestInitForceConfirmDestroy:
    def test_init_force_blocked_when_completed_features_exist(self, temp_dir, capsys):
        """init_tracking(force=True) returns False and prints an error when completed_count > 0."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        _mark_feature_completed(temp_dir)

        result = progress_manager.init_tracking("New Project", force=True)

        assert result is False
        captured = capsys.readouterr()
        assert "completed feature(s) detected" in captured.out
        assert "confirm_destroy=True" in captured.out
        # Verify original data was NOT overwritten
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "Real Project"

    def test_init_force_confirm_destroy_bypasses_protection(self, temp_dir):
        """init_tracking(force=True, confirm_destroy=True) proceeds despite completed features."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        _mark_feature_completed(temp_dir)

        result = progress_manager.init_tracking(
            "New Project", force=True, confirm_destroy=True
        )

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "New Project"

    def test_init_force_allowed_when_no_completed_features(self, temp_dir):
        """init_tracking(force=True) without confirm_destroy proceeds when all features are pending."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        # Feature remains completed=False — no confirm_destroy needed

        result = progress_manager.init_tracking("New Project", force=True)

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "New Project"

    def test_init_force_allowed_on_empty_project(self, temp_dir):
        """init_tracking(force=True) on a project with no features proceeds without confirm_destroy."""
        progress_manager.init_tracking("First", force=True)

        result = progress_manager.init_tracking("Second", force=True)

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "Second"

    def test_cli_init_force_blocked_without_confirm_destroy(self, temp_dir, capsys):
        """CLI: prog init --force returns False and prints error when completed features exist."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        _mark_feature_completed(temp_dir)

        with patch(
            "sys.argv",
            ["progress_manager.py", "init", "--force", "New Project"],
        ):
            result = progress_manager.main()

        assert result is False
        captured = capsys.readouterr()
        assert "completed feature(s) detected" in captured.out

    def test_cli_init_force_confirm_destroy_succeeds(self, temp_dir):
        """CLI: prog init --force --confirm-destroy proceeds with completed features."""
        progress_manager.init_tracking("Real Project", force=True)
        progress_manager.add_feature("Feature A", ["step-a"])
        _mark_feature_completed(temp_dir)

        with patch(
            "sys.argv",
            ["progress_manager.py", "init", "--force", "--confirm-destroy", "New Project"],
        ):
            result = progress_manager.main()

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "New Project"

    def test_cli_confirm_destroy_without_force_is_noop(self, temp_dir):
        """CLI: --confirm-destroy without --force is silently ignored; init proceeds normally."""
        with patch(
            "sys.argv",
            ["progress_manager.py", "init", "--confirm-destroy", "My Project"],
        ):
            result = progress_manager.main()

        assert result is True
        data = progress_manager.load_progress_json()
        assert data["project_name"] == "My Project"
```

- [ ] **Step 2: Run tests and confirm 7 failures**

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 -m pytest plugins/progress-tracker/tests/test_init_confirm_destroy.py -v
```

Expected: 7 failures. Typical errors:
- `TypeError: init_tracking() got an unexpected keyword argument 'confirm_destroy'` (tests 1-4)
- `error: unrecognized arguments: --confirm-destroy` (tests 5-7)

---

### Task 2: Implement `init_tracking()` guard

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:5102`

- [ ] **Step 1: Add `confirm_destroy` parameter and guard logic**

Find this block (around line 5102):

```python
def init_tracking(project_name, features=None, force=False):
    """
    Initialize progress tracking for a project.

    Args:
        project_name: Name of the project to track
        features: Optional list of feature dicts with keys: name, test_steps
        force: Force re-initialization even if tracking exists
    """
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if json_path.exists() and not force:
        existing = load_progress_json()
        if existing:
            print(
                f"Progress tracking already exists for project: {existing.get('project_name', 'Unknown')}"
            )
            print(f"Location: {progress_dir}")
            print("Use --force to re-initialize")
            return False

    archived_entry = None
    existing_parent_root: Optional[str] = None
    if force:
        existing = load_progress_json()
        if isinstance(existing, dict):
            raw = existing.get("parent_project_root")
            if isinstance(raw, str) and raw.strip():
                existing_parent_root = raw.strip()
        archived_entry = archive_current_progress(reason="reinitialize")
```

Replace with:

```python
def init_tracking(project_name, features=None, force=False, confirm_destroy=False):
    """
    Initialize progress tracking for a project.

    Args:
        project_name: Name of the project to track
        features: Optional list of feature dicts with keys: name, test_steps
        force: Force re-initialization even if tracking exists
        confirm_destroy: Required when force=True and completed features exist
    """
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if json_path.exists() and not force:
        existing = load_progress_json()
        if existing:
            print(
                f"Progress tracking already exists for project: {existing.get('project_name', 'Unknown')}"
            )
            print(f"Location: {progress_dir}")
            print("Use --force to re-initialize")
            return False

    archived_entry = None
    existing_parent_root: Optional[str] = None
    if force:
        existing = load_progress_json()
        if isinstance(existing, dict):
            if not confirm_destroy:
                raw_features = existing.get("features")
                feature_list = raw_features if isinstance(raw_features, list) else []
                completed_count = sum(
                    1 for f in feature_list
                    if isinstance(f, dict) and bool(f.get("completed", False))
                )
                if completed_count > 0:
                    project = existing.get("project_name", "unknown")
                    print(
                        f"ERROR: {completed_count} completed feature(s) detected in "
                        f"'{project}'. Refusing to overwrite real project data.\n"
                        "Pass confirm_destroy=True (API) or --confirm-destroy (CLI) to proceed."
                    )
                    return False
            raw = existing.get("parent_project_root")
            if isinstance(raw, str) and raw.strip():
                existing_parent_root = raw.strip()
        archived_entry = archive_current_progress(reason="reinitialize")
```

- [ ] **Step 2: Run the 4 Python API tests**

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 -m pytest plugins/progress-tracker/tests/test_init_confirm_destroy.py::TestInitForceConfirmDestroy::test_init_force_blocked_when_completed_features_exist plugins/progress-tracker/tests/test_init_confirm_destroy.py::TestInitForceConfirmDestroy::test_init_force_confirm_destroy_bypasses_protection plugins/progress-tracker/tests/test_init_confirm_destroy.py::TestInitForceConfirmDestroy::test_init_force_allowed_when_no_completed_features plugins/progress-tracker/tests/test_init_confirm_destroy.py::TestInitForceConfirmDestroy::test_init_force_allowed_on_empty_project -v
```

Expected: 4 passed. The CLI tests (5-7) still fail — that's expected at this stage.

- [ ] **Step 3: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git add plugins/progress-tracker/tests/test_init_confirm_destroy.py
git commit -m "feat(PT): add confirm_destroy guard to init_tracking()

Blocks prog init --force when completed_count > 0 unless
confirm_destroy=True is explicitly passed.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: CLI changes — subparser, dispatch, Usage doc

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:9,11415,12065`

- [ ] **Step 1: Update Usage doc (line 9)**

Find:

```python
    python3 progress_manager.py init [--force] <project_name>
```

Replace with:

```python
    python3 progress_manager.py init [--force] [--confirm-destroy] <project_name>
```

- [ ] **Step 2: Add `--confirm-destroy` to subparser (around line 11415)**

Find:

```python
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize progress tracking")
    init_parser.add_argument("project_name", help="Name of the project")
    init_parser.add_argument(
        "--force", action="store_true", help="Force re-initialization"
    )
```

Replace with:

```python
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize progress tracking")
    init_parser.add_argument("project_name", help="Name of the project")
    init_parser.add_argument(
        "--force", action="store_true", help="Force re-initialization"
    )
    init_parser.add_argument(
        "--confirm-destroy",
        action="store_true",
        dest="confirm_destroy",
        help="Required when --force is used and the project has completed features.",
    )
```

- [ ] **Step 3: Update dispatch (around line 12065)**

Find:

```python
        if args.command == "init":
            return init_tracking(args.project_name, force=args.force)
```

Replace with:

```python
        if args.command == "init":
            return init_tracking(
                args.project_name,
                force=args.force,
                confirm_destroy=getattr(args, "confirm_destroy", False),
            )
```

- [ ] **Step 4: Run all 7 new tests**

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 -m pytest plugins/progress-tracker/tests/test_init_confirm_destroy.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Run full test suite to detect regressions**

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 -m pytest plugins/progress-tracker/tests/ -x -q 2>&1 | tail -20
```

Expected: failures in `test_init_tracking_existing_with_force` (needs Rule B fix — handled in Task 4). All other tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git commit -m "feat(PT): wire --confirm-destroy CLI flag for prog init

Adds --confirm-destroy to init subparser and dispatch.
Updates Usage doc to reflect new flag.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix Rule B — `test_init_tracking_existing_with_force`

**Files:**
- Modify: `plugins/progress-tracker/tests/test_progress_manager.py:298`

Context: `progress_file` fixture sets up "Test Project" with Feature 1 `completed=True`. After our change, `init_tracking("New Project", force=True)` will be blocked unless `confirm_destroy=True` is added.

- [ ] **Step 1: Add `confirm_destroy=True` to the test**

Find (around line 296):

```python
    def test_init_tracking_existing_with_force(self, progress_file):
        """Should re-initialize when force is True."""
        result = progress_manager.init_tracking("New Project", force=True)
        assert result is True
```

Replace with:

```python
    def test_init_tracking_existing_with_force(self, progress_file):
        """Should re-initialize when force is True (with confirm_destroy for completed data)."""
        result = progress_manager.init_tracking("New Project", force=True, confirm_destroy=True)
        assert result is True
```

- [ ] **Step 2: Run the fixed test**

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 -m pytest plugins/progress-tracker/tests/test_progress_manager.py::TestInitTracking::test_init_tracking_existing_with_force -v
```

Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins
git add plugins/progress-tracker/tests/test_progress_manager.py
git commit -m "test(PT): add confirm_destroy=True to reinit-over-completed-data test

Rule B: test_init_tracking_existing_with_force uses progress_file
fixture (Feature 1 completed=True), so confirm_destroy=True is required.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Fix Rule A — assert `configure_project_scope` return values

**Files:**
- Modify: `plugins/progress-tracker/tests/test_auto_state_commit.py` (20 call sites)
- Modify: `plugins/progress-tracker/tests/test_scope_fail_closed.py:86`

Rule A: Every explicit call to `configure_project_scope(...)` must assert `is True`. This ensures that if path resolution silently fails, the test fails loudly instead of continuing to mutate the real directory.

- [ ] **Step 1: Fix `test_auto_state_commit.py` (20 sites, mechanical replacement)**

All 20 sites follow the same pattern: `progress_manager.configure_project_scope(str(mock_git_repo))` with no assertion. Run this Python script to replace them all:

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 - <<'EOF'
path = "plugins/progress-tracker/tests/test_auto_state_commit.py"
content = open(path).read()
old = "progress_manager.configure_project_scope(str(mock_git_repo))"
new = "assert progress_manager.configure_project_scope(str(mock_git_repo)) is True"
assert content.count(old) == 20, f"Expected 20 occurrences, found {content.count(old)}"
content = content.replace(old, new)
open(path, "w").write(content)
print(f"Replaced 20 occurrences in {path}")
EOF
```

Expected output: `Replaced 20 occurrences in plugins/progress-tracker/tests/test_auto_state_commit.py`

- [ ] **Step 2: Fix `test_scope_fail_closed.py` (1 site)**

Find (around line 86):

```python
    progress_manager.configure_project_scope(None)
    progress_manager.init_tracking("Root Tracker", force=True)
```

Replace with:

```python
    assert progress_manager.configure_project_scope(None) is True
    progress_manager.init_tracking("Root Tracker", force=True)
```

- [ ] **Step 3: Run the modified test files**

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 -m pytest plugins/progress-tracker/tests/test_auto_state_commit.py plugins/progress-tracker/tests/test_scope_fail_closed.py -v -q 2>&1 | tail -15
```

Expected: all tests in both files pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins
git add plugins/progress-tracker/tests/test_auto_state_commit.py
git add plugins/progress-tracker/tests/test_scope_fail_closed.py
git commit -m "test(PT): assert configure_project_scope return value (Rule A)

Adds assertion on all 21 unguarded configure_project_scope() calls
across test_auto_state_commit.py (20) and test_scope_fail_closed.py (1).
Silent path-resolution failures now cause immediate test failure instead
of falling through to mutate the real project directory.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run the full PT test suite**

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 -m pytest plugins/progress-tracker/tests/ -q 2>&1 | tail -10
```

Expected: all tests pass, no failures.

- [ ] **Step 2: Smoke-test the protection via CLI**

```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker
python3 hooks/scripts/progress_manager.py init --help | grep confirm-destroy
```

Expected output contains: `--confirm-destroy`

- [ ] **Step 3: Done — hand off to `/prog done`**

Implementation complete. All 7 new tests pass, full suite green, CLI flag wired and documented.
