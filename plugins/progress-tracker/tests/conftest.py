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
    claude_dir = temp_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    progress_file = claude_dir / "progress.json"
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
    claude_dir = temp_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    plans_dir = temp_dir / "docs" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / "feature-2-in-progress.md").write_text(
        "# Plan\n\n## Tasks\n- Task 1\n\n## Acceptance Mapping\n- Step A -> Verification\n\n## Risks\n- None\n",
        encoding="utf-8",
    )

    progress_file = claude_dir / "progress.json"
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(in_progress_data, f)

    return progress_file


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
