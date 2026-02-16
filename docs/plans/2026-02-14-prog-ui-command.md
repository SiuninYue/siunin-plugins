# /prog-ui Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a `/prog-ui` slash command that启动当前项目的 Progress UI 服务器并打开浏览器。

**Architecture:** 遵循现有 command→skill 模式。`prog-ui.md` 命令文件仅负责调用 `ui-launcher` skill；skill 内包含完整的服务器生命周期管理逻辑（进程检测、启动、浏览器打开）。进程检测不仅检查端口，还校验进程名为 `progress_ui_server` 且 `--working-dir` 匹配当前项目。

**Tech Stack:** Python (existing server), Bash (process management), Claude Code plugin system (command .md + skill SKILL.md)

**验收测试修正说明:** progress.json 中的 test_step `grep 'prog-ui' plugin.json` 没有运行时消费方——plugin.json 当前不声明 commands 列表，命令是通过 `commands/` 目录自动发现的。计划改为在 plugin.json description 中自然提及 `prog-ui`，使 grep 通过且语义合理。

---

### Task 1: Create the `ui-launcher` skill

**Files:**
- Create: `plugins/progress-tracker/skills/ui-launcher/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p plugins/progress-tracker/skills/ui-launcher
```

**Step 2: Write the skill file**

Create `plugins/progress-tracker/skills/ui-launcher/SKILL.md`:

```markdown
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
  if echo "$CMDLINE" | grep -q -- "--working-dir.*$(pwd)"; then
    PORT=$(lsof -nP -p "$PID" -iTCP -sTCP:LISTEN 2>/dev/null | awk '{split($9,a,":"); print a[2]}' | head -1)
    echo "FOUND:$PORT"
    break
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
SERVER_SCRIPT="plugins/progress-tracker/hooks/scripts/progress_ui_server.py"

# Verify script exists
if [ ! -f "$SERVER_SCRIPT" ]; then
  echo "ERROR: Server script not found at $SERVER_SCRIPT"
  exit 1
fi

# Start server in background
nohup python3 "$SERVER_SCRIPT" --working-dir "$(pwd)" > /tmp/progress-ui-server-$$.log 2>&1 &
SERVER_PID=$!

# Wait for server to bind
sleep 1

# Verify process is still alive
if ! kill -0 $SERVER_PID 2>/dev/null; then
  echo "ERROR: Server failed to start. Check log:"
  cat /tmp/progress-ui-server-$$.log
  exit 1
fi

# Detect assigned port from the process
PORT=$(lsof -nP -p $SERVER_PID -iTCP -sTCP:LISTEN 2>/dev/null | awk '{split($9,a,":"); print a[2]}' | head -1)

if [ -z "$PORT" ]; then
  echo "ERROR: Server started but no listening port detected"
  cat /tmp/progress-ui-server-$$.log
  exit 1
fi

echo "STARTED:$PORT:$SERVER_PID"
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
日志:   /tmp/progress-ui-server-<PID>.log

停止服务器:
  kill <SERVER_PID>
```

## Error Handling

- **Script not found**: 提示用户检查插件安装路径
- **Port range exhausted**: 提示关闭占用 3737-3747 的其他进程
- **Server crash on start**: 显示日志内容帮助排查
```

**Step 3: Verify skill file**

Run: `ls plugins/progress-tracker/skills/ui-launcher/SKILL.md`
Expected: file listed

**Step 4: Commit**

```bash
git add plugins/progress-tracker/skills/ui-launcher/SKILL.md
git commit -m "feat(prog-ui): add ui-launcher skill with process-aware detection"
```

---

### Task 2: Create the command file `prog-ui.md`

**Files:**
- Create: `plugins/progress-tracker/commands/prog-ui.md`

**Step 1: Write the command file**

Following the existing pattern (command delegates to skill):

```markdown
---
description: Launch Progress UI web server and open browser
version: "1.0.0"
scope: command
inputs:
  - User request to open progress UI
outputs:
  - Server started on available port
  - Browser opened to UI
  - Server status displayed
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:ui-launcher"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
```

**Step 2: Verify file exists**

Run: `ls plugins/progress-tracker/commands/prog-ui.md`
Expected: file listed

**Step 3: Verify command follows skill-delegation pattern**

Run: `grep 'progress-tracker:ui-launcher' plugins/progress-tracker/commands/prog-ui.md`
Expected: match found (confirms command delegates to skill, not inline logic)

**Step 4: Commit**

```bash
git add plugins/progress-tracker/commands/prog-ui.md
git commit -m "feat(prog-ui): add /prog-ui command delegating to ui-launcher skill"
```

---

### Task 3: Update plugin.json description to reference prog-ui

**Files:**
- Modify: `plugins/progress-tracker/.claude-plugin/plugin.json`

**Step 1: Read current plugin.json**

Read the file to get exact content.

**Step 2: Update description to naturally mention prog-ui**

Change the `description` field to include the UI capability:

```json
{
  "name": "progress-tracker",
  "version": "1.2.0",
  "description": "Track long-running AI agent tasks with feature-based progress tracking, test-driven status updates, Git integration, and prog-ui web dashboard",
  "author": {
    "name": "siunin"
  },
  "license": "MIT",
  "keywords": [
    "progress-tracking",
    "tdd",
    "feature-development",
    "git-integration",
    "session-recovery",
    "task-management",
    "ai-agent",
    "workflow",
    "web-ui"
  ]
}
```

**Step 3: Verify grep passes**

Run: `grep 'prog-ui' plugins/progress-tracker/.claude-plugin/plugin.json`
Expected: match in description field

**Step 4: Commit**

```bash
git add plugins/progress-tracker/.claude-plugin/plugin.json
git commit -m "feat(prog-ui): update plugin description to reference web UI"
```

---

### Task 4: Update documentation source (PROG_COMMANDS.md)

**Files:**
- Modify: `plugins/progress-tracker/docs/PROG_COMMANDS.md`

**Step 1: Read current PROG_COMMANDS.md**

Read the file to identify exact insertion points.

**Step 2: Add /prog-ui to README_EN section**

Insert before `### Progress Manager CLI` (line 48):

```markdown
### `/prog-ui`

Launch the Progress UI web server and open in browser. Auto-detects available port (3737-3747). Detects if a server for the current project is already running.
```

**Step 3: Add /prog-ui to README_ZH section**

Insert before `### Progress Manager 命令行` (line 108):

```markdown
### `/prog-ui`

启动 Progress UI 网页服务器并在浏览器中打开。自动探测可用端口（3737-3747），检测当前项目是否已有运行中的服务器。
```

**Step 4: Add /prog-ui to PROG_HELP section**

Add to the Primary Commands list after the `/prog reset` line:

```markdown
- `/prog-ui`: launch web UI server and open browser.
```

**Step 5: Regenerate docs**

Run: `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --write`
Expected: docs updated successfully

**Step 6: Verify docs are in sync**

Run: `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check`
Expected: check passes (exit 0)

**Step 7: Commit**

```bash
git add plugins/progress-tracker/docs/PROG_COMMANDS.md plugins/progress-tracker/README.md plugins/progress-tracker/readme-zh.md plugins/progress-tracker/docs/PROG_HELP.md
git commit -m "docs(prog-ui): add /prog-ui to command documentation"
```

---

### Task 5: Behavioral end-to-end verification

This task verifies actual runtime behavior, not just file existence.

**Step 1: Verify no server is running**

```bash
pgrep -f progress_ui_server.py && echo "WARN: server already running" || echo "OK: no server running"
```

**Step 2: Start server via the same logic the skill uses**

```bash
SERVER_SCRIPT="plugins/progress-tracker/hooks/scripts/progress_ui_server.py"
nohup python3 "$SERVER_SCRIPT" --working-dir "$(pwd)" > /tmp/progress-ui-e2e-test.log 2>&1 &
E2E_PID=$!
sleep 1
```

**Step 3: Verify server is listening and responds**

```bash
PORT=$(lsof -nP -p $E2E_PID -iTCP -sTCP:LISTEN 2>/dev/null | awk '{split($9,a,":"); print a[2]}' | head -1)
echo "PORT=$PORT"
# Verify HTTP response
curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" | grep 200
```

Expected: HTTP 200

**Step 4: Verify process detection logic finds this instance**

```bash
for PID in $(pgrep -f progress_ui_server.py 2>/dev/null); do
  CMDLINE=$(ps -p "$PID" -o args= 2>/dev/null)
  if echo "$CMDLINE" | grep -q -- "--working-dir.*$(pwd)"; then
    echo "DETECTED:$PID"
  fi
done
```

Expected: outputs `DETECTED:<E2E_PID>`

**Step 5: Clean up test server**

```bash
kill $E2E_PID 2>/dev/null
sleep 0.5
pgrep -f progress_ui_server.py || echo "OK: server stopped"
rm -f /tmp/progress-ui-e2e-test.log
```

**Step 6: Verify all static artifacts**

```bash
# Command file
ls plugins/progress-tracker/commands/prog-ui.md && echo "✓ command file"

# Skill file
ls plugins/progress-tracker/skills/ui-launcher/SKILL.md && echo "✓ skill file"

# Plugin.json reference
grep 'prog-ui' plugins/progress-tracker/.claude-plugin/plugin.json && echo "✓ plugin.json"

# Documentation
grep -c 'prog-ui' plugins/progress-tracker/docs/PROG_COMMANDS.md | xargs -I{} echo "✓ {} references in PROG_COMMANDS.md"

# Command delegates to skill (not inline logic)
grep 'progress-tracker:ui-launcher' plugins/progress-tracker/commands/prog-ui.md && echo "✓ command→skill delegation"
```

Expected: all checks pass
