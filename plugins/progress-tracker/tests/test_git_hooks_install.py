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
        """创建 hooks 目录（可以是 .git/hooks 或 worktree 的 hooks 路径），
        同时准备 pre-commit 脚本源供 cmd_install_git_hooks 读取。
        """
        git_hooks = tmp_path / ".git" / "hooks"
        git_hooks.mkdir(parents=True)
        # 创建 pre-commit 脚本源（位于 hooks/ 目录下）
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-commit").write_text("#!/bin/bash\necho pre-commit-test\n")
        return git_hooks

    def test_creates_both_hooks(self, tmp_path):
        """安装后 post-merge 和 pre-commit 均存在。"""
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            result = pm.cmd_install_git_hooks()
        assert (git_hooks / "post-merge").exists()
        assert (git_hooks / "pre-commit").exists()
        assert result["installed"] is True

    def test_both_hooks_are_executable(self, tmp_path):
        """安装后两个 hook 均具有执行权限。"""
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            pm.cmd_install_git_hooks()
        post_merge = git_hooks / "post-merge"
        pre_commit = git_hooks / "pre-commit"
        assert post_merge.stat().st_mode & stat.S_IXUSR
        assert pre_commit.stat().st_mode & stat.S_IXUSR

    def test_post_merge_hook_content_contains_reconcile_state(self, tmp_path):
        """post-merge hook 内容仍包含 reconcile-state。"""
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            pm.cmd_install_git_hooks()
        content = (git_hooks / "post-merge").read_text()
        assert "reconcile-state" in content

    def test_pre_commit_hook_contains_check_command(self, tmp_path):
        """pre-commit hook 内容包含 generate_prog_docs.py --check。"""
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            pm.cmd_install_git_hooks()
        content = (git_hooks / "pre-commit").read_text()
        assert "generate_prog_docs.py" in content
        assert "--check" in content

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

    def test_overwrites_existing_hooks(self, tmp_path):
        """已存在的 hook 被覆盖，两个 hook 均正确。"""
        git_hooks = self._setup_hooks_dir(tmp_path)
        (git_hooks / "post-merge").write_text("#!/bin/bash\necho old_hook")
        (git_hooks / "pre-commit").write_text("#!/bin/bash\necho old_hook")
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            result = pm.cmd_install_git_hooks()
        assert result["installed"] is True
        assert "reconcile-state" in (git_hooks / "post-merge").read_text()
        assert "generate_prog_docs.py" in (git_hooks / "pre-commit").read_text()

    def test_worktree_git_file_scenario(self, tmp_path):
        """P1 修复验证：worktree 下 .git 是文件，hooks 在不同路径。

        通过 mock git rev-parse 返回 worktree hooks 路径，模拟 worktree 场景。
        """
        # worktree 的 hooks 指向主 repo 的 hooks
        worktree_hooks = tmp_path / "main_repo" / ".git" / "hooks"
        worktree_hooks.mkdir(parents=True)
        # 创建 pre-commit 脚本源
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-commit").write_text("#!/bin/bash\necho pre-commit-test\n")
        # .git 是文件（模拟 worktree）
        git_file = tmp_path / "worktree" / ".git"
        git_file.parent.mkdir(parents=True)
        git_file.write_text(f"gitdir: {tmp_path}/main_repo/.git/worktrees/wt1\n")

        with patch("progress_manager.find_project_root", return_value=tmp_path / "worktree"), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(worktree_hooks)):
            result = pm.cmd_install_git_hooks()
        assert result["installed"] is True
        assert (worktree_hooks / "post-merge").exists()
        assert (worktree_hooks / "pre-commit").exists()
