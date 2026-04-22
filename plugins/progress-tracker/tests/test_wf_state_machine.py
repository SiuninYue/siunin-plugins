"""
T1 [RED]: wf_state_machine.py 纯函数 FSM 测试

compute_next_action(phase, context) → str | None
"""

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from wf_state_machine import compute_next_action


class TestComputeNextActionExecutionComplete:
    """execution_complete phase → run_prog_done"""

    def test_execution_complete_returns_run_prog_done(self):
        result = compute_next_action("execution_complete", {})
        assert result == "run_prog_done"

    def test_execution_complete_ignores_context(self):
        """execution_complete 始终触发 gate，与 context 无关"""
        result = compute_next_action("execution_complete", {"completed_tasks": [], "total_tasks": 0})
        assert result == "run_prog_done"

    def test_execution_complete_none_context(self):
        result = compute_next_action("execution_complete", None)
        assert result == "run_prog_done"


class TestComputeNextActionExecution:
    """execution phase → 根据任务进度决定"""

    def test_execution_tasks_incomplete_returns_continue(self):
        result = compute_next_action("execution", {"completed_tasks": [1, 2], "total_tasks": 5})
        assert result == "continue_execution"

    def test_execution_tasks_complete_returns_run_prog_done(self):
        result = compute_next_action("execution", {"completed_tasks": [1, 2, 3], "total_tasks": 3})
        assert result == "run_prog_done"

    def test_execution_no_tasks_returns_continue(self):
        """没有任务信息时，保守返回 continue_execution"""
        result = compute_next_action("execution", {})
        assert result == "continue_execution"

    def test_execution_zero_total_returns_continue(self):
        result = compute_next_action("execution", {"completed_tasks": [], "total_tasks": 0})
        assert result == "continue_execution"


class TestComputeNextActionPlanningPhases:
    """planning 阶段映射"""

    def test_planning_draft_returns_resume_planning_draft(self):
        result = compute_next_action("planning:draft", {})
        assert result == "resume_planning_draft"

    def test_planning_approved_returns_execute_approved_plan(self):
        result = compute_next_action("planning:approved", {})
        assert result == "execute_approved_plan"

    def test_planning_clarifying_returns_resume_clarifying(self):
        result = compute_next_action("planning:clarifying", {})
        assert result == "resume_planning_clarifying"

    def test_planning_base_returns_restart_from_planning(self):
        result = compute_next_action("planning", {})
        assert result == "restart_from_planning"


class TestComputeNextActionUnknown:
    """unknown / None phase → None（无操作）"""

    def test_none_phase_returns_none(self):
        result = compute_next_action(None, {})
        assert result is None

    def test_unknown_phase_returns_none(self):
        result = compute_next_action("some_unknown_phase", {})
        assert result is None

    def test_empty_string_phase_returns_none(self):
        result = compute_next_action("", {})
        assert result is None


class TestComputeNextActionPurity:
    """纯函数性：无副作用，相同输入产生相同输出"""

    def test_same_input_same_output_execution_complete(self):
        r1 = compute_next_action("execution_complete", {"x": 1})
        r2 = compute_next_action("execution_complete", {"x": 1})
        assert r1 == r2 == "run_prog_done"

    def test_context_not_mutated(self):
        ctx = {"completed_tasks": [1, 2], "total_tasks": 5}
        original = dict(ctx)
        compute_next_action("execution", ctx)
        assert ctx == original

    def test_multiple_calls_no_state_leak(self):
        """多次调用不累积状态"""
        compute_next_action("execution_complete", {})
        result = compute_next_action("execution", {"completed_tasks": [1], "total_tasks": 3})
        assert result == "continue_execution"
