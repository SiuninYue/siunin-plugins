# Testing Document Naming Conventions

This reference provides complete naming rules for all testing documents.

## File Naming Pattern

```
[document-type]-[id]-[descriptor].md
```

## Document Types and Patterns

### Feature Documents

| Pattern | Description | Example |
|---------|-------------|---------|
| `feature-{id}-acceptance-report.md` | Feature acceptance verification | `feature-2-acceptance-report.md` |
| `feature-{id}-test-guide.md` | Testing instructions | `feature-3-hotkey-test-guide.md` |
| `feature-{id}-verification.md` | Verification checklist | `feature-1-verification.md` |

### Bug Documents

| Pattern | Description | Example |
|---------|-------------|---------|
| `bug-{id}-fix-report.md` | Bug fix documentation | `bug-002-fix-report.md` |
| `bug-{id}-solution.md` | Complete solution details | `bug-002-solution.md` |
| `bug-{id}-analysis.md` | Bug analysis only | `bug-001-analysis.md` |

### Guide Documents

| Pattern | Description | Example |
|---------|-------------|---------|
| `guide-{topic}.md` | General guide | `guide-dev-permission.md` |
| `guide-{feature}-{topic}.md` | Feature-specific guide | `guide-hotkey-debugging.md` |

## Naming Rules

### Feature IDs

- Use plain numeric IDs: `1`, `2`, `3`
- Match the ID from `progress.json`
- Example: `feature-5-acceptance-report.md`

### Bug IDs

- Use BUG-XXX format: `BUG-001`, `BUG-002`
- Match the ID from `progress.json` bugs array
- Example: `bug-002-fix-report.md`

### Descriptors

Use lowercase hyphenated words:
- ✅ `hotkey-test-guide.md`
- ✅ `dev-permission-guide.md`
- ❌ `Hotkey_Test_Guide.md`
- ❌ `dev permission guide.md`

## Forbidden Patterns

| Pattern | Why | Alternative |
|---------|-----|-------------|
| `test-report-feature-2.md` | Wrong order | `feature-2-acceptance-report.md` |
| `fix-hotkey-bug.md` | Missing bug ID | `bug-002-fix-report.md` |
| `Feature2_Test.md` | Caps and underscore | `feature-2-acceptance-report.md` |
| `final-solution.md` | No ID | `bug-002-solution.md` |

## Migration Guide

### Renaming Existing Files

If you find files that don't match the convention:

| Current Name | Correct Name |
|--------------|--------------|
| `fn-key-solution-final.md` | `bug-002-solution.md` |
| `hotkey-solution-recommendation.md` | `bug-002-recommendation.md` |
| `bug-fix-report-hotkey.md` | `bug-002-fix-report.md` |
| `dev-permission-guide.md` | ✅ Already correct |
| `feature-2-acceptance-report.md` | ✅ Already correct |
| `feature-3-hotkey-test-guide.md` | ✅ Already correct |

## Validation Checklist

Before finalizing a test document name, verify:

- [ ] Uses lowercase letters only
- [ ] Uses hyphens for word separation (no underscores)
- [ ] Contains correct ID (feature number or BUG-XXX)
- [ ] Has clear descriptor indicating document type
- [ ] Ends with `.md` extension
- [ ] No spaces or special characters

## Examples by Use Case

### Use Case 1: Feature Completed

```bash
# User: /prog done
# AI generates: docs/testing/feature-2-acceptance-report.md
```

### Use Case 2: Bug Fixed

```bash
# User: /prog fix BUG-002 --fixed
# AI generates: docs/testing/bug-002-fix-report.md
```

### Use Case 3: Creating Test Guide

```bash
# User: Need a test guide for feature 3
# AI generates: docs/testing/feature-3-test-guide.md
```

### Use Case 4: Documenting Solution

```bash
# User: Document the complete solution for bug-002
# AI generates: docs/testing/bug-002-solution.md`
```
