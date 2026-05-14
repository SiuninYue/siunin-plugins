---
name: prog-smart
description: Route /prog-smart to prog smart CLI with AI classification. Use when user wants to add a work item via natural language (bug report, feature idea, task, or status update).
model: haiku
---

# prog-smart intake flow

## Purpose
Classify user's natural language input and commit it to progress tracking as the correct work-item type (bug/feature/task/update).

## Flow

1. **Classify**: Call haiku to analyze the user's text. Output: `{type, confidence, profile}`
2. **Preview**: Call `prog smart --candidate-json '<json>'` (no --commit). Show candidate to user.
3. **Clarify (if needed)**: If confidence < 0.6, ask the user ONE clarification question. Re-classify with their answer.
4. **Commit**: Call `prog smart --candidate-json '<json>' --commit <type>` to write the record.

## candidate JSON format

```json
{
  "type": "bug",
  "confidence": 0.92,
  "profile": {
    "description": "crash on startup when config is missing",
    "priority": "P0",
    "details": "reproducible on fresh install",
    "refs": [],
    "next_action": "investigate config loader",
    "category": "status"
  }
}
```

## Rules

- **Never write JSON without explicit --commit** (preview is zero-mutation)
- **Exactly one clarification question** when ambiguous (confidence < 0.6)
- priority values: P0 (critical/high), P1 (medium), P2 (low/normal)
- category (for update type): status | decision | risk | handoff | assignment | meeting

## CLI reference

```bash
# Preview only (no mutation)
prog smart --candidate-json '<json>'

# Commit
prog smart --candidate-json '<json>' --commit bug
prog smart --candidate-json '<json>' --commit feature
prog smart --candidate-json '<json>' --commit task
prog smart --candidate-json '<json>' --commit update
```

## Common Mistakes

| 错误 ❌ | 正确 ✅ |
|----------|--------|
| `--json` | `--candidate-json` |
| 直接 `--commit` 跳过预览 | 先预览，用户确认后再 `--commit` |
| `--type bug` | `--commit bug` |
