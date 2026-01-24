# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.1.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.1.0
[1.0.0]: https://github.com/siunin/Claude-Plugins/releases/tag/v1.0.0
