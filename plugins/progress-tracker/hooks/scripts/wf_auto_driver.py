"""
wf_auto_driver.py — 薄层自动驱动器（hook 入口）

职责：
1. 读取 workflow_state.phase
2. 调用 wf_state_machine.compute_next_action()
3. 写回 workflow_state.pending_action（在锁内，直接更新 progress.json）
4. fail-open：任何异常静默退出 0，不阻塞 Claude Code

入口：
  python wf_auto_driver.py [--project-root <path>]
"""

import sys
from pathlib import Path
from typing import Optional

# 将 scripts 目录加入路径（支持直接执行和测试导入两种场景）
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from wf_state_machine import compute_next_action


def run(project_root: Optional[str] = None) -> None:
    """
    主入口：fail-open 包装。

    所有异常均静默捕获，保证不阻塞 Claude Code lifecycle event。
    """
    try:
        _drive(project_root)
    except Exception:
        pass  # fail-open


def _drive(project_root: Optional[str] = None) -> None:
    """
    内部驱动逻辑（可被测试直接调用）。

    流程：
    1. 直接从 project_root 路径读取 progress.json（不通过 scope 校验）
    2. 检查 current_feature_id 和 workflow_state
    3. 计算 pending_action
    4. 写回（atomic，使用 lifecycle_state_machine.acquire_lock）
    """
    data = _load_progress_direct(project_root)
    if not data:
        return

    current_id = data.get("current_feature_id")
    if not current_id:
        return

    workflow_state = data.get("workflow_state")
    if not workflow_state or not isinstance(workflow_state, dict):
        return

    phase = workflow_state.get("phase")
    context = {
        "completed_tasks": workflow_state.get("completed_tasks") or [],
        "total_tasks": workflow_state.get("total_tasks") or 0,
    }

    pending_action = compute_next_action(phase, context)

    if pending_action is None:
        return

    _write_back_pending_action(pending_action, project_root)


def _load_progress_direct(project_root: Optional[str]) -> dict:
    """直接读取 progress.json，不依赖 configure_project_scope。"""
    from prog_paths import find_project_root, ensure_tracker_layout, ensure_storage_migrated, get_state_dir
    import json as _json

    root = Path(project_root) if project_root is not None else find_project_root()
    ensure_tracker_layout(root)
    ensure_storage_migrated(root)
    state_dir = get_state_dir(root)

    progress_file = state_dir / "progress.json"
    if not progress_file.exists():
        return {}

    try:
        return _json.loads(progress_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_back_pending_action(pending_action: str, project_root: Optional[str]) -> None:
    """在文件锁内原子写回 pending_action。"""
    from prog_paths import find_project_root
    from lifecycle_state_machine import acquire_lock
    from pathlib import Path
    import json
    import os

    # 找到 progress.json 路径，使用 prog_paths.find_project_root() 代替 progress_manager.find_project_root()
    project_path = Path(project_root) if project_root else find_project_root()
    state_dir = project_path / "docs" / "progress-tracker" / "state"
    progress_file = state_dir / "progress.json"
    lock_path = state_dir / "progress.lock"

    if not progress_file.exists():
        return

    with acquire_lock(lock_path):
        data = json.loads(progress_file.read_text(encoding="utf-8"))
        workflow_state = data.get("workflow_state")
        if not workflow_state:
            return
        workflow_state["pending_action"] = pending_action
        # 原子写入
        tmp = progress_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, progress_file)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="wf_auto_driver — 自动推进工作流状态"
    )
    parser.add_argument("--project-root", default=None, help="项目根目录")
    args = parser.parse_args()
    run(project_root=args.project_root)
