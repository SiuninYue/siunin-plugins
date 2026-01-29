# Package Manager Plugin Standards

This document defines conventions and standards for the Package Manager plugin.

## Core Principles

### 1. Version Management Strategy
- **Always use latest stable versions** unless compatibility requires otherwise
- **Use mise for tool version management** when available
- **Document version compatibility requirements** when fixed versions are needed

### 2. Package Manager Selection Rules

| Language | Primary | Secondary | Fallback |
|----------|---------|-----------|----------|
| Python | `uv` | `pip` | `system pip` |
| Node.js | `pnpm` | `bun` | `npm` (when lock file present) |
| Ruby | `bundle` | `gem install --user-install` | `system gem` |
| Swift | `swift package` | - | - |
| Rust | `cargo` | - | - |
| Go | `go modules` | - | - |

### 3. Project Type Detection Logic

1. **Check root directory** for configuration files
2. **Prioritize by language specificity**:
   - Specific: `pyproject.toml`, `Gemfile`, `Package.swift`, `Cargo.toml`, `go.mod`
   - General: `package.json` (then check lock files)
3. **Lock file precedence**:
   - `pnpm-lock.yaml` → use pnpm
   - `bun.lockb` → use bun
   - `yarn.lock` → use yarn
   - `package-lock.json` → use npm
   - No lock file → recommend pnpm

## Skill Standards

### SKILL.md Frontmatter Requirements

```yaml
---
name: skill-name
description: This skill should be used when the user asks to [specific phrases] or mentions [concrete scenarios]
version: X.Y.Z
---
```

**Description Requirements**:
- Use third-person format: "This skill should be used when..."
- Include specific trigger phrases users would say
- Mention concrete scenarios, not vague terms
- Example: ✅ "This skill should be used when the user asks to 'install a package', 'add a dependency', or mentions package installation"
- Example: ❌ "This skill should be used when dealing with packages"

### Skill Content Structure

1. **Purpose** - Clear statement of what the skill accomplishes
2. **When to Use** - Specific trigger conditions
3. **Core Principles** - Fundamental rules and guidelines
4. **Implementation Details** - Step-by-step guidance
5. **Examples** - Concrete command examples (✅ correct, ❌ incorrect)
6. **References** - Links to detailed documentation

## Reference Documentation Standards

### package-managers.md Structure

1. **Overview** - High-level introduction and philosophy
2. **Version Strategy** - Detailed explanation of "latest stable" approach
3. **Language-Specific Guides** - Complete command references per language
4. **Troubleshooting** - Common issues and solutions
5. **Advanced Configuration** - Mise, workspace, and project configs
6. **Best Practices** - Summary of key recommendations

## Script Standards

### verify-rules.sh Requirements

1. **Portability**: Use `$CLAUDE_PLUGIN_ROOT` for all path references
2. **Error Handling**: Graceful degradation when tools are missing
3. **Clear Output**: Human-readable status messages with emoji indicators
4. **Project Detection**: Accurate detection based on actual files
5. **Actionable Suggestions**: Specific next steps for users

### Script Structure

```bash
#!/bin/bash
# Clear header with purpose
echo "=== Purpose ==="

# Check prerequisites
if [ ! -d "$CLAUDE_PLUGIN_ROOT" ]; then
    echo "⚠️  Plugin not found"
    exit 1
fi

# Tool detection
if command -v mise &> /dev/null; then
    echo "✅ mise installed"
else
    echo "❌ mise not installed"
fi

# Project analysis
# ...

# Recommendations
# ...
```

## Naming Conventions

### File and Directory Names
- Use **kebab-case** for all names
- Skill directories: descriptive and specific (e.g., `package-manager`, `rules-reviewer`)
- Reference files: descriptive names (e.g., `package-managers.md`)

### Variable and Command Names
- Use lowercase with underscores in scripts
- Use consistent terminology across all documentation
- Document acronyms on first use (e.g., "MCP (Model Context Protocol)")

## Quality Standards

### Documentation Quality
- Include both Chinese and English documentation where appropriate
- Use code blocks with language specification
- Include both positive (✅) and negative (❌) examples
- Link to official documentation when referencing external tools

### Code Quality
- Scripts must handle edge cases gracefully
- No hardcoded paths except for `$CLAUDE_PLUGIN_ROOT` fallbacks
- Include error checking for required tools
- Use comments to explain complex logic

## Compatibility Requirements

### Tool Compatibility
- Support all major platforms: macOS, Linux, Windows (WSL)
- Work with both bash and zsh shells
- Handle missing tools gracefully with installation instructions

### Plugin Compatibility
- Follow Claude Code plugin structure standards
- Compatible with other productivity plugins
- No conflicting command or skill names

## Testing Standards

### Manual Testing Checklist
- [ ] Plugin installs correctly via marketplace
- [ ] Skills activate on appropriate triggers
- [ ] verify-rules.sh runs without errors
- [ ] Documentation is clear and complete
- [ ] All code examples work as documented

### Validation
- Use plugin-validator agent to validate plugin structure
- Test with actual package installation scenarios
- Verify cross-platform compatibility