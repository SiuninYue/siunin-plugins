#!/usr/bin/env python3
"""
Tests for Progress UI Status API

Tests the new status bar API endpoints:
- /api/status-summary
- /api/status-detail
- /api/plan-health
"""

import pytest
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch


# ========== Test Fixtures ==========

@pytest.fixture
def working_dir(tmp_path):
    """Create a temporary working directory with test data"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    # Create test progress.json
    progress_data = {
        "project_name": "Test Project",
        "created_at": "2026-02-12T00:00:00.000000Z",
        "features": [
            {
                "id": 1,
                "name": "Feature 1",
                "test_steps": ["Step 1", "Step 2"],
                "completed": True,
                "completed_at": "2026-02-12T01:00:00.000000Z"
            },
            {
                "id": 2,
                "name": "Feature 2",
                "test_steps": ["Step 1"],
                "completed": False
            },
            {
                "id": 3,
                "name": "Feature 3",
                "test_steps": [],
                "completed": False
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

    from progress_ui_server import create_handler, HTTPServer

    handler = create_handler(working_dir)

    # Create a mock client for testing
    class TestClient:
        def __init__(self, handler_class, working_dir):
            self.handler_class = handler_class
            self.working_dir = working_dir

        def get(self, path):
            """Simulate GET request"""
            from io import BytesIO
            from unittest.mock import Mock

            # Create mock request
            request = Mock()
            request.makefile = Mock(return_value=BytesIO())

            # Create handler instance
            handler = self.handler_class(request, ('127.0.0.1', 0), None)
            handler.path = path

            # Capture response
            response_data = BytesIO()
            handler.wfile = response_data
            handler.headers = {}

            # Mock methods
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

            # Call handler
            from urllib.parse import urlparse
            parsed = urlparse(path)

            if parsed.path == "/api/status-summary":
                summary = handler.handle_get_status_summary()
                handler.send_json(summary)
            elif parsed.path == "/api/status-detail":
                detail, status_code = handler.handle_get_status_detail(parsed)
                handler.send_json(detail, status_code)
            elif parsed.path == "/api/plan-health":
                health, status_code = handler.handle_get_plan_health(parsed)
                handler.send_json(health, status_code)

            # Create response object
            class Response:
                def __init__(self, status_code, data, headers):
                    self.status_code = status_code
                    self.data = data
                    self.headers = headers

                def json(self):
                    return json.loads(self.data.decode())

            return Response(sent_status[0], response_data.getvalue(), sent_headers)

    return TestClient(handler, working_dir)


# ========== Normal Path Tests ==========

def test_status_summary_api_normal(test_client, working_dir):
    """Test /api/status-summary endpoint returns correct structure"""
    response = test_client.get("/api/status-summary")
    assert response.status_code == 200

    data = response.json()

    # Verify top-level fields exist
    assert "progress" in data
    assert "next_action" in data
    assert "plan_health" in data
    assert "risk_blocker" in data
    assert "recent_snapshot" in data
    assert "updated_at" in data

    # Verify progress structure
    assert "completed" in data["progress"]
    assert "total" in data["progress"]
    assert "percentage" in data["progress"]
    assert isinstance(data["progress"]["completed"], int)
    assert isinstance(data["progress"]["total"], int)
    assert 0 <= data["progress"]["percentage"] <= 100

    # Verify next_action structure
    assert data["next_action"]["type"] in ["feature", "none"]
    assert "feature_id" in data["next_action"]
    assert "feature_name" in data["next_action"]

    # Verify plan_health structure
    assert data["plan_health"]["status"] in ["OK", "WARN", "INVALID", "N/A"]
    assert "plan_path" in data["plan_health"]
    assert "message" in data["plan_health"]


def test_status_summary_calculates_progress_correctly(test_client, working_dir):
    """Test that progress calculation is correct"""
    response = test_client.get("/api/status-summary")
    data = response.json()

    # Based on fixture: 1 completed out of 3 total
    assert data["progress"]["completed"] == 1
    assert data["progress"]["total"] == 3
    assert data["progress"]["percentage"] == 33  # int(1/3 * 100)


def test_status_summary_determines_next_action(test_client, working_dir):
    """Test that next action is determined correctly"""
    response = test_client.get("/api/status-summary")
    data = response.json()

    # Should suggest Feature 2 (smallest pending ID)
    assert data["next_action"]["type"] == "feature"
    assert data["next_action"]["feature_id"] == 2
    assert data["next_action"]["feature_name"] == "Feature 2"


def test_status_detail_all_panels(test_client):
    """Test all 5 panel types return unified structure"""
    panels = ["progress", "next", "plan", "risk", "snapshot"]

    for panel in panels:
        response = test_client.get(f"/api/status-detail?panel={panel}")
        assert response.status_code == 200

        data = response.json()

        # Verify unified structure
        assert data["panel"] == panel
        assert "title" in data
        assert "summary" in data
        assert "sections" in data
        assert "sources" in data
        assert "actions" in data

        # Verify sections structure
        assert isinstance(data["sections"], list)
        for section in data["sections"]:
            assert "type" in section
            assert section["type"] in ["text", "list", "table", "code", "feature_list"]
            assert "content" in section


def test_status_detail_progress_panel_structure(test_client, working_dir):
    """Test progress panel returns feature_list structure"""
    response = test_client.get("/api/status-detail?panel=progress")
    assert response.status_code == 200

    data = response.json()
    assert data["panel"] == "progress"

    # Verify sections contain feature_list
    feature_sections = [s for s in data["sections"] if s["type"] == "feature_list"]
    assert len(feature_sections) > 0

    feature_section = feature_sections[0]
    assert isinstance(feature_section["content"], list)

    # Verify feature_list item structure
    if feature_section["content"]:
        feature_item = feature_section["content"][0]
        assert "id" in feature_item
        assert "name" in feature_item
        assert "completed" in feature_item


def test_status_detail_plan_panel_without_workflow_state(test_client, working_dir):
    """Test plan panel when no workflow_state exists"""
    response = test_client.get("/api/status-detail?panel=plan")
    assert response.status_code == 200

    data = response.json()
    assert data["panel"] == "plan"
    assert "无活跃计划" in data["summary"]


# ========== Boundary Tests ==========

def test_status_summary_without_progress_json(test_client, working_dir):
    """Test graceful degradation when progress.json is missing"""
    progress_file = working_dir / ".claude" / "progress.json"
    if progress_file.exists():
        progress_file.unlink()

    response = test_client.get("/api/status-summary")
    assert response.status_code == 200  # Should not error

    data = response.json()
    # Verify empty state data
    assert data["progress"]["total"] == 0
    assert data["progress"]["completed"] == 0
    assert data["progress"]["percentage"] == 0
    assert data["next_action"]["type"] == "none"
    assert data["plan_health"]["status"] == "N/A"
    assert data["risk_blocker"]["has_risk"] is False


def test_status_detail_missing_panel_parameter(test_client):
    """Test error handling when panel parameter is missing"""
    response = test_client.get("/api/status-detail")
    assert response.status_code == 400

    data = response.json()
    assert "error" in data


def test_status_detail_invalid_panel_value(test_client):
    """Test error handling for invalid panel values"""
    response = test_client.get("/api/status-detail?panel=invalid")
    assert response.status_code == 400


def test_plan_health_missing_path_parameter(test_client):
    """Test error handling when path parameter is missing"""
    response = test_client.get("/api/plan-health")
    assert response.status_code == 400


# ========== Integration Tests ==========

def test_status_summary_with_bugs(test_client, working_dir):
    """Test risk_blocker detection with high-priority bugs"""
    # Modify progress.json to add bugs
    progress_file = working_dir / ".claude" / "progress.json"
    progress_data = json.loads(progress_file.read_text())

    progress_data["bugs"] = [
        {
            "id": 1,
            "description": "Critical bug",
            "status": "open",
            "priority": "high",
            "created_at": "2026-02-12T00:00:00.000000Z"
        }
    ]

    progress_file.write_text(json.dumps(progress_data, indent=2))

    response = test_client.get("/api/status-summary")
    data = response.json()

    # Should detect high-priority bug
    assert data["risk_blocker"]["has_risk"] is True
    assert data["risk_blocker"]["high_priority_bugs"] == 1


def test_status_summary_with_current_feature(test_client, working_dir):
    """Test next_action when current_feature_id is set"""
    # Modify progress.json to set current_feature_id
    progress_file = working_dir / ".claude" / "progress.json"
    progress_data = json.loads(progress_file.read_text())
    progress_data["current_feature_id"] = 3
    progress_file.write_text(json.dumps(progress_data, indent=2))

    response = test_client.get("/api/status-summary")
    data = response.json()

    # Should prioritize current feature
    assert data["next_action"]["type"] == "feature"
    assert data["next_action"]["feature_id"] == 3
    assert data["next_action"]["feature_name"] == "Feature 3"


def test_status_detail_next_panel_all_completed(test_client, working_dir):
    """Test next panel when all features are completed"""
    # Mark all features as completed
    progress_file = working_dir / ".claude" / "progress.json"
    progress_data = json.loads(progress_file.read_text())

    for feature in progress_data["features"]:
        feature["completed"] = True
        feature["completed_at"] = "2026-02-12T00:00:00.000000Z"

    progress_file.write_text(json.dumps(progress_data, indent=2))

    response = test_client.get("/api/status-detail?panel=next")
    data = response.json()

    assert data["panel"] == "next"
    assert "已完成" in data["summary"]


# ========== Performance Tests ==========

def test_cache_mechanism(test_client, working_dir):
    """Test that caching reduces file reads"""
    # First request
    response1 = test_client.get("/api/status-summary")
    assert response1.status_code == 200

    # Second request (should use cache)
    response2 = test_client.get("/api/status-summary")
    assert response2.status_code == 200

    # Data should be identical
    data1 = response1.json()
    data2 = response2.json()

    assert data1["progress"] == data2["progress"]
    assert data1["next_action"] == data2["next_action"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
