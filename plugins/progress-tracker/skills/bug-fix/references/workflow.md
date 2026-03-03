# Bug Fix Workflow - Complete Examples

This document provides detailed workflow examples for bug fixing scenarios.

## Complete Bug Reporting Session

**User**: `/prog-fix "登录后5分钟会话自动断开"`

**Phase 1: Quick Verification**

```markdown
## 🔍 Quick Bug Verification

Analyzing: "登录后5分钟会话自动断开"

**Step 1**: Searching for related code...
✓ Found: src/auth/session.js (line 45: session timeout)
✓ Found: src/middleware/auth.js (line 12: session validation)

**Step 2**: Checking if this is a known issue...
✓ No similar bugs found

**Step 3**: Assessing reproducibility...
🔬 Reproducibility: High (clear symptom, specific timing)

### Verification Results

✅ **Related code found**:
  - src/auth/session.js (session timeout logic)
  - src/middleware/auth.js (session validation)
  - Confidence: Possible bug

⚠️ **Known issues**: None

🔬 **Reproducibility**: High

### Initial Assessment

🟡 **Preliminary**: Likely a real bug
  - Session timeout code exists
  - 5 minutes is unusually short (typically 24h+)
  - Cannot confirm without deeper investigation
```

**Phase 2: User Confirmation**

```markdown
### How would you like to proceed?

[1] **Record to itinerary** (Recommended)
   - Add to bug backlog with "pending_investigation" status
   - Smart scheduling based on impact analysis
   - Investigate and fix later

[2] **Investigate now** (Systematic debugging)
   - Use systematic debugging to find root cause
   - Confirm if this is a real bug
   - Fix immediately with TDD

[3] **Cancel**
   - Dismiss this report

Your choice [1/2/3]?
```

**User**: `1`

**Phase 3: Smart Scheduling**

```markdown
### 🎯 Smart Scheduling Analysis

**Bug**: 登录后5分钟会话自动断开
**Impact Assessment**:

**Related Features**:
  - Feature 1: User Authentication (likely affected)
  - Feature 3: Dashboard (might be affected - requires auth)

**Priority Calculation**:
  - Severity: Medium (affects UX, not blocking)
  - Scope: Narrow (auth-related only)
  - Urgency: Medium

**Calculated Priority**: Medium

**Scheduling Recommendation**:

🟡 **Medium Priority** - Insert after related feature
  Reason: Related to Feature 1 (User Authentication)
  Position: After Feature 1

### Proposed Schedule

Current itinerary:
  1. [ ] Feature 1: User Authentication
  2. [ ] Feature 2: Password Reset
  3. [ ] Feature 3: Dashboard
  4. [ ] Feature 4: User Profile

After insertion:
  1. [ ] Feature 1: User Authentication
  → [BUG-001] 会话5分钟超时 ← NEW
  2. [ ] Feature 2: Password Reset
  3. [ ] Feature 3: Dashboard
  4. [ ] Feature 4: User Profile

**Confirm insertion?** [Y/n]
```

**User**: `Y`

**Final Confirmation**

```markdown
### ✅ Bug Recorded!

**BUG-001**: 登录后5分钟会话自动断开

**Details**:
- Status: 🔴 待深入调查
- Priority: Medium
- Created: 2025-01-29 14:35:00
- Scheduled: After Feature 1

**Progress Updated**:
- Bug added to progress.json
- Itinerary updated in progress.md

### Next Steps

1. **Continue current work**: Feature implementation not interrupted
2. **Investigate later**: Use `/prog-fix BUG-001` when ready to debug
3. **View backlog**: Use `/prog-fix` to see all bugs

💡 Tip: Bugs are intelligently scheduled to minimize disruption.
```

## Bug Fixing Session

**User**: `/prog-fix BUG-001`

```markdown
## 🔧 Fixing Bug: BUG-001

**Description**: 登录后5分钟会话自动断开
**Status**: pending_investigation
**Priority**: Medium
**Created**: 2025-01-29 14:35:00

### Current Bug State

🔴 **Status**: Needs Investigation

This bug hasn't been deeply analyzed yet.

**Recommended Workflow**:
1. Use systematic debugging to find root cause
2. Confirm it's a real bug
3. Fix with TDD

---

### Proceeding with Systematic Debugging...

<Invoking systematic-debugging skill>
```

**After systematic debugging completes:**

```markdown
### Investigation Complete ✅

**Root Cause Found**: session.js hardcodes 300 second timeout

**Evidence**:
- Line 45: `const TIMEOUT = 300; // 5 minutes`
- Should be: `const TIMEOUT = 86400; // 24 hours`

**Updating bug status...**
```

```bash
plugins/progress-tracker/prog update-bug \
  --bug-id "BUG-001" \
  --status "confirmed" \
  --root-cause "session.js line 45: TIMEOUT hardcoded to 300 seconds instead of 86400"
```

```markdown
### 🟢 Bug Confirmed!

**Root Cause**: session.js line 45 hardcodes TIMEOUT to 300 seconds

**Ready for TDD Fix**

<Invoking test-driven-development skill>
```

**After TDD completes:**

```markdown
### ✅ Bug Fixed!

**Fix Applied**:
- Changed TIMEOUT from 300 to 86400 in session.js
- Added test for 24-hour session duration
- All tests passing

**Updating bug status...**
```

```bash
plugins/progress-tracker/prog update-bug \
  --bug-id "BUG-001" \
  --status "fixed" \
  --fix-summary "Updated TIMEOUT constant from 300 to 86400 seconds"
```

```markdown
### 🎉 Bug Fixed!

**BUG-001**: 登录后5分钟会话自动断开

**Fix Summary**:
- Root cause: TIMEOUT hardcoded to 300 seconds
- Fix applied: Changed to 86400 (24 hours)
- Tests: All passing
- Code review: Pending

**Progress Updated**:
- Bug marked as fixed in progress.json
- Bug moved to "Fixed (✅)" section in progress.md

---

### Next Steps

[1] **Test in real environment**: Verify fix works end-to-end
[2] **Run code review**: Verify fix quality
[3] **Commit the fix**: Create git commit

Use `/prog` to see overall project status.
```

## Bug Status Reference

| Status | Icon | Description | Triggered By | Next Action |
|--------|------|-------------|--------------|-------------|
| `pending_investigation` | 🔴 | Quick verified, needs deep analysis | User records bug | Investigate |
| `investigating` | 🟡 | Systematic debugging in progress | User selects bug | Wait/Resume |
| `confirmed` | 🟢 | Real bug, root cause found | Debugging completes | Fix with TDD |
| `fixing` | 🔧 | TDD fix in progress | User starts TDD | Wait/Resume |
| `fixed` | ✅ | Fixed and verified | TDD completes | Commit |
| `false_positive` | ❌ | Not a bug | Investigation proves not bug | Remove from list |

## Priority Reference

### High Priority (🔴)
**Triggers**: "crash", "broken", "fail", "security", "data loss", "崩溃", "失败"
**Characteristics**:
- Blocks critical functionality
- Security vulnerability
- Data loss or corruption
- Wide scope (affects multiple features)

**Scheduling**: Insert before next feature

### Medium Priority (🟡)
**Triggers**: "slow", "error", "wrong", "慢", "错误"
**Characteristics**:
- Affects UX but not blocking
- Narrow scope (single feature)
- Workarounds available

**Scheduling**: Insert after related feature

### Low Priority (🟢)
**Triggers**: "typo", "cosmetic", "minor", "拼写"
**Characteristics**:
- Cosmetic issues
- Edge cases
- Nice-to-have fixes

**Scheduling**: Add to end of itinerary
