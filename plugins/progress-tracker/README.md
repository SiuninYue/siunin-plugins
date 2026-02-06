# Progress Tracker Plugin

Track long-running AI agent tasks with feature-based progress tracking, test-driven status updates, and Git integration. An intelligent development orchestrator that guides you through systematic, TDD-driven implementation.

## Overview

The Progress Tracker plugin solves a critical problem in AI-assisted development: **how to maintain progress across multi-session projects** without losing context or skipping testing.

### Core Problems Addressed

1. **Context Window Exhaustion** - Long tasks get compressed, losing progress memory
2. **Testing Skip** - Features marked "done" without verification don't actually work
3. **Session Interruption** - Closing the window means losing your place
4. **No Clear Progress** - Unclear what's done vs. what remains
5. **Skill Invocation Reliability** - Skills described but not executed

### Solutions

- **Feature List Driven** - Goals broken into specific, testable features
- **Test-Driven Status** - Features start `false`, only `true` after passing tests
- **Git as Memory** - Each feature commits, creating a clear history
- **External Persistence** - Progress stored in files, survives session restarts
- **Superpowers Integration** - Professional TDD workflow with enforced quality gates
- **Intelligent Session Recovery** - Auto-detects and guides resumption of interrupted work
- **Rich Progress Feedback** - Clear visual progress indicators and phase transitions

## Dependencies

This plugin integrates with the **Superpowers** skills library for systematic development workflows:

```bash
# Install Superpowers (recommended)
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

**Alternative**: You can still use the legacy **feature-dev** plugin, but Superpowers provides stronger TDD enforcement and code review processes.

```bash
# Legacy option (feature-dev)
claude plugins install feature-dev@claude-plugins-official
```

## Commands

### `/prog init <goal description>`

Initialize progress tracking for a new goal.

Analyzes your objective and breaks it down into 5-10 specific features with test steps.

**Example:**
```bash
/prog init Build a user authentication system with registration and login
```

**Behavior:**
- Checks for existing progress tracking
- Intelligently decomposes goal into features
- Defines test steps for each feature
- Orders features by dependency
- Creates `.claude/progress.json` and `.claude/progress.md`

### `/prog`

Display current project status.

Shows completion statistics, current feature, and next step recommendations.

**Example Output:**
```
## Project Progress: User Authentication

**Status**: 2/5 completed (40%)
**Current Feature**: Login API (in progress)

### Recommended Next Steps

Continue with current feature or run `/prog done` to complete.
```

### `/prog next`

Start implementing the next pending feature.

Automatically invokes the **feature-dev** plugin for guided implementation.

**Behavior:**
1. Identifies first uncompleted feature
2. Sets `current_feature_id`
3. Displays feature details and test steps
4. Launches `/feature-dev` workflow
5. Prompts to run `/prog done` when complete

### `/prog done`

Complete the current feature after testing.

Runs test steps, updates progress tracking, and creates a Git commit.

**Behavior:**
1. Executes all test steps defined for the feature
2. If tests fail → Reports error, keeps feature in progress
3. If tests pass → Creates Git commit, Marks complete
4. Updates `progress.json` (stores commit hash) and `progress.md`
5. Suggests next action

### `/prog fix`

Report, list, or fix bugs with smart scheduling and systematic debugging.

**Example:**
```bash
/prog fix "Users are logged out after refresh"
```

**Behavior:**
- Runs quick verification (under 30 seconds)
- Offers to record the bug or investigate immediately
- Schedules bugs into the feature timeline by priority
- Orchestrates Superpowers debugging + TDD fix + code review

## Maintenance Phase

Once development is underway, you may need to manage the project state.

### `/prog undo`

Revert the most recently completed feature.

**Behavior:**
1. **Safety Check**: Ensures git working directory is clean.
2. **Git Revert**: Creates a *new* commit that inverses the changes of the feature (safe for shared repos).
3. **Status Rollback**: Marks the feature as "pending" again in the tracker.

### `/prog reset`

Completely remove progress tracking from the project.

**Behavior:**
1. Asks for confirmation.
2. Deletes `.claude/progress.json` and `.claude/progress.md`.
3. **Does NOT** affect your code or Git history.

## Architecture

### Commands vs Skills

The plugin follows a **Commands → Skills** architecture:

| Component | Role | Description |
|-----------|------|-------------|
| **Commands** | Entry points | Thin layer that invokes skills |
| **Skills** | Logic | Reusable knowledge with business logic |
| **Hooks** | Events | SessionStart detects incomplete work |
| **Scripts** | State | Python script manages JSON/MD files |

### Skills (9 total)

1. **feature-breakdown** - Analyzes goals, creates feature lists
2. **progress-status** - Displays status and statistics
3. **feature-implement** - Orchestrates Superpowers workflow with complexity assessment
4. **feature-complete** - Validates workflow, runs tests, commits, updates state
5. **progress-recovery** - Auto-detects incomplete work, provides recovery options
6. **architectural-planning** - Coordinates architecture design and stack selection
7. **bug-fix** - Systematic bug triage, scheduling, and fixing workflow
8. **git-commit** - Creates conventional Git commits with auto-generated messages
9. **progress-management** - Workflow state operations, undo, reset

### Progress Manager Commands

The `progress_manager.py` script provides state management commands:

```bash
# Core commands
python3 progress_manager.py init <project_name> [--force]
python3 progress_manager.py status
python3 progress_manager.py check
python3 progress_manager.py set-current <feature_id>
python3 progress_manager.py complete <feature_id> --commit <hash>

# Workflow state commands (NEW)
python3 progress_manager.py set-workflow-state --phase <phase> [--plan-path <path>] [--next-action <action>]
python3 progress_manager.py update-workflow-task <id> completed
python3 progress_manager.py clear-workflow-state

# Feature management
python3 progress_manager.py add-feature <name> <test_steps...>
python3 progress_manager.py undo
python3 progress_manager.py reset [--force]

# Bug tracking
python3 progress_manager.py add-bug --description "<desc>" [--status <status>] [--priority <high|medium|low>]
python3 progress_manager.py update-bug --bug-id "BUG-XXX" [--status <status>] [--root-cause "<cause>"] [--fix-summary "<summary>"]
python3 progress_manager.py list-bugs
python3 progress_manager.py remove-bug "BUG-XXX"
```

### Progress Files

Stored in your project's `.claude/` directory:

**progress.json** - Machine-readable state:
```json
{
  "project_name": "User Authentication",
  "created_at": "2024-01-18T10:00:00Z",
  "features": [
    {
      "id": 1,
      "name": "User database model",
      "test_steps": ["Run migration", "Check table exists"],
      "completed": true
    },
    {
      "id": 2,
      "name": "Registration API",
      "test_steps": ["curl test endpoint", "Verify database"],
      "completed": false
    }
  ],
  "current_feature_id": 2
}
```

**progress.md** - Human-readable log:
```markdown
# Project Progress: User Authentication

## Completed
- [x] User database model (commit: abc123)

## In Progress
- [ ] Registration API
  Test steps:
  - POST /api/register with valid data
  - Check database for new user

## Pending
- [ ] Login API
- [ ] JWT token generation
```

## Workflow Example

```bash
# 1. Start a new project
/prog init Build a TODO app with CRUD operations

# → Creates feature list: database, API, frontend, etc.

# 2. Check status
/prog

# → Shows 0/5 complete

# 3. Start first feature (auto-invokes Superpowers workflow)
/prog next

╔════════════════════════════════════════════════════════╗
║  🚀 Starting Feature Implementation                    ║
╚════════════════════════════════════════════════════════╝

**Feature**: User Database Model
**Progress**: Feature 1/5 in project

**Acceptance Test Steps**:
✓ Run migrations successfully
✓ Verify users table exists
✓ Test user creation

**Complexity Assessment**: Simple
**Selected Workflow**: Direct TDD

---

⏳ Using superpowers:test-driven-development skill...
[RED-GREEN-REFACTOR cycle executes]

✅ Implementation Complete

**Next Step**: Run `/prog done` to finalize

# 4. Complete and commit
/prog done

## ✅ All Tests Passed!

Feature "User Database Model" has been successfully verified.

### Creating Git Commit
feat: complete user database model

[Commit created: abc1234]

**Remaining features**: 4

# [Session closes or restarts]

# 5. SessionStart hook detects incomplete work
╔════════════════════════════════════════════════════════╗
║  📋 Progress Tracker: Unfinished Work Detected        ║
╚════════════════════════════════════════════════════════╝

**Feature**: Registration API (ID: 2)
**Status**: execution - 2/5 tasks completed
**Plan**: docs/plans/2024-01-24-registration-api.md

### Recovery Options
1️⃣ Resume from Task 3 (Recommended)
2️⃣ Restart Execution
3️⃣ Re-create Plan
4️⃣ Skip Feature

# 6. Resume and continue
# (Select option 1 - automatic resume)

Resuming from task 3...
Progress: [████░░░░] 40% - Task 3/5
```

## Bug Tracking Example

```bash
# Report a bug with quick verification
/prog fix "Users are logged out after refresh"

# View backlog and pick a bug to fix
/prog fix

# Resume a specific bug by ID
/prog fix BUG-001
```

**Bug lifecycle**: pending_investigation → investigating → confirmed → fixing → fixed (or false_positive)

## Integration with Superpowers Skills

The Progress Tracker orchestrates **Superpowers** workflow skills for systematic, TDD-driven implementation:

| Responsibility | Component |
|----------------|-----------|
| Feature breakdown | progress-tracker |
| Progress state | progress-tracker |
| Acceptance testing | progress-tracker |
| Git commits (feature-level) | progress-tracker |
| Design exploration | superpowers:brainstorming |
| Implementation planning | superpowers:writing-plans |
| TDD execution | superpowers:test-driven-development |
| Subagent coordination | superpowers:subagent-driven-development |
| Code review (dual-stage) | superpowers reviewers |

**Key benefits of Superpowers integration**:
- ✅ **Enforced TDD**: Mandatory RED-GREEN-REFACTOR cycle
- ✅ **Dual-stage review**: Spec compliance + code quality
- ✅ **Task-level commits**: Clean Git history
- ✅ **Session recovery**: Resume interrupted workflows
- ✅ **Proven patterns**: Battle-tested development processes

**Workflow example**:
```bash
/prog next               # Progress Tracker selects feature
                         # → Assesses complexity
                         # → Invokes superpowers:writing-plans
                         # → Invokes superpowers:subagent-driven-development
                         # → Each task: TDD + review + commit
/prog done               # Progress Tracker runs acceptance tests
                         # → Creates feature commit
                         # → Updates progress.json
```

**Alternative: feature-dev plugin**

The legacy integration with feature-dev is still supported:
- Better for **legacy codebases** (has code-explorer for deep analysis)
- Superpowers is better for **new projects** (stronger process enforcement)

To use feature-dev instead, modify `skills/feature-implement/SKILL.md` to invoke `/feature-dev` as before.

## Quick Start

Get started with Progress Tracker in 3 steps:

```bash
# 1. Initialize your project
/prog init Build a user authentication system

# 2. Start the first feature
/prog next

# 3. Complete and commit
/prog done
```

**That's it!** The plugin will:
- ✅ Break down your goal into features
- ✅ Guide you through TDD implementation
- ✅ Run acceptance tests
- ✅ Create clean Git commits
- ✅ Remember your progress between sessions

## Directory Structure

```
plugins/progress-tracker/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   ├── prog.md
│   ├── prog-init.md
│   ├── prog-plan.md
│   ├── prog-next.md
│   ├── prog-fix.md
│   ├── prog-done.md
│   ├── prog-undo.md
│   └── prog-reset.md
├── skills/
│   ├── architectural-planning/
│   │   └── SKILL.md
│   ├── bug-fix/
│   │   └── SKILL.md
│   ├── feature-breakdown/
│   │   └── SKILL.md
│   ├── progress-status/
│   │   └── SKILL.md
│   ├── feature-implement/
│   │   └── SKILL.md
│   ├── feature-complete/
│   │   └── SKILL.md
│   ├── git-commit/
│   │   ├── SKILL.md
│   │   ├── references/
│   │   │   └── conventional-commits.md
│   │   └── examples/
│   │       ├── usage.md
│   │       └── integration.md
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

## Session Recovery

The plugin automatically detects incomplete work when you open a new session and provides intelligent recovery options.

**SessionStart Hook** checks:
1. Does `.claude/progress.json` exist?
2. Are there uncompleted features?
3. Is there a `current_feature_id` set?
4. What is the `workflow_state.phase`?
5. Are there uncommitted Git changes?

### Auto-Recovery Scenarios

**Scenario A: Implementation Complete**
```
✅ Implementation appears complete!

All tasks in the plan have been executed and committed.

**Recommended Action**: Run `/prog done` to finalize
```

**Scenario B: Almost Complete (80%+)**
```
⚙️ Almost complete: 4/5 tasks done

Resuming automatically in 3 seconds... (type 'stop' to cancel)
```

**Scenario C: Mid-Implementation**
```
╔════════════════════════════════════════════════════════╗
║  📋 Progress Tracker: Unfinished Work Detected        ║
╚════════════════════════════════════════════════════════╝

**Feature**: Registration API (ID: 2)
**Status**: execution - 2/5 tasks completed
**Plan**: docs/plans/2024-01-24-registration-api.md

### Recovery Options
1️⃣ Resume from Task 3 (Recommended)
2️⃣ Restart Execution
3️⃣ Re-create Plan
4️⃣ Skip Feature
```

### Workflow State Tracking

The plugin tracks detailed workflow state for accurate recovery:

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

**Phase values**:
- `design_complete` - Brainstorming done, ready for planning
- `planning_complete` - Plan created, ready for execution
- `execution` - Currently executing tasks
- `execution_complete` - All tasks done, ready for verification

## Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Test-Driven** | Features only complete after passing tests |
| **Git-Native** | Each feature commits, history is progress |
| **External State** | Progress in files, survives context loss |
| **Clear Separation** | Commands → Skills → Scripts |
| **Professional** | Leverages Superpowers for implementation |
| **Recoverable** | Session resumption with context |
| **Explicit Invocation** | CRITICAL blocks ensure skills actually execute |
| **Rich Feedback** | Progress bars, phase banners, next steps |
| **Convention over Config** | Smart defaults, no configuration needed |

## What's New (v2.0)

### P0 Core Reliability Improvements

1. **Skill Invocation Reliability**
   - `<CRITICAL>` blocks force explicit Skill tool calls
   - No more "describing skills" - skills are actually invoked
   - Complete examples for each skill invocation

2. **Workflow State Persistence**
   - New `set-workflow-state`, `update-workflow-task`, `clear-workflow-state` commands
   - JSON-formatted recovery information from `check` command
   - Smart recovery action recommendations

3. **Enhanced Session Recovery**
   - Auto-recovery for clear cases (execution_complete, 80%+ done)
   - Recovery banner with phase-based options
   - Error handling for missing/corrupted state

4. **User-Friendly Progress Feedback**
   - Feature start banner with complexity assessment
   - Progress bars: `[████░░] 33% - Phase 1/3 done`
   - Phase transition indicators
   - Completion summaries with next steps

5. **Workflow Completion Validation**
   - `/prog done` validates workflow_state before running tests
   - Prevents completion without going through Superpowers workflow
   - Guides recovery if workflow is incomplete

---

## Changelog

### v1.2.0 (2025-01-29)

#### 新增命令
- ✅ `/prog plan` - 架构规划命令
  - 技术栈推荐
  - 系统架构设计
  - 架构决策记录 (`.claude/architecture.md`)
  - 与 feature breakdown 的集成指导
- ✅ `/prog fix` - Bug 管理命令
  - Bug 报告与快速验证 (30秒)
  - 智能调度到功能时间线
  - Bug 生命周期追踪 (pending_investigation → investigating → confirmed → fixing → fixed)
  - 集成 Superpowers: systematic-debugging, test-driven-development, code-reviewer

#### 新增技能
- ✅ `architectural-planning` - 协调架构设计
- ✅ `bug-fix` - 系统化 Bug 处理
  - 三阶段工作流：验证 → 调度 → 修复
  - Bug CRUD 操作 (add-bug, update-bug, list-bugs, remove-bug)
  - 优先级计算 (基于严重性和范围)
- ✅ `progress-management` - 工作流状态操作

#### 功能增强
- 更新 progress_manager.py 添加 Bug 管理命令
- 添加 Bug 追踪数据结构到 progress.json
- 渐进式披露：bug-fix skill 包含 workflow.md, integration.md, session.md 示例
- 命令总数从 6 增加到 8
- 技能总数从 5 增加到 8

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

## License

MIT
