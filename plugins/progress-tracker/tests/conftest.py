"""
Pytest configuration and shared fixtures for progress_tracker tests.
"""

import json
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import sys

# Add the hooks/scripts directory to the path so we can import progress_manager
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


# Import progress_manager module functions
import progress_manager


@pytest.fixture(autouse=True)
def reset_progress_tracker_module_state():
    """Reset module-level root/storage caches between tests."""
    progress_manager._PROJECT_ROOT_OVERRIDE = None
    progress_manager._REPO_ROOT = None
    progress_manager._STORAGE_READY_ROOT = None

    try:
        import project_memory  # type: ignore

        project_memory._PROJECT_ROOT_OVERRIDE = None
        project_memory._REPO_ROOT = None
        project_memory._STORAGE_READY_ROOT = None
    except Exception:
        pass

    yield

    progress_manager._PROJECT_ROOT_OVERRIDE = None
    progress_manager._REPO_ROOT = None
    progress_manager._STORAGE_READY_ROOT = None

    try:
        import project_memory  # type: ignore

        project_memory._PROJECT_ROOT_OVERRIDE = None
        project_memory._REPO_ROOT = None
        project_memory._STORAGE_READY_ROOT = None
    except Exception:
        pass


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_cwd)


@pytest.fixture
def sample_progress_data():
    """Sample progress data for testing."""
    return {
        "project_name": "Test Project",
        "created_at": "2024-01-01T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Feature 1",
                "test_steps": ["Step 1", "Step 2"],
                "completed": True,
                "completed_at": "2024-01-02T00:00:00Z",
                "commit_hash": "abc123"
            },
            {
                "id": 2,
                "name": "Feature 2",
                "test_steps": ["Step A", "Step B"],
                "completed": False
            },
            {
                "id": 3,
                "name": "Feature 3",
                "test_steps": ["Step X"],
                "completed": False
            }
        ],
        "current_feature_id": None
    }


@pytest.fixture
def progress_file(temp_dir, sample_progress_data):
    """Create a progress.json file with sample data."""
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    progress_file = state_dir / "progress.json"
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(sample_progress_data, f)

    return progress_file


@pytest.fixture
def mock_git_repo(temp_dir):
    """Create a mock git repository."""
    # Initialize git repo
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, capture_output=True)

    # Create initial commit
    (temp_dir / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_dir, capture_output=True)

    return temp_dir


@pytest.fixture
def clean_filesystem():
    """Fixture that provides a clean filesystem state."""
    # This fixture can be used to ensure no leftover test artifacts
    yield
    # Cleanup happens automatically via tmp_path fixture


@pytest.fixture
def patch_cwd(temp_dir):
    """Patch the current working directory."""
    with patch("pathlib.Path.cwd", return_value=temp_dir):
        yield temp_dir


@pytest.fixture
def patch_find_project_root(temp_dir):
    """Patch find_project_root to return temp_dir."""
    with patch("progress_manager.find_project_root", return_value=temp_dir):
        yield temp_dir


@pytest.fixture
def in_progress_data():
    """Progress data with a feature currently in progress."""
    return {
        "project_name": "In Progress Project",
        "created_at": "2024-01-01T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Completed Feature",
                "test_steps": ["Step 1"],
                "completed": True,
                "completed_at": "2024-01-02T00:00:00Z",
                "commit_hash": "done123"
            },
            {
                "id": 2,
                "name": "In Progress Feature",
                "test_steps": ["Step A", "Step B", "Step C"],
                "completed": False
            }
        ],
        "current_feature_id": 2,
        "workflow_state": {
            "phase": "execution",
            "plan_path": "docs/plans/feature-2-in-progress.md",
            "completed_tasks": [1, 2],
            "total_tasks": 5,
            "current_task": 3,
            "updated_at": "2024-01-03T00:00:00Z"
        }
    }


@pytest.fixture
def in_progress_file(temp_dir, in_progress_data):
    """Create a progress.json file with in-progress feature."""
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    plans_dir = temp_dir / "docs" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / "feature-2-in-progress.md").write_text(
        "# Plan\n\n## Tasks\n- Task 1\n\n## Acceptance Mapping\n- Step A -> Verification\n\n## Risks\n- None\n",
        encoding="utf-8",
    )

    progress_file = state_dir / "progress.json"
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(in_progress_data, f)

    return progress_file


@pytest.fixture()
def project_scope(tmp_path, monkeypatch):
    """隔离 progress_manager 和 audit_log 到 tmp_path。

    - 直接设置 _PROJECT_ROOT_OVERRIDE（不走 configure_project_scope 的 git 检查，
      因为 tmp_path 通常在仓库外，会被 resolve_target_project_root 拒绝）
    - 创建 docs/progress-tracker/state/ 目录结构
    - 不设置 PROGRESS_TRACKER_STATE_DIR：核心测试通过 project_root 参数路由
      （只有 audit_log 模块单元测试才用 env var）
    - 测试结束后重置全局状态

    用法：
        def test_foo(project_scope):
            root = project_scope["root"]
            state_dir = project_scope["state_dir"]
            # 通过 audit_log.read_audit_log(project_root=str(root)) 读取
    """
    root = tmp_path
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # 直接注入 project root，绕过 git 检查（tmp_path 可能不在 git repo 内）
    progress_manager._PROJECT_ROOT_OVERRIDE = root
    progress_manager._STORAGE_READY_ROOT = None  # 清除路径缓存

    yield {"root": root, "state_dir": state_dir}

    # 测试结束后重置全局状态
    progress_manager._PROJECT_ROOT_OVERRIDE = None
    progress_manager._STORAGE_READY_ROOT = None


def _write_progress(state_dir: Path, features: list, current_id=None) -> Path:
    """辅助函数：写 progress.json 到隔离的 state_dir。"""
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": features,
        "current_feature_id": current_id,
    }
    path = state_dir / "progress.json"
    path.write_text(json.dumps(data))
    return path


def _write_audit_event(state_dir: Path, event_type: str,
                        feature_id=None, ts="2026-04-24T12:00:00Z",
                        counter=[0]):
    """辅助函数：直接写入 audit 事件（绕过白名单，用于测试数据准备）。

    注意：此函数直接写文件，不经过 append_audit_record，用于模拟历史数据
    或在测试中准备不走白名单校验的测试数据。
    """
    counter[0] += 1
    path = state_dir / "audit.log"
    record = {
        "id": f"AUDIT-{counter[0]:03d}",
        "tx_id": f"TX-{counter[0]:08d}",
        "timestamp": ts,
        "event_type": event_type,
    }
    if feature_id is not None:
        record["feature_id"] = feature_id
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


@pytest.fixture
def execution_complete_data():
    """Progress data where execution is complete but feature not yet marked done."""
    return {
        "project_name": "Execution Complete Project",
        "created_at": "2024-01-01T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Feature To Test",
                "test_steps": ["Test 1", "Test 2"],
                "completed": False
            }
        ],
        "current_feature_id": 1,
        "workflow_state": {
            "phase": "execution_complete",
            "plan_path": "docs/plans/feature-1-execution-complete.md",
            "completed_tasks": [1, 2, 3, 4, 5],
            "total_tasks": 5,
            "current_task": 6,
            "updated_at": "2024-01-03T00:00:00Z"
        }
    }
