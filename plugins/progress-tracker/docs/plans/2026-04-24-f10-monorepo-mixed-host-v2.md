# F10 Monorepo Mixed Host v2 Implementation Plan

> **For agentic workers:** This is the canonical execution plan. Do not implement from the two source notes directly; they are retained only as historical inputs.

**Goal:** Make the repository root a Progress Tracker mixed host: root `/prog` shows a monorepo dashboard, root `/prog next-feature` routes work across root-level and child-plugin features, and child status is aggregated without copying full child `progress.json` files into the parent.

**Architecture:** Use Pull for dashboard display and Push only for coordination. Child `status_summary.v1.json` files are the primary display source; parent `routing_queue` controls where `/prog next-feature` goes; parent `active_routes` remains the concurrency lock; parent `linked_snapshot` is degraded to fallback display data only.

**Tech Stack:** Python 3, argparse, pytest, existing `progress_manager.py` and `prog_paths.py` infrastructure.

**Plan path:** `docs/plans/2026-04-24-f10-monorepo-mixed-host-v2.md`

**Working directory for all commands:** `/Users/siunin/Projects/Claude-Plugins`

## Source Notes

This document supersedes:

- `/Users/siunin/.claude/plans/jolly-tumbling-hollerith.md`
- `/Users/siunin/.claude/plans/ancient-petting-meadow.md`

The older notes explain the original architecture and first-pass implementation plan. This v2 plan folds in the review findings and is intended to be sufficient on its own for implementation.

## Current State

- Step 0 is already complete: F10 has been registered and moved to the front of `plugins/progress-tracker/docs/progress-tracker/state/progress.json`.
- Do not run the old `prog add-feature` command again.
- The implementation target remains the `progress-tracker` plugin project root: `/Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker`.
- The workflow-compatible plan path is relative to that project root: `docs/plans/2026-04-24-f10-monorepo-mixed-host-v2.md`.

## Goals

- Allow `prog` and `/prog` from `/Users/siunin/Projects/Claude-Plugins` without ambiguous monorepo failure.
- Allow root `prog init` to create a parent tracker with root-level features.
- Auto-discover initialized child trackers under `plugins/`.
- Display a root dashboard by reading child `status_summary.v1.json` projections.
- Route root `prog next-feature` through an explicit queue that can include root-level work.
- Keep route coordination data in the parent while avoiding display-time writes to parent `progress.json`.
- Provide queue-management commands that an AI worker can use safely.
- Update the progress-status skill so future `/prog` output follows the mixed-host model.

## Scope Boundaries

In scope:

- `plugins/progress-tracker/hooks/scripts/prog_paths.py`
- `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- `plugins/progress-tracker/skills/progress-status/SKILL.md`
- Focused tests under `plugins/progress-tracker/tests/`

Out of scope:

- Rewriting the feature lifecycle model.
- Replacing RouteV1 `active_routes`.
- Creating a background watcher or daemon.
- Reading all child `progress.json` files for root dashboard rendering.
- Changing non-progress-tracker plugins unless test fixtures require temporary directories.

## Interface Contracts

- `ROOT_ROUTE_CODE = "ROOT"` is the only supported root queue token.
- `ROOT_ROUTE_CODE` must be treated as a first-class queue entry, not as a linked child project.
- Parent dashboard display order is:
  1. child `status_summary.v1.json` via `load_status_summary_projection(str(child_root))`
  2. parent `linked_snapshot` fallback
  3. visible `unreachable` / `-- not initialized --` status
- Parent `linked_snapshot` must not be the primary dashboard source.
- Parent `prog next-feature` must not silently fall back to root features outside `routing_queue`.
- Non-parent trackers must keep the existing `get_next_feature()` behavior.
- Child discovery must be idempotent and must preserve existing user queue order where possible.
- Existing parent `progress.json` must not be overwritten by root `prog init` unless `--force` is explicit and existing archive behavior is preserved.
- Queue validation must allow `ROOT_ROUTE_CODE` even though it is not present in `linked_projects`.
- Unknown child codes in `routing_queue` must not block dispatch; warn, skip the stale entry, and continue scanning the queue.

## State Flow

Root status flow:

1. Load root parent `progress.json`.
2. Read root features from the parent payload.
3. Call `_discover_plugin_catalog(repo_root, parent_root)` (read-only) to get the two-tier plugin list.
4. For each **initialized** plugin (has tracker), call `load_status_summary_projection(str(child_root))`.
5. If summary loading fails, read matching fallback data from `linked_snapshot`.
6. For each **uninitialized** plugin (no tracker), render `-- not initialized --` directly without any file writes.
7. Render root features, child rows, active route, and queue.

Root next-feature flow:

1. Load root parent `progress.json`.
2. Normalize `routing_queue`.
3. Scan queue in order.
4. If entry is `ROOT`, return the next root-level feature.
5. If entry is a child code, skip it when there is a non-stale active route conflict.
6. Return the first child pending feature with a `cd plugins/<name> && prog next` instruction.
7. If no entry is actionable, return a clear no-action/configuration message.

Child update flow:

1. Child mutating commands update child `progress.json`.
2. Child `status_summary.v1.json` is refreshed best-effort.
3. `_notify_parent_sync()` may refresh parent `linked_snapshot` for fallback and route-related metadata.
4. Root dashboard still pulls fresh child summary on demand.

## Failure Handling

- Missing child summary: rebuild through `load_status_summary_projection(str(child_root))`.
- Corrupt child summary: rely on the existing loader self-healing path; if it still fails, fallback to snapshot.
- Child without `progress.json`: display `-- not initialized --`; do not create child files from dashboard rendering.
- Duplicate fallback project code: generate a deterministic unique code and emit a warning.
- Unknown child code in queue: report as conflict unless it is `ROOT_ROUTE_CODE`.
- Unknown child code during dispatch: emit `[WARN] Code "<CODE>" not found in linked_projects, skipping` and continue scanning.
- Empty parent queue: normalize to at least `["ROOT"]` plus known child codes when safe; otherwise report that queue setup is required.
- `_notify_parent_sync()` summary refresh failure: log at `debug` or `warning`, but do not break the child command.

## Key Architectural Decisions

### ADR-001: Root Tracker Role Is Mixed Host

**Status:** Accepted

**Decision:** A root tracker can own root-level features and aggregate child tracker status.

**Consequence:** Root `progress.json` stores root features plus child references, not copied child feature lists.

> **Q4 Evolution Note:** ADR-001 extends the Q4 decision that "parent stores only metadata." Root `progress.json` now stores (1) root-level features that participate in `routing_queue` via `ROOT_ROUTE_CODE`, and (2) child plugin reference metadata. It does **not** store copies of child plugin feature lists. Root-level features are reserved for cross-project work: monorepo infrastructure changes, multi-plugin coordination tasks, and repository-wide concerns.

### ADR-002: Pull Display, Push Coordination

**Status:** Accepted

**Decision:** Dashboard rendering pulls child summaries. Push writes are limited to route coordination and fallback snapshots.

**Consequence:** Root dashboard remains accurate without frequent parent writes and without increasing merge-conflict pressure.

### ADR-003: ROOT Is an Explicit Queue Entry

**Status:** Accepted

**Decision:** Root-level work participates in `routing_queue` through `ROOT_ROUTE_CODE`.

**Consequence:** There is no implicit fallback ordering for parent trackers. Queue order is the source of truth.

### ADR-004: Discovery Is Refreshable and Idempotent

**Status:** Accepted

**Decision:** Initial root `prog init` discovers child trackers, and a separate refresh path can discover later-added children.

**Consequence:** Existing queues and links are preserved instead of being overwritten during repeated discovery.

## Execution Constraints

- [CONSTRAINT-001] Root path resolution is explicit.
  - Applies to: `prog_paths.py`
  - Must: Return `(repo_root, repo_root)` when CWD is exactly repo root and `plugins/` exists.
  - Validation: Test `resolve_target_project_root(cwd=repo_root)` accepts repo root.

- [CONSTRAINT-002] Parent init is non-destructive.
  - Applies to: `init_tracking()`
  - Must: Existing root `progress.json` is not overwritten without `--force`.
  - Validation: Test repeated root init returns false and preserves data.

- [CONSTRAINT-003] ROOT is a constant.
  - Applies to: route queue handling
  - Must: Use `ROOT_ROUTE_CODE`, not scattered string literals.
  - Validation: Search code for direct `"ROOT"` route comparisons outside the constant definition and tests.

- [CONSTRAINT-004] Dashboard reads summaries through the projection loader.
  - Applies to: `_display_root_dashboard()`
  - Must: Use `load_status_summary_projection(str(child_root))` before snapshot fallback.
  - Validation: Corrupt summary test still renders dashboard.

- [CONSTRAINT-005] Parent routing is queue-only.
  - Applies to: `next_feature()`, `_get_dispatched_child_feature()`
  - Must: Parent trackers do not use implicit `get_next_feature()` fallback after child dispatch fails.
  - Validation: Test a parent without `ROOT` in queue does not return root features silently.

- [CONSTRAINT-006] Route validation allows ROOT.
  - Applies to: `route_status()`, queue commands
  - Must: `ROOT_ROUTE_CODE` is valid even though absent from `linked_projects`.
  - Validation: `route-status` with `["ROOT"]` has no Type B conflict.

- [CONSTRAINT-007] Discovery preserves user priority.
  - Applies to: `_auto_discover_child_plugins()` and refresh command
  - Must: Existing queue order is preserved; new codes are appended unless the queue is empty.
  - Validation: Test existing queue `["PT", "ROOT"]` remains in that order after discovery.

- [CONSTRAINT-008] Unknown queue codes are dispatch warnings, not blockers.
  - Applies to: `_get_dispatched_child_feature()`
  - Must: Unknown non-ROOT codes are skipped with a warning and do not prevent later queue entries from being dispatched.
  - Validation: Test queue `["GHOST", "ROOT"]` warns for `GHOST` and returns the root feature.

## File Map

| File | Change |
|------|--------|
| `plugins/progress-tracker/hooks/scripts/prog_paths.py` | Allow repo root as a valid tracker scope |
| `plugins/progress-tracker/hooks/scripts/progress_manager.py` | Add root role support, child discovery, dashboard, ROOT dispatch, queue commands, summary freshness |
| `plugins/progress-tracker/skills/progress-status/SKILL.md` | Add Root Dashboard Mode guidance |
| `plugins/progress-tracker/tests/test_monorepo_root_init.py` | New tests for path resolution and parent init |
| `plugins/progress-tracker/tests/test_auto_discover_child_plugins.py` | New tests for discovery, code generation, queue preservation |
| `plugins/progress-tracker/tests/test_root_dashboard.py` | New tests for summary pull, fallback, corrupt summary |
| `plugins/progress-tracker/tests/test_dispatch_child_feature.py` | Extend tests for ROOT queue behavior |
| `plugins/progress-tracker/tests/test_routing_queue_commands.py` | New tests for prioritize and set-queue |
| Existing route-status tests if present | Extend Type B conflict logic to allow ROOT |

## Code Landmarks

- `prog_paths.py`
  - `resolve_target_project_root()` definition: line 104
  - insertion point: before the `if (repo_root / "plugins").is_dir():` ambiguous-monorepo block near line 153
- `progress_manager.py`
  - linked schema normalization: `_normalize_linked_schema()` near line 800
  - route schema normalization: `_normalize_route_schema()` near line 829
  - `_notify_parent_sync()` definition: line 1231
  - `link_project()` definition: line 1278
  - `init_tracking()` definition: line 4013
  - `status()` definition: line 4106
  - `load_status_summary_projection()` definition: line 3836
  - `_get_dispatched_child_feature()` definition: line 5298
  - `next_feature()` definition: line 5374

Line numbers are orientation aids. Prefer function names when editing.

## v2 Patches Applied (2026-04-25)

Three issues identified in conditional-pass review; patched inline below:

1. **Root wrapper (Task 0):** Root `/prog` does not exist; a wrapper that forwards to `plugins/progress-tracker/prog` with auto-injected `--project-root` is required before all other tasks.
2. **KNOWN_PLUGIN_CODES removed (Task 3):** Hardcoded dict replaced with `_derive_plugin_code()` + `.claude-plugin/plugin.json` scan path. Discovering an initialized child must also write back `tracker_role/project_code/parent_project_root` to the child tracker so child mutating preflight does not reject it.
3. **Q4 regression test explicit (Task 5):** `features=[]` in parent is not a constraint, it is a deliberate Q4 decision. Corresponding test for CONSTRAINT-005 made explicit: parent with `features=[]` and no `ROOT` in queue must not silently return root features.

---

## Tasks

### Task Dependencies

Implement in this order:

```text
Task 0 -> Task 1 -> Task 2 -> Task 3 -> {Task 4, Task 5, Task 6, Task 7} -> Task 8 -> Task 9
```

Task 2 establishes root parent identity only. Task 3 implements child discovery and then wires the `init_tracking()` discovery call after the helper exists.

### Task 0: Root `prog` Wrapper Script

**Files:**

- Create: `/Users/siunin/Projects/Claude-Plugins/prog`

**Context:** Repo root has no `prog` executable. Without it, acceptance criteria "在仓库根目录运行 prog init" cannot be met. The wrapper must mirror the existing `plugins/progress-tracker/prog` parameter-normalization model (project-root forwarding + `memory` routing).

- [ ] Confirm root has no `prog`: `ls /Users/siunin/Projects/Claude-Plugins/prog 2>/dev/null || echo "confirmed absent"`.
- [ ] Create `/Users/siunin/Projects/Claude-Plugins/prog` with this content:

```bash
#!/usr/bin/env bash
# Root-level prog wrapper for monorepo parent usage.
# Forwards all arguments to the progress-tracker CLI.
# Auto-injects --project-root <repo_root> ONLY when caller has not already
# passed --project-root; explicit child scope is always preserved.
# Memory routing: delegates to project_memory.py when first non-global arg is "memory".
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PT_PROG="$SCRIPT_DIR/plugins/progress-tracker/prog"

if [[ ! -x "$PT_PROG" ]]; then
  echo "Error: progress-tracker prog not found at $PT_PROG" >&2
  exit 1
fi

# Scan for explicit --project-root to avoid double-injection
HAS_PROJECT_ROOT=0
for arg in "$@"; do
  case "$arg" in
    --project-root|--project-root=*) HAS_PROJECT_ROOT=1; break ;;
  esac
done

if [[ "$HAS_PROJECT_ROOT" -eq 0 ]]; then
  exec "$PT_PROG" --project-root "$SCRIPT_DIR" "$@"
else
  exec "$PT_PROG" "$@"
fi
```

- [ ] `chmod +x /Users/siunin/Projects/Claude-Plugins/prog`.
- [ ] Verify: `/Users/siunin/Projects/Claude-Plugins/prog --help 2>&1 | head -3` shows Progress Tracker help text.
- [ ] Verify memory routing: `/Users/siunin/Projects/Claude-Plugins/prog memory read 2>&1 | head -3` does not error with "unknown command".
- [ ] Verify `--project-root` pass-through: `/Users/siunin/Projects/Claude-Plugins/prog --project-root plugins/progress-tracker status` does not inject a second `--project-root`.
- [ ] Add one wrapper test in `test_monorepo_root_init.py`:
  - Test that invoking the wrapper without `--project-root` injects `SCRIPT_DIR` automatically.
  - Test that invoking with explicit `--project-root plugins/progress-tracker` keeps it unchanged.
- [ ] Commit the wrapper and tests.

### Task 1: Allow Repo Root Path Resolution

**Files:**

- Modify: `plugins/progress-tracker/hooks/scripts/prog_paths.py`
- Add tests: `plugins/progress-tracker/tests/test_monorepo_root_init.py`

- [ ] Add a failing test where a fake git repo contains `plugins/` and CWD is the repo root.
- [ ] Update `resolve_target_project_root()` so exact repo root returns `(repo_root, repo_root)` before the ambiguous monorepo branch.
- [ ] Keep CWD under repo root but outside `plugins/` ambiguous, for example `repo_root/scripts`.
- [ ] Keep worktree plugin inference unchanged for non-root CWD.
- [ ] Run the new path-resolution tests.

### Task 2: Add Parent Init Without Overwrite

**Files:**

- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Extend tests: `plugins/progress-tracker/tests/test_monorepo_root_init.py`

- [ ] Define `ROOT_ROUTE_CODE = "ROOT"` near route constants.
- [ ] In `init_tracking()`, detect target roots with a `plugins/` directory.
- [ ] For new root tracker data, set `tracker_role = "parent"` and `project_code = ROOT_ROUTE_CODE`.
- [ ] Initialize root `routing_queue` to `[ROOT_ROUTE_CODE]` before discovery exists.
- [ ] Ensure repeated init without `--force` preserves existing data and returns the current already-exists behavior.
- [ ] Preserve existing `--force` archive behavior.
- [ ] Do not call child discovery in this task; Task 3 wires discovery after the helper is implemented.
- [ ] Run root init tests.

### Task 3: Extract Link Core and Add Child Discovery

**Files:**

- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Add tests: `plugins/progress-tracker/tests/test_auto_discover_child_plugins.py`

- [ ] Extract the reusable registration portion of `link_project()` into `_link_child_to_parent(parent_data, parent_root, repo_root, child_root, code, label=None, append_to_queue=True)`.
- [ ] Keep public `link_project()` behavior and output compatible.
- [ ] **No KNOWN_PLUGIN_CODES dict.** (Patch: removed hardcoded mapping that required source edits for every new plugin.)
- [ ] Add `_derive_plugin_code(plugin_name: str) -> str`:
  - Input: plugin `name` field from `.claude-plugin/plugin.json` (e.g. `"note-organizer"`, `"super-product-manager"`).
  - Algorithm: take the first letter of each hyphen/underscore-separated segment, uppercase. `"note-organizer"` → `"NO"`, `"super-product-manager"` → `"SPM"`, `"progress-tracker"` → `"PT"`.
  - Truncate to 8 chars maximum.
- [ ] Add `_generate_project_code(plugin_name, used_codes)` wrapping `_derive_plugin_code` with collision handling: if the derived code is in `used_codes`, append numeric suffix `2`, `3`, ... up to 8-char max. Emit a warning when a suffix is applied.
- [ ] Add `_discover_plugin_catalog(repo_root, parent_root) -> dict`:
  - **Pure read-only.** Never writes to parent or child trackers, never calls `ensure_tracker_layout`, never registers links.
  - Scan path: `repo_root/plugins/*/.claude-plugin/plugin.json`.
  - Skip the parent root itself.
  - Returns `{"initialized": [...], "uninitialized": [...]}` where each entry has `{"name": str, "root": Path, "plugin_json": dict}`.
  - `initialized`: directories that additionally have `docs/progress-tracker/state/progress.json`.
  - `uninitialized`: directories with `.claude-plugin/plugin.json` but no tracker file.
  - Dashboard **must only** call this function for the uninitialized plugin list — never `_auto_discover_child_plugins()` at display time.
- [ ] Add `_auto_discover_child_plugins(project_root, repo_root, parent_data)`:
  - Calls `_discover_plugin_catalog(repo_root, parent_root=project_root)` internally to get the two-tier list.
  - **Code resolution priority for each initialized child:**
    1. If child's `progress.json` already contains a non-empty `project_code` field → use it directly (preserves previously assigned codes, avoids drift).
    2. Otherwise → derive with `_generate_project_code(plugin_name, used_codes)` and write back to child.
  - Registers initialized children idempotently using the resolved code; call `_link_child_to_parent`.
  - **Write back to child:** after registering in parent, write `tracker_role="child"`, `project_code=<resolved_code>`, and `parent_project_root=<parent_root>` to each initialized child's `progress.json` (use the same fields that `link_project()` writes at line 1398). This ensures child mutating preflight (`enforce_route_preflight`) accepts the child later.
  - Preserve existing queue order; append newly discovered codes.
  - Initialize empty queue as `[ROOT_ROUTE_CODE] + sorted(initialized_codes)`.
  - Returns `{"added_codes": [...], "uninitialized_plugins": [...], "warnings": [...], "final_queue": [...]}` for `--json` output.
- [ ] Add warning output or structured warning data when fallback code generation or writeback fails.
- [ ] Wire `init_tracking()` to call `_auto_discover_child_plugins()` only after the helper exists and after the parent base data has been constructed.
- [ ] Add a refresh command `prog discover-children`:
  - Runs `_auto_discover_child_plugins()` against the current parent tracker.
  - Only runs from a parent tracker; returns an error without writing from non-parent.
  - Is a mutating command; register in `MUTATING_COMMANDS`.
  - Supports `--json` output with: `discovered_codes`, `added_codes`, `uninitialized_plugins`, `warnings`, `final_queue`.
- [ ] `init --force` on a root parent tracker must run discovery after new parent payload is created.
- [ ] Add tests:
  - `_derive_plugin_code("note-organizer")` → `"NO"`, `_derive_plugin_code("super-product-manager")` → `"SPM"`.
  - Discovery with three plugins: two initialized, one (`package-manager`) uninitialized — confirm only two appear in `linked_projects/routing_queue`, and `package-manager` is in `uninitialized_plugins`.
  - Discovery writes back `tracker_role=child`, `project_code`, `parent_project_root` to each initialized child tracker.
  - Repeated discovery with existing `["PT", "ROOT"]` queue preserves order and appends newly found `NO`.
- [ ] Run discovery tests.

### Task 4: Add Root Dashboard Pull Aggregation

**Files:**

- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Add tests: `plugins/progress-tracker/tests/test_root_dashboard.py`

- [ ] Add `_display_root_dashboard(data, project_root, repo_root, output_json=False)`.
- [ ] In `status()`, when `tracker_role == "parent"`, call root dashboard and return.
- [ ] Read child summaries via `load_status_summary_projection(str(child_root))`.
- [ ] If the loader raises, fallback to the matching child entry in `linked_snapshot`.
- [ ] If child progress data is absent, show `-- not initialized --`. The `-- not initialized --` row must come from `plugin_catalog` (all plugins with `.claude-plugin/plugin.json`), not from `linked_projects`. Specifically: do not call `load_status_summary_projection()` for uninitialized plugins — that function calls `ensure_tracker_layout()` which would create directories in the uninitialized child (line 4253). Read the uninitialized plugin list by calling `_discover_plugin_catalog(repo_root, parent_root)` (read-only, no registration side-effects). **Never call `_auto_discover_child_plugins()` from dashboard display code.**
- [ ] Render root feature progress separately from child summaries.
- [ ] Render active route and queue using `ROOT_ROUTE_CODE`.
- [ ] Text dashboard output must follow this shape so AI workers can parse queue and active route context consistently:

```text
## Monorepo Dashboard

| Code | Plugin           | Done  | Pct  | Next Action    |
|------|------------------|-------|------|----------------|
| NO   | note-organizer   | 10/10 | 100% | (complete)     |
| PT   | progress-tracker | 1/11  | 9%   | Event Sourcing |

Root Features: 1/1 pending
  [ ] 根目录混合宿主架构

Active Route: none  |  Queue: ROOT -> PT -> NO -> SPM
```

- [ ] `_display_root_dashboard()` must support `output_json=True` consistent with existing status behavior.
- [ ] Add corrupt summary coverage by writing invalid JSON and confirming dashboard still renders.
- [ ] Run dashboard tests.

### Task 5: Make ROOT a First-Class Dispatch Target

**Files:**

- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Extend tests: `plugins/progress-tracker/tests/test_dispatch_child_feature.py`

- [ ] Update `_get_dispatched_child_feature()` to scan queue entries in order.
- [ ] When entry is `ROOT_ROUTE_CODE`, return a root-level pending feature from parent data.
- [ ] Ensure root entries are not checked against child `linked_projects`.
- [ ] Ensure `active_routes` conflicts apply only to child project codes.
- [ ] When a queue entry is an unknown non-ROOT code, emit `[WARN] Code "<CODE>" not found in linked_projects, skipping` and continue to the next queue entry.
- [ ] Include route position in returned payload.
- [ ] Update text output:
  - child: `[NEXT] Dispatching to [PT] (routing_queue position 2):`
  - root: `[NEXT] Root-level feature (routing_queue position 1):`
- [ ] Remove parent-only implicit fallback after dispatch failure. **Risk:** once `tracker_role="parent"` is set by root init, the `if data.get("tracker_role") == "parent"` branch at line 5852 will activate, and the implicit `pass  # Fall through to parent's own features` at **lines 5875-5877** will route into `get_next_feature()` — violating CONSTRAINT-005. Change lines 5875-5877 from `pass` to an explicit no-action return (e.g. return `False` or a structured no-action message) for parent trackers. Non-parent fallback at this location must remain unchanged.
- [ ] Keep non-parent `next_feature()` fallback unchanged.
- [ ] Add tests for:
  - `["ROOT", "PT"]` returns root feature first
  - `["PT", "ROOT"]` returns child first if child has work
  - active child route causes scanner to continue to `ROOT`
  - unknown code before `ROOT` warns and dispatches `ROOT`
  - queue without `ROOT` does not silently return root features (CONSTRAINT-005 Q4 regression guard): parent with `features=["some root feature"]` and `routing_queue=["PT"]` (no ROOT) must not return the root feature — it must return the child PT feature or nothing.
  - parent with `features=[]` (empty, Q4 decision) and `routing_queue=["PT"]` dispatches to PT correctly and never falls through to parent feature list.
- [ ] Run dispatch tests.

### Task 6: Add Queue Management Commands

**Files:**

- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Add tests: `plugins/progress-tracker/tests/test_routing_queue_commands.py`

- [ ] Add `prioritize_route(code, output_json=False)`:
  - validates code is `ROOT_ROUTE_CODE` or an existing linked child code
  - moves exactly one code to the front
  - errors if code is absent from current queue
- [ ] Add `set_routing_queue(codes, force=False, output_json=False)`:
  - validates every code is `ROOT_ROUTE_CODE` or an existing linked child code
  - requires all existing queue codes unless `--force`
  - preserves given order exactly
- [ ] Register CLI commands:
  - `prog prioritize <code>`
  - `prog set-queue <code1> <code2> ... [--force]`
- [ ] Add mutating command registration if the command framework requires it.
- [ ] Update queue conflict logic so `ROOT_ROUTE_CODE` is never Type B. Use the exclusion approach at the existing Type B loop (near line 1610): `if code and code != ROOT_ROUTE_CODE and code not in linked_codes:`. Do **not** inject `ROOT_ROUTE_CODE` into `linked_codes` as a workaround — use the exclusion test directly.
- [ ] Run queue command tests and existing route command tests.

### Task 7: Keep Summary Fresh Without Silent Failure

**Files:**

- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Add tests: `plugins/progress-tracker/tests/test_summary_writeback.py`

- [ ] In `_notify_parent_sync()`, after determining `child_root`, call `load_status_summary_projection(str(child_root))` best-effort.
- [ ] Catch exceptions and log with `logger.debug()` or `logger.warning()`.
- [ ] Do not print warnings during JSON-output command paths unless existing behavior already prints warning-only text.
- [ ] Preserve existing parent `linked_snapshot` writeback behavior.
- [ ] Add a test that a child mutation path attempts summary refresh.
- [ ] Add a test that summary refresh failure does not abort the child operation.

### Task 8: Document Feature Ownership and Root Dashboard Mode

**Files:**

- Modify: `plugins/progress-tracker/skills/progress-status/SKILL.md`

- [ ] Add a Root Dashboard Mode section.
- [ ] State that root-level features are for repo-level work or changes touching two or more plugin directories.
- [ ] State child plugin features should stay in the child tracker.
- [ ] State dashboard rendering should read child summaries, not full child `progress.json`.
- [ ] Include expected handoff behavior for root dashboard and root next-feature output.

### Task 9: Final Regression and Validation

**Files:**

- No source edits unless failures identify a scoped issue.

- [ ] Run focused tests added in this plan.
- [ ] Run route-related existing tests.
- [ ] Run `pytest -q plugins/progress-tracker/tests/`.
- [ ] Before implementation begins, validate this plan path from the `plugins/progress-tracker` project root and confirm it passes:
  `./prog validate-plan --plan-path docs/plans/2026-04-24-f10-monorepo-mixed-host-v2.md`.
- [ ] After implementation, run the same plan validation command again to confirm the plan remains workflow-compatible.
- [ ] Manually verify root command behavior:
  - `prog init "Claude-Plugins Monorepo"` at repo root creates parent tracker only when no root tracker exists.
  - `prog` at repo root shows Monorepo Dashboard.
  - `prog next-feature` at repo root follows `routing_queue`.
  - `prog prioritize PT` moves PT to the front.
  - `prog set-queue PT ROOT NO SPM` sets full queue.
  - Adding a child feature is reflected by root dashboard without a sync command.
  - Corrupting or deleting child `status_summary.v1.json` does not crash root dashboard.

## Acceptance Criteria Mapping

| Requirement | Acceptance Criteria | Tests |
|-------------|---------------------|-------|
| Root `/prog` is allowed | Repo root resolves as target root when CWD is exactly repo root | `test_monorepo_root_init.py` |
| Existing root data is safe | Repeated init without force does not overwrite | `test_monorepo_root_init.py` |
| Parent tracker identity exists | Root init writes `tracker_role=parent`, `project_code=ROOT` | `test_monorepo_root_init.py` |
| Child discovery works | Initialized child trackers are linked and queued | `test_auto_discover_child_plugins.py` |
| Discovery is idempotent | Existing links and queue order are preserved | `test_auto_discover_child_plugins.py` |
| Code fallback is observable | Unknown plugin code generation emits warning and avoids collisions | `test_auto_discover_child_plugins.py` |
| Dashboard is Pull-based | Child summary loader is used before snapshot fallback | `test_root_dashboard.py` |
| Corrupt summary is safe | Invalid summary JSON does not crash root dashboard | `test_root_dashboard.py` |
| ROOT dispatch works | `ROOT` queue entry returns root feature at its position | `test_dispatch_child_feature.py` |
| Stale queue entries do not block dispatch | Unknown non-ROOT queue code warns and is skipped | `test_dispatch_child_feature.py` |
| Parent fallback is explicit | Parent without `ROOT` does not silently return root feature | `test_dispatch_child_feature.py` |
| Queue commands are safe | `prioritize` and `set-queue` validate codes and preserve required entries | `test_routing_queue_commands.py` |
| Route validation supports ROOT | `route-status` does not flag `ROOT` as unlinked | route command tests |
| Child summary freshness is best-effort | Refresh failure is logged but child command succeeds | root dashboard/writeback tests |
| Skill guidance is updated | `progress-status/SKILL.md` documents Root Dashboard Mode | documentation review |
| Uninitialized plugin is visible | `package-manager` row shows `-- not initialized --` and no tracker directory is created | `test_root_dashboard.py` |
| Code derivation is written back to child | After discovery, child tracker has `tracker_role=child`, `project_code=<code>`, `parent_project_root` | `test_auto_discover_child_plugins.py` |
| Route validation supports ROOT without linked_projects entry | `route-status` with `["ROOT"]` in queue reports zero Type B conflicts | route command tests |
| Root wrapper forwards correctly | `./prog status` at repo root uses repo root as project root; `./prog --project-root plugins/progress-tracker status` uses plugin root | `test_monorepo_root_init.py` |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Parent init overwrites real root tracker data | Data loss | Keep existing no-force behavior; add tests |
| `ROOT` remains a scattered magic string | Inconsistent queue behavior | Centralize `ROOT_ROUTE_CODE`; test route-status and dispatch |
| Queue empty or missing ROOT causes confusing next-feature output | AI may choose wrong work | Normalize safe cases and emit explicit configuration message |
| Dashboard reads full child progress files | Token and performance regression | Require summary projection loader in dashboard tests |
| Corrupt summary crashes dashboard | Root `/prog` becomes unreliable | Use `load_status_summary_projection()` and fallback snapshot |
| Fallback plugin code collisions | Wrong child dispatch | Deterministic unique fallback plus warning |
| Summary refresh warning pollutes JSON output | Broken automation | Use logger for best-effort failures |
| Refactoring `link_project()` changes existing behavior | RouteV1 regression | Keep public behavior tests and run existing route/link tests |

## Verification Commands

Run from `/Users/siunin/Projects/Claude-Plugins` unless noted.

```bash
pytest -q plugins/progress-tracker/tests/test_monorepo_root_init.py
pytest -q plugins/progress-tracker/tests/test_auto_discover_child_plugins.py
pytest -q plugins/progress-tracker/tests/test_root_dashboard.py
pytest -q plugins/progress-tracker/tests/test_dispatch_child_feature.py
pytest -q plugins/progress-tracker/tests/test_routing_queue_commands.py
pytest -q plugins/progress-tracker/tests/
```

Optional plan validation from the progress-tracker project root:

```bash
cd plugins/progress-tracker
prog validate-plan --plan-path docs/plans/2026-04-24-f10-monorepo-mixed-host-v2.md
```
