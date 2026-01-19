# Progress Tracker 插件

使用基于功能的进度跟踪、测试驱动的状态更新和 Git 集成来跟踪长期运行的 AI 代理任务。

## 概述

Progress Tracker 插件解决了 AI 辅助开发中的一个关键问题：**如何在跨会话项目中保持进度**，同时避免丢失上下文或跳过测试。

### 解决的核心问题

1. **上下文窗口耗尽** - 长时间运行的任务被压缩，导致进度记忆丢失
2. **跳过测试** - 未经验证就被标记为"完成"的功能实际上并不工作
3. **会话中断** - 关闭窗口意味着丢失当前进度位置
4. **进度不清晰** - 不清楚哪些已完成、哪些待完成

### 解决方案

- **功能列表驱动** - 目标被分解为具体的、可测试的功能
- **测试驱动状态** - 功能开始时为 `false`，仅通过测试后才变为 `true`
- **Git 作为记忆** - 每个功能都会提交，创建清晰的历史记录
- **外部持久化** - 进度存储在文件中，可经受会话重启
- **feature-dev 集成** - 通过官方插件实现专业的工作流程

## 依赖项

此插件需要 **feature-dev** 官方插件：

```bash
# 安装所需的依赖项
claude plugins install feature-dev@claude-plugins-official
```

## 命令

### `/prog init <目标描述>`

为新目标初始化进度跟踪。

分析您的目标并将其分解为 5-10 个具有测试步骤的具体功能。

**示例：**
```bash
/prog init 构建一个包含注册和登录功能的用户认证系统
```

**行为：**
- 检查现有的进度跟踪
- 智能地将目标分解为功能
- 为每个功能定义测试步骤
- 按依赖关系排序功能
- 创建 `.claude/progress.json` 和 `.claude/progress.md`

### `/prog`

显示当前项目状态。

显示完成统计、当前功能和推荐的下一步操作。

**示例输出：**
```
## 项目进度：用户认证

**状态**：2/5 已完成（40%）
**当前功能**：登录 API（进行中）

### 推荐的下一步

继续当前功能或运行 `/prog done` 来完成它。
```

### `/prog next`

开始实现下一个待完成的功能。

自动调用 **feature-dev** 插件进行引导式实现。

**行为：**
1. 识别第一个未完成的功能
2. 设置 `current_feature_id`
3. 显示功能详情和测试步骤
4. 启动 `/feature-dev` 工作流程
5. 完成后提示运行 `/prog done`

### `/prog done`

在测试后完成当前功能。

运行测试步骤、更新进度跟踪并创建 Git 提交。

**行为：**
1. 执行为该功能定义的所有测试步骤
2. 如果测试失败 → 报告错误，保持功能进行中状态
3. 如果测试通过 → 创建 Git 提交，标记为完成
4. 更新 `progress.json`（存储提交哈希）和 `progress.md`
5. 建议下一步操作

## 维护阶段

一旦开发开始，您可能需要管理项目状态。

### `/prog undo`

恢复最近完成的功能。

**行为：**
1. **安全检查**：确保 git 工作目录是干净的。
2. **Git 恢复**：创建一个*新的*提交来反向更改该功能（对共享仓库是安全的）。
3. **状态回滚**：在跟踪器中将该功能再次标记为"待完成"。

### `/prog reset`

完全从项目中删除进度跟踪。

**行为：**
1. 请求确认。
2. 删除 `.claude/progress.json` 和 `.claude/progress.md`。
3. **不会**影响您的代码或 Git 历史。

## 架构

### 命令 vs 技能

插件遵循 **命令 → 技能** 架构：

| 组件 | 角色 | 描述 |
|-----------|------|-------------|
| **命令** | 入口点 | 调用技能的薄层 |
| **技能** | 逻辑 | 具有业务逻辑的可重用知识 |
| **钩子** | 事件 | SessionStart 检测未完成的工作 |
| **脚本** | 状态 | Python 脚本管理 JSON/MD 文件 |

### 技能（共 5 个）

1. **feature-breakdown** - 分析目标，创建功能列表
2. **progress-status** - 显示状态和统计信息
3. **feature-implement** - 与 feature-dev 插件协调
4. **feature-complete** - 运行测试、提交、更新状态
5. **progress-recovery** - 分析上下文以恢复会话

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
      "completed": false
    }
  ],
  "current_feature_id": 2
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

## 工作流程示例

```bash
# 1. 开始新项目
/prog init 构建一个具有 CRUD 操作的 TODO 应用

# → 创建功能列表：数据库、API、前端等

# 2. 检查状态
/prog

# → 显示 0/5 已完成

# 3. 开始第一个功能（自动调用 feature-dev）
/prog next

# → feature-dev 指导架构和实现

# 4. 完成并提交
/prog done

# → 运行测试、标记完成、创建 Git 提交

# [会话关闭或重启]

# 5. SessionStart 钩子检测未完成的工作
# → 显示："进度 1/5，使用 /prog 继续"

# 6. 恢复并继续
/prog
/prog next
```

## 与 feature-dev 插件集成

Progress Tracker 将实现委托给官方 **feature-dev** 插件：

| 职责 | 插件 |
|----------------|--------|
| 功能分解 | progress-tracker |
| 进度状态 | progress-tracker |
| 测试执行 | progress-tracker |
| Git 提交 | progress-tracker |
| 代码探索 | feature-dev |
| 架构设计 | feature-dev |
| 实现 | feature-dev |
| 代码审查 | feature-dev |

这种分离确保：
- **质量** - 专业的实现工作流程
- **专注** - 每个插件只做一件事
- **利用** - 重用官方插件的能力

## 目录结构

```
plugins/progress-tracker/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   ├── prog.md
│   ├── prog-init.md
│   ├── prog-next.md
│   └── prog-done.md
├── skills/
│   ├── feature-breakdown/
│   │   └── SKILL.md
│   ├── progress-status/
│   │   └── SKILL.md
│   ├── feature-implement/
│   │   └── SKILL.md
│   ├── feature-complete/
│   │   └── SKILL.md
│   └── progress-recovery/
│       └── SKILL.md
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       └── progress_manager.py
└── README.md
```

## 会话恢复

当您打开新会话时，插件会自动检测未完成的工作：

**SessionStart 钩子**检查：
1. `.claude/progress.json` 是否存在？
2. 是否有未完成的功能？
3. 是否设置了 `current_feature_id`？
4. 是否有未提交的 Git 更改？

如果检测到未完成的工作，将显示：
```
[Progress Tracker] 检测到未完成的项目
项目：用户认证
进度：2/5 已完成
当前功能：登录 API
使用 /prog 查看状态
```

## 设计原则

| 原则 | 实现 |
|-----------|----------------|
| **测试驱动** | 功能仅通过测试后才完成 |
| **Git 原生** | 每个功能都提交，历史即进度 |
| **外部状态** | 进度存储在文件中，经受上下文丢失 |
| **清晰分离** | 命令 → 技能 → 脚本 |
| **专业** | 利用 feature-dev 进行实现 |
| **可恢复** | 带有上下文的会话恢复 |

## 许可证

MIT
