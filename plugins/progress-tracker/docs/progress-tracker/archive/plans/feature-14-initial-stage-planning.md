# Feature 14 Plan: `/prog next` 初始化为 planning 阶段

## Tasks

- 更新 `progress_manager.py`
  - 在 `set-current` 时为未完成功能写入 `development_stage = planning`
  - 提供统一的 `set-development-stage` 命令，支持 `planning|developing|completed`
  - 在 `complete` 时写入 `development_stage = completed`
- 更新 `prog-start` 结构与实现
  - 将命令注册改为标准 command `.md` 调 skill
  - 修复 `skills/prog-start/SKILL.md` frontmatter 与触发描述
  - 复用 `progress_manager.set_development_stage(\"developing\")`
- 更新 Progress UI 状态展示
  - 后端返回 `development_stage` 与 `stage_label`
  - `planning` 阶段显示“规划中”，并建议 `/prog start`
  - `developing` 阶段显示“开发中”，并建议 `/prog done`
- 补充自动化测试
  - `progress_manager` 阶段写入与命令入口测试
  - `progress_ui_status` 阶段文案与动作分流测试
  - `prog-start` command/skill 契约测试

## Acceptance Mapping

- `ls plugins/progress-tracker/skills/git-auto/SKILL.md`
  - 验证 Feature 14 目标 skill 文件存在（定位成功）
- `验证 /prog next 设置 development_stage = 'planning'`
  - 由 `test_progress_manager.py` 用例验证 `set_current()` 会写入 `planning`
- `测试新功能显示为'规划中'`
  - 由 `test_progress_ui_status.py` 用例验证 summary/detail 返回“规划中”
- `确认 progress.json 包含 development_stage 字段`
  - 活跃 feature 数据包含 `development_stage` 字段（实际状态检查）

## Risks

- 根目录 `.claude/progress.json` 被旧状态覆盖，导致当前 feature/workflow 丢失
  - 缓解：先恢复 `Feature 14` 上下文后再执行完成流程
- `feature-complete` 依赖 `workflow_state.plan_path`
  - 缓解：补齐最小合规计划文件并先跑 `validate-plan`
