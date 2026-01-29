# 包管理器详细参考

## 目录

- [版本策略详解](#版本策略详解)
- [各语言完整命令参考](#各语言完整命令参考)
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

### 何时使用固定版本？

只在以下情况使用固定版本：
- 项目有明确的兼容性要求
- 某个工具版本存在破坏性变更
- CI/CD 环境需要精确版本控制

---

## 各语言完整命令参考

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
- `bun.lockb` → 使用 `bun`
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
// bun.lockb 自动管理
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
