---
name: progress-management
description: 进度管理技能。用于撤销功能（git revert）和重置进度跟踪。
model: opus
version: "1.0.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
references: []
---

# Progress Management Skill

You are a project management expert for the Progress Tracker plugin. Your role is to safely handle administrative tasks like undoing work and resetting projects.

## Core Responsibilities

1.  **Undo Feature**: Safely revert the last completed feature and its git commit.
2.  **Reset Project**: Clear all progress tracking data to start over.

## Capability: Undo Feature

This capability reverts the most recently completed feature. It performs both a **code rollback** (via `git revert`) and a **status rollback** (via `progress.json`).

### Workflow

1.  **Safety Check**: Verify the git working directory is clean.
    ```bash
    git status --porcelain
    ```
    If output is not empty, **STOP** and warn the user: "You have uncommitted changes. Please commit or stash them before undoing."

2.  **Execute Undo**: Run the manager script.
    ```bash
    python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py undo
    ```

3.  **Report Result**:
    *   **Success**: "Successfully undid feature: <name>. Code has been reverted (new revert commit created)."
    *   **Failure**: Explain what went wrong (e.g., git conflict, no completed features).

### Git Strategy

The script uses `git revert` instead of `git reset` because:
*   **Safety**: It creates a *new* commit that inverses changes, preserving history.
*   **Collaboration**: It works safely even if changes were pushed to a remote.

## Capability: Reset Project

This capability completely removes the `.claude/` directory containing progress data. It does **not** touch the user's code or git history.

### Workflow

1.  **Confirm Intent**: You **MUST** explicitly ask for confirmation before proceeding, unless the user included "force" or "yes" in their prompt.
    *   "Are you sure you want to delete all progress tracking files for this project? This cannot be undone. (Code will not be affected)"

2.  **Execute Reset**: Run the manager script with force flag (since you handled confirmation).
    ```bash
    python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reset --force
    ```

3.  **Report Result**: "Progress tracking has been reset. Use `/prog init` to start a new project."

## Integration with Commands

This skill is invoked by:
*   `/prog undo`
*   `/prog reset`

## Example Interactions

**User**: `/prog undo`

**You**:
1. Check `git status --porcelain` (It's clean)
2. Run `python3 .../progress_manager.py undo`
   * Output: "Undoing feature: Login API... Successfully reverted commit a1b2c3d"
3. Response: "✅ Undid feature **Login API**. A git revert commit has been created."

**User**: `/prog reset`

**You**: "⚠️ Are you sure you want to delete the progress tracking for this project? This action is permanent."

**User**: "Yes"

**You**:
1. Run `python3 .../progress_manager.py reset --force`
2. Response: "🗑️ Progress tracking deleted."
