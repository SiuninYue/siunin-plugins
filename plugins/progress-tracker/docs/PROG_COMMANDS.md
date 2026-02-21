# PROG Commands Source

Single source of truth for command help text, quick references, and generated command sections.

Do not edit generated sections in README/readme-zh/PROG_HELP directly. Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/generate_prog_docs.py --write
```

## Source Blocks

### README_EN

<!-- SOURCE:README_EN:START -->
### `/prog plan <project description>`

Create architecture plan and technology decisions before feature implementation.

### `/prog init <goal description>`

Initialize progress tracking and break goal into testable features.

### `/prog`

Show current project status and recommended next action.

### `/prog sync`

Sync project capability memory from incremental Git history with batch confirmation.

### `/prog next`

Start the next pending feature with deterministic complexity routing.

### `/prog done`

Run acceptance verification and complete the current feature.

### `/prog-fix`

Report, list, investigate, and fix bugs with systematic debugging and TDD.

### `/prog undo`

Revert the most recently completed feature safely via `git revert`.

### `/prog reset`

Reset progress tracking files after explicit confirmation.

### `/progress-tracker:help`

Show plugin command help (namespaced entry for conflict-free discovery).

### `/prog-ui`

Launch the Progress UI web server and open in browser. Auto-detects available port (3737-3747). Detects if a server for the current project is already running.

### Progress Manager CLI

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py init <project_name> [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py status
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py check
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-current <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete <feature_id> --commit <hash>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state --phase <phase> [--plan-path <path>] [--next-action <action>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-workflow-task <id> completed
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py clear-workflow-state
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> --complexity-score <score> --selected-model <model> --workflow-path <path>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete-feature-ai-metrics <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py auto-checkpoint
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan [--plan-path <path>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-feature <name> <test_steps...>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py undo
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reset [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-bug --description "<desc>" [--status <status>] [--priority <high|medium|low>] [--category <bug|technical_debt>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-bug --bug-id "BUG-XXX" [--status <status>] [--root-cause "<cause>"] [--fix-summary "<summary>"]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-bugs
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py remove-bug "BUG-XXX"
```

### Project Memory CLI

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py read
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py append --payload-json '<object>'
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py batch-upsert --payload-json '<array>' --sync-meta-json '<object>'
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py register-rejections --payload-json '<array>' --sync-id '<sync_id>'
```
<!-- SOURCE:README_EN:END -->

### README_ZH

<!-- SOURCE:README_ZH:START -->
### `/prog plan <项目描述>`

在实施前完成技术选型、系统架构与关键决策记录。

### `/prog init <目标描述>`

初始化进度跟踪，并将目标拆分为可测试功能列表。

### `/prog`

显示项目当前进度与推荐下一步。

### `/prog sync`

从增量 Git 历史同步项目能力记忆，并进行批量确认写入。

### `/prog next`

按复杂度路由启动下一个待完成功能。

### `/prog done`

执行验收验证并完成当前功能。

### `/prog-fix`

报告、查看、调查并修复 Bug（系统化调试 + TDD）。

### `/prog undo`

使用 `git revert` 安全撤销最近完成的功能。

### `/prog reset`

在明确确认后重置进度跟踪文件。

### `/progress-tracker:help`

显示插件命令帮助（命名空间入口，避免全局命令冲突）。

### `/prog-ui`

启动 Progress UI 网页服务器并在浏览器中打开。自动探测可用端口（3737-3747），检测当前项目是否已有运行中的服务器。

### Progress Manager 命令行

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py init <project_name> [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py status
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py check
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-current <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete <feature_id> --commit <hash>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state --phase <phase> [--plan-path <path>] [--next-action <action>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-workflow-task <id> completed
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py clear-workflow-state
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> --complexity-score <score> --selected-model <model> --workflow-path <path>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete-feature-ai-metrics <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py auto-checkpoint
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan [--plan-path <path>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-feature <name> <test_steps...>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py undo
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reset [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-bug --description "<desc>" [--status <status>] [--priority <high|medium|low>] [--category <bug|technical_debt>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-bug --bug-id "BUG-XXX" [--status <status>] [--root-cause "<cause>"] [--fix-summary "<summary>"]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-bugs
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py remove-bug "BUG-XXX"
```

### Project Memory 命令行

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py read
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py append --payload-json '<object>'
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py batch-upsert --payload-json '<array>' --sync-meta-json '<object>'
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py register-rejections --payload-json '<array>' --sync-id '<sync_id>'
```
<!-- SOURCE:README_ZH:END -->

### PROG_HELP

<!-- SOURCE:PROG_HELP:START -->
# PROG Command Help

## Primary Commands

- `/prog plan <project description>`: architecture planning and stack decisions.
- `/prog init <goal description>`: initialize tracking and feature decomposition.
- `/prog`: show progress status and recommendations.
- `/prog sync`: sync capability memory from incremental Git history.
- `/prog next`: begin next feature using deterministic routing.
- `/prog done`: run acceptance checks and complete current feature.
- `/prog-fix [description|BUG-ID]`: report/list/fix bugs.
- `/prog undo`: revert most recently completed feature.
- `/prog reset`: reset tracking files with confirmation.
- `/progress-tracker:help`: show plugin command help (namespaced).
- `/prog-ui`: launch web UI server and open browser.

## Operational Notes

- Command docs in README/readme-zh are generated from this file.
- Use `generate_prog_docs.py --check` in CI-style validation.
- Use `generate_prog_docs.py --write` after changing this source.
<!-- SOURCE:PROG_HELP:END -->
