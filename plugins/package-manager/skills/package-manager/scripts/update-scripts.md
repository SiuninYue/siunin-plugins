# 更新脚本（Update Scripts）

将以下函数添加到 `~/.zshrc` 或 `~/.bashrc`：

```bash
# === 并发更新所有内容（工具 + 全局包 + 项目依赖）===
# 用法: update-all [--skip-brew] [--skip-mise] [--skip-rust] [--skip-project]
update-all() {
    local skip_mise=false skip_brew=false skip_rust=false skip_project=false

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-brew) skip_brew=true ;;
            --skip-mise) skip_mise=true ;;
            --skip-rust) skip_rust=true ;;
            --skip-project) skip_project=true ;;
            *) echo "❌ 未知参数: $1"; return 1 ;;
        esac
        shift
    done

    echo "🚀 开始并发更新所有包管理器..."
    echo "======================================"

    # 并发更新全局工具
    if ! $skip_mise; then
        echo "🔧 mise 工具更新中..."
        mise upgrade &
    fi

    if ! $skip_brew && command -v brew &>/dev/null; then
        echo "📦 Homebrew 更新中..."
        brew upgrade &>/dev/null &
    fi

    if ! $skip_rust && command -v rustup &>/dev/null; then
        echo "⚙️  Rust 更新中..."
        rustup update &
    fi

    # 等待所有后台任务完成
    wait

    # Homebrew 清理（需要顺序执行）
    if ! $skip_brew && command -v brew &>/dev/null; then
        echo "🧹 清理 Homebrew 缓存..."
        brew cleanup &>/dev/null
    fi

    # 更新全局包
    echo "🌐 更新全局包..."
    mise exec uv -- uv tool upgrade --all 2>/dev/null || true
    mise exec pnpm -- pnpm update -g 2>/dev/null || true
    npm update -g 2>/dev/null || true

    # 更新 Claude Code（使用 latest 通道）
    if ! $skip_brew && command -v brew &>/dev/null; then
        echo "🤖 更新 Claude Code (latest 通道)..."
        brew upgrade --cask claude-code@latest --greedy &>/dev/null || true
    fi

    # 更新项目依赖
    if ! $skip_project; then
        echo "📂 更新项目依赖..."
        [ -f "Cargo.toml" ] && cargo update &>/dev/null
        [ -f "Package.swift" ] && swift package update &>/dev/null
        [ -f "pyproject.toml" ] && mise exec uv -- uv sync --upgrade &>/dev/null
        if [ -f "package.json" ]; then
            [ -f "pnpm-lock.yaml" ] && mise exec pnpm -- pnpm update &>/dev/null
            [ -f "bun.lock" ] && mise exec bun -- bun update &>/dev/null
            [ ! -f "pnpm-lock.yaml" ] && [ ! -f "bun.lock" ] && npm update &>/dev/null
        fi
        [ -f "Gemfile" ] && bundle update &>/dev/null
        [ -f "go.mod" ] && go get -u ./... &>/dev/null && go mod tidy &>/dev/null
    fi

    echo "======================================"
    echo "✅ 检查过时项..."
    mise outdated 2>/dev/null || true
    command -v brew &>/dev/null && brew outdated 2>/dev/null || true
    echo "🎉 全部更新完成！"
}

# === 仅更新全局工具 ===
# 用法: update-global [--skip-brew] [--skip-mise] [--skip-rust]
update-global() {
    local skip_mise=false skip_brew=false skip_rust=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-brew) skip_brew=true ;;
            --skip-mise) skip_mise=true ;;
            --skip-rust) skip_rust=true ;;
            *) echo "❌ 未知参数: $1"; return 1 ;;
        esac
        shift
    done

    echo "🚀 开始并发更新全局工具..."

    if ! $skip_mise; then mise upgrade &; fi
    if ! $skip_brew && command -v brew &>/dev/null; then brew upgrade &>/dev/null &; fi
    if ! $skip_rust && command -v rustup &>/dev/null; then rustup update &; fi

    wait

    if ! $skip_brew && command -v brew &>/dev/null; then
        brew cleanup &>/dev/null
    fi

    echo "📦 更新全局包..."
    mise exec uv -- uv tool upgrade --all 2>/dev/null || true
    mise exec pnpm -- pnpm update -g 2>/dev/null || true
    npm update -g 2>/dev/null || true

    # 更新 Claude Code（使用 latest 通道）
    if ! $skip_brew && command -v brew &>/dev/null; then
        echo "🤖 更新 Claude Code (latest 通道)..."
        brew upgrade --cask claude-code@latest --greedy &>/dev/null || true
    fi

    echo "✅ 全局更新完成！"
}

# 仅更新当前项目
update-project() {
    if [ -f "Cargo.toml" ]; then cargo update
    elif [ -f "Package.swift" ]; then swift package update
    elif [ -f "pyproject.toml" ]; then mise exec uv -- uv sync --upgrade
    elif [ -f "package.json" ]; then
        [ -f "pnpm-lock.yaml" ] && mise exec pnpm -- pnpm update
        [ -f "bun.lock" ] && mise exec bun -- bun update
        [ ! -f "pnpm-lock.yaml" ] && [ ! -f "bun.lock" ] && npm update
    elif [ -f "Gemfile" ]; then bundle update
    elif [ -f "go.mod" ]; then go get -u ./... && go mod tidy
    else echo "❓ 未检测到支持的项目类型"; fi
}
```

## 使用方法

```bash
update-all      # 更新所有内容
update-global   # 仅更新全局工具
update-project  # 仅更新当前项目
```
