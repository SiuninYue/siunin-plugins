# Feature Contract Files

Place optional feature contract files in this directory for automatic import
during `add-feature` and `update-feature`.

## File Naming

- `feature-<id>.json`
- `feature-<id>.md`

Only one file is allowed per feature ID. If both files exist, import fails with
an ambiguity error.

## Markdown Contract Format

```markdown
# Feature: <name>

## Requirements
- REQ-xxx: Description

## Changes
### Why
Reason text...
### In Scope
- item
### Out of Scope
- item
### Risks
- item

## Acceptance Scenarios
- Scenario: ...
```

## Parser Safety Limits

- Maximum file size: 64KB
- Maximum line length: 1024
- Allowed heading depth: `#`, `##`, `###`
- Unknown sections: rejected
- Parse budget: `max_steps=20000` or `>200ms` aborts
