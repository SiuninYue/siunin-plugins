# SPM-1 Add Four Gstack Planning Commands And Workflow Bridge

**Goal:** Deliver four planner-facing gstack planning commands that write artifacts and sync structured planning updates into PROG with `source=spm_planning`.
**Architecture:** Keep command contracts in `commands/*.md`; implement command execution and artifact generation in `scripts/planning_workflow.py`; route PROG synchronization through `scripts/prog_bridge.py` via `sync_planning_update` with stage-specific refs.

## Locked Decisions

1. Keep command set and parameter contracts unchanged:
   - `office-hours`
   - `plan-ceo-review`
   - `plan-design-review`
   - `plan-devex-review`
2. Feature 2 scope is limited to:
   - `scripts/planning_workflow.py`
   - `scripts/prog_bridge.py`
   - `commands/*.md` for the four planning commands
   - planning-related tests in `tests/`
3. Do not add new SPM CLI subcommands in this feature.
4. Do not change PROG planning gate semantics in this feature (belongs to later PROG features).

## Tasks

1. Confirm command contract files are complete and consistent.
   - Files: `commands/office-hours.md`, `commands/plan-ceo-review.md`, `commands/plan-design-review.md`, `commands/plan-devex-review.md`
   - Check: frontmatter validity, planner-only boundary text, and lane suggestion wording for optional reviews.
2. Verify `planning_workflow.py` end-to-end behavior for all four stages.
   - Check artifact directories:
     - `docs/product-contracts/` for `office-hours`
     - `docs/product-reviews/` for review commands
   - Check sync payload includes stage refs and `doc:*` refs.
3. Verify bridge behavior in `prog_bridge.py`.
   - Ensure `sync_planning_update()` enforces stage whitelist.
   - Ensure emitted update source is always `spm_planning`.
   - Ensure planning refs are normalized to `planning:<stage>`.
4. Close test coverage gaps for Feature 2 acceptance.
   - Keep command contract tests.
   - Ensure workflow tests cover success path and sync-failure path.
   - Ensure bridge tests cover `spm_planning` source, planning refs, and invalid stage.
5. Run acceptance checks and map them to feature test steps.
   - Expected acceptance focus:
     - planning commands write docs into expected directories
     - `sync_planning_update` emits refs + `source=spm_planning`

## Acceptance Mapping

- Acceptance 1 (`office-hours and plan-* commands write docs under docs/product-contracts or docs/product-reviews`):
  - Verify via workflow tests and command-level spot checks.
- Acceptance 2 (`sync_planning_update writes updates with refs and source spm_planning`):
  - Verify via `tests/test_prog_bridge.py::test_sync_planning_update_emits_planning_source_and_refs`.

## Risks

- Local Python environment currently lacks `pytest`; acceptance execution may require dependency setup before `/prog-done`.
- Planning gate behavior in PROG may be interpreted differently by users; wording improvements should be tracked in PROG feature scope, not this feature.
