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
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs

# Import validation functions from progress_manager
sys.path.insert(0, str(Path(__file__).parent))
try:
    from progress_manager import validate_plan_path, validate_plan_document
    PROGRESS_MANAGER_AVAILABLE = True
except ImportError:
    PROGRESS_MANAGER_AVAILABLE = False
    print("Warning: progress_manager module not available, plan validation will be disabled", file=sys.stderr)

PORT_RANGE = range(3737, 3748)  # 3737-3747 inclusive
BIND_HOST = "127.0.0.1"  # P0: Localhost only
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"


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


# Checkbox status mapping: status char -> markdown checkbox representation
CHECKBOX_STATES = {
    " ": " ",  # ☐ unchecked
    "/": "/",  # 🔄 in progress
    "x": "x",  # ☑ completed
    "-": "-",  # ➖ not applicable
    "!": "!",  # ❌ blocked/cancelled
    "?": "?",  # ❓ uncertain
}

# --- Path Whitelist ---
# Default writable paths - only project data directory
DEFAULT_WRITABLE_PATHS = [".claude"]

# Runtime writable list (default + extra)
WRITABLE_PATHS = list(DEFAULT_WRITABLE_PATHS)

# Optional: Allow extra directories via environment variable
import os
_EXTRA_PATHS_RAW = os.environ.get("PROGRESS_UI_WRITABLE_PATHS", "")
if _EXTRA_PATHS_RAW:
    for extra in _EXTRA_PATHS_RAW.split(","):
        extra = extra.strip()
        if not extra:
            continue
        if extra.startswith("/") or extra.startswith("~"):
            raise ValueError(f"Invalid PROGRESS_UI_WRITABLE_PATHS: absolute path not allowed: {extra}")
        if ".." in extra or extra == ".":
            raise ValueError(f"Invalid PROGRESS_UI_WRITABLE_PATHS: dangerous path: {extra}")
        WRITABLE_PATHS.append(extra)


def is_path_writable(rel_path: str) -> bool:
    """
    Check if a validated relative path is in the writable whitelist.

    MUST be called AFTER validate_path() has confirmed the path is safe.
    Only matches files under whitelisted directories, not the directory itself.
    """
    rel_path_normalized = rel_path.replace("\\", "/")

    for writable in WRITABLE_PATHS:
        writable_normalized = writable.replace("\\", "/")
        if rel_path_normalized.startswith(writable_normalized + "/"):
            return True

    return False


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


# ========== File Cache for Status API ==========
_file_cache = {}


def load_json_with_cache(file_path: Path, cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Load JSON file with mtime-based caching to avoid frequent file reads.

    Args:
        file_path: Path to the JSON file
        cache_key: Cache key for storing the data

    Returns:
        Parsed JSON data or None if file doesn't exist or is invalid
    """
    try:
        current_mtime = file_path.stat().st_mtime
        cached = _file_cache.get(cache_key, {"mtime": 0, "data": None})

        if cached["mtime"] == current_mtime and cached["data"] is not None:
            return cached["data"]

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        _file_cache[cache_key] = {"mtime": current_mtime, "data": data}
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


class ProgressUIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Progress UI"""

    def __init__(self, *args, working_dir: Path, **kwargs):
        self.working_dir = working_dir
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/":
            self.handle_get_index()
        elif parsed_path.path == "/api/file":
            self.handle_get_file(parsed_path)
        elif parsed_path.path == "/api/files":
            self.handle_get_files()
        elif parsed_path.path == "/api/status-summary":
            summary = self.handle_get_status_summary()
            self.send_json(summary)
        elif parsed_path.path == "/api/status-detail":
            detail, status_code = self.handle_get_status_detail(parsed_path)
            self.send_json(detail, status_code)
        elif parsed_path.path == "/api/plan-health":
            health, status_code = self.handle_get_plan_health(parsed_path)
            self.send_json(health, status_code)
        else:
            self.send_error(404, "Not Found")

    def handle_get_index(self):
        """Handle GET / - serve the single-file UI"""
        if not INDEX_FILE.exists():
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "UI entry file not found"}).encode())
            return

        try:
            content = INDEX_FILE.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Failed to read UI entry file"}).encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def do_PUT(self):
        """Handle PUT requests"""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/api/file":
            self.handle_put_file(parsed_path)
        else:
            self.send_error(404, "Not Found")

    def do_PATCH(self):
        """Handle PATCH requests"""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/api/checkbox":
            self.handle_patch_checkbox(parsed_path)
        else:
            self.send_error(404, "Not Found")

    def handle_patch_checkbox(self, parsed_path):
        """Handle PATCH /api/checkbox - update single checkbox status"""
        # Validate Origin header for P0 security
        origin = self.headers.get("Origin")
        if not is_valid_origin(origin):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid Origin"}).encode())
            return

        # Read request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid Content-Length"}).encode())
            return

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
        file_path = data.get("file_path")
        line_index = data.get("line_index")
        new_status = data.get("new_status")
        base_rev = data.get("base_rev", "")
        base_mtime = data.get("base_mtime", 0)

        # Validate required fields
        if file_path is None or line_index is None or new_status is None:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "file_path, line_index, and new_status required"}).encode())
            return

        # Validate line_index is integer
        if not isinstance(line_index, int) or line_index < 0:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "line_index must be non-negative integer"}).encode())
            return

        # Validate new_status
        if new_status not in CHECKBOX_STATES:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Invalid new_status. Must be one of: {list(CHECKBOX_STATES.keys())}"}).encode())
            return

        # Validate path security
        if not validate_path(self.working_dir, file_path):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid path"}).encode())
            return

        # Whitelist check
        if not is_path_writable(file_path):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Path not in writable whitelist"}).encode())
            return

        full_path = (self.working_dir / file_path).resolve()

        if not full_path.exists():
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "File not found"}).encode())
            return

        # Read current file for concurrency control
        current_content = full_path.read_text()
        current_rev = calculate_rev(current_content)
        current_mtime = calculate_mtime(full_path)

        # Check for concurrent modification
        if not validate_put_request(current_rev, current_mtime, base_rev, base_mtime):
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Conflict: File was modified", "current_rev": current_rev, "current_mtime": current_mtime}).encode())
            return

        # Split file into lines
        lines = current_content.splitlines(keepends=True)

        # Validate line_index is within bounds
        if line_index >= len(lines):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"line_index {line_index} out of bounds (file has {len(lines)} lines)"}).encode())
            return

        # Get the target line
        original_line = lines[line_index]

        # Check if line contains a checkbox pattern
        import re
        checkbox_pattern = r'^(\s*-\s*\[)([ /x\-!?])(\])'
        match = re.match(checkbox_pattern, original_line)

        if not match:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Line {line_index} does not contain a checkbox"}).encode())
            return

        # Update the checkbox status
        prefix = match.group(1)  # "- ["
        suffix = match.group(3)  # "]"
        rest_of_line = original_line[match.end():]  # Everything after "]"

        updated_line = f"{prefix}{new_status}{suffix}{rest_of_line}"
        lines[line_index] = updated_line

        # Join lines back together
        new_content = "".join(lines)

        # Write to file
        full_path.write_text(new_content)

        # Calculate new rev/mtime
        new_rev = calculate_rev(new_content)
        new_mtime = calculate_mtime(full_path)

        response = {
            "rev": new_rev,
            "mtime": new_mtime,
            "updated_line": updated_line.rstrip("\n\r")
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

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

        # Whitelist check
        if not is_path_writable(file_path):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Path not in writable whitelist"}).encode())
            return

        full_path = (self.working_dir / file_path).resolve()

        # Read request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid Content-Length"}).encode())
            return

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

    def send_json(self, payload: Dict[str, Any], status_code: int = 200):
        """Send JSON response with appropriate headers"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def _format_relative_time(self, iso_timestamp: str) -> str:
        """Format ISO timestamp as relative time (e.g., '2 hours ago')"""
        try:
            timestamp = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = now - timestamp

            if delta.days > 0:
                return f"{delta.days} 天前"
            elif delta.seconds >= 3600:
                hours = delta.seconds // 3600
                return f"{hours} 小时前"
            elif delta.seconds >= 60:
                minutes = delta.seconds // 60
                return f"{minutes} 分钟前"
            else:
                return "刚刚"
        except Exception:
            return iso_timestamp

    def _normalize_development_stage(self, feature: Dict[str, Any]) -> str:
        """
        Normalize feature development stage with backward compatibility.

        Legacy progress files may not include development_stage, and those active
        features should be treated as developing by default.
        """
        if feature.get("completed", False):
            return "completed"

        stage = feature.get("development_stage")
        if stage in {"planning", "developing", "completed"}:
            return stage

        return "developing"

    def _development_stage_label(self, stage: str) -> str:
        """Return localized label for development stage."""
        return {
            "planning": "规划中",
            "developing": "开发中",
            "completed": "已完成",
            "pending": "待开始",
        }.get(stage, "未知")

    def _determine_next_action(self, features: list, progress_data: Dict) -> Dict[str, Any]:
        """Determine the next action based on current feature state"""
        current_id = progress_data.get("current_feature_id")

        # Priority 1: Active feature
        if current_id is not None:
            feature = next((f for f in features if f.get("id") == current_id), None)
            if feature:
                stage = self._normalize_development_stage(feature)
                return {
                    "type": "feature",
                    "feature_id": current_id,
                    "feature_name": feature.get("name", "Unknown"),
                    "development_stage": stage,
                    "stage_label": self._development_stage_label(stage),
                }

        # Priority 2: Smallest ID pending feature
        pending = [f for f in features if not f.get("completed", False)]
        if pending:
            next_feature = min(pending, key=lambda f: f.get("id", float("inf")))
            return {
                "type": "feature",
                "feature_id": next_feature.get("id"),
                "feature_name": next_feature.get("name", "Unknown"),
                "development_stage": "pending",
                "stage_label": self._development_stage_label("pending"),
            }

        # All completed
        return {
            "type": "none",
            "feature_id": None,
            "feature_name": "无待办功能",
            "development_stage": None,
            "stage_label": None,
        }

    def _check_plan_health(self, progress_data: Dict) -> Dict[str, Any]:
        """Check plan compliance using progress_manager validation"""
        workflow_state = progress_data.get("workflow_state")

        if not workflow_state or not workflow_state.get("plan_path"):
            return {"status": "N/A", "plan_path": None, "message": "无活跃计划"}

        plan_path = workflow_state["plan_path"]

        if not PROGRESS_MANAGER_AVAILABLE:
            return {
                "status": "N/A",
                "plan_path": plan_path,
                "message": "计划验证模块不可用"
            }

        try:
            # Path validation
            path_result = validate_plan_path(plan_path, require_exists=True)
            if not path_result["valid"]:
                return {
                    "status": "WARN",
                    "plan_path": plan_path,
                    "message": path_result["error"]
                }

            # Document structure validation
            doc_result = validate_plan_document(plan_path)
            if not doc_result["valid"]:
                missing = ", ".join(doc_result["missing_sections"])
                return {
                    "status": "INVALID",
                    "plan_path": plan_path,
                    "message": f"缺少必需章节: {missing}"
                }

            return {
                "status": "OK",
                "plan_path": plan_path,
                "message": "计划文件完整且符合规范"
            }
        except Exception as e:
            return {
                "status": "WARN",
                "plan_path": plan_path,
                "message": f"验证失败: {str(e)}"
            }

    def _check_risk_blocker(self, progress_data: Dict) -> Dict[str, Any]:
        """Check for high-priority bugs or blockers"""
        bugs = progress_data.get("bugs", [])

        high_priority = [
            b for b in bugs
            if b.get("priority") == "high" and b.get("status") != "fixed"
        ]
        blocked = [b for b in bugs if b.get("status") == "blocked"]

        if high_priority or blocked:
            return {
                "has_risk": True,
                "high_priority_bugs": len(high_priority),
                "blocked_count": len(blocked),
                "message": f"{len(high_priority)} 个高优先级 bug"
            }

        return {
            "has_risk": False,
            "high_priority_bugs": 0,
            "blocked_count": 0,
            "message": "正常"
        }

    def _load_recent_snapshot(self, checkpoints_data: Optional[Dict]) -> Dict[str, Any]:
        """Load most recent snapshot information"""
        if not checkpoints_data:
            return {"exists": False, "timestamp": None, "relative_time": "暂无快照"}

        last_time = checkpoints_data.get("last_checkpoint_at")
        if not last_time:
            return {"exists": False, "timestamp": None, "relative_time": "暂无快照"}

        relative = self._format_relative_time(last_time)
        return {"exists": True, "timestamp": last_time, "relative_time": relative}

    def handle_get_status_summary(self) -> Dict[str, Any]:
        """
        Handle GET /api/status-summary - return 5 status indicators summary.

        Returns:
            Dictionary with progress, next_action, plan_health, risk_blocker, recent_snapshot
        """
        progress_data = load_json_with_cache(
            self.working_dir / ".claude" / "progress.json", "progress_json"
        )
        checkpoints_data = load_json_with_cache(
            self.working_dir / ".claude" / "checkpoints.json", "checkpoints_json"
        )

        # Graceful degradation: return empty state if progress_data is missing
        if progress_data is None:
            progress_data = {"features": [], "current_feature_id": None, "bugs": []}

        # 1. Calculate overall progress
        features = progress_data.get("features", [])
        completed = sum(1 for f in features if f.get("completed", False))
        total = len(features)
        percentage = int((completed / total * 100)) if total > 0 else 0

        # 2. Determine next action
        next_action = self._determine_next_action(features, progress_data)

        # 3. Check plan health
        plan_health = self._check_plan_health(progress_data)

        # 4. Check risk/blocker
        risk_blocker = self._check_risk_blocker(progress_data)

        # 5. Load recent snapshot
        recent_snapshot = self._load_recent_snapshot(checkpoints_data)

        return {
            "progress": {
                "completed": completed,
                "total": total,
                "percentage": percentage
            },
            "next_action": next_action,
            "plan_health": plan_health,
            "risk_blocker": risk_blocker,
            "recent_snapshot": recent_snapshot,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

    def _build_progress_detail(self, progress_data: Dict) -> Dict[str, Any]:
        """Build progress panel detail (unified structured format)"""
        features = progress_data.get("features", [])
        completed = sum(1 for f in features if f.get("completed", False))
        total = len(features)
        pending = total - completed

        # Build feature_list section
        feature_list_section = {
            "type": "feature_list",
            "title": "功能列表",
            "content": [
                {
                    "id": f.get("id"),
                    "name": f.get("name", "Unknown"),
                    "completed": f.get("completed", False),
                    "completed_at": f.get("completed_at"),
                    "development_stage": self._normalize_development_stage(f),
                    "stage_label": self._development_stage_label(
                        self._normalize_development_stage(f)
                    ),
                }
                for f in features
            ]
        }

        return {
            "panel": "progress",
            "title": "总进度详情",
            "summary": f"已完成 {completed} 个功能，待办 {pending} 个功能",
            "sections": [feature_list_section],
            "sources": [
                {"path": ".claude/progress.json", "label": "进度数据"}
            ],
            "actions": [
                {"label": "刷新进度", "command": "/prog", "type": "copy"}
            ]
        }

    def _build_plan_detail(self, progress_data: Dict) -> Dict[str, Any]:
        """Build plan compliance panel detail (unified structured format)"""
        workflow_state = progress_data.get("workflow_state")

        # Case 1: No active plan
        if not workflow_state or not workflow_state.get("plan_path"):
            return {
                "panel": "plan",
                "title": "计划合规详情",
                "summary": "当前无活跃计划",
                "sections": [
                    {
                        "type": "text",
                        "content": "没有进行中的功能，因此无活跃计划。使用 /prog next 开始下一个功能。"
                    }
                ],
                "sources": [],
                "actions": [
                    {"label": "开始下一个功能", "command": "/prog next", "type": "copy"}
                ]
            }

        # Case 2: Has active plan, perform validation
        plan_path = workflow_state["plan_path"]

        if not PROGRESS_MANAGER_AVAILABLE:
            return {
                "panel": "plan",
                "title": "计划合规详情",
                "summary": "验证模块不可用",
                "sections": [
                    {
                        "type": "text",
                        "content": "无法验证计划文件：progress_manager 模块未加载"
                    }
                ],
                "sources": [],
                "actions": []
            }

        try:
            path_result = validate_plan_path(plan_path, require_exists=True)
            doc_result = validate_plan_document(plan_path) if path_result["valid"] else None
        except Exception as e:
            return {
                "panel": "plan",
                "title": "计划合规详情",
                "summary": f"验证失败: {str(e)}",
                "sections": [
                    {
                        "type": "text",
                        "content": f"无法验证计划文件: {str(e)}"
                    }
                ],
                "sources": [],
                "actions": []
            }

        # Build validation result table
        validation_rows = [
            {"key": "计划路径", "value": plan_path}
        ]

        if path_result["valid"]:
            validation_rows.append({"key": "路径合规", "value": "✓ 通过"})
        else:
            validation_rows.append({"key": "路径合规", "value": f"✗ {path_result['error']}"})

        if doc_result and doc_result["valid"]:
            validation_rows.append({"key": "结构合规", "value": "✓ 包含 Tasks/Acceptance/Risks"})
        elif doc_result:
            missing = ", ".join(doc_result["missing_sections"])
            validation_rows.append({"key": "结构合规", "value": f"✗ 缺少: {missing}"})

        validation_section = {
            "type": "table",
            "title": "验证结果",
            "content": validation_rows
        }

        # Determine summary
        if path_result["valid"] and doc_result and doc_result["valid"]:
            summary = "计划文件完整且符合规范"
        else:
            summary = "计划文件存在问题，请检查"

        return {
            "panel": "plan",
            "title": "计划合规详情",
            "summary": summary,
            "sections": [validation_section],
            "sources": [
                {"path": plan_path, "label": "计划文档"}
            ],
            "actions": [
                {"label": "打开计划文档", "command": f"loadFile('{plan_path}')", "type": "link"}
            ]
        }

    def _build_next_detail(self, progress_data: Dict) -> Dict[str, Any]:
        """Build next action panel detail (unified structured format)"""
        features = progress_data.get("features", [])
        current_id = progress_data.get("current_feature_id")

        # Determine next feature and whether it's active
        next_feature = None
        is_active = False
        if current_id is not None:
            next_feature = next((f for f in features if f.get("id") == current_id), None)
            is_active = next_feature is not None

        if not next_feature:
            pending = [f for f in features if not f.get("completed", False)]
            if pending:
                next_feature = min(pending, key=lambda f: f.get("id", float("inf")))

        # Case 1: No pending features
        if not next_feature:
            return {
                "panel": "next",
                "title": "下一步详情",
                "summary": "所有功能已完成！",
                "sections": [
                    {
                        "type": "text",
                        "content": "恭喜！项目的所有功能已完成。"
                    }
                ],
                "sources": [],
                "actions": []
            }

        # Case 2: Has next feature
        sections = [
            {
                "type": "text",
                "title": "功能描述",
                "content": next_feature.get("name", "Unknown")
            }
        ]

        test_steps = next_feature.get("test_steps", [])
        if test_steps:
            sections.append({
                "type": "list",
                "title": "测试步骤",
                "content": test_steps[:5]  # Show only first 5
            })

        # Determine action based on whether feature is active
        if is_active:
            active_stage = self._normalize_development_stage(next_feature)
            stage_label = self._development_stage_label(active_stage)

            action_map = {
                "planning": {
                    "label": "开始开发",
                    "command": "/prog start",
                },
                "developing": {
                    "label": "完成此功能",
                    "command": "/prog done",
                },
            }
            action = action_map.get(active_stage)
            actions = (
                [{"label": action["label"], "command": action["command"], "type": "copy"}]
                if action
                else []
            )

            return {
                "panel": "next",
                "title": "当前功能详情",
                "summary": (
                    f"{stage_label} Feature #{next_feature.get('id')}: "
                    f"{next_feature.get('name', 'Unknown')}"
                ),
                "sections": sections,
                "sources": [
                    {"path": ".claude/progress.json", "label": "进度数据"}
                ],
                "actions": actions
            }
        else:
            # Pending feature: suggest starting it
            return {
                "panel": "next",
                "title": "下一步详情",
                "summary": f"建议开始 Feature #{next_feature.get('id')}: {next_feature.get('name', 'Unknown')}",
                "sections": sections,
                "sources": [
                    {"path": ".claude/progress.json", "label": "进度数据"}
                ],
                "actions": [
                    {"label": "开始此功能", "command": "/prog next", "type": "copy"}
                ]
            }

    def _build_risk_detail(self, progress_data: Dict) -> Dict[str, Any]:
        """Build risk/blocker panel detail (unified structured format)"""
        bugs = progress_data.get("bugs", [])
        high_priority = [
            b for b in bugs
            if b.get("priority") == "high" and b.get("status") != "fixed"
        ]
        blocked = [b for b in bugs if b.get("status") == "blocked"]

        if not high_priority and not blocked:
            return {
                "panel": "risk",
                "title": "风险阻塞详情",
                "summary": "当前无高风险问题",
                "sections": [
                    {"type": "text", "content": "项目运行正常，无阻塞性问题。"}
                ],
                "sources": [],
                "actions": []
            }

        # Build risk list
        risk_items = []
        for bug in high_priority:
            risk_items.append(f"[高优先级] {bug.get('description', 'Unknown bug')}")
        for bug in blocked:
            risk_items.append(f"[阻塞] {bug.get('description', 'Unknown bug')}")

        return {
            "panel": "risk",
            "title": "风险阻塞详情",
            "summary": f"发现 {len(high_priority)} 个高优先级问题，{len(blocked)} 个阻塞问题",
            "sections": [
                {
                    "type": "list",
                    "title": "风险列表",
                    "content": risk_items
                }
            ],
            "sources": [
                {"path": ".claude/progress.json", "label": "进度数据"}
            ],
            "actions": [
                {"label": "查看问题", "command": "/prog-fix list", "type": "copy"}
            ]
        }

    def _build_snapshot_detail(self, checkpoints_data: Optional[Dict]) -> Dict[str, Any]:
        """Build snapshot panel detail (unified structured format)"""
        if not checkpoints_data or not checkpoints_data.get("entries"):
            return {
                "panel": "snapshot",
                "title": "快照历史",
                "summary": "暂无快照记录",
                "sections": [
                    {"type": "text", "content": "尚未创建任何进度快照。"}
                ],
                "sources": [],
                "actions": []
            }

        entries = checkpoints_data.get("entries", [])
        last_entry = entries[0] if entries else None

        # Build snapshot list
        snapshot_items = []
        for entry in entries[:5]:  # Show only recent 5
            timestamp = entry.get("timestamp", "")
            relative = self._format_relative_time(timestamp)
            feature_id = entry.get("feature_id", "?")
            feature_name = entry.get("feature_name", "Unknown")
            snapshot_items.append(f"{relative} - Feature #{feature_id}: {feature_name}")

        return {
            "panel": "snapshot",
            "title": "快照历史",
            "summary": f"最近快照: {self._format_relative_time(last_entry.get('timestamp', ''))}",
            "sections": [
                {
                    "type": "list",
                    "title": "最近快照",
                    "content": snapshot_items
                }
            ],
            "sources": [
                {"path": ".claude/checkpoints.json", "label": "快照数据"}
            ],
            "actions": []
        }

    def handle_get_status_detail(self, parsed_path) -> Tuple[Dict[str, Any], int]:
        """
        Handle GET /api/status-detail?panel=<panel_type>

        Returns:
            Tuple of (response_dict, http_status_code)
        """
        query = parse_qs(parsed_path.query)
        panel = query.get("panel", [None])[0]

        if panel not in ["progress", "next", "plan", "risk", "snapshot"]:
            return {"error": "Missing or invalid panel parameter"}, 400

        progress_data = load_json_with_cache(
            self.working_dir / ".claude" / "progress.json", "progress_json"
        )

        # Graceful degradation
        if progress_data is None:
            progress_data = {"features": [], "current_feature_id": None, "bugs": []}

        if panel == "progress":
            return self._build_progress_detail(progress_data), 200
        elif panel == "plan":
            return self._build_plan_detail(progress_data), 200
        elif panel == "next":
            return self._build_next_detail(progress_data), 200
        elif panel == "risk":
            return self._build_risk_detail(progress_data), 200
        elif panel == "snapshot":
            checkpoints_data = load_json_with_cache(
                self.working_dir / ".claude" / "checkpoints.json", "checkpoints_json"
            )
            return self._build_snapshot_detail(checkpoints_data), 200

        return {"error": "Unknown panel type"}, 400

    def handle_get_plan_health(self, parsed_path) -> Tuple[Dict[str, Any], int]:
        """
        Handle GET /api/plan-health?path=<plan_path>

        Validates the specified plan file for compliance.

        Returns:
            Tuple of (response_dict, http_status_code)
        """
        query = parse_qs(parsed_path.query)
        plan_path = query.get("path", [None])[0]

        if not plan_path:
            return {"error": "path parameter required"}, 400

        if not PROGRESS_MANAGER_AVAILABLE:
            return {
                "error": "progress_manager module not available",
                "plan_path": plan_path,
                "overall_status": "N/A"
            }, 200

        try:
            path_result = validate_plan_path(plan_path, require_exists=False)
            doc_result = None
            if path_result["valid"]:
                doc_result = validate_plan_document(plan_path)

            if not path_result["valid"]:
                overall_status = "WARN"
            elif not doc_result or not doc_result["valid"]:
                overall_status = "INVALID"
            else:
                overall_status = "OK"

            return {
                "plan_path": plan_path,
                "path_validation": path_result,
                "document_validation": doc_result,
                "overall_status": overall_status
            }, 200
        except Exception as e:
            return {
                "error": f"Validation failed: {str(e)}",
                "plan_path": plan_path,
                "overall_status": "WARN"
            }, 200


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

    print(f"Progress UI Server starting on {BIND_HOST}:{port}", flush=True)
    print(f"Working directory: {working_dir}", flush=True)
    print(f"Open http://{BIND_HOST}:{port}/ in your browser", flush=True)
    print(f"Press Ctrl+C to stop", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped", flush=True)
        server.shutdown()
        return 0


if __name__ == "__main__":
    sys.exit(main())
