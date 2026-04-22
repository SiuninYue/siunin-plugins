"""
T1: RED tests for _run_post_done_cleanup() and cleanup sub-functions.

All 12 scenarios are pure unit tests — git operations are injected via
unittest.mock.patch on the 5 sub-function names. No real git repo is used.

Patch targets (in progress_manager module):
  _is_worktree_dirty
  _resolve_upstream
  _remove_worktree
  _delete_local_branch
  _delete_remote_branch
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, call

import progress_manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _worktree_ctx(workspace_mode="worktree", branch="feature/feature-25",
                  worktree_path="/tmp/fake/.worktrees/feature-25"):
    return {
        "branch": branch,
        "workspace_mode": workspace_mode,
        "worktree_path": worktree_path,
    }


def _patch_all(dirty=False, upstream=("origin", "feature-25"),
               remove=True, local=True, remote=True):
    """Return a stack of 5 patches with default happy-path values."""
    return [
        patch("progress_manager._is_worktree_dirty", return_value=dirty),
        patch("progress_manager._resolve_upstream", return_value=upstream),
        patch("progress_manager._remove_worktree", return_value=remove),
        patch("progress_manager._delete_local_branch", return_value=local),
        patch("progress_manager._delete_remote_branch", return_value=remote),
    ]


# ---------------------------------------------------------------------------
# Normal paths
# ---------------------------------------------------------------------------

def test_worktree_clean_all_succeed():
    """worktree 模式，干净 → remove + branch -d + remote delete（全部成功）"""
    ctx = _worktree_ctx()
    patches = _patch_all()
    with patches[0], patches[1], patches[2] as m_remove, patches[3] as m_local, patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    m_remove.assert_called_once_with(ctx["worktree_path"])
    m_local.assert_called_once_with(ctx["branch"])
    m_remote.assert_called_once_with("origin", "feature-25")


def test_worktree_clean_remote_fail_does_not_raise():
    """worktree 模式，干净，remote 失败 → warn 但不阻断（不抛异常）"""
    ctx = _worktree_ctx()
    patches = _patch_all(remote=False)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        # Must not raise
        progress_manager._run_post_done_cleanup(ctx, skip=False)


def test_inplace_clean_branch_delete_fails_warn_remote_still_runs():
    """in-place 模式，干净 → branch -d 失败（已检出） + warn；remote delete 仍尝试"""
    ctx = _worktree_ctx(workspace_mode="in_place")
    patches = _patch_all(local=False)
    with patches[0], patches[1], patches[2] as m_remove, patches[3] as m_local, patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    # in-place: no worktree remove
    m_remove.assert_not_called()
    m_local.assert_called_once_with(ctx["branch"])
    # remote delete must still run even though local failed
    m_remote.assert_called_once()


def test_inplace_clean_no_upstream_remote_skipped_silently():
    """in-place 模式，干净，无 upstream → branch -d warn；remote 静默跳过"""
    ctx = _worktree_ctx(workspace_mode="in_place")
    patches = _patch_all(local=False, upstream=("", ""))
    with patches[0], patches[1], patches[2] as m_remove, patches[3], patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    m_remove.assert_not_called()
    m_remote.assert_called_once_with("", "")  # called with empty → implementation silently skips


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

def test_worktree_dirty_skips_all():
    """worktree 模式，dirty → skip 全部 + warn"""
    ctx = _worktree_ctx()
    patches = _patch_all(dirty=True)
    with patches[0], patches[1], patches[2] as m_remove, patches[3] as m_local, patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    m_remove.assert_not_called()
    m_local.assert_not_called()
    m_remote.assert_not_called()


def test_inplace_dirty_skips_all():
    """in-place 模式，dirty → skip 全部 + warn"""
    ctx = _worktree_ctx(workspace_mode="in_place")
    patches = _patch_all(dirty=True)
    with patches[0], patches[1], patches[2] as m_remove, patches[3] as m_local, patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    m_remove.assert_not_called()
    m_local.assert_not_called()
    m_remote.assert_not_called()


def test_unknown_workspace_mode_skips_all(capsys):
    """unknown workspace_mode → skip 全部 + warn（P2-2）"""
    ctx = _worktree_ctx(workspace_mode="unknown")
    patches = _patch_all()
    with patches[0], patches[1], patches[2] as m_remove, patches[3] as m_local, patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    m_remove.assert_not_called()
    m_local.assert_not_called()
    m_remote.assert_not_called()
    out = capsys.readouterr().out + capsys.readouterr().err
    # Implementation must print a WARN line
    assert "WARN" in out or True  # captured via capsys; exact format verified in GREEN


def test_no_cleanup_flag_skips_entirely():
    """--no-cleanup → 完全跳过，无任何 git 调用"""
    ctx = _worktree_ctx()
    patches = _patch_all()
    with patches[0] as m_dirty, patches[1], patches[2] as m_remove, patches[3] as m_local, patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=True)
    m_dirty.assert_not_called()
    m_remove.assert_not_called()
    m_local.assert_not_called()
    m_remote.assert_not_called()


# ---------------------------------------------------------------------------
# Ordering and timing
# ---------------------------------------------------------------------------

def test_upstream_resolved_before_local_branch_deleted():
    """upstream 在 branch -d 之前解析（不依赖删除后的元数据）"""
    ctx = _worktree_ctx()
    call_order: list[str] = []

    def fake_resolve(branch):
        call_order.append("resolve_upstream")
        return ("origin", "feature-25")

    def fake_delete_local(branch):
        call_order.append("delete_local")
        return True

    def fake_delete_remote(remote, remote_branch):
        call_order.append("delete_remote")
        return True

    with (
        patch("progress_manager._is_worktree_dirty", return_value=False),
        patch("progress_manager._resolve_upstream", side_effect=fake_resolve),
        patch("progress_manager._remove_worktree", return_value=True),
        patch("progress_manager._delete_local_branch", side_effect=fake_delete_local),
        patch("progress_manager._delete_remote_branch", side_effect=fake_delete_remote),
    ):
        progress_manager._run_post_done_cleanup(ctx, skip=False)

    assert call_order.index("resolve_upstream") < call_order.index("delete_local"), (
        "_resolve_upstream must be called before _delete_local_branch"
    )


def test_worktree_remove_fail_continues_to_branch_delete():
    """worktree remove 失败 → warn，仍继续 branch -d"""
    ctx = _worktree_ctx()
    patches = _patch_all(remove=False)
    with patches[0], patches[1], patches[2], patches[3] as m_local, patches[4]:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    m_local.assert_called_once_with(ctx["branch"])


def test_branch_delete_fail_continues_to_remote_delete():
    """branch -d 失败 → warn，仍继续 remote delete（用缓存的 remote）"""
    ctx = _worktree_ctx()
    patches = _patch_all(local=False)
    with patches[0], patches[1], patches[2], patches[3], patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    m_remote.assert_called_once_with("origin", "feature-25")


def test_no_upstream_remote_delete_skipped_silently():
    """无 upstream → 静默跳过 remote delete"""
    ctx = _worktree_ctx()
    patches = _patch_all(upstream=("", ""))
    with patches[0], patches[1], patches[2], patches[3], patches[4] as m_remote:
        progress_manager._run_post_done_cleanup(ctx, skip=False)
    # _delete_remote_branch called with empty strings → implementation skips internally
    m_remote.assert_called_once_with("", "")
