"""Scope fail-closed regression tests for monorepo tracker selection."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import progress_manager


def _init_tracker(temp_dir: Path, plugin_name: str, project_name: str) -> Path:
    plugin_root = temp_dir / "plugins" / plugin_name
    plugin_root.mkdir(parents=True, exist_ok=True)

    assert progress_manager.configure_project_scope(f"plugins/{plugin_name}") is True
    assert progress_manager.init_tracking(project_name, force=True) is True

    progress_manager._PROJECT_ROOT_OVERRIDE = None
    progress_manager._REPO_ROOT = None
    progress_manager._STORAGE_READY_ROOT = None
    return plugin_root


def _progress_path(plugin_root: Path) -> Path:
    return plugin_root / "docs" / "progress-tracker" / "state" / "progress.json"


def _load_progress(plugin_root: Path) -> dict:
    return json.loads(_progress_path(plugin_root).read_text(encoding="utf-8"))


def _save_progress(plugin_root: Path, payload: dict) -> None:
    _progress_path(plugin_root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_monorepo_root_blocks_mutating_command_when_scope_is_ambiguous(temp_dir, capsys):
    """Mutating commands must fail closed at monorepo root when multiple trackers exist."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    _init_tracker(temp_dir, "alpha-plugin", "Alpha Tracker")
    _init_tracker(temp_dir, "beta-plugin", "Beta Tracker")

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        ["progress_manager.py", "add-feature", "Feature X", "Step 1"],
    ):
        result = progress_manager.main()

    output = capsys.readouterr().out
    assert result in (False, 1)  # Accept both bool and int for error returns
    assert "Ambiguous monorepo scope" in output
    assert "prog --project-root plugins/<name>" in output


def test_explicit_project_root_recovers_mutating_command_from_monorepo_root(temp_dir):
    """The same mutating command should succeed once --project-root is specified."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    target_root = _init_tracker(temp_dir, "alpha-plugin", "Alpha Tracker")
    _init_tracker(temp_dir, "beta-plugin", "Beta Tracker")

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/alpha-plugin",
            "add-feature",
            "Feature Y",
            "Step Y",
        ],
    ):
        result = progress_manager.main()

    assert result is True

    progress_file = target_root / "docs" / "progress-tracker" / "state" / "progress.json"
    payload = json.loads(progress_file.read_text(encoding="utf-8"))
    assert any(feature["name"] == "Feature Y" for feature in payload.get("features", []))


@pytest.mark.parametrize(
    "mutating_tail",
    [
        ["set-current", "1"],  # /prog next path
        ["add-feature", "Feature X", "Step 1"],
        ["update-feature", "1", "Feature X Updated", "Step 2"],
        ["complete", "1", "--skip-archive"],
        ["done"],
    ],
)
def test_child_route_mismatch_blocks_core_mutating_commands(temp_dir, capsys, mutating_tail):
    """Child mutating commands must fail closed when parent active_routes points elsewhere."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    parent_root = _init_tracker(temp_dir, "parent-plugin", "Parent Tracker")
    child_root = _init_tracker(temp_dir, "child-plugin", "Child Tracker")

    parent_payload = _load_progress(parent_root)
    parent_payload["tracker_role"] = "parent"
    parent_payload["project_code"] = "PT"
    parent_payload["linked_projects"] = [
        {
            "project_root": "plugins/child-plugin",
            "project_code": "NO",
            "label": "Child Tracker",
        }
    ]
    parent_payload["routing_queue"] = ["NO"]
    parent_payload["active_routes"] = [
        {"project_code": "PT", "feature_ref": "PT-F1"},
    ]
    _save_progress(parent_root, parent_payload)

    child_payload = _load_progress(child_root)
    child_payload["tracker_role"] = "child"
    child_payload["project_code"] = "NO"
    child_payload["features"] = [
        {"id": 1, "name": "Child Feature", "test_steps": ["true"], "completed": False}
    ]
    child_payload["current_feature_id"] = 1
    child_payload["workflow_state"] = {"phase": "execution_complete"}
    _save_progress(child_root, child_payload)

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        ["progress_manager.py", "--project-root", "plugins/child-plugin", *mutating_tail],
    ):
        result = progress_manager.main()

    output = capsys.readouterr().out
    assert result in (False, 1)  # Accept both bool and int for error returns
    assert "Route Preflight" in output
    assert "--project-root" in output
    assert "cd " in output


def test_child_mutating_blocks_when_not_registered_in_parent(temp_dir, capsys):
    """Unregistered child tracker should be blocked with actionable routing guidance."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    parent_root = _init_tracker(temp_dir, "parent-plugin", "Parent Tracker")
    child_root = _init_tracker(temp_dir, "child-plugin", "Child Tracker")

    parent_payload = _load_progress(parent_root)
    parent_payload["tracker_role"] = "parent"
    parent_payload["project_code"] = "PT"
    parent_payload["linked_projects"] = []
    parent_payload["routing_queue"] = []
    parent_payload["active_routes"] = []
    _save_progress(parent_root, parent_payload)

    child_payload = _load_progress(child_root)
    child_payload["tracker_role"] = "child"
    child_payload["project_code"] = "NO"
    _save_progress(child_root, child_payload)

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        ["progress_manager.py", "--project-root", "plugins/child-plugin", "add-feature", "F", "S"],
    ):
        result = progress_manager.main()

    output = capsys.readouterr().out
    assert result in (False, 1)  # Accept both bool and int for error returns
    assert "not registered in any parent linked_projects" in output
    assert "link-project --project-root" in output
    assert "--project-root" in output


def test_child_mutating_allowed_when_parent_route_matches(temp_dir):
    """Child mutating command should proceed when parent active_routes matches child code."""
    os.system(f"git -C {temp_dir} init >/dev/null 2>&1")

    parent_root = _init_tracker(temp_dir, "parent-plugin", "Parent Tracker")
    child_root = _init_tracker(temp_dir, "child-plugin", "Child Tracker")

    parent_payload = _load_progress(parent_root)
    parent_payload["tracker_role"] = "parent"
    parent_payload["project_code"] = "PT"
    parent_payload["linked_projects"] = [
        {
            "project_root": "plugins/child-plugin",
            "project_code": "NO",
            "label": "Child Tracker",
        }
    ]
    parent_payload["routing_queue"] = ["NO"]
    parent_payload["active_routes"] = [
        {"project_code": "NO", "feature_ref": "NO-F1"},
    ]
    _save_progress(parent_root, parent_payload)

    child_payload = _load_progress(child_root)
    child_payload["tracker_role"] = "child"
    child_payload["project_code"] = "NO"
    _save_progress(child_root, child_payload)

    os.chdir(temp_dir)
    with patch(
        "sys.argv",
        [
            "progress_manager.py",
            "--project-root",
            "plugins/child-plugin",
            "add-feature",
            "Allowed Feature",
            "Step 1",
        ],
    ):
        result = progress_manager.main()

    assert result is True
    payload = _load_progress(child_root)
    assert any(feature["name"] == "Allowed Feature" for feature in payload.get("features", []))


"""
F21 验收测试：worktree/branch 一致性校验 (fail-closed)
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "scripts"))
import progress_manager


# ── 共用 fixture ────────────────────────────────────────────────────────────

def _make_progress(tmp_path, extra=None):
    """在 tmp_path 写入最小 progress.json，返回路径。"""
    data = {
        "project_name": "TestProj",
        "schema_version": "2.1",
        "features": [],
        "active_routes": [],
        "workflow_state": {},
        "tracker_role": "standalone",
    }
    if extra:
        data.update(extra)
    p = tmp_path / "docs" / "progress-tracker" / "state"
    p.mkdir(parents=True)
    (p / "progress.json").write_text(json.dumps(data))
    return tmp_path


# ── Task 1 测试 ─────────────────────────────────────────────────────────────

class TestRouteSelectRecordsWorktreeAndBranch:
    def test_route_select_stores_worktree_path_and_branch(self, tmp_path):
        """route_select() 应将当前 worktree_path 和 branch 写入 active_routes 条目。"""
        _make_progress(tmp_path)
        fake_git = {
            "workspace_mode": "worktree",
            "worktree_path": "/repo/.worktrees/feat-1",
            "project_root": "/repo",
            "cwd": "/repo/.worktrees/feat-1",
            "git_dir": None,
            "branch": "feature/1-test",
            "upstream": None,
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", tmp_path),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.route_select("MYPROJ")

        assert result is True
        data = json.loads((tmp_path / "docs" / "progress-tracker" / "state" / "progress.json").read_text())
        routes = data["active_routes"]
        assert len(routes) == 1
        entry = routes[0]
        assert entry["project_code"] == "MYPROJ"
        assert entry["worktree_path"] == "/repo/.worktrees/feat-1"
        assert entry["branch"] == "feature/1-test"


class TestCheckWorktreeBranchConsistency:
    """check_worktree_branch_consistency() 的单元测试。"""

    def _make_with_exec_context(self, tmp_path, branch, worktree_path):
        """构建含 execution_context 的 progress.json。"""
        return _make_progress(tmp_path, extra={
            "workflow_state": {
                "phase": "execution",
                "execution_context": {
                    "branch": branch,
                    "worktree_path": worktree_path,
                    "source": "set_workflow_state",
                },
            }
        })

    def test_returns_true_when_no_execution_context(self, tmp_path):
        """workflow_state 无 execution_context 时不阻断。"""
        _make_progress(tmp_path)
        with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                          tmp_path):
            result = progress_manager.check_worktree_branch_consistency("next-feature")
        assert result is True

    def test_returns_true_when_context_matches(self, tmp_path):
        """worktree_path 和 branch 都匹配时不阻断。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {
            "worktree_path": "/repo/.worktrees/feat-21",
            "branch": "feature/21-test",
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         tmp_path),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("next-feature")
        assert result is True

    def test_returns_false_when_branch_mismatches(self, tmp_path, capsys):
        """branch 不匹配时阻断并打印错误。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {
            "worktree_path": "/repo/.worktrees/feat-21",
            "branch": "main",   # 错误的 branch
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         tmp_path),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("next-feature")
        assert result is False
        captured = capsys.readouterr()
        assert "route-select" in captured.out
        assert "BLOCKED" in captured.out or "branch" in captured.out.lower()

    def test_returns_false_when_worktree_path_mismatches(self, tmp_path, capsys):
        """worktree_path 不匹配时阻断并打印错误。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {
            "worktree_path": "/repo",   # 错误路径（非 worktree）
            "branch": "feature/21-test",
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         tmp_path),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("done")
        assert result is False
        captured = capsys.readouterr()
        assert "route-select" in captured.out

    def test_returns_false_when_both_mismatch(self, tmp_path, capsys):
        """branch 和 worktree_path 都不匹配时阻断。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {
            "worktree_path": "/repo",
            "branch": "main",
        }
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                         tmp_path),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("done")
        assert result is False

    def test_returns_false_when_expected_context_exists_but_current_context_missing(self, tmp_path):
        """expected 有 branch/worktree 约束，但 current 缺失上下文时也应 fail-closed。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", "/repo/.worktrees/feat-21")
        fake_git = {"worktree_path": None, "branch": None}
        with (
            patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", tmp_path),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
        ):
            result = progress_manager.check_worktree_branch_consistency("done")
        assert result is False

    def test_returns_true_when_execution_context_empty(self, tmp_path):
        """execution_context 存在但 branch/worktree_path 都为空时不阻断。"""
        _make_progress(tmp_path, extra={
            "workflow_state": {
                "phase": "planning",
                "execution_context": {},
            }
        })
        with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE",
                          tmp_path):
            result = progress_manager.check_worktree_branch_consistency("next-feature")
        assert result is True



class TestMainConsistencyGate:
    """next-feature 和 done 命令的集成级阻断测试（通过 main() 路径）。"""

    def _make_with_exec_context(self, tmp_path, branch, worktree_path):
        data = {
            "project_name": "TestProj",
            "schema_version": "2.1",
            "features": [
                {
                    "id": 1,
                    "name": "Test Feature",
                    "test_steps": ["step1"],
                    "completed": False,
                    "deferred": False,
                    "development_stage": "developing",
                    "lifecycle_state": "implementing",
                }
            ],
            "active_routes": [],
            "workflow_state": {
                "phase": "execution",
                "execution_context": {
                    "branch": branch,
                    "worktree_path": worktree_path,
                    "source": "set_workflow_state",
                },
            },
            "current_feature_id": 1,
            "tracker_role": "standalone",
        }
        p = tmp_path / "docs" / "progress-tracker" / "state"
        p.mkdir(parents=True)
        (p / "progress.json").write_text(json.dumps(data))
        return tmp_path

    def test_next_feature_blocked_on_branch_mismatch(self, tmp_path, capsys):
        """main() 中 next-feature 在 branch 不匹配时返回 1（被阻断）。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", None)
        fake_git = {"worktree_path": None, "branch": "main"}
        with (
            patch.object(progress_manager, "find_project_root", return_value=tmp_path),
            patch.object(progress_manager, "configure_project_scope", return_value=True),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
            patch("sys.argv", ["prog", "next-feature"]),
        ):
            result = progress_manager.main()
        assert result == 1
        captured = capsys.readouterr()
        assert "route-select" in captured.out

    def test_done_blocked_on_worktree_mismatch(self, tmp_path, capsys):
        """main() 中 done 在 worktree 不匹配时返回 1（被阻断）。"""
        self._make_with_exec_context(tmp_path, None, "/repo/.worktrees/feat-21")
        fake_git = {"worktree_path": "/repo", "branch": "main"}
        with (
            patch.object(progress_manager, "find_project_root", return_value=tmp_path),
            patch.object(progress_manager, "configure_project_scope", return_value=True),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
            patch("sys.argv", ["prog", "done"]),
        ):
            result = progress_manager.main()
        assert result == 1
        captured = capsys.readouterr()
        assert "route-select" in captured.out

    def test_next_feature_passes_when_context_matches(self, tmp_path, capsys):
        """branch 匹配时 next-feature 正常执行（不被阻断）。"""
        self._make_with_exec_context(tmp_path, "feature/21-test", None)
        fake_git = {"worktree_path": None, "branch": "feature/21-test"}
        with (
            patch.object(progress_manager, "find_project_root", return_value=tmp_path),
            patch.object(progress_manager, "configure_project_scope", return_value=True),
            patch.object(progress_manager, "collect_git_context", return_value=fake_git),
            patch("sys.argv", ["prog", "next-feature"]),
        ):
            result = progress_manager.main()
        # 结果是 ok 或无 feature 均可，关键是没有被阻断
        captured = capsys.readouterr()
        assert "BLOCKED" not in captured.out
        assert "route-select" not in captured.out or "BLOCKED" not in captured.out
