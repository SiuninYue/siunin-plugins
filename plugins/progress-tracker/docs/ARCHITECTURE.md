# Progress Tracker Plugin - Architecture Documentation

## System Overview

Progress Tracker is a Claude Code plugin that provides cross-session progress tracking for AI-assisted development projects. It maintains feature lists, bug backlogs, and workflow state through a JSON-based persistence layer.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Claude Code                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │   Commands   │      │    Skills    │      │    Hooks     │  │
│  │              │      │              │      │              │  │
│  │ /prog init   │─────▶│feature-      │─────▶│SessionStart  │  │
│  │ /prog next   │      │implement     │      │              │  │
│  │ /prog done   │      │breakdown     │      │check command │  │
│  │ /prog status │      │architectural │      │              │  │
│  │ /prog fix    │      │planning      │      │              │  │
│  └──────────────┘      └──────────────┘      └──────────────┘  │
│                                                  │              │
│                                                  ▼              │
│                                    ┌─────────────────────┐     │
│                                    │  progress_manager   │     │
│                                    │                     │     │
│                                    │ - load_progress_json │     │
│                                    │ - save_progress_json │     │
│                                    │ - init_tracking      │     │
│                                    │ - complete_feature   │     │
│                                    │ - add_bug            │     │
│                                    └─────────────────────┘     │
│                                                  │              │
│          ┌───────────────────────────────────────┘              │
│          ▼                                                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   Security Layer                            │ │
│  │                                                             │ │
│  │  ┌────────────────┐      ┌──────────────────────────┐     │ │
│  │  │ git_validator   │      │  complexity_analyzer     │     │ │
│  │  │                │      │                          │     │ │
│  │  │ - validate_    │      │  - analyze_complexity()  │     │ │
│  │  │   commit_hash  │      │  - caching with TTL      │     │ │
│  │  │ - safe_git_    │      │  - metrics calculation   │     │ │
│  │  │   command()    │      │                          │     │ │
│  │  └────────────────┘      └──────────────────────────┘     │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                  │              │
│                                                  ▼              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Persistence Layer                        │ │
│  │                                                             │ │
│  │  .claude/                                                   │ │
│  │  ├── progress.json   (feature list, bugs, workflow state)   │ │
│  │  ├── progress.md     (human-readable status)                │ │
│  │  ├── architecture.md (technical decisions)                  │ │
│  │  └── .cache/                                                   │
│  │      └── complexity_cache.json                               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Git Integration                          │ │
│  │                                                             │ │
│  │  - Auto-commit after task completion                        │ │
│  │  - Feature-level commits                                    │ │
│  │  - Git revert for undo functionality                        │ │
│  │  - Safe command execution (injection protection)            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
User Input
    │
    ▼
┌──────────────┐
│  /prog next  │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────┐
│  Load .claude/progress.json     │
│  - Find next incomplete feature │
│  - Check workflow state         │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│  Update current_feature_id      │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│  Assess Complexity              │
│  (complexity_analyzer)          │
└──────┬──────────────────────────┘
       │
       ├── Simple ──────────────────────┐
       │                                  │
       ├── Standard ──────────────┐      │
       │                          │      │
       └── Complex ────────┐      │      │
                          │      │      │
       ┌──────────────────┘      │      │
       │                         │      │
       ▼                         ▼      ▼
┌─────────────┐         ┌────────────┐
│ Superpowers │         │  Fallback  │
│ Workflow    │         │  Workflow  │
└──────┬──────┘         └─────┬──────┘
       │                     │
       └──────────┬──────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Implementation │
         │ - TDD cycle    │
         │ - Code review  │
         └───────┬────────┘
                 │
                 ▼
         ┌────────────────┐
         │ /prog done     │
         │ - Run tests    │
         │ - Git commit   │
         │ - Mark complete│
         └────────────────┘
```

## State Machine

```
                    ┌──────────────┐
                    │   No Track   │
                    │     ing      │
                    └──────┬───────┘
                           │  /prog init
                           ▼
                    ┌──────────────┐
                    │   Pending    │◀────────────────────┐
                    │              │                     │
                    └──────┬───────┘                     │
                           │ /prog next                  │
                           ▼                             │
                    ┌──────────────┐                     │
                    │ In Progress  │                     │
                    │              │─────┐               │
                    └──────┬───────┘     │ /prog undo    │
                           │             │ (revert)      │
                           │             ▼               │
                           │      ┌──────────────┐       │
                           │      │  Completed   │       │
                           │      │              │───────┘
                           │      └──────┬───────┘
                           │             │ /prog next
                           │             ▼
                           │      ┌──────────────┐
                           │      │   Pending    │
                           │      │  (next feat) │
                           │      └──────────────┘
                           │
                           │ /prog done
                           ▼
                    ┌──────────────┐
                    │  Completed   │
                    │              │
                    └──────────────┘
```

## Workflow State Machine

```
┌──────────────┐
│     None     │ (no workflow state)
└──────┬───────┘
       │ /prog next
       ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Design     │────▶│   Planning   │────▶│  Execution   │
│   Complete   │     │   Complete   │     │              │
└──────────────┘     └──────┬───────┘     └──────┬───────┘
                           │                     │
                           │                     ▼
                           │              ┌──────────────┐
                           │              │  Execution   │
                           │              │   Complete   │
                           │              └──────┬───────┘
                           │                     │
                           │                     ▼
                           │              ┌──────────────┐
                           │              │    Verify    │
                           │              │   & Complete │
                           │              └──────────────┘
                           │                     │
                           └─────────────────────┘
                                       │
                                       ▼
                                /prog done
```

## Component Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                        Core Modules                             │
│                                                                   │
│  progress_manager.py          git_validator.py                  │
│  ┌──────────────────┐        ┌──────────────────┐              │
│  │ Feature Tracking │        │ Security Layer    │              │
│  │ - init_tracking  │◀───────│ - validate_commit │              │
│  │ - add_feature    │        │ - safe_git_cmd    │              │
│  │ - complete_feat  │        │ - is_git_repo     │              │
│  │ - undo_last_feat │        └──────────────────┘              │
│  │                  │                                           │
│  │ Bug Tracking     │        complexity_analyzer.py            │
│  │ - add_bug        │        ┌──────────────────┐              │
│  │ - update_bug     │        │ Performance Layer │              │
│  │ - list_bugs      │        │ - analyze_complex │              │
│  │                  │        │ - caching         │              │
│  │ Workflow State   │        │ - metrics         │              │
│  │ - set_workflow   │        └──────────────────┘              │
│  │ - update_task    │                                           │
│  │ - clear_state    │                                           │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Security Layer Design

The security layer provides protection against command injection and other security threats:

### Git Command Validation

1. **Commit Hash Validation**
   - Format: 7-40 hexadecimal characters
   - Pattern: `^[0-9a-f]{7,40}$`
   - Blocks: Shell metacharacters, command substitution

2. **Command Argument Validation**
   - Dangerous characters: `; & | $ \` ( ) < > \n \r \t`
   - Pattern detection: `$(...)`, backticks, pipes, redirections

3. **Timeout Enforcement**
   - Default: 30 seconds
   - Prevents hanging operations
   - Configurable per operation

### Data Sanitization

1. **Bug Descriptions**
   - Max length: 2000 characters
   - Control character removal
   - Duplicate detection

2. **Feature Names**
   - Whitespace trimming
   - Empty string validation

## File Structure

```
progress-tracker/
├── commands/              # CLI commands (prog-*.md)
├── skills/                # Skill definitions
│   ├── feature-implement/
│   ├── feature-breakdown/
│   ├── feature-complete/
│   ├── bug-fix/
│   └── progress-*
├── hooks/                 # Plugin hooks
│   ├── hooks.json        # Hook configuration
│   └── scripts/          # Executable scripts
│       ├── progress_manager.py
│       ├── git_validator.py
│       └── complexity_analyzer.py
├── tests/                 # Test suite
│   ├── test_git_validator.py
│   └── test_integration.py
├── docs/                  # Documentation
│   ├── ARCHITECTURE.md   # This file
│   └── TROUBLESHOOTING.md
├── .claude-plugin/        # Plugin metadata
│   └── plugin.json
├── README.md
├── CHANGELOG.md
└── STANDARDS.md
```

## Database Schema

### progress.json Structure

```json
{
  "schema_version": "2.0",
  "project_name": "Project Name",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T14:20:00Z",
  "features": [
    {
      "id": 1,
      "name": "Feature Name",
      "test_steps": ["step1", "step2"],
      "completed": false,
      "completed_at": "2024-01-15T14:20:00Z",
      "commit_hash": "a1b2c3d4e5f6...",
      "archive_info": {
        "archived_at": "2024-01-15T14:25:00Z",
        "files_moved": 2,
        "files": [...]
      }
    }
  ],
  "bugs": [
    {
      "id": "BUG-001",
      "description": "Bug description",
      "status": "pending_investigation",
      "priority": "high",
      "created_at": "2024-01-15T10:30:00Z",
      "root_cause": "Root cause analysis",
      "fix_summary": "Summary of fix",
      "fix_commit_hash": "abc1234",
      "verified_working": true,
      "scheduled_position": {
        "type": "before_feature",
        "feature_id": 3,
        "reason": "Blocks feature implementation"
      }
    }
  ],
  "current_feature_id": 2,
  "current_bug_id": "BUG-001",
  "workflow_state": {
    "phase": "execution",
    "plan_path": "docs/plans/2024-01-15-feature.md",
    "completed_tasks": [1, 2],
    "current_task": 3,
    "total_tasks": 5,
    "next_action": "verify_and_complete",
    "updated_at": "2024-01-15T14:20:00Z"
  }
}
```

## Key Design Decisions

### 1. JSON-Based Persistence
- **Rationale**: Human-readable, easy to inspect, git-friendly
- **Trade-off**: No ACID guarantees, but sufficient for single-user workflow

### 2. Git Integration
- **Rationale**: Leverage Git for version control and undo
- **Trade-off**: Requires clean working directory for some operations

### 3. Hook-Based Architecture
- **Rationale**: Automatic session recovery via SessionStart hook
- **Trade-off**: 30-second timeout required for large projects

### 4. Complexity Caching
- **Rationale**: Improve performance for repeated analyses
- **Trade-off**: Cache invalidation complexity

### 5. Security-First Design
- **Rationale**: Prevent command injection in Git operations
- **Trade-off**: Additional validation overhead

## Extension Points

### Adding New Commands
1. Create `<command>.md` in `commands/`
2. Reference in plugin skills as needed
3. Update documentation

### Adding New Skills
1. Create skill directory in `skills/`
2. Add `SKILL.md` with proper frontmatter
3. Reference in `plugin.json` if needed

### Extending Workflow States
1. Add new phase to workflow state enum
2. Update state machine documentation
3. Handle in progress-recovery skill

## Performance Considerations

### Cache Strategy
- Complexity analysis cached for 1 hour
- Cache stored in `.claude/.cache/complexity_cache.json`
- Automatic expiration on read

### Git Operations
- All Git commands have 30-second timeout
- Status checks use `--porcelain` for fast output
- Working directory checks are cached during workflow

### Large Projects
- For projects with 100+ features, consider:
  - Increasing hook timeout in `hooks.json`
  - Running health check to get recommended timeout
  - Disabling complexity cache if not needed

## Monitoring

### Health Check Command
```bash
python3 hooks/scripts/progress_manager.py health
```

Returns:
```json
{
  "status": "healthy",
  "response_time_ms": 45,
  "load_time_ms": 12,
  "git_time_ms": 8,
  "git_healthy": true,
  "data_valid": true,
  "features_count": 5,
  "bugs_count": 2,
  "recommended_timeout": 10
}
```

### Logs
- Check logs via Claude Code's debug output
- Progress manager uses Python logging module
- Set `CLAUDE_DEBUG=1` for verbose output
