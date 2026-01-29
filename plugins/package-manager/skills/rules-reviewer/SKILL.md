---
name: rules-reviewer
description: This skill should be used when the user asks to "review rules", "check prompt quality", "validate instructions", "audit system prompts", or mentions reviewing, validating, or checking Claude Code rules, prompts, or instructions. Provides guidance for reviewing rule quality, identifying issues, and suggesting improvements.
version: 0.1.0
---

# Rules Reviewer

## Purpose

Review Claude Code rules, prompts, and instructions for quality, clarity, and effectiveness. Identify common issues and provide actionable feedback for improvement.

## When to Use

Activate this skill when:
- Reviewing rule files (.md files in rules/ directories)
- Validating system prompts or instructions
- Auditing skill or agent descriptions
- Checking configuration files for Claude Code

## Review Criteria

### 1. Clarity and Specificity

**Check for:**
- ❌ Vague instructions like "be helpful" or "do good work"
- ✅ Specific, actionable instructions
- ❌ Ambiguous pronouns ("it", "that", "they")
- ✅ Clear referents and specific terminology

**Examples:**

❌ **Poor:**
```markdown
Make sure it works well and handles errors properly.
```

✅ **Good:**
```markdown
Validate all user input before processing. Return clear error messages with:
- Error description
- Expected input format
- How to fix the issue
```

### 2. Trigger Quality (for skills/commands)

**Check that descriptions include:**
- Specific phrases users would say
- Third-person format ("This skill should be used when...")
- Concrete scenarios

❌ **Poor:**
```yaml
description: Helps with debugging
```

✅ **Good:**
```yaml
description: This skill should be used when the user asks to "debug this", "find the bug", or "fix this error".
```

### 3. Writing Style

**Imperative form:**
- ❌ "You should read the file first"
- ✅ "Read the file first"

**Objective language:**
- ❌ "Try to be helpful"
- ✅ "Provide clear, actionable responses"

### 4. Progressive Disclosure

**Check for:**
- SKILL.md is lean (1,500-2,000 words)
- Detailed content in references/
- No unnecessary duplication

**Good structure:**
```
SKILL.md (core essentials)
├── references/
│   ├── patterns.md (detailed patterns)
│   └── advanced.md (advanced techniques)
```

### 5. Common Anti-Patterns

**Look for and flag:**
- Overly prescriptive instructions that limit adaptability
- Contradictory instructions
- Missing edge cases
- Unclear success criteria
- Outdated information

## Review Workflow

1. **Read the content** - Understand the full context
2. **Check against criteria** - Use the review checklist
3. **Identify issues** - List specific problems with line numbers
4. **Suggest improvements** - Provide actionable recommendations
5. **Prioritize** - Mark issues as critical/important/nice-to-have

## Output Format

Structure review feedback as:

```markdown
# Review of [File Name]

## Summary
[One sentence overall assessment]

## Issues Found

### Critical
- [Issue 1 with location]

### Important
- [Issue 2 with location]

### Nice-to-Have
- [Issue 3 with location]

## Recommendations
1. [Specific action]
2. [Specific action]
```

## Additional Resources

### References

- **`references/review-checklist.md`** - Comprehensive review checklist
- **`references/common-issues.md`** - Common problems and solutions
