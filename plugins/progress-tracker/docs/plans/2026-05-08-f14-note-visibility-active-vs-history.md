# F14 Plan: `prog-note` Visibility (Active Memo vs History)

## Goal
Prevent stale memo noise in `/prog` while preserving complete historical notes for audit and recovery.

## Problem
- `/prog` currently shows the latest updates list without recency/state lifecycle filtering.
- Users who note infrequently may see old memo entries persist in primary status view.
- Status-only view can miss critical handoff details; memo visibility needs structure.

## Scope
- Define an "active memo" concept for status view.
- Keep historical notes queryable through `list-updates`.
- Improve `/prog` rendering logic so old closed notes do not dominate primary output.

## Non-Goals
- Deleting historical updates from `progress.json`.
- Replacing `prog-note` with another logging system.
- Changing `add-update` schema in a breaking way without migration plan.

## Decisions
1. `/prog` should prioritize actionable notes (recent and/or open).
2. History remains intact and is viewed via `prog list-updates`.
3. UI output should show concise summary counters when older notes are hidden.

## Proposed Behavior
- `/prog` displays:
  - recent actionable updates (e.g., with `next_action`)
  - active/open memo items (if lifecycle marker exists)
  - optional summary: `hidden historical notes: N`
- `prog list-updates --limit N` remains the full retrieval path.

## Implementation Steps
1. Define filtering rules for `/prog` update block.
2. Implement rendering changes in `status()` and `generate_progress_md()`.
3. Add tests for:
   - recent actionable note shown
   - old non-actionable note hidden from `/prog`
   - hidden-count summary accurate
   - full history still accessible via `list-updates`

## Acceptance Criteria
- `/prog` no longer surfaces very old stale memo by default.
- Actionable handoff notes are still visible in status output.
- `list-updates` can still retrieve full memo history.
- No regressions in existing update write/read workflows.

## Risk & Mitigation
- Risk: hiding too much context from status view.
  - Mitigation: include hidden-count summary and clear retrieval hint.
- Risk: behavioral surprise for existing users.
  - Mitigation: document new display rules and provide examples.

## Verification Plan
- Unit tests around update filtering and rendering.
- Snapshot-style status output checks.
- Manual check across:
  - no updates
  - only old updates
  - mixed old + actionable updates

## Rollback
- Revert `/prog` and markdown rendering filters to current "latest 5" behavior.
