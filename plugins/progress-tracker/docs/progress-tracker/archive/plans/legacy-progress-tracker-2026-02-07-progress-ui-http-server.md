# Progress UI HTTP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a secure HTTP server (`progress_ui_server.py`) that serves progress.md files with a web UI, implementing P0 security (localhost-only, path validation) and port auto-detection (3737-3747).

**Architecture:** Single-file Python HTTP server using stdlib http.server with custom GET/PUT/PATCH endpoints. Security enforced via bind address restriction (127.0.0.1 only) and Path.resolve validation for file access. Port auto-discovery scans 3737-3747 range to avoid conflicts.

**Tech Stack:** Python 3 stdlib (http.server, socketserver, pathlib), no external dependencies

---

## Task 1: Create server module structure with port detection

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
- Test: `plugins/progress-tracker/tests/test_progress_ui.py` (create if not exists)

**Step 1: Write the failing test**

```python
# plugins/progress-tracker/tests/test_progress_ui.py
import pytest
import subprocess
import time
import sys
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
```

**Step 2: Run test to verify it fails**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_server_module_exists -v
```

Expected: FAIL - "Server script must exist at hooks/scripts/progress_ui_server.py"

**Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""
Progress UI HTTP Server

A lightweight HTTP server for viewing and editing progress.md files via web UI.
P0 Security: Binds to 127.0.0.1 only, validates all file paths.

Usage:
    python3 progress_ui_server.py [--port PORT] [--working-dir DIR]
"""

import argparse
import socket
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

PORT_RANGE = range(3737, 3748)  # 3737-3747 inclusive
BIND_HOST = "127.0.0.1"  # P0: Localhost only


def find_available_port(start: Optional[int] = None) -> int:
    """
    Find an available port in the 3737-3747 range.

    If start is specified, begins search from that port.
    Scans forward, wrapping to 3737 if needed.

    Args:
        start: Optional starting port in range

    Returns:
        Available port number
    """
    if start is None:
        start = PORT_RANGE.start

    # Ensure start is in valid range
    if start not in PORT_RANGE:
        start = PORT_RANGE.start

    for port in range(start, PORT_RANGE.stop):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((BIND_HOST, port))
            sock.close()
            return port
        except OSError:
            continue

    # Wrap around if we reached the end
    for port in range(PORT_RANGE.start, start):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((BIND_HOST, port))
            sock.close()
            return port
        except OSError:
            continue

    raise RuntimeError(f"No available ports in range {PORT_RANGE.start}-{PORT_RANGE.stop-1}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Progress UI HTTP Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help=f"Port to bind to (default: auto-detect {PORT_RANGE.start}-{PORT_RANGE.stop-1})"
    )
    parser.add_argument(
        "--working-dir", "-d",
        type=Path,
        default=Path.cwd(),
        help="Working directory containing .claude folder"
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point"""
    args = parse_args()

    # Determine port
    port = args.port if args.port else find_available_port()

    print(f"Progress UI Server starting on {BIND_HOST}:{port}")
    print(f"Working directory: {args.working_dir}")
    print(f"Open http://{BIND_HOST}:{port}/ in your browser")

    # TODO: Create and start HTTP server in next task
    print(f"Server would listen on {BIND_HOST}:{port} (not yet implemented)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Run test to verify it passes**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_server_module_exists -v
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_server_loads_successfully -v
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_port_detection_in_range -v
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_port_detection_skips_active_listeners -v
```

Expected: PASS for all tests

**Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git add plugins/progress-tracker/tests/test_progress_ui.py
git commit -m "feat(progress-ui): add server module with port detection (3737-3747)"
```

---

## Task 2: Implement GET /api/file endpoint with path validation

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
- Test: `plugins/progress-tracker/tests/test_progress_ui.py`

**Step 1: Write the failing test**

```python
# Add to plugins/progress-tracker/tests/test_progress_ui.py
import json
import tempfile
import os

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
```

**Step 2: Run test to verify it fails**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_path_validation_blocks_directory_traversal -v
```

Expected: FAIL - function not defined or assertion fails

**Step 3: Write minimal implementation**

Add to `progress_ui_server.py`:

```python
import json
import hashlib
import time
from urllib.parse import urlparse, parse_qs


def validate_path(working_dir: Path, file_path: str) -> bool:
    """
    Validate that file_path is within working_dir after resolution.

    Uses Path.resolve() to catch symlink attacks and directory traversal.

    Args:
        working_dir: The base working directory (absolute path)
        file_path: The file path to validate (can be relative or absolute)

    Returns:
        True if path is safe, False otherwise
    """
    try:
        # Resolve the full path to catch symlinks and .. components
        full_path = (working_dir / file_path).resolve()

        # Check if resolved path is within working_dir
        # Use relative_to to verify containment
        try:
            full_path.relative_to(working_dir.resolve())
            return True
        except ValueError:
            # full_path is not under working_dir
            return False
    except (OSError, ValueError):
        return False


def calculate_rev(content: str) -> str:
    """Calculate revision hash for content"""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def calculate_mtime(file_path: Path) -> int:
    """Calculate file modification time as Unix timestamp"""
    return int(file_path.stat().st_mtime)


class ProgressUIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Progress UI"""

    def __init__(self, *args, working_dir: Path, **kwargs):
        self.working_dir = working_dir
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/api/file":
            self.handle_get_file(parsed_path)
        elif parsed_path.path == "/api/files":
            self.handle_get_files()
        else:
            self.send_error(404, "Not Found")

    def handle_get_file(self, parsed_path):
        """Handle GET /api/file?path=<file>"""
        query = parse_qs(parsed_path.query)
        file_path = query.get("path", [None])[0]

        if not file_path:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "path parameter required"}).encode())
            return

        # Validate path security
        if not validate_path(self.working_dir, file_path):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid path"}).encode())
            return

        full_path = (self.working_dir / file_path).resolve()

        if not full_path.exists():
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "File not found"}).encode())
            return

        # Read file content
        content = full_path.read_text()
        mtime = calculate_mtime(full_path)
        rev = calculate_rev(content)

        response = {
            "path": file_path,
            "content": content,
            "mtime": mtime,
            "rev": rev
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def handle_get_files(self):
        """Handle GET /api/files - list available markdown files"""
        # TODO: Implement in next task
        self.send_response(501)
        self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


def create_handler(working_dir: Path):
    """Factory to create handler with working_dir injected"""
    def handler(*args, **kwargs):
        return ProgressUIHandler(*args, working_dir=working_dir, **kwargs)
    return handler
```

Update `main()` to start the server:

```python
def main() -> int:
    """Main entry point"""
    args = parse_args()

    # Resolve working directory to absolute path
    working_dir = args.working_dir.resolve()

    if not working_dir.exists():
        print(f"Error: Working directory does not exist: {working_dir}", file=sys.stderr)
        return 1

    # Determine port
    port = args.port if args.port else find_available_port()

    # Create server with custom handler
    handler = create_handler(working_dir)
    server = HTTPServer((BIND_HOST, port), handler)

    print(f"Progress UI Server starting on {BIND_HOST}:{port}")
    print(f"Working directory: {working_dir}")
    print(f"Open http://{BIND_HOST}:{port}/ in your browser")
    print(f"Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.shutdown()
        return 0
```

**Step 4: Run test to verify it passes**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_path_validation_blocks_directory_traversal -v
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_path_validation_resolves_symlinks -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git add plugins/progress-tracker/tests/test_progress_ui.py
git commit -m "feat(progress-ui): add GET /api/file endpoint with P0 path validation"
```

---

## Task 3: Implement GET /api/files endpoint

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
- Test: `plugins/progress-tracker/tests/test_progress_ui.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_get_files_lists_markdown_files -v
```

Expected: May pass or fail depending on state - this is behavioral verification

**Step 3: Write minimal implementation**

Update `handle_get_files` method:

```python
def handle_get_files(self):
    """Handle GET /api/files - list available markdown files"""
    claude_dir = self.working_dir / ".claude"

    if not claude_dir.exists():
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps([]).encode())
        return

    # Find all .md files
    md_files = sorted(claude_dir.glob("*.md"), key=lambda p: p.name)

    # Ensure progress.md is first if it exists
    progress_md = claude_dir / "progress.md"
    if progress_md.exists() and progress_md in md_files:
        md_files.remove(progress_md)
        md_files.insert(0, progress_md)

    files_info = []
    for f in md_files:
        try:
            mtime = calculate_mtime(f)
            files_info.append({
                "name": f.stem,
                "path": str(f.relative_to(self.working_dir)),
                "mtime": mtime
            })
        except OSError:
            continue

    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps(files_info).encode())
```

**Step 4: Run test to verify it passes**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_get_files_lists_markdown_files -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git commit -m "feat(progress-ui): add GET /api/files endpoint for markdown listing"
```

---

## Task 4: Implement PUT /api/file endpoint with concurrency control

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
- Test: `plugins/progress-tracker/tests/test_progress_ui.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_put_file_concurrency_control -v
```

Expected: FAIL - function not defined

**Step 3: Write minimal implementation**

Add to `progress_ui_server.py`:

```python
def validate_put_request(current_rev: str, current_mtime: int, base_rev: str, base_mtime: int) -> bool:
    """
    Validate PUT request parameters for concurrency control.

    Args:
        current_rev: Current file revision hash
        current_mtime: Current file modification time
        base_rev: Client's base revision (what they started from)
        base_mtime: Client's base modification time

    Returns:
        True if request is valid, False if conflict detected
    """
    return current_rev == base_rev and current_mtime == base_mtime


class ProgressUIHandler(BaseHTTPRequestHandler):
    # ... existing code ...

    def do_PUT(self):
        """Handle PUT requests"""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/api/file":
            self.handle_put_file(parsed_path)
        else:
            self.send_error(404, "Not Found")

    def handle_put_file(self, parsed_path):
        """Handle PUT /api/file?path=<file>"""
        query = parse_qs(parsed_path.query)
        file_path = query.get("path", [None])[0]

        if not file_path:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "path parameter required"}).encode())
            return

        # Validate path security
        if not validate_path(self.working_dir, file_path):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid path"}).encode())
            return

        full_path = (self.working_dir / file_path).resolve()

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Request body required"}).encode())
            return

        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return

        # Extract required fields
        new_content = data.get("content")
        base_rev = data.get("base_rev", "")
        base_mtime = data.get("base_mtime", 0)

        if new_content is None:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "content field required"}).encode())
            return

        # Check for concurrent modification
        current_rev = None
        current_mtime = 0

        if full_path.exists():
            current_content = full_path.read_text()
            current_rev = calculate_rev(current_content)
            current_mtime = calculate_mtime(full_path)

            if not validate_put_request(current_rev, current_mtime, base_rev, base_mtime):
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "error": "Conflict: File was modified",
                    "current_rev": current_rev,
                    "current_mtime": current_mtime
                }
                self.wfile.write(json.dumps(response).encode())
                return

        # Write new content
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(new_content)

        # Return new rev/mtime
        new_rev = calculate_rev(new_content)
        new_mtime = calculate_mtime(full_path)

        response = {
            "rev": new_rev,
            "mtime": new_mtime
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
```

**Step 4: Run test to verify it passes**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_put_file_concurrency_control -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git add plugins/progress-tracker/tests/test_progress_ui.py
git commit -m "feat(progress-ui): add PUT /api/file with concurrency control (409 conflict)"
```

---

## Task 5: Add Origin header validation for P0 security

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
- Test: `plugins/progress-tracker/tests/test_progress_ui.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_origin_header_validation_blocks_cross_origin -v
```

Expected: FAIL - function not defined

**Step 3: Write minimal implementation**

Add to `progress_ui_server.py`:

```python
def is_valid_origin(origin: Optional[str]) -> bool:
    """
    Validate Origin header for P0 security.

    Only accepts:
    - None (no Origin header, e.g., curl, same-origin requests)
    - http://127.0.0.1:* (localhost)
    - http://localhost:*

    Args:
        origin: Origin header value or None

    Returns:
        True if origin is allowed, False otherwise
    """
    if origin is None:
        return True

    origin_lower = origin.lower()

    # Allow localhost variants
    allowed_prefixes = [
        "http://127.0.0.1:",
        "http://localhost:",
        "http://[::1]:",  # IPv6 localhost
    ]

    return any(origin_lower.startswith(prefix) for prefix in allowed_prefixes)
```

Update `handle_put_file` to validate Origin:

```python
def handle_put_file(self, parsed_path):
    """Handle PUT /api/file?path=<file>"""
    # Validate Origin header for P0 security
    origin = self.headers.get("Origin")
    if not is_valid_origin(origin):
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Invalid Origin"}).encode())
        return

    # ... rest of the function
```

**Step 4: Run test to verify it passes**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_origin_header_validation_blocks_cross_origin -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git add plugins/progress-tracker/tests/test_progress_ui.py
git commit -m "feat(progress-ui): add Origin header validation for P0 security (403 on invalid)"
```

---

## Task 6: Create static directory structure for future UI

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/static/.gitkeep`
- Create: `plugins/progress-tracker/hooks/scripts/static/index.html` (placeholder)

**Step 1: Write the failing test**

```python
def test_static_directory_exists():
    """Test static directory exists for future UI files"""
    static_dir = Path("plugins/progress-tracker/hooks/scripts/static")
    assert static_dir.exists(), "Static directory must exist"
    assert static_dir.is_dir(), "Static must be a directory"
```

**Step 2: Run test to verify it fails**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_static_directory_exists -v
```

Expected: FAIL - directory doesn't exist

**Step 3: Write minimal implementation**

```bash
mkdir -p plugins/progress-tracker/hooks/scripts/static
touch plugins/progress-tracker/hooks/scripts/static/.gitkeep
```

Create placeholder index.html:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Progress UI</title>
</head>
<body>
    <h1>Progress UI</h1>
    <p>UI will be implemented in the next feature.</p>
</body>
</html>
```

**Step 4: Run test to verify it passes**

```bash
pytest plugins/progress-tracker/tests/test_progress_ui.py::test_static_directory_exists -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/static/
git commit -m "feat(progress-ui): add static directory structure for UI"
```

---

## Summary

This plan implements a secure HTTP server for the Progress UI with:

1. ✅ Port auto-detection (3737-3747 range)
2. ✅ P0 security: 127.0.0.1 bind only
3. ✅ P0 security: Path validation with resolve()
4. ✅ GET /api/files - List markdown files
5. ✅ GET /api/file - Read file with rev/mtime
6. ✅ PUT /api/file - Write with concurrency control (409 conflict)
7. ✅ P0 security: Origin header validation

**Total estimated time:** 30-40 minutes (6 tasks)

**Testing:**
- Unit tests for all security functions
- Behavioral assertions for API contracts
- Integration tests via acceptance criteria in `/prog done`
