# Design Doc: F22 - RouteV1: Parent Sequential Dispatching

## 1. Context & Goals
In a multi-project setup (Parent-Children), users currently have to manually navigate between projects. This feature automates the "next step" discovery by allowing a Parent project to delegate `prog next` to its children based on a prioritized queue.

**Goals:**
- **Automated Navigation**: `prog next` in a Parent project points to the first actionable feature in its Children.
- **Conflict Prevention**: Skip Children that already have active routes (assigned to other agents).
- **Snapshot Loopback**: Automatically update Parent's view of Child progress when a feature is completed in the Child.

## 2. Proposed Changes

### 2.1 Parent Dispatching Logic
Modify `next_feature()` in `progress_manager.py`:
1.  **Role Check**: If `tracker_role == "parent"`.
2.  **Queue Traversal**:
    - Get `routing_queue` (list of `project_code`).
    - Get `active_routes` (list of active project assignments).
    - For each `code` in `routing_queue`:
        - **Skip Conflict**: If `code` is in `active_routes` (specifically, checking if any entry in `active_routes` matches this `project_code`), skip it to avoid parallel work conflicts.
        - **Load Child**: Look up `path` in `linked_projects`. Load the child's `progress.json`.
        - **Find Feature**: Find the first `pending` (not completed, not deferred) feature in the child.
        - **Dispatch**: If found, return the child feature info.
3.  **Fallback**: If no child has pending features, or no queue exists, fall back to the parent's own features (if any).

### 2.2 Output Format
- **JSON**:
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
- **Terminal**:
  > [NEXT] Parent project complete. Found next feature in child [PM]:
  > F3: Install dependencies
  > Run: cd plugins/package-manager && prog next

### 2.3 Snapshot Writeback (Option A)
Modify `cmd_done()`:
1.  **Trigger**: After a feature is successfully marked as `completed`.
2.  **Parent Discovery**:
    - Use `PROG_PARENT_ROOT` environment variable.
    - Or scan upwards for a `.claude-plugin/` or `progress.json` with `tracker_role: "parent"`.
3.  **Sync**: Call a new internal function `_maybe_sync_parent_snapshot()` which:
    - Locates the parent project.
    - Updates the parent's `linked_projects[code].snapshot` with the current child state (total features, completed, etc.).
    - This ensures `prog status` at the parent level is always fresh.

## 3. Data Flow
1. User runs `prog next` in Parent.
2. Parent scans Children -> Finds Child B -> Returns "Go to Child B".
3. User runs `prog next` in Child B -> Completes Feature.
4. User runs `prog done` in Child B.
5. Child B detects Parent -> Updates Parent's snapshot.

## 4. Testing Strategy
- **Unit Tests**:
    - `test_dispatch_logic`: Verify skipping active routes.
    - `test_dispatch_empty_queue`: Verify fallback to parent features.
    - `test_snapshot_writeback`: Verify parent `progress.json` is updated after child `prog done`.
- **Integration Tests**:
    - Setup a parent and two children.
    - Verify `prog next` correctly hops between them.

## 5. Implementation Plan
1. [ ] Implement `_get_dispatched_child_feature()` helper.
2. [ ] Update `next_feature()` to use the helper.
3. [ ] Implement `_maybe_sync_parent_snapshot()` helper.
4. [ ] Hook `_maybe_sync_parent_snapshot()` into `cmd_done()`.
5. [ ] Add comprehensive tests.
