# Frontmatter Standards

This reference provides complete frontmatter specifications for all testing documents.

## Required Fields

All test documents must include these fields in YAML frontmatter:

```yaml
---
type: [document_type]
id: [feature_id or bug_id]
date: YYYY-MM-DD
status: [status_value]
---
```

## Field Specifications

### type (required)

The document type identifier.

| Value | Usage |
|-------|-------|
| `feature-acceptance` | Feature verification and sign-off |
| `bug-fix-report` | Bug analysis and fix documentation |
| `test-guide` | Testing instructions for a feature |
| `solution-doc` | Detailed solution for a bug |

### id (required)

The identifier for the feature or bug.

**Format:**
- Features: Plain number (`1`, `2`, `3`)
- Bugs: BUG-XXX format (`BUG-001`, `BUG-002`)

**Examples:**
```yaml
id: 2           # Feature acceptance
id: BUG-002     # Bug fix report
```

### date (required)

The document creation date in ISO 8601 format.

**Format:** `YYYY-MM-DD`

**Examples:**
```yaml
date: 2024-01-20
```

**Invalid formats:**
```yaml
date: 2026/01/28    # Wrong separator
date: Jan 20, 2024   # Not ISO format
date: 01-20-2024     # Wrong order
```

### status (required)

The current status of the document or testing.

#### For Feature Acceptance

| Value | Meaning |
|-------|---------|
| `passed` | All tests passed, feature accepted |
| `passed-with-notes` | Passed with known limitations documented |
| `failed` | Tests failed, feature rejected |
| `partial` | Partially complete, more work needed |

#### For Bug Fix Reports

| Value | Meaning |
|-------|---------|
| `fixed` | Bug is resolved and verified |
| `in-progress` | Currently being fixed |
| `verified` | Fix has been tested and confirmed |

#### For Test Guides

| Value | Meaning |
|-------|---------|
| `draft` | Initial draft, not yet reviewed |
| `approved` | Reviewed and approved |
| `archived` | No longer relevant |

## Optional Fields

### tester

The person who performed testing.

```yaml
tester: Username or Name
```

### build

The git commit hash for this test.

```yaml
build: abc123d
```

### environment

Testing environment information.

```yaml
environment: macOS 15.2, M5-24GB-1TB
```

### priority

For bug reports only.

```yaml
priority: high | medium | low | critical
```

## Complete Examples

### Feature Acceptance Report

```yaml
---
type: feature-acceptance
id: 2
date: 2024-01-28
status: passed-with-notes
tester: Outliers
build: abc123d
environment: macOS 15.2, M5-24GB-1TB
---
```

### Bug Fix Report

```yaml
---
type: bug-fix-report
id: BUG-002
date: 2024-01-30
status: fixed
priority: critical
---
```

### Test Guide

```yaml
---
type: test-guide
id: 3
date: 2024-01-18
status: draft
---
```

## Frontmatter Placement

Frontmatter must be:
1. At the very top of the file
2. Enclosed in triple dashes (`---`)
3. Valid YAML syntax
4. Followed immediately by document content

## Common Mistakes

### Mistake 1: Missing Required Fields

❌ **Incorrect:**
```yaml
---
type: feature-acceptance
id: 2
---
```

✅ **Correct:**
```yaml
---
type: feature-acceptance
id: 2
date: 2024-01-28
status: passed
---
```

### Mistake 2: Invalid Date Format

❌ **Incorrect:**
```yaml
date: 2026/01/28
```

✅ **Correct:**
```yaml
date: 2024-01-28
```

### Mistake 3: Wrong ID Format

❌ **Incorrect:**
```yaml
id: "2"        # Don't quote numbers
id: bug-2      # Missing BUG prefix
id: BUG-2      # Missing leading zeros
```

✅ **Correct:**
```yaml
id: 2          # Feature ID
id: BUG-002    # Bug ID
```

### Mistake 4: Invalid Status Value

❌ **Incorrect:**
```yaml
status: complete     # Not a valid value
status: done         # Not a valid value
status: fixing       # Not a valid value
```

✅ **Correct:**
```yaml
status: passed               # For features
status: fixed                # For bugs
status: passed-with-notes    # For features with issues
```

## Validation

Before saving a test document, verify:

- [ ] All 4 required fields present
- [ ] `type` is a valid document type
- [ ] `id` matches progress.json
- [ ] `date` is in YYYY-MM-DD format
- [ ] `status` is a valid value for document type
- [ ] YAML syntax is correct (no syntax errors)
- [ ] Triple dashes properly placed
