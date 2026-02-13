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
| `user-invocable` | boolean | Whether a skill is directly invocable by users (optional) |

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
| `checkpoints.json` | `.claude/` | Lightweight auto-checkpoint snapshots |

### Plan Artifact Boundaries

Use these two artifacts with strict responsibilities:

| Artifact | Location | Responsibility |
|----------|----------|----------------|
| Architecture master plan | `.claude/architecture.md` | Goals, boundaries, interface contracts, state flow, failure handling, ADRs, execution constraints |
| Feature execution plans | `docs/plans/feature-*.md` | Task-level execution plans for individual features |

Do not archive or mutate `.claude/architecture.md` during feature completion.

### Minimum Feature Plan Contract

Every execution plan under `docs/plans/feature-*.md` must include:

1. `Tasks`
2. `Acceptance Mapping`
3. `Risks`

Validate this contract before completion:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan
```

## Command Naming

All commands use the `prog` prefix:
- `/prog plan` - Architecture planning
- `/prog` - Display status
- `/prog init` - Initialize tracking
- `/prog next` - Start next feature
- `/prog done` - Complete feature
- `/prog-fix` - Bug report/list/fix workflow
- `/prog undo` - Undo last feature
- `/prog reset` - Remove tracking

`/prog-fix` is the canonical bug command spelling in docs and skill descriptions. Do not use `/prog fix` in new content.

## Command Docs Source Of Truth

`docs/PROG_COMMANDS.md` is the single source of truth for command help content.

- `README.md` command section is generated into `<!-- BEGIN:GENERATED:PROG_COMMANDS --> ... <!-- END:GENERATED:PROG_COMMANDS -->`
- `readme-zh.md` command section is generated into `<!-- BEGIN:GENERATED:PROG_COMMANDS --> ... <!-- END:GENERATED:PROG_COMMANDS -->`
- `docs/PROG_HELP.md` is generated from the same source.

After editing `docs/PROG_COMMANDS.md`, run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/generate_prog_docs.py --write
```

To check for drift without writing:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/generate_prog_docs.py --check
```

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
| `ai_metrics` | object\|null | No | Lightweight AI routing and duration metadata |

**Future v2.1+ fields (optional):**
| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Enum: `pending` \| `in_progress` \| `blocked` \| `done` |
| `started_at` | string | ISO 8601 timestamp (when started) |

### AI Metrics Object Schema (features[].ai_metrics)

| Field | Type | Description |
|-------|------|-------------|
| `complexity_score` | int | Complexity score in range 0-40 |
| `complexity_bucket` | string | Enum: `simple` \| `standard` \| `complex` |
| `selected_model` | string | Enum: `haiku` \| `sonnet` \| `opus` |
| `workflow_path` | string | Enum: `direct_tdd` \| `plan_execute` \| `full_design_plan_execute` |
| `started_at` | string | ISO 8601 timestamp |
| `finished_at` | string | ISO 8601 timestamp |
| `duration_seconds` | int | Elapsed seconds |

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
| `category` | string | Enum: `bug` \| `technical_debt` |
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
| `plan_path` | string | Relative path to execution plan file under `docs/plans/*.md` |
| `completed_tasks` | array | List of completed task IDs |
| `current_task` | int | Current task ID |
| `total_tasks` | int | Total number of tasks |
| `next_action` | string | Recommended next action |
| `updated_at` | string | ISO 8601 timestamp |

### Checkpoints Schema (`.claude/checkpoints.json`)

| Field | Type | Description |
|-------|------|-------------|
| `last_checkpoint_at` | string\|null | ISO 8601 timestamp of latest checkpoint |
| `max_entries` | int | Retention limit (default 50) |
| `entries` | array | Snapshot entries |

Checkpoint entry fields:
- `timestamp` (ISO-8601)
- `feature_id`
- `feature_name`
- `phase`
- `plan_path`
- `current_task`
- `total_tasks`
- `reason` (default `auto_interval`)

## AI-First Skill Documentation Pattern

For skills primarily consumed by AI, prefer fixed sections in this order:
1. `Purpose`
2. `Inputs`
3. `Outputs`
4. `State Read/Write`
5. `Steps`
6. `Failure Modes`
7. `Commands`
8. `Examples`

Use stable field names and enums (`complexity_bucket`, `workflow_path`, `category`) to reduce ambiguity across models.

### Migration Notes

- **v1 → v2.0**: Automatic migration adds `schema_version`, `updated_at` fields
- **Backward Compatibility**: Old v1 files are auto-upgraded on first save
- **Breaking Changes**: Increment `schema_version` major version when removing fields
