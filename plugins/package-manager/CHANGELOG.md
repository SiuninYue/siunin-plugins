# Changelog

All notable changes to the Package Manager plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-03-20

### Fixed
- **Critical update command fixes**:
  - 移除不必要的 `pnpm self-update`（mise 已管理）
  - 移除不必要的 `uv self update`（mise 已管理）
  - 修正 `mise exec` 语法：`mise exec -uv --` → `mise exec uv --`
  - 修复 `update-project` 函数，添加 `mise exec` 调用确保非交互式环境可用
  - 修正注释错误：`npm -g outdated` 是自带功能，无需额外安装
- **Global package management clarity**:
  - 添加 npm vs pnpm 全局包冲突警告
  - 简化一键更新命令，移除 `npm update -g`（避免与 pnpm 冲突）
  - 快捷脚本中保留 `npm update -g` 作为兼容性选项
- Updated command reference table to clarify self-update is handled by mise
- Simplified update scripts - mise already manages pnpm/uv/bun versions
- Ensured all commands use correct `mise exec` syntax for non-interactive shells

## [1.0.0] - 2026-03-17

### Added
- One-command update scripts (`update-all`, `update-global`, `update-project`)
- Comprehensive update strategy with clear layer diagram
- Global package update commands for all supported languages
- Project dependency update commands
- Unified language command reference tables
- mise upgrade limitation warning

### Changed
- **Complete skill restructuring** for better organization
- Replaced text-heavy sections with concise tables
- Simplified mise proxy mechanism explanation
- Consolidated duplicate content (reduced from ~770 to ~350 lines)

### Fixed
- Clarified Rust special handling with mise vs rustup
- Corrected PATH vs Shims activation comparison

## [0.1.0] - 2026-01-29

### Added
- Initial release of Package Manager plugin
- `package-manager` skill with comprehensive package management guidance
- `rules-reviewer` skill for reviewing rules and instructions
- `verify-rules.sh` script for validating package manager setup
- Support for modern package managers: mise, uv, pnpm, bun
- Language-specific package manager recommendations:
  - Python: uv
  - Node.js: pnpm (recommended) or bun
  - Ruby: bundle
  - Swift: swift package
  - Rust: cargo
  - Go: go modules
- Project type detection based on configuration files
- Latest stable version strategy
- Mise integration for tool version management
- Complete documentation in Chinese and English references