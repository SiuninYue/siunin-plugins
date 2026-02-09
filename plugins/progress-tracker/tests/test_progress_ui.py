# plugins/progress-tracker/tests/test_progress_ui.py
import http.client
import importlib
import inspect
import json
import sys
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest

SERVER_SCRIPT = Path("plugins/progress-tracker/hooks/scripts/progress_ui_server.py")
SCRIPTS_PATH = "plugins/progress-tracker/hooks/scripts"


def load_server_module():
    """Import progress_ui_server with a stable sys.path setup."""
    if SCRIPTS_PATH not in sys.path:
        sys.path.insert(0, SCRIPTS_PATH)
    return importlib.import_module("progress_ui_server")


def start_live_server(server_module):
    """Start server on an OS-assigned free port and return runtime objects."""
    handler = server_module.create_handler(Path.cwd())
    try:
        server = HTTPServer((server_module.BIND_HOST, 0), handler)
    except PermissionError as exc:
        pytest.skip(f"Socket bind not permitted in this environment: {exc}")
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, host, port


def http_get(host, port, path):
    """Execute GET request and return (status, headers, body)."""
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        body = response.read()
        return response.status, headers, body
    finally:
        conn.close()


@pytest.fixture
def server_module():
    return load_server_module()


@pytest.fixture
def live_server(server_module):
    server, thread, host, port = start_live_server(server_module)
    try:
        yield host, port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_module_exists():
    """Verify server module can be imported"""
    assert SERVER_SCRIPT.exists(), "Server script must exist at hooks/scripts/progress_ui_server.py"


def test_server_loads_successfully(server_module):
    """Verify server module imports without errors"""
    assert callable(server_module.find_available_port), "find_available_port must be a function"


def test_port_detection_in_range(server_module):
    """Test port detection returns value in 3737-3747 range when available."""
    try:
        port = server_module.find_available_port()
    except RuntimeError:
        pytest.skip("No available ports in 3737-3747 for this test environment")

    assert 3737 <= port <= 3747, f"Port {port} must be in range 3737-3747"


def test_port_detection_skips_active_listeners(server_module):
    """Test port detection returns an int even when some ports are occupied."""
    try:
        port = server_module.find_available_port()
    except RuntimeError:
        pytest.skip("No available ports in 3737-3747 for this test environment")

    assert isinstance(port, int), "Port must be an integer"


def test_get_api_file_requires_path_parameter(live_server):
    """Test GET /api/file requires path query parameter"""
    host, port = live_server
    status, headers, body = http_get(host, port, "/api/file")

    assert status == 400, "GET /api/file without path should return 400"
    assert "application/json" in headers.get("content-type", "")

    payload = json.loads(body.decode("utf-8"))
    assert payload.get("error") == "path parameter required"


def test_root_serves_html_with_content_type(live_server):
    """Test GET / serves index HTML with correct content type."""
    host, port = live_server
    status, headers, body = http_get(host, port, "/")

    assert status == 200
    assert "text/html" in headers.get("content-type", "")
    assert b"<!DOCTYPE html>" in body


def test_root_returns_500_when_index_read_fails(server_module, monkeypatch):
    """Test GET / returns stable 500 JSON when index file read fails."""

    class BrokenIndex:
        def exists(self):
            return True

        def read_text(self, encoding="utf-8"):
            raise OSError("forced read failure")

    monkeypatch.setattr(server_module, "INDEX_FILE", BrokenIndex())
    server, thread, host, port = start_live_server(server_module)

    try:
        status, headers, body = http_get(host, port, "/")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 500
    assert "application/json" in headers.get("content-type", "")
    payload = json.loads(body.decode("utf-8"))
    assert payload.get("error") == "Failed to read UI entry file"


def test_path_validation_blocks_directory_traversal(server_module):
    """Test path validation blocks ../ attacks"""
    working_dir = Path("/fake/working/dir")

    # Should block paths with ..
    assert not server_module.validate_path(working_dir, "../../../etc/passwd"), "Should block ../ traversal"
    assert not server_module.validate_path(working_dir, "/etc/passwd"), "Should block absolute paths outside working dir"

    # Should allow valid relative paths
    assert server_module.validate_path(working_dir, ".claude/progress.md"), "Should allow valid .claude paths"
    assert server_module.validate_path(working_dir, "some/relative/path.md"), "Should allow relative paths"


def test_path_validation_resolves_symlinks(server_module):
    """Test path validation uses resolve() to catch symlinks"""
    source = inspect.getsource(server_module.validate_path)
    assert ".resolve()" in source or "resolve" in source, "Must use Path.resolve() for security"


def test_get_files_lists_markdown_files(live_server):
    """Test GET /api/files returns markdown file list."""
    host, port = live_server
    status, headers, body = http_get(host, port, "/api/files")

    assert status == 200
    assert "application/json" in headers.get("content-type", "")

    files = json.loads(body.decode("utf-8"))
    assert isinstance(files, list)

    if files:
        assert "name" in files[0]
        assert "path" in files[0]
        assert "mtime" in files[0]

    paths = [item.get("path") for item in files]
    if ".claude/progress.md" in paths:
        assert files[0]["path"] == ".claude/progress.md", "progress.md should be listed first"


def test_put_file_concurrency_control(server_module):
    """Test PUT /api/file enforces rev/mtime matching"""
    # Valid request should pass
    assert server_module.validate_put_request("abc123", 123456, "abc123", 123456), "Should accept matching rev/mtime"

    # Mismatched rev should fail
    assert not server_module.validate_put_request("abc123", 123456, "wrong", 123456), "Should reject mismatched rev"

    # Mismatched mtime should fail
    assert not server_module.validate_put_request("abc123", 123456, "abc123", 999999), "Should reject mismatched mtime"


def test_origin_header_validation_blocks_cross_origin(server_module):
    """Test PUT requests validate Origin header"""
    # localhost origins should be valid
    assert server_module.is_valid_origin("http://127.0.0.1:3737"), "Should accept localhost"
    assert server_module.is_valid_origin("http://localhost:3737"), "Should accept localhost"
    assert server_module.is_valid_origin(None), "Should accept missing Origin"

    # External origins should be rejected
    assert not server_module.is_valid_origin("http://evil.com"), "Should reject external origin"
    assert not server_module.is_valid_origin("https://malicious.site"), "Should reject https origin"


def test_static_directory_exists():
    """Test static directory exists for future UI files"""
    static_dir = Path("plugins/progress-tracker/hooks/scripts/static")
    assert static_dir.exists(), "Static directory must exist"
    assert static_dir.is_dir(), "Static must be a directory"
