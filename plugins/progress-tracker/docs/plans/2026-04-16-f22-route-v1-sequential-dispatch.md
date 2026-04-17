# Design Doc: F22 - RouteV1: Parent Sequential Dispatching

## 1. Context & Goals

In a multi-project setup (Parent-Children), users currently have to manually navigate between projects. This feature automates the "next step" discovery by allowing a Parent project to delegate `prog next` to its children based on a prioritized queue.

**F22 Goals (narrowed scope):**
- **Automated Navigation**: `prog next` in a Parent project points to the first actionable feature in its Children.
- **Conflict Prevention**: Skip Children that already have active routes (assigned to other agents).

**Out of scope (→ F23):**
- Snapshot writeback: updating Parent's `linked_projects[code].snapshot` after child `prog done`.

## 2. Proposed Changes

### 2.1 Parent Dispatching Logic

Modify `next_feature()` in `progress_manager.py`:

1. **Role Check**: If `tracker_role == "parent"`.
2. **Queue Traversal**:
   - Get `routing_queue` (list of `project_code`).
   - Get `active_routes` (list of active project assignments).
   - For each `code` in `routing_queue`:
     - **Skip Conflict**: If `code` appears in any `active_routes` entry with a non-terminal state (i.e., exclude `done`/`cancelled` entries). This prevents parallel work conflicts.
     - **Stale Protection**: Active routes older than a configurable threshold (default: 24h) are treated as stale and do not block the queue.
     - **Load Child**: Look up `path` in `linked_projects`. Load the child's `progress.json`.
     - **Find Feature**: Find the first `pending` (not completed, not deferred) feature in the child.
     - **Dispatch**: If found, return the child feature info.
3. **Fallback**: If no child has pending features, or no queue exists, fall back to the parent's own features (if any).

**active_routes conflict check preconditions:**
- One child project allows only one active feature at a time.
- Only non-terminal states count as conflicts (active, in_progress — not done/cancelled).
- Stale routes (past timeout) are skipped to prevent permanent queue blockage.

### 2.2 Output Format

**JSON** (`--json` flag):
```json
{
  "dispatched_to": "child",
  "child_project_code": "PM",
  "child_project_root": "plugins/package-manager",
  "next_feature_id": "F3",
  "next_feature_name": "Install dependencies",
  "action_required": "cd plugins/package-manager && prog next"
}
```

**Terminal** (default):
```
[NEXT] Parent project complete. Found next feature in child [PM]:
F3: Install dependencies
Run: cd plugins/package-manager && prog next
```

**Fallback (no child features):**
```json
{
  "dispatched_to": "parent",
  "next_feature_id": "...",
  "next_feature_name": "..."
}
```

## 3. Data Flow

1. User runs `prog next` in Parent.
2. Parent scans `routing_queue` → skips conflicted/stale children → finds Child B → returns "Go to Child B".
3. User runs `prog next` in Child B → works on Feature.
4. (F23) After `prog done` in Child B, snapshot writeback to Parent.

## 4. Testing Strategy

- **Unit Tests**:
  - `test_dispatch_first_in_queue`: Verify first pending child is returned.
  - `test_dispatch_skips_active_routes`: Verify active (non-terminal) routes are skipped.
  - `test_dispatch_skips_only_active_not_done`: Verify done/cancelled routes do NOT block.
  - `test_dispatch_stale_route_unblocks`: Verify stale routes (past timeout) are skipped.
  - `test_dispatch_empty_queue_fallback`: Verify fallback to parent features.
  - `test_dispatch_all_children_done_fallback`: Verify fallback when all children complete.
- **Integration Tests**:
  - Setup a parent with two children in `routing_queue`.
  - Verify `prog next` returns first non-conflicted child's pending feature.
  - Verify conflict skipping respects only active (not terminal) routes.

## 5. Implementation Plan

1. [ ] Implement `_get_dispatched_child_feature(routing_queue, active_routes, linked_projects)` helper.
2. [ ] Update `next_feature()` to call helper when `tracker_role == "parent"`.
3. [ ] Add unit tests covering all scenarios above.
4. [ ] Add integration test with parent + two children.
