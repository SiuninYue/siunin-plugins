# F2 Plan: Normalize skill frontmatter to SOP-compliant shape

## Goal

Remove prohibited keys (`version`, `scope`, `inputs`, `outputs`, `evidence`) from all 15
`skills/*/SKILL.md` frontmatter blocks, keeping only SOP-compliant fields:
- **Required**: `name`, `description`
- **Optional retained**: `model`, `user-invocable`, `references` (non-empty only)

## Target files

All files matching `plugins/progress-tracker/skills/*/SKILL.md`.

## Tasks

### T1 — Audit: list each file and its current prohibited fields

For each SKILL.md, record which prohibited keys are present and whether `references` is empty.

Acceptance: audit table produced (internal, no file write needed).

### T2 — Edit each SKILL.md: remove prohibited keys

For each of the 15 SKILL.md files:
- Delete lines belonging to `version`, `scope`, `inputs`, `outputs`, `evidence` keys (including multi-line values).
- Delete `references: []` lines (empty list only).
- Leave `model`, `user-invocable`, `references` (non-empty) intact.

Acceptance: `grep -r 'version:\|^scope:\|^inputs:\|^outputs:\|^evidence:' skills/*/SKILL.md` returns no matches.

### T3 — Run contract tests (regression)

```bash
pytest -q tests/test_command_discovery_contract.py
```

Acceptance: 3 passed, 0 failures.

### T4 — Re-run compliance scan

```bash
python3 hooks/scripts/quick_validate.py
```

Acceptance: "Quick validation passed."

## Out of scope

- Adding new frontmatter validation tests (covered by F4).
- Changing `description` text.
- Modifying any files outside `skills/*/SKILL.md`.
- Other plugins.
