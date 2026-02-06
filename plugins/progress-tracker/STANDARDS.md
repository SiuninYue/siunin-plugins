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

## Progress JSON Schema (v2.0)

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | Yes | Schema version (e.g., "2.0") |
| `project_name` | string | Yes | Human-readable project name |
| `created_at` | string | Yes | ISO 8601 timestamp (project creation) |
| `updated_at` | string | Yes | ISO 8601 timestamp (last modification) |
| `features` | array | Yes | List of feature objects |
| `bugs` | array | No | List of bug objects |
| `current_feature_id` | int\|null | Yes | Currently active feature ID |
| `current_bug_id` | string\|null | No | Currently active bug ID |
| `workflow_state` | object\|null | No | Workflow execution state |

### Feature Object Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | int | Yes | Unique feature identifier (sequential) |
| `name` | string | Yes | Human-readable feature name |
| `test_steps` | array | Yes | List of test step strings or objects |
| `completed` | boolean | Yes | Feature completion status |
| `completed_at` | string\|null | No | ISO 8601 timestamp (when completed) |
| `commit_hash` | string\|null | No | Git commit hash (when completed) |

**Future v2.1+ fields (optional):**
| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Enum: `pending` \| `in_progress` \| `blocked` \| `done` |
| `started_at` | string | ISO 8601 timestamp (when started) |

### Bug Object Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Bug identifier (e.g., "BUG-001") |
| `description` | string | Yes | Bug description (max 2000 chars) |
| `status` | string | Yes | Enum: `pending_investigation` \| `investigating` \| `confirmed` \| `fixing` \| `fixed` \| `false_positive` |
| `priority` | string | Yes | Enum: `high` \| `medium` \| `low` |
| `created_at` | string | Yes | ISO 8601 timestamp |

**Optional Bug Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `updated_at` | string | ISO 8601 timestamp (last update) |
| `root_cause` | string | Root cause analysis |
| `fix_summary` | string | Summary of applied fix |
| `fix_commit_hash` | string | Git commit hash of fix |
| `verified_working` | boolean | Fix verification status |
| `repro_steps` | string | Steps to reproduce |
| `workaround` | string | Temporary workaround |
| `quick_verification` | object | JSON verification results (max 10KB) |
| `scheduled_position` | object | Scheduling directive (before/after feature) |
| `investigation` | object | Investigation details with sub-fields |

### Workflow State Schema

| Field | Type | Description |
|-------|------|-------------|
| `phase` | string | Current phase: `design_complete` \| `planning_complete` \| `execution` \| `execution_complete` |
| `plan_path` | string | Path to execution plan file |
| `completed_tasks` | array | List of completed task IDs |
| `current_task` | int | Current task ID |
| `total_tasks` | int | Total number of tasks |
| `next_action` | string | Recommended next action |
| `updated_at` | string | ISO 8601 timestamp |

### Migration Notes

- **v1 → v2.0**: Automatic migration adds `schema_version`, `updated_at` fields
- **Backward Compatibility**: Old v1 files are auto-upgraded on first save
- **Breaking Changes**: Increment `schema_version` major version when removing fields
