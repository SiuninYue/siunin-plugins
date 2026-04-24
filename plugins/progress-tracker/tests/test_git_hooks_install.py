"""测试 install-git-hooks 命令。

注意：实现使用 `git rev-parse --git-path hooks`（支持 worktree 的 .git 文件）。
测试必须 mock subprocess.run 使其返回 hooks 目录路径，而不是依赖真实 git repo。
"""
import stat
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager as pm


def _make_git_rev_parse_mock(hooks_dir: Path):
    """创建 subprocess.run mock，对 --git-path hooks 返回指定目录。"""
    def mock_run(cmd, **kwargs):
        if "--git-path" in cmd and "hooks" in cmd:
            m = MagicMock()
            m.returncode = 0
            m.stdout = str(hooks_dir) + "\n"
            return m
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        return m
    return mock_run


class TestInstallGitHooks:
    def _setup_hooks_dir(self, tmp_path):
        """创建 hooks 目录（可以是 .git/hooks 或 worktree 的 hooks 路径）。"""
        git_hooks = tmp_path / ".git" / "hooks"
        git_hooks.mkdir(parents=True)
        return git_hooks

    def test_creates_post_merge_hook(self, tmp_path):
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            result = pm.cmd_install_git_hooks()
        assert (git_hooks / "post-merge").exists()
        assert result["installed"] is True

    def test_hook_is_executable(self, tmp_path):
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            pm.cmd_install_git_hooks()
        hook = git_hooks / "post-merge"
        assert hook.stat().st_mode & stat.S_IXUSR

    def test_hook_content_contains_reconcile_state(self, tmp_path):
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            pm.cmd_install_git_hooks()
        content = (git_hooks / "post-merge").read_text()
        assert "reconcile-state" in content

    def test_git_command_failure_returns_error(self, tmp_path):
        """git rev-parse 失败时返回 installed=False。"""
        def mock_git_fail(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 128
            m.stderr = "not a git repository"
            return m

        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=mock_git_fail):
            result = pm.cmd_install_git_hooks()
        assert result["installed"] is False
        assert result.get("error")

    def test_overwrites_existing_hook(self, tmp_path):
        git_hooks = self._setup_hooks_dir(tmp_path)
        (git_hooks / "post-merge").write_text("#!/bin/bash\necho old_hook")
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            result = pm.cmd_install_git_hooks()
        assert result["installed"] is True
        assert "reconcile-state" in (git_hooks / "post-merge").read_text()

    def test_worktree_git_file_scenario(self, tmp_path):
        """P1 修复验证：worktree 下 .git 是文件，hooks 在不同路径。

        通过 mock git rev-parse 返回 worktree hooks 路径，模拟 worktree 场景。
        """
        # worktree 的 hooks 指向主 repo 的 hooks
        worktree_hooks = tmp_path / "main_repo" / ".git" / "hooks"
        worktree_hooks.mkdir(parents=True)
        # .git 是文件（模拟 worktree）
        git_file = tmp_path / "worktree" / ".git"
        git_file.parent.mkdir(parents=True)
        git_file.write_text(f"gitdir: {tmp_path}/main_repo/.git/worktrees/wt1\n")

        with patch("progress_manager.find_project_root", return_value=tmp_path / "worktree"), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(worktree_hooks)):
            result = pm.cmd_install_git_hooks()
        assert result["installed"] is True
        assert (worktree_hooks / "post-merge").exists()