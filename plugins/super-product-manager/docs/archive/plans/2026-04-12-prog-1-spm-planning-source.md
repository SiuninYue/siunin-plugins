# PROG-1 Support `spm_planning` Source

**Goal:** Ensure PROG feature acceptance for SPM planning source linkage is executable and verifiable in `/prog-done`.
**Architecture:** Reuse existing `progress-tracker` CLI flow; no new subsystem. Wire output visibility in `list-updates`, then validate through command-based acceptance steps executed from the SPM project root.

## Tasks

1. Update `progress-tracker` `list-updates` formatter to display update source marker as `source=<value>`.
2. Add regression test to assert `list-updates` output includes `source=spm_planning`.
3. Verify command-level acceptance from `plugins/super-product-manager` using `prog add-update` and `prog list-updates`.
4. Set workflow `plan_path` and replace feature `test_steps` with executable shell commands for `/prog-done`.

## Acceptance Mapping

- Acceptance 1 (`add-update --source spm_planning succeeds`):
  `../../plugins/progress-tracker/prog add-update --category decision --summary "Feature 1 acceptance: spm_planning source" --source spm_planning --feature-id 1`
- Acceptance 2 (`list-updates shows source=spm_planning`):
  `../../plugins/progress-tracker/prog list-updates --limit 20 | rg -q "source=spm_planning"`

## Risks

- Acceptance command 1 appends a new update entry every run; this is expected and non-blocking for completion.
- Acceptance command 2 depends on `rg` availability in the local environment.
