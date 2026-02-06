---
name: testing-standards
description: This skill should be used when the user asks to "generate test documentation", "create acceptance report", "write bug fix report", "document testing results", "create test guide", or "standardize test documents". Defines naming conventions, frontmatter standards, and content structure for all testing documents in docs/testing/. Automatically referenced by feature-complete and bug-fix skills.
version: "1.0.0"
scope: skill
inputs:
  - Feature ID or Bug ID
  - Test results or verification status
outputs:
  - Formatted test documentation
  - Acceptance reports
  - Bug fix reports
evidence: optional
references:
  - naming-conventions.md
  - frontmatter-standards.md
  - template-examples.md
---

# Testing Standards Skill

This skill defines the standards for all testing documentation in the project. All test documents must follow consistent naming, frontmatter, and content structure standards.

## Purpose

Testing documents provide traceability for feature acceptance and bug fixes. When completing features or fixing bugs, generate documentation that records what was tested, results, and any issues discovered.

## When This Skill Is Used

This skill is automatically referenced by:
- **feature-complete** skill when generating acceptance reports
- **bug-fix** skill when generating bug fix reports

This skill may also be used directly when:
- Creating test guides for upcoming features
- Documenting verification procedures
- Standardizing existing test documentation

## Document Naming Conventions

All test documents must follow these naming patterns:

| Document Type | Pattern | Example |
|---------------|---------|---------|
| Feature Acceptance Report | `feature-{id}-acceptance-report.md` | `feature-2-acceptance-report.md` |
| Bug Fix Report | `bug-{id}-fix-report.md` | `bug-002-fix-report.md` |
| Test Guide | `feature-{id}-test-guide.md` | `feature-3-test-guide.md` |
| Solution Document | `bug-{id}-solution.md` | `bug-002-solution.md` |
| General Guide | `guide-{topic}.md` | `guide-dev-permission.md` |

**Rules:**
- Use lowercase letters
- Feature IDs: plain numbers (1, 2, 3)
- Bug IDs: BUG-XXX format (BUG-001, BUG-002)
- Use hyphens to separate words
- No spaces or underscores

## Document Location

All testing documents go in: `docs/testing/`

```
project-root/
└── docs/
    └── testing/
        ├── feature-1-acceptance-report.md
        ├── feature-2-acceptance-report.md
        ├── bug-001-fix-report.md
        └── feature-3-test-guide.md
```

## Frontmatter Standards

All test documents must include YAML frontmatter with these fields:

```yaml
---
type: [document_type]
id: [feature_id or bug_id]
date: YYYY-MM-DD
status: [current_status]
---
```

### Document Types

| Type | Usage |
|------|-------|
| `feature-acceptance` | Feature verification and sign-off |
| `bug-fix-report` | Bug analysis and fix documentation |
| `test-guide` | Testing instructions for a feature |
| `solution-doc` | Detailed solution for a bug |

### Status Values

For acceptance reports:
- `passed` - All tests passed, feature accepted
- `passed-with-notes` - Passed with known limitations
- `failed` - Tests failed, feature rejected
- `partial` - Partially complete, needs more work

For bug reports:
- `fixed` - Bug is resolved and verified
- `in-progress` - Currently being fixed
- `verified` - Fix verified by testing

## Smart Verification Workflow

When using this skill from feature-complete or bug-fix, follow this interactive workflow:

### 1. Generate Test Checklist

Analyze the implemented code and generate a relevant test checklist. Present this to the user:

```
Based on the code analysis, here are the recommended verification items:

## Feature #{id} Verification Checklist

### 1. [Component Name]
- [ ] Test item 1
- [ ] Test item 2
- [ ] Test item 3

### 2. [Another Component]
- [ ] Test item 1
- [ ] Test item 2

What have you tested? Describe results in natural language.
```

### 2. Process User Response

Handle different response types appropriately:

| User Response | AI Action |
|---------------|-----------|
| "All passed" / "1,2,3 passed" | Fill in checklist, generate report |
| "Already filled in docs/testing/..." | Read existing document, validate format |
| "1,2 passed but don't know how to test 3" | Explain testing method for item 3 |
| "1,2 passed, forgot to test 3" | Remind about missing item, wait for response |
| "Item 3 has a bug" | Record the issue, ask how to proceed |
| Other questions | Respond appropriately to help user |

### 3. Handle Missing Tests

If user reports they haven't tested some items:
- Explain how to test the missing items
- If user is unclear, provide step-by-step instructions
- Wait for user to complete testing
- Loop back to step 2

### 4. Generate Report

Once all items are addressed:
1. Fill in the checklist based on user's responses
2. Generate the complete report with frontmatter
3. Save to `docs/testing/` with correct filename
4. Update progress tracking

### 5. Handle Issues

If testing reveals bugs or issues:
- Document the issue in the report
- Request user decision on:
  - Fix now and re-test
  - Record as known limitation and proceed
  - Create a new bug report

## Content Structure by Type

For complete templates and content structure, refer to **`references/template-examples.md`**.

**Quick summary:**

| Document Type | Key Sections | Frontmatter Type |
|---------------|--------------|------------------|
| Feature Acceptance | 测试前准备, 测试结果, 总体评估, 遗留问题 | `feature-acceptance` |
| Bug Fix Report | 🐛 Bug 描述, 🔍 根本原因, ✅ 解决方案, 🧪 验证 | `bug-fix-report` |
| Test Guide | 测试环境要求, 测试场景, 边界情况, 故障排查 | `test-guide` |

**Ready-to-use templates** are available in **`assets/`**:
- **`assets/feature-acceptance-template.md`** - Full acceptance report template
- **`assets/bug-fix-template.md`** - Full bug fix report template

## Date Format

Always use ISO 8601 format: `YYYY-MM-DD`

Examples:
- ✅ `2024-01-20`
- ❌ `2026/01/28`
- ❌ `Jan 20, 2024`

## Checkbox Format

Use markdown checkboxes:
- Empty: `- [ ]`
- Checked: `- [x]`

## Language

Test documents should use:
- **Chinese** for content and descriptions
- **English** for code, technical terms, file paths
- **Markdown** for formatting

## Additional Resources

### Reference Files

For detailed standards and templates:
- **`references/naming-conventions.md`** - Complete naming rules
- **`references/frontmatter-standards.md`** - Frontmatter reference
- **`references/template-examples.md`** - Full template examples

### Asset Files

Working templates in `assets/`:
- **`assets/feature-acceptance-template.md`** - Acceptance report template
- **`assets/bug-fix-template.md`** - Bug fix report template
