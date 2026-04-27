# Add explicit model declaration checks for required skill scopes -- direct_tdd execution note

**Goal:** Deliver Add explicit model declaration checks for required skill scopes with traceable acceptance coverage.

**Architecture:** Direct TDD implementation of Add explicit model declaration checks for required skill scopes. Out of scope: Unrelated refactors and behavior changes outside this feature..

---

## Tasks

- [ ] Update required skill frontmatter with model declarations
- [ ] Run skill contract tests: pytest -q plugins/progress-tracker/tests/test_project_memory_skill_contract.py
- [ ] Re-run scan and confirm no missing model in required scopes

## Acceptance Mapping

- Scenario: Update required skill frontmatter with model declarations
- Scenario: Run skill contract tests: pytest -q plugins/progress-tracker/tests/test_project_memory_skill_contract.py
- Scenario: Re-run scan and confirm no missing model in required scopes

## Risks

- Potential regression in adjacent workflows; verify with listed test_steps.
