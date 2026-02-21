# Progress Tracker Plugin

> Track long-running AI agent tasks with feature-based progress tracking, test-driven status updates, and Git integration.

## Description

The Progress Tracker plugin solves the critical problem of maintaining progress across multi-session AI-assisted development projects. It provides:

- **Feature-based tracking** - Break goals into testable features
- **Test-driven status** - Features only complete after passing tests
- **Git integration** - Each feature creates a clean commit
- **Session recovery** - Auto-detects and resumes interrupted work
- **Superpowers integration** - Professional TDD workflow orchestration

## Installation

```bash
/plugin install progress-tracker
```

**Dependencies**: Requires [Superpowers](https://github.com/obra/superpowers-marketplace) plugin for systematic development workflows.

## Quick Start

```bash
# Initialize project tracking
/prog init Build a user authentication system

# Start next feature
/prog next

# Complete and commit
/prog done
```

## Commands

| Command | Description |
|---------|-------------|
| `/prog init <goal>` | Initialize progress tracking for a new goal |
| `/prog plan` | Create architectural plan with technology selection |
| `/prog` | Display current project status |
| `/prog sync` | Sync capability memory from incremental Git history |
| `/prog next` | Start implementing next pending feature |
| `/prog-fix [bug]` | Report, list, or fix bugs with smart scheduling |
| `/prog done` | Complete current feature after testing |
| `/prog undo` | Revert most recently completed feature |
| `/prog reset` | Remove progress tracking from project |

## Features

- 9 commands for progress management
- 9 skills with clear responsibilities
- SessionStart hook for auto-recovery
- External state persistence (survives context loss)
- Rich progress feedback with visual indicators
- Complexity-based workflow selection

## License

MIT
