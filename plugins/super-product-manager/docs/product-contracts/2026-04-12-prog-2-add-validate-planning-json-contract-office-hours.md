# Office Hours: PROG-2 add validate-planning json contract

- Date: 2026-04-12
- Mode: planner-only (no technical implementation path)

## Goals
- Add validate-planning command to prog CLI
- Return structured JSON for planning artifact completeness
- Enable planning gate in next-feature to rely on well-defined contract

## Scope
- New validate-planning command in progress-tracker prog CLI
- JSON output schema: status/required/missing/optional_missing/refs/message
- Status values: ready/warn/missing
- No UI changes; CLI-only output

## Acceptance Criteria
- validate-planning returns ready when all required refs present
- validate-planning returns warn when only optional refs absent
- validate-planning returns missing when required refs absent
- JSON output always includes all 6 required fields

## Risks
- Schema drift between validate-planning and next-feature gate causes silent failures
- Incomplete test coverage leaves edge cases undetected
