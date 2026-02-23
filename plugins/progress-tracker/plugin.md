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

**Command naming note**: Plugin commands are registered from `commands/*.md` and use hyphenated slash names (for example `/prog-start`, `/prog-sync`). In namespaced form they appear as `/progress-tracker:<command>`.

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
| `/prog-init <goal>` | Initialize progress tracking for a new goal |
| `/prog-plan` | Create architectural plan with technology selection |
| `/prog` | Display current project status |
| `/prog-sync` | Sync capability memory from incremental Git history |
| `/prog-next` | Start implementing next pending feature |
| `/prog-start` | Transition the active feature from planning to developing |
| `/prog-fix [bug]` | Report, list, or fix bugs with smart scheduling |
| `/prog-done` | Complete current feature after testing |
| `/prog-undo` | Revert most recently completed feature |
| `/prog-reset` | Remove progress tracking from project |
| `/prog-ui` | Launch the progress web UI |
| `/progress-tracker:help` | Show namespaced plugin command help |

## Features

- Progress and UI commands auto-discovered from `commands/*.md`
- Skills organized under `skills/*/SKILL.md`
- SessionStart hook for auto-recovery
- External state persistence (survives context loss)
- Rich progress feedback with visual indicators
- Complexity-based workflow selection

## License

MIT
