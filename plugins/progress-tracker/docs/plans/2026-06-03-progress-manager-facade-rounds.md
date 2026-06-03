# progress_manager Facade Convergence Plan

> **For agentic workers:** This is the canonical execution plan for the next stage of `progress_manager.py` optimization. Do not treat `progress.json` as the full design document; it should hold only a concise pointer back to this plan.

**Goal:** Continue shrinking `progress_manager.py` into a stable facade that owns parser wiring, dispatch, and compatibility wrappers only, while moving remaining business logic into focused collaborator modules without changing command semantics.

**Architecture:** Preserve `progress_manager.py` as the only stable public facade. New or expanded collaborator modules own real implementation. Cross-module access must use explicit parameters or callback injection. No submodule may reverse-import `progress_manager`.

**Tech Stack:** Python 3, argparse, pytest, existing `prog_paths.py`, `state_io.py`, `route_*`, `git_utils.py`, `worktree_handler.py`, and the current progress-tracker validation scripts.

**Plan path:** `docs/plans/2026-06-03-progress-manager-facade-rounds.md`

**Working directory for all commands:** `/Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker`

## Goals

- Keep `progress_manager.py` as the single stable facade for CLI entrypoints and backward-compatible test imports.
- Stop adding new business logic to `progress_manager.py`.
- Extract remaining high-volume logic in bounded rounds, one responsibility cluster at a time.
- Strengthen enforcement so reverse imports to `progress_manager` are actually detected.
- Make future AI sessions able to answer three questions cheaply:
  - what module owns this behavior
  - what was already extracted
  - what remains in the facade

## Scope Boundaries

In scope:

- `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- `plugins/progress-tracker/hooks/scripts/*.py` collaborator modules created or expanded by this work
- `plugins/progress-tracker/docs/plans/*.md`
- `plugins/progress-tracker/docs/changes/*`
- `scripts/check_pm_boundary.sh`

Out of scope:

- Changing `/prog-*` command semantics
- Reworking feature lifecycle rules
- Replacing the tracker data model
- Implementing the full F19 mechanism body in this round
- Mass-renaming tests to import leaf modules directly

## Interface Contracts

- `progress_manager.py` remains the only required import surface for callers and tests that already depend on it.
- Public function names and external signatures stay stable unless a dedicated behavior change plan is approved first.
- Every extracted facade-level export in `progress_manager.py` must remain visibly marked as a wrapper via `is_wrapper = True` when compatibility matters.
- New collaborator modules may depend on low-level helpers (`prog_paths`, `state_io`, `Path`, `json`, `datetime`, etc.) but must not import `progress_manager`.
- If a collaborator needs facade-owned behavior, it must receive it through injected functions, not reverse imports.
- `progress.json` stores only a planning pointer:
  - short summary
  - refs to this plan
  - next action
  It must not embed this full phased design.
- `progress-manager-module-map.md` is a future navigation artifact, not a runtime knowledge graph and not the source of truth. Its purpose is to summarize ownership and migration status after extractions begin.

## State Flow

Planning and execution flow:

1. Create or update the canonical plan in `docs/plans/`.
2. Write one concise `spm_planning` update into `progress.json` that points back to the plan.
3. Execute one extraction round at a time.
4. In each round:
   - move one responsibility cluster into one new or expanded module
   - keep facade wrappers in `progress_manager.py`
   - run boundary and docs checks
   - run focused pytest coverage for the touched cluster
   - append one change record into `docs/changes/index.jsonl`
5. After Round 1, create `docs/progress-tracker/architecture/progress-manager-module-map.md` so future sessions can navigate the extracted ownership map.
6. Continue rounds until `progress_manager.py` only contains facade responsibilities.

Planned extraction order:

1. Round 0: fix enforcement guardrails
2. Round 1: summary projection + status rendering
3. Round 2: readiness validation
4. Round 3: feature activation and stage commands
5. Round 4: work-item selection + `next_feature`
6. Round 5: completion flow + done pipeline
7. Round 6: intake and backlog mutation commands
8. Round 7: workflow and reconcile commands
9. Final round: remove remaining reverse imports and compress facade

## Detailed Round Breakdown

### Round 0: Boundary Checker Hardening

- Target file:
  - `scripts/check_pm_boundary.sh`
- Primary work:
  - make the checker fail on local function-scope `import progress_manager`
  - make the checker fail on local function-scope `from progress_manager import ...`
  - verify the checker no longer gives false confidence for reverse-import violations
- Completion signal:
  - the checker reliably blocks reverse imports before any more structural extraction starts

### Round 1: Summary + Status Read Path

- New modules:
  - `summary_projector.py`
  - `status_commands.py`
- Extract into `summary_projector.py`:
  - `_read_json_dict`
  - `_status_source_snapshot`
  - `_status_summary_source_fingerprint`
  - `_load_progress_data_for_summary`
  - `_format_relative_time_for_summary`
  - `_normalize_feature_stage_for_summary`
  - `_stage_label_for_summary`
  - `_determine_next_action_for_summary`
  - `_check_plan_health_for_summary`
  - `_check_risk_blocker_for_summary`
  - `_load_recent_snapshot_for_summary`
  - `_build_status_summary_core`
  - `_extract_projection_source_fingerprint`
  - `_projection_has_required_core_fields`
  - `_projection_needs_rebuild`
  - `_legacy_summary_migration_info`
  - `_resolve_status_summary_target_root`
  - `get_status_summary_projection_path`
  - `_build_status_summary_projection`
  - `load_status_summary_projection`
- Extract into `status_commands.py`:
  - `_build_status_handoff_block`
  - `_display_root_dashboard`
  - `_get_stale_bugs`
  - `status`
- Keep in facade:
  - thin wrappers with stable public signatures
  - compatibility exports marked with `is_wrapper = True`

### Round 2: Readiness Validation

- New module:
  - `readiness_validator.py`
- Candidate moves:
  - `validate_feature_readiness`
  - `print_readiness_warnings`
  - `_build_readiness_fix_commands`
  - `print_readiness_error`
  - `validate_readiness_command`
  - `validate_planning_command`
  - `fix_readiness_command`

### Round 3: Feature Activation and Stage Commands

- New module:
  - `feature_commands.py`
- Candidate moves:
  - `set_current`
  - `set_development_stage`
- Injection contract:
  - `load_progress_json_fn`
  - `save_progress_json_fn`
  - `generate_progress_md_fn`
  - `save_progress_md_fn`
  - `update_runtime_context_fn`

### Round 4: Work-Item Selection and next_feature

- New modules:
  - `work_item_selector.py`
  - optional `next_feature_commands.py`
- Candidate moves:
  - `get_next_feature`
  - `_get_dispatched_child_feature`
  - `_select_next_work_item`
  - `next_feature`

### Round 5: Completion Pipeline

- New modules:
  - `completion_flow.py`
  - optional follow-on `acceptance_runner.py`
  - optional follow-on `completion_cleanup.py`
- Candidate moves:
  - `cmd_done`
  - `complete_feature`
  - done-gate orchestration helpers
  - acceptance report persistence
  - post-done cleanup helpers

### Round 6: Backlog and Intake Mutation Commands

- New module:
  - `work_item_commands.py` or `backlog_commands.py`
- Candidate moves:
  - `smart_intake`
  - `add_feature`
  - `update_feature`
  - `defer_features`
  - `resume_deferred_features`
  - `add_update`
  - `list_updates`
  - `add_retro`
  - `set_feature_owner`

### Round 7: Workflow + Reconcile

- New module:
  - `workflow_commands.py`
- Candidate moves:
  - `set_workflow_state`
  - `update_workflow_task`
  - `clear_workflow_state`
  - `validate_plan`
  - `health_check`
  - `reconcile`

### Final Round: Reverse Import Cleanup + Facade Compression

- Target submodules currently needing cleanup:
  - `sprint_ledger.py`
  - `wf_auto_driver.py`
  - `lifecycle_state_machine.py`
  - `progress_ui_server.py`
- Final facade work:
  - normalize dispatch registration
  - keep only wrapper exports, parser wiring, command routing, and `main()`

## Execution Feature Strategy

- Register one executable feature now for Round 0-1 only.
- Do not register one feature per leaf module.
- Do not register the full multi-round convergence as one giant feature.
- After Round 1 is complete, reassess remaining weight and split the later rounds into follow-on features only if the remaining scope is still too large for one implementation cycle.

## Failure Handling

- If `scripts/check_pm_boundary.sh` still misses reverse imports, stop extraction work and fix the checker first.
- If an extraction introduces a reverse import or callback cycle, revert that round and redesign the dependency direction before proceeding.
- If a proposed round spans both read-only and write-path behaviors, split it again; the round is too large.
- If wrapper compatibility becomes unclear, preserve the facade export and move only the body, not the public name.
- If a new module boundary is still ambiguous after code review, keep the logic in the facade temporarily and document the unresolved ownership instead of forcing a bad split.
- If AI workers begin bypassing the facade and editing leaf modules inconsistently, create the module map immediately and add a facade-level module index comment block.

## Acceptance Criteria

- A canonical plan exists in `docs/plans/` and `progress.json` points to it via a planning update.
- Round 0 ends with a boundary checker that catches direct and local reverse imports of `progress_manager`.
- Round 1 extracts the status summary and status rendering chains behind stable facade wrappers.
- Every extraction round preserves command behavior and passes:
  - `scripts/check_pm_boundary.sh`
  - `python3 hooks/scripts/generate_prog_docs.py --check`
  - focused pytest coverage for the touched command family
- `docs/changes/index.jsonl` receives one record per extraction round.
- Before the facade is considered converged:
  - no remaining submodule reverse-imports to `progress_manager`
  - no new business logic added to the facade
  - module ownership is documented

## Key Architectural Decisions (ADR)

### ADR-001: Use Facade Convergence, Not Big-Bang Rewrite

**Status:** Accepted

We will not rewrite `progress_manager.py` in one change. The file will be reduced through bounded extraction rounds so behavior stays testable and regressions remain attributable to one cluster at a time.

### ADR-002: Fix the Boundary Checker Before More Large Extractions

**Status:** Accepted

Current manual inspection shows reverse-import patterns that the boundary script can miss. Additional structural work without a reliable guardrail would create false confidence.

### ADR-003: Prioritize Read-Only Paths Before Write Paths

**Status:** Accepted

Summary projection and status rendering are safer first-round candidates than `cmd_done`, `smart_intake`, or `next_feature`, because they reduce facade weight without immediately touching mutation and gate pipelines.

### ADR-004: `progress.json` Holds Pointers, Not Design Bodies

**Status:** Accepted

Tracker state should remain compact and operational. Detailed architecture and phased execution plans live in markdown plan documents, while `progress.json` stores only a concise planning pointer.

### ADR-005: `module-map.md` Is a Navigation Aid, Not a Knowledge Graph

**Status:** Accepted

The future `progress-manager-module-map.md` file is not meant to auto-drive behavior. It exists to help humans and AI sessions quickly answer ownership and migration-status questions after the split deepens.

## Execution Constraints

- [CONSTRAINT-001] Preserve facade imports
  - Applies to: `progress_manager.py` public functions used by CLI, tests, hooks, and helpers
  - Must: Keep existing external names stable; move implementations behind wrappers instead of forcing callers to import leaf modules
  - Validation: Touched tests continue importing `progress_manager`; wrapper exports remain present

- [CONSTRAINT-002] No reverse imports
  - Applies to: `plugins/progress-tracker/hooks/scripts/*.py`
  - Must: Submodules must not import `progress_manager` directly, including local function-scope imports
  - Validation: `scripts/check_pm_boundary.sh` fails on any such import

- [CONSTRAINT-003] One responsibility cluster per round
  - Applies to: each extraction batch
  - Must: Do not mix unrelated clusters such as status rendering and completion cleanup in the same round
  - Validation: Each round can be described in one sentence with one dominant ownership theme

- [CONSTRAINT-004] Read-only first
  - Applies to: early rounds
  - Must: Extract summary/status chains before `next_feature`, `cmd_done`, and `smart_intake`
  - Validation: Round 1 changes only read-path modules and facade wrappers

- [CONSTRAINT-005] Tracker stores pointers only
  - Applies to: `progress.json` updates for this initiative
  - Must: Store only concise summary, refs, and next action; never inline the full phased design
  - Validation: The planning update is shorter than the plan document and references it via `doc:` ref

- [CONSTRAINT-006] Per-round auditability
  - Applies to: every extraction round after this plan
  - Must: Write one matching `docs/changes/index.jsonl` record and detail markdown record
  - Validation: `docs/changes/index.jsonl` contains one new row per completed round

- [CONSTRAINT-007] Module map follows first real split
  - Applies to: architecture documentation
  - Must: Create `docs/progress-tracker/architecture/progress-manager-module-map.md` after Round 1, not before
  - Validation: The file exists and lists at least module owner, exported wrappers, and migration status for each extracted cluster
