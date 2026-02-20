# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.2] - 2026-02-19

### Changed
- Upgraded `skills/git-auto/SKILL.md` to `v1.2.0` with a worktree-first decision gate.
- Added explicit worktree output contract to `git-auto` plans:
  - `Workspace Mode`
  - `Worktree Decision Reason`
- Added condition-triggered worktree policy (`MUST/SHOULD/MAY`) using:
  - default-branch dirty-start detection
  - `parallel_pressure`
  - `branch_checked_out_elsewhere`
  - enforcement-mode-aware routing
- Added idempotent worktree reuse rules and explicit delegation boundary to `using-git-worktrees`.
- Reordered `git-auto` workflow to evaluate worktree mode before branch creation, while retaining existing merge gates.

## [1.6.1] - 2026-02-19

### Changed
- Updated `skills/git-auto/SKILL.md` to `v1.1.0` with executable governance rules.
- Added explicit collaboration baseline:
  - trunk-based + short-lived branches
  - Draft PR on first push
  - squash merge as default recommendation
- Added 14-day rolling escalation standard with metric-based transitions:
  - `soft -> hybrid -> hard`
  - numeric thresholds and clean-window de-escalation rules
- Replaced decision tree and scenarios to enforce:
  - branch-before-commit on default branch
  - Draft PR creation for first push
  - merge recommendation gates by sync/CI/review readiness per mode
- Added plan output requirement in `git-auto`:
  - `Enforcement Mode`
  - `Escalation Reason`

## [1.6.0] - 2026-02-18

### Added
- **Progress UI Web Dashboard** (`/prog-ui` command)
  - Single-file HTML interface with inline CSS and JavaScript
  - Real-time progress tracking with checkbox status management
  - Six-state checkbox support: ☐ (pending), 🔄 (in progress), ☑ (done), ➖ (skipped), ❌ (blocked), ❓ (unclear)
  - Multi-document navigation and switching
  - Auto-save with conflict detection and resolution
  - HTTP server with localhost-only binding (ports 3737-3747)
  - Path traversal protection and CORS security
  - Auto-refresh on window focus and periodic polling (10-30s)
  - Keyboard shortcuts: Ctrl+S (save), j/k (navigate), 1-6 (status), ? (help)
  - Context menu for quick status changes
- **Progress UI Backend** (`progress_ui_server.py`)
  - RESTful API endpoints: `/api/files`, `/api/file`, `/api/checkbox`
  - Revision-based concurrency control (base_rev + base_mtime)
  - Write whitelist for `.claude/*.md` files only
  - Dynamic port detection with automatic fallback
  - JSON response format with proper Content-Type headers
- **Testing Infrastructure** for Progress UI
  - Comprehensive pytest suite in `tests/test_progress_ui.py`
  - Path security validation tests
  - Concurrency control tests
  - Six-state checkbox parsing tests
  - Origin validation and CORS tests

### Changed
- Enhanced file scanning with priority ordering (progress.md first)
- Improved conflict resolution UI with "keep my changes" option
- Status bar indicators for save states (unsaved/saving/saved/conflict)

## [1.5.0] - 2026-02-13

### Added
- Single command-doc source: `docs/PROG_COMMANDS.md`
- Generated help artifact: `docs/PROG_HELP.md`
- Command doc generator: `hooks/scripts/generate_prog_docs.py`
  - `--write` mode to update generated targets
  - `--check` mode to detect documentation drift
- Quick validator: `hooks/scripts/quick_validate.py`
  - Checks bug-fix contract consistency
  - Checks key skill description trigger tokens
  - Checks main-skill word-count threshold
  - Checks generated doc synchronization
- New references to support progressive disclosure:
  - `skills/feature-implement/references/session-playbook.md`
  - `skills/feature-complete/references/verification-playbook.md`
  - `skills/feature-complete/references/session-examples.md`
  - `skills/progress-recovery/references/scenario-playbook.md`
  - `skills/progress-recovery/references/communication-templates.md`
- New tests:
  - `tests/test_generate_prog_docs.py`
  - `tests/test_quick_validate.py`

### Changed
- Fixed `bug-fix` documentation contract:
  - Replaced `superpowers:code-reviewer` with `superpowers:requesting-code-review`
  - Removed deprecated `--commit-hash` examples, aligned to `--fix-summary`
  - Standardized bug-fix CLI examples to `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py`
- Rewrote and slimmed core skills with references-based progressive disclosure:
  - `skills/feature-implement/SKILL.md`
  - `skills/feature-complete/SKILL.md`
  - `skills/progress-recovery/SKILL.md`
- Strengthened trigger-focused descriptions:
  - `skills/feature-breakdown/SKILL.md`
  - `skills/architectural-planning/SKILL.md`
  - `skills/progress-management/SKILL.md`
  - `skills/progress-recovery/SKILL.md`
- Standardized user-facing bug command spelling to `/prog-fix` in active docs.
- Updated standards to enforce generated command-doc flow from `docs/PROG_COMMANDS.md`.

## [1.4.0] - 2026-02-11

### Added
- `progress_manager.py validate-plan` command to validate:
  - `workflow_state.plan_path` shape (`docs/plans/*.md`)
  - Minimum plan sections (`Tasks`, `Acceptance Mapping`, `Risks`)
- Plan path validation helper in `progress_manager.py` with:
  - Relative-path enforcement
  - `docs/plans/` prefix enforcement
  - Optional existence checks
- Recovery metadata from `check` output:
  - `plan_path_valid`
  - `plan_path_error`

### Changed
- Standardized workflow `plan_path` contract on `docs/plans/*.md` (no migration required).
- Updated skills to reduce planning ambiguity and align downstream execution:
  - `architectural-planning`
  - `feature-breakdown`
  - `feature-implement`
  - `feature-implement-complex`
  - `progress-recovery`
  - `feature-complete`
- Updated `STANDARDS.md` with:
  - Plan artifact boundaries
  - Minimum feature plan contract
- Updated docs (`README.md`, `readme-zh.md`) to reflect:
  - `validate-plan` command
  - `docs/plans/*.md` path policy

## [1.3.0] - 2026-02-11

### Added
- **Deterministic model routing** for `/prog next`
  - Explicit delegation to `feature-implement-simple` (haiku) and `feature-implement-complex` (opus)
  - Standard path remains coordinator-driven (sonnet)
- **Two new implementation skills**
  - `feature-implement-simple`
  - `feature-implement-complex`
- **Complexity reference doc**
  - `skills/feature-implement/references/complexity-assessment.md`
- **Lightweight AI metrics** in `features[].ai_metrics`
  - `complexity_score`, `complexity_bucket`, `selected_model`, `workflow_path`
  - `started_at`, `finished_at`, `duration_seconds`
- **Lightweight auto-checkpoints**
  - `.claude/checkpoints.json`
  - `progress_manager.py auto-checkpoint`
  - `UserPromptSubmit` hook integration
- **Bug category support**
  - `bugs[].category` with `bug|technical_debt`
  - `add-bug --category ...`

### Changed
- Updated `feature-implement` skill to v3.0.0 with explicit delegation and fallback strategy.
- Updated `feature-complete` skill to include optional quality-gate checks and technical debt recording flow.
- Updated `progress-status` skill to include lightweight AI metric reporting guidance.
- Expanded `progress_manager.py` CLI with:
  - `set-feature-ai-metrics`
  - `complete-feature-ai-metrics`
  - `auto-checkpoint`
- Updated docs (`README.md`, `readme-zh.md`, `STANDARDS.md`) for AI-first schema and workflow behavior.

## [1.2.0] - 2025-01-29

### Added
- **`/prog plan` command** for architectural planning
  - Technology stack recommendations
  - System architecture design
  - Architectural decision records (`.claude/architecture.md`)
  - Integration guidance for feature breakdown
- **`/prog fix` command** for bug management
  - Bug reporting with quick verification (30s)
  - Smart scheduling into feature timeline
  - Bug lifecycle tracking (pending_investigation → investigating → confirmed → fixing → fixed)
  - Integration with Superpowers: systematic-debugging, test-driven-development, code-reviewer
- **`architectural-planning` skill** for coordinated architecture design
- **`bug-fix` skill** for systematic bug handling
  - Three-phase workflow: verification → scheduling → fixing
  - Bug CRUD operations in progress_manager.py (add-bug, update-bug, list-bugs, remove-bug)
  - Priority calculation (high/medium/low) based on severity and scope
- **`progress-management` skill** for workflow state operations

### Changed
- Updated total commands from 6 to 8
- Updated total skills from 5 to 8
- Improved command documentation consistency across all files

### Technical Improvements
- Added bug tracking data structure to progress.json
- Enhanced progress_manager.py with bug management commands
- Progressive disclosure: bug-fix skill includes workflow.md, integration.md, and session.md examples

## [1.1.0] - 2025-01-25

### Added
- **Environment variable fallback mechanism** in `progress_manager.py`
  - `get_plugin_root()` function with multi-layer fallback
  - `validate_plugin_root()` function for path validation
  - Diagnostic logging for troubleshooting
- **Comprehensive test suite** with pytest
  - `tests/test_progress_manager.py` - 16 core functionality tests
  - `tests/test_git_integration.py` - 11 Git operation tests
  - `tests/test_workflow_state.py` - 10 workflow state machine tests
  - Shared fixtures in `tests/conftest.py`
  - Test fixtures for sample data
- **Test coverage** targeting 80%+ for core functionality

### Changed
- **Model selection optimization** for ~30% API cost reduction:
  - `progress-management/SKILL.md`: opus → sonnet (undo/reset are simple operations)
  - `progress-recovery/SKILL.md`: haiku → sonnet (recovery needs context analysis)
  - Updated `STANDARDS.md` model selection guide
- **Unified skill reference format** across all commands
  - Changed from `**skill-name**` to `skills/xxx/SKILL.md`
  - Applied to all 6 command files (`prog.md`, `prog-init.md`, `prog-next.md`, `prog-done.md`, `prog-undo.md`, `prog-reset.md`)
  - Improved consistency with Super-Product-Manager plugin

### Fixed
- **P0: Environment variable instability** - `${CLAUDE_PLUGIN_ROOT}` now has robust fallback

### Technical Improvements
- Better error messages for plugin root detection failures
- Enhanced diagnostic output for troubleshooting hook failures
- Testable architecture with clear separation of concerns

## [1.0.0] - 2025-01-XX

### Added
- Initial release of Progress Tracker plugin
- Feature-based progress tracking system
- Test-driven status updates
- Git integration for automatic commits
- Session recovery with SessionStart hook
- 6 core commands: `/prog`, `/prog init`, `/prog next`, `/prog done`, `/prog undo`, `/prog reset`
- 5 skills: feature-breakdown, feature-complete, feature-implement, progress-management, progress-recovery, progress-status
- External state persistence via `.claude/progress.json`
- Progress markdown rendering at `.claude/progress.md`
- Python script for core state management
- Undo capability with git revert support
- Workflow state tracking for complex implementations
- Integration with Superpowers plugin for TDD workflows

### Documentation
- English README.md
- Chinese readme-zh.md
- plugin.md with installation and quick start guide
- LICENSE (MIT)

[1.6.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.6.0
[1.5.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.5.0
[1.4.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.4.0
[1.3.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.3.0
[1.2.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.2.0
[1.1.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.1.0
[1.0.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.0.0
