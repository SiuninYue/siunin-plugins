"""Contract tests for F27 workflow/reconcile command extraction."""

from __future__ import annotations

import sys
from pathlib import Path


_HOOKS_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import progress_manager
import workflow_commands


def test_workflow_command_exports_and_facade_wrappers():
    assert callable(workflow_commands.set_workflow_state_command)
    assert callable(workflow_commands.update_workflow_task_command)
    assert callable(workflow_commands.clear_workflow_state_command)
    assert callable(workflow_commands.health_check_command)
    assert callable(workflow_commands.validate_plan_command)
    assert callable(workflow_commands.analyze_reconcile_state_command)
    assert callable(workflow_commands.reconcile_command)
    assert callable(workflow_commands.cmd_reconcile_state_command)

    assert progress_manager.set_workflow_state.is_wrapper is True
    assert progress_manager.update_workflow_task.is_wrapper is True
    assert progress_manager.clear_workflow_state.is_wrapper is True
    assert progress_manager.health_check.is_wrapper is True
    assert progress_manager.validate_plan.is_wrapper is True
    assert progress_manager.analyze_reconcile_state.is_wrapper is True
    assert progress_manager.reconcile.is_wrapper is True
    assert progress_manager.cmd_reconcile_state.is_wrapper is True


def test_reconcile_constants_are_re_exported_from_progress_manager():
    assert progress_manager.RECONCILE_DIAGNOSES == workflow_commands.RECONCILE_DIAGNOSES
    assert (
        progress_manager.RECONCILE_NEXT_STEPS
        == workflow_commands.RECONCILE_NEXT_STEPS
    )


def test_progress_manager_line_budget_meets_f27_target():
    progress_manager_path = Path(progress_manager.__file__)
    line_count = sum(1 for _ in progress_manager_path.open("r", encoding="utf-8"))
    assert line_count < 6528
