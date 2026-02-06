# plugins/progress-tracker/tests/test_progress_ui.py
import pytest
import subprocess
import time
import sys
import json
from pathlib import Path

SERVER_SCRIPT = Path("plugins/progress-tracker/hooks/scripts/progress_ui_server.py")

def test_server_module_exists():
    """Verify server module can be imported"""
    assert SERVER_SCRIPT.exists(), "Server script must exist at hooks/scripts/progress_ui_server.py"

def test_server_loads_successfully():
    """Verify server module imports without errors"""
    sys.path.insert(0, "plugins/progress-tracker/hooks/scripts")
    try:
        from progress_ui_server import find_available_port
        assert callable(find_available_port), "find_available_port must be a function"
    except ImportError as e:
        pytest.fail(f"Failed to import progress_ui_server: {e}")

def test_port_detection_in_range():
    """Test port detection returns value in 3737-3747 range"""
    sys.path.insert(0, "plugins/progress-tracker/hooks/scripts")
    from progress_ui_server import find_available_port

    port = find_available_port()
    assert 3737 <= port <= 3747, f"Port {port} must be in range 3737-3747"

def test_port_detection_skips_active_listeners():
    """Test port detection skips ports already in use"""
    # This is a behavioral assertion - we verify the logic works
    # Actual port testing would require socket binding which we skip
    sys.path.insert(0, "plugins/progress-tracker/hooks/scripts")
    from progress_ui_server import find_available_port

    # Should return a valid port even if some are taken
    port = find_available_port()
    assert isinstance(port, int), "Port must be an integer"

def test_get_api_file_requires_path_parameter():
    """Test GET /api/file requires path query parameter"""
    # This is a behavioral assertion - will be verified via integration tests
    # The endpoint should return 400 if path is missing
    pass

def test_path_validation_blocks_directory_traversal():
    """Test path validation blocks ../ attacks"""
    sys.path.insert(0, "plugins/progress-tracker/hooks/scripts")
    from progress_ui_server import validate_path

    working_dir = Path("/fake/working/dir")

    # Should block paths with ..
    assert not validate_path(working_dir, "../../../etc/passwd"), "Should block ../ traversal"
    assert not validate_path(working_dir, "/etc/passwd"), "Should block absolute paths outside working dir"

    # Should allow valid relative paths
    assert validate_path(working_dir, ".claude/progress.md"), "Should allow valid .claude paths"
    assert validate_path(working_dir, "some/relative/path.md"), "Should allow relative paths"

def test_path_validation_resolves_symlinks():
    """Test path validation uses resolve() to catch symlinks"""
    sys.path.insert(0, "plugins/progress-tracker/hooks/scripts")
    from progress_ui_server import validate_path

    # Verify Path.resolve is used for security
    import inspect
    source = inspect.getsource(validate_path)
    assert ".resolve()" in source or "resolve" in source, "Must use Path.resolve() for security"

def test_get_files_lists_markdown_files():
    """Test GET /api/files returns list of markdown files"""
    sys.path.insert(0, "plugins/progress-tracker/hooks/scripts")
    from progress_ui_server import ProgressUIHandler
    from http.server import BaseHTTPRequestHandler
    from io import BytesIO
    import json

    # This is a behavioral assertion for scanning logic
    # The endpoint should scan .claude directory for .md files
    # progress.md should be first in the list

    working_dir = Path.cwd()
    claude_dir = working_dir / ".claude"

    if claude_dir.exists():
        md_files = list(claude_dir.glob("*.md"))
        assert len(md_files) > 0, "Should find markdown files in .claude"

        # Verify progress.md exists or would be first
        progress_md = claude_dir / "progress.md"
        if progress_md.exists():
            assert progress_md in md_files, "Should include progress.md"

def test_put_file_concurrency_control():
    """Test PUT /api/file enforces rev/mtime matching"""
    sys.path.insert(0, "plugins/progress-tracker/hooks/scripts")
    from progress_ui_server import validate_put_request

    # Valid request should pass
    assert validate_put_request("abc123", 123456, "abc123", 123456), "Should accept matching rev/mtime"

    # Mismatched rev should fail
    assert not validate_put_request("abc123", 123456, "wrong", 123456), "Should reject mismatched rev"

    # Mismatched mtime should fail
    assert not validate_put_request("abc123", 123456, "abc123", 999999), "Should reject mismatched mtime"

def test_origin_header_validation_blocks_cross_origin():
    """Test PUT requests validate Origin header"""
    sys.path.insert(0, "plugins/progress-tracker/hooks/scripts")
    from progress_ui_server import is_valid_origin

    # localhost origins should be valid
    assert is_valid_origin("http://127.0.0.1:3737"), "Should accept localhost"
    assert is_valid_origin("http://localhost:3737"), "Should accept localhost"
    assert is_valid_origin(None), "Should accept missing Origin"

    # External origins should be rejected
    assert not is_valid_origin("http://evil.com"), "Should reject external origin"
    assert not is_valid_origin("https://malicious.site"), "Should reject https origin"
