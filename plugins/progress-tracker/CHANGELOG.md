# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.3.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.3.0
[1.1.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.1.0
[1.0.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.0.0
