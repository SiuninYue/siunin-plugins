# Progress Tracker Plugin

Track long-running AI agent tasks with feature-based progress tracking, test-driven status updates, and Git integration. An intelligent development orchestrator that guides you through systematic, TDD-driven implementation.

## Overview

The Progress Tracker plugin solves a critical problem in AI-assisted development: **how to maintain progress across multi-session projects** without losing context or skipping testing.

### Core Problems Addressed

1. **Context Window Exhaustion** - Long tasks get compressed, losing progress memory
2. **Testing Skip** - Features marked "done" without verification don't actually work
3. **Session Interruption** - Closing the window means losing your place
4. **No Clear Progress** - Unclear what's done vs. what remains
5. **Skill Invocation Reliability** - Skills described but not executed

### Solutions

- **Feature List Driven** - Goals broken into specific, testable features
- **Test-Driven Status** - Features start `false`, only `true` after passing tests
- **Git as Memory** - Each feature commits, creating a clear history
- **External Persistence** - Progress stored in files, survives session restarts
- **Superpowers Integration** - Professional TDD workflow with enforced quality gates
- **Intelligent Session Recovery** - Auto-detects and guides resumption of interrupted work
- **Rich Progress Feedback** - Clear visual progress indicators and phase transitions
- **Deterministic Model Routing** - Explicitly routes simple/standard/complex work to haiku/sonnet/opus paths
- **Lightweight AI Metrics** - Tracks complexity bucket, selected model, and duration (no token/cost estimation)
- **Technical Debt Unification** - Records debt items in existing bug system via `category=technical_debt`
- **Structured Update Stream** - Captures `status|decision|risk|handoff|assignment|meeting` updates in `updates[]`
- **Role Ownership Tracking** - Stores `architecture|coding|testing` owners per feature for cross-team handoff clarity
- **Lightweight Checkpoints** - Auto-saves workflow snapshots to `docs/progress-tracker/state/checkpoints.json` (no git history pollution)
- **Worktree-Aware Recovery** - Records branch/worktree context so `/prog` and `/prog-done` can warn when you resume in the wrong workspace
- **Unified Git Preflight** - `prog git-auto-preflight --json` is the single workspace/Git risk probe used by `git-auto` and `/prog-next`

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

Command help in this section is generated from `docs/PROG_COMMANDS.md`.

<!-- BEGIN:GENERATED:PROG_COMMANDS -->
<!-- GENERATED CONTENT: DO NOT EDIT DIRECTLY -->
### `/progress-tracker:prog-plan <project description>` (alias: `/prog-plan`)

Create architecture plan and technology decisions before feature implementation.

### `/progress-tracker:prog-init <goal description>` (alias: `/prog-init`)

Initialize progress tracking and break goal into testable features.

### `/progress-tracker:prog` (alias: `/prog`)

Show current project status and recommended next action. Includes linked project matrix (completion rate, stale markers) and archive history summary when available.

### `/progress-tracker:prog-log` (alias: `/prog-log`)

Sync project capability memory from git history with batch confirmation.

### `/progress-tracker:prog-note` (alias: `/prog-note`)

Record a structured progress update (status/decision/risk/handoff/assignment/meeting).

### `/progress-tracker:prog-next` (alias: `/prog-next`)

Start the next pending feature with deterministic complexity routing.

### `/progress-tracker:prog-next` — `prog next --done`

Close the currently active task.

- **Standalone task** (`parent_feature_id=null`): squash-merges the task branch into the default branch, deletes the branch, adds exactly 1 commit. No feature done-gate is triggered.
- **Feature-bound task** (`parent_feature_id` set): marks the task completed and advances parent feature task-progress counter. Parent feature is **not** auto-closed.

**RC semantics:** 0 = success; 1 = precondition failure (no active task, invalid state); 2 = parameter error.

```bash
prog next --done           # close current task (human-readable output)
prog next --done --json    # machine-readable: {"status","closed_task_id","message"}
```

### `/progress-tracker:prog-add-task` — `prog add-task`

Create a new task item.

```bash
prog add-task --description "Fix typo in README"
prog add-task --description "Implement login" --feature-id 3
prog add-task --description "Quick cleanup" --workflow-profile quick_task --priority P0
```

**Constraints:**
- `--feature-id` must reference an existing feature (RC=1 if not found).
- `--feature-id` and `--workflow-profile quick_task` are mutually exclusive (RC=2).

### Ghost Commands (do NOT use)

| Command | Correct replacement |
|---------|---------------------|
| `prog start-task <id>` | `prog next --done` |

### `/progress-tracker:prog-done` (alias: `/prog-done`)

Run acceptance verification and complete the current feature.

### `/progress-tracker:prog-fix` (alias: `/prog-fix`)

Report, list, investigate, and fix bugs with systematic debugging and TDD.

### `/progress-tracker:prog-undo` (alias: `/prog-undo`)

Undo the last completed feature and revert its code changes.

### `/progress-tracker:prog-reset` (alias: `/prog-reset`)

Reset active progress tracking files after explicit confirmation (auto-archives previous snapshot).

### `/progress-tracker:help`

Show plugin command help (namespaced entry for conflict-free discovery).

### `/progress-tracker:prog-ui` (alias: `/prog-ui`)

Launch the Progress UI web server and open in browser. Auto-detects available port (3737-3747). Detects if a server for the current project is already running.

### Low-Learning-Cost Command Layers

Daily commands (default path):

- `/prog` → status + next recommendation
- `/prog-next` → start/continue the next actionable feature
- `/prog-done` → acceptance closeout for active feature

Admin commands (only when needed):

- `prog check` / `prog reconcile` for drift diagnostics
- `prog defer` / `prog resume` for backlog parking and restore
- `prog next-feature --json` for machine-driven feature selection

### Runtime Boundary (Claude vs Codex)

- Slash commands (`/prog`, `/prog-next`, `/prog-done`) are the daily UX in Claude Code.
- CLI commands (`prog check`, `prog reconcile`, `prog defer`, `prog resume`, `prog next-feature --json`) are for diagnostics/admin/automation.
- Both runtimes share the same backend logic (`hooks/scripts/progress_manager.py`).

### Progress Manager CLI

Preferred cross-runtime wrapper (Codex/local shell):

```bash
plugins/progress-tracker/prog --project-root plugins/<name> status
```

Global scope override (recommended in monorepos):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py --project-root plugins/<name> status
```

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py init <project_name> [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py status
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py check
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reconcile [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py next-feature [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-archives [--limit <n>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py restore-archive <archive_id> [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py sync-linked [--json] [--stale-after-hours <hours>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-current <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-readiness <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py fix-readiness <feature_id> [--add-requirement <req-id>] [--set-why "<why>"] [--add-acceptance "<scenario>"]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete <feature_id> --commit <hash>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py defer (--all-pending|--feature-id <id>) --reason "<reason>" [--defer-group <group>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py resume (--all|--defer-group <group>)
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state --phase <phase> [--plan-path <path>] [--next-action <action>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-workflow-task <id> completed
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py clear-workflow-state
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> --complexity-score <score> --selected-model <model> --workflow-path <path>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete-feature-ai-metrics <feature_id>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py auto-checkpoint
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py git-auto-preflight [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py entropy-check [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py entropy-fix [--safe] [--apply] [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py sync-runtime-context [--source <session_start|manual>] [--quiet] [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan [--plan-path <path>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-planning <feature_id> [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-feature <name> <test_steps...>
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py undo
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py reset [--force]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-update --category <category> --summary "<summary>" [--details "<details>"] [--feature-id <id>] [--bug-id <BUG-ID>] [--role <role>] [--owner "<owner>"] [--source <source>] [--next-action "<next>"] [--ref <token> ...]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-updates [--limit <n>]  (--limit 0 = all)
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-owner <feature_id> <architecture|coding|testing> "<owner|none>"
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-bug --description "<desc>" [--status <status>] [--priority <high|medium|low>] [--category <bug|technical_debt>]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py update-bug --bug-id "BUG-XXX" [--status <status>] [--root-cause "<cause>"] [--fix-summary "<summary>"]
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py list-bugs
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py remove-bug "BUG-XXX"
```

### Workspace Entropy (`entropy-check` / `entropy-fix`)

`entropy-check` inspects workspace entropy and emits a tri-state cleanup decision
without mutating anything. `entropy-fix` applies only the safe (green) cleanup
actions it derives from the same report.

Usage:

```bash
prog entropy-check [--json]
prog entropy-fix [--safe] [--apply] [--json]
```

Green / yellow / red policy:

- Green (safe): tracker-state file edits (classified as `auto_commit` in the report;
  auto-commit action is reserved for a future iteration) and local branches that are
  merged, not current, and not checked out in a worktree.
  `entropy-fix --safe` deletes those merged branches with `git branch -d`.
- Yellow (quarantine): non-tracker source edits. Reported only; never deleted or
  reverted. `--apply` is reserved for opting into yellow handling.
- Red (block): deletion of non-tracker-state files. `entropy-check` reports it and
  `entropy-fix` refuses to act, exiting non-zero with a `blocked` status.

No-destructive-action guarantee: `entropy-check` never mutates the workspace.
`entropy-fix` performs at most safe-delete of merged branches (`git branch -d`,
which itself refuses unmerged branches); it never force-deletes, never touches
working-tree files, and never reverts source edits.

Example JSON output (`entropy-check --json`):

```json
{
  "status": "ok",
  "decision": "safe_fix_available",
  "dirty_changes": {
    "auto_commit": ["docs/progress-tracker/state/progress.json"],
    "quarantine": ["hooks/scripts/foo.py"],
    "block": []
  },
  "branches": {"delete_local": ["f21"], "review": ["old-topic"], "keep": ["main"]},
  "routes": {"repair": [], "block": []},
  "worktrees": {"prune": false, "block": []}
}
```

### Project Memory CLI

Global scope override (recommended in monorepos):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py --project-root plugins/<name> read
```

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py read
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py append --payload-json '<object>'
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py batch-upsert --payload-json '<array>' --sync-meta-json '<object>'
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py register-rejections --payload-json '<array>' --sync-id '<sync_id>'
```
<!-- END:GENERATED:PROG_COMMANDS -->

## Drift Prevention P0 Status

For a clear done/pending matrix across drift-prevention and low-learning-cost plans, see:
`docs/DRIFT_PREVENTION_P0_STATUS.md`.

## Architecture

### Commands vs Skills

The plugin follows a **Commands → Skills** architecture:

| Component | Role | Description |
|-----------|------|-------------|
| **Commands** | Entry points | Thin layer that invokes skills |
| **Skills** | Logic | Reusable knowledge with business logic |
| **Hooks** | Events | SessionStart detects incomplete work |
| **Scripts** | State | Python script manages JSON/MD files |

### Skills (11 total)

1. **feature-breakdown** - Analyzes goals, creates feature lists
2. **progress-status** - Displays status and statistics
3. **feature-implement** - Orchestrates Superpowers workflow with complexity assessment
4. **feature-complete** - Validates workflow, runs tests, commits, updates state
5. **progress-recovery** - Auto-detects incomplete work, provides recovery options
6. **architectural-planning** - Coordinates architecture design and stack selection
7. **bug-fix** - Systematic bug triage, scheduling, and fixing workflow
8. **git-auto** - Intelligent Git automation: branch, commit, push, PR creation with smart decision making
9. **progress-management** - Workflow state operations, undo, reset
10. **feature-implement-simple** - Haiku-mode direct TDD for simple features
11. **feature-implement-complex** - Opus-mode full design/planning/execution for complex features

### Progress Manager Commands

Progress Manager command reference is generated from `docs/PROG_COMMANDS.md` into the Commands section above.  
Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/generate_prog_docs.py --write` after editing the source file.

### Progress Files

Stored in your project's `docs/progress-tracker/state/` directory:

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
      "completed": false,
      "ai_metrics": {
        "complexity_score": 18,
        "complexity_bucket": "standard",
        "selected_model": "sonnet",
        "workflow_path": "plan_execute",
        "started_at": "2026-02-11T10:00:00Z",
        "finished_at": "2026-02-11T10:08:30Z",
        "duration_seconds": 510
      }
    }
  ],
  "current_feature_id": 2
}
```

**checkpoints.json** - Lightweight auto-checkpoint snapshots:
```json
{
  "last_checkpoint_at": "2026-02-11T10:30:00Z",
  "max_entries": 50,
  "entries": [
    {
      "timestamp": "2026-02-11T10:30:00Z",
      "feature_id": 2,
      "feature_name": "Registration API",
      "phase": "execution",
      "plan_path": "docs/plans/feature-2-registration-api.md",
      "current_task": 2,
      "total_tasks": 5,
      "reason": "auto_interval"
    }
  ]
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

### Plan Artifacts

- Architecture master plan: `docs/progress-tracker/architecture/architecture.md`
- Feature execution plans: `docs/plans/feature-*.md`
- `workflow_state.plan_path` must always reference `docs/plans/*.md`

## Workflow Example

```bash
# 1. Start a new project
/prog-init Build a TODO app with CRUD operations

# → Creates feature list: database, API, frontend, etc.

# 2. Check status
/prog

# → Shows 0/5 complete

# 3. Start first feature (auto-invokes Superpowers workflow)
/prog-next

╔════════════════════════════════════════════════════════╗
║  🚀 Starting Feature Implementation                    ║
╚════════════════════════════════════════════════════════╝

**Feature**: User Database Model
**Progress**: Feature 1/5 in project

**Acceptance Test Steps**:
✓ Run migrations successfully
✓ Verify users table exists
✓ Test user creation

**Complexity Assessment**: Simple
**Selected Workflow**: Direct TDD

---

⏳ Using superpowers:test-driven-development skill...
[RED-GREEN-REFACTOR cycle executes]

✅ Implementation Complete

**Next Step**: Run `/prog-done` to finalize

# 4. Complete and commit
/prog-done

## ✅ All Tests Passed!

Feature "User Database Model" has been successfully verified.

### Creating Git Commit
feat: complete user database model

[Commit created: abc1234]

**Remaining features**: 4

# [Session closes or restarts]

# 5. SessionStart hook detects incomplete work
╔════════════════════════════════════════════════════════╗
║  📋 Progress Tracker: Unfinished Work Detected        ║
╚════════════════════════════════════════════════════════╝

**Feature**: Registration API (ID: 2)
**Status**: execution - 2/5 tasks completed
**Plan**: docs/plans/2024-01-24-registration-api.md

### Recovery Options
1️⃣ Resume from Task 3 (Recommended)
2️⃣ Restart Execution
3️⃣ Re-create Plan
4️⃣ Skip Feature

# 6. Resume and continue
# (Select option 1 - automatic resume)

Resuming from task 3...
Progress: [████░░░░] 40% - Task 3/5
```

## Bug Tracking Example

```bash
# Report a bug with quick verification
/prog-fix "Users are logged out after refresh"

# View backlog and pick a bug to fix
/prog-fix

# Resume a specific bug by ID
/prog-fix BUG-001
```

**Bug lifecycle**: pending_investigation → investigating → confirmed → fixing → fixed (or false_positive)

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
/prog-next               # Progress Tracker selects feature
                         # → Assesses complexity
                         # → Invokes superpowers:writing-plans
                         # → Invokes superpowers:subagent-driven-development
                         # → Each task: TDD + review + commit
/prog-done               # Progress Tracker runs acceptance tests
                         # → Creates feature commit
                         # → Updates progress.json
```

**Alternative: feature-dev plugin**

The legacy integration with feature-dev is still supported:
- Better for **legacy codebases** (has code-explorer for deep analysis)
- Superpowers is better for **new projects** (stronger process enforcement)

To use feature-dev instead, modify `skills/feature-implement/SKILL.md` to invoke `/feature-dev` as before.

## Progress UI Web Dashboard

The Progress Tracker includes a built-in web interface for visual progress tracking and interactive task management.

### Launching Progress UI

```bash
/prog-ui
```

This command will:
1. Start a local HTTP server (auto-detects ports 3737-3747)
2. Open your default browser to the dashboard
3. Display all progress tracking documents

**Security**: The server only binds to `127.0.0.1` (localhost) and is not accessible from the network.

### Features

**📊 Visual Progress Tracking**
- Real-time display of all progress documents (`docs/progress-tracker/state/*.md`)
- Six-state checkbox system with intuitive icons:
  - ☐ Pending (todo)
  - 🔄 In Progress (doing)
  - ☑ Done (completed)
  - ➖ Skipped (not needed)
  - ❌ Blocked (waiting)
  - ❓ Unclear (needs clarification)

**✏️ Interactive Editing**
- Click checkboxes to cycle through states
- Right-click for quick status menu
- Keyboard shortcuts for power users:
  - `1-6`: Set specific status
  - `j/k`: Navigate between items
  - `Ctrl+S`: Manual save
  - `?`: Show help

**🔄 Auto-Sync & Conflict Resolution**
- Auto-save after checkbox changes
- Background polling (10-30 seconds)
- Refresh on window focus
- Smart conflict detection with merge UI

**📁 Multi-Document Support**
- Switch between progress files
- Prioritized file listing (progress.md first)
- No duplicate paths

**🔒 Safety & Reliability**
- Write whitelist (only `docs/progress-tracker/**/*.md` files)
- Path traversal protection
- Revision-based concurrency control
- Origin validation (CORS protection)

### Use Cases

**During Development**
```bash
# Start your feature work
/prog-next

# Open Progress UI in another window
/prog-ui

# Track your progress visually while implementing
# Mark tasks as you complete them
```

**Project Review**
```bash
# See overall project status at a glance
/prog-ui

# Review what's done, what's blocked, what's pending
# Update statuses interactively
```

**Team Collaboration**
```bash
# Share your screen with Progress UI open
# Walk through progress with stakeholders
# Update statuses during standup meetings
```

### Technical Details

**Server**:
- Python HTTP server with RESTful API
- Endpoints: `/api/files`, `/api/file`, `/api/checkbox`
- JSON responses with proper content types
- Automatic port detection and fallback

**Frontend**:
- Single-file HTML with inline CSS/JS
- No external dependencies
- Works in all modern browsers
- Responsive design

**Testing**:
- Comprehensive pytest suite
- Path security tests
- Concurrency control tests
- Six-state checkbox parsing tests

## Quick Start

Get started with Progress Tracker in 3 steps:

```bash
# 1. Initialize your project
/prog-init Build a user authentication system

# 2. Start the first feature
/prog-next

# 3. Complete and commit
/prog-done
```

**That's it!** The plugin will:
- ✅ Break down your goal into features
- ✅ Guide you through TDD implementation
- ✅ Run acceptance tests
- ✅ Create clean Git commits
- ✅ Remember your progress between sessions

## Directory Structure

```
plugins/progress-tracker/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   ├── prog.md
│   ├── prog-init.md
│   ├── prog-plan.md
│   ├── prog-next.md
│   ├── prog-fix.md
│   ├── prog-done.md
│   ├── prog-undo.md
│   └── prog-reset.md
├── skills/
│   ├── architectural-planning/
│   │   └── SKILL.md
│   ├── bug-fix/
│   │   └── SKILL.md
│   ├── feature-breakdown/
│   │   └── SKILL.md
│   ├── progress-status/
│   │   └── SKILL.md
│   ├── feature-implement/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── complexity-assessment.md
│   ├── feature-implement-simple/
│   │   └── SKILL.md
│   ├── feature-implement-complex/
│   │   └── SKILL.md
│   ├── feature-complete/
│   │   └── SKILL.md
│   ├── git-auto/
│   │   └── SKILL.md
│   ├── progress-management/
│   │   └── SKILL.md
│   └── progress-recovery/
│       └── SKILL.md
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       └── progress_manager.py
├── .gitignore
├── LICENSE
├── plugin.md
├── README.md
└── readme-zh.md
```

## Session Recovery

The plugin automatically detects incomplete work when you open a new session and provides intelligent recovery options.

**SessionStart Hook** checks:
1. Does `docs/progress-tracker/state/progress.json` exist?
2. Are there uncompleted features?
3. Is there a `current_feature_id` set?
4. What is the `workflow_state.phase`?
5. Does the current session branch/worktree match the last recorded execution context?
6. Are there uncommitted Git changes?

**UserPromptSubmit Hook**:
- Triggers lightweight `auto-checkpoint` every 30 minutes during active feature work
- Writes snapshots (phase/task/branch/worktree) to `docs/progress-tracker/state/checkpoints.json`
- Never creates git commits

When a mismatch is detected (for example, feature implementation happened in a worktree and you resume in the main checkout), recovery/status output shows a strong warning with the recorded branch/worktree path before recommending next actions.

### Auto-Recovery Scenarios

**Scenario A: Implementation Complete**
```
✅ Implementation appears complete!

All tasks in the plan have been executed and committed.

**Recommended Action**: Run `/prog-done` to finalize
```

**Scenario B: Almost Complete (80%+)**
```
⚙️ Almost complete: 4/5 tasks done

Resuming automatically in 3 seconds... (type 'stop' to cancel)
```

**Scenario C: Mid-Implementation**
```
╔════════════════════════════════════════════════════════╗
║  📋 Progress Tracker: Unfinished Work Detected        ║
╚════════════════════════════════════════════════════════╝

**Feature**: Registration API (ID: 2)
**Status**: execution - 2/5 tasks completed
**Plan**: docs/plans/2024-01-24-registration-api.md

### Recovery Options
1️⃣ Resume from Task 3 (Recommended)
2️⃣ Restart Execution
3️⃣ Re-create Plan
4️⃣ Skip Feature
```

### Workflow State Tracking

The plugin tracks detailed workflow state for accurate recovery:

```json
{
  "current_feature_id": 2,
  "workflow_state": {
    "phase": "execution",
    "plan_path": "docs/plans/2024-01-24-registration-api.md",
    "completed_tasks": [1, 2],
    "current_task": 3,
    "total_tasks": 5,
    "next_action": "verify_and_complete"
  }
}
```

**Phase values**:
- `design_complete` - Brainstorming done, ready for planning
- `planning_complete` - Plan created, ready for execution
- `execution` - Currently executing tasks
- `execution_complete` - All tasks done, ready for verification

## Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Test-Driven** | Features only complete after passing tests |
| **Git-Native** | Each feature commits, history is progress |
| **External State** | Progress in files, survives context loss |
| **Clear Separation** | Commands → Skills → Scripts |
| **Professional** | Leverages Superpowers for implementation |
| **Recoverable** | Session resumption with context |
| **Explicit Invocation** | CRITICAL blocks ensure skills actually execute |
| **Rich Feedback** | Progress bars, phase banners, next steps |
| **Convention over Config** | Smart defaults, no configuration needed |

## What's New (v2.0)

### P0 Core Reliability Improvements

1. **Skill Invocation Reliability**
   - `<CRITICAL>` blocks force explicit Skill tool calls
   - No more "describing skills" - skills are actually invoked
   - Complete examples for each skill invocation

2. **Workflow State Persistence**
   - New `set-workflow-state`, `update-workflow-task`, `clear-workflow-state` commands
   - JSON-formatted recovery information from `check` command
   - Smart recovery action recommendations

3. **Enhanced Session Recovery**
   - Auto-recovery for clear cases (execution_complete, 80%+ done)
   - Recovery banner with phase-based options
   - Error handling for missing/corrupted state

4. **User-Friendly Progress Feedback**
   - Feature start banner with complexity assessment
   - Progress bars: `[████░░] 33% - Phase 1/3 done`
   - Phase transition indicators
   - Completion summaries with next steps

5. **Workflow Completion Validation**
   - `/prog-done` validates workflow_state before running tests
   - Prevents completion without going through Superpowers workflow
   - Guides recovery if workflow is incomplete

---

## Changelog

### v1.2.0 (2025-01-29)

#### 新增命令
- ✅ `/prog-plan` - 架构规划命令
  - 技术栈推荐
  - 系统架构设计
  - 架构决策记录 (`docs/progress-tracker/architecture/architecture.md`)
  - 与 feature breakdown 的集成指导
- ✅ `/prog-fix` - Bug 管理命令
  - Bug 报告与快速验证 (30秒)
  - 智能调度到功能时间线
  - Bug 生命周期追踪 (pending_investigation → investigating → confirmed → fixing → fixed)
  - 集成 Superpowers: systematic-debugging, test-driven-development, code-reviewer

#### 新增技能
- ✅ `architectural-planning` - 协调架构设计
- ✅ `bug-fix` - 系统化 Bug 处理
  - 三阶段工作流：验证 → 调度 → 修复
  - Bug CRUD 操作 (add-bug, update-bug, list-bugs, remove-bug)
  - 优先级计算 (基于严重性和范围)
- ✅ `progress-management` - 工作流状态操作

#### 功能增强
- 更新 progress_manager.py 添加 Bug 管理命令
- 添加 Bug 追踪数据结构到 progress.json
- 渐进式披露：bug-fix skill 包含 workflow.md, integration.md, session.md 示例
- 命令总数从 6 增加到 8
- 技能总数从 5 增加到 8

### v1.1.0 (2025-01-25)

#### 规范完善
- ✅ 添加 `STANDARDS.md`：定义共享的 frontmatter schema 约定
- ✅ 添加 `CHANGELOG.md`：完整的版本历史记录
- ✅ 修复所有 7 个 commands 的 frontmatter，添加必填字段
  - 新增字段：`version`, `scope`, `inputs`, `outputs`, `evidence`, `references`

#### 测试覆盖
- ✅ 新增 `tests/` 目录，包含 pytest 测试套件
  - `test_progress_manager.py` - 核心功能测试
  - `test_workflow_state.py` - 工作流状态测试
  - `test_git_integration.py` - Git 集成测试
  - `conftest.py` - 测试配置和 fixtures

#### 功能增强
- 更新 `plugin.json` hooks 配置
- 增强进度管理器的命令行接口

### v1.0.0
- 初始版本，包含完整的进度追踪功能

## License

MIT
