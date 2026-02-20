---
name: git-auto
description: This skill should be used when the user asks to "create a git commit", "commit changes", "commit and push", "make a commit", "handle git", "git auto", "git auto start", "git auto done", or "git auto fix", or needs git operations automated with branch/PR/merge decisions.
model: sonnet
version: "1.2.0"
scope: skill
inputs:
  - Current git repository state
  - Optional user intent (feature/bug/refactor)
  - Optional repository protection rules and CI/review signals
  - Optional complexity/scope hint for worktree decision
outputs:
  - Execution plan with reasons, enforcement mode, escalation reason, workspace mode, and worktree decision reason
  - Execution results after confirmation
evidence: optional
references:
  - "using-git-worktrees"
---

# Git Auto

Intelligent Git automation that analyzes repository state and decides branch, worktree, commit, push, PR, and merge actions with explicit governance rules.

## Purpose

Eliminate Git decision fatigue while enforcing stable collaboration defaults:
- Determine whether to use in-place workspace or worktree isolation.
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
- User wants to commit but isn't sure about branching/worktree strategy
- User has changes and wants AI to handle the full workflow
- User wants to automate repetitive Git operations

## Normative Keywords

The terms `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

## Default Collaboration Policy

Apply these defaults unless user gives explicit override:

1. Use trunk-based collaboration with short-lived branches.
2. Treat default branch (`main`/`master`) as protected for day-to-day work.
3. Route default-branch changes through short-lived branch + Draft PR, including docs/CI by default.
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
- Pull/Rebase: `SHOULD` run sync checks at session start and pre-merge.
- Merge recommendation: allow only when no critical sync risk is present.

### hybrid

- Includes all `soft` rules.
- Pull/Rebase: `MUST` run sync checks at session start and pre-merge.
- Merge recommendation: `MUST` require clean sync state + passing CI + review-ready signal.

### hard

- Includes all `hybrid` rules.
- Branching: `MUST NOT` allow direct default-branch commit path in plans.
- Worktree: `MUST` isolate new feature/large refactor starts in worktree.
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

## Worktree Decision Gate

Run this gate before branch creation.

### Required Inputs

- Current branch and default branch
- Working tree cleanliness
- Upstream divergence and sync risks
- `parallel_pressure` signal
- `branch_checked_out_elsewhere` signal (from git-sync analysis)
- Optional complexity/scope hint (single-file vs multi-module)

### Decision Rules

#### MUST use worktree (any one is true)

1. New work starts from default branch and local working tree has unrelated/unclassified changes.
2. `parallel_pressure == true`.
3. `branch_checked_out_elsewhere` detected (same branch checked out in another worktree/session).
4. `Enforcement Mode == hard` and work is a new feature or large refactor.

#### SHOULD use worktree (any one is true)

1. `Enforcement Mode == hybrid` and change scope is medium/high (multi-module or broad diff).
2. User explicitly requests isolated development.

#### MAY keep in-place (all are true)

1. Continuing iteration on a non-default branch with an existing PR.
2. Working tree is clean and no parallel conflict signals exist.
3. No high-risk gate is triggered.

### Idempotency Rules

1. If already inside target worktree, `MUST` reuse and skip creation.
2. If worktree for target branch already exists, `MUST` switch/reuse instead of creating duplicate.

### Delegation Boundary

When worktree mode is selected, invoke:

```text
Skill("using-git-worktrees", args="Set up isolated workspace for <branch-or-feature>")
```

`git-auto` owns *when* to use worktree.
`using-git-worktrees` owns directory selection, ignore verification, baseline setup, and readiness checks.

### Workspace Output Contract

Every generated execution plan `MUST` print:

- `Workspace Mode: <in-place|worktree>`
- `Worktree Decision Reason: <triggered rule(s)>`

## Analysis Process (Revised)

### 1. Session Preflight (Sync Node)

Run sync preflight before planning:

```bash
git fetch origin --prune
CURRENT_BRANCH=$(git branch --show-current)
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null || true)
BEHIND_AHEAD=$(git rev-list --left-right --count @{upstream}...HEAD 2>/dev/null || echo "0 0")

GIT_DIR=$(git rev-parse --absolute-git-dir)
test -e "$GIT_DIR/rebase-merge" -o -e "$GIT_DIR/rebase-apply" -o -e "$GIT_DIR/MERGE_HEAD" \
  -o -e "$GIT_DIR/CHERRY_PICK_HEAD" -o -e "$GIT_DIR/REVERT_HEAD" && echo "operation_in_progress"
```

Block plan execution when critical sync risks exist (detached HEAD, divergence, operation in progress).

### 2. Compute Enforcement Mode

Compute 14-day metrics and select mode (`soft|hybrid|hard`) with explicit reason.

### 3. Worktree Decision Gate

Decide `Workspace Mode` and `Worktree Decision Reason` before any branch/commit step.

### 4. Analyze Change Intent and Branch Strategy

```bash
git diff --cached --name-only
git diff --name-only
```

Categorize for commit/branch naming:
- Feature -> `feat/<name>`
- Bug fix -> `fix/<name>`
- Refactor/chore/docs/ci -> `chore/<name>` or `docs/<name>`

### 5. Generate Plan

Always include all four control fields:

```
## Plan

Enforcement Mode: hybrid
Escalation Reason: sync_risk_events=2 in last 14 days (threshold: soft -> hybrid)
Workspace Mode: worktree
Worktree Decision Reason: default branch + unrelated local changes

1. [Worktree setup or reuse]
   *Reason: triggered worktree gate*

2. [Create or switch to short-lived branch]
   *Reason: default branch changes must flow through PR*

3. [Commit changes]
4. [Push to remote]
5. [Create Draft PR on first push, or update existing PR]

Confirm? (y/n)
```

## Decision Tree (Worktree-First)

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
                           Run Worktree Decision Gate
                                         │
                                         ▼
                          Workspace Mode: in-place/worktree
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                               │
             worktree                                        in-place
                 │                                               │
                 ▼                                               ▼
      Call using-git-worktrees                         Continue current workspace
                 │                                               │
                 └───────────────────────┬───────────────────────┘
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

```
## Execution Plan

Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days
Workspace Mode: worktree
Worktree Decision Reason: default branch + unrelated local changes

1. Set up or reuse worktree
2. Create branch feat/login-system
3. Stage and commit changes
4. Push to remote
5. Create Draft PR

Execute this plan? [y/n]
```

### Step 2: Wait for Confirmation

Do not execute until user confirms.

### Step 3: Execute Operations

When `Workspace Mode=worktree`, call `using-git-worktrees` first, then continue commit/push/PR steps in that workspace.

## Scenarios

### Scenario A: `main + dirty` (must use worktree)

```
Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days
Workspace Mode: worktree
Worktree Decision Reason: MUST rule #1 (default branch start + unrelated local changes)

Action: call using-git-worktrees, then create branch and Draft PR.
```

### Scenario B: active feature branch + open PR + clean (in-place)

```
Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days
Workspace Mode: in-place
Worktree Decision Reason: MAY rule satisfied (existing feature PR iteration)

Action: commit + push, update existing PR.
```

### Scenario C: `branch_checked_out_elsewhere` detected

```
Enforcement Mode: hybrid
Escalation Reason: sync risk elevated
Workspace Mode: worktree
Worktree Decision Reason: MUST rule #3 (branch_checked_out_elsewhere)

Action: isolate work in separate worktree to avoid concurrent branch writes.
```

### Scenario D: already in worktree (reuse)

```
Workspace Mode: worktree
Worktree Decision Reason: idempotent reuse; target worktree already active

Action: skip creation, continue in current isolated workspace.
```

### Scenario E: hybrid + medium/high scope

```
Workspace Mode: worktree
Worktree Decision Reason: SHOULD rule #1 (hybrid mode + medium/high scope)
```

### Scenario F: hard + new feature start

```
Workspace Mode: worktree
Worktree Decision Reason: MUST rule #4 (hard mode + new feature/large refactor)
```

## Return Values

- **Success**: Summary of executed operations with results
- **No changes**: Notify user and suggest next action
- **Cancelled**: User cancelled execution
- **Error**: Specific error with recovery suggestion

## Error Handling

### Worktree directory not ignored

```
Worktree directory is not ignored.
Plan:
1. add ignore rule (.worktrees/ or worktrees/)
2. commit ignore fix
3. continue worktree creation
```

### Worktree branch conflict

```
Target branch already has an existing worktree.
Plan: switch/reuse existing worktree path instead of creating duplicate.
```

### Duplicate worktree request

```
Current workspace already matches target worktree.
Plan: reuse current workspace and continue.
```

### Push rejected

```
Push rejected (remote has changes).
Plan:
1. git fetch origin
2. git rebase @{upstream}
3. re-evaluate enforcement/worktree decisions
4. retry push
```

### PR creation failed

```
PR creation failed: draft PR already exists.
Plan: update existing draft PR.
```

### Mode escalation during current run

```
Enforcement mode changed during execution: soft -> hybrid
Plan adjustment: keep PR draft/review-ready and enforce stricter merge gates.
```

## Merge Gate Summary

Before any merge recommendation, run pre-merge sync check and mode gates:

1. Sync gate (all modes): no detached HEAD, no operation in progress, not behind, not diverged.
2. `soft`: sync gate required.
3. `hybrid`: sync gate + passing CI + review-ready signal.
4. `hard`: sync gate + passing CI + required approvals + no blocking discussion.

Default merge recommendation:
- `SHOULD` recommend squash merge when all gates pass.

## Assumptions and Defaults

1. Rolling window is fixed at 14 days.
2. Escalation is progressive (`soft -> hybrid -> hard`) and de-escalates with clean windows.
3. This is policy-first guidance and does not require immediate hook-level hard blocking.
