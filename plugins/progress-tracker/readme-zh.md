# Progress Tracker 插件

使用基于功能的进度跟踪、测试驱动的状态更新和 Git 集成来跟踪长期运行的 AI 代理任务。这是一个智能开发编排器，引导您完成系统化的 TDD 驱动实现。

## 概述

Progress Tracker 插件解决了 AI 辅助开发中的一个关键问题：**如何在跨会话项目中保持进度**，同时避免丢失上下文或跳过测试。

### 解决的核心问题

1. **上下文窗口耗尽** - 长时间运行的任务被压缩，导致进度记忆丢失
2. **跳过测试** - 未经验证就被标记为"完成"的功能实际上并不工作
3. **会话中断** - 关闭窗口意味着丢失当前进度位置
4. **进度不清晰** - 不清楚哪些已完成、哪些待完成
5. **技能调用不可靠** - 技能被描述但未实际执行

### 解决方案

- **功能列表驱动** - 目标被分解为具体的、可测试的功能
- **测试驱动状态** - 功能开始时为 `false`，仅通过测试后才变为 `true`
- **Git 作为记忆** - 每个功能都会提交，创建清晰的历史记录
- **外部持久化** - 进度存储在文件中，可经受会话重启
- **Superpowers 集成** - 专业 TDD 工作流程，强制执行质量门控
- **智能会话恢复** - 自动检测并引导中断工作的恢复
- **丰富的进度反馈** - 清晰的视觉进度指示器和阶段转换
- **确定性模型路由** - 按复杂度显式路由到 haiku/sonnet/opus 路径
- **轻量 AI 统计** - 仅记录复杂度、模型和时长（不做 token/cost 估算）
- **技术债归一化** - 技术债复用现有 bug 体系（`category=technical_debt`）
- **轻量检查点** - 自动快照写入 `.claude/checkpoints.json`（不创建 git 提交）

## 依赖项

此插件集成 **Superpowers** 技能库以实现系统化的开发工作流程：

```bash
# 安装 Superpowers（推荐）
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

**备选方案**：您仍然可以使用传统的 **feature-dev** 插件，但 Superpowers 提供了更强的 TDD 强制执行和代码审查流程。

## 快速开始

只需 3 步即可开始使用 Progress Tracker：

```bash
# 1. 初始化您的项目
/prog init 构建一个用户认证系统

# 2. 开始第一个功能
/prog next

# 3. 完成并提交
/prog done
```

**对于复杂项目**，可以先进行架构规划：

```bash
# 1. 架构规划（可选）
/prog plan 构建分布式电商系统
# → 技术选型：Python + FastAPI + PostgreSQL
# → 系统架构设计
# → 生成 .claude/architecture.md

# 2. 基于架构初始化功能
/prog init 构建分布式电商系统
# → 自动读取架构决策
# → 生成 Python 特定的功能列表（SQLAlchemy、Pydantic、Alembic）

# 3. 开始实施
/prog next
```

**就是这样！** 插件将：
- ✅ 将您的目标分解为功能
- ✅ 引导您完成 TDD 实现
- ✅ 运行验收测试
- ✅ 创建干净的 Git 提交
- ✅ 在会话之间记住您的进度

## 命令

本节命令说明由 `docs/PROG_COMMANDS.md` 自动生成。

<!-- BEGIN:GENERATED:PROG_COMMANDS -->
<!-- GENERATED CONTENT: DO NOT EDIT DIRECTLY -->
### `/progress-tracker:prog-plan <项目描述>` (别名：`/prog-plan`)

在实施前完成技术选型、系统架构与关键决策记录。

### `/progress-tracker:prog-init <目标描述>` (别名：`/prog-init`)

初始化进度跟踪，并将目标拆分为可测试功能列表。

### `/progress-tracker:prog` (别名：`/prog`)

显示项目当前进度与推荐下一步。

### `/progress-tracker:prog-sync` (别名：`/prog-sync`)

从增量 Git 历史同步项目能力记忆，并进行批量确认写入。

### `/progress-tracker:prog-next` (别名：`/prog-next`)

按复杂度路由启动下一个待完成功能。

### `/progress-tracker:prog-done` (别名：`/prog-done`)

执行验收验证并完成当前功能。

### `/progress-tracker:prog-fix` (别名：`/prog-fix`)

报告、查看、调查并修复 Bug（系统化调试 + TDD）。

### `/progress-tracker:prog-undo` (别名：`/prog-undo`)

使用 `git revert` 安全撤销最近完成的功能。

### `/progress-tracker:prog-reset` (别名：`/prog-reset`)

在明确确认后重置进度跟踪文件。

### `/progress-tracker:help`

显示插件命令帮助（命名空间入口，避免全局命令冲突）。

### `/progress-tracker:prog-ui` (别名：`/prog-ui`)

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
<!-- END:GENERATED:PROG_COMMANDS -->

## 架构

### 命令 vs 技能

插件遵循 **命令 → 技能** 架构：

| 组件 | 角色 | 描述 |
|-----------|------|-------------|
| **命令** | 入口点 | 调用技能的薄层 |
| **技能** | 逻辑 | 具有业务逻辑的可重用知识 |
| **钩子** | 事件 | SessionStart 检测未完成的工作 |
| **脚本** | 状态 | Python 脚本管理 JSON/MD 文件 |

### 技能（共 11 个）

1. **feature-breakdown** - 分析目标，创建功能列表
2. **progress-status** - 显示状态和统计信息
3. **architectural-planning** - 技术选型、系统架构设计、架构决策记录
4. **feature-implement** - 编排 Superpowers 工作流程，进行复杂度评估
5. **feature-complete** - 验证工作流程，运行测试，提交，更新状态
6. **progress-recovery** - 自动检测未完成的工作，提供恢复选项
7. **bug-fix** - 系统化 Bug/技术债管理
8. **git-auto** - 智能 Git 自动化：分支、提交、推送、PR 创建（智能决策）
9. **progress-management** - 工作流状态操作与管理
10. **feature-implement-simple** - Haiku 简单路径执行
11. **feature-implement-complex** - Opus 复杂路径执行

### Progress Manager 命令

Progress Manager 命令清单已由 `docs/PROG_COMMANDS.md` 生成到上方“命令”章节。  
修改真源后请运行：`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/generate_prog_docs.py --write`。

### 进度文件

存储在项目的 `.claude/` 目录中：

**progress.json** - 机器可读状态：
```json
{
  "project_name": "用户认证",
  "created_at": "2024-01-18T10:00:00Z",
  "features": [
    {
      "id": 1,
      "name": "用户数据库模型",
      "test_steps": ["运行迁移", "检查表是否存在"],
      "completed": true
    },
    {
      "id": 2,
      "name": "注册 API",
      "test_steps": ["curl 测试端点", "验证数据库"],
      "completed": false,
      "ai_metrics": {
        "complexity_score": 18,
        "complexity_bucket": "standard",
        "selected_model": "sonnet",
        "workflow_path": "plan_execute",
        "started_at": "2026-02-11T10:00:00Z",
        "finished_at": "2026-02-11T10:08:30Z",
        "duration_seconds": 510
      }
    }
  ],
  "current_feature_id": 2
}
```

**checkpoints.json** - 轻量自动检查点：

```json
{
  "last_checkpoint_at": "2026-02-11T10:30:00Z",
  "max_entries": 50,
  "entries": [
    {
      "timestamp": "2026-02-11T10:30:00Z",
      "feature_id": 2,
      "feature_name": "注册 API",
      "phase": "execution",
      "plan_path": "docs/plans/feature-2-registration-api.md",
      "current_task": 2,
      "total_tasks": 5,
      "reason": "auto_interval"
    }
  ]
}
```

**progress.md** - 人类可读日志：

```markdown
# 项目进度：用户认证

## 已完成
- [x] 用户数据库模型（提交：abc123）

## 进行中
- [ ] 注册 API
  测试步骤：
  - POST /api/register 使用有效数据
  - 检查数据库中的新用户

## 待完成
- [ ] 登录 API
- [ ] JWT 令牌生成
```

### 计划文档边界

- 架构主文档：`.claude/architecture.md`
- 功能执行计划：`docs/plans/feature-*.md`
- `workflow_state.plan_path` 必须始终指向 `docs/plans/*.md`

**architecture.md** - 架构决策记录（可选）：

```markdown
# Architecture: 电商系统

**Created**: 2024-01-25T10:00:00Z

## Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| Backend   | Python + FastAPI | 高性能，自动API文档 |
| Database  | PostgreSQL | ACID支持，成熟稳定 |
| Cache     | Redis | 高性能缓存层 |

## Architectural Decisions

### ADR-001: 选择 FastAPI 而非 Express

**Context**: 需要高性能异步后端

**Decision**: FastAPI + Python 3.11

**Consequences**:
- Positive: 自动OpenAPI文档，类型检查
- Negative: 异步生态不如Node.js成熟

## System Architecture

[架构图或描述]
```
```markdown
# 项目进度：用户认证

## 已完成
- [x] 用户数据库模型（提交：abc123）

## 进行中
- [ ] 注册 API
  测试步骤：
  - POST /api/register 使用有效数据
  - 检查数据库中的新用户

## 待完成
- [ ] 登录 API
- [ ] JWT 令牌生成
```

## 架构规划与功能分解的集成

`/prog plan` 和 `/prog init` 可以独立使用或组合使用，提供灵活的开发工作流。

### 工作流 1：快速启动（仅使用 init）

适合简单项目或快速原型：

```bash
/prog init 添加评论功能
# → 直接生成通用功能列表
# → 不依赖特定技术栈

/prog next  # 开始实施
```

### 工作流 2：规划优先（plan + init）

适合中大型项目或团队协作：

```bash
# 步骤 1：先做架构规划
/prog plan 构建电商系统
# → 选择技术栈：Python + FastAPI + PostgreSQL
# → 设计系统架构
# → 生成 .claude/architecture.md

# 步骤 2：基于架构生成功能
/prog init 构建电商系统
# → 自动读取架构决策
# → 生成 Python 特定功能：
#   • "Create SQLAlchemy models for Product"
#   • "Implement POST /api/products with FastAPI"
#   • "Add Pydantic schemas for validation"
#   • "Write Alembic migration for products table"

/prog next  # 开始实施
```

### 智能集成

当 `.claude/architecture.md` 存在时，`/prog init` 会：

1. **读取技术栈**：了解使用的技术（语言、框架、数据库）
2. **适配功能描述**：生成与该技术匹配的功能名称
3. **定制测试步骤**：使用该技术的测试命令
4. **引用架构决策**：在实施时参考设计约束

**示例对比**：

| 架构 | 功能列表示例 |
|------|-------------|
| **Node.js + Express** | "Create Sequelize models", "Implement Express router", "Add Joi validation" |
| **Python + FastAPI** | "Create SQLAlchemy models", "Implement FastAPI endpoint", "Add Pydantic schemas" |
| **Go + Gin** | "Define Go structs", "Implement Gin handler", "Add validator package" |

## 工作流程示例

```bash
# 1. 开始新项目
/prog init 构建一个具有 CRUD 操作的 TODO 应用

# → 创建功能列表：数据库、API、前端等

# 2. 检查状态
/prog

# → 显示 0/5 已完成

# 3. 开始第一个功能（自动调用 Superpowers 工作流程）
/prog next

╔════════════════════════════════════════════════════════╗
║  🚀 Starting Feature Implementation                    ║
╚════════════════════════════════════════════════════════╝

**功能**: 用户数据库模型
**进度**: 项目中的功能 1/5

**验收测试步骤**:
✓ 成功运行迁移
✓ 验证 users 表存在
✓ 测试用户创建

**复杂度评估**: Simple
**选择的工作流程**: 直接 TDD

---

⏳ 使用 superpowers:test-driven-development 技能...
[执行 RED-GREEN-REFACTOR 循环]

✅ 实现完成

**下一步**: 运行 `/prog done` 来完成

# 4. 完成并提交
/prog done

## ✅ 所有测试通过！

功能 "用户数据库模型" 已成功验证。

### 创建 Git 提交
feat: complete user database model

[已创建提交: abc1234]

**剩余功能**: 4

# [会话关闭或重启]

# 5. SessionStart 钩子检测未完成的工作
╔════════════════════════════════════════════════════════╗
║  📋 Progress Tracker: Unfinished Work Detected        ║
╚════════════════════════════════════════════════════════╝

**功能**: 注册 API (ID: 2)
**状态**: execution - 已完成 2/5 任务
**计划**: docs/plans/2024-01-24-registration-api.md

### 恢复选项
1️⃣ 从任务 3 恢复（推荐）
2️⃣ 重新开始执行
3️⃣ 重新创建计划
4️⃣ 跳过此功能

# 6. 恢复并继续
# (选择选项 1 - 自动恢复)

从任务 3 恢复...
进度: [████░░░] 40% - 任务 3/5
```

## 与 Superpowers 技能集成

Progress Tracker 编排 **Superpowers** 工作流程技能以实现系统化的、TDD 驱动的实现：

| 职责 | 组件 |
|----------------|--------|
| 功能分解 | progress-tracker |
| 进度状态 | progress-tracker |
| 验收测试 | progress-tracker |
| Git 提交（功能级别） | progress-tracker |
| 设计探索 | superpowers:brainstorming |
| 实现规划 | superpowers:writing-plans |
| TDD 执行 | superpowers:test-driven-development |
| Subagent 协调 | superpowers:subagent-driven-development |
| 代码审查（双阶段） | superpowers reviewers |

**Superpowers 集成的关键优势**：
- ✅ **强制 TDD**：强制 RED-GREEN-REFACTOR 循环
- ✅ **双阶段审查**：规范合规性 + 代码质量
- ✅ **任务级提交**：干净的 Git 历史
- ✅ **会话恢复**：恢复中断的工作流程
- ✅ **经过验证的模式**：经过实战测试的开发流程

**工作流程示例**：
```bash
/prog next               # Progress Tracker 选择功能
                         # → 评估复杂度
                         # → 调用 superpowers:writing-plans
                         # → 调用 superpowers:subagent-driven-development
                         # → 每个任务: TDD + 审查 + 提交
/prog done               # Progress Tracker 运行验收测试
                         # → 创建功能提交
                         # → 更新 progress.json
```

**备选方案：feature-dev 插件**

仍然支持与 feature-dev 的传统集成：
- 更适合 **遗留代码库**（具有 code-explorer 用于深度分析）
- Superpowers 更适合 **新项目**（更强的流程强制执行）

要使用 feature-dev，请修改 `skills/feature-implement/SKILL.md` 以像以前一样调用 `/feature-dev`。

## 目录结构

```
plugins/progress-tracker/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   ├── prog.md
│   ├── prog-init.md
│   ├── prog-plan.md        # 架构规划命令
│   ├── prog-next.md
│   ├── prog-fix.md         # Bug 管理命令
│   ├── prog-done.md
│   ├── prog-undo.md
│   └── prog-reset.md
├── skills/
│   ├── architectural-planning/  # 架构规划技能
│   │   └── SKILL.md
│   ├── bug-fix/               # Bug 修复技能
│   │   └── SKILL.md
│   ├── feature-breakdown/
│   │   └── SKILL.md
│   ├── progress-status/
│   │   └── SKILL.md
│   ├── feature-implement/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── complexity-assessment.md
│   ├── feature-implement-simple/
│   │   └── SKILL.md
│   ├── feature-implement-complex/
│   │   └── SKILL.md
│   ├── feature-complete/
│   │   └── SKILL.md
│   ├── progress-management/
│   │   └── SKILL.md
│   └── progress-recovery/
│       └── SKILL.md
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       └── progress_manager.py
├── .gitignore
├── LICENSE
├── plugin.md
├── README.md
└── readme-zh.md
```

## 会话恢复

当您打开新会话时，插件会自动检测未完成的工作并提供智能恢复选项。

**SessionStart 钩子**检查：
1. `.claude/progress.json` 是否存在？
2. 是否有未完成的功能？
3. 是否设置了 `current_feature_id`？
4. `workflow_state.phase` 是什么？
5. 是否有未提交的 Git 更改？

**UserPromptSubmit 钩子**：
- 每 30 分钟自动创建轻量检查点
- 快照保存到 `.claude/checkpoints.json`
- 不执行 git commit

### 自动恢复场景

**场景 A：实现完成**
```
✅ 实现似乎已完成！

计划中的所有任务都已执行并提交。

**推荐操作**: 运行 `/prog done` 来完成
```

**场景 B：几乎完成（80%+）**
```
⚙️ 几乎完成: 已完成 4/5 任务

将在 3 秒后自动恢复...（输入 'stop' 取消）
```

**场景 C：实现过程中**
```
╔════════════════════════════════════════════════════════╗
║  📋 Progress Tracker: Unfinished Work Detected        ║
╚════════════════════════════════════════════════════════╝

**功能**: 注册 API (ID: 2)
**状态**: execution - 已完成 2/5 任务
**计划**: docs/plans/2024-01-24-registration-api.md

### 恢复选项
1️⃣ 从任务 3 恢复（推荐）
2️⃣ 重新开始执行
3️⃣ 重新创建计划
4️⃣ 跳过此功能
```

### 工作流状态追踪

插件追踪详细的工作流状态以实现准确恢复：

```json
{
  "current_feature_id": 2,
  "workflow_state": {
    "phase": "execution",
    "plan_path": "docs/plans/2024-01-24-registration-api.md",
    "completed_tasks": [1, 2],
    "current_task": 3,
    "total_tasks": 5,
    "next_action": "verify_and_complete"
  }
}
```

**Phase 值**：
- `design_complete` - 头脑风暴完成，准备规划
- `planning_complete` - 计划已创建，准备执行
- `execution` - 当前正在执行任务
- `execution_complete` - 所有任务完成，准备验证

## 设计原则

| 原则 | 实现 |
|-----------|----------------|
| **测试驱动** | 功能仅通过测试后才完成 |
| **Git 原生** | 每个功能都提交，历史即进度 |
| **外部状态** | 进度存储在文件中，经受上下文丢失 |
| **清晰分离** | 命令 → 技能 → 脚本 |
| **专业** | 利用 Superpowers 进行实现 |
| **可恢复** | 带有上下文的会话恢复 |
| **显式调用** | CRITICAL 块确保技能实际执行 |
| **丰富反馈** | 进度条、阶段横幅、下一步操作 |
| **约定优于配置** | 智能默认值，无需配置 |

## 新增功能 (v2.0)

### v1.2.0 (2025-01-29)

#### 架构规划功能
- ✅ 新增 `/prog plan` 命令：技术选型和系统架构设计
- ✅ 新增 `architectural-planning` 技能：
  - 交互式技术栈选择
  - 系统架构设计指导
  - 架构决策记录（ADR）生成
  - 保存到 `.claude/architecture.md`
- ✅ 更新 `feature-breakdown` 技能：
  - 自动读取架构文档
  - 基于技术选型生成适配的功能列表
  - 技术特定的测试步骤
- ✅ 更新 `feature-implement` 技能：
  - 实施时读取架构上下文
  - 参考架构决策约束

**设计理念**：职责分离
- `/prog plan` 回答"如何构建"（技术选型、架构设计）
- `/prog init` 回答"构建什么"（功能分解）
- 可独立使用或组合使用

#### Bug 管理功能
- ✅ 新增 `/prog-fix` 命令：报告、列出或修复 Bug
- ✅ 新增 `bug-fix` 技能：
  - 三阶段工作流：快速验证 (30秒) → 智能调度 → 系统修复
  - Bug 生命周期追踪 (pending_investigation → investigating → confirmed → fixing → fixed)
  - 集成 Superpowers: systematic-debugging, test-driven-development, code-reviewer
  - Bug CRUD 操作 (add-bug, update-bug, list-bugs, remove-bug)
  - 优先级智能计算 (基于严重性和范围)
  - 渐进式文档：workflow.md, integration.md, session.md

#### 统计更新
- 命令总数：6 → 8
- 技能总数：5 → 8
- 新增 `progress-management` 技能用于工作流状态操作

### v1.1.0 (2025-01-25)

#### 规范完善
- ✅ 添加 `STANDARDS.md`：定义共享的 frontmatter schema 约定
- ✅ 添加 `CHANGELOG.md`：完整的版本历史记录
- ✅ 修复所有 7 个 commands 的 frontmatter，添加必填字段
  - 新增字段：`version`, `scope`, `inputs`, `outputs`, `evidence`, `references`

#### 测试覆盖
- ✅ 新增 `tests/` 目录，包含 pytest 测试套件
  - `test_progress_manager.py` - 核心功能测试
  - `test_workflow_state.py` - 工作流状态测试
  - `test_git_integration.py` - Git 集成测试
  - `conftest.py` - 测试配置和 fixtures

#### 功能增强
- 更新 `plugin.json` hooks 配置
- 增强进度管理器的命令行接口

### v1.0.0
- 初始版本，包含完整的进度追踪功能

### P0 核心可靠性改进

1. **技能调用可靠性**
   - `<CRITICAL>` 块强制显式 Skill tool 调用
   - 不再"描述技能" - 技能实际被调用
   - 每个技能调用的完整示例

2. **工作流状态持久化**
   - 新增 `set-workflow-state`、`update-workflow-task`、`clear-workflow-state` 命令
   - `check` 命令输出 JSON 格式的恢复信息
   - 智能恢复操作推荐

3. **增强的会话恢复**
   - 明确场景的自动恢复（execution_complete、80%+ 完成）
   - 带有基于阶段选项的恢复横幅
   - 缺失/损坏状态的错误处理

4. **用户友好的进度反馈**
   - 功能启动横幅，带有复杂度评估
   - 进度条：`[████░░] 33% - 阶段 1/3 完成`
   - 阶段转换指示器
   - 带有下一步操作的完成摘要

5. **工作流完成验证**
   - `/prog done` 在运行测试前验证 workflow_state
   - 防止在没有经过 Superpowers 工作流的情况下完成
   - 如果工作流不完整，引导恢复

## 许可证

MIT
