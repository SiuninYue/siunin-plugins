from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import progress_manager


def test_validate_done_preconditions_no_active_feature_includes_scope(tmp_path: Path):
    """No active feature should include scope diagnostics for faster recovery."""
    data = {
        "current_feature_id": None,
        "tracker_role": "child",
        "project_code": "PT",
    }

    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", tmp_path):
        valid, reason, code, feature = progress_manager._validate_done_preconditions(data)

    assert valid is False
    assert code == 1
    assert feature is None
    assert "No active feature. Run /prog next first." in reason
    assert f"scope={tmp_path}" in reason
    assert "tracker_role=child" in reason
    assert "project_code=PT" in reason


def test_resolve_acceptance_command_cwd_prefers_repo_root_for_repo_relative_paths(
    tmp_path: Path,
):
    """
    When running inside plugin root, repo-relative test paths should use repo_root.
    """
    repo_root = tmp_path
    project_root = repo_root / "plugins" / "progress-tracker"
    (repo_root / "plugins" / "progress-tracker" / "tests").mkdir(parents=True)

    command = "uv run pytest plugins/progress-tracker/tests/ -q"
    cwd = progress_manager._resolve_acceptance_command_cwd(
        command=command,
        project_root=project_root,
        repo_root=repo_root,
    )

    assert cwd == repo_root


def test_resolve_acceptance_command_cwd_keeps_project_root_for_local_paths(tmp_path: Path):
    """Plugin-local relative paths should keep project_root as execution cwd."""
    repo_root = tmp_path
    project_root = repo_root / "plugins" / "progress-tracker"
    (project_root / "tests").mkdir(parents=True)

    command = "uv run pytest tests/ -q"
    cwd = progress_manager._resolve_acceptance_command_cwd(
        command=command,
        project_root=project_root,
        repo_root=repo_root,
    )

    assert cwd == project_root
