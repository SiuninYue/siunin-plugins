# F9 Refactor progress_manager into Modular Command Helpers

**Goal:** Extract handoff and completion prompt builders from `progress_manager.py` into a dedicated `progress_prompt_builders` module, reducing the monolithic file size and improving maintainability without changing any external behavior.

**Tech Stack:** Python 3, argparse, pytest, existing `progress_manager.py` infrastructure.

**Plan path:** `docs/plans/2026-04-26-f9-refactor-pm-modular-helpers.md`

## Tasks

- [x] Extract handoff and completion prompt builders into `progress_prompt_builders.py`
- [x] Replace builder functions in `progress_manager.py` with thin import shims to `progress_prompt_builders`
- [x] Add regression tests for `/prog done` and `/prog status` handoff output

## Risks

- Extracted functions may break if `progress_manager.py` imports are not updated correctly — covered by regression tests.
- Shim layer adds one extra import hop — negligible performance impact.

## Acceptance

- `pytest -q plugins/progress-tracker/tests/test_progress_manager.py -k "done_command_outputs_next_feature_handoff or done_command_outputs_completion_summary_when_all_complete or status_handoff_block_execution_complete"` passes