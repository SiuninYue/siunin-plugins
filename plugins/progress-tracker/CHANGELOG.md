# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.28] — 2026-06-14

### Changed
- Finalized the F28 facade cleanup round:
  - removed the remaining dead `progress_manager`-availability branches in `progress_ui_server.py`
  - updated `wf_auto_driver.py` docs to match the direct write-back path
  - deduplicated plan-path constants and fixed the `Callable` typing import in `progress_manager.py`

### Fixed
- `/prog done` integration coverage now resolves `test_reports` relative to the test state file, preventing cwd-dependent leakage into the repository root during isolated test runs.
- Refreshed the root marketplace parent-tracker projection after the F28 closeout so the published repo state reflects `27/29` completed features on `main`.

## [1.6.18] — 2026-04-28

### Fixed
- **Standard path phase stuck**: `feature-implement` Step 4B (complexity 16-25) was missing explicit `set-workflow-state --phase "execution_complete"` command, causing phase to remain at `planning:approved` after all implementation work completed. Added explicit phase transition commands at each gate.
- **Parent dispatch sync**: `prog next` now registers dispatched child projects in `active_routes` and refreshes `linked_snapshot`, so `/prog` at parent level shows accurate child status.

## [Unreleased]

### Changed
- **BREAKING**: Plan paths now only accept `docs/plans/` (Superpowers standard). Legacy `docs/progress-tracker/plans/` paths are no longer supported. Users with plans in that location should move them to `docs/plans/`.

### Removed
- Deprecated `prog-launcher` skill and associated files:
  - Removed `skills/prog-launcher/` directory and SKILL.md
  - Removed `tests/test_prog_start_contract.py`
  - Updated `quick_validate.py` to remove prog-start contract checks
  - Updated `tests/test_feature_implement_workspace_gate_contract.py` to remove prog-start references
  - Updated `tests/test_quick_validate.py` to remove prog-start test cases
  - Rationale: `/prog-start` workflow has been superseded by integrated `/prog-next` command flow

### Fixed
- Documentation consistency issues:
  - Unified command descriptions across `commands/*.md`, `help.md`, and `docs/PROG_COMMANDS.md`
  - `prog-sync`: Added missing "with batch confirmation" and "project" keywords
  - `prog-update`: Simplified to match command file description
  - `prog-undo`: Changed "revert" to "Undo" for consistency
  - Regenerated documentation using `generate_prog_docs.py --write`

### Changed
- Skill version alignment and description optimization:
  - `feature-implement-simple`: Upgraded from v1.0.0 to v1.1.0 to align with `feature-implement-complex`
  - `feature-implement`: Simplified description (removed technical implementation details)
  - `bug-fix`: Simplified description (removed "smart scheduling" jargon)
  - `testing-standards`: Added `model: sonnet` field

- Command version synchronization with referenced skills:
  - `prog-next`: v1.0.0 → v3.2.0 (aligned with `feature-implement`)
  - `prog-done`: v1.0.0 → v2.2.0 (aligned with `feature-complete`)
  - `prog`: v1.0.0 → v2.0.0 (aligned with `progress-status`)

### Technical Debt
- Removed all prog-launcher related validation logic and tests
- Standardized command version management to track skill evolution

<!-- START_F19_MANAGED_BLOCK -->
### AI Traceable Changes

- **[2026-05-21] [20260521-pm-modularize-a7d2](docs/changes/20260521-pm-modularize-a7d2.md)**: 拆分 progress_manager.py 为 7 个子模块（Method A，零测试改动） (fixes: F18)
- **[2026-05-26] [20260526-pm-compress-below-10k](docs/changes/20260526-pm-compress-below-10k.md)**: 进一步提取文档、缺陷与工作区校验模块，使主入口降至 10,000 行以下 (fixes: F18)
- **[2026-06-03] [20260603-boundary-fix-r0-c4f2](docs/changes/20260603-boundary-fix-r0.md)**: Fix \b regex bug causing all local-scope imports to evade boundary detection; add allowlist for known violations (fixes: scripts/check_pm_boundary.sh: change \\b to \b in reverse-import regex pattern, scripts/.pm_boundary_allowlist: add allowlist for 4 files scheduled for Final round cleanup)
- **[2026-06-03] [20260603-f20-post-review-cleanup](docs/changes/20260603-f20-post-review-cleanup.md)**: Post-review cleanup for F20: align allowlist docs, reduce status service injection, replace collect_git_context facade probing with explicit injection, and add module map (fixes: Update R0 change record for file-scoped allowlist behavior, Reduce StatusCommandServices to callbacks that still need facade state, Remove sys.modules progress_manager probe from git_utils.collect_git_context, Add explicit collect_git_context_fn injection for runtime/execution context builders, Create progress-manager-module-map.md navigation artifact)
- **[2026-06-03] [20260603-summary-status-r1-f20a](docs/changes/20260603-summary-status-r1.md)**: Round 1: Extract status/summary read path to summary_projector.py and status_commands.py (fixes: Create summary_projector.py with 20 status summary projection functions, Create status_commands.py with 4 status display functions (plus StatusCommandServices dataclass), Add facade wrappers in progress_manager.py for all 24 extracted functions, Wire callbacks via _make_status_command_services() factory to avoid reverse dependencies)
- **[2026-06-04] [20260604-f23-work-item-selection-round4](docs/changes/20260604-f23-work-item-selection-round4.md)**: Round 4: Extract work-item selection and next-feature command orchestration from the progress_manager facade. (fixes: Create work_item_selector.py for get_next_feature, child/root dispatch, and unified work-item priority selection, Create next_feature_commands.py for next-feature orchestration, output rendering, task activation, and active-route bookkeeping, Add progress_manager.py wrappers marked is_wrapper = True, Update progress-manager-module-map.md with Round 4 ownership)
- **[2026-06-04] [20260604-feature-activation-f22a](docs/changes/20260604-feature-activation-f22a.md)**: Round 3: Extract feature activation and stage commands to feature_commands.py (fixes: Create feature_commands.py with FeatureCommandsServices callback injection, Extract set_current and set_development_stage from progress_manager.py, Add thin facade wrappers marked is_wrapper=True in progress_manager.py)
- **[2026-06-04] [20260604-readiness-validator-r2](docs/changes/20260604-readiness-validator-r2.md)**: Round 2: Extract readiness validation cluster to readiness_validator.py (fixes: Create readiness_validator.py with ReadinessValidatorServices dataclass and 8 extracted functions, Add facade wrappers in progress_manager.py for all 7 public/command functions (is_wrapper = True), Wire callbacks via _make_readiness_validator_services() factory; inject _evaluate_planning_readiness as callback, Net reduction ~234 lines in progress_manager.py (8997/10000))
- **[2026-06-05] [20260604-completion-flow-r5](docs/changes/20260604-completion-flow-r5.md)**: Round 5: Extract completion pipeline (cmd_done, complete_feature, acceptance tests, done preflight, state finalization) to completion_flow.py. (fixes: Create completion_flow.py with CompletionFlowServices dataclass and 19 extracted functions, Add _make_completion_flow_services() factory in progress_manager.py, Add facade wrappers marked is_wrapper=True for all extracted functions, Re-import FINISH_PENDING_STATE and _is_project_fully_completed from completion_flow, Write 8 RED-then-GREEN contract tests in test_completion_flow_contract.py, Update patch targets in test_cmd_done_cleanup_integration.py and test_auto_state_commit.py, progress_manager.py reduced from 8122 to 7121 lines (-1001))
- **[2026-06-16] [20260616-f25-workspace-entropy-manager](docs/changes/20260616-workspace-entropy-manager.md)**: Add workspace entropy detection and safe-fix engine: classify dirty changes/branches, add entropy-check and entropy-fix commands, integrate entropy preflight into next_feature. (fixes: Create workspace_entropy.py with classify_dirty_entries, classify_branches, build_entropy_report, entropy_check_command, entropy_fix_command, run_safe_entropy_preflight, Add entropy-check and entropy-fix CLI commands with green/yellow/red policy, Add entropy_preflight_fn callback to NextFeatureCommandServices; next_feature blocks on red entropy, Add EntropyPreflightResult class for structured preflight results)
- **[2026-06-16] [20260616-traceability-rollback-f19a](docs/changes/20260616-traceability-rollback-f19a.md)**: AI 可追溯与可回退机制 v1：变更记录 + 自动守卫 + 回退 SOP (fixes: F19)
- **[2026-06-16] [20260616-traceability-rollback-fix-a2d9](docs/changes/20260616-traceability-rollback-fix-a2d9.md)**: 修复 rollback_helper 变量引用错误并进行 done-gate 状态晋升 (fixes: F19)
- **[2026-06-16] [20260616-traceability-rollback-sophisticate-c7a8](docs/changes/20260616-traceability-rollback-sophisticate-c7a8.md)**: 增强回退机制：实现物理归档检测与跨分支 Git 检索 (fixes: F19)
<!-- END_F19_MANAGED_BLOCK -->

## [1.6.13] - 2026-03-10

### Fixed
- AI command misinterpretation bug in skill documentation:
  - Fixed issue where command references in parentheses like (`/prog`, `/prog next`) were being misinterpreted by AI as executable commands
  - Updated `feature-complete`, `feature-implement`, `superpowers-integration`, and `testing-standards` skills to use descriptive text format instead
  - Root cause: Parenthetical command references triggered AI command execution during skill processing

### Added
- Structured progress update stream in `progress.json`:
  - new top-level `updates[]` collection
  - new CLI commands: `add-update`, `list-updates`
- Role owner support for features:
  - `features[].owners` with fixed roles `architecture|coding|testing`
  - new CLI command: `set-feature-owner`
- New `/prog-update` command + `progress-update` skill contract for recording structured updates from command layer.

### Changed
- `load_progress_json`/`save_progress_json` now backfill schema defaults for legacy files (owners + updates) without breaking existing state.
- `/prog` status and generated `progress.md` now include role owner summary and latest updates section.

## [1.6.12] - 2026-03-05

### Fixed
- `prog-start` contract and anti-regression hardening:
  - `/prog-start` now consistently routes to `progress-tracker:prog-launcher`
  - removed remaining `/prog start|done|next` command text from runtime/UI critical paths in favor of hyphenated forms
  - added `quick_validate` checks to block `prog-start` alias regression (`skills/prog-start/` reintroduction or deprecated command binding)
- Progress UI next-step actions now consistently return hyphenated commands for active and pending states (`/prog-start`, `/prog-done`, `/prog-next`).
- Restored `quick_validate` compatibility with current `bug-fix` skill command style (`plugins/progress-tracker/prog ...`).
- Tightened git hash validation to reject leading/trailing whitespace inputs.

## [1.6.10] - 2026-03-04

### Fixed
- Plan path unification with Superpowers standard:
  - Plans now stored in `docs/plans/` (Superpowers standard) instead of `docs/progress-tracker/plans/`
  - Added legacy fallback support for old plan locations
  - Separated implementation plans (public) from internal state files
- Plan validation now supports both Superpowers and native formats:
  - Supports `## Task 1:` style headings (Superpowers)
  - Supports both English (`**Goal:**`) and Chinese (`**目标:**`) field names
- Updated all tests and documentation to reflect `docs/plans/` path standard

## [1.6.9] - 2026-03-03

### Added
- Progress snapshot archive management in `progress_manager.py`:
  - `list-archives [--limit <n>]` to inspect historical snapshots
  - `restore-archive <archive_id> [--force]` to recover previous progress state

### Changed
- `init --force` now auto-archives existing `progress.json`/`progress.md` before re-initializing.
- `progress-tracker` storage moved to `docs/progress-tracker/` under each target project root:
  - state files now live under `docs/progress-tracker/state/`
  - plans/testing moved to `docs/progress-tracker/plans|testing/`
  - architecture moved to `docs/progress-tracker/architecture/architecture.md`
  - complexity cache moved to `docs/progress-tracker/cache/complexity_cache.json`
- Added strict project scope resolution with global `--project-root` for:
  - `progress_manager.py`
  - `project_memory.py`
  - `progress_ui_server.py`
- Monorepo root now requires explicit `--project-root plugins/<name>` (no implicit guessing).
- One-time migration now moves legacy `.claude/*` and legacy `docs/plans|testing` into the new layout with conflict logging in `docs/progress-tracker/state/migration_log.json`.

## [1.6.8] - 2026-03-03

### Fixed
- Skills and commands now use `prog` entry point instead of `${CLAUDE_PLUGIN_ROOT}`:
  - added `prog` CLI wrapper that auto-locates plugin root directory
  - replaced all `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/` references in SKILL.md files
  - supports both `progress_manager.py` and `project_memory.py` via `prog memory` subcommand
  - ensures commands work correctly from any working directory

## [1.6.7] - 2026-03-03

### Fixed
- Hooks now use wrapper script to handle `CLAUDE_PLUGIN_ROOT` environment variable:
  - added `hooks/run-hook.sh` wrapper that falls back to relative path when env var is not set
  - ensures hooks work correctly regardless of Claude Code's environment variable setup

## [1.6.6] - 2026-03-01

### Fixed
- `prog-start` skill circular reference bug:
  - removed self-referencing `/progress-tracker:prog-start` from skill description to prevent infinite loop
  - corrected command format from `/prog start` to `/prog-start`

### Added
- Worktree-aware progress context tracking in `progress_manager.py`:
  - `runtime_context` (top-level current session snapshot)
  - `workflow_state.execution_context` (last workflow-advance branch/worktree snapshot)
- `sync-runtime-context` CLI command for non-blocking session context persistence.
- Context alignment hints in `check` JSON output (`context_hint`, `last_checkpoint_hint`).
- Checkpoint entries now include branch/worktree + workflow progress metadata.

### Changed
- `save_progress_json` now supports runtime-only writes without touching semantic `updated_at`.
- `/prog` status and `.claude/progress.md` now surface workflow phase/task progress plus execution/runtime context mismatch warnings.
- Progress UI `snapshot` panel now shows newest checkpoints first and includes phase/task/branch/worktree context.
- Progress UI `next` and `plan` panels now show context alignment and workflow progress metadata.
- SessionStart hook now records runtime context after recovery check (without high-frequency `progress.json` writes).

## [1.6.3] - 2026-02-25

### Fixed
- Claude Code plugin manifest compatibility for command loading:
  - removed invalid inline `commands` entry list from `.claude-plugin/plugin.json`
  - switched to standard command auto-discovery (root `commands/` directory)
- Moved command markdown files from deprecated `/.claude-plugin/commands/` layout to plugin-root `/commands/` layout so Claude Code can discover all commands consistently.

### Changed
- Updated manifest/command contract tests to validate auto-discovery-based command registration.

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
