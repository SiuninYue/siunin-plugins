# Feature 3 Plan: Monorepo Scope Fail-Closed and Explicit Scope Recovery

**Goal:** Enforce fail-closed behavior for mutating commands under ambiguous monorepo scope and ensure explicit `--project-root` recovers deterministically.
**Architecture:** Keep scope resolution centralized in `hooks/scripts/prog_paths.py` and validate behavior through command-level regression tests under `tests/`.

## Tasks

- Add a dedicated regression suite `test_scope_fail_closed.py` for mutating-command scope gating in multi-tracker monorepos.
- Verify fail-closed behavior emits actionable repair guidance at monorepo root without explicit scope.
- Verify explicit `--project-root plugins/<name>` allows the same mutating command to proceed.
- Re-run focused scope regression tests to guard against behavior drift.

## Acceptance Mapping

- "在多候选 tracker 情况下阻断 mutating 命令并给出修复提示" -> `test_monorepo_root_blocks_mutating_command_when_scope_is_ambiguous`.
- "运行: pytest -q plugins/progress-tracker/tests/test_scope_fail_closed.py" -> command executed and passing.
- "校验 --project-root 显式指定后同命令可继续执行" -> `test_explicit_project_root_recovers_mutating_command_from_monorepo_root`.

## Risks

- Scope rules are sensitive; relaxing fail-closed behavior can silently route writes to the wrong plugin.
- Regression risk remains if future path-resolution heuristics bypass explicit scope requirements.
