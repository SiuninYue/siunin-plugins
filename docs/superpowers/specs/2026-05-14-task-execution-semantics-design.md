# Feature 14: Task Execution Semantics and Visibility

**Date:** 2026-05-14  
**Feature:** PT-F14 — Task execution semantics and visibility (standalone task vs feature task) with profile-aware done gates  
**Status:** Approved for implementation

---

## Overview

Feature 14 introduces three distinct capabilities:

1. **Task execution lifecycle**: `prog next` activates a task (creating a short-lived branch for standalone quick_tasks), and `prog next --done` closes it via profile-aware paths (squash-merge for standalone; progress-advance for feature-bound).
2. **MUTATING_COMMANDS lock safety**: task-close path exempted from the outer `progress_transaction()` lock to avoid RC=9 / 10s timeout (BUG-002 class).
3. **Status visibility**: stale P0/P1 bug warnings, hidden-history count in `prog status`, and unfiltered `prog list-updates`.

A cross-cutting concern is also addressed: the ghost command `prog start-task` (referenced in output but undefined) is eliminated and replaced with the correct CLI API.

---

## Section 1: Data Model

### New top-level field in `progress.json`

```json
{
  "current_task_id": "TASK-001"   // string | null
}
```

**Invariants:**
- Must reference a `tasks[].id` that exists and has `status != "completed"`.
- On load, if the referenced task is missing or already completed, auto-null this field (fail-soft on read, fail-closed on `next --done`).
- Cleared to `null` whenever: task is `--done`'d, task is deleted, or parent feature is deleted.

### New optional field on `tasks[]` entries

```json
{
  "parent_feature_id": 7   // int | null
}
```

**Invariants:**
- Written by `prog add-task --feature-id <int>`.
- If `--feature-id` is omitted, value is `null` (standalone quick_task).
- `--feature-id` value must reference an existing feature; otherwise RC=1 error.
- `--feature-id` and `--workflow-profile quick_task` are mutually exclusive; passing both = RC=2 error.

### Migration compatibility

Old `progress.json` files missing either field are treated as:
- `current_task_id = null`
- `parent_feature_id = null` (all existing tasks are standalone)

### Task type discriminant

| `parent_feature_id` | Task type | Close path |
|---------------------|-----------|------------|
| `null` | Standalone quick_task | Branch creation + squash-merge |
| `<int>` | Feature-bound task | Progress-advance on parent feature only |

---

## Section 2: CLI Interface

### `prog next` — new `--done` flag

```
prog next [--json] [--ack-planning-risk] [--done]
```

- `--done`: Close the task referenced by `current_task_id`. Does **not** execute "select next work item" logic (no side effects from that path).
- `--done --json` returns a structured JSON response (minimum contract):
  ```json
  {
    "status": "ok|error",
    "closed_task_id": "TASK-001",
    "message": "..."
  }
  ```
- Missing `current_task_id`, or pointing to a non-existent/already-completed task: RC=1 + explicit repair instruction.
- When closing a feature-bound task: only advances parent feature progress; parent feature is **not** auto-closed.

### `prog add-task` — new `--feature-id` parameter

```
prog add-task --description "..." [--feature-id <int>] [--workflow-profile <profile>]
```

- `--feature-id <int>`: Writes `parent_feature_id` to the task record. Validates feature exists → RC=1 on failure.
- `--feature-id` + `--workflow-profile quick_task` together → RC=2 (mutually exclusive).
- Without `--feature-id`: `parent_feature_id = null` (standalone, unchanged existing behavior).

### `prog list-updates` — default changed to unlimited

```
prog list-updates [--limit <n>]
```

- Default: `limit=0` = full unfiltered history (parser default changed from 10 → 0).
- `--limit <n>` where `n > 0`: show at most `min(len(updates), n)` entries.
- `--limit <n>` where `n < 0`: RC=2 error.

### RC semantics (canonical, documented in PROG_COMMANDS.md)

| Condition | RC |
|-----------|----|
| Success | 0 |
| Pre-condition failure (no `current_task_id`, invalid state) | 1 |
| Parameter / command error (bad args, unknown subcommand) | 2 |

### Ghost command elimination

`prog next` output when selecting a task changes from:
```
Run: prog start-task TASK-001     ← does not exist
```
to:
```
Task selected: TASK-001
Run: prog next --done
```

`_task_item()["action"]` updated to `"prog next --done"`.

`wf_state_machine.py` line 54: `"task:pending": "start_task"` action renamed to map to `prog next` (activate) not the non-existent `prog start-task`.

### Unknown subcommand protection

On unknown subcommand, print suggestion + help + exit RC=2:
```
Error: unknown command 'start-task'
Did you mean: 'next --done'?
Run: prog next --help
```

"Did you mean" is only shown when the Levenshtein edit-distance between the unknown subcommand and the closest candidate is ≤ 2. Above 2: only `--help` is shown (no suggestion).

---

## Section 3: Internal Function Architecture

All new functions reside in `progress_manager.py`.

### CLI dispatch (lock exemption)

```python
# In main() dispatch block — before MUTATING_COMMANDS check:
if args.command == "next" and getattr(args, "done", False):
    return _close_current_task(output_json=getattr(args, "output_json", False))
```

This path bypasses `progress_transaction()` exactly as `done` and `complete` do (avoids BUG-002 class nested-lock deadlock).

### New internal functions

```python
def _close_current_task(output_json: bool = False) -> int:
    """Main dispatch for `prog next --done`.

    Pre-conditions checked (fail-closed RC=1):
    - current_task_id is not null
    - task exists in tasks[]
    - task.status != "completed"

    Dispatches by parent_feature_id:
    - null  → _close_standalone_task()
    - int   → _close_feature_bound_task()

    Clears current_task_id after successful close.
    Returns RC (0/1/2).
    """

def _close_standalone_task(task: dict, output_json: bool = False) -> int:
    """Close a standalone quick_task via squash-merge.

    Atomic ordering guarantee (fail-closed at each step):
    1. _git_squash_close_task() → all git ops succeed (squash + commit + delete branch)
    2. Only then: mark task.status = "completed"
    3. Only then: clear current_task_id, write progress.json (minimal JSON transaction)

    On any git step failure: no business state is modified.
    Does not trigger any feature done gate.
    """

def _close_feature_bound_task(task: dict, output_json: bool = False) -> int:
    """Close a feature-bound task (no git operations).

    1. Mark task.status = "completed"
    2. Parent feature "task progress" is derived dynamically — no new field added to
       the feature record. Progress = count of tasks[] with matching parent_feature_id
       and status=completed. No feature state transition occurs.
    3. Do NOT auto-close or transition parent feature state
    4. Clear current_task_id, write progress.json
    """

def _git_squash_close_task(task_id: str, branch: str, base_branch: str = "main") -> tuple[bool, str]:
    """Execute git squash-merge sequence.

    Commit message format: "task(<task_id>): close standalone task"

    Pre-conditions checked (fail-closed):
    - branch exists in local repo
    - working tree is clean

    Sequence:
    1. git checkout <base_branch>
    2. git merge --squash <branch>
    3. git commit -m "task(<task_id>): close standalone task"
    4. git branch -d <branch>

    Returns: (success: bool, value: str)
      success=True  → value = commit hash (from `git rev-parse HEAD`)
      success=False → value = human-readable error message (e.g., "working tree dirty")
    Guarantees: base_branch has exactly +1 commit on success.
    """
```

### `next_feature()` modifications (minimal)

When selecting a task with `item_type == "task"`:

```
if parent_feature_id is None:          # standalone quick_task
    git checkout -b task/<task_id>     # fail-closed: if branch fails, don't activate
    write current_task_id = task_id    # only after branch succeeds

elif parent_feature_id is not None:    # feature-bound
    write current_task_id = task_id    # no branch creation
```

`next_feature()` retains all existing logic; these are additive branches at the task dispatch point.

### `_get_stale_bugs()` helper

```python
def _get_stale_bugs(data: dict, now: datetime) -> list[dict]:
    """Return P0/P1 bugs exceeding stale threshold.

    Thresholds (strict >):
    - P0 (priority=high):   > 3 days
    - P1 (priority=medium): > 7 days

    Excluded: fixed, false_positive status.
    Time base: updated_at preferred, fallback created_at.
    Timestamps: converted to timezone-aware UTC; parse failures are skipped + logged.

    Output order: P0 first, then P1; same-priority sorted by stale_days descending.
    """
```

---

## Section 4: Status Visibility

### `status()` changes

**① Stale bug warnings block** (inserted before updates section):

```
### Bug Warnings:
  [P0] BUG-002: <description truncated> (stale 5d, last: 2026-05-09)
  [P1] BUG-003: <description truncated> (stale 9d, last: 2026-05-05)
```

Ordering: P0 before P1, same priority sorted by stale_days descending (most stale first).
Only shown when at least one stale bug exists.

**② Hidden-history count** (appended to updates block):

```
### Recent Updates (showing 5/12):
  [UPD-008] ...
  [UPD-009] ...
  +7 more updates (run: prog list-updates)
```

- `updates` list sorted ascending by `created_at` (ISO string sort) before slicing `[-5:]`.
- "+N more" line only shown when `len(updates) > 5`; N = `len(updates) - 5`.

### `list_updates()` changes

- `limit=0` → outputs all updates (parser default changed to 0).
- `limit > 0` → `safe_limit = min(len(updates), limit)`.
- `limit < 0` → RC=2 error, no output.

---

## Section 5: AI Command Hygiene

### PROG_COMMANDS.md (new reference document)

Path: `plugins/progress-tracker/docs/reference/PROG_COMMANDS.md`

Contents:
- Whitelist of all valid `prog` subcommands with signatures
- RC semantics table (RC=0/1/2)
- Explicit note: `prog start-task` does NOT exist; use `prog next --done`

### Skill layer constraints

Added to relevant skill files (`prog-next`, `feature-implement`):
- Check `prog <subcmd> --help` before first use of any unfamiliar subcommand.
- Only use commands from PROG_COMMANDS.md whitelist.
- On RC=2 error: read stderr suggestion, do NOT retry original command.

---

## Section 6: Test Coverage

File: `plugins/progress-tracker/tests/test_task_execution_semantics.py`

| Test | Assertion |
|------|-----------|
| `prog next` selects quick_task | branch `task/TASK-001` created; `current_task_id` written |
| `prog next --done` on standalone | squash-merge succeeds; branch deleted; main +1 commit; no feature done gate |
| `prog next --done` on feature-bound | task completed; parent feature progress +1; parent feature status unchanged |
| MUTATING_COMMANDS lock | `next --done` does not hold outer lock (RC≠9, no timeout) |
| `prog status` stale P0 | bug >3d shown with stale_days; terminal-status bug not shown |
| `prog status` stale P1 | bug >7d shown; >3d but P1 not shown (threshold respects `>` not `>=`) |
| `prog status` hidden-history | 12 updates → "+7 more" line present |
| `prog list-updates` default | no `--limit` → all updates returned |
| `prog list-updates --limit -1` | RC=2 |
| Ghost command | `prog start-task TASK-001` → RC=2 + "Did you mean: next --done" |
| "Did you mean" negative | low-similarity unknown command → only --help, no suggestion |
| `add-task --feature-id` invalid | non-existent feature → RC=1 |
| `add-task` mutually exclusive | `--feature-id` + `--workflow-profile quick_task` → RC=2 |
| `current_task_id` invalid | pointing to completed/missing task → RC=1 + repair instruction |
| Git unit test | `_git_squash_close_task` mocked; verifies call sequence |
| Git integration test | actual branch created, squash-merged, deleted; main has exactly +1 commit |

---

## Acceptance Test Steps (from Feature 14)

1. `prog next` → selects quick_task; verify `task/TASK-001` branch created automatically.
2. `prog next --done` on active quick_task → squash-merge succeeds, branch deleted, exactly 1 commit added to main; no feature done gate triggered.
3. `prog next --done` on feature-bound task → task marked complete, parent feature progress advances, parent feature NOT auto-closed.
4. `prog next --done` on quick_task → close path does not trigger MUTATING_COMMANDS outer lock (no 10s timeout / RC=9).
5. `prog status` → actionable updates shown; stale P0/P1 bugs displayed as warnings; hidden-history count shown; `prog list-updates` returns full unfiltered history.
