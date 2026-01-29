# Changelog

All notable changes to the Package Manager plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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