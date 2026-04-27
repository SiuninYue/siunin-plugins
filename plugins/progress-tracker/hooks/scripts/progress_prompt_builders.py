"""
Progress Prompt Builders — handoff and completion prompt construction.

Pure functions that build the context handoff blocks printed at the end of
`/prog status` and `/prog done`. Extracted from progress_manager.py to keep
builder logic testable in isolation.

No imports from progress_manager — all needed data is passed as parameters.
"""

from typing import Any, Dict, Optional

__all__ = [
    "build_status_handoff_block",
    "build_done_handoff_block",
    "build_project_completion_summary",
]


def _is_deferred(feature: Dict[str, Any]) -> bool:
    """Single source of truth for deferred-feature checks.

    progress_manager._is_feature_deferred delegates here; do not duplicate logic.
    """
    return bool(feature.get("deferred", False))


def build_status_handoff_block(
    data: Dict[str, Any],
    completed: int,
    total: int,
    project_root: str,
    current_branch: Optional[str] = None,
) -> Optional[str]:
    """Build context handoff block for /prog status output.

    Args:
        current_branch: Real-time git branch name. If provided, overrides the
            stale ``workflow_state.execution_context.branch`` so the handoff
            block always reflects the *actual* checked-out branch.
    """
    features = data.get("features", [])
    current_id = data.get("current_feature_id")
    workflow_state = data.get("workflow_state") or {}

    # All features complete — no handoff block
    if completed == total and total > 0:
        return None

    # Prefer real-time git branch over stale execution_context
    execution_context = workflow_state.get("execution_context") or {}
    branch = current_branch or execution_context.get("branch") or "main"
    worktree_path: Optional[str] = None
    if execution_context.get("workspace_mode") == "worktree":
        worktree_path = execution_context.get("worktree_path")

    branch_line = f"Branch: {branch}"
    if worktree_path:
        branch_line += f" | Worktree: {worktree_path}"

    # No active feature — simple prog-next block
    if not current_id:
        remaining = [
            f for f in features
            if isinstance(f, dict)
            and not f.get("completed", False)
            and not _is_deferred(f)
        ]
        if not remaining:
            return None
        return "\n".join([
            "/progress-tracker:prog-next",
            "",
            f"Project: {completed}/{total} features done",
            f"ProjectRoot: {project_root}",
            "→ Context pre-loaded. Auto-selects and starts next pending feature.",
        ])

    # Active feature — find it
    current_feature = next((f for f in features if f.get("id") == current_id), None)
    if not current_feature:
        return None

    feature_name = current_feature.get("name", "Unknown")
    phase = workflow_state.get("phase") or "execution"
    plan_path = workflow_state.get("plan_path") or ""
    total_tasks = workflow_state.get("total_tasks")
    completed_tasks_list = workflow_state.get("completed_tasks") or []
    completed_tasks_count = len(completed_tasks_list) if isinstance(completed_tasks_list, list) else 0
    next_action = workflow_state.get("next_action") or ""

    if phase == "execution_complete":
        task_count = total_tasks or completed_tasks_count
        return "\n".join([
            "/progress-tracker:prog-done",
            "",
            f'Feature: {current_id} "{feature_name}" | Phase: execution_complete',
            f"Plan: {plan_path} | Tasks: {task_count}/{task_count} done",
            branch_line,
            f"ProjectRoot: {project_root}",
            "→ Context pre-loaded. Run verification and commit.",
        ])

    # All other active phases (execution, planning:approved, planning_complete, etc.)
    tasks_done = completed_tasks_count
    tasks_total = total_tasks if total_tasks is not None else "?"
    lines = [
        "/progress-tracker:prog-next",
        "",
        f'Feature: {current_id} "{feature_name}" | Phase: {phase}',
        f"Plan: {plan_path} | Tasks: {tasks_done}/{tasks_total} done",
    ]
    if next_action:
        lines.append(f"Next: {next_action}")
    lines.extend([
        branch_line,
        f"ProjectRoot: {project_root}",
        "→ Context pre-loaded. Resume from next task.",
    ])
    return "\n".join(lines)


def build_done_handoff_block(
    data: Dict[str, Any],
    next_feature: Optional[Dict[str, Any]],
    project_root: str,
) -> Optional[str]:
    """Build the post-completion handoff block for `/prog done`.

    Unlike the original _build_done_handoff_block in progress_manager.py, this
    function does not read progress.json itself. The caller is responsible for
    resolving the next feature (e.g. via get_next_feature()) and passing it here.

    Args:
        data: Full progress.json dict.
        next_feature: The next pending feature dict (keys used: id, name, test_steps),
            or None if no pending features remain.
        project_root: Absolute path to the project root.
    """
    features = data.get("features", [])
    if not isinstance(features, list):
        features = []

    completed = sum(
        1
        for feature in features
        if isinstance(feature, dict) and feature.get("completed", False)
    )
    total = len(features)

    if not next_feature:
        return None

    project_name = data.get("project_name", "Unknown")
    next_id = next_feature.get("id", "?")
    next_name = next_feature.get("name", "Unknown")
    test_steps = next_feature.get("test_steps", [])
    if not isinstance(test_steps, list):
        test_steps = []

    lines = [
        "---",
        "**粘贴到新会话以启动下一个功能：**",
        "",
        "/progress-tracker:prog-next",
        "",
        f'Project: {project_name} | {completed}/{total} completed',
        f'Feature: F{next_id} "{next_name}"',
        f"ProjectRoot: {project_root}",
        "→ Context pre-loaded. Auto-selects and starts next pending feature.",
        "",
        "**下一个功能预览：**",
        f"- ID: F{next_id}",
        f"- Name: {next_name}",
    ]

    if test_steps:
        lines.append("- Test steps:")
        for index, step in enumerate(test_steps, start=1):
            lines.append(f"  {index}. {step}")
    else:
        lines.append("- Test steps: none recorded")

    lines.append("---")
    return "\n".join(lines)


def build_project_completion_summary(
    data: Dict[str, Any],
    project_root: str,
) -> str:
    """Build a concise summary when no more pending features remain."""
    features = data.get("features", [])
    if not isinstance(features, list):
        features = []
    completed = sum(
        1
        for feature in features
        if isinstance(feature, dict) and feature.get("completed", False)
    )
    total = len(features)
    project_name = data.get("project_name", "Unknown")

    return "\n".join([
        "### Project Complete",
        f"Project: {project_name} | {completed}/{total} completed",
        f"ProjectRoot: {project_root}",
        "→ No pending features remain.",
    ])
