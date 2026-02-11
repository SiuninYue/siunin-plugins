# Package Manager Plugin

包管理器规则和最佳实践插件。提供 mise、uv、pnpm、bun 等现代包管理器的标准化指导和自动化配置。

## 功能

- **标准化包管理规则**：为不同语言项目提供一致的包管理指导
- **现代工具推荐**：优先使用 mise、uv、pnpm、bun 等现代工具
- **项目类型自动检测**：根据项目配置文件智能推荐包管理器
- **最新稳定版策略**：推荐使用最新稳定版本，减少维护负担
- **验证脚本**：提供自动化验证脚本检查项目配置

## 安装

```bash
/plugin install package-manager@siunin-plugins
```

## 使用方法

### 自动激活技能

当用户提及以下内容时，技能会自动激活：
- "install a package" 或 "安装包"
- "add a dependency" 或 "添加依赖"
- "set up a project" 或 "设置项目"
- "configure package manager" 或 "配置包管理器"
- "initialize scaffolding" 或 "初始化项目脚手架"

### 核心原则

1. **使用 Mise 管理版本**：所有工具版本通过 mise 管理
2. **优先使用最新稳定版**：除非有明确兼容性要求
3. **语言专用包管理器**：
   - Python → uv
   - Node.js → pnpm（推荐）或 bun
   - Ruby → bundle
   - Swift → swift package
   - Rust → cargo
   - Go → go modules

### 项目类型检测

插件会根据项目根目录的配置文件自动检测项目类型：

- `pyproject.toml` → Python 项目 → 使用 `uv`
- `package.json` → Node.js 项目 → 根据锁定文件选择包管理器
- `Gemfile` → Ruby 项目 → 使用 `bundle`
- `Package.swift` → Swift 项目 → 使用 `swift package`
- `Cargo.toml` → Rust 项目 → 使用 `cargo`
- `go.mod` → Go 项目 → 使用 `go modules`

## 技能

### 1. package-manager
**触发条件**：安装包、添加依赖、项目设置、包管理器配置

提供全面的包管理指导，包括：
- 项目类型检测
- 包管理器推荐
- 正确命令格式
- 版本管理策略

### 2. rules-reviewer
**触发条件**：审查规则、检查提示质量、验证指令、审计系统提示

用于审查和验证 Claude Code 规则、提示和指令的质量。

### 3. codex-plugin-sync
**触发条件**：同步 Codex skill、迁移 Claude plugin 资源、刷新迁移后的 skills/commands/agents、修复 `${CLAUDE_PLUGIN_ROOT}` 兼容性

用于将插件资源同步到 `~/.codex/skills` 并做 Codex 兼容转换：
- `skills/*/SKILL.md` 仅保留 `name` 和 `description`
- `commands/*.md` 与 `agents/*.md` 清理 `model`/`madel`
- `${CLAUDE_PLUGIN_ROOT}` 可改写为 Codex 可执行路径

## 脚本

### verify-rules.sh
验证包管理器设置和项目配置的脚本。

```bash
# 运行验证脚本
bash $CLAUDE_PLUGIN_ROOT/scripts/verify-rules.sh
```

功能包括：
- 检查插件安装状态
- 检测系统工具安装情况
- 分析项目类型和配置
- 提供建议操作

### publish-codex-plugin-sync.sh
将仓库中的 `codex-plugin-sync` 技能发布到 `~/.codex/skills/codex-plugin-sync`。

```bash
bash /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/scripts/publish-codex-plugin-sync.sh
```

## Codex 同步流程（新增）

### 1) 发布技能到 Codex

```bash
bash /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/scripts/publish-codex-plugin-sync.sh
```

### 2) 执行干跑（推荐）

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins progress-tracker,package-manager,super-product-manager \
  --source-policy workspace-first \
  --extra-dirs auto \
  --placeholder-mode rewrite \
  --dry-run \
  --report /tmp/codex-sync-report.json
```

### 3) 正式同步

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins all \
  --source-policy workspace-first \
  --extra-dirs auto \
  --placeholder-mode rewrite
```

默认行为：
- `workspace-first`：优先读工作区插件目录，不存在时回退 manifest source
- `extra-dirs=auto`：检测到 `${CLAUDE_PLUGIN_ROOT}` 时按需补迁 `hooks/`、`scripts/`
- `placeholder-mode=rewrite`：改写为 `${CODEX_HOME:-$HOME/.codex}/skills/<wrapper_name>`

## 文件结构

```
package-manager/
├── .claude-plugin/
│   └── plugin.json          # 插件配置
├── skills/
│   ├── codex-plugin-sync/
│   │   ├── SKILL.md         # Codex 迁移/同步技能
│   │   ├── agents/
│   │   │   └── openai.yaml
│   │   ├── references/
│   │   │   └── migration-rules.md
│   │   └── scripts/
│   │       └── sync_codex_imports.py
│   ├── package-manager/
│   │   ├── SKILL.md         # 包管理器技能
│   │   └── references/
│   │       └── package-managers.md  # 详细参考文档
│   └── rules-reviewer/
│       └── SKILL.md         # 规则审查技能
├── scripts/
│   ├── verify-rules.sh      # 验证脚本
│   └── publish-codex-plugin-sync.sh # 发布 codex-plugin-sync 到 ~/.codex/skills
├── README.md                # 本文档
└── LICENSE                  # MIT 许可证
```

## 依赖项

- **mise**：推荐用于版本管理（但不是必需）
- 各语言包管理器（uv、pnpm、bun、cargo 等）

## 许可证

MIT

## 作者

siunin

## 版本历史

- v0.1.0 (2026-01-29): 初始版本发布
