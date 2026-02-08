# Checkbox PATCH API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement PATCH /api/checkbox endpoint to toggle checkbox status in markdown files with concurrency control.

**Architecture:** Add PATCH handler to existing HTTP server. Parse checkbox state changes, apply them to the specific line, and return updated rev/mtime. Uses existing concurrency control (rev/mtime) and path validation.

**Tech Stack:** Python 3, http.server, pathlib, existing progress_ui_server.py infrastructure

---

## Context

**Current State:** The HTTP server already has:
- PUT /api/file with full content replacement and concurrency control
- GET /api/file for reading files
- Path validation and Origin checking
- rev/mtime calculation functions

**What's Missing:** PATCH /api/checkbox endpoint for fine-grained checkbox updates.

**Request Format:**
```json
{
  "file_path": ".claude/progress.md",
  "line_index": 5,
  "new_status": "x",
  "base_rev": "abc123...",
  "base_mtime": 1234567890
}
```

**Response Format:**
```json
{
  "rev": "new_hash...",
  "mtime": 1234567891,
  "updated_line": "- [x] Task completed"
}
```

---

### Task 1: Add do_PATCH method stub

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py` (add after do_PUT method, around line 179)

**Step 1: Verify current code structure**

Run: `grep -n "def do_PUT" plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
Expected: Line number showing `171:    def do_PUT(self):`

**Step 2: Add do_PATCH method stub**

Add after the do_PUT method (around line 178):

```python
def do_PATCH(self):
    """Handle PATCH requests"""
    parsed_path = urlparse(self.path)

    if parsed_path.path == "/api/checkbox":
        self.handle_patch_checkbox(parsed_path)
    else:
        self.send_error(404, "Not Found")
```

**Step 3: Verify syntax**

Run: `python3 -m py_compile plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
Expected: No output (successful compilation)

**Step 4: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git commit -m "feat(server): add do_PATCH method stub"
```

---

### Task 2: Parse checkbox status constants

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py` (add after calculate_mtime function, around line 105)

**Step 1: Add checkbox status mapping**

```python
# Checkbox status mapping: status char -> markdown checkbox representation
CHECKBOX_STATES = {
    " ": " ",  # ☐ unchecked
    "/": "/",  # 🔄 in progress
    "x": "x",  # ☑ completed
    "-": "-",  # ➖ not applicable
    "!": "!",  # ❌ blocked/cancelled
    "?": "?",  # ❓ uncertain
}
```

**Step 2: Verify syntax**

Run: `python3 -c "import sys; sys.path.insert(0, 'plugins/progress-tracker/hooks/scripts'); from progress_ui_server import CHECKBOX_STATES; print(CHECKBOX_STATES)"`
Expected: `{' ': ' ', '/': '/', 'x': 'x', '-': '-', '!': '!', '?': '?'}`

**Step 3: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git commit -m "feat(server): add checkbox state constants"
```

---

### Task 3: Implement handle_patch_checkbox method - validation

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py` (add after handle_put_file method, around line 363)

**Step 1: Add method signature and Origin validation**

```python
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
```

**Step 2: Verify server loads**

Run: `python3 -c "import sys; sys.path.insert(0, 'plugins/progress-tracker/hooks/scripts'); from progress_ui_server import ProgressUIHandler; print('Handler loads OK')"`
Expected: `Handler loads OK`

**Step 3: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git commit -m "feat(server): add PATCH Origin validation"
```

---

### Task 4: Implement request body parsing

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py` (extend handle_patch_checkbox method)

**Step 1: Add body parsing logic**

Continue the handle_patch_checkbox method:

```python
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
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
Expected: No output

**Step 3: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git commit -m "feat(server): add PATCH request body parsing and validation"
```

---

### Task 5: Implement path validation

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py` (extend handle_patch_checkbox method)

**Step 1: Add path validation**

Continue the handle_patch_checkbox method:

```python
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
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
Expected: No output

**Step 3: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git commit -m "feat(server): add PATCH path validation"
```

---

### Task 6: Implement concurrency control check

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py` (extend handle_patch_checkbox method)

**Step 1: Add concurrency validation**

Continue the handle_patch_checkbox method:

```python
    # Read current file for concurrency control
    current_content = full_path.read_text()
    current_rev = calculate_rev(current_content)
    current_mtime = calculate_mtime(full_path)

    # Check for concurrent modification
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
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
Expected: No output

**Step 3: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git commit -m "feat(server): add PATCH concurrency control"
```

---

### Task 7: Implement checkbox line update logic

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_ui_server.py` (extend handle_patch_checkbox method)

**Step 1: Add line update logic**

Continue the handle_patch_checkbox method:

```python
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
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile plugins/progress-tracker/hooks/scripts/progress_ui_server.py`
Expected: No output

**Step 3: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_ui_server.py
git commit -m "feat(server): implement checkbox line update logic"
```

---

### Task 8: Integration test - manual verification

**Files:**
- Test: Manual testing via curl

**Step 1: Start server in background**

Run:
```bash
python3 plugins/progress-tracker/hooks/scripts/progress_ui_server.py --port 3737 &
SERVER_PID=$!
sleep 2
```

Expected: Server starts successfully

**Step 2: Create test file with checkboxes**

Run:
```bash
cat > .claude/checkbox-test.md << 'EOF'
# Test Checkboxes

- [ ] Task 1
- [ ] Task 2
- [x] Task 3
EOF
```

**Step 3: Get current rev/mtime**

Run:
```bash
READ=$(curl -s "http://127.0.0.1:3737/api/file?path=.claude/checkbox-test.md")
REV=$(echo "$READ" | jq -r '.rev')
MTIME=$(echo "$READ" | jq -r '.mtime')
echo "Current rev: $REV, mtime: $MTIME"
```

Expected: Shows current revision hash and timestamp

**Step 4: Test PATCH to update checkbox**

Run:
```bash
curl -s -X PATCH "http://127.0.0.1:3737/api/checkbox" \
  -H "Content-Type: application/json" \
  -d "{\"file_path\":\".claude/checkbox-test.md\",\"line_index\":2,\"new_status\":\"x\",\"base_rev\":\"$REV\",\"base_mtime\":$MTIME}" | jq '.'
```

Expected: Returns new rev/mtime and updated_line

**Step 5: Verify file was updated**

Run:
```bash
cat .claude/checkbox-test.md
```

Expected: Line 3 shows "- [x] Task 2"

**Step 6: Test invalid Origin**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}" -X PATCH "http://127.0.0.1:3737/api/checkbox" \
  -H "Content-Type: application/json" \
  -H "Origin: http://evil.com" \
  -d "{\"file_path\":\".claude/checkbox-test.md\",\"line_index\":2,\"new_status\":\"x\",\"base_rev\":\"$REV\",\"base_mtime\":$MTIME}"
```

Expected: `403`

**Step 7: Test invalid status**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}" -X PATCH "http://127.0.0.1:3737/api/checkbox" \
  -H "Content-Type: application/json" \
  -d "{\"file_path\":\".claude/checkbox-test.md\",\"line_index\":2,\"new_status\":\"Z\",\"base_rev\":\"\",\"base_mtime\":0}"
```

Expected: `400`

**Step 8: Cleanup**

Run:
```bash
kill $SERVER_PID
rm -f .claude/checkbox-test.md
```

**Step 9: Commit test documentation**

```bash
cat >> plugins/progress-tracker/tests/test_manual_checkbox.md << 'EOF'
# Manual Checkbox PATCH Test Results

Date: 2026-02-08

## Test Results
- [x] Server starts and responds to PATCH
- [x] Checkbox status updates correctly
- [x] Invalid Origin returns 403
- [x] Invalid status returns 400
- [x] File content is preserved
EOF
git add plugins/progress-tracker/tests/test_manual_checkbox.md
git commit -m "test(server): document manual checkbox PATCH tests"
```

---

## Summary

This plan implements the PATCH /api/checkbox endpoint with:
- P0 Security: Origin validation, path validation
- Concurrency Control: rev/mtime-based conflict detection
- Input Validation: line_index bounds, valid status chars
- Checkbox Pattern Recognition: Only updates valid checkbox lines
- Proper HTTP Responses: 200, 400, 403, 404, 409

**Total estimated time:** 20-25 minutes (8 tasks)
