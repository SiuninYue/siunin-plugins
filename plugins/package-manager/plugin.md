# Package Manager Plugin

> Standardized package management guidance with modern tools like mise, uv, pnpm, and bun.

## Description

The Package Manager plugin provides consistent, modern package management guidance for Claude Code. It ensures all package installations and project setups use efficient, up-to-date tools configured with latest stable version strategy.

**Key features:**
- **Modern tool recommendations** - Prefer mise, uv, pnpm, bun over legacy tools
- **Latest stable versions** - Automatic security updates and feature access
- **Project type detection** - Smart recommendations based on config files
- **Consistent commands** - Language-specific best practices
- **Validation script** - Automated setup verification

## Installation

```bash
/plugin install package-manager@siunin-plugins
```

**Dependencies**: Recommended but not required: mise for tool version management.

## Quick Start

```bash
# Check your current setup
bash $CLAUDE_PLUGIN_ROOT/scripts/verify-rules.sh

# When Claude asks about package installation, it will automatically
# provide appropriate commands for your project type
```

## Skills

### package-manager
**Activation**: When user mentions "install a package", "add a dependency", "set up a project", "configure package manager", or "initialize scaffolding"

Provides comprehensive package management guidance including:
- Project type detection
- Package manager selection
- Correct command patterns
- Version management strategy

### rules-reviewer
**Activation**: When user asks to "review rules", "check prompt quality", "validate instructions", or "audit system prompts"

Reviews Claude Code rules, prompts, and instructions for quality and effectiveness.

## Supported Languages & Tools

| Language | Package Manager | Command Pattern |
|----------|----------------|-----------------|
| Python | `uv` | `uv add <package>` |
| Node.js | `pnpm` (preferred) / `bun` | `pnpm add <package>` / `bun add <package>` |
| Ruby | `bundle` | `bundle add <gem>` |
| Swift | `swift package` | Edit `Package.swift` |
| Rust | `cargo` | `cargo add <package>` |
| Go | `go modules` | `go get <package>@version` |

## Philosophy

### Why Latest Stable?
1. **Security** - Automatic security patches
2. **Compatibility** - Support for latest language features
3. **Maintainability** - Reduced version-lock maintenance burden

### Why Modern Tools?
- `mise` - Consistent tool version management
- `uv` - Extremely fast Python package installer
- `pnpm` - Efficient disk space usage for Node.js
- `bun` - All-in-one JavaScript runtime & package manager

## Project Detection

The plugin detects project type by checking root directory for configuration files:

```
pyproject.toml      → Python project  → use uv
package.json        → Node.js project → check lock file:
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

## License

MIT

## Version

0.1.0