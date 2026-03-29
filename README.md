# Claude Plugins

siunin的Claude插件集合仓库。

## 插件列表

### 1. 超级产品经理 (super-product-manager)
- **版本**: 1.3.0
- **描述**: 全能产品经理插件 - 为超级个体/一人企业设计，帮助从想法到产品的全流程管理
- **类别**: 生产力 (productivity)
- **功能**: 14个命令、8个专业Agent、16个专业技能

### 2. 进度追踪器 (progress-tracker)
- **版本**: 1.6.12
- **描述**: 跟踪长时间运行的 AI Agent 任务，支持基于功能的进度追踪、测试驱动状态更新和 Git 集成
- **类别**: 生产力 (productivity)
- **功能**: 4个命令、5个专业技能、会话恢复机制、Web 仪表板
- **依赖**: feature-dev 官方插件

### 3. 笔记整理器 (note-organizer)
- **版本**: 1.3.0
- **描述**: 智能笔记整理插件 - 将 AI 提取的笔记转换为结构化知识库内容，支持 NotebookLM 和 Obsidian 双平台
- **类别**: 生产力 (productivity)
- **功能**: 3个命令、2个技能、时间戳清理、内容增强、双模板支持

### 4. 包管理器 (package-manager)
- **版本**: 0.3.0
- **描述**: 包管理器规则和最佳实践插件 - 提供 mise、uv、pnpm、bun 等现代包管理器的标准化指导和自动化配置
- **类别**: 生产力 (productivity)
- **功能**: 4个技能（mise、uv、pnpm、bun）、mise 代理说明、自动化更新脚本

## 安装

### 方法1：从GitHub安装（推荐）
```bash
# 添加市场
/plugin marketplace add https://github.com/SiuninYue/siunin-plugins.git

# 安装超级产品经理插件
/plugin install super-product-manager@siunin-plugins

# 安装进度追踪器插件（需要先安装 feature-dev 依赖）
/plugin install feature-dev@claude-plugins-official
/plugin install progress-tracker@siunin-plugins

# 安装笔记整理器插件
/plugin install note-organizer@siunin-plugins

# 安装包管理器插件
/plugin install package-manager@siunin-plugins
```

### 方法2：本地开发安装
```bash
# 添加本地市场（直接使用本仓库根目录）
/plugin marketplace add /Users/siunin/Projects/Claude-Plugins

# 安装插件
/plugin install super-product-manager@siunin-plugins
/plugin install progress-tracker@siunin-plugins
/plugin install note-organizer@siunin-plugins
/plugin install package-manager@siunin-plugins
```

## 项目结构

```
claude-plugins/                    # 插件市场根目录
├── .claude-plugin/                # 市场配置目录
│   └── marketplace.json           # 市场配置文件（名称：siunin-plugins）
├── plugins/                       # 所有插件目录
│   ├── super-product-manager/     # 超级产品经理插件
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json       # 插件配置
│   │   ├── commands/             # 14个命令
│   │   ├── skills/               # 16个专业技能
│   │   ├── agents/               # 8个专业Agent
│   │   ├── README.md             # 插件文档
│   │   ├── CHANGELOG.md          # 变更日志
│   │   └── LICENSE               # MIT许可证
│   └── progress-tracker/         # 进度追踪器插件
│       ├── .claude-plugin/
│       │   └── plugin.json       # 插件配置
│       ├── commands/             # 4个命令
│       ├── skills/               # 5个专业技能
│       ├── hooks/                # 会话恢复钩子
│       │   └── scripts/          # Python状态管理脚本
│       ├── README.md             # 插件文档
│       └── LICENSE               # MIT许可证
│   ├── note-organizer/           # 笔记整理器插件
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json       # 插件配置
│   │   ├── commands/             # 3个命令
│   │   ├── skills/               # 2个技能
│   │   ├── scripts/              # Python处理脚本
│   │   ├── templates/            # NotebookLM/Obsidian模板
│   │   ├── tests/                # 单元测试
│   │   ├── README.md             # 插件文档
│   │   └── LICENSE               # MIT许可证
│   └── package-manager/          # 包管理器插件
│       ├── .claude-plugin/
│       │   └── plugin.json       # 插件配置
│       ├── skills/               # 4个技能
│       ├── scripts/              # 更新脚本
│       ├── README.md             # 插件文档
│       ├── CHANGELOG.md          # 变更日志
│       └── LICENSE               # MIT许可证
├── README.md                      # 项目说明（本文件）
└── .gitignore                     # Git忽略文件
```

## 添加新插件

要在本仓库中添加新插件：

1. 在 `plugins/` 目录下创建新插件目录
2. 确保插件包含正确的 `.claude-plugin/plugin.json` 配置
3. 在根目录 `.claude-plugin/marketplace.json` 的 `plugins` 数组中添加新条目
4. 更新版本和配置信息
5. 提交并推送到GitHub

## 更新现有插件

1. 修改对应插件目录中的代码
2. 如果需要，更新 `.claude-plugin/marketplace.json` 中的版本号
3. 提交并推送到GitHub

## 用户安装体验

用户只需执行一次市场添加命令：
```bash
/plugin marketplace add https://github.com/SiuninYue/siunin-plugins.git
```

之后可以通过以下命令安装任何插件：
```bash
/plugin install <plugin-name>@siunin-plugins
```

## 许可证

本仓库中的插件遵循各自的许可证（通常是MIT许可证）。

## 维护者

- siunin