---
name: bug-fix
description: This skill should be used when the user asks to "fix a bug", "report a bug", "/prog-fix", "investigate bug", or mentions debugging workflow within progress-tracker plugin. Manages bug discovery, verification, smart scheduling, and systematic fixing through TDD.
version: "1.0.0"
scope: skill
inputs:
  - Bug description or no arguments
outputs:
  - Bug verification results
  - Smart scheduling recommendations
  - Coordinated debugging and fixing workflow
evidence: optional
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

Coordinate bug handling within progress-tracker plugin: quick verification, smart scheduling into feature timeline, and orchestrate Superpowers skills for systematic debugging and TDD fixes.

## When to Use

Invoke this skill when:
- User runs `/prog-fix` command
- User reports a bug during feature implementation
- Bug needs to be recorded and scheduled into itinerary
- Recorded bug requires investigation or fixing

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

### Scenario 2: Bug Description - Three-Phase Flow

#### Phase 1: Quick Verification (Under 30 seconds)

Perform fast preliminary check:

```markdown
## 🔍 Quick Bug Verification

Analyzing: "<bug description>"

**Step 1**: Search related code...
→ Use Grep tool for keywords from bug description

**Step 2**: Check known issues...
→ Compare with existing bugs in progress.json

**Step 3**: Assess reproducibility...
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

#### Phase 2: User Confirmation

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
- **[1]**: Proceed to Phase 3 (Smart Scheduling)
- **[2]**: Invoke `systematic-debugging`
- **[3]**: Exit

#### Phase 3: Smart Scheduling

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

### Proceeding with Systematic Debugging...

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

For bugs needing investigation:
Use the Skill tool with these exact parameters:
  - skill: "systematic-debugging"
  - args: "<bug description>"

WAIT for the skill to complete.

After investigation completes, update bug status:
→ plugins/progress-tracker/prog update-bug --bug-id "BUG-XXX" --status "confirmed"

For confirmed bugs requiring TDD fix:
Use the Skill tool with these exact parameters:
  - skill: "test-driven-development"
  - args: "Fix <bug>: <one-line description>"

WAIT for the skill to complete.

After TDD completes, update bug status:
→ plugins/progress-tracker/prog update-bug --bug-id "BUG-XXX" --status "fixed"
  (This automatically updates both progress.json and progress.md)

Next, create a commit for the bug fix using git-auto:

<CRITICAL>
Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:git-auto"
  - args: "auto"

WAIT for the skill to complete and return the result.

The git-auto skill will:
- Detect that this is a bug fix
- Create fix branch if needed
- Commit with proper message
- Push and create PR for review

After receiving the commit hash, update the bug:
→ plugins/progress-tracker/prog update-bug --bug-id "BUG-XXX" --fix-summary "Fix applied (commit: <commit_hash>)"
  (This automatically updates both progress.json and progress.md)
</CRITICAL>

Finally, verify the fix with code review:
Use the Skill tool with these exact parameters:
  - skill: "requesting-code-review"
  - args: "Verify bug fix for: <bug>"

WAIT for the skill to complete.
</CRITICAL>

## Progress Manager Extensions

### Required New Commands

```bash
# Add bug
plugins/progress-tracker/prog add-bug \
  --description "<desc>" \
  --status "<status>" \
  --priority "<high|medium|low>" \
  --scheduled-position "<before|after>:<feature_id>"

# Update bug status
plugins/progress-tracker/prog update-bug \
  --bug-id "BUG-XXX" \
  --status "<new_status>" \
  --root-cause "<cause>"

# List bugs
plugins/progress-tracker/prog list-bugs

# Remove bug (false positive)
plugins/progress-tracker/prog remove-bug "BUG-XXX"
```

### Data Structure

Add to progress.json:

```json
{
  "bugs": [
    {
      "id": "BUG-001",
      "description": "登录后会话丢失",
      "status": "pending_investigation",
      "priority": "medium",
      "created_at": "2025-01-29T14:30:00Z",
      "quick_verification": {
        "code_exists": true,
        "related_files": ["auth/session.js"],
        "reproducibility": "medium",
        "confidence": "possible"
      },
      "scheduled_position": {
        "type": "before_feature",
        "feature_id": 3,
        "reason": "可能影响 Dashboard"
      }
    }
  ],
  "current_bug_id": null
}
```

## Priority Calculation

```python
def calculate_bug_priority(description, verification):
    severity_keywords = {
        "high": ["crash", "broken", "fail", "security", "崩溃", "失败"],
        "medium": ["slow", "error", "wrong", "慢", "错误"],
        "low": ["typo", "cosmetic", "minor", "拼写"]
    }

    # Check severity
    for level, keywords in severity_keywords.items():
        if any(kw in description.lower() for kw in keywords):
            severity = level
            break

    # Check scope
    scope = "wide" if len(verification["related_files"]) > 3 else "narrow"

    # Calculate
    if severity == "high" or scope == "wide":
        return "high"
    elif severity == "low":
        return "low"
    return "medium"
```

## Scheduling Logic

```python
def schedule_bug(bug, features):
    priority = bug["priority"]

    # High priority: before next feature
    if priority == "high":
        return {"type": "before_feature", "feature_id": next_pending_feature["id"]}

    # Medium priority: after related feature
    related = find_related_features(bug["description"], features)
    if related:
        return {"type": "after_feature", "feature_id": related[-1]["id"]}

    # Low priority: end
    return {"type": "last"}
```

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
