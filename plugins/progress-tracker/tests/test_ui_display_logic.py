#!/usr/bin/env python3
"""
Tests for UI Display Logic Based on Development Stage

Verifies that the HTML UI correctly displays buttons and titles
based on the development_stage field from the API response.
"""

import pytest
import json
from pathlib import Path


@pytest.fixture
def working_dir(tmp_path):
    """Create a temporary working directory with test data"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    # Create test progress.json with Feature 2 as active
    progress_data = {
        "project_name": "Test Project",
        "created_at": "2026-02-12T00:00:00.000000Z",
        "features": [
            {
                "id": 1,
                "name": "Feature 1",
                "test_steps": ["Step 1"],
                "completed": True,
                "completed_at": "2026-02-12T01:00:00.000000Z"
            },
            {
                "id": 2,
                "name": "Feature 2 - Planning Stage",
                "test_steps": ["Step 1"],
                "completed": False,
                "development_stage": "planning"
            },
            {
                "id": 3,
                "name": "Feature 3 - Developing",
                "test_steps": ["Step 1"],
                "completed": False,
                "development_stage": "developing"
            },
            {
                "id": 4,
                "name": "Feature 4 - Completed",
                "test_steps": ["Step 1"],
                "completed": True,
                "development_stage": "completed",
                "completed_at": "2026-02-12T02:00:00.000000Z"
            }
        ],
        "current_feature_id": None,
        "bugs": [],
        "schema_version": "2.0"
    }

    progress_file = claude_dir / "progress.json"
    progress_file.write_text(json.dumps(progress_data, indent=2))

    return tmp_path


@pytest.fixture
def test_client(working_dir):
    """Create a test client for the HTTP server"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "scripts"))

    from progress_ui_server import create_handler
    from io import BytesIO
    from unittest.mock import Mock

    handler_class = create_handler(working_dir)

    class TestClient:
        def __init__(self, handler_class, working_dir):
            self.handler_class = handler_class
            self.working_dir = working_dir

        def get_json(self, path):
            """Get JSON response from an endpoint"""
            # Create mock request/response
            request = Mock()
            request.makefile = Mock(return_value=BytesIO())

            # Create handler
            handler = self.handler_class(request, ('127.0.0.1', 0), None)
            handler.path = path

            # Capture response
            response_data = BytesIO()
            handler.wfile = response_data

            sent_status = [200]
            sent_headers = {}

            def mock_send_response(code):
                sent_status[0] = code

            def mock_send_header(key, value):
                sent_headers[key] = value

            def mock_end_headers():
                pass

            handler.send_response = mock_send_response
            handler.send_header = mock_send_header
            handler.end_headers = mock_end_headers

            # Handle request
            from urllib.parse import urlparse
            parsed = urlparse(path)

            if parsed.path == "/api/status-detail":
                detail, status_code = handler.handle_get_status_detail(parsed)
                handler.send_json(detail, status_code)

            response_bytes = response_data.getvalue()
            if response_bytes:
                return sent_status[0], json.loads(response_bytes.decode())
            return sent_status[0], {}

    return TestClient(handler_class, working_dir)


# ========== RED Tests (Failing Tests for Feature 17) ==========

def test_ui_displays_prog_start_button_when_planning(test_client, working_dir):
    """
    FAILING TEST: When feature is in 'planning' stage and is active,
    the drawer should display "开始开发" button with /prog start command.
    """
    # Set Feature 2 as active (planning stage)
    progress_file = working_dir / ".claude" / "progress.json"
    progress_data = json.loads(progress_file.read_text())
    progress_data["current_feature_id"] = 2
    progress_file.write_text(json.dumps(progress_data, indent=2))

    status_code, data = test_client.get_json("/api/status-detail?panel=next")

    # Verify response contains correct title for active feature
    assert data["title"] == "当前功能详情", \
        f"Expected title '当前功能详情' for active feature, got '{data.get('title')}'"

    # Verify suggested action contains "开始开发" button
    assert len(data["actions"]) > 0, "Expected actions to be present"
    action = data["actions"][0]
    assert action["label"] == "开始开发", \
        f"Expected button label '开始开发', got '{action.get('label')}'"
    assert action["command"] == "/prog start", \
        f"Expected command '/prog start', got '{action.get('command')}'"


def test_ui_displays_prog_done_button_when_developing(test_client, working_dir):
    """
    FAILING TEST: When feature is in 'developing' stage and is active,
    the drawer should display "完成此功能" button with /prog done command.
    """
    # Set Feature 3 as active (developing stage)
    progress_file = working_dir / ".claude" / "progress.json"
    progress_data = json.loads(progress_file.read_text())
    progress_data["current_feature_id"] = 3
    progress_file.write_text(json.dumps(progress_data, indent=2))

    status_code, data = test_client.get_json("/api/status-detail?panel=next")

    # Verify response contains correct title for active feature
    assert data["title"] == "当前功能详情", \
        f"Expected title '当前功能详情' for active feature, got '{data.get('title')}'"

    # Verify suggested action contains "完成此功能" button
    assert len(data["actions"]) > 0, "Expected actions to be present"
    action = data["actions"][0]
    assert action["label"] == "完成此功能", \
        f"Expected button label '完成此功能', got '{action.get('label')}'"
    assert action["command"] == "/prog done", \
        f"Expected command '/prog done', got '{action.get('command')}'"


def test_ui_displays_next_step_title_when_pending(test_client, working_dir):
    """
    FAILING TEST: When feature is pending (not active),
    the drawer title should show "下一步详情" not "当前功能详情".
    """
    # Leave current_feature_id as null (no active feature)
    # This should make Feature 2 a pending feature
    progress_file = working_dir / ".claude" / "progress.json"
    progress_data = json.loads(progress_file.read_text())
    progress_data["current_feature_id"] = None
    progress_file.write_text(json.dumps(progress_data, indent=2))

    status_code, data = test_client.get_json("/api/status-detail?panel=next")

    # Verify response contains "下一步详情" for pending features
    assert data["title"] == "下一步详情", \
        f"Expected title '下一步详情' for pending feature, got '{data.get('title')}'"

    # Should not have suggested actions for pending feature
    # (actions are only for active features)


def test_ui_marks_completed_feature_as_completed(test_client, working_dir):
    """
    FAILING TEST: Completed features should be displayed with appropriate
    '已完成' marker and no suggested actions.
    """
    # Check Feature 4 which is already completed
    progress_file = working_dir / ".claude" / "progress.json"
    progress_data = json.loads(progress_file.read_text())
    # Make Feature 4 the "next" feature to display
    for i, f in enumerate(progress_data["features"]):
        if i < 3:
            f["completed"] = True
    progress_file.write_text(json.dumps(progress_data, indent=2))

    status_code, data = test_client.get_json("/api/status-detail?panel=next")

    # Verify summary shows completed status
    assert "已完成" in data["summary"], \
        f"Expected '已完成' in summary, got: {data.get('summary')}"


def test_ui_displays_correct_stage_label_in_summary(test_client, working_dir):
    """
    FAILING TEST: The summary should include the correct stage label
    (规划中/开发中/已完成) based on development_stage field.
    """
    # Set Feature 2 (planning) as active
    progress_file = working_dir / ".claude" / "progress.json"
    progress_data = json.loads(progress_file.read_text())
    progress_data["current_feature_id"] = 2
    progress_file.write_text(json.dumps(progress_data, indent=2))

    status_code, data = test_client.get_json("/api/status-detail?panel=next")

    # Verify summary includes stage label
    assert "规划中" in data["summary"], \
        f"Expected '规划中' (planning label) in summary, got: {data.get('summary')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
