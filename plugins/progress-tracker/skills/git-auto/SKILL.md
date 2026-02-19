---
name: git-auto
description: This skill should be used when the user asks to "create a git commit", "commit changes", "commit and push", "make a commit", "handle git", "git auto", "git auto start", "git auto done", or "git auto fix", or needs git operations automated with branch/PR/merge decisions.
model: sonnet
version: "1.1.0"
scope: skill
inputs:
  - Current git repository state
  - Optional user intent (feature/bug/refactor)
  - Optional repository protection rules and CI/review signals
outputs:
  - Execution plan with reasons, enforcement mode, and escalation reason
  - Execution results after confirmation
evidence: optional
references: []
---

# Git Auto

Intelligent Git automation that analyzes repository state and decides branch, commit, push, PR, and merge actions with explicit governance rules.

## Purpose

Eliminate Git decision fatigue while enforcing stable collaboration defaults:
- Determine whether to create or reuse a short-lived branch.
- Determine whether to commit and push now or delay for sync recovery.
- Determine whether to create a Draft PR or update an existing PR.
- Determine whether merge can be recommended under current enforcement mode.

## Stable Command Interface

Keep command names unchanged:
- `git auto`
- `git auto start <feature-name>`
- `git auto done`
- `git auto fix <bug-description>`

## When to Use

Invoke this skill when:
- User says "handle git", "git auto", "process changes"
- User wants to commit but isn't sure about branching strategy
- User has changes and wants AI to handle the full workflow
- User wants to automate repetitive Git operations

## Normative Keywords

The terms `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

## Default Collaboration Policy

Apply these defaults unless user gives explicit override:

1. Use trunk-based collaboration with short-lived branches.
2. Treat default branch (`main`/`master`) as protected for day-to-day work.
3. Route all default-branch changes through short-lived branch + Draft PR, including docs/CI by default.
4. Create Draft PR on first push of a new short-lived branch.
5. Recommend squash merge as the default merge strategy.

Mandatory rules:
- `MUST` create or switch to a short-lived branch before committing if current branch is default branch.
- `MUST` create a Draft PR on first push when no PR exists for the branch.
- `MUST NOT` recommend merge when branch is behind or diverged from upstream.
- `SHOULD` rebase on upstream before push/merge recommendation.

## Enforcement Modes

Compute one active mode: `soft`, `hybrid`, or `hard`.

### soft

- Branching: `MUST` use short-lived branch on default branch.
- PR: `MUST` create Draft PR on first push.
- Pull/Rebase: `SHOULD` run `fetch + rebase` at session start and pre-merge.
- Merge recommendation: allow only when no critical sync risk is present.

### hybrid

- Includes all `soft` rules.
- Pull/Rebase: `MUST` run sync checks at session start and pre-merge.
- Merge recommendation: `MUST` require clean sync state + passing CI + review-ready signal.

### hard

- Includes all `hybrid` rules.
- Branching: `MUST NOT` allow direct default-branch commit path in plans.
- Merge recommendation: `MUST` require clean sync state + passing CI + required review approvals + no unresolved blocking discussion.
- Any missing required signal blocks merge recommendation.

## Escalation Threshold Standard (14-day rolling)

Evaluate a 14-day rolling window on every planning run.

### Metrics

1. `sync_risk_events`
   - Count each occurrence of:
     - detached HEAD state
     - diverged branch (ahead > 0 and behind > 0)
     - non-fast-forward push rejection
     - in-progress rebase/merge/cherry-pick/revert conflict state
2. `integration_regressions`
   - Count each revert or hotfix occurring within 24 hours after merge to default branch.
3. `parallel_pressure`
   - `true` when either condition is met:
     - 3+ active contributors in current window
     - high PR concurrency on default branch (multiple concurrent active PRs that materially overlap)

### Transition Rules

Apply transitions exactly:

1. `soft -> hybrid` when:
   - `sync_risk_events >= 2`, or
   - `integration_regressions >= 1`, or
   - `parallel_pressure == true`
2. `hybrid -> hard` when:
   - `sync_risk_events >= 4`, or
   - `integration_regressions >= 2`
3. `hard -> hybrid` when:
   - 14 consecutive clean days with `sync_risk_events = 0` and `integration_regressions = 0`
4. `hybrid -> soft` when:
   - another 14 consecutive clean days with no regression

### Escalation Output Contract

Every generated execution plan `MUST` print:

- `Enforcement Mode: <soft|hybrid|hard>`
- `Escalation Reason: <explicit metric-driven reason>`

## Analysis Process (Revised)

### 1. Preflight Sync Check (Session-Start Node)

Run sync preflight before commit planning:

```bash
git fetch origin --prune
CURRENT_BRANCH=$(git branch --show-current)
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null || true)
BEHIND_AHEAD=$(git rev-list --left-right --count @{upstream}...HEAD 2>/dev/null || echo "0 0")

# Detect operation-in-progress markers
GIT_DIR=$(git rev-parse --absolute-git-dir)
test -e "$GIT_DIR/rebase-merge" -o -e "$GIT_DIR/rebase-apply" -o -e "$GIT_DIR/MERGE_HEAD" \
  -o -e "$GIT_DIR/CHERRY_PICK_HEAD" -o -e "$GIT_DIR/REVERT_HEAD" && echo "operation_in_progress"
```

Block plan execution when critical sync risks exist (detached HEAD, divergence, or operation in progress).

### 2. Gather Context

Collect current run context:

```bash
HAS_CHANGES=$(git status --porcelain | wc -l)
STAGED=$(git diff --cached --name-only)
UNSTAGED=$(git diff --name-only)
UNPUSHED=$(git log @{u}.. 2>/dev/null | wc -l)
RECENT_COMMITS=$(git log --oneline -10)
```

Collect PR context when not on default branch:

```bash
EXISTING_PR=$(gh pr list --head "$CURRENT_BRANCH" --json number,url,title,isDraft,reviewDecision,statusCheckRollup --jq '.[0]' 2>/dev/null)
```

### 3. Compute Enforcement Mode (Pre-Plan Node)

Compute metrics for last 14 days and derive active mode using transition rules.

Minimum required artifacts for planning output:
- mode (`soft|hybrid|hard`)
- reason string with metric values and triggered threshold

### 4. Analyze Change Intent

```bash
git diff --cached --name-only
git diff --name-only

# Categorize for commit message and branch naming:
# - Feature -> feat/<name>
# - Bug fix -> fix/<name>
# - Refactor/chore/docs/ci -> chore/<name> or docs/<name>
```

Default-branch policy:
- If `CURRENT_BRANCH == DEFAULT_BRANCH` and `HAS_CHANGES > 0`, branch creation is mandatory before commit.

### 5. Generate Plan

Always include enforcement metadata:

```
## Plan

Enforcement Mode: hybrid
Escalation Reason: sync_risk_events=2 in last 14 days (threshold: soft -> hybrid)

1. [Create or switch to short-lived branch]
   *Reason: Default branch changes must flow through PR*

2. [Commit changes]
   *Reason: Save atomic, testable unit*

3. [Push to remote]
   *Reason: Share state and enable PR automation*

4. [Create Draft PR on first push, or update existing PR]
   *Reason: Early CI and review feedback*

Confirm? (y/n)
```

## Decision Tree (Replaced)

```
┌──────────────────────────────────────────────────────────────┐
│                    RUN SYNC PREFLIGHT                        │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────────────┐
              │ Critical sync risk present?  │
              └──────────────┬───────────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
                YES                     NO
                 │                       │
                 ▼                       ▼
      "Stop and resolve sync"   Compute enforcement mode
                                         │
                                         ▼
                           ┌────────────────────────┐
                           │ Any changes to commit? │
                           └───────────┬────────────┘
                                       │
                           ┌───────────┴───────────┐
                           │                       │
                          NO                      YES
                           │                       │
                           ▼                       ▼
                    "Nothing to do"      On default branch?
                                                  │
                                      ┌───────────┴───────────┐
                                      │                       │
                                     YES                      NO
                                      │                       │
                                      ▼                       ▼
                           Create short-lived branch      Commit
                                      │                       │
                                      └───────────┬───────────┘
                                                  │
                                                  ▼
                                               Push
                                                  │
                                                  ▼
                                     Existing PR for branch?
                                                  │
                                      ┌───────────┴───────────┐
                                      │                       │
                                     YES                      NO
                                      │                       │
                                      ▼                       ▼
                                 Update PR            Create Draft PR
                                      │                       │
                                      └───────────┬───────────┘
                                                  │
                                                  ▼
                                         Merge requested?
                                                  │
                                      ┌───────────┴───────────┐
                                      │                       │
                                     NO                      YES
                                      │                       │
                                      ▼                       ▼
                                   Finish        Run pre-merge sync check
                                                           │
                                                           ▼
                                         Behind/diverged or gate fail?
                                                           │
                                            ┌──────────────┴──────────────┐
                                            │                             │
                                           YES                           NO
                                            │                             │
                                            ▼                             ▼
                                  Block merge recommendation     Recommend squash merge
```

## Execution Flow

### Step 1: Present Plan

Show actions and governance state:

```
Found 3 modified files:
  - src/auth/login.ts (new feature)
  - src/auth/types.ts (new types)
  - tests/auth.test.ts (tests)

## Execution Plan

Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days

1. Create branch feat/login-system
   *Reason: Default branch changes must flow through PR*

2. Stage and commit changes
   *Reason: 3 files ready, atomic change unit*

3. Push to remote
   *Reason: Enable Draft PR and CI*

4. Create Draft PR
   *Reason: First push should open Draft PR for early feedback*

Execute this plan? [y/n]
```

### Step 2: Wait for Confirmation

DO NOT execute until user confirms with "y" or "yes".

### Step 3: Execute Operations

Execute in order, reporting each step:

```bash
# Step 1: Create branch
git switch -c feat/login-system

# Step 2: Commit
git add src/auth/ tests/auth.test.ts
git commit -m "feat: implement login system

- Add login endpoint with JWT
- Add type definitions
- Add unit tests

Co-Authored-By: Claude <noreply@anthropic.com>"

# Step 3: Push
git push -u origin feat/login-system

# Step 4: Create Draft PR on first push
gh pr create --draft --title "feat: implement login system" --body "..." --base main
```

### Step 4: Report Results

```
✓ Created branch: feat/login-system
✓ Committed: abc123def (feat: implement login system)
✓ Pushed to origin/feat/login-system
✓ Created Draft PR: https://github.com/user/repo/pull/42

Next: Use '/review' to get AI code review
```

## Scenarios

### Scenario A: Small documentation fix on main

```
## Execution Plan

Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days

1. Create branch docs/update-readme
   *Reason: Default-branch docs changes also use branch + PR by default*

2. Commit and push
   *Reason: Save and share update*

3. Create Draft PR
   *Reason: First push on new branch*

Execute? [y/n]
```

### Scenario B: Feature implementation on main

```
## Execution Plan

Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days

1. Create branch feat/feature-name
   *Reason: Feature work should use branches*

2. Stage and commit changes
   *Reason: 5 files implementing new feature*

3. Push to remote
   *Reason: Enable review*

4. Create Draft PR
   *Reason: New branch first push should create Draft PR*

Execute? [y/n]
```

### Scenario C: Additional commit on feature branch with PR

```
## Execution Plan

Enforcement Mode: hybrid
Escalation Reason: sync_risk_events=2 in last 14 days

1. Commit changes
   *Reason: Continuing work on feature-xyz*

2. Push to remote
   *Reason: Update existing PR #42*

3. Re-evaluate enforcement mode after push
   *Reason: Thresholds may have changed during active work*

No new PR created (existing PR auto-updates)

Execute? [y/n]
```

### Scenario D: Bug fix

```
## Execution Plan

Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days

1. Create branch fix/bug-description
   *Reason: Bug fix should use branch for tracking*

2. Stage and commit changes
   *Reason: Fix for reported issue*

3. Push to remote
   *Reason: Enable review*

4. Create Draft PR
   *Reason: Bug fix needs verification and CI feedback*

Execute? [y/n]
```

### Scenario E: Escalation from soft to hybrid

```
Observed metrics in last 14 days:
- sync_risk_events=2
- integration_regressions=0
- parallel_pressure=false

Transition:
soft -> hybrid

Action:
- Keep branch + Draft PR workflow
- Enforce CI + review-ready gate before merge recommendation
```

### Scenario F: No changes

```
No changes detected. Working directory is clean.

To create a new branch for upcoming work, specify:
"git auto start feature-name"
```

## Return Values

- **Success**: Summary of executed operations with results
- **No changes**: Notify user, suggest alternative actions
- **Cancelled**: User cancelled execution
- **Error**: Specific error with recovery suggestion

## Advanced Usage

### Starting New Work

User can specify intent to skip some analysis:

```
"git auto start feature-name"
→ Creates branch, evaluates mode, and prepares Draft-PR path
```

### Finishing Feature

```
"git auto done"
→ Commits, pushes, creates Draft PR if needed, and applies merge gates by mode
```

### Quick Fix

```
"git auto fix bug-description"
→ Creates fix branch, commits, pushes, creates Draft PR
```

## Error Handling

### Branch already exists

```
Branch feat/xyz already exists.
Options:
1. Switch to existing branch
2. Create with different name
3. Commit on current branch
```

### Push rejected

```
Push rejected (remote has changes).
Plan:
1. git fetch origin
2. git rebase @{upstream}
3. Re-evaluate enforcement mode
4. Retry push

Reason: non-fast-forward rejection counts as sync_risk_event.
Execute? [y/n]
```

### PR creation failed

```
PR creation failed: A draft PR already exists.
Plan: Update draft PR instead.
Execute? [y/n]
```

### Mode escalation during current run

```
Enforcement mode changed during execution: soft -> hybrid
Trigger: sync_risk_events reached threshold in rolling 14-day window

Plan adjustment:
1. Continue commit/push
2. Keep PR in Draft or review-ready state
3. Block merge recommendation until hybrid gates are satisfied

Execute adjusted plan? [y/n]
```

## Merge Gate Summary

Before any merge recommendation, run pre-merge sync check and mode gate:

1. Sync gate (all modes): no detached HEAD, no operation in progress, not behind, not diverged.
2. soft mode: sync gate required.
3. hybrid mode: sync gate + passing CI + review-ready signal required.
4. hard mode: sync gate + passing CI + required approvals + no blocking discussion required.

Default merge recommendation:
- `SHOULD` recommend squash merge when all mode gates pass.

## Assumptions and Defaults

1. Rolling window is fixed at 14 days.
2. Escalation is progressive (`soft -> hybrid -> hard`) and de-escalates with clean windows.
3. This is policy-first guidance and does not require immediate hook-level hard blocking.
