---
name: git-auto
description: Use when user asks to "create a git commit", "commit changes", "commit and push", "make a commit", "handle git", "git auto", or needs git operations automated. Intelligently analyzes state and decides when to create branches, commit, push, create PR, or merge. Shows plan with reasons before executing.
model: sonnet
version: "1.0.0"
scope: skill
inputs:
  - Current git repository state
  - Optional user intent (feature/bug/refactor)
outputs:
  - Execution plan with reasons
  - Execution results after confirmation
evidence: optional
---

# Git Auto

Intelligent Git automation that analyzes the current state and automatically decides what Git operations are needed.

## Purpose

Eliminate Git decision fatigue by letting AI analyze the context and automatically determine:
- Whether to create a new branch
- Whether to commit changes
- Whether to push
- Whether to create/update a PR
- Whether to merge to main

## When to Use

Invoke this skill when:
- User says "handle git", "git auto", "process changes"
- User wants to commit but isn't sure about branching strategy
- User has changes and wants AI to handle the full workflow
- User wants to automate repetitive Git operations

## Analysis Process

### 1. Gather Context

First, analyze the current state:

```bash
# Current state
CURRENT_BRANCH=$(git branch --show-current)
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')

# Check for changes
HAS_CHANGES=$(git status --porcelain | wc -l)
CHANGES_TYPE=$(git diff --name-only | head -5)

# Check for unpushed commits
UNPUSHED=$(git log @{u}.. 2>/dev/null | wc -l)

# Check for existing PR
if [[ "$CURRENT_BRANCH" != "$DEFAULT_BRANCH" ]]; then
    EXISTING_PR=$(gh pr list --head $CURRENT_BRANCH --json url,number,title --jq '.[0]' 2>/dev/null)
fi

# Recent commits (for context)
RECENT_COMMITS=$(git log --oneline -5)
```

### 2. Analyze Changes

Categorize the changes to determine strategy:

```bash
# What files changed?
git diff --cached --name-only
git diff --name-only

# Categorize:
# - New feature implementation → new feature branch
# - Bug fix → can be quick-fix branch or feature branch
# - Documentation/refactor → depends on scope
# - Configuration/CI → usually main branch is fine
```

### 3. Generate Plan

Based on the analysis, generate a plan with reasons:

```
## Plan

1. [Create branch feature-xxx]
   *Reason: You're on main with functional changes*

2. [Commit changes]
   *Reason: 3 files modified, ready to save*

3. [Push to remote]
   *Reason: Need to share changes for review*

4. [Create PR]
   *Reason: Feature branch, no existing PR*

Confirm? (y/n)
```

## Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│                    ANALYZE CURRENT STATE                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────────┐
            │   Any changes to commit?   │
            └────────────┬───────────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
           NO                       YES
            │                         │
            ▼                         ▼
      "Nothing to do"      ┌────────────────────┐
                          │  On main/master?   │
                          └─────────┬──────────┘
                                    │
                       ┌────────────┴────────────┐
                       │                         │
                      YES                       NO
                       │                         │
                       ▼                         ▼
         ┌─────────────────────┐       ┌──────────────────┐
         │  Change type?       │       │  Commit & Push   │
         └──────────┬──────────┘       └─────────┬────────┘
                    │                            │
       ┌────────────┼────────────┐              │
       │            │            │              │
   Feature      Bug fix      Docs/CI           │
       │            │            │              │
       ▼            ▼            ▼              ▼
  New branch   New branch   Commit     Check existing PR
       │            │       (on main)          │
       └────────────┼─────────────────────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │  After commit/push   │
         └──────────┬───────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │  Has existing PR?   │
         └──────────┬──────────┘
                    │
          ┌─────────┴─────────┐
         YES                  NO
          │                   │
          ▼                   ▼
    "PR exists"          Create PR
```

## Execution Flow

### Step 1: Present Plan

Show the user what will happen and why:

```
Found 3 modified files:
  - src/auth/login.ts (new feature)
  - src/auth/types.ts (new types)
  - tests/auth.test.ts (tests)

## Execution Plan

1. Create branch feat/login-system
   *Reason: Functional changes on main branch*

2. Stage and commit changes
   *Reason: 3 files ready, implementing login feature*

3. Push to remote
   *Reason: Enable PR creation and review*

4. Create PR
   *Reason: No existing PR for this branch*

Execute this plan? [y/n]
```

### Step 2: Wait for Confirmation

DO NOT execute until user confirms with "y" or "yes".

### Step 3: Execute Operations

Execute in order, reporting each step:

```bash
# Step 1: Create branch
git checkout -b feat/login-system

# Step 2: Commit
git add src/auth/ tests/auth.test.ts
git commit -m "feat: implement login system

- Add login endpoint with JWT
- Add type definitions
- Add unit tests

Co-Authored-By: Claude <noreply@anthropic.com>"

# Step 3: Push
git push -u origin feat/login-system

# Step 4: Create PR
gh pr create --title "feat: implement login system" --body "..." --base main
```

### Step 4: Report Results

```
✓ Created branch: feat/login-system
✓ Committed: abc123def (feat: implement login system)
✓ Pushed to origin/feat/login-system
✓ Created PR: https://github.com/user/repo/pull/42

Next: Use '/review' to get AI code review
```

## Scenarios

### Scenario A: Small documentation fix on main

```
## Execution Plan

1. Commit changes
   *Reason: Minor doc update on main is fine*

2. Push to remote
   *Reason: Backup and share changes*

Execute? [y/n]
```

### Scenario B: Feature implementation on main

```
## Execution Plan

1. Create branch feat/feature-name
   *Reason: Feature work should use branches*

2. Stage and commit changes
   *Reason: 5 files implementing new feature*

3. Push to remote
   *Reason: Enable review*

4. Create PR
   *Reason: New feature needs review*

Execute? [y/n]
```

### Scenario C: Additional commit on feature branch with PR

```
## Execution Plan

1. Commit changes
   *Reason: Continuing work on feature-xyz*

2. Push to remote
   *Reason: Update existing PR #42*

No new PR needed (existing PR will auto-update)

Execute? [y/n]
```

### Scenario D: Bug fix

```
## Execution Plan

1. Create branch fix/bug-description
   *Reason: Bug fix should use branch for tracking*

2. Stage and commit changes
   *Reason: Fix for reported issue*

3. Push to remote
   *Reason: Enable review*

4. Create PR
   *Reason: Bug fix needs verification*

Execute? [y/n]
```

### Scenario E: No changes

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
→ Creates branch immediately, ready for work
```

### Finishing Feature

```
"git auto done"
→ Commits, pushes, creates PR if needed
```

### Quick Fix

```
"git auto fix bug-description"
→ Creates fix branch, commits, pushes, creates PR
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
Plan: Pull rebase first, then push.
Execute? [y/n]
```

### PR creation failed

```
PR creation failed: A draft PR already exists.
Plan: Update draft PR instead.
Execute? [y/n]
```
