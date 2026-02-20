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

Check if a `progress_ui_server.py` process is already serving the current working directory:

```bash
# Find progress_ui_server processes and check their working-dir argument
for PID in $(pgrep -f progress_ui_server.py 2>/dev/null); do
  CMDLINE=$(ps -p "$PID" -o args= 2>/dev/null)
  if echo "$CMDLINE" | grep -F -q -- "--working-dir $(pwd)"; then
    PORT=$(lsof -nP -p "$PID" -iTCP -sTCP:LISTEN 2>/dev/null | awk '/LISTEN/{split($9,a,":"); print a[2]}' | head -1)
    if [ -n "$PORT" ]; then
      echo "FOUND:$PORT"
      break
    fi
  fi
done
```

### Step 2: Branch on detection result

**If `FOUND:<PORT>` was output** — server is already running for this project:

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

# Start server in background, capture log path
LOG_FILE="/tmp/progress-ui-server-$$.log"
nohup python3 "$SERVER_SCRIPT" --working-dir "$(pwd)" > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

# Wait for server to bind
sleep 1

# Verify process is still alive
if ! kill -0 $SERVER_PID 2>/dev/null; then
  echo "ERROR: Server failed to start. Check log:"
  cat "$LOG_FILE"
  exit 1
fi

# Detect assigned port from the process
PORT=$(lsof -nP -p $SERVER_PID -iTCP -sTCP:LISTEN 2>/dev/null | awk '/LISTEN/{split($9,a,":"); print a[2]}' | head -1)

if [ -z "$PORT" ]; then
  echo "ERROR: Server started but no listening port detected"
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

## Error Handling

- **Script not found**: 提示用户重新安装 progress-tracker 插件（`~/.claude/plugins/cache` 中未找到脚本）
- **Port range exhausted**: 提示关闭占用 3737-3747 的其他进程
- **Server crash on start**: 显示日志内容帮助排查
