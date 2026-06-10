---
name: bug-fix
description: Use when a bug is reported, discovered, or needs investigation — including /prog-fix, "something is broken", "debug this", "failing test", or any request to investigate, record, schedule, or fix a bug. Invoke even when the user doesn't say "bug" explicitly.
references:
  - "testing-standards"
  - "superpowers:systematic-debugging"
  - "superpowers:test-driven-development"
  - "superpowers:requesting-code-review"
  - "references/workflow.md"
  - "references/integration.md"
  - "examples/session.md"
model: sonnet
---

# Bug Fix Skill

Manage bug lifecycle from discovery to resolution through systematic debugging and TDD workflows.

## Purpose

Coordinate bug handling: quick verification, smart scheduling into feature timeline, and orchestrate Superpowers skills for systematic debugging and TDD fixes.

## Bug Lifecycle

```
pending_investigation → investigating → confirmed → fixing → fixed
                      ↓
                   false_positive
```

## Core Workflow

### Scenario 1: No Arguments - Bug List

When `/prog-fix` runs without arguments, display bug backlog:

```markdown
## Bug Backlog

<IF no bugs>
No bugs recorded. Use `/prog-fix "<description>"` to report a bug.

<ELSE>
### Pending Bugs

Display bugs sorted by priority with:
- Bug ID and description
- Current status (icon)
- Creation time
- Scheduled position

**High Priority** (🔴)
- [BUG-001] Session timeout
  Status: 待深入调查 | Created: 2h ago
  📍 Before Feature 3

**Medium Priority** (🟡)
- [BUG-002] Avatar upload slow
  Status: 已确认 | Created: 1d ago
  📍 After Feature 4

**Low Priority** (🟢)
- [BUG-003] Occasional crash
  Status: 待调查 | Created: 3d ago
  📍 Last

### Options
1. Fix highest priority bug
2. Select bug by ID
3. Report new bug
```

### Scenario 2: Bug Description - Three-Step Flow

#### Step 1: Quick Verification (Under 30 seconds)

Perform fast preliminary check:

```markdown
## 🔍 Quick Bug Verification

Analyzing: "<bug description>"

**Check 1**: Search related code...
→ Use Grep tool for keywords from bug description

**Check 2**: Check known issues...
→ Compare with existing bugs in progress.json

**Check 3**: Assess reproducibility...
→ Evaluate based on description clarity

### Verification Results

✅ **Related code**: <file paths or "none">
⚠️ **Known issues**: <count> similar bugs
🔬 **Reproducibility**: <High/Medium/Low>

### Initial Assessment

🟡 **Preliminary**: Likely a real bug
  - Code exists, needs investigation

OR

🟢 **Possible False Positive**
  - Might be config or user error

OR

🔴 **Uncertain**: Needs investigation
```

#### Step 2: User Confirmation

```markdown
### How would you like to proceed?

[1] **Record to itinerary** (Recommended)
   - Add to bug backlog
   - Smart scheduling based on impact
   - Investigate and fix later

[2] **Investigate now** (Systematic debugging)
   - Use systematic-debugging
   - Confirm if real bug
   - Fix immediately with TDD

[3] **Cancel**
   - Dismiss this report

Your choice [1/2/3]?
```

Handle user choice:
- **[1]**: Proceed to Step 3 (Smart Scheduling)
- **[2]**: Invoke `systematic-debugging`
- **[3]**: Exit

#### Step 3: Smart Scheduling

Analyze impact and recommend insertion point:

```markdown
### 🎯 Smart Scheduling Analysis

**Bug**: <description>

**Impact Assessment**:
→ Analyze affected features via Grep
→ Check current feature list

**Related Features**:
  - Feature X: <name> (likely affected)
  - Feature Y: <name> (might be affected)

**Priority Calculation**:
  - Severity: <High/Medium/Low>
  - Scope: <Wide/Narrow>
  - **Calculated**: <High/Medium/Low>

**Scheduling Recommendation**:

<IF high_priority>
🔴 **High Priority** - Insert before next feature

<ELSE IF medium_priority>
🟡 **Medium Priority** - Insert after related feature

<ELSE>
🟢 **Low Priority** - Add to end

### Proposed Schedule

Current itinerary: <display list>
After insertion: <display with bug>

**Confirm insertion?** [Y/n]
```

Update progress.json and progress.md on confirmation.

### Scenario 3: Fixing Recorded Bug

When user selects bug to fix:

```markdown
## 🔧 Fixing Bug: BUG-XXX

**Description**: <bug description>
**Status**: <current status>
**Priority**: <priority>

### Current Bug State

<IF pending_investigation>
🔴 **Needs Investigation**

Use systematic debugging to find root cause.

<IF investigating>
🟡 **Investigation In Progress**

Resume investigation?

<IF confirmed>
🟢 **Confirmed Bug**

Root cause: <recorded cause>
Ready for TDD fix.

<IF fixing>
🔧 **Fix In Progress**

Resume fixing?
```

**Route by current bug state before executing phases:**
- `pending_investigation` / `investigating` → run **Phase 1 → 2 → 3 → 4** (full flow)
- `confirmed` → skip to **Phase 4** (root cause already known, go straight to TDD fix)
- `fixing` → resume from **Phase 4** (TDD already started, continue from where it left off)

---

#### Phase 1: 结构化证据收集 (Evidence Collection)

Collect structured evidence before starting investigation:

```markdown
## 📋 Phase 1: 结构化证据收集

**复现路径 (Reproduction Path)**:
→ List exact steps to reproduce: environment setup, input sequence, trigger action

**错误日志 (Error Logs)**:
→ Collect relevant log output, stack traces, error messages

**输入输出对比 (Input/Output Comparison)**:
→ Document expected vs actual: what was input, what was returned vs what was expected
```

---

#### Phase 2: 触发模式分析 (Trigger Pattern Analysis)

Analyze when and how the bug triggers:

```markdown
## 🔍 Phase 2: 触发模式分析

**稳定触发条件 (Stable Trigger Conditions)**:
→ Conditions that reliably reproduce the bug every time (e.g., specific input, state)

**边界条件 (Boundary Conditions)**:
→ Edge cases where behavior changes — empty/null values, limit inputs, concurrent access
```

---

#### Phase 3: Systematic Debugging + 假设唯一性验证

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

For bugs needing investigation:
Use the Skill tool with these exact parameters:
  - skill: "systematic-debugging"
  - args: "<bug description>"

WAIT for the skill to complete.

After investigation completes, update bug status:
→ plugins/progress-tracker/prog update-bug --bug-id "BUG-XXX" --status "confirmed"
</CRITICAL>

Once systematic-debugging completes and returns a root cause, perform **唯一性验证 (Hypothesis Uniqueness Check)** before proceeding to Phase 4:

```markdown
## ✅ 假设唯一性验证

**Proposed Root Cause**: <hypothesis from systematic-debugging>

**竞争假设排除 (Competing Hypotheses)**:
→ List all other hypotheses that could explain the same symptoms
→ For each competing hypothesis: state the evidence that disproves it
→ Confirm all competing hypotheses are eliminated

**结论**: This hypothesis is the unique cause — no other explanation survives the evidence.
Only proceed to Phase 4 after uniqueness is confirmed.
```

---

#### Phase 4: TDD Fix + 回归检查 (Regression Check)

<CRITICAL>
For confirmed bugs requiring TDD fix:
Use the Skill tool with these exact parameters:
  - skill: "test-driven-development"
  - args: "Fix <bug>: <one-line description>"

WAIT for the skill to complete.

After TDD completes, update bug status:
→ plugins/progress-tracker/prog update-bug --bug-id "BUG-XXX" --status "fixed"
  (This automatically updates both progress.json and progress.md)
</CRITICAL>

After TDD completes, run **显式回归检查 (Explicit Regression Check)**:

```markdown
## 🔁 回归检查

1. ✅ **问题A 已消失 (Bug gone)**: Confirm the original failure case no longer reproduces
   → Re-run the reproduction path (from Phase 1 if you ran it, otherwise reproduce manually) — expect it to pass now

2. ✅ **功能B 未受影响 (No side-effect regressions)**: Run full test suite
   → Confirm no adjacent features were broken by the fix
```

---

#### Phase 5: Commit & Review

<CRITICAL>
DO NOT skip this phase. Both sub-steps are mandatory.

**5a — Commit via git-auto:**
Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:git-auto"
  - args: "auto"

WAIT for the skill to complete and return the result.

The git-auto skill detects this is a bug fix, creates a fix branch if needed, commits with a proper message, and pushes for review. After receiving the commit hash, update the bug:
→ plugins/progress-tracker/prog update-bug --bug-id "BUG-XXX" --fix-summary "Fix applied (commit: <commit_hash>)"

**5b — Code review:**
Use the Skill tool with these exact parameters:
  - skill: "requesting-code-review"
  - args: "Verify bug fix for: <bug>"

WAIT for the skill to complete.
</CRITICAL>

## CLI Quick Reference

| 命令 | 关键参数 |
|------|---------|
| `add-bug` | `--description` (必填), `--status` (可选) |
| `update-bug` | `--bug-id`, `--status`, `--fix-summary` |
| `list-bugs` | 无参数 |
| `remove-bug` | `--bug-id` |

完整签名和其他参数见 `--help` 或 [`references/integration.md`](references/integration.md)。

## Priority and Scheduling Algorithms

Priority is calculated from severity keywords (high/medium/low) + scope (wide if > 3 related files). Scheduling places high-priority before next feature, medium after related feature, low at end. Full algorithms in [`references/workflow.md`](references/workflow.md).

## Error Handling

### No Progress Tracking

```markdown
## No Progress Tracking Found

No active project tracking.

### Options
1. Initialize: `/prog init <project>`
2. Fix without tracking: Use debugging directly
```

### Duplicate Bug

```markdown
## Duplicate Bug Detected

Similar bug exists: BUG-XXX

### Options
1. Update existing bug
2. Create new report
3. Cancel
```

## Common Mistakes

| 错误 ❌ | 正确 ✅ |
|----------|--------|
| `prog bug` | `prog add-bug` |
| `--title "..."` | `--description "..."` |
| `--severity P2` | 严重程度写进 description 文本 |
| `prog fix-bug` | `prog update-bug` |

## Key Reminders

1. **Quick verification first** - Don't skip 30-second check
2. **User controls flow** - Always present options
3. **Smart scheduling** - Insert bugs where they make sense
4. **Use Superpowers** - systematic-debugging and TDD are mandatory
5. **Update state immediately** - Keep progress.json as source of truth
6. **Code review required** - Don't skip verification
7. **Imperative language** - Use verb-first instructions

## Additional Resources

For detailed implementation patterns, consult:
- **`references/workflow.md`** - Complete workflow examples
- **`references/integration.md`** - Superpowers skill integration details
- **`examples/session.md`** - Example bug fixing session
