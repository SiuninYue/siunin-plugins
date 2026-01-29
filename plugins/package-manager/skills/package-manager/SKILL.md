---
name: package-manager
description: This skill should be used when the user asks to "install a package", "add a dependency", "set up a project", "configure package manager", "initialize scaffolding", or mentions package installation, dependency management, or project setup. Provides comprehensive guidance for using mise, uv, pnpm, bun, and other modern package managers with latest stable version strategy.
version: 0.1.0
---

# Package Manager Rules

## Purpose

This skill provides standardized package management guidance for Claude Code. It ensures all package installations and project setups use modern, efficient tools (mise, uv, pnpm, bun) configured with latest stable versions.

## When to Use

Activate this skill when:
- Installing any package or dependency
- Setting up new projects
- Configuring package managers
- Initializing scaffolding
- Questions about which package manager to use

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

| Language | Package Manager | Command Pattern |
|----------|----------------|-----------------|
| Python | `uv` | `uv add <package>` |
| Node.js | `pnpm` (preferred) / `bun` | `pnpm add <package>` / `bun add <package>` |
| Ruby | `bundle` | `bundle add <gem>` |
| Swift | `swift package` | Edit `Package.swift` |
| Rust | `cargo` | `cargo add <package>` |
| Go | `go modules` | `go get <package>@version` |

## Project Type Detection

Detect project type by checking root directory files:

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

## Workflow

1. **Detect project type** by checking root directory for config files
2. **Check mise configuration** for tool versions
3. **Select appropriate package manager** based on project type
4. **Use correct command pattern** for the package manager
5. **Recommend mise use latest** if using outdated tools

## Additional Resources

### Scripts

- **`$CLAUDE_PLUGIN_ROOT/scripts/verify-rules.sh`** - Verify package manager setup and detect project type

### References

- **`references/package-managers.md`** - Detailed package manager documentation with examples and troubleshooting
