#!/usr/bin/env python3
"""
Progress UI HTTP Server

A lightweight HTTP server for viewing and editing progress.md files via web UI.
P0 Security: Binds to 127.0.0.1 only, validates all file paths.

Usage:
    python3 progress_ui_server.py [--port PORT] [--working-dir DIR]
"""

import argparse
import hashlib
import json
import socket
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

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

    def do_PUT(self):
        """Handle PUT requests"""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/api/file":
            self.handle_put_file(parsed_path)
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

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


def create_handler(working_dir: Path):
    """Factory to create handler with working_dir injected"""
    def handler(*args, **kwargs):
        return ProgressUIHandler(*args, working_dir=working_dir, **kwargs)
    return handler


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


if __name__ == "__main__":
    sys.exit(main())
