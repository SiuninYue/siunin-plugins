"""Contract tests for F26 work-item command extraction."""

from __future__ import annotations

import sys
from pathlib import Path


_HOOKS_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import progress_manager
import work_item_commands


def test_work_item_command_exports_and_facade_wrappers():
    assert callable(work_item_commands.add_update_command)
    assert callable(work_item_commands.list_updates_command)
    assert callable(work_item_commands.add_retro_command)
    assert callable(work_item_commands.set_feature_owner_command)
    assert callable(work_item_commands.add_feature_command)
    assert callable(work_item_commands.update_feature_command)
    assert callable(work_item_commands.defer_features_command)
    assert callable(work_item_commands.resume_deferred_features_command)
    assert callable(work_item_commands.add_task_item_command)
    assert callable(work_item_commands.smart_intake_command)

    assert progress_manager.add_update.is_wrapper is True
    assert progress_manager.list_updates.is_wrapper is True
    assert progress_manager.add_retro.is_wrapper is True
    assert progress_manager.set_feature_owner.is_wrapper is True
    assert progress_manager.add_feature.is_wrapper is True
    assert progress_manager.update_feature.is_wrapper is True
    assert progress_manager.defer_features.is_wrapper is True
    assert progress_manager.resume_deferred_features.is_wrapper is True
    assert progress_manager.add_task_item.is_wrapper is True
    assert progress_manager.smart_intake.is_wrapper is True


def test_work_item_constants_are_re_exported_from_progress_manager():
    assert progress_manager.WORK_ITEM_TAXONOMY == work_item_commands.WORK_ITEM_TAXONOMY
    assert (
        progress_manager.WORKFLOW_PROFILE_VALUES
        == work_item_commands.WORKFLOW_PROFILE_VALUES
    )
    assert (
        progress_manager.WORKFLOW_PROFILE_DEFAULT
        == work_item_commands.WORKFLOW_PROFILE_DEFAULT
    )
    assert progress_manager.UPDATE_CATEGORIES == work_item_commands.UPDATE_CATEGORIES
    assert (
        progress_manager.UPDATE_REFS_INLINE_LIMIT
        == work_item_commands.UPDATE_REFS_INLINE_LIMIT
    )
    assert progress_manager.UPDATE_SOURCES == work_item_commands.UPDATE_SOURCES


def test_progress_manager_line_budget_meets_f26_target():
    progress_manager_path = Path(progress_manager.__file__)
    line_count = sum(1 for _ in progress_manager_path.open("r", encoding="utf-8"))
    assert line_count <= 6821
