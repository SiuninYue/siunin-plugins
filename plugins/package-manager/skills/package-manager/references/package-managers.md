# 包管理器详细参考

## 目录

- [版本策略详解](#版本策略详解)
  - [迁移未被 mise 管理的语言](#迁移未被-mise-管理的语言)
- [各语言完整命令参考](#各语言完整命令参考)
- [环境检测和状态检查](#环境检测和状态检查)
- [故障排除](#故障排除)
- [高级配置](#高级配置)

---

## 版本策略详解

### 为什么使用最新稳定版？

1. **安全性**：自动获得最新安全补丁
2. **兼容性**：支持最新的语言特性和包生态
3. **维护性**：减少版本锁定带来的维护负担

### mise 版本管理

```bash
# 查看已安装的工具
mise list

# 使用最新稳定版
mise use python@latest
mise use node@latest
mise use rust@stable
mise use pnpm@latest
mise use bun@latest
mise use uv@latest
mise use ruby@latest
mise use swift@latest
mise use go@latest

# 或使用别名（推荐）
mise use python
mise use node
mise use rust
mise use pnpm
mise use bun
mise use ruby
mise use swift
mise use go

# 运行工具（使用mise管理的版本）
mise exec python -- --version
mise exec node -- --version
mise exec pnpm -- --version
mise exec bun -- --version
mise exec ruby -- --version
mise exec rustc -- --version
mise exec swift -- --version
mise exec go -- --version

# 临时使用特定版本执行命令
mise x python@3.14 -- python script.py
mise x node@20 -- node server.js
```

### 完整配置示例

在 `.mise.toml` 中配置所有语言使用最新稳定版：

```toml
[tools]
node = "lts"
pnpm = "latest"
python = "latest"
ruby = "latest"
swift = "latest"
rust = "stable"
go = "latest"
java = "latest"
```

在 `~/.config/mise/config.toml` 中配置全局默认值：

```toml
[tools]
node = "lts"
pnpm = "latest"
python = "latest"
ruby = "latest"
swift = "latest"
rust = "stable"
go = "latest"
java = "latest"
```

### 何时使用固定版本？

只在以下情况使用固定版本：
- 项目有明确的兼容性要求
- 某个工具版本存在破坏性变更
- CI/CD 环境需要精确版本控制

### 迁移未被 mise 管理的语言

根据用户实际环境分析，常见的语言管理状态如下：

#### ✅ 已由 mise 管理的语言
1. **Node.js** - 通过 mise 管理，使用 LTS 版本
2. **pnpm** - 通过 mise 管理，使用最新版本
3. **Python** - 通过 mise 管理，使用最新版本
4. **uv** - 通过 mise 管理，使用最新版本

#### 🔄 需要迁移到 mise 管理的语言
1. **Ruby** - 使用系统版本 (`/usr/bin/ruby`)
2. **Swift** - 使用系统版本 (`/usr/bin/swift`)
3. **Rust** - 使用 Homebrew 版本 (`/opt/homebrew/bin/rustc`)
4. **Go** - 未安装或使用系统版本
5. **Java** - 使用系统版本 (`/usr/bin/java`)

#### 迁移步骤

1. **检查当前语言版本**：
```bash
# 检查 Ruby
which ruby
ruby --version

# 检查 Swift
which swift
swift --version

# 检查 Rust
which rustc
rustc --version

# 检查 Go
which go
go version

# 检查 Java
which java
java --version
```

2. **添加到 mise 配置**：
```bash
# 添加语言到 mise 管理
mise use ruby@latest
mise use swift@latest
mise use rust@stable
mise use go@latest
mise use java@latest

# 或编辑 ~/.config/mise/config.toml
[tools]
ruby = "latest"
swift = "latest"
rust = "stable"
go = "latest"
java = "latest"
```

3. **验证迁移结果**：
```bash
# 检查 mise 管理的版本
mise exec ruby -- --version
mise exec swift -- --version
mise exec rustc -- --version
mise exec go -- --version
mise exec java -- --version

# 对比系统版本
which ruby
which swift
which rustc
which go
which java
```

4. **更新 Shell 配置**：
```bash
# 重新加载 shell 配置
source ~/.zshrc  # 或 ~/.bashrc
```

#### 迁移前后对比

| 语言 | 迁移前 | 迁移后 | 优点 |
|------|--------|--------|------|
| Ruby | 系统版本 (`/usr/bin/ruby`) | mise 管理 (`~/.local/share/mise/installs/ruby/latest/bin/ruby`) | 版本隔离，项目独立 |
| Swift | 系统版本 (`/usr/bin/swift`) | mise 管理 (`~/.local/share/mise/installs/swift/latest/bin/swift`) | 支持多版本，最新特性 |
| Rust | Homebrew 版本 (`/opt/homebrew/bin/rustc`) | mise 管理 (`~/.local/share/mise/installs/rust/stable/bin/rustc`) | 统一版本管理，与项目绑定 |
| Go | 系统版本或未安装 | mise 管理 (`~/.local/share/mise/installs/go/latest/bin/go`) | 自动下载，版本控制 |
| Java | 系统版本 (`/usr/bin/java`) | mise 管理 (`~/.local/share/mise/installs/java/latest/bin/java`) | 多版本共存，项目隔离 |

---

## 各语言完整命令参考

### 项目检测和 mise 管理检查

在开始项目开发前，应检查语言是否由 mise 管理：

```bash
# 检查语言是否由 mise 管理
mise list | grep -E "ruby|swift|rust|go|java"

# 如果未被管理，建议迁移
which ruby swift go rustc java
```

#### 项目检测逻辑流程图

1. **检查项目配置文件**（如 pyproject.toml、package.json 等）
2. **检查语言是否由 mise 管理**（使用 mise list 和 which 命令）
3. **如果未被管理**，建议迁移到 mise 管理
4. **如果已管理**，使用正确的包管理器命令

#### 各语言项目检测规则

| 语言 | 配置文件 | 包管理器 | mise 管理检查 |
|------|----------|----------|---------------|
| Python | `pyproject.toml` | `uv` | `mise exec python -- --version` |
| Node.js | `package.json` | `pnpm`/`bun`/`npm`/`yarn` | `mise exec node -- --version` |
| Ruby | `Gemfile` | `bundle` | `mise exec ruby -- --version` |
| Swift | `Package.swift` | `swift package` | `mise exec swift -- --version` |
| Rust | `Cargo.toml` | `cargo` | `mise exec rustc -- --version` |
| Go | `go.mod` | `go modules` | `mise exec go -- --version` |
| Java | `pom.xml`/`build.gradle` | `maven`/`gradle` | `mise exec java -- --version` |

### Python 项目

#### ✅ 正确命令（使用 mise 管理的 uv）

```bash
# 安装包
uv add <package-name>

# 安装特定版本
uv add <package-name>@1.2.3

# 安装开发依赖
uv add --dev <package-name>

# 同步依赖
uv sync

# 运行 Python 脚本
uv run python script.py

# 运行测试
uv run pytest

# 初始化新项目
uv init

# 安装所有依赖
uv pip install -r requirements.txt  # 如果有 requirements.txt
```

#### ❌ 错误命令（应避免）

```bash
pip install <package-name>
python -m pip install <package-name>
system pip install <package-name>
```

#### 项目检测

存在 `pyproject.toml` → Python 项目 → 使用 `uv`

### Node.js 项目

#### ✅ 正确命令（使用 mise 管理的 pnpm/bun）

```bash
# pnpm（推荐）
pnpm add <package-name>
pnpm add -D <package-name>
pnpm install
pnpm run <script-name>
pnpm test

# bun（现代项目）
bun add <package-name>
bun add -d <package-name>
bun install
bun run <script-name>

# npm（已有 package-lock.json 时）
npm install <package-name>
npm install -D <package-name>
npm install
npm run <script-name>

# yarn（已有 yarn.lock 时）
yarn add <package-name>
yarn add -D <package-name>
yarn install
yarn run <script-name>
```

#### ❌ 错误命令（应避免）

```bash
# 不要混用包管理器
npm install       # 当项目使用 pnpm 时
yarn add          # 当项目使用 pnpm 时

# 不要使用旧命令
npm i             # 应使用 npm install 的完整形式
yarn add          # 当项目没有 yarn.lock 时
```

#### 包管理器检测

根据锁定文件选择：
- `pnpm-lock.yaml` → 使用 `pnpm`
- `bun.lock` → 使用 `bun`
- `yarn.lock` → 使用 `yarn`
- `package-lock.json` → 使用 `npm`
- 无锁定文件 → 推荐使用 `pnpm`

### Ruby 项目

#### ✅ 正确命令（使用 Bundler）

```bash
# 安装项目依赖（使用 Gemfile）
bundle install

# 添加 gem 到 Gemfile
bundle add <gem-name>

# 运行命令（使用 bundle 执行）
bundle exec <command>

# 更新依赖
bundle update

# 检查依赖
bundle check

# 查看 Gemfile 中的 gems
bundle list
```

#### ❌ 错误命令（应避免）

```bash
# 除非是全局工具，否则避免直接使用 gem install
gem install <gem-name> --user-install  # ❌（项目依赖应使用 bundle add）

# 避免直接运行 gem 命令而不使用 bundle exec
gem list  # ❌（应使用 bundle exec gem list）
```

#### 项目检测

存在 `Gemfile` → Ruby 项目 → 使用 `bundle`

### Swift 项目

#### ✅ 正确命令（使用 Swift Package Manager）

```bash
# 添加依赖（编辑 Package.swift）
# 使用 Xcode：File > Add Package Dependencies

# 构建项目
swift build

# 运行测试
swift test

# 更新依赖
swift package update

# 重置依赖
swift package reset

# 初始化新包
swift package init --type executable
swift package init --type library
```

#### ❌ 错误命令（应避免）

```bash
# 避免使用 CocoaPods 和 Carthage（除非项目已有）
pod install      # ❌（除非项目已有 Podfile）
carthage update  # ❌（除非项目已有 Cartfile）
```

#### 项目检测

存在 `Package.swift` → Swift 项目 → 使用 `swift package`

### Rust 项目

#### ✅ 正确命令（使用 Cargo）

```bash
# 添加依赖
cargo add <package-name>

# 构建项目
cargo build

# 运行测试
cargo test

# 运行项目
cargo run

# 检查代码
cargo check

# 更新依赖
cargo update

# 初始化新项目
cargo new <project-name>
cargo init --bin
```

#### ❌ 错误命令（应避免）

```bash
# Rust 没有替代包管理器，所有操作都应使用 cargo
# 避免手动管理依赖
# 不要手动编辑 Cargo.toml 的 dependencies 部分
```

#### 项目检测

存在 `Cargo.toml` → Rust 项目 → 使用 `cargo`

### Go 项目

#### ✅ 正确命令（使用 go modules）

```bash
# 初始化模块（如果不存在 go.mod）
go mod init <module-name>

# 添加依赖（会自动更新 go.mod）
go get <package>@<version>

# 整理依赖
go mod tidy

# 运行项目
go run main.go

# 构建项目
go build

# 下载依赖
go mod download

# 验证依赖
go mod verify

# 查看依赖
go mod graph
```

#### ❌ 错误命令（应避免）

```bash
# 避免使用旧的依赖管理方式
# 不要手动编辑 vendor 目录
# 不要使用 glide 或 godep 等已废弃的工具
```

#### 项目检测

存在 `go.mod` → Go 项目 → 使用 `go modules`

---

## 环境检测和状态检查

### 诊断命令

```bash
# 检查所有语言管理状态
mise list
which ruby swift go rustc java

# 检查配置
cat ~/.config/mise/config.toml 2>/dev/null || echo "无全局配置"
cat .mise.toml 2>/dev/null || echo "无项目配置"

# 检查包管理器状态
uv --version 2>/dev/null || echo "uv未安装"
pnpm --version 2>/dev/null || echo "pnpm未安装"
bun --version 2>/dev/null || echo "bun未安装"
```

### 状态检查脚本

创建 `check-env.sh` 脚本：

```bash
#!/bin/bash
# 环境检测脚本

echo "=== 环境检测报告 ==="
echo "生成时间: $(date)"
echo

echo "1. Mise 管理状态:"
mise list

echo -e "\n2. 语言版本检查:"
for lang in ruby swift rustc go java; do
    which $lang 2>/dev/null && $lang --version 2>/dev/null || echo "$lang: 未安装"
done

echo -e "\n3. 包管理器检查:"
for pm in uv pnpm bun; do
    which $pm 2>/dev/null && $pm --version 2>/dev/null || echo "$pm: 未安装"
done

echo -e "\n4. 配置检查:"
[ -f ~/.config/mise/config.toml ] && echo "全局配置: 存在" || echo "全局配置: 不存在"
[ -f .mise.toml ] && echo "项目配置: 存在" || echo "项目配置: 不存在"

echo -e "\n=== 检测完成 ==="
```

#### 检测结果解读

| 状态 | 含义 | 建议操作 |
|------|------|----------|
| ✅ mise 管理 | 语言由 mise 管理 | 继续使用，版本已隔离 |
| ⚠️ 系统版本 | 使用系统默认版本 | 建议迁移到 mise 管理 |
| ❌ 未安装 | 语言未安装 | 使用 `mise use <lang>@latest` 安装 |
| 🔄 混合状态 | 部分语言由 mise 管理 | 统一迁移到 mise 管理 |

### 自动化检测

在项目根目录添加预检脚本：

```bash
#!/bin/bash
# 项目环境预检

# 检测项目类型
if [ -f "pyproject.toml" ]; then
    echo "Python 项目检测到"
    mise exec python -- --version
elif [ -f "package.json" ]; then
    echo "Node.js 项目检测到"
    mise exec node -- --version
elif [ -f "Gemfile" ]; then
    echo "Ruby 项目检测到"
    mise exec ruby -- --version 2>/dev/null || echo "Ruby 未被 mise 管理，建议迁移"
elif [ -f "Package.swift" ]; then
    echo "Swift 项目检测到"
    mise exec swift -- --version 2>/dev/null || echo "Swift 未被 mise 管理，建议迁移"
elif [ -f "Cargo.toml" ]; then
    echo "Rust 项目检测到"
    mise exec rustc -- --version 2>/dev/null || echo "Rust 未被 mise 管理，建议迁移"
elif [ -f "go.mod" ]; then
    echo "Go 项目检测到"
    mise exec go -- --version 2>/dev/null || echo "Go 未被 mise 管理，建议迁移"
else
    echo "未检测到标准项目配置文件"
fi
```

---

## 故障排除

### mise 相关问题

#### mise 命令未找到

```bash
# 确保 mise 已安装并初始化
mise --version

# 重新加载 shell 配置
source ~/.bashrc  # 或 ~/.zshrc

# 确保 mise 在 PATH 中
which mise
```

#### 工具版本未生效

```bash
# 检查当前激活的工具
mise list

# 确保在项目目录中使用
cd /path/to/project
mise use python@latest

# 检查 .mise.toml 配置
cat .mise.toml
```

### uv 相关问题

#### uv 命令未找到

```bash
# 通过 mise 安装 uv
mise use uv@latest

# 或使用官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### 依赖安装失败

```bash
# 清理缓存并重试
uv cache clean
uv sync

# 检查 Python 版本兼容性
uv run python --version
```

### pnpm 相关问题

#### pnpm 命令未找到

```bash
# 通过 mise 安装 pnpm
mise use pnpm@latest

# 或使用 npm 安装
npm install -g pnpm
```

#### 依赖解析错误

```bash
# 清理缓存并重新安装
pnpm store prune
rm -rf node_modules pnpm-lock.yaml
pnpm install
```

### bun 相关问题

#### bun 命令未找到

```bash
# 通过 mise 安装 bun
mise use bun@latest

# 或使用官方安装脚本
curl -fsSL https://bun.sh/install | bash
```

---

## 高级配置

### mise 项目配置

创建 `.mise.toml` 文件：

```toml
[tools]
python = "latest"
node = "latest"
pnpm = "latest"
bun = "latest"
uv = "latest"

[env]
PYTHONPATH = "./src"
NODE_ENV = "development"
```

### uv 工作区配置

```toml
# pyproject.toml
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest", "black", "ruff"]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "ruff>=0.1",
]
```

### pnpm 工作区配置

```json
// pnpm-workspace.yaml
packages:
  - "packages/*"
  - "apps/*"
```

### bun 工作区配置

```json
// bun.lock 自动管理
// 使用 package.json 的 workspaces 字段
{
  "workspaces": [
    "packages/*"
  ]
}
```

---

## 最佳实践总结

1. **优先使用最新稳定版**：除非有明确的兼容性要求
2. **检测项目类型**：根据配置文件选择正确的包管理器
3. **不要混用包管理器**：一个项目使用一个包管理器
4. **使用 mise 管理版本**：保持工具版本的一致性
5. **清理缓存**：遇到问题时先清理缓存
6. **查看锁定文件**：锁定文件决定了使用哪个包管理器
