# AI Workspace Entropy Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `prog next` reduce workspace entropy automatically by classifying dirty changes, stale routes/worktrees, and obsolete branches, then safely fixing low-risk cases before blocking the user.

**Architecture:** Add a bounded entropy decision engine behind the `progress_manager.py` facade. The engine emits explicit green/yellow/red decisions, applies only reversible or provably safe fixes by default, and records every automated action through progress updates or JSON reports. `next_feature` should call the safe preflight path before normal selection so recoverable entropy does not terminate `/prog-next`.

**Tech Stack:** Python 3, argparse, pytest, existing `git_utils.py`, `worktree_handler.py`, `route_sync.py`, `route_commands.py`, `state_io.py`, and `scripts/check_pm_boundary.sh`.

**Plan path:** `docs/plans/2026-06-04-f25-ai-workspace-entropy-manager.md`

**Working directory for all commands:** `/Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker`

---

## Product Principle

`prog` exists to reduce project entropy. It should not stop a workflow for issues it can safely diagnose and repair. It should stop only when continuing would risk losing user work, hiding unmerged code, or fabricating required review evidence.

## Decision Model

Green actions are safe to apply automatically in `prog next`:

- Remove stale `active_routes` that point to missing or completed child work.
- Rebuild routes from child `current_feature_id` via existing linked-project state.
- Prune orphaned Git worktree metadata when `git worktree prune` reports no dirty worktree.
- Delete local branches only when they are ancestors of the default branch and have no checked-out worktree.
- Commit whitelisted tracker state files as `chore(PT): state sync ... [skip ci]`.
- Continue past optional planning warnings when required lanes pass, after writing an audit update that records the skipped optional lanes.

Yellow actions may be automated only with an audit trail and reversible quarantine:

- Stash ambiguous user edits with a named `prog-entropy/<timestamp>` stash message.
- Create a quarantine branch for unrelated but tracked source changes.
- Mark old unmerged branches as cleanup candidates without deleting them.
- Keep generated files when ownership is unclear, but include them in the JSON report.

Red actions must block:

- Discard tracked source changes.
- Delete unmerged branches.
- Force-push, hard-reset, or rewrite shared refs.
- Create fake required planning evidence such as `planning:ceo_review` without a real planning source.

## Risks

- Over-aggressive cleanup could hide user work. Mitigation: destructive operations are red and always block; yellow actions use stash or quarantine branch only.
- Branch deletion can be wrong if ancestry checks ignore remote/default branch drift. Mitigation: only delete local branches that are ancestors of the resolved default branch and are not checked out by any worktree.
- Auto-committing state can mix unrelated files. Mitigation: reuse the existing tracker state whitelist and never include source files in state-sync commits.
- Integrating into `next_feature` could mask real planning failures. Mitigation: only optional planning warnings may auto-continue; required planning evidence remains fail-closed.
- Route/worktree repair can create confusing state if child trackers disagree. Mitigation: safe route repair must emit a JSON action report and progress update with the child project code and reason.

## File Structure

- Create `hooks/scripts/workspace_entropy.py`
  - Owns dirty-change classification, branch/worktree inspection, route repair decisions, and JSON report construction.
- Modify `hooks/scripts/progress_manager.py`
  - Adds facade wrappers and CLI subcommands: `entropy-check`, `entropy-fix`.
  - Calls the safe entropy preflight from `next_feature` before normal planning/selection gates.
- Modify or extend `hooks/scripts/git_utils.py`
  - Reuse `_run_git`, `_get_dirty_state_files`, `_git_commit_state`, and branch ancestry helpers; do not duplicate Git subprocess wrappers.
- Modify or extend `hooks/scripts/worktree_handler.py`
  - Reuse worktree parsing and merged-branch detection helpers where possible.
- Modify or extend `hooks/scripts/route_sync.py` / `hooks/scripts/route_commands.py`
  - Reuse existing route repair behavior rather than inventing a second route writer.
- Test `tests/test_workspace_entropy.py`
  - Unit coverage for classification, branch deletion eligibility, safe-fix decisions, and red/yellow/green policy.
- Test `tests/test_next_feature_entropy_preflight.py`
  - Integration coverage that `next-feature` repairs safe entropy and blocks only red cases.
- Modify `docs/PROG_COMMANDS.md`
  - Document `entropy-check`, `entropy-fix`, default safe behavior, and red/yellow/green policy.
- Modify `docs/progress-tracker/architecture/progress-manager-module-map.md`
  - Add workspace entropy ownership and facade wrapper map.
- Add `docs/changes/YYYYMMDD-workspace-entropy-manager.md`
  - Record shipped behavior, tests, rollback strategy, and command examples.
- Modify `docs/changes/index.jsonl`
  - Append one matching change record at completion.

## CLI Contract

### `prog entropy-check --json`

Inspects the current workspace without mutation and returns:

```json
{
  "status": "ok",
  "decision": "safe_fix_available",
  "dirty_changes": {
    "auto_commit": ["docs/progress-tracker/state/progress.json"],
    "quarantine": [],
    "block": []
  },
  "branches": {
    "delete_local": ["f21"],
    "review": ["old-unmerged-topic"],
    "keep": ["main"]
  },
  "routes": {
    "repair": ["PT stale route points to missing worktree"],
    "block": []
  },
  "worktrees": {
    "prune": true,
    "block": []
  }
}
```

### `prog entropy-fix --safe --json`

Applies green actions only. It must be idempotent and must not delete unmerged branches or discard tracked source changes.

### `prog entropy-fix --apply --json`

May apply yellow quarantine actions such as named stash or quarantine branch creation. It still must not perform red actions.

## Tasks

### Task 1: Add Entropy Report Model and Dirty-Change Classifier

**Files:**
- Create: `hooks/scripts/workspace_entropy.py`
- Test: `tests/test_workspace_entropy.py`

- [ ] **Step 1: Write failing tests for green/yellow/red dirty classification**

Add tests that construct porcelain entries and assert:

```python
def test_classifies_tracker_state_as_auto_commit():
    report = workspace_entropy.classify_dirty_entries([
        " M docs/progress-tracker/state/progress.json",
        " M plugins/progress-tracker/docs/progress-tracker/state/status_summary.v1.json",
    ])

    assert report["auto_commit"] == [
        "docs/progress-tracker/state/progress.json",
        "plugins/progress-tracker/docs/progress-tracker/state/status_summary.v1.json",
    ]
    assert report["quarantine"] == []
    assert report["block"] == []


def test_classifies_source_edits_as_quarantine_not_delete():
    report = workspace_entropy.classify_dirty_entries([
        " M plugins/progress-tracker/hooks/scripts/progress_manager.py",
    ])

    assert report["auto_commit"] == []
    assert report["quarantine"] == [
        "plugins/progress-tracker/hooks/scripts/progress_manager.py",
    ]
    assert report["block"] == []


def test_classifies_delete_of_source_file_as_block():
    report = workspace_entropy.classify_dirty_entries([
        " D plugins/progress-tracker/hooks/scripts/progress_manager.py",
    ])

    assert report["block"] == [
        "plugins/progress-tracker/hooks/scripts/progress_manager.py",
    ]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/test_workspace_entropy.py -q`

Expected: failure because `workspace_entropy.py` does not exist.

- [ ] **Step 3: Implement minimal classifier**

Create `workspace_entropy.py` with:

```python
TRACKER_STATE_PREFIXES = (
    "docs/progress-tracker/state/",
    "plugins/progress-tracker/docs/progress-tracker/state/",
    "plugins/note-organizer/docs/progress-tracker/state/",
    "plugins/super-product-manager/docs/progress-tracker/state/",
)


def _porcelain_path(line: str) -> str:
    return line[3:].strip()


def classify_dirty_entries(entries: list[str]) -> dict[str, list[str]]:
    result = {"auto_commit": [], "quarantine": [], "block": []}
    for entry in entries:
        if len(entry) < 4:
            continue
        status = entry[:2]
        path = _porcelain_path(entry)
        if not path:
            continue
        if "D" in status and not path.startswith(TRACKER_STATE_PREFIXES):
            result["block"].append(path)
        elif path.startswith(TRACKER_STATE_PREFIXES):
            result["auto_commit"].append(path)
        else:
            result["quarantine"].append(path)
    return result
```

- [ ] **Step 4: Verify the tests pass**

Run: `uv run pytest tests/test_workspace_entropy.py -q`

Expected: pass.

### Task 2: Add Branch Cleanup Eligibility

**Files:**
- Modify: `hooks/scripts/workspace_entropy.py`
- Test: `tests/test_workspace_entropy.py`

- [ ] **Step 1: Write tests for merged branch deletion policy**

Assert that a branch is deletable only when it is local, merged into the default branch, not checked out, and not protected:

```python
def test_branch_cleanup_deletes_only_merged_unchecked_local_branch():
    branches = [
        {"name": "f21", "is_current": False, "merged": True, "has_worktree": False},
        {"name": "main", "is_current": True, "merged": True, "has_worktree": True},
        {"name": "old-topic", "is_current": False, "merged": False, "has_worktree": False},
    ]

    report = workspace_entropy.classify_branches(branches, default_branch="main")

    assert report["delete_local"] == ["f21"]
    assert "main" in report["keep"]
    assert report["review"] == ["old-topic"]
```

- [ ] **Step 2: Implement branch classifier**

Add protected branch handling:

```python
PROTECTED_BRANCHES = {"main", "master", "develop", "dev"}


def classify_branches(
    branches: list[dict[str, object]], *, default_branch: str
) -> dict[str, list[str]]:
    report = {"delete_local": [], "review": [], "keep": []}
    protected = set(PROTECTED_BRANCHES)
    protected.add(default_branch)
    for branch in branches:
        name = str(branch.get("name") or "")
        if not name:
            continue
        if (
            name not in protected
            and branch.get("merged") is True
            and branch.get("is_current") is not True
            and branch.get("has_worktree") is not True
        ):
            report["delete_local"].append(name)
        elif branch.get("merged") is False and name not in protected:
            report["review"].append(name)
        else:
            report["keep"].append(name)
    return report
```

- [ ] **Step 3: Verify branch tests pass**

Run: `uv run pytest tests/test_workspace_entropy.py -q`

Expected: pass.

### Task 3: Add `entropy-check` and `entropy-fix` Facade Commands

**Files:**
- Modify: `hooks/scripts/progress_manager.py`
- Modify: `hooks/scripts/workspace_entropy.py`
- Test: `tests/test_workspace_entropy.py`
- Docs: `docs/PROG_COMMANDS.md`

- [ ] **Step 1: Write CLI tests**

Add tests that call `progress_manager.main()` with:

```python
with patch("sys.argv", ["progress_manager.py", "entropy-check", "--json"]):
    assert progress_manager.main() == 0

with patch("sys.argv", ["progress_manager.py", "entropy-fix", "--safe", "--json"]):
    assert progress_manager.main() in (0, 1)
```

Expected JSON fields: `dirty_changes`, `branches`, `routes`, `worktrees`, `actions`.

- [ ] **Step 2: Add parser entries**

In `progress_manager.py`, register:

```python
entropy_check_parser = subparsers.add_parser(
    "entropy-check", help="Inspect workspace entropy and emit cleanup decisions"
)
entropy_check_parser.add_argument("--json", action="store_true")

entropy_fix_parser = subparsers.add_parser(
    "entropy-fix", help="Apply safe workspace entropy cleanup actions"
)
entropy_fix_parser.add_argument("--safe", action="store_true")
entropy_fix_parser.add_argument("--apply", action="store_true")
entropy_fix_parser.add_argument("--json", action="store_true")
```

- [ ] **Step 3: Add facade wrappers**

Keep behavior in `workspace_entropy.py`; expose wrappers in `progress_manager.py` and mark them:

```python
def entropy_check(output_json: bool = False) -> int:
    return workspace_entropy.entropy_check_command(output_json=output_json)


entropy_check.is_wrapper = True


def entropy_fix(*, safe: bool = False, apply: bool = False, output_json: bool = False) -> int:
    return workspace_entropy.entropy_fix_command(
        safe=safe,
        apply=apply,
        output_json=output_json,
    )


entropy_fix.is_wrapper = True
```

- [ ] **Step 4: Document commands**

Add `entropy-check` and `entropy-fix` sections to `docs/PROG_COMMANDS.md`, including green/yellow/red examples and the no-destructive-action guarantee.

- [ ] **Step 5: Run checks**

Run:

```bash
scripts/check_pm_boundary.sh
python3 hooks/scripts/generate_prog_docs.py --check
uv run pytest tests/test_workspace_entropy.py -q
```

Expected: all pass.

### Task 4: Integrate Safe Entropy Preflight into `next_feature`

**Files:**
- Modify: `hooks/scripts/progress_manager.py`
- Modify: `hooks/scripts/workspace_entropy.py`
- Test: `tests/test_next_feature_entropy_preflight.py`

- [ ] **Step 1: Write integration tests**

Cover:

```python
def test_next_feature_repairs_stale_route_before_dispatch(temp_dir):
    # Arrange parent active_routes with missing worktree.
    # Act: run next_feature(output_json=True).
    # Assert: stale route is removed and next child dispatch still succeeds.


def test_next_feature_continues_on_optional_planning_warn_with_audit(temp_dir):
    # Arrange required planning refs present and optional refs missing.
    # Act: run next_feature(output_json=True).
    # Assert: returns feature instead of blocking and writes an audit update.


def test_next_feature_blocks_on_red_entropy(temp_dir):
    # Arrange tracked source deletion.
    # Act: run next_feature(output_json=True).
    # Assert: returns blocked with reason workspace_entropy_red.
```

- [ ] **Step 2: Implement safe preflight hook**

Before planning gate and work-item selection in `next_feature`, call:

```python
preflight = workspace_entropy.run_safe_entropy_preflight(project_root=find_project_root())
if preflight.has_red_blocks:
    return _emit_entropy_block(preflight, output_json=output_json)
```

Green actions may run automatically. Yellow actions should report and continue only when they are non-mutating or explicitly reversible.

- [ ] **Step 3: Convert optional planning warn to auditable continue**

When required lanes are present and only optional lanes are missing, write an update:

```text
category=status
source=prog_update
summary=Optional planning lanes skipped for /prog next
refs=planning:optional_ack
```

Then continue. Do not do this for `planning_missing`.

- [ ] **Step 4: Verify next-feature tests**

Run: `uv run pytest tests/test_next_feature_entropy_preflight.py -q`

Expected: pass.

### Task 5: Add Audit Report and Change Record

**Files:**
- Modify: `hooks/scripts/workspace_entropy.py`
- Modify: `docs/progress-tracker/architecture/progress-manager-module-map.md`
- Create: `docs/changes/YYYYMMDD-workspace-entropy-manager.md`
- Modify: `docs/changes/index.jsonl`

- [ ] **Step 1: Persist action summaries**

Every `entropy-fix` mutation writes a compact summary to stdout JSON and a progress update when a tracker state file is available:

```json
{
  "category": "status",
  "source": "prog_update",
  "summary": "Workspace entropy safe-fix applied",
  "refs": ["entropy:safe_fix", "command:entropy-fix"]
}
```

- [ ] **Step 2: Update module map**

Add a row:

```markdown
| Workspace entropy | `workspace_entropy.py` | Extracted command owner | `progress_manager.py` keeps CLI wrappers only. |
```

- [ ] **Step 3: Add change record**

Create `docs/changes/YYYYMMDD-workspace-entropy-manager.md` with:

- shipped commands
- safe/yellow/red policy
- test commands and results
- rollback strategy: revert the F25 commit and remove `entropy-*` parser entries

Append matching JSONL to `docs/changes/index.jsonl`.

- [ ] **Step 4: Run required checks**

Run:

```bash
scripts/check_pm_boundary.sh
python3 hooks/scripts/generate_prog_docs.py --check
uv run pytest tests/test_workspace_entropy.py tests/test_next_feature_entropy_preflight.py -q
uv run pytest tests -q
```

Expected: required checks pass and full regression passes.

## Acceptance Criteria

- `prog entropy-check --json` returns a deterministic report covering dirty changes, branches, worktrees, routes, and recommended actions.
- `prog entropy-fix --safe --json` applies only green actions and is idempotent.
- Local branches are auto-deleted only when already merged into the default branch, not protected, and not attached to any worktree.
- Tracker state changes can be auto-committed only through the existing whitelisted state-file path.
- Ambiguous edits are stashed or quarantined only under an explicit reversible yellow decision; they are never discarded.
- Red decisions block with actionable recovery text and JSON `reason=workspace_entropy_red`.
- `next_feature` runs safe entropy preflight before stopping the workflow and no longer terminates on stale route or optional planning warnings.
- Required planning evidence is never fabricated; `planning_missing` remains fail-closed.
- `scripts/check_pm_boundary.sh` and `python3 hooks/scripts/generate_prog_docs.py --check` pass.
- Focused entropy tests and full progress-tracker tests pass.

## Rollback Strategy

Revert the F25 implementation commit. If a safe-fix command created audit updates or state-sync commits, keep them unless they point to incorrect state; otherwise revert only the code/docs commit and leave the audit trail intact.
