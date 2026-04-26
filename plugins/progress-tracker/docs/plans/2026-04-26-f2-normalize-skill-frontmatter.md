# F2: Normalize Skill Frontmatter to SOP-Compliant Shape

## Summary

Delete prohibited fields (version, scope, inputs, outputs, evidence) from all 15 progress-tracker SKILL.md files. Preserve allowed fields (model, user-invocable, non-empty references). Run regression tests and compliance scan.

## Scope

### In Scope

- Remove version, scope, inputs, outputs, evidence from frontmatter
- Remove references: [] (empty list)
- Preserve model, user-invocable, references (non-empty)
- Verify with contract tests and quick_validate.py

### Out of Scope

- Adding new validation tests (F4 responsibility)
- Modifying description content
- Other plugins' SKILL.md files

## Tasks

### T1 — Audit: Identify violation fields per file

List each SKILL.md and its prohibited fields.

### T2 — Edit: Remove prohibited fields from frontmatter

For each file:
- Delete version, scope, inputs, outputs, evidence keys and their values
- Delete references: [] (empty list)
- Preserve model, user-invocable, references (non-empty)

**Acceptance:** `rg -n '^(version|scope|inputs|outputs|evidence):|^references: \[\]' skills/*/SKILL.md` returns no output.

### T3 — Regression test

Run `pytest -q tests/test_command_discovery_contract.py`

**Acceptance:** 3 passed, 0 failures.

### T4 — Compliance scan

Run `python3 hooks/scripts/quick_validate.py`

**Acceptance:** Quick validation passed.

## Acceptance Mapping

| Test Step | Plan Task | Expected Outcome |
|-----------|-----------|-----------------|
| Update target SKILL.md frontmatter to keep required fields and remove prohibited keys | T2 | All 15 SKILL.md files contain only allowed fields (name, description, model, user-invocable, references with items) |
| Run contract tests: pytest -q plugins/progress-tracker/tests/test_command_discovery_contract.py | T3 | 3 passed, 0 failures |
| Re-run scan: python3 plugins/progress-tracker/hooks/scripts/quick_validate.py | T4 | Quick validation passed |

## Risks

- **Risk: Frontmatter removal breaks skill discovery** — Mitigated by T3 contract tests verifying command discovery still works.
- **Risk: References list format changes affect downstream consumers** — Mitigated by only removing empty references; non-empty references preserved unchanged.
- **Risk: Other plugins have same violations** — Out of scope for this feature; tracked separately.