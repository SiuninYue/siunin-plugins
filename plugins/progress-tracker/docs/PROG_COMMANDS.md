# PROG Commands Source

Single source of truth for command help text, quick references, and generated command sections.

Do not edit generated sections in README/readme-zh/PROG_HELP directly. Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/generate_prog_docs.py --write
```

## Source Blocks

### README_EN

<!-- SOURCE:README_EN:START -->
### `/progress-tracker:prog-plan <project description>` (alias: `/prog-plan`)

Create architecture plan and technology decisions before feature implementation.

### `/progress-tracker:prog-init <goal description>` (alias: `/prog-init`)

Initialize progress tracking and break goal into testable features.

### `/progress-tracker:prog` (alias: `/prog`)

Show current project status and recommended next action.

### `/progress-tracker:prog-sync` (alias: `/prog-sync`)

Sync project capability memory from incremental Git history with batch confirmation.

### `/progress-tracker:prog-update` (alias: `/prog-update`)

Record a structured progress update entry and optional role owner assignment.

### `/progress-tracker:prog-next` (alias: `/prog-next`)

Start the next pending feature with deterministic complexity routing.

### `/progress-tracker:prog-start` (alias: `/prog-start`)

Transition the active feature from planning to developing.

### `/progress-tracker:prog-done` (alias: `/prog-done`)

Run acceptance verification and complete the current feature.

### `/progress-tracker:prog-fix` (alias: `/prog-fix`)

Report, list, investigate, and fix bugs with systematic debugging and TDD.

### `/progress-tracker:prog-undo` (alias: `/prog-undo`)

Revert the most recently completed feature safely via `git revert`.

### `/progress-tracker:prog-reset` (alias: `/prog-reset`)

Reset active progress tracking files after explicit confirmation (auto-archives previous snapshot).

### `/progress-tracker:help`

Show plugin command help (namespaced entry for conflict-free discovery).

### `/progress-tracker:prog-ui` (alias: `/prog-ui`)

Launch the Progress UI web server and open in browser. Auto-detects available port (3737-3747). Detects if a server for the current project is already running.

### Low-Learning-Cost Command Layers

Daily commands (default path):

- `/prog` → status + next recommendation
- `/prog-next` → start/continue the next actionable feature
- `/prog-done` → acceptance closeout for active feature

Admin commands (only when needed):

- `prog check` / `prog reconcile` for drift diagnostics
- `prog defer` / `prog resume` for backlog parking and restore
- `prog next-feature --json` for machine-driven feature selection

### Progress Manager CLI

Global scope override (recommended in monorepos):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py --project-root plugins/<name> status
```

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py init <project_name> [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py status
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py check
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reconcile [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py next-feature [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-archives [--limit <n>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py restore-archive <archive_id> [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-current <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete <feature_id> --commit <hash>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py defer (--all-pending|--feature-id <id>) --reason "<reason>" [--defer-group <group>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py resume (--all|--defer-group <group>)
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state --phase <phase> [--plan-path <path>] [--next-action <action>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-workflow-task <id> completed
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py clear-workflow-state
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> --complexity-score <score> --selected-model <model> --workflow-path <path>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete-feature-ai-metrics <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py auto-checkpoint
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py git-auto-preflight [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py sync-runtime-context [--source <session_start|manual>] [--quiet] [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan [--plan-path <path>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-feature <name> <test_steps...>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py undo
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reset [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-update --category <category> --summary "<summary>" [--details "<details>"] [--feature-id <id>] [--bug-id <BUG-ID>] [--role <role>] [--owner "<owner>"] [--source <source>] [--next-action "<next>"] [--ref <token> ...]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-updates [--limit <n>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-owner <feature_id> <architecture|coding|testing> "<owner|none>"
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-bug --description "<desc>" [--status <status>] [--priority <high|medium|low>] [--category <bug|technical_debt>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-bug --bug-id "BUG-XXX" [--status <status>] [--root-cause "<cause>"] [--fix-summary "<summary>"]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-bugs
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py remove-bug "BUG-XXX"
```

### Project Memory CLI

Global scope override (recommended in monorepos):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py --project-root plugins/<name> read
```

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py read
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py append --payload-json '<object>'
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py batch-upsert --payload-json '<array>' --sync-meta-json '<object>'
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py register-rejections --payload-json '<array>' --sync-id '<sync_id>'
```
<!-- SOURCE:README_EN:END -->

### README_ZH

<!-- SOURCE:README_ZH:START -->
### `/progress-tracker:prog-plan <项目描述>` (别名：`/prog-plan`)

在实施前完成技术选型、系统架构与关键决策记录。

### `/progress-tracker:prog-init <目标描述>` (别名：`/prog-init`)

初始化进度跟踪，并将目标拆分为可测试功能列表。

### `/progress-tracker:prog` (别名：`/prog`)

显示项目当前进度与推荐下一步。

### `/progress-tracker:prog-sync` (别名：`/prog-sync`)

从增量 Git 历史同步项目能力记忆，并进行批量确认写入。

### `/progress-tracker:prog-update` (别名：`/prog-update`)

记录结构化进度更新，并可选同步角色负责人。

### `/progress-tracker:prog-next` (别名：`/prog-next`)

按复杂度路由启动下一个待完成功能。

### `/progress-tracker:prog-start` (别名：`/prog-start`)

将当前活跃功能从规划阶段切换到开发阶段。

### `/progress-tracker:prog-done` (别名：`/prog-done`)

执行验收验证并完成当前功能。

### `/progress-tracker:prog-fix` (别名：`/prog-fix`)

报告、查看、调查并修复 Bug（系统化调试 + TDD）。

### `/progress-tracker:prog-undo` (别名：`/prog-undo`)

使用 `git revert` 安全撤销最近完成的功能。

### `/progress-tracker:prog-reset` (别名：`/prog-reset`)

在明确确认后重置当前活动进度文件（会自动归档旧快照）。

### `/progress-tracker:help`

显示插件命令帮助（命名空间入口，避免全局命令冲突）。

### `/progress-tracker:prog-ui` (别名：`/prog-ui`)

启动 Progress UI 网页服务器并在浏览器中打开。自动探测可用端口（3737-3747），检测当前项目是否已有运行中的服务器。

### 低学习成本命令分层

日常命令（默认路径）：

- `/prog`：看状态与下一步建议
- `/prog-next`：开始/继续下一个可执行功能
- `/prog-done`：对当前功能做验收收尾

管理命令（仅在需要时）：

- `prog check` / `prog reconcile`：诊断 tracker 漂移
- `prog defer` / `prog resume`：挂起与恢复 backlog
- `prog next-feature --json`：给自动化流程做机器可读选项

### Progress Manager 命令行

Monorepo 中建议显式指定作用域：

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py --project-root plugins/<name> status
```

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py init <project_name> [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py status
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py check
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reconcile [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py next-feature [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-archives [--limit <n>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py restore-archive <archive_id> [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-current <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete <feature_id> --commit <hash>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py defer (--all-pending|--feature-id <id>) --reason "<reason>" [--defer-group <group>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py resume (--all|--defer-group <group>)
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state --phase <phase> [--plan-path <path>] [--next-action <action>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-workflow-task <id> completed
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py clear-workflow-state
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> --complexity-score <score> --selected-model <model> --workflow-path <path>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete-feature-ai-metrics <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py auto-checkpoint
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py git-auto-preflight [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py sync-runtime-context [--source <session_start|manual>] [--quiet] [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan [--plan-path <path>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-feature <name> <test_steps...>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py undo
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reset [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-update --category <category> --summary "<summary>" [--details "<details>"] [--feature-id <id>] [--bug-id <BUG-ID>] [--role <role>] [--owner "<owner>"] [--source <source>] [--next-action "<next>"] [--ref <token> ...]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-updates [--limit <n>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-owner <feature_id> <architecture|coding|testing> "<owner|none>"
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-bug --description "<desc>" [--status <status>] [--priority <high|medium|low>] [--category <bug|technical_debt>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-bug --bug-id "BUG-XXX" [--status <status>] [--root-cause "<cause>"] [--fix-summary "<summary>"]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-bugs
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py remove-bug "BUG-XXX"
```

### Project Memory 命令行

Monorepo 中建议显式指定作用域：

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py --project-root plugins/<name> read
```

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

- `/progress-tracker:prog-plan <project description>` (alias: `/prog-plan`): architecture planning and stack decisions.
- `/progress-tracker:prog-init <goal description>` (alias: `/prog-init`): initialize tracking and feature decomposition.
- `/progress-tracker:prog` (alias: `/prog`): show progress status and recommendations.
- `/progress-tracker:prog-sync` (alias: `/prog-sync`): sync capability memory from incremental Git history.
- `/progress-tracker:prog-update` (alias: `/prog-update`): append structured updates and optional owner assignments.
- `/progress-tracker:prog-next` (alias: `/prog-next`): begin next feature using deterministic routing.
- `/progress-tracker:prog-start` (alias: `/prog-start`): transition the active feature from planning to developing.
- `/progress-tracker:prog-done` (alias: `/prog-done`): run acceptance checks and complete the current feature.
- `/progress-tracker:prog-fix [description|BUG-ID]` (alias: `/prog-fix`): report/list/fix bugs.
- `/progress-tracker:prog-undo` (alias: `/prog-undo`): revert the most recently completed feature.
- `/progress-tracker:prog-reset` (alias: `/prog-reset`): reset active tracking files with confirmation (auto-archive previous snapshot).
- `/progress-tracker:help`: show plugin command help (prefer namespaced form to avoid `/help` conflicts).
- `/progress-tracker:prog-ui` (alias: `/prog-ui`): launch web UI server and open browser.

## Operational Notes

- Command docs in README/readme-zh are generated from this file.
- Namespaced command format must not include a space after `:` (use `/progress-tracker:prog`, not `/progress-tracker: prog`).
- In monorepo root contexts, pass `--project-root plugins/<name>` to `progress_manager.py`, `project_memory.py`, and `progress_ui_server.py`.
- Use `generate_prog_docs.py --check` in CI-style validation.
- Use `generate_prog_docs.py --write` after changing this source.
<!-- SOURCE:PROG_HELP:END -->
