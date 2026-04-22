"""
wf_state_machine.py — 纯函数工作流状态机

compute_next_action(phase, context) → str | None

规则：
- execution_complete → "run_prog_done"
- execution + completed_tasks == total_tasks → "run_prog_done"
- execution + completed_tasks < total_tasks → "continue_execution"
- planning:draft → "resume_planning_draft"
- planning:approved → "execute_approved_plan"
- planning:clarifying → "resume_planning_clarifying"
- planning → "restart_from_planning"
- None / unknown → None（无操作）

设计约束：无 I/O，无副作用，可安全重复调用。
"""

from typing import Optional

_PHASE_ACTION_MAP: dict[str, str] = {
    "execution_complete": "run_prog_done",
    "planning:draft": "resume_planning_draft",
    "planning:approved": "execute_approved_plan",
    "planning:clarifying": "resume_planning_clarifying",
    "planning": "restart_from_planning",
}


def compute_next_action(
    phase: Optional[str],
    context: Optional[dict] = None,
) -> Optional[str]:
    """
    计算当前 workflow_state 的下一步动作。

    Args:
        phase: workflow_state.phase 当前值
        context: 附加上下文，支持 completed_tasks / total_tasks

    Returns:
        pending_action 字符串，或 None（无需操作）
    """
    if not phase:
        return None

    # execution 阶段需要根据任务进度判断
    if phase == "execution":
        return _compute_execution_action(context or {})

    # 静态映射
    return _PHASE_ACTION_MAP.get(phase)


def _compute_execution_action(context: dict) -> str:
    """execution 阶段：任务全完 → run_prog_done，否则 continue_execution"""
    completed = context.get("completed_tasks") or []
    total = context.get("total_tasks") or 0

    if total > 0 and len(completed) >= total:
        return "run_prog_done"
    return "continue_execution"
