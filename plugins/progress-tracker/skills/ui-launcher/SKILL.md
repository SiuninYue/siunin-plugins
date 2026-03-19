---
name: ui-launcher
description: This skill should be used when the user runs "/prog-ui", asks to "open progress UI", "launch progress web UI", or wants to view progress in a browser. Manages the Progress UI server lifecycle (detect, start, open browser) for the current project.
model: haiku
version: "1.0.0"
scope: skill
inputs:
  - User request to open Progress UI
outputs:
  - Server running status
  - Browser opened to UI URL
  - Server management instructions
evidence: optional
references: []
---

# Progress UI Launcher Skill

You are a Progress UI launcher. Your role is to start the Progress UI web server for the **current working directory** and open it in the user's browser.

## Core Logic

Execute these steps in order. Use the Bash tool for all commands.

### Step 1: Detect existing server for this project

Check if a `progress_ui_server.py` process is already serving the current working directory.
Validate the candidate port with an HTTP probe (not just `lsof`) to avoid false positives/negatives during startup:

```bash
# Find progress_ui_server processes and check their working-dir argument
for PID in $(pgrep -f progress_ui_server.py 2>/dev/null); do
  CMDLINE=$(ps -p "$PID" -o args= 2>/dev/null)
  if echo "$CMDLINE" | grep -F -q -- "--working-dir $(pwd)"; then
    PORT=$(lsof -nP -p "$PID" -iTCP -sTCP:LISTEN 2>/dev/null | awk '/LISTEN/{split($9,a,":"); print a[2]}' | head -1)
    if [ -n "$PORT" ] && curl -fsS --max-time 1 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
      echo "FOUND:$PORT:$PID"
      break
    fi
  fi
done
```

### Step 2: Branch on detection result

**If `FOUND:<PORT>:<PID>` was output** — server is already running for this project:

Display:
```
✅ Progress UI already running

URL: http://127.0.0.1:<PORT>/
Working directory: <pwd>
```

Open browser:
```bash
open "http://127.0.0.1:<PORT>/" 2>/dev/null || xdg-open "http://127.0.0.1:<PORT>/" 2>/dev/null
```

**If nothing was found** — start a new server:

```bash
# Find server script in plugin cache (works from any project directory)
SERVER_SCRIPT=$(find ~/.claude/plugins/cache -name "progress_ui_server.py" -path "*/progress-tracker/*" 2>/dev/null | sort -V | tail -1)

# Fall back to relative path (for development use within Claude-Plugins repo)
if [ -z "$SERVER_SCRIPT" ]; then
  SERVER_SCRIPT="plugins/progress-tracker/hooks/scripts/progress_ui_server.py"
fi

# Verify script exists
if [ ! -f "$SERVER_SCRIPT" ]; then
  echo "ERROR: Server script not found. Reinstall the progress-tracker plugin."
  exit 1
fi

# Pick a port up front so we can probe readiness without relying on lsof race timing
PORT=""
for CANDIDATE_PORT in $(seq 3737 3747); do
  if ! lsof -nP -iTCP:"$CANDIDATE_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    PORT="$CANDIDATE_PORT"
    break
  fi
done

if [ -z "$PORT" ]; then
  echo "ERROR: No available ports in range 3737-3747"
  exit 1
fi

# Start server in background, capture log path
LOG_FILE="/tmp/progress-ui-server-$$.log"
nohup python3 "$SERVER_SCRIPT" --working-dir "$(pwd)" --port "$PORT" > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

# Wait for HTTP readiness (avoid fixed sleep + lsof race)
READY=0
for _ in $(seq 1 50); do
  if curl -fsS --max-time 1 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    READY=1
    break
  fi

  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "ERROR: Server failed to start. Check log:"
    cat "$LOG_FILE"
    exit 1
  fi

  sleep 0.2
done

if [ "$READY" -ne 1 ]; then
  echo "ERROR: Server did not become ready on port $PORT within timeout"
  kill "$SERVER_PID" 2>/dev/null || true
  cat "$LOG_FILE"
  exit 1
fi

echo "STARTED:$PORT:$SERVER_PID:$LOG_FILE"
```

### Step 3: Open browser

```bash
open "http://127.0.0.1:$PORT/" 2>/dev/null || xdg-open "http://127.0.0.1:$PORT/" 2>/dev/null
```

### Step 4: Display status

```
╔════════════════════════════════════════╗
║  🌐 Progress UI                       ║
╚════════════════════════════════════════╝

URL:    http://127.0.0.1:<PORT>/
项目:   <pwd>
PID:    <SERVER_PID>
日志:   <LOG_FILE>

停止服务器:
  kill <SERVER_PID>
```

### Step 5: Provide usage guidance

After displaying server status, provide helpful next steps:

**If no progress tracking exists** (no `docs/progress-tracker/state/progress.json`):
```markdown
### No Active Project

No progress tracking found in this directory.

**Next Steps**:
- Start a new project: `/prog-init <your goal>`
- Learn more: `/progress-tracker:help`
```

**If active project exists**:
```markdown
### Progress UI Running

**Tips**:
- Keep UI open in another window while you work
- Checkboxes auto-sync to progress files
- Press `?` in UI for keyboard shortcuts

---
**Paste into a new session to check status:**

/progress-tracker:prog

ProjectRoot: <abs_project_root>
→ Context pre-loaded. Shows current status and recommendations.
---
```

Get `ProjectRoot` by running: `pwd -P`

## Error Handling

- **Script not found**: 提示用户重新安装 progress-tracker 插件（`~/.claude/plugins/cache` 中未找到脚本）
- **Port range exhausted**: 提示关闭占用 3737-3747 的其他进程
- **Server crash on start**: 显示日志内容帮助排查（技能会在超时/失败时清理刚启动的进程，避免遗留占端口）
