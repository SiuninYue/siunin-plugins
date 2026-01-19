# Progress Tracker Plugin

Track long-running AI agent tasks with feature-based progress tracking, test-driven status updates, and Git integration.

## Overview

The Progress Tracker plugin solves a critical problem in AI-assisted development: **how to maintain progress across multi-session projects** without losing context or skipping testing.

### Core Problems Addressed

1. **Context Window Exhaustion** - Long tasks get compressed, losing progress memory
2. **Testing Skip** - Features marked "done" without verification don't actually work
3. **Session Interruption** - Closing the window means losing your place
4. **No Clear Progress** - Unclear what's done vs. what remains

### Solutions

- **Feature List Driven** - Goals broken into specific, testable features
- **Test-Driven Status** - Features start `false`, only `true` after passing tests
- **Git as Memory** - Each feature commits, creating a clear history
- **External Persistence** - Progress stored in files, survives session restarts
- **feature-dev Integration** - Professional implementation workflow via official plugin

## Dependencies

This plugin integrates with the **Superpowers** skills library for systematic development workflows:

```bash
# Install Superpowers (recommended)
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

**Alternative**: You can still use the legacy **feature-dev** plugin, but Superpowers provides stronger TDD enforcement and code review processes.

```bash
# Legacy option (feature-dev)
claude plugins install feature-dev@claude-plugins-official
```

## Commands

### `/prog init <goal description>`

Initialize progress tracking for a new goal.

Analyzes your objective and breaks it down into 5-10 specific features with test steps.

**Example:**
```bash
/prog init Build a user authentication system with registration and login
```

**Behavior:**
- Checks for existing progress tracking
- Intelligently decomposes goal into features
- Defines test steps for each feature
- Orders features by dependency
- Creates `.claude/progress.json` and `.claude/progress.md`

### `/prog`

Display current project status.

Shows completion statistics, current feature, and next step recommendations.

**Example Output:**
```
## Project Progress: User Authentication

**Status**: 2/5 completed (40%)
**Current Feature**: Login API (in progress)

### Recommended Next Steps

Continue with current feature or run `/prog done` to complete.
```

### `/prog next`

Start implementing the next pending feature.

Automatically invokes the **feature-dev** plugin for guided implementation.

**Behavior:**
1. Identifies first uncompleted feature
2. Sets `current_feature_id`
3. Displays feature details and test steps
4. Launches `/feature-dev` workflow
5. Prompts to run `/prog done` when complete

### `/prog done`

Complete the current feature after testing.

Runs test steps, updates progress tracking, and creates a Git commit.

**Behavior:**
1. Executes all test steps defined for the feature
2. If tests fail → Reports error, keeps feature in progress
3. If tests pass → Creates Git commit, Marks complete
4. Updates `progress.json` (stores commit hash) and `progress.md`
5. Suggests next action

## Maintenance Phase

Once development is underway, you may need to manage the project state.

### `/prog undo`

Revert the most recently completed feature.

**Behavior:**
1. **Safety Check**: Ensures git working directory is clean.
2. **Git Revert**: Creates a *new* commit that inverses the changes of the feature (safe for shared repos).
3. **Status Rollback**: Marks the feature as "pending" again in the tracker.

### `/prog reset`

Completely remove progress tracking from the project.

**Behavior:**
1. Asks for confirmation.
2. Deletes `.claude/progress.json` and `.claude/progress.md`.
3. **Does NOT** affect your code or Git history.

## Architecture

### Commands vs Skills

The plugin follows a **Commands → Skills** architecture:

| Component | Role | Description |
|-----------|------|-------------|
| **Commands** | Entry points | Thin layer that invokes skills |
| **Skills** | Logic | Reusable knowledge with business logic |
| **Hooks** | Events | SessionStart detects incomplete work |
| **Scripts** | State | Python script manages JSON/MD files |

### Skills (5 total)

1. **feature-breakdown** - Analyzes goals, creates feature lists
2. **progress-status** - Displays status and statistics
3. **feature-implement** - Coordinates with feature-dev plugin
4. **feature-complete** - Runs tests, commits, updates state
5. **progress-recovery** - Analyzes context for session resumption

### Progress Files

Stored in your project's `.claude/` directory:

**progress.json** - Machine-readable state:
```json
{
  "project_name": "User Authentication",
  "created_at": "2024-01-18T10:00:00Z",
  "features": [
    {
      "id": 1,
      "name": "User database model",
      "test_steps": ["Run migration", "Check table exists"],
      "completed": true
    },
    {
      "id": 2,
      "name": "Registration API",
      "test_steps": ["curl test endpoint", "Verify database"],
      "completed": false
    }
  ],
  "current_feature_id": 2
}
```

**progress.md** - Human-readable log:
```markdown
# Project Progress: User Authentication

## Completed
- [x] User database model (commit: abc123)

## In Progress
- [ ] Registration API
  Test steps:
  - POST /api/register with valid data
  - Check database for new user

## Pending
- [ ] Login API
- [ ] JWT token generation
```

## Workflow Example

```bash
# 1. Start a new project
/prog init Build a TODO app with CRUD operations

# → Creates feature list: database, API, frontend, etc.

# 2. Check status
/prog

# → Shows 0/5 complete

# 3. Start first feature (auto-invokes feature-dev)
/prog next

# → feature-dev guides through architecture and implementation

# 4. Complete and commit
/prog done

# → Runs tests, marks complete, creates Git commit

# [Session closes or restarts]

# 5. SessionStart hook detects incomplete work
# → Shows: "Progress 1/5, use /prog to continue"

# 6. Resume and continue
/prog
/prog next
```

## Integration with Superpowers Skills

The Progress Tracker orchestrates **Superpowers** workflow skills for systematic, TDD-driven implementation:

| Responsibility | Component |
|----------------|-----------|
| Feature breakdown | progress-tracker |
| Progress state | progress-tracker |
| Acceptance testing | progress-tracker |
| Git commits (feature-level) | progress-tracker |
| Design exploration | superpowers:brainstorming |
| Implementation planning | superpowers:writing-plans |
| TDD execution | superpowers:test-driven-development |
| Subagent coordination | superpowers:subagent-driven-development |
| Code review (dual-stage) | superpowers reviewers |

**Key benefits of Superpowers integration**:
- ✅ **Enforced TDD**: Mandatory RED-GREEN-REFACTOR cycle
- ✅ **Dual-stage review**: Spec compliance + code quality
- ✅ **Task-level commits**: Clean Git history
- ✅ **Session recovery**: Resume interrupted workflows
- ✅ **Proven patterns**: Battle-tested development processes

**Workflow example**:
```bash
/prog next               # Progress Tracker selects feature
                         # → Assesses complexity
                         # → Invokes superpowers:writing-plans
                         # → Invokes superpowers:subagent-driven-development
                         # → Each task: TDD + review + commit
/prog done               # Progress Tracker runs acceptance tests
                         # → Creates feature commit
                         # → Updates progress.json
```

**Alternative: feature-dev plugin**

The legacy integration with feature-dev is still supported:
- Better for **legacy codebases** (has code-explorer for deep analysis)
- Superpowers is better for **new projects** (stronger process enforcement)

To use feature-dev instead, modify `skills/feature-implement/SKILL.md` to invoke `/feature-dev` as before.

## Directory Structure

```
plugins/progress-tracker/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   ├── prog.md
│   ├── prog-init.md
│   ├── prog-next.md
│   └── prog-done.md
├── skills/
│   ├── feature-breakdown/
│   │   └── SKILL.md
│   ├── progress-status/
│   │   └── SKILL.md
│   ├── feature-implement/
│   │   └── SKILL.md
│   ├── feature-complete/
│   │   └── SKILL.md
│   └── progress-recovery/
│       └── SKILL.md
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       └── progress_manager.py
└── README.md
```

## Session Recovery

The plugin automatically detects incomplete work when you open a new session:

**SessionStart Hook** checks:
1. Does `.claude/progress.json` exist?
2. Are there uncompleted features?
3. Is there a `current_feature_id` set?
4. Are there uncommitted Git changes?

If incomplete work is detected, displays:
```
[Progress Tracker] Unfinished project detected
Project: User Authentication
Progress: 2/5 complete
Current feature: Login API
Use /prog to view status
```

## Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Test-Driven** | Features only complete after passing tests |
| **Git-Native** | Each feature commits, history is progress |
| **External State** | Progress in files, survives context loss |
| **Clear Separation** | Commands → Skills → Scripts |
| **Professional** | Leverages feature-dev for implementation |
| **Recoverable** | Session resumption with context |

## License

MIT
