#!/bin/bash
# Rules Manager Package Verification Script
# This script verifies package manager setup and project configuration

CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-/Users/siunin/Projects/Claude-Plugins/plugins/package-manager}"

echo "=== Claude 包管理器规则验证 ==="
echo ""

# 检查插件是否已安装
if [ -d "$CLAUDE_PLUGIN_ROOT" ]; then
    echo "✅ Package Manager 插件已安装"
    echo "   路径: $CLAUDE_PLUGIN_ROOT"

    # 检查技能文件
    if [ -f "$CLAUDE_PLUGIN_ROOT/skills/package-manager/SKILL.md" ]; then
        echo "✅ package-manager 技能已加载"
    else
        echo "⚠️  package-manager 技能文件缺失"
    fi
else
    echo "⚠️  Package Manager 插件未找到"
    echo "   预期路径: $CLAUDE_PLUGIN_ROOT"
fi

echo ""
echo "=== 工具检测 ==="

# 检查 mise
if command -v mise &> /dev/null; then
    echo "✅ mise 已安装"
    echo "当前安装的工具版本："
    mise list 2>/dev/null | head -10 || echo "   (mise list 未返回结果)"

    # 检查项目 mise 配置
    echo ""
    echo "项目 mise 配置："
    if [ -f "$PWD/.mise.toml" ]; then
        echo "✅ .mise.toml 存在"
    elif [ -f "$PWD/.tool-versions" ]; then
        echo "✅ .tool-versions 存在"
    else
        echo "⚠️  项目未配置 mise（使用全局配置）"
    fi
else
    echo "❌ mise 未安装"
    echo "   安装: curl https://mise.run | sh"
fi

# 检查包管理器
echo ""
echo "=== 包管理器检测 ==="

# uv (Python)
if command -v uv &> /dev/null; then
    echo "✅ uv 已安装: $(uv --version 2>/dev/null || echo 'version unknown')"
else
    echo "⚠️  uv 未安装"
    echo "   安装: mise use uv@latest"
fi

# pnpm (Node.js)
if command -v pnpm &> /dev/null; then
    echo "✅ pnpm 已安装: $(pnpm --version 2>/dev/null || echo 'version unknown')"
else
    echo "⚠️  pnpm 未安装"
    echo "   安装: mise use pnpm@latest"
fi

# bun (Node.js)
if command -v bun &> /dev/null; then
    echo "✅ bun 已安装: $(bun --version 2>/dev/null || echo 'version unknown')"
else
    echo "ℹ️  bun 未安装（可选）"
    echo "   安装: mise use bun@latest"
fi

# 检查当前项目类型
echo ""
echo "=== 项目类型检测 ==="
PROJECT_DETECTED=false

if [ -f "pyproject.toml" ]; then
    echo "✅ Python 项目 (pyproject.toml 存在)"
    echo "   推荐命令: uv add <package>"
    PROJECT_DETECTED=true
fi

if [ -f "package.json" ]; then
    echo "✅ Node.js 项目 (package.json 存在)"
    if [ -f "pnpm-lock.yaml" ]; then
        echo "   包管理器: pnpm"
        echo "   推荐命令: pnpm add <package>"
    elif [ -f "bun.lockb" ]; then
        echo "   包管理器: bun"
        echo "   推荐命令: bun add <package>"
    elif [ -f "yarn.lock" ]; then
        echo "   包管理器: yarn"
        echo "   推荐命令: yarn add <package>"
    elif [ -f "package-lock.json" ]; then
        echo "   包管理器: npm"
        echo "   推荐命令: npm install <package>"
    else
        echo "   包管理器: 未检测到锁定文件"
        echo "   推荐使用: pnpm add <package>"
    fi
    PROJECT_DETECTED=true
fi

if [ -f "Gemfile" ]; then
    echo "✅ Ruby 项目 (Gemfile 存在)"
    echo "   推荐命令: bundle add <gem>"
    PROJECT_DETECTED=true
fi

if [ -f "Package.swift" ]; then
    echo "✅ Swift 项目 (Package.swift 存在)"
    echo "   推荐命令: swift package add-dependency"
    PROJECT_DETECTED=true
fi

if [ -f "Cargo.toml" ]; then
    echo "✅ Rust 项目 (Cargo.toml 存在)"
    echo "   推荐命令: cargo add <package>"
    PROJECT_DETECTED=true
fi

if [ -f "go.mod" ]; then
    echo "✅ Go 项目 (go.mod 存在)"
    echo "   推荐命令: go get <package>@version"
    PROJECT_DETECTED=true
fi

if [ "$PROJECT_DETECTED" = false ]; then
    echo "ℹ️  未检测到项目配置文件"
    echo "   提示: 运行此脚本时应在项目根目录"
fi

echo ""
echo "=== 建议操作 ==="
echo "1. 安装 mise（如未安装）: curl https://mise.run | sh"
echo "2. 安装最新稳定版工具: mise use python@latest node@latest pnpm@latest uv@latest"
echo "3. Python 项目初始化: uv init"
echo "4. Node.js 项目初始化: pnpm init"
echo "5. 检查 skill 是否生效: 向 Claude 提问'如何安装 express'"
