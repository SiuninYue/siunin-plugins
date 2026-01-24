# Repository Standards

This document defines shared conventions for commands, agents, and skills in this plugin.

## Front Matter Schema

All markdown files under `commands/`, `agents/`, and `skills/*/SKILL.md` must include these keys.

### Required Keys

| Key | Type | Description |
|-----|------|-------------|
| `version` | string | Semantic version string (e.g., "1.0.0") |
| `scope` | string | One of: `command`, `agent`, `skill` |
| `inputs` | array | Short list of required inputs |
| `outputs` | array | Short list of expected outputs |
| `evidence` | string | One of: `required`, `conditional`, `optional` |
| `references` | array | List of attachments loaded only when needed |

### Optional Keys

| Key | Type | Description |
|-----|------|-------------|
| `model` | string | Recommended Claude model (haiku, sonnet, opus) |
| `name` | string | Command/agent/skill name (optional if derived from filename) |
| `description` | string | Short description of purpose |

## Model Selection Guide

Choose the appropriate model based on task complexity:

| Model | Use Case | Examples |
|-------|----------|----------|
| **haiku** | Simple queries, status display, formatting | `/prog` |
| **sonnet** | Standard tasks, analysis, recovery, administrative | `/prog init`, `/prog next`, `/prog done`, `/prog undo`, `/prog reset`, progress-recovery |
| **opus** | Complex planning, multi-step reasoning | Complex feature breakdown with dependencies |

## Evidence & Timestamp

Outputs that involve external facts or user research must include:
- **Data source type** (e.g., interview, analytics, public source)
- **Timestamp** (date/time of data)
- **Evidence strength** (strong/medium/weak)

## Output Modes

Every command supports two modes:

- **简版 (Brief)**: Only decision + key reasons + next actions
- **完整版 (Full)**: Complete template output

Default is **完整版** unless the user explicitly asks for a short version.

## Skill Attachments (Delayed Load)

Skill attachments live in the same folder as `SKILL.md`.

**Rules**:
- Do not load attachments by default
- Only load when the user asks for details or the command explicitly needs it
- All attachments must be listed in `references`

## Changes & Compatibility

If output templates change materially:
1. Update the version in front matter
2. Document changes in `CHANGELOG.md`
3. Update `README.md` with a short note if user-facing

## Progress Tracking Conventions

### Feature State Machine

```
pending → in_progress → completed
    ↑                    ↓
    └─────── undo ───────┘
```

### Git Commit Message Format

Features are committed with this format:
```
feat(complete): <feature name>

- Test steps verified
- Progress tracking updated
```

### Progress File Locations

| File | Location | Purpose |
|------|----------|---------|
| `progress.json` | `.claude/` | Machine-readable state |
| `progress.md` | `.claude/` | Human-readable display |

## Command Naming

All commands use the `prog` prefix:
- `/prog` - Display status
- `/prog init` - Initialize tracking
- `/prog next` - Start next feature
- `/prog done` - Complete feature
- `/prog undo` - Undo last feature
- `/prog reset` - Remove tracking

## Error Handling

Commands should handle these error conditions gracefully:

| Condition | Action |
|-----------|--------|
| No progress tracking found | Suggest `/prog init` |
| No features pending | Display completion message |
| Git working directory dirty | For `/prog undo`, abort with error message |
| Feature not found | Display available features |

## Testing Requirements

Each feature MUST include test steps that are:
- **Specific**: Clear actions to perform
- **Verifiable**: Observable results
- **Atomic**: Can be run independently

Example:
```markdown
Test steps:
- Run: curl -X POST http://localhost:8000/api/register -d '{"email":"test@example.com","password":"pass123"}'
- Check: sqlite3 database.db "SELECT * FROM users WHERE email='test@example.com';"
- Verify: Response contains user ID and timestamp
```
