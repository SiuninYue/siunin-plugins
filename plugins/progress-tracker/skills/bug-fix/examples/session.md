# Bug Fix Session Example

Complete example of a bug fixing session from report to resolution.

## Context

**Project**: User Authentication System
**Current Feature**: Feature 2 - Password Reset
**Bug Reported**: "登录后5分钟会话自动断开" (Session drops after 5 minutes)

## Session Transcript

### User Action
```
/prog-fix "登录后5分钟会话自动断开"
```

### AI Response - Phase 1: Quick Verification
```
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

### AI Response - Phase 2: User Confirmation
```
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

### User Action
```
1
```

### AI Response - Phase 3: Smart Scheduling
```
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
  2. [ ] Feature 2: Password Reset (in progress)
  3. [ ] Feature 3: Dashboard
  4. [ ] Feature 4: User Profile

After insertion:
  1. [ ] Feature 1: User Authentication
  → [BUG-001] 会话5分钟超时 ← NEW
  2. [ ] Feature 2: Password Reset (in progress)
  3. [ ] Feature 3: Dashboard
  4. [ ] Feature 4: User Profile

**Confirm insertion?** [Y/n]
```

### User Action
```
Y
```

### AI Response - Confirmation
```
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

1. **Continue current work**: Feature 2 implementation not interrupted
2. **Investigate later**: Use `/prog-fix BUG-001` when ready to debug
3. **View backlog**: Use `/prog-fix` to see all bugs

💡 Tip: Bugs are intelligently scheduled to minimize disruption.
```

### User Continues Work
*(User completes Feature 2, then returns to bug)*

### User Action
```
/prog-fix BUG-001
```

### AI Response - Bug Fixing Start
```
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
```

*(Systematic debugging skill executes...)*

### AI Response - Investigation Complete
```
### Investigation Complete ✅

**Root Cause Found**: session.js hardcodes 300 second timeout

**Evidence**:
- File: src/auth/session.js, Line 45
- Code: `const TIMEOUT = 300; // 5 minutes`
- Issue: Should be 86400 (24 hours) for typical web sessions
- Impact: Users are logged out after 5 minutes

**Verification**:
- Reproduced: Yes, session expires after 300 seconds
- Related features confirmed: Feature 1, Feature 3 affected
- Not a config issue: Hardcoded constant in source

**Updating bug status...**
```

### AI Response - Bug Confirmed
```
### 🟢 Bug Confirmed!

**Root Cause**: session.js line 45 hardcodes TIMEOUT to 300 seconds (5 minutes)

**Impact**: Users logged out after 5 minutes of inactivity

**Ready for TDD Fix**
```

*(TDD skill executes...)*

### AI Response - Fix Complete
```
### ✅ Bug Fixed!

**Fix Applied**:
- Changed TIMEOUT from 300 to 86400 seconds (24 hours)
- Added test: `test_session_duration_24h()`
- Added test: `test_session_cleanup_after_expiry()`
- All tests: PASSING

**Code Changes**:
```diff
- const TIMEOUT = 300; // 5 minutes
+ const TIMEOUT = 86400; // 24 hours
```

**Tests Added**:
- test_session_duration_24h: Verifies 24-hour session duration
- test_session_cleanup_after_expiry: Verifies cleanup after expiry

**Updating bug status...**
```

### AI Response - Final State
```
### 🎉 Bug Fixed!

**BUG-001**: 登录后5分钟会话自动断开

**Fix Summary**:
- Root cause: TIMEOUT hardcoded to 300 seconds
- Fix applied: Changed to 86400 (24 hours)
- Tests: 2 new tests, all passing
- Code review: Recommended before commit

**Updated Status**: fixed

### Next Steps

[1] **Test in real environment**: Login and verify session lasts 24h
[2] **Run code review**: Verify fix quality with code-reviewer
[3] **Commit the fix**: Create git commit

**Suggested Commit Message**:
```
fix(session): increase timeout from 5 minutes to 24 hours

- Update TIMEOUT constant from 300 to 86400 seconds
- Add tests for session duration and cleanup
- Fixes BUG-001

Co-Authored-By: Claude <noreply@anthropic.com>
```

Use `/prog` to see overall project status.
```

## Outcome

**Bug Status**: Fixed
**Time to Fix**: ~15 minutes
**Tests Added**: 2
**Breaking Changes**: None

**Key Success Factors**:
1. Quick verification identified likely real bug
2. Smart scheduling didn't interrupt current work
3. Systematic debugging found exact root cause
4. TDD ensured fix works and has tests
5. Clear commit message with bug reference
