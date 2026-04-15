# Feature 19 Plan: Route Preflight Fail-Closed for Mutating Commands

**Goal:** Enforce a unified RouteV1 preflight gate for child tracker mutating commands so writes fail closed when route ownership is missing or mismatched.

**Architecture:** Add a centralized `enforce_route_preflight()` gate in `progress_manager.py` and execute it once in `main()` before mutating command dispatch/transaction logic.

## Tasks

- [x] Add route-preflight command exemptions for setup commands (`init`, `link-project`, `route-select`).
- [x] Implement parent-route discovery for child tracker roots and linked-project matching.
- [x] Implement fail-closed checks:
  - child missing `project_code`
  - child not registered in any parent `linked_projects`
  - child linked to multiple parents (ambiguous)
  - parent registration code mismatch
  - parent `active_routes` mismatch
- [x] Add deterministic recovery guidance containing `cd` + `--project-root` instructions.
- [x] Add regression tests covering:
  - core mutating commands blocked on route mismatch
  - unregistered child blocked
  - matched route allows mutation

## Acceptance Mapping

- "对 next/done/add-feature/update-feature/complete 等 mutating 命令执行 preflight"  
  -> `test_child_route_mismatch_blocks_core_mutating_commands`
- "未注册子项目或路由不一致时阻断并给出 cd + --project-root 指令"  
  -> `test_child_mutating_blocks_when_not_registered_in_parent` + mismatch assertions
- "运行: pytest -q plugins/progress-tracker/tests/test_scope_fail_closed.py"  
  -> target test command executed and passing

## Risks

- Parent discovery currently scans repo root + immediate `plugins/*` roots; non-standard parent locations remain out of scope.
- Multi-parent link ambiguity is blocked hard to avoid silent cross-project writes.
