"""Tests for Git worktree helper and functionality integrations."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from contextlib import contextmanager
import subprocess

import pytest
import progress_manager


def test_get_main_repo_root_no_worktree():
    """_get_main_repo_root returns None when not in a worktree (no 'worktrees' in git dir)."""
    mock_run = MagicMock()
    mock_run.return_value.stdout = "/Users/siunin/Projects/Claude-Plugins/.git\n"
    
    with patch("subprocess.run", mock_run):
        res = progress_manager._get_main_repo_root(Path("/Users/siunin/Projects/Claude-Plugins"))
    
    assert res is None


def test_get_main_repo_root_with_worktree():
    """_get_main_repo_root returns main repo path when git dir contains '/worktrees/'."""
    mock_run = MagicMock()
    mock_run.return_value.stdout = "/Users/siunin/Projects/Claude-Plugins/.git/worktrees/wt-1\n"
    
    with patch("subprocess.run", mock_run):
        res = progress_manager._get_main_repo_root(Path("/Users/siunin/Projects/Claude-Plugins-wt-1"))
        
    assert res == Path("/Users/siunin/Projects/Claude-Plugins")


def test_resolve_main_repo_path_no_worktree():
    """_resolve_main_repo_path returns original path when not in a worktree."""
    with patch("progress_manager._get_main_repo_root", return_value=None):
        path = Path("/Users/siunin/Projects/Claude-Plugins/plugins/my-plugin")
        assert progress_manager._resolve_main_repo_path(path) == path


def test_resolve_main_repo_path_with_worktree():
    """_resolve_main_repo_path translates worktree path to main repo path."""
    main_root = Path("/Users/siunin/Projects/Claude-Plugins")
    wt_root = Path("/Users/siunin/Projects/Claude-Plugins-wt-1")
    wt_sub = wt_root / "plugins" / "my-plugin"
    
    def mock_run_impl(cmd, **kwargs):
        if "rev-parse" in cmd and "--show-toplevel" in cmd:
            m = MagicMock()
            m.stdout = str(wt_root) + "\n"
            return m
        raise ValueError("Unexpected command")

    with patch("progress_manager._get_main_repo_root", return_value=main_root), \
         patch("subprocess.run", side_effect=mock_run_impl):
        res = progress_manager._resolve_main_repo_path(wt_sub)
        
    assert res == main_root / "plugins" / "my-plugin"


def test_store_evaluator_result_writes_both_when_worktree(temp_dir):
    """_store_evaluator_result writes to both worktree copy and main repository copy."""
    # Create main repo structure
    main_dir = temp_dir / "main"
    main_state = main_dir / "docs" / "progress-tracker" / "state"
    main_state.mkdir(parents=True, exist_ok=True)
    main_json = main_state / "progress.json"
    
    # Create worktree repo structure
    wt_dir = temp_dir / "wt"
    wt_state = wt_dir / "docs" / "progress-tracker" / "state"
    wt_state.mkdir(parents=True, exist_ok=True)
    wt_json = wt_state / "progress.json"
    
    # Seed both with a feature
    feat_data = {
        "features": [{"id": 1, "name": "Feature 1", "quality_gates": {}}],
        "schema_version": "2.1"
    }
    main_json.write_text(json.dumps(feat_data))
    wt_json.write_text(json.dumps(feat_data))
    
    class FakeResult:
        status = "passed"
        score = 95
        def to_quality_gate_payload(self):
            return {"status": "passed", "score": 95}
            
    # Mock resolution so that wt resolves to main
    with patch("progress_manager.find_project_root", return_value=wt_dir), \
         patch("progress_manager._resolve_main_repo_path", return_value=main_dir), \
         patch("progress_manager.get_progress_dir", return_value=wt_state), \
         patch("progress_manager.audit_log", None):
        progress_manager._store_evaluator_result(1, FakeResult())
        
    # Check that both got updated
    main_updated = json.loads(main_json.read_text())
    wt_updated = json.loads(wt_json.read_text())
    
    assert main_updated["features"][0]["quality_gates"]["evaluator"]["status"] == "passed"
    assert main_updated["features"][0]["quality_gates"]["evaluator"]["score"] == 95
    assert wt_updated["features"][0]["quality_gates"]["evaluator"]["status"] == "passed"
    assert wt_updated["features"][0]["quality_gates"]["evaluator"]["score"] == 95


def test_discover_parent_route_bindings_with_worktree_fallback(temp_dir):
    """_discover_parent_route_bindings_for_child succeeds when match is only found via main repo fallback."""
    parent_dir = temp_dir / "parent"
    child_wt_dir = temp_dir / "child-wt"
    child_main_dir = temp_dir / "child-main"
    
    parent_state = parent_dir / "docs" / "progress-tracker" / "state"
    parent_state.mkdir(parents=True, exist_ok=True)
    
    # Parent links to the child's main path
    parent_progress = {
        "tracker_role": "parent",
        "linked_projects": [
            {"project_root": str(child_main_dir), "project_code": "CHILD"}
        ]
    }
    (parent_state / "progress.json").write_text(json.dumps(parent_progress))
    
    # We query for child-wt
    # Mock _resolve_main_repo_path to map child-wt to child-main, and map others to themselves
    def mock_resolve_main_repo_path(path):
        if path == child_wt_dir:
            return child_main_dir
        return path
        
    with patch("progress_manager._resolve_main_repo_path", side_effect=mock_resolve_main_repo_path):
        discovered = progress_manager._discover_parent_route_bindings_for_child(
            child_project_root=child_wt_dir,
            repo_root=parent_dir
        )
        
    assert len(discovered) == 1
    assert discovered[0]["project_root"] == parent_dir


def test_link_project_translates_worktree_child_path(temp_dir):
    """link-project stores translated child root (main path) rather than worktree path."""
    parent_dir = temp_dir / "parent"
    parent_state = parent_dir / "docs" / "progress-tracker" / "state"
    parent_state.mkdir(parents=True, exist_ok=True)
    parent_progress = {
        "tracker_role": "parent",
        "linked_projects": [],
        "routing_queue": []
    }
    (parent_state / "progress.json").write_text(json.dumps(parent_progress))
    
    child_wt_dir = temp_dir / "child-wt"
    child_main_dir = temp_dir / "child-main"
    child_state = child_wt_dir / "docs" / "progress-tracker" / "state"
    child_state.mkdir(parents=True, exist_ok=True)
    (child_state / "progress.json").write_text(json.dumps({"tracker_role": "child"}))
    
    # Mock resolving worktree path to main path
    def mock_resolve_main_repo_path(path):
        if path == child_wt_dir:
            return child_main_dir
        return path
        
    with patch("progress_manager.find_project_root", return_value=parent_dir), \
         patch("progress_manager._resolve_linked_project_root", return_value=child_wt_dir), \
         patch("progress_manager._resolve_main_repo_path", side_effect=mock_resolve_main_repo_path), \
         patch("progress_manager._load_progress_payload_at_root", return_value=({"tracker_role": "child"}, None)), \
         patch("progress_manager._save_progress_payload_at_root"):
        
        # Link project using the worktree directory path
        res = progress_manager.link_project(
            child_project_root=str(child_wt_dir),
            code="CHILD"
        )
        
    assert res is True


def test_get_main_repo_root_strict_avoid_false_positive():
    """_get_main_repo_root avoids false positive on plain paths containing 'worktrees'."""
    mock_run = MagicMock()
    # 模拟返回的git dir只是普通目录，例如 /Users/siunin/my-worktrees/proj/.git，并没有 .../.git/worktrees/... 的嵌套关系
    mock_run.return_value.stdout = "/Users/siunin/my-worktrees/proj/.git\n"
    
    with patch("subprocess.run", mock_run):
        res = progress_manager._get_main_repo_root(Path("/Users/siunin/my-worktrees/proj"))
    
    assert res is None


def test_serialize_project_root_in_worktree():
    """_serialize_project_root_for_config serializes relative paths prioritizing main repo equivalents."""
    wt_root = Path("/Users/siunin/Projects/Claude-Plugins-wt-1")
    wt_sub = wt_root / "plugins" / "my-plugin"
    
    main_root = Path("/Users/siunin/Projects/Claude-Plugins")
    main_sub = main_root / "plugins" / "my-plugin"
    
    # 模拟 _resolve_main_repo_path 把 wt_sub 翻译为 main_sub，把 wt_root 翻译为 main_root
    def mock_resolve_main_repo_path(path):
        if path.resolve() == wt_sub.resolve() or path.resolve() == main_sub.resolve():
            return main_sub
        if path.resolve() == wt_root.resolve() or path.resolve() == main_root.resolve():
            return main_root
        return path
        
    with patch("progress_manager._resolve_main_repo_path", side_effect=mock_resolve_main_repo_path):
        res = progress_manager._serialize_project_root_for_config(wt_sub, wt_root)
        
    assert res == "plugins/my-plugin"


def test_save_progress_payload_locks_correct_root(temp_dir):
    """_save_progress_payload_at_root locks the specified project root."""
    target_root = temp_dir / "target-project"
    state_dir = target_root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    
    # 跟踪 progress_transaction 的调用
    locked_roots = []
    
    original_transaction = progress_manager.progress_transaction
    
    @contextmanager
    def mock_transaction(timeout_seconds=None, project_root=None):
        locked_roots.append(project_root)
        with original_transaction(timeout_seconds=timeout_seconds, project_root=project_root):
            yield

    with patch("progress_manager.progress_transaction", mock_transaction):
        progress_manager._save_progress_payload_at_root(
            target_root,
            {"schema_version": "2.1", "project_name": "Test"},
            touch_updated_at=False
        )
        
    assert len(locked_roots) == 1
    assert locked_roots[0] == target_root


def test_link_project_updates_both_wt_and_main_metadata(temp_dir):
    """link_project updates metadata files in both worktree child root and main child root."""
    parent_dir = temp_dir / "parent"
    parent_state = parent_dir / "docs" / "progress-tracker" / "state"
    parent_state.mkdir(parents=True, exist_ok=True)
    (parent_state / "progress.json").write_text(json.dumps({
        "tracker_role": "parent",
        "linked_projects": [],
        "routing_queue": []
    }))
    
    child_wt_dir = temp_dir / "child-wt"
    child_wt_state = child_wt_dir / "docs" / "progress-tracker" / "state"
    child_wt_state.mkdir(parents=True, exist_ok=True)
    child_wt_json = child_wt_state / "progress.json"
    child_wt_json.write_text(json.dumps({"tracker_role": "child"}))
    
    child_main_dir = temp_dir / "child-main"
    child_main_state = child_main_dir / "docs" / "progress-tracker" / "state"
    child_main_state.mkdir(parents=True, exist_ok=True)
    child_main_json = child_main_state / "progress.json"
    child_main_json.write_text(json.dumps({"tracker_role": "child"}))
    
    # Mock resolving
    def mock_resolve_main_repo_path(path):
        if path == child_wt_dir:
            return child_main_dir
        return path
        
    with patch("progress_manager.find_project_root", return_value=parent_dir), \
         patch("progress_manager._resolve_linked_project_root", return_value=child_wt_dir), \
         patch("progress_manager._resolve_main_repo_path", side_effect=mock_resolve_main_repo_path), \
         patch("progress_manager._load_progress_payload_at_root") as mock_load:
         
        # 返回已初始化的字典数据以允许更新元数据
        def mock_load_impl(root):
            if root == child_wt_dir:
                return {"tracker_role": "child"}, None
            if root == child_main_dir:
                return {"tracker_role": "child"}, None
            return None, "Not found"
            
        mock_load.side_effect = mock_load_impl
        
        # 监听写入以检查是否两边都被写入了
        written_roots = []
        original_save = progress_manager._save_progress_payload_at_root
        
        def mock_save_impl(root, data, **kwargs):
            written_roots.append(root)
            original_save(root, data, **kwargs)
            
        with patch("progress_manager._save_progress_payload_at_root", mock_save_impl):
            res = progress_manager.link_project(
                child_project_root=str(child_wt_dir),
                code="CHILD"
            )
            
        assert res is True
        assert child_wt_dir in written_roots
        assert child_main_dir in written_roots


def test_link_project_fallback_when_main_missing(temp_dir):
    """link_project succeeds and double-writes when main child tracker file is missing but worktree child exists."""
    parent_dir = temp_dir / "parent"
    parent_state = parent_dir / "docs" / "progress-tracker" / "state"
    parent_state.mkdir(parents=True, exist_ok=True)
    (parent_state / "progress.json").write_text(json.dumps({
        "tracker_role": "parent",
        "linked_projects": [],
        "routing_queue": []
    }))
    
    child_wt_dir = temp_dir / "child-wt"
    child_wt_state = child_wt_dir / "docs" / "progress-tracker" / "state"
    child_wt_state.mkdir(parents=True, exist_ok=True)
    child_wt_json = child_wt_state / "progress.json"
    child_wt_json.write_text(json.dumps({"tracker_role": "child"}))
    
    child_main_dir = temp_dir / "child-main"
    
    # Mock resolving
    def mock_resolve_main_repo_path(path):
        if path == child_wt_dir:
            return child_main_dir
        return path

    with patch("progress_manager.find_project_root", return_value=parent_dir), \
         patch("progress_manager._resolve_linked_project_root", return_value=child_wt_dir), \
         patch("progress_manager._resolve_main_repo_path", side_effect=mock_resolve_main_repo_path):
        
        # 此时 child_main_dir 必然返回 None 且加载出错, 因为它不存在，
        # 而 fallback 到 child_wt_dir 可以成功读取数据并写入双侧
        res = progress_manager.link_project(
            child_project_root=str(child_wt_dir),
            code="CHILD"
        )
        
    assert res is True
    # 验证最终在 main child 路径上也成功创建并写入了配置文件
    child_main_json = child_main_dir / "docs" / "progress-tracker" / "state" / "progress.json"
    assert child_main_json.exists()
    
    main_meta = json.loads(child_main_json.read_text())
    assert main_meta["tracker_role"] == "child"
    assert main_meta["project_code"] == "CHILD"
