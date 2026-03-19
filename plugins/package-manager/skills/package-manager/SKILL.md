---
name: package-manager
description: Use for ANY package installation (mise/brew/npm/pip/cargo/etc), dependency management, or project setup. Covers: installing packages, adding dependencies, setting up projects, configuring package managers, initializing scaffolding, updating packages.
version: 1.0.0
---

# Package Manager Rules

## Purpose

提供标准化包管理指导，确保所有包安装和项目设置使用现代、高效的工具（mise、uv、pnpm、bun），配置为最新稳定版本。

---

## ⚠️ CRITICAL: mise First Policy

**ALWAYS check mise before using any other package manager.**

### 决策流程

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

### mise vs brew 对照表

| 工具类型 | 首选 | 示例 |
|----------|------|------|
| GUI 应用 | brew cask | Claude Code, VSCode, Docker |
| 语言运行时 | mise | python, node, rust, go, java, swift, ruby |
| 包管理器 | mise | pnpm, bun, uv, cargo |
| 开发工具（mise 支持） | mise | terraform, kubectl, deno, cmake |
| 开发工具（mise 不支持） | brew | gh, jq, ripgrep, fzf |

### mise 支持的主要工具

```bash
# 编程语言
mise use -g python@latest    mise use -g node@lts
mise use -g rust@stable      mise use -g go@latest
mise use -g java@lts         mise use -g ruby@latest
mise use -g swift@latest

# 包管理器 & 构建工具
mise use -g pnpm@latest      mise use -g bun@latest
mise use -g uv@latest        mise use -g cmake@latest

# 开发工具
mise use -g terraform@latest mise use -g kubectl@latest
mise use -g deno@latest
```

---

## mise 代理机制

### Shims 工作原理

所有 shim 都指向 mise 二进制，mise 根据调用名称路由到正确版本：

```bash
~/.local/share/mise/shims/python  → /opt/homebrew/bin/mise
~/.local/share/mise/shims/cargo   → /opt/homebrew/bin/mise
~/.local/share/mise/shims/uv      → /opt/homebrew/bin/mise
```

### 调用链

```
你运行: uv add requests
   ↓
Shell 找到 ~/.local/share/mise/shims/uv
   ↓
mise 读取配置 (uv = "latest")
   ↓
mise 执行实际的 uv add requests
```

### Rust 特殊处理

Rust 通过 **rustup** 管理，mise 只设置环境变量：

| 方面 | 普通工具 | Rust |
|------|---------|------|
| 安装位置 | `~/.local/share/mise/installs/` | `~/.rustup/toolchains/` |
| 管理方式 | mise 直接管理 | mise → rustup (委托) |
| 环境变量 | PATH 修改 | `RUSTUP_TOOLCHAIN` 变量 |
| 更新方法 | `mise upgrade` | `rustup update` |

```bash
# 更新 Rust
rustup update              # 直接更新
mise upgrade rust          # 通过 mise
```

---

## 项目类型检测

通过检查根目录文件自动检测项目类型：

```
pyproject.toml      → Python  → uv
package.json        → Node.js → 检查 lock 文件
  ├─ pnpm-lock.yaml → pnpm
  ├─ bun.lockb      → bun
  ├─ yarn.lock      → yarn
  ├─ package-lock.json → npm
  └─ (none)         → 推荐 pnpm
Gemfile             → Ruby   → bundle
Package.swift       → Swift  → swift package
Cargo.toml          → Rust   → cargo
go.mod              → Go     → go modules
```

---

## 更新策略

### 🚀 完整一键更新（macOS）

```bash
# 更新所有工具（推荐按顺序执行）
mise upgrade && brew upgrade && brew cleanup && rustup update && npm update -g && pnpm add -g pnpm && uv self update
```

### 🐧 完整一键更新（Linux）

```bash
# 更新所有工具（推荐按顺序执行）
mise upgrade && sudo apt update && sudo apt upgrade && rustup update && npm update -g && pnpm add -g pnpm && uv self update
```

### 分项更新说明

```bash
# ===== 版本管理器 =====
mise upgrade              # 更新所有 mise 管理的工具

# ===== 系统包管理器 =====
brew upgrade              # macOS: 更新所有 Homebrew 包
brew cleanup              # macOS: 清理旧版本缓存
sudo apt update && sudo apt upgrade  # Linux: 更新所有 apt 包
sudo softwareupdate -i -a  # macOS: 更新系统

# ===== 语言运行时/工具链 =====
rustup update             # Rust: 更新所有已安装的工具链

# ===== 全局包管理器 =====
npm update -g             # Node.js: 更新全局 npm 包
pnpm add -g pnpm          # 更新 pnpm 自身
bun upgrade               # 更新 bun 自身
uv self update            # Python: 更新 uv 自身
gem update --system       # Ruby: 更新 gem 自身
go install golang.org/x/tools/gopls@latest  # Go: 示例更新工具

# ===== Docker 清理 =====
docker system prune -af --volumes  # 清理未使用的镜像、容器、卷
```

### 检查哪些需要更新

```bash
# 检查 mise 工具
mise outdated

# 检查 Homebrew
brew outdated

# 检查 Rust
rustup check

# 检查 npm 全局包（需 npm-check-updates）
npm -g outdated

# 检查 apt（Linux）
apt list --upgradable
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

---

## 语言命令速查

### Python (uv)

| 操作 | 命令 |
|------|------|
| 安装依赖 | `uv add <package>` / `uv add --dev <package>` |
| 同步依赖 | `uv sync` / `uv sync --upgrade` |
| 运行脚本 | `uv run python script.py` / `uv run pytest` |
| 全局工具 | `uv tool install <package>` / `uv tool list` / `uv tool upgrade --all` |

### Node.js (pnpm/bun)

| 操作 | pnpm | bun |
|------|------|-----|
| 安装依赖 | `pnpm add <package>` | `bun add <package>` |
| 开发依赖 | `pnpm add -D <package>` | `bun add -d <package>` |
| 安装全部 | `pnpm install` | `bun install` |
| 运行脚本 | `pnpm run <script>` | `bun run <script>` |
| 更新依赖 | `pnpm update` / `pnpm update --latest` | `bun update` |
| 全局工具 | `pnpm add -g <package>` / `pnpm update -g` | `bun add -g <package>` |

### Rust (cargo)

| 操作 | 命令 |
|------|------|
| 添加依赖 | `cargo add <crate>` |
| 构建/测试 | `cargo build` / `cargo test` |
| 更新依赖 | `cargo update` / `cargo update -p <package>` |
| 全局工具 | `cargo install <crate>` / `cargo install --force <crate>` |

### Swift

| 操作 | 命令 |
|------|------|
| 解析依赖 | `swift package resolve` |
| 构建/测试 | `swift build` / `swift test` |
| 更新依赖 | `swift package update` |

### Ruby (bundle)

| 操作 | 命令 |
|------|------|
| 安装依赖 | `bundle install` |
| 添加 gem | `bundle add <gem>` |
| 更新依赖 | `bundle update` / `bundle update --conservative <gem>` |

### Go

| 操作 | 命令 |
|------|------|
| 添加依赖 | `go get <package>@version` |
| 更新全部 | `go get -u ./...` |
| 整理依赖 | `go mod tidy` |

---

## 统一更新策略

### 更新层级

```
┌─────────────────────────────────────────┐
│           全部更新 (update-all)          │
├─────────────────┬───────────────────────┤
│   全局工具      │     项目依赖           │
│  (update-global)│  (update-project)     │
├─────────────────┴───────────────────────┤
│ mise → brew → rustup → 全局包 → 项目    │
└─────────────────────────────────────────┘
```

### ⚠️ 重要提醒

`mise upgrade` **只更新工具版本**，不更新：
- ❌ 项目依赖（Cargo.lock、package.json）
- ❌ 全局包（npm -g、uv tool、cargo install）

```bash
mise upgrade
# ✅ python 3.14.0 → 3.14.3
# ✅ node 24.0.0 → 24.14.0
# ❌ 不更新 pnpm 全局包
# ❌ 不更新项目依赖
```

---

## 快捷脚本

将以下函数添加到 `~/.zshrc` 或 `~/.bashrc`：

```bash
# 更新所有内容（工具 + 全局包 + 项目依赖）
update-all() {
    echo "🔧 Step 1: mise 工具..."
    mise upgrade

    echo "📦 Step 2: Homebrew..."
    brew upgrade && brew cleanup

    echo "⚙️  Step 3: Rust..."
    rustup update

    echo "🌐 Step 4: 全局包..."
    uv tool upgrade --all 2>/dev/null || true
    pnpm update -g 2>/dev/null || true

    echo "📂 Step 5: 项目依赖..."
    [ -f "Cargo.toml" ] && cargo update
    [ -f "Package.swift" ] && swift package update
    [ -f "pyproject.toml" ] && uv sync --upgrade
    if [ -f "package.json" ]; then
        [ -f "pnpm-lock.yaml" ] && pnpm update
        [ -f "bun.lockb" ] && bun update
        [ ! -f "pnpm-lock.yaml" ] && [ ! -f "bun.lockb" ] && npm update
    fi
    [ -f "Gemfile" ] && bundle update
    [ -f "go.mod" ] && go get -u ./... && go mod tidy

    echo "✅ 检查过时项..."
    mise outdated
    brew outdated
    echo "🎉 完成！"
}

# 仅更新全局工具
update-global() {
    mise upgrade
    brew upgrade && brew cleanup
    rustup update
    uv tool upgrade --all
    pnpm update -g
    echo "✅ 全局更新完成！"
}

# 仅更新当前项目
update-project() {
    if [ -f "Cargo.toml" ]; then cargo update
    elif [ -f "Package.swift" ]; then swift package update
    elif [ -f "pyproject.toml" ]; then uv sync --upgrade
    elif [ -f "package.json" ]; then
        [ -f "pnpm-lock.yaml" ] && pnpm update
        [ -f "bun.lockb" ] && bun update
        [ ! -f "pnpm-lock.yaml" ] && [ ! -f "bun.lockb" ] && npm update
    elif [ -f "Gemfile" ]; then bundle update
    elif [ -f "go.mod" ]; then go get -u ./... && go mod tidy
    else echo "❓ 未检测到支持的项目类型"; fi
}
```

### 使用方法

```bash
update-all      # 更新所有内容
update-global   # 仅更新全局工具
update-project  # 仅更新当前项目
```

---

## 工作流程

```
1. 检查 mise 支持 → mise search <tool>
2. 检测项目类型 → 查看根目录配置文件
3. 检查工具版本 → mise ls / mise outdated
4. 选择包管理器 → 基于项目类型
5. 执行命令 → 遵循语言特定模式
```

---

## 安装检查清单

安装任何东西之前：

- [ ] mise 是否支持？(`mise search <tool>`)
- [ ] 项目依赖还是全局工具？
- [ ] 对应语言的包管理器是什么？
- [ ] 最新稳定版还是特定版本？

---

## 激活 mise

### 推荐: PATH 修改

```bash
# ~/.zshrc or ~/.bashrc
eval "$(mise activate zsh)"
```

### 替代: Shims

```bash
# ~/.zshrc or ~/.bashrc
eval "$(mise activate zsh --shims)"
```

| 方式 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| PATH | 交互式 shell | 完整功能、环境变量立即可用 | 较重 |
| Shims | IDE/脚本/CI | 轻量、可预测 | 某些功能受限 |

---

## 参考资料

### Scripts

- `$CLAUDE_PLUGIN_ROOT/scripts/verify-rules.sh` - 验证包管理器设置

### Documentation

- [mise Official Docs](https://mise.jdx.dev)
- [mise Rust Guide](https://mise.jdx.dev/lang/rust.html)
- [mise Shims vs PATH](https://mise.jdx.dev/dev-tools/shims.html)
