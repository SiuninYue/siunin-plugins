# progress_manager Facade Module Map

**Status:** F21 Round 2 navigation artifact  
**Plan:** `docs/plans/2026-06-03-progress-manager-facade-rounds.md`  
**Updated:** 2026-06-04

## Purpose

This document is a human/AI navigation map for the ongoing
`progress_manager.py` facade convergence work. It answers three questions:

1. Which module owns a behavior cluster?
2. Which clusters have already moved out of `progress_manager.py`?
3. Which clusters still remain in the facade and should be targeted next?

It is not a runtime dependency, not a generated knowledge graph, and not the
source of truth for boundary rules. Boundary rules remain in
`docs/progress-tracker/architecture/module-boundaries.md`; the canonical
execution plan remains `docs/plans/2026-06-03-progress-manager-facade-rounds.md`.

## Current Facade Role

`hooks/scripts/progress_manager.py` remains the stable public CLI facade. It
should own only:

- CLI parser wiring and command dispatch
- Compatibility wrapper exports for existing tests and callers
- Thin callback/service factories where leaf modules need facade-owned state
- Process-scope configuration such as `--project-root` override handling

New business logic should move into focused modules under
`hooks/scripts/*.py`. Submodules must not import `progress_manager`.

## Extracted Ownership

| Cluster | Owner module | Facade status | Notes |
|---|---|---|---|
| Locking primitives | `lock_manager.py` | Wrapper/delegation | F18 extraction. |
| State IO helpers | `state_io.py` | Mixed wrapper/delegation | Schema defaults still partially facade-owned. |
| Git/worktree context helpers | `git_utils.py` | Wrapper/delegation | F20 cleanup removed `collect_git_context()` runtime `progress_manager` probing; older compatibility probes in `_run_git` and `_detect_default_branch` remain future cleanup candidates. |
| Worktree inspection helpers | `worktree_handler.py` | Wrapper/delegation | Feature-deferred checks are directly importable by status commands. |
| Route sync helpers | `route_sync.py` | Wrapper/delegation | Active-route conflict detection and child payload reads are directly importable. |
| Route commands | `route_commands.py` | Wrapper/delegation | Root dashboard can call repo-root resolution directly. |
| Docs generation helpers | `doc_generator.py` | Wrapper/delegation | Owner formatting and plan document validation live here. |
| Evaluator gateway | `evaluator_gateway.py` | Wrapper/delegation | F18 extraction. |
| Summary projection read path | `summary_projector.py` | F20 wrappers only | Owns status summary projection, fingerprinting, cache rebuild, relative time formatting. |
| Status display/read command | `status_commands.py` | F20 wrappers only | Owns `status`, root dashboard, stale bug display, status handoff rendering. |
| Readiness validation | `readiness_validator.py` | F21 wrappers only | Owns `validate_feature_readiness`, `print_readiness_warnings`, `_build_readiness_fix_commands`, `print_readiness_error`, `validate_readiness_command`, `validate_planning_command`, `fix_readiness_command`, and `_evaluate_planning_readiness`. Callbacks injected: load/save json, generate/save md. |

## Remaining Facade Weight

These clusters still contain substantial logic in `progress_manager.py` and
are candidates for the next extraction rounds:

| Planned round | Candidate module | Remaining behavior cluster |
|---|---|---|
| Round 3 | `feature_commands.py` | `set_current`, development-stage transitions, active feature mutation. |
| Round 4 | `work_item_selector.py`, optional `next_feature_commands.py` | Work-item selection and `next_feature` routing. |
| Round 5 | `completion_flow.py`, optional `acceptance_runner.py`, optional `completion_cleanup.py` | `done`, `complete_feature`, acceptance reports, finish-state cleanup. |
| Round 6 | `work_item_commands.py` or `backlog_commands.py` | Intake, feature/backlog/update/retro/owner mutation commands. |
| Round 7 | `workflow_commands.py` | Workflow state commands, plan validation command, health check, reconcile command. |
| Final | existing allowlisted modules | Remove remaining reverse imports and compress parser/dispatch structure. |

## Current Injection Boundary

`status_commands.StatusCommandServices` intentionally retains only callbacks
that still depend on facade-owned process state or compatibility behavior:

| Callback | Why still injected |
|---|---|
| `load_progress_json_fn` | Reads the active scoped progress payload through the facade. |
| `find_project_root_fn` | Honors `--project-root` and test/session overrides. |
| `load_checkpoints_fn` | Preserves current checkpoint compatibility and storage readiness behavior. |
| `apply_schema_defaults_fn` | Applies facade-owned schema default migration logic. |
| `validate_plan_path_fn` | Uses facade path validation semantics and scoped root handling. |
| `validate_plan_document_fn` | Preserves facade-compatible validation wrapper. |
| `analyze_reconcile_state_fn` | Reconcile diagnosis has not been extracted yet. |
| `load_progress_history_fn` | Archive/history loading has not been extracted yet. |
| `collect_git_context_fn` | Preserves facade patch/test compatibility while `git_utils` remains facade-agnostic. |

Everything else in the F20 status read path should call leaf modules directly.

## Known Boundary Debt

`scripts/.pm_boundary_allowlist` currently suppresses reverse imports in a
small set of legacy modules until the Final round:

| File | Cleanup direction |
|---|---|
| `wf_auto_driver.py` | Inject progress/state directory callbacks instead of importing the facade. |
| `sprint_ledger.py` | Inject transaction and state read/write callbacks. |
| `lifecycle_state_machine.py` | Inject markdown generation/persistence callbacks. |
| `progress_ui_server.py` | Depend on validation/context helpers directly or via explicit callbacks. |

Allowlist entries may include line numbers for traceability, but the checker
filters by file name to avoid CI churn from line drift.

## Progress JSON Policy

Do not copy this full roadmap into `progress.json`. The tracker state should
hold concise pointers only: active feature metadata, a plan path, and short
updates. Detailed sequencing belongs in the canonical plan and this module map.

When F20 closes, register follow-on extraction work as one or more new features
only if the remaining rounds are ready to execute. Avoid one giant feature that
bundles all write-path refactors.
