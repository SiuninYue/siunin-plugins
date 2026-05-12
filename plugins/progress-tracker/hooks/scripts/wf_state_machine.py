"""
wf_state_machine.py — 纯函数工作流状态机

compute_next_action(phase, context) → str | None

规则：
- execution_complete → "run_prog_done"
- execution + completed_tasks == total_tasks → "run_prog_done"
- execution + completed_tasks < total_tasks → "continue_execution"
- planning:review → "resume_planning_draft"
- planning:draft → "resume_planning_draft"
- planning:clarifying → "resume_planning_draft"（归一化：与 planning:review 行为一致）
- planning:approved → "execute_approved_plan"
- planning_complete → "execute_approved_plan"（计划完成 = 可执行）
- planning → "restart_from_planning"
- design_complete → "restart_from_planning"（设计完成 → 进入规划）
- design → "restart_from_planning"（防御性覆盖）
- None / unknown → None（无操作）

work-item intake flow（F13）：
- intake:pending    → "classify_with_ai"
- intake:classified → "confirm_or_clarify"
- intake:confirmed  → "commit_work_item"
- intake:committed  → "route_to_queue"

task lifecycle（F13 定义常量，F14 接入执行语义）：
- task:pending → "start_task"
- task:active  → "complete_task"
- task:done    → None（终态，无后续动作）

设计约束：无 I/O，无副作用，可安全重复调用。
"""

from typing import Optional

_PHASE_ACTION_MAP: dict[str, Optional[str]] = {
    "execution_complete": "run_prog_done",
    "planning:review": "resume_planning_draft",
    "planning:draft": "resume_planning_draft",
    "planning:clarifying": "resume_planning_draft",  # 归一化：与 planning:review 一致
    "planning:approved": "execute_approved_plan",
    "planning_complete": "execute_approved_plan",     # 计划完成 = 可执行
    "planning": "restart_from_planning",
    "design_complete": "restart_from_planning",       # 设计完成 → 进入规划
    "design": "restart_from_planning",                # 防御性覆盖

    # work-item intake flow states
    "intake:pending":    "classify_with_ai",
    "intake:classified": "confirm_or_clarify",
    "intake:confirmed":  "commit_work_item",
    "intake:committed":  "route_to_queue",

    # task lifecycle states (F13 defines constants, F14 wires execution)
    "task:pending":      "start_task",
    "task:active":       "complete_task",
    "task:done":         None,
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
