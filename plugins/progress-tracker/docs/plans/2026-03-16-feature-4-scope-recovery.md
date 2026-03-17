# Feature 4 Plan: Scope Split-Brain Fix and Degrade Switch

**Goal:** Close scope baseline drift by enforcing fail-closed monorepo behavior and making explicit `--project-root .` semantics deterministic.
**Architecture:** Keep strict scope resolution in `prog_paths.py`; treat explicit path input as cwd-relative first with repo-relative fallback for compatibility.

## Tasks

- Update project-root resolution to evaluate explicit relative paths in a deterministic order.
- Preserve monorepo fail-closed behavior when no explicit scope is provided.
- Align scope baseline tests with fail-closed contract.
- Add regression coverage for `--project-root .` from plugin root context.
- Re-run target acceptance checks.

## Acceptance Mapping

- `pytest -q -k "reconcile or legacy or disable_v2 or scope"` verifies scope and compatibility behavior.
- `PROG_DISABLE_V2=1 ... --project-root . status` verifies compatibility-mode command path.
- Monorepo root command without explicit `--project-root` must fail closed.
- Monorepo root command with explicit `--project-root plugins/progress-tracker` must succeed.

## Risks

- Relative-path semantics change may break existing scripts if fallback behavior regresses.
- Scope rules can regress silently if test contracts drift from architecture constraints.
