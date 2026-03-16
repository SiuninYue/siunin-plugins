---
name: package-manager
description: This skill should be used when the user asks to "install a package", "add a dependency", "set up a project", "configure package manager", "initialize scaffolding", or mentions package installation, dependency management, or project setup. Provides comprehensive guidance for using mise, uv, pnpm, bun, and other modern package managers with latest stable version strategy.
version: 0.3.0
---

# Package Manager Rules

## Purpose

This skill provides standardized package management guidance for Claude Code. It ensures all package installations and project setups use modern, efficient tools (mise, uv, pnpm, bun) configured with latest stable versions.

## ⚠️ CRITICAL: mise First Policy

**ALWAYS check mise before using any other package manager.**

When installing or updating any tool, follow this order:

```bash
# 1. Check if mise supports the tool
mise search <tool-name>

# 2. If mise supports it, install via mise
mise use -g <tool>@latest

# 3. Only use brew/apt if mise doesn't support it
```

### 🎯 mise 优先决策流程（最终版）

```
需要安装工具
      │
      ▼
  是 GUI 应用？
  ─────┬─────
   是 │ 否
      │
      ├─→ brew install --cask xxx
      │
      ▼
  mise search xxx
  ─────┬─────
   有 │ 没有
      │
      ├─→ mise use -g xxx@latest
      │
      ▼
  brew install xxx
```

### 💡 简化记忆：

```
🖥️ GUI 应用     → brew cask
🔧 其他任何工具   → 先查 mise
🚫 mise 没有    → brew 或语言专用管理器
```

### mise vs brew 对照表

| 工具类型 | 首选 | 示例 |
|----------|------|------|
| GUI 应用 | brew cask | Claude Code, VSCode, Docker |
| 语言运行时 | mise | python, node, rust, go, java |
| 包管理器 | mise | pnpm, bun, uv, cargo |
| 开发工具（mise 支持） | mise | terraform, kubectl, deno |
| 开发工具（mise 不支持） | brew | gh, jq, ripgrep, fzf |

### mise 已支持的主要工具

```bash
# 编程语言
mise use -g python@latest    # Python
mise use -g node@lts        # Node.js
mise use -g rust@stable     # Rust
mise use -g go@latest       # Go
mise use -g java@lts        # Java
mise use -g ruby@latest     # Ruby
mise use -g swift@latest    # Swift

# 包管理器
mise use -g pnpm@latest     # pnpm
mise use -g bun@latest      # bun
mise use -g uv@latest       # uv

# 构建工具
mise use -g cmake@latest    # CMake

# 开发工具
mise use -g terraform@latest  # Terraform
mise use -g kubectl@latest    # kubectl
mise use -g deno@latest       # Deno
```

### When to Use brew/apt

Only use brew/apt when:
1. ✅ **GUI 应用程序**
2. ✅ **mise registry 中不存在的工具**
3. ✅ **系统级底层工具/库**

4. ❌ **不要用 brew 安装 mise 已支持的编程语言运行时**
   ```bash
   # ❌ 错误
   brew install python node rust go java

   # ✅ 正确
   mise use -g python@latest node@lts rust@stable go@latest java@lts
   ```

## When to Use

Activate this skill when:
- Installing any package or dependency
- Setting up new projects
- Configuring package managers
- Initializing scaffolding
- Questions about which package manager to use
- **Any time a user wants to install/update anything**

## 🔗 mise 如何代理包管理器

### Shims 工作原理

```bash
# 所有 shim 都指向 mise 二进制
~/.local/share/mise/shims/python  → /opt/homebrew/bin/mise
~/.local/share/mise/shims/cargo   → /opt/homebrew/bin/mise
~/.local/share/mise/shims/uv      → /opt/homebrew/bin/mise
... (97 个 shim 都指向同一个 mise)
```

### 调用链示例

```bash
你运行: uv add requests
   │
   ▼
Shell 在 PATH 中找到 ~/.local/share/mise/shims/uv
   │
   ▼
mise 二进制 (通过调用名称知道是 uv)
   │
   ▼
mise 读取 .mise.toml 配置 (uv = "latest")
   │
   ▼
mise 执行实际的: ~/.local/share/mise/installs/uv/.../uv add requests
```

### mise 代理的包管理器清单

| 包管理器 | 语言 | mise 代理 | 实际位置 |
|---------|------|----------|----------|
| **npm** | Node.js | ✅ | `~/.local/share/mise/installs/node/` |
| **pnpm** | Node.js | ✅ | `~/Library/pnpm/` |
| **bun** | Node.js | ✅ | `~/.local/share/mise/installs/bun/` |
| **pip** | Python | ✅ | `~/.local/share/mise/installs/python/` |
| **cargo** | Rust | ✅ | `~/.cargo/bin/` (rustup 管理) |
| **go** | Go | ✅ | `~/.local/share/mise/installs/go/` |
| **gem** | Ruby | ✅ | `~/.local/share/mise/installs/ruby/` |
| **swift-package** | Swift | ✅ | `~/.local/share/mise/installs/swift/` |

### 使用 mise 执行命令

```bash
# 方式 1: 激活 mise 后直接运行 (推荐)
eval "$(mise activate zsh)"
uv add requests        # 使用 mise 管理的 uv
pnpm add lodash        # 使用 mise 管理的 pnpm

# 方式 2: 一次性执行
mise x -- uv add requests
mise x -- pnpm add lodash

# 方式 3: 运行任务
mise run install-deps
```

## Core Principles

### 1. Use Mise for Version Management

Configure mise to use **latest stable versions**, not fixed versions:

```bash
# ✅ Correct - use latest stable
mise use python@latest
mise use node@latest
mise use pnpm@latest
mise use bun@latest
mise use uv@latest

# ❌ Avoid - fixed versions (unless compatibility requires)
mise use python@3.14.2
```

**Rationale**: Latest versions provide security patches, latest features, and reduce maintenance burden.

### 2. Language-Specific Package Managers

| Language | Package Manager | Command Pattern | mise managed? |
|----------|----------------|-----------------|---------------|
| Python | `uv` | `uv add <package>` | ✅ |
| Node.js | `pnpm` (preferred) / `bun` | `pnpm add <package>` / `bun add <package>` | ✅ |
| Ruby | `bundle` | `bundle add <gem>` | ✅ |
| Swift | `swift package` | Edit `Package.swift` | ✅ |
| Rust | `cargo` | `cargo add <package>` | ✅ (via rustup) |
| Go | `go modules` | `go get <package>@version` | ✅ |

### 3. ⚠️ Rust 特殊处理: mise + rustup

**Rust 在 mise 中的工作方式不同**：

```bash
# mise 声明版本但使用 rustup 在底层安装
mise use -g rust@stable

# Rust 不在 ~/.local/share/mise/installs
# 而是 mise 设置 RUSTUP_TOOLCHAIN 环境变量
# rustup 管理实际安装

# 更新 Rust
rustup update              # 直接更新
mise upgrade rust          # 通过 mise (调用 rustup check)
```

**关键差异：**

| 方面 | 普通工具 | Rust |
|------|---------|------|
| 安装位置 | `~/.local/share/mise/installs/` | `~/.rustup/toolchains/` |
| 管理方式 | mise 直接管理 | mise → rustup (委托) |
| 环境变量 | PATH 修改 | `RUSTUP_TOOLCHAIN` 变量 |
| 更新方法 | `mise upgrade` | `rustup update` 或 `mise upgrade rust` |

**环境变量隔离：**

```bash
# 隔离 mise 的 rustup 与系统-wide
export MISE_RUSTUP_HOME="$HOME/.mise/rustup"
export MISE_CARGO_HOME="$HOME/.mise/cargo"
```

## One-Command Updates

### 更新所有工具

```bash
# 更新所有 mise 管理的工具
mise upgrade

# 更新所有 Homebrew 包
brew upgrade

# 更新 Rust 工具链
rustup update

# 完整更新流程
mise upgrade && brew upgrade && rustup update
```

### 检查哪些需要更新

```bash
# 检查 mise 工具
mise outdated

# 检查 Homebrew
brew outdated

# 检查 Rust
rustup check
```

### 选择性更新

```bash
# 更新特定 mise 工具
mise upgrade rust

# 更新特定 Homebrew 包
brew upgrade python

# 更新特定 Rust 工具链
rustup update stable
```

## Project Type Detection

通过检查根目录文件检测项目类型：

```
pyproject.toml      → Python project  → use uv
package.json        → Node.js project  → check lock file:
  ├─ pnpm-lock.yaml → pnpm
  ├─ bun.lockb      → bun
  ├─ yarn.lock      → yarn
  ├─ package-lock.json → npm
  └─ (none)         → recommend pnpm
Gemfile             → Ruby project   → use bundle
Package.swift       → Swift project  → use swift package
Cargo.toml          → Rust project   → use cargo
go.mod              → Go project     → use go modules
```

## Common Commands Reference

### Python (uv)
```bash
uv add <package>              # Install package
uv add --dev <package>        # Install dev dependency
uv sync                       # Sync dependencies
uv run python script.py       # Run script
uv run pytest                 # Run tests
```

### Node.js (pnpm/bun)
```bash
# pnpm
pnpm add <package>            # Install package
pnpm add -D <package>         # Install dev dependency
pnpm install                  # Install all dependencies
pnpm run <script>             # Run script

# bun
bun add <package>             # Install package
bun add -d <package>          # Install dev dependency
bun install                   # Install all dependencies
bun run <script>              # Run script
```

### Ruby (bundle)
```bash
bundle install                # Install dependencies
bundle add <gem>              # Add gem to Gemfile
bundle exec <command>         # Run command with bundle context
bundle update                 # Update dependencies
```

### Rust (cargo)
```bash
cargo add <crate>             # Add dependency
cargo build                   # Build project
cargo test                    # Run tests
cargo install --force <crate> # Reinstall global tool
```

### Swift
```bash
swift package resolve         # Resolve dependencies
swift build                   # Build project
swift test                    # Run tests
```

## Global Tool Installation

```bash
# Python tools via uv
uv tool install <package>

# Node.js tools via pnpm
pnpm add -g <package>

# Ruby tools via gem
gem install <gem-name>

# Rust tools via cargo
cargo install <crate-name>

# Go tools via go install
go install <package>@latest
```

## mise Activation: PATH vs Shims

### 推荐: PATH 修改（交互式使用）

```bash
# ~/.zshrc or ~/.bashrc
eval "$(mise activate zsh)"
```

**优点：**
- 完整功能支持
- 环境变量立即可用
- 更适合交互式 shell

### 替代方案: Shims（IDE/脚本/CI）

```bash
# ~/.zshrc or ~/.bashrc
eval "$(mise activate zsh --shims)"
```

**优点：**
- 更适合 IDE 集成
- 对脚本更可预测
- 更轻量

**缺点：**
- 某些功能受限
- 环境变量只在 shim 执行时加载

### 目录结构

```
~/.local/share/mise/
├── installs/          # 实际工具安装（Rust 除外）
│   ├── python/
│   ├── node/
│   └── ...
└── shims/             # 符号链接包装器（97 个）
    ├── python
    ├── node
    ├── uv
    ├── cargo          # 指向 rustup
    └── ...            # 都指向同一个 mise 二进制
```

## Workflow

1. **检查 mise 是否支持** - `mise search <tool>`
2. **检测项目类型** - 检查根目录的配置文件
3. **检查 mise 配置** - 验证工具版本
4. **选择合适的包管理器** - 基于项目类型
5. **使用正确的命令模式** - 遵循语言特定模式
6. **推荐 mise use latest** - 如果使用过时工具

## Installation Checklist

安装任何东西之前，问自己：

- [ ] 这个工具在 mise 中可用吗？(`mise search <tool>`)
- [ ] 应该是项目依赖还是全局工具？
- [ ] 这个语言/运行时适合的包管理器是什么？
- [ ] 最新稳定版本是否合适，还是需要特定版本？

## Additional Resources

### Scripts

- **`$CLAUDE_PLUGIN_ROOT/scripts/verify-rules.sh`** - Verify package manager setup and detect project type

### References

- **`references/package-managers.md`** - Detailed package manager documentation with examples and troubleshooting

### mise Documentation

- [mise Official Docs](https://mise.jdx.dev)
- [mise Rust Guide](https://mise.jdx.dev/lang/rust.html)
- [mise Shims vs PATH](https://mise.jdx.dev/dev-tools/shims.html)
- [mise Exec Command](https://mise.jdx.dev/cli/exec.html)
